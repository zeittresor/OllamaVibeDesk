from __future__ import annotations

import argparse
import re
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DEFAULT_START_URL = "https://www.ard-text.de/mobil/100"
DEFAULT_FILENAME = "news.pdf"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0 Safari/537.36 TeletextNewsPDF/1.1"
)
TIMEOUT = 20
MAX_PAGES_PER_CATEGORY = 250

NAV_STOP_LABELS = {
    "ansicht aktualisieren",
    "zur vorigen seite zurückblättern",
    "zur vorige seite zurückblättern",
    "zur nächste seite blättern",
    "zur naechste seite blättern",
    "zur naechste seite blattern",
    "zurück zur zuletzt aufgerufenen seite im browser",
    "zuruck zur zuletzt aufgerufenen seite im browser",
    "home",
    "inhalt",
    "impressum",
    "datenschutz",
}

CONTENT_STOP_PREFIXES = (
    "weitere textseiten",
    "home",
    "inhalt",
    "impressum",
    "datenschutz",
    "zurück zur zuletzt aufgerufenen seite im browser",
    "zuruck zur zuletzt aufgerufenen seite im browser",
    "ansicht aktualisieren",
    "zur vorigen seite zurückblättern",
    "zur vorigen seite zuruckblattern",
    "zur nächste seite blättern",
    "zur naechste seite",
    ">>",
)

EXCLUDED_PAGE_NUMBERS = {100, 790, 899}

EXCLUDED_CATEGORY_KEYWORDS = {
    "tv-programm",
    "fernsehprogramm",
    "fernsehen",
    "programm",
    "das erste",
    "ard-alpha",
    "one",
    "phoenix",
    "arte",
    "3sat",
    "kika",
    "tv",
    "sport",
    "fussball",
    "fußball",
    "bundesliga",
    "champions league",
    "europa league",
    "conference league",
    "tennis",
    "formel 1",
    "motorsport",
    "handball",
    "basketball",
    "eishockey",
    "biathlon",
    "olympia",
}

EXCLUDED_PAGE_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\btv-?programm\b",
        r"\bfernsehprogramm\b",
        r"\bheute im tv\b",
        r"\bprogrammvorschau\b",
        r"\bsendungen?\b",
    )
]

SPORT_PAGE_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bsport\b",
        r"\bfussball\b",
        r"\bfußball\b",
        r"\bbundesliga\b",
        r"\b2\.\s*bundesliga\b",
        r"\b3\.\s*liga\b",
        r"\bchampions\s+league\b",
        r"\beuropa\s+league\b",
        r"\bconference\s+league\b",
        r"\bdfb-?pokal\b",
        r"\btennis\b",
        r"\bformel\s*1\b",
        r"\bmotorsport\b",
        r"\bhandball\b",
        r"\bbasketball\b",
        r"\beishockey\b",
        r"\bbiathlon\b",
        r"\bolympia\b",
        r"\bspieltag\b",
        r"\bliga\b",
        r"\btrainer\b",
        r"\bverein\b",
    )
]


@dataclass
class TeletextLink:
    label: str
    url: str
    page_number: int | None


@dataclass
class PageData:
    url: str
    page_number: int | None
    title: str
    subtitle: str
    body: str
    teaser_links: list[TeletextLink] = field(default_factory=list)


@dataclass
class CategoryData:
    label: str
    root_url: str
    root_page_number: int | None
    pages: list[PageData] = field(default_factory=list)


def repair_mojibake(value: str) -> str:
    text = value or ""
    text = text.replace("\ufeff", "")
    if not text:
        return ""
    suspicious = ("Ã", "Â", "â", "ð", "¤", "�")
    if any(token in text for token in suspicious):
        for source_encoding in ("latin-1", "cp1252"):
            try:
                repaired = text.encode(source_encoding).decode("utf-8")
            except Exception:
                continue
            if repaired and repaired.count("Ã") < text.count("Ã"):
                text = repaired
                break
    return text


def normalize_text(value: str) -> str:
    value = repair_mojibake(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    cleaned_path = re.sub(r"/+", "/", parsed.path)
    return parsed._replace(path=cleaned_path, fragment="").geturl()


def page_number_from_url(url: str) -> int | None:
    match = re.search(r"/(\d{3,4})(?:$|[/?#])", url)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_teletext_page_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return page_number_from_url(url) is not None


def is_generic_nav_label(label: str) -> bool:
    cleaned = normalize_text(label).lower()
    if not cleaned:
        return True
    return cleaned in NAV_STOP_LABELS or cleaned == "dark"


def should_exclude_category_label(label: str) -> bool:
    lowered = normalize_text(label).lower()
    if not lowered:
        return True
    for keyword in EXCLUDED_CATEGORY_KEYWORDS:
        if keyword in lowered:
            return True
    return False


def should_exclude_page_content(
    title: str,
    subtitle: str,
    body: str,
    include_sports: bool = False,
) -> bool:
    clean_title = normalize_text(title)
    clean_subtitle = normalize_text(subtitle)
    clean_body = normalize_text(body)
    combined = " ".join(part for part in (clean_title, clean_subtitle, clean_body) if part).lower()
    if not combined:
        return False
    if any(pattern.search(combined) for pattern in EXCLUDED_PAGE_PATTERNS):
        return True
    if not include_sports:
        headline_area = " ".join(part for part in (clean_title, clean_subtitle) if part).lower()
        headline_hits = sum(1 for pattern in SPORT_PAGE_PATTERNS if pattern.search(headline_area))
        total_hits = sum(1 for pattern in SPORT_PAGE_PATTERNS if pattern.search(combined))
        if headline_hits >= 1 or total_hits >= 2:
            return True
    return False


def extract_link_label(anchor) -> str:
    text = normalize_text(anchor.get_text(" ", strip=True))
    text = re.sub(r"\s+\d{3,4}$", "", text).strip()
    return text


def extract_teletext_links(soup: BeautifulSoup, base_url: str) -> list[TeletextLink]:
    results: list[TeletextLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        absolute_url = normalize_url(urljoin(base_url, anchor["href"]))
        if not is_teletext_page_url(absolute_url):
            continue
        label = extract_link_label(anchor)
        page_number = page_number_from_url(absolute_url)
        key = f"{absolute_url}|{label}"
        if key in seen:
            continue
        seen.add(key)
        results.append(TeletextLink(label=label, url=absolute_url, page_number=page_number))
    return results


def extract_top_navigation_links(soup: BeautifulSoup, base_url: str) -> list[TeletextLink]:
    body = soup.body or soup
    first_heading = body.find(re.compile(r"^h[1-6]$", re.I))
    nav_links: list[TeletextLink] = []
    seen_pages: set[int] = set()

    for element in body.descendants:
        if first_heading is not None and element is first_heading:
            break
        if getattr(element, "name", None) != "a":
            continue
        href = element.get("href")
        if not href:
            continue
        url = normalize_url(urljoin(base_url, href))
        if not is_teletext_page_url(url):
            continue
        label = extract_link_label(element)
        page_number = page_number_from_url(url)
        if page_number is None or page_number in EXCLUDED_PAGE_NUMBERS:
            continue
        if is_generic_nav_label(label):
            continue
        if should_exclude_category_label(label):
            continue
        if page_number in seen_pages:
            continue
        seen_pages.add(page_number)
        nav_links.append(TeletextLink(label=label or f"Page {page_number}", url=url, page_number=page_number))

    return nav_links


def extract_all_candidate_category_links(soup: BeautifulSoup, base_url: str) -> list[TeletextLink]:
    candidates = []
    seen_pages: set[int] = set()
    for link in extract_teletext_links(soup, base_url):
        if link.page_number is None or link.page_number in EXCLUDED_PAGE_NUMBERS:
            continue
        if is_generic_nav_label(link.label):
            continue
        if should_exclude_category_label(link.label):
            continue
        if not link.label:
            continue
        if link.page_number in seen_pages:
            continue
        seen_pages.add(link.page_number)
        candidates.append(link)
    return candidates


def extract_heading_text(soup: BeautifulSoup, tag_names: Iterable[str]) -> str:
    heading = soup.find(list(tag_names))
    if heading:
        return normalize_text(heading.get_text(" ", strip=True))
    return ""


def extract_body_and_teasers(lines: list[str], title: str, subtitle: str) -> tuple[str, list[str]]:
    start_after = subtitle or title
    start_index = -1
    for idx, line in enumerate(lines):
        if normalize_text(line) == normalize_text(start_after):
            start_index = idx + 1
            break
    if start_index < 0:
        for idx, line in enumerate(lines):
            if normalize_text(line) == normalize_text(title):
                start_index = idx + 1
                break
    if start_index < 0:
        start_index = 0

    body_lines: list[str] = []
    teaser_lines: list[str] = []

    for raw_line in lines[start_index:]:
        line = normalize_text(raw_line)
        lower = line.lower()
        if not line:
            if body_lines and body_lines[-1] != "":
                body_lines.append("")
            continue
        if any(lower.startswith(prefix) for prefix in CONTENT_STOP_PREFIXES):
            if line.startswith(">>"):
                teaser_lines.append(line)
            break
        if re.fullmatch(r"\d{3,4}", line):
            continue
        body_lines.append(line)

    if len([line for line in body_lines if line]) < 2:
        for raw_line in lines[start_index:]:
            line = normalize_text(raw_line)
            if line.startswith(">>"):
                teaser_lines.append(line)

    paragraphs: list[str] = []
    current: list[str] = []
    for line in body_lines:
        if line == "":
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current))

    body = "\n\n".join(paragraphs).strip()
    teaser_lines = [line for line in teaser_lines if line]
    return body, teaser_lines


def extract_page_data(soup: BeautifulSoup, url: str) -> PageData:
    page_number = page_number_from_url(url)
    title = extract_heading_text(soup, ["h1"])
    subtitle = extract_heading_text(soup, ["h2", "h3"])
    if not title:
        title = normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else f"Page {page_number or '?'}"

    text_lines = [repair_mojibake(line.rstrip()) for line in soup.get_text("\n").splitlines()]
    body, _ = extract_body_and_teasers(text_lines, title, subtitle)
    teaser_links = extract_teletext_links(soup, url)

    if not body:
        relevant_teasers = []
        for link in teaser_links:
            if link.page_number in EXCLUDED_PAGE_NUMBERS:
                continue
            if is_generic_nav_label(link.label):
                continue
            if not link.label:
                continue
            relevant_teasers.append(f"- {normalize_text(link.label)}")
        if relevant_teasers:
            body = "Related subpages:\n" + "\n".join(relevant_teasers[:30])

    return PageData(
        url=url,
        page_number=page_number,
        title=normalize_text(title),
        subtitle=normalize_text(subtitle),
        body=normalize_text(body).replace(" \n ", "\n").strip(),
        teaser_links=teaser_links,
    )


def should_keep_page(page: PageData, include_sports: bool = False) -> bool:
    if page.page_number in EXCLUDED_PAGE_NUMBERS:
        return False
    if should_exclude_page_content(page.title, page.subtitle, page.body, include_sports=include_sports):
        return False
    if page.page_number is None:
        return bool(page.body)
    return bool(page.body or page.subtitle)


def should_follow_link(
    link: TeletextLink,
    current_url: str,
    root_page_number: int | None,
    all_root_pages: set[int],
    include_sports: bool = False,
) -> bool:
    if link.page_number is None:
        return False
    if link.page_number in EXCLUDED_PAGE_NUMBERS:
        return False
    if is_generic_nav_label(link.label):
        return False

    lowered_label = normalize_text(link.label).lower()
    if not include_sports and any(pattern.search(lowered_label) for pattern in SPORT_PAGE_PATTERNS):
        return False
    if any(lowered_label.startswith(prefix) for prefix in CONTENT_STOP_PREFIXES[:-1]):
        return False

    current_page_number = page_number_from_url(current_url)
    if current_page_number is not None and link.page_number == current_page_number:
        return False

    if link.page_number in all_root_pages and link.page_number != root_page_number:
        return False

    return True


def escape_para(text: str) -> str:
    return (
        repair_mojibake(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def story_headline_for_page(page: PageData) -> str:
    headline = page.subtitle or page.title
    headline = normalize_text(headline)
    headline = re.sub(r"^seite\s+\d{3,4}\s*[-:]\s*", "", headline, flags=re.I)
    return headline or "Untitled entry"


def story_context_for_page(page: PageData) -> str:
    if page.subtitle and page.title and normalize_text(page.subtitle).lower() != normalize_text(page.title).lower():
        return normalize_text(page.title)
    return ""


def register_fonts() -> None:
    if "TeletextSans" in pdfmetrics.getRegisteredFontNames():
        return

    import reportlab

    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    regular = font_dir / "Vera.ttf"
    bold = font_dir / "VeraBd.ttf"
    italic = font_dir / "VeraIt.ttf"

    pdfmetrics.registerFont(TTFont("TeletextSans", str(regular)))
    pdfmetrics.registerFont(TTFont("TeletextSans-Bold", str(bold)))
    pdfmetrics.registerFont(TTFont("TeletextSans-Italic", str(italic)))


def build_styles():
    register_fonts()
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Title"],
            fontName="TeletextSans-Bold",
            fontSize=23,
            leading=28,
            textColor=colors.HexColor("#0F2B46"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["Normal"],
            fontName="TeletextSans",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#444444"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading1"],
            fontName="TeletextSans-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#123E63"),
            spaceBefore=8,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="StoryHeading",
            parent=styles["Heading2"],
            fontName="TeletextSans-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#1C1C1C"),
            spaceBefore=10,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="StoryContext",
            parent=styles["Normal"],
            fontName="TeletextSans-Italic",
            fontSize=9.5,
            leading=12.5,
            textColor=colors.HexColor("#666666"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyTextNews",
            parent=styles["BodyText"],
            fontName="TeletextSans",
            fontSize=10.5,
            leading=14.5,
            alignment=TA_LEFT,
            textColor=colors.black,
            spaceAfter=7,
        )
    )
    return styles


class TeletextScraper:
    def __init__(self, start_url: str, timeout: int = TIMEOUT, include_sports: bool = False) -> None:
        self.start_url = start_url
        self.timeout = timeout
        self.include_sports = include_sports
        self.session = self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=4,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": USER_AGENT})
        return session

    def fetch_soup(self, url: str) -> BeautifulSoup:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()

        raw = response.content
        encodings = []
        for value in (response.encoding, response.apparent_encoding, "utf-8", "cp1252", "latin-1"):
            if value and value not in encodings:
                encodings.append(value)

        decoded_text = None
        for encoding in encodings:
            try:
                candidate = raw.decode(encoding, errors="replace")
            except Exception:
                continue
            candidate = repair_mojibake(candidate)
            if candidate:
                decoded_text = candidate
                if "Ã" not in candidate:
                    break

        if decoded_text is None:
            decoded_text = repair_mojibake(response.text)

        return BeautifulSoup(decoded_text, "html.parser")

    def discover_categories(self) -> list[TeletextLink]:
        soup = self.fetch_soup(self.start_url)
        categories = extract_top_navigation_links(soup, self.start_url)
        if not categories:
            categories = extract_all_candidate_category_links(soup, self.start_url)
        if not categories:
            raise RuntimeError("No categories could be discovered on the given start page.")
        return categories

    def crawl_category(
        self,
        category_label: str,
        root_url: str,
        root_page_number: int | None,
        all_root_pages: set[int],
        max_pages: int = MAX_PAGES_PER_CATEGORY,
    ) -> CategoryData:
        category = CategoryData(label=category_label, root_url=root_url, root_page_number=root_page_number)
        queue: deque[str] = deque([root_url])
        visited: set[str] = set()
        seen_content_keys: set[tuple[str, str, str]] = set()

        while queue and len(visited) < max_pages:
            current_url = queue.popleft()
            current_url = normalize_url(current_url)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                soup = self.fetch_soup(current_url)
            except Exception as exc:
                print(f"[WARN] Could not load {current_url}: {exc}", file=sys.stderr)
                continue

            page = extract_page_data(soup, current_url)
            page_key = (
                story_headline_for_page(page).lower(),
                story_context_for_page(page).lower(),
                normalize_text(page.body)[:220].lower(),
            )
            if page_key not in seen_content_keys and should_keep_page(page, include_sports=self.include_sports):
                category.pages.append(page)
                seen_content_keys.add(page_key)

            for link in page.teaser_links:
                if should_follow_link(
                    link=link,
                    current_url=current_url,
                    root_page_number=root_page_number,
                    all_root_pages=all_root_pages,
                    include_sports=self.include_sports,
                ):
                    queue.append(link.url)

        category.pages.sort(key=lambda item: (story_headline_for_page(item).lower(), item.url))
        return category


def build_pdf(output_path: Path, start_url: str, categories: list[CategoryData]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="news.pdf",
        author="Teletext News PDF CLI",
        subject="Current teletext news compiled into a searchable text PDF",
    )

    story = []
    now = datetime.now()

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("news.pdf", styles["CoverTitle"]))
    story.append(
        Paragraph(
            "Current teletext news compiled into a searchable text PDF.",
            styles["Meta"],
        )
    )
    story.append(
        Paragraph(
            f"Created: {now.strftime('%Y-%m-%d %H:%M:%S')}",
            styles["Meta"],
        )
    )
    story.append(
        Paragraph(
            "The document contains real text, so it can be searched, indexed, and read by LLM tools.",
            styles["Meta"],
        )
    )
    story.append(Spacer(1, 6 * mm))

    visible_categories = [category for category in categories if category.pages]
    overview_rows = [["Category", "Entries"]]
    for category in visible_categories:
        overview_rows.append([category.label, str(len(category.pages))])

    overview_table = Table(overview_rows, colWidths=[126 * mm, 34 * mm], repeatRows=1)
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E7F3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#10263A")),
                ("FONTNAME", (0, 0), (-1, 0), "TeletextSans-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "TeletextSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("LEADING", (0, 0), (-1, -1), 12),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AABBCD")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(overview_table)
    story.append(PageBreak())

    for category in visible_categories:
        story.append(Paragraph(escape_para(category.label), styles["SectionHeading"]))
        story.append(
            Paragraph(
                escape_para(f"Collected entries: {len(category.pages)}"),
                styles["StoryContext"],
            )
        )
        story.append(Spacer(1, 1.5 * mm))

        for index, page in enumerate(category.pages, start=1):
            story.append(Paragraph(escape_para(story_headline_for_page(page)), styles["StoryHeading"]))
            context = story_context_for_page(page)
            if context:
                story.append(Paragraph(escape_para(context), styles["StoryContext"]))
            story.append(Paragraph(escape_para(page.body), styles["BodyTextNews"]))
            if index != len(category.pages):
                story.append(Spacer(1, 3 * mm))

        story.append(PageBreak())

    if not visible_categories:
        story.append(Paragraph("No relevant categories or entries were collected.", styles["BodyTextNews"]))

    doc.build(story)


def decide_output_path(output_dir: Path, keep_history: bool) -> Path:
    if keep_history:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"news_{timestamp}.pdf"
    else:
        filename = DEFAULT_FILENAME
    return output_dir / filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch teletext news pages starting from a page-100 URL and save the result as a "
            "searchable text PDF. Default start page: https://www.ard-text.de/mobil/100"
        ),
        epilog=(
            "Examples:\n"
            "  py news_ripper.py\n"
            "  py news_ripper.py --output-dir \"D:\\NewsPDF\"\n"
            "  py news_ripper.py --keep-history\n"
            "  py news_ripper.py --include-sports\n"
            "  py news_ripper.py --start-url \"https://example.org/mobil/100\"\n"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--start-url",
        default=DEFAULT_START_URL,
        help="Teletext page-100 start URL. Default: %(default)s",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where the PDF will be written. Default: current directory.",
    )
    parser.add_argument(
        "--keep-history",
        action="store_true",
        help="Do not overwrite news.pdf. Write news_YYYYMMDD_HHMMSS.pdf instead.",
    )
    parser.add_argument(
        "--include-sports",
        action="store_true",
        help="Keep sports categories and sports articles instead of filtering them out.",
    )
    parser.add_argument(
        "--max-pages-per-category",
        type=int,
        default=MAX_PAGES_PER_CATEGORY,
        help=f"Safety limit for crawled pages per category. Default: {MAX_PAGES_PER_CATEGORY}",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT,
        help=f"HTTP timeout in seconds. Default: {TIMEOUT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_path = decide_output_path(output_dir, args.keep_history)

    print(f"[INFO] Start URL: {args.start_url}")
    print(f"[INFO] Output:    {output_path}")
    print(f"[INFO] Include sports pages: {'yes' if args.include_sports else 'no'}")

    scraper = TeletextScraper(
        start_url=args.start_url,
        timeout=args.timeout,
        include_sports=args.include_sports,
    )

    try:
        root_categories = scraper.discover_categories()
    except Exception as exc:
        print(f"[ERROR] Could not discover categories: {exc}", file=sys.stderr)
        return 2

    print(f"[INFO] Categories discovered: {len(root_categories)}")
    all_root_pages = {link.page_number for link in root_categories if link.page_number is not None}

    categories: list[CategoryData] = []
    for index, root in enumerate(root_categories, start=1):
        label = root.label or f"Category {root.page_number or index}"
        print(f"[INFO] [{index}/{len(root_categories)}] Crawling {label} ({root.url})")
        category = scraper.crawl_category(
            category_label=label,
            root_url=root.url,
            root_page_number=root.page_number,
            all_root_pages=all_root_pages,
            max_pages=args.max_pages_per_category,
        )
        if category.pages:
            categories.append(category)
        print(f"[INFO]     -> {len(category.pages)} relevant pages collected")

    try:
        build_pdf(output_path=output_path, start_url=args.start_url, categories=categories)
    except Exception as exc:
        print(f"[ERROR] Could not create PDF: {exc}", file=sys.stderr)
        return 3

    print(f"[OK] Done: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

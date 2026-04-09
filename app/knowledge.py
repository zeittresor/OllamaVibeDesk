from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

TEXT_EXTENSIONS = {
    '.txt', '.md', '.markdown', '.rst', '.json', '.jsonl', '.csv', '.tsv', '.ini', '.cfg', '.yaml', '.yml',
    '.xml', '.html', '.htm', '.py', '.pyw', '.js', '.ts', '.css', '.scss', '.sql', '.php', '.cs', '.cpp', '.c', '.h',
    '.java', '.kt', '.swift', '.go', '.rs', '.lua', '.rb', '.sh', '.bat', '.ps1', '.log'
}
MEDIA_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.mp3', '.wav', '.flac', '.ogg', '.m4a',
    '.mp4', '.mkv', '.avi', '.mov', '.webm', '.pdf'
}
STOPWORDS = {
    'und','oder','aber','nicht','eine','einer','eines','einem','einen','der','die','das','den','dem','des','mit','ohne',
    'for','the','and','that','this','with','from','your','you','are','was','were','have','has','had','into','about','please',
    'ein','eine','einer','einem','einen','ist','sind','war','wir','uns','ich','du','er','sie','es','als','auch','noch','mal',
}


def _slug(text: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', str(text or '').strip())
    return cleaned.strip('-_') or 'item'


def _norm(text: str) -> str:
    return re.sub(r'\s+', ' ', str(text or '').strip().lower())


def extract_keywords(text: str) -> list[str]:
    words = re.findall(r"[\wÄÖÜäöüß]{3,}", str(text or '').lower())
    result: list[str] = []
    seen: set[str] = set()
    for word in words:
        if word in STOPWORDS or word.isdigit() or word in seen:
            continue
        seen.add(word)
        result.append(word)
    return result[:32]


def _safe_read_text(path: Path, max_chars: int = 50000) -> str:
    for encoding in ('utf-8', 'utf-8-sig', 'cp1252', 'latin-1'):
        try:
            data = path.read_text(encoding=encoding, errors='ignore')
            return data[:max_chars]
        except Exception:
            continue
    return ''


def _tiddler_timestamp() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]


class LocalKnowledgeBase:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.entries_path = self.root_dir / 'entries.jsonl'
        self.imports_dir = self.root_dir / 'imports'
        self.default_wiki_dir = self.root_dir / 'tiddlywiki'
        self.default_wiki_template = self.root_dir.parent / 'cache' / 'tiddlywiki_empty.html'
        self.ensure()

    def ensure(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        if not self.entries_path.exists():
            self.entries_path.touch()

    def linked_wiki_path(self, configured_path: str) -> Path | None:
        raw = str(configured_path or '').strip()
        return Path(raw) if raw else None

    def create_wiki_workspace(self, base_path: Path | None = None) -> Path:
        wiki_dir = Path(base_path) if base_path else self.default_wiki_dir
        wiki_dir.mkdir(parents=True, exist_ok=True)
        (wiki_dir / 'tiddlers').mkdir(parents=True, exist_ok=True)
        info_path = wiki_dir / 'tiddlywiki.info'
        if not info_path.exists():
            info = {
                'description': 'OllamaVibeDesk local knowledge workspace',
                'plugins': [],
                'themes': [],
                'languages': [],
                'build': {},
            }
            info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
        readme = wiki_dir / 'README_OllamaVibeDesk.txt'
        if not readme.exists():
            readme.write_text(
                'Dieser Ordner wird von OllamaVibeDesk als lokale Wissensquelle verwendet.\n'
                'Die App schreibt hier Tiddler-kompatible Textdateien in den Unterordner tiddlers.\n'
                'Falls im Cache eine blanke TiddlyWiki-Datei vorhanden ist, wird sie hier als brain.html abgelegt.\n'
                'Für eine interaktive Nutzung mit TiddlyWiki5 kann diese Datei lokal geöffnet und später weiter angepasst werden.\n',
                encoding='utf-8'
            )
        brain_html = wiki_dir / 'brain.html'
        if not brain_html.exists():
            if self.default_wiki_template.exists():
                shutil.copy2(self.default_wiki_template, brain_html)
            else:
                brain_html.write_text(
                    '<!doctype html><html><head><meta charset="utf-8"><title>OllamaVibeDesk Brain</title></head>'
                    '<body><h1>OllamaVibeDesk Brain</h1><p>Es wurde noch keine blanke TiddlyWiki-Vorlage im Cache gefunden.</p>'
                    '<p>Lege eine Datei <code>app_data/cache/tiddlywiki_empty.html</code> ab, damit neue Wissensquellen automatisch mit einer lokalen blanken TiddlyWiki-Datei angelegt werden.</p></body></html>',
                    encoding='utf-8'
                )
        return wiki_dir

    def _copy_if_reasonable(self, source_path: Path) -> tuple[Path, bool]:
        try:
            size = source_path.stat().st_size
        except Exception:
            return source_path, False
        if size > 32 * 1024 * 1024:
            return source_path, False
        prefix = hashlib.sha1(str(source_path).encode('utf-8')).hexdigest()[:10]
        target = self.imports_dir / f'{prefix}_{source_path.name}'
        if not target.exists():
            shutil.copy2(source_path, target)
        return target, True

    def _append_entry(self, entry: dict, wiki_path: Path | None = None) -> dict:
        self.ensure()
        with self.entries_path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
        if wiki_path is not None:
            self.write_tiddler(entry, wiki_path)
        return entry

    def import_file(self, file_path: Path, session_title: str = '', persist_to_memory: bool = False, wiki_path: Path | None = None) -> dict:
        file_path = Path(file_path)
        mime, _ = mimetypes.guess_type(str(file_path))
        ext = file_path.suffix.lower()
        is_text = ext in TEXT_EXTENSIONS or (mime or '').startswith('text/')
        copied_path, copied = self._copy_if_reasonable(file_path) if persist_to_memory else (file_path, False)
        content = _safe_read_text(file_path) if is_text else ''
        entry = {
            'id': uuid_hash(file_path, content),
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'type': 'file',
            'title': file_path.name,
            'source_path': str(file_path),
            'stored_path': str(copied_path),
            'copied_to_store': bool(copied),
            'mime_type': mime or '',
            'extension': ext,
            'is_text': bool(is_text),
            'session_title': session_title,
            'content': content,
            'keywords': extract_keywords(f'{file_path.name} {content}'),
        }
        if persist_to_memory:
            self._append_entry(entry, wiki_path=wiki_path)
        prompt_context = self._entry_prompt_context(entry)
        return {'entry': entry, 'prompt_context': prompt_context}

    def remember_exchange(self, session_id: str, session_title: str, user_text: str, assistant_text: str, model_name: str = '', wiki_path: Path | None = None) -> dict:
        body = f'Nutzer:\n{user_text.strip()}\n\nAssistent:\n{assistant_text.strip()}'
        entry = {
            'id': hashlib.sha1(f'{session_id}|{user_text}|{assistant_text}'.encode('utf-8')).hexdigest()[:24],
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'type': 'chat_memory',
            'title': session_title or 'Chat-Erinnerung',
            'session_id': session_id,
            'model_name': model_name,
            'content': body[:12000],
            'keywords': extract_keywords(f'{session_title} {user_text} {assistant_text}'),
        }
        return self._append_entry(entry, wiki_path=wiki_path)

    def load_entries(self) -> list[dict]:
        self.ensure()
        entries: list[dict] = []
        with self.entries_path.open('r', encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    entries.append(item)
        return entries

    def search(self, query: str, limit: int = 5) -> list[dict]:
        query_keywords = extract_keywords(query)
        if not query_keywords:
            return []
        scored: list[tuple[int, dict]] = []
        for entry in self.load_entries():
            hay_title = _norm(entry.get('title', ''))
            hay_content = _norm(entry.get('content', ''))
            hay_keywords = ' '.join(entry.get('keywords', []) or [])
            score = 0
            for kw in query_keywords:
                if kw in hay_title:
                    score += 6
                if kw in hay_keywords:
                    score += 4
                if kw in hay_content:
                    score += 2
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: (item[0], item[1].get('created_at', '')), reverse=True)
        return [entry for _score, entry in scored[:max(1, limit)]]

    def build_retrieval_context(self, query: str, limit: int = 5) -> tuple[str, list[dict]]:
        hits = self.search(query, limit=limit)
        if not hits:
            return '', []
        lines = ['Selektiv relevantes Langzeitgedächtnis / Wissensarchiv:']
        for idx, entry in enumerate(hits, 1):
            title = str(entry.get('title', 'Eintrag')).strip() or 'Eintrag'
            kind = str(entry.get('type', 'memory')).strip()
            if entry.get('content'):
                snippet = re.sub(r'\s+', ' ', str(entry.get('content', ''))).strip()[:700]
                lines.append(f'{idx}. [{kind}] {title}: {snippet}')
            else:
                ref = entry.get('stored_path') or entry.get('source_path') or ''
                lines.append(f'{idx}. [{kind}] {title}: Referenz auf Medium/Datei {ref}')
        return '\n'.join(lines).strip(), hits

    def delete_all(self) -> None:
        if self.root_dir.exists():
            shutil.rmtree(self.root_dir)
        self.ensure()

    def write_tiddler(self, entry: dict, wiki_path: Path) -> Path:
        wiki_dir = self.create_wiki_workspace(wiki_path)
        tiddlers_dir = wiki_dir / 'tiddlers'
        title = str(entry.get('title', 'Memory')).strip() or 'Memory'
        created = _tiddler_timestamp()
        tags = ' '.join(_slug(tag) for tag in entry.get('keywords', [])[:8])
        body = str(entry.get('content', '') or '')
        if not body:
            ref = entry.get('stored_path') or entry.get('source_path') or ''
            body = f'Referenz: {ref}'
        text = f'title: {title}\ncreated: {created}\ntags: OllamaVibeDesk {tags}\nentry-id: {entry.get("id","")}\nentry-type: {entry.get("type","")}\n\n{body}\n'
        target = tiddlers_dir / f'{created}_{_slug(title)}.tid'
        target.write_text(text, encoding='utf-8')
        return target

    def _entry_prompt_context(self, entry: dict) -> str:
        title = str(entry.get('title', 'Datei')).strip() or 'Datei'
        if entry.get('content'):
            snippet = re.sub(r'\s+', ' ', str(entry.get('content', ''))).strip()[:4000]
            return f'Datei/Quelle "{title}":\n{snippet}'
        ref = entry.get('stored_path') or entry.get('source_path') or ''
        return f'Datei/Medium "{title}" wurde als Kontextquelle ausgewählt. Referenz: {ref}'


def uuid_hash(path: Path, content: str = '') -> str:
    return hashlib.sha1(f'{path}|{content[:200]}|{datetime.now().isoformat(timespec="seconds")}'.encode('utf-8')).hexdigest()[:24]

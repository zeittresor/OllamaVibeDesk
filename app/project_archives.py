"""Package code from one assistant answer as a versioned, inspectable project ZIP."""
from __future__ import annotations

import io
import ast
import json
import re
import tomllib
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath


FENCE = re.compile(r"^\s*(`{3,}|~{3,})([\w+#.\-]*)(?:\s+(.+?))?\s*$")
FILE_LABEL = re.compile(r"^\s*(?:#{1,6}\s*)?(?:(?:file|datei|filename|path|pfad)\s*[:=]\s*)?([\w.\-/\\ ]+?\.[A-Za-z0-9]{1,12})\s*$", re.I)
PROJECT_LABEL = re.compile(r"^\s*#{0,6}\s*(?:project|projekt)(?:name)?\s*[:=]\s*(.{2,90}?)\s*$", re.I)
VERSION_LABEL = re.compile(r"^\s*#{0,6}\s*(?:version|stand)\s*[:=]\s*(.{1,32}?)\s*$", re.I)
EXTENSIONS = {
    'py': 'py', 'python': 'py', 'javascript': 'js', 'js': 'js', 'typescript': 'ts', 'ts': 'ts',
    'html': 'html', 'css': 'css', 'json': 'json', 'yaml': 'yml', 'yml': 'yml', 'markdown': 'md',
    'md': 'md', 'bash': 'sh', 'sh': 'sh', 'powershell': 'ps1', 'ps1': 'ps1', 'bat': 'bat',
    'batch': 'bat', 'cmd': 'cmd', 'csharp': 'cs', 'cs': 'cs', 'java': 'java', 'cpp': 'cpp',
    'c++': 'cpp', 'c': 'c', 'rust': 'rs', 'rs': 'rs', 'go': 'go', 'xml': 'xml', 'sql': 'sql',
    'txt': 'txt', 'text': 'txt', 'toml': 'toml', 'ini': 'ini',
    'gdscript': 'gd', 'gd': 'gd', 'gdscene': 'tscn', 'tscn': 'tscn', 'tres': 'tres',
    'gdshader': 'gdshader', 'shader': 'gdshader', 'glsl': 'gdshader', 'godot': 'godot',
}
MAX_FILES = 100
MAX_TEXT_BYTES = 5_000_000


def safe_relative_path(raw: str) -> str | None:
    value = str(raw or '').strip().strip('`"\'').replace('\\', '/')
    if not value or len(value) > 200 or value.startswith('/') or re.match(r'^[A-Za-z]:', value):
        return None
    path = PurePosixPath(value)
    if value.split('/') != list(path.parts) or len(path.parts) > 12 or any(part in ('', '.', '..') or part.endswith((' ', '.')) or ':' in part for part in path.parts):
        return None
    if any(re.search(r'[<>:"|?*\x00-\x1f]', part) for part in path.parts):
        return None
    if any(part.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))} for part in path.parts):
        return None
    return path.as_posix()


def slug(value: str) -> str:
    cleaned = re.sub(r'[^a-z0-9_-]+', '-', str(value).lower()).strip('-')[:48]
    return cleaned or 'project'


def _unique_file(preferred: str, existing: dict[str, object]) -> str:
    if preferred not in existing:
        return preferred
    path = PurePosixPath(preferred)
    count = 2
    while True:
        candidate = str(path.with_name(f'{path.stem}_{count}{path.suffix}'))
        if candidate not in existing:
            return candidate
        count += 1


def _content_file_hint(text: str) -> tuple[str, str, str] | None:
    """Infer conservative filenames only from strong source signatures."""
    value = str(text or '').lstrip('\ufeff').strip()
    lower = value.lower()
    if re.match(r'^\[gd_scene\b', value):
        return 'main.tscn', 'tscn', 'Godot scene header'
    if re.match(r'^\[gd_resource\b', value):
        return 'resource.tres', 'tres', 'Godot resource header'
    if re.search(r'(?m)^config_version\s*=\s*\d+', value) and re.search(r'(?m)^\[(?:application|rendering|display|input)\]', value):
        return 'project.godot', 'godot', 'Godot project configuration'
    if (re.search(r'(?m)^\s*(?:@(?:export|onready|tool)\b|extends\s+[A-Za-z_]|class_name\s+[A-Za-z_]|func\s+_[a-zA-Z_]+\s*\()', value)
            and not re.search(r'(?m)^\s*(?:def|class)\s+[A-Za-z_]', value)):
        return 'main.gd', 'gd', 'GDScript syntax'
    if re.match(r'(?is)^\s*<!doctype\s+html\b', value) or re.search(r'(?is)<html\b[^>]*>.*</html>', value):
        return 'index.html', 'html', 'HTML document'
    if re.search(r'(?m)^\s*(?:from\s+[\w.]+\s+import\s+|import\s+[\w.]+|def\s+[A-Za-z_]\w*\s*\(|class\s+[A-Za-z_]\w*\s*[:(])', value):
        return 'main.py', 'py', 'Python syntax'
    if re.search(r'(?m)^\s*(?:using\s+[\w.]+\s*;|namespace\s+[\w.]+|(?:public|internal)\s+(?:sealed\s+)?class\s+\w+)', value):
        return 'Program.cs', 'cs', 'C# syntax'
    if re.search(r'(?m)^\s*(?:package\s+main\b|func\s+main\s*\(\s*\))', value):
        return 'main.go', 'go', 'Go syntax'
    if re.search(r'(?m)^\s*(?:fn\s+main\s*\(\s*\)|use\s+(?:std|crate)::)', value):
        return 'src/main.rs', 'rs', 'Rust syntax'
    if re.search(r'(?m)^\s*(?:#version\s+\d+|shader_type\s+\w+\s*;)', value):
        return 'shader.gdshader', 'gdshader', 'shader syntax'
    if re.match(r'(?is)^\s*<\?xml\b', value):
        return 'data.xml', 'xml', 'XML declaration'
    try:
        parsed = json.loads(value)
        if isinstance(parsed, (dict, list)):
            preferred = 'package.json' if isinstance(parsed, dict) and ('dependencies' in parsed or 'scripts' in parsed) else 'config.json'
            return preferred, 'json', 'valid JSON'
    except (ValueError, TypeError):
        pass
    if re.search(r'(?m)^\s*@echo\s+off\b', lower):
        return 'run.bat', 'bat', 'Windows batch syntax'
    if re.search(r'(?m)^\s*(?:param\s*\(|\$ErrorActionPreference\s*=|Write-Host\b)', value, re.I):
        return 'run.ps1', 'ps1', 'PowerShell syntax'
    if re.match(r'^#!.*\b(?:bash|sh)\b', value):
        return 'run.sh', 'sh', 'shell shebang'
    if re.search(r'(?m)^\s*(?:const|let|var)\s+[A-Za-z_$]|(?:async\s+)?function\s+[A-Za-z_$]|(?:import|export)\s+(?:\{|default|class|function)', value):
        return 'index.js', 'js', 'JavaScript syntax'
    if re.search(r'(?m)^\s*(?:[.#]?[A-Za-z][\w.-]*\s*(?:,\s*[^{}]+)?\{\s*$|@media\b)', value):
        return 'style.css', 'css', 'CSS syntax'
    return None


def _fallback_file(language: str, existing: dict[str, object], text: str = '') -> tuple[str, dict | None]:
    normalized = str(language or '').lower()
    if normalized in {'', 'txt', 'text', 'plain', 'plaintext', 'ini', 'conf', 'config', 'godot'}:
        inferred = _content_file_hint(text)
        if inferred:
            preferred, ext, reason = inferred
            name = _unique_file(preferred, existing)
            return name, {'extension': ext, 'reason': reason, 'confidence': 'high'}
    ext = EXTENSIONS.get(normalized, 'txt')
    preferred = {'py': 'main.py', 'js': 'index.js', 'ts': 'index.ts', 'html': 'index.html',
                 'css': 'style.css', 'json': 'config.json', 'md': 'README.md', 'ps1': 'run.ps1',
                 'bat': 'install.bat', 'sh': 'run.sh', 'gd': 'main.gd', 'tscn': 'main.tscn',
                 'gdshader': 'shader.gdshader'}.get(ext, f'source.{ext}')
    return _unique_file(preferred, existing), ({'extension': ext, 'reason': f'code fence language: {normalized}', 'confidence': 'high'} if normalized else None)


def _correct_mislabeled_text_file(path: str, text: str, existing: dict[str, object]) -> tuple[str, dict | None]:
    """Correct only explicit .txt paths contradicted by a strong content signature."""
    candidate = PurePosixPath(path)
    if candidate.suffix.lower() != '.txt':
        return path, None
    hint = _content_file_hint(text)
    if not hint:
        return path, None
    _preferred, extension, reason = hint
    embedded_suffix = PurePosixPath(candidate.stem).suffix.lower().lstrip('.')
    known_extensions = set(EXTENSIONS.values()) | {'tres', 'godot'}
    if embedded_suffix == extension or embedded_suffix in known_extensions:
        corrected = str(candidate.with_suffix(''))
    else:
        corrected = str(candidate.with_suffix('.' + extension))
    corrected = safe_relative_path(corrected) or path
    if corrected != path:
        corrected = _unique_file(corrected, existing)
        return corrected, {
            'extension': extension,
            'reason': f'corrected explicit .txt name; detected {reason}',
            'confidence': 'high',
            'original_path': path,
        }
    return path, None


def _clean_label_markup(line: str) -> str:
    """Remove harmless Markdown/list decoration around model file labels."""
    value = str(line or '').strip()
    value = re.sub(r'^(?:[-*+]\s+|\d+[.)]\s+)', '', value)
    value = re.sub(r'^#{1,6}\s*', '', value)
    value = re.sub(r'^(?:\*\*|__|`)+', '', value)
    value = re.sub(r'(?:\*\*|__|`)+$', '', value)
    return value.strip()


def _extract_file_label(line: str) -> str:
    """Return a safe path from plain, bold, listed, or fenced File: markers."""
    value = _clean_label_markup(line)
    prefixed = re.match(r'^(?:file|datei|filename|path|pfad)\s*[:=]\s*(.+)$', value, re.I)
    candidate = prefixed.group(1).strip() if prefixed else value
    candidate = _clean_label_markup(candidate)
    return safe_relative_path(candidate) or ''


def parse_projects(answer: str, default_name: str, *, include_unclosed: bool = True) -> list[dict]:
    """Use explicit project/file headings; otherwise group code in this answer."""
    projects: list[dict] = []
    current = {'name': default_name or 'project', 'version_label': '', 'files': {}, 'inferred_files': {}}
    pending_file = ''
    lines_since_file = 0
    fence_char = ''
    fence_len = 0
    language = ''
    chosen_file = ''
    code: list[str] = []
    total_bytes = 0

    def add_code():
        nonlocal total_bytes, pending_file, lines_since_file
        text = '\n'.join(code).rstrip() + '\n'
        # Some models put the filename itself in a tiny fenced text block,
        # followed by the actual source block. Treat that marker as metadata,
        # otherwise it becomes source.txt and all following files lose names.
        marker_lines = [item for item in text.splitlines() if item.strip()]
        if len(marker_lines) == 1:
            marker = _extract_file_label(marker_lines[0])
            if marker and re.match(r'^(?:file|datei|filename|path|pfad)\s*[:=]', _clean_label_markup(marker_lines[0]), re.I):
                pending_file = marker
                lines_since_file = 0
                return
        total_bytes += len(text.encode('utf-8'))
        if total_bytes > MAX_TEXT_BYTES or len(current['files']) >= MAX_FILES:
            raise ValueError('Code response exceeds the archive safety limits')
        if text.strip():
            if chosen_file:
                name, inference = _correct_mislabeled_text_file(chosen_file, text, current['files'])
            else:
                name, inference = _fallback_file(language, current['files'], text)
            current['files'][name] = text
            if inference:
                current['inferred_files'][name] = inference

    for line in str(answer or '').replace('\r\n', '\n').split('\n'):
        match = FENCE.match(line)
        if not fence_char:
            if match:
                fence_char, fence_len = match.group(1)[0], len(match.group(1))
                language = match.group(2) or ''
                hint = match.group(3) or ''
                hint = re.sub(r'^(?:file|filename|path)\s*[:=]\s*', '', hint, flags=re.I)
                chosen_file = safe_relative_path(hint) or (pending_file if lines_since_file <= 2 else '')
                pending_file = ''
                code = []
                continue
            clean_line = _clean_label_markup(line)
            project = PROJECT_LABEL.match(clean_line)
            if project:
                if current['files']:
                    projects.append(current)
                    current = {'name': project.group(1).strip(), 'version_label': '', 'files': {}, 'inferred_files': {}}
                else:
                    current['name'] = project.group(1).strip()
                pending_file = ''
                continue
            version = VERSION_LABEL.match(clean_line)
            if version:
                current['version_label'] = version.group(1).strip()
            label = _extract_file_label(line)
            if label:
                pending_file = label
                lines_since_file = 0
            else:
                lines_since_file += 1
            continue
        close = re.match(r'^\s*([`~]{3,})\s*$', line)
        if close and close.group(1)[0] == fence_char and len(close.group(1)) >= fence_len:
            add_code()
            fence_char = ''
        else:
            code.append(line)
    if include_unclosed and fence_char and code:
        add_code()
    if current['files']:
        projects.append(current)
    return projects


def _zip_files(data: bytes) -> dict[str, bytes]:
    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            path = safe_relative_path(item.filename)
            if item.is_dir() or not path or path.startswith('_archive/') or item.file_size > MAX_TEXT_BYTES:
                continue
            files[path] = archive.read(item)
    return files


def latest_archive_for_sessions(root: Path, session_ids: set[str]) -> Path | None:
    """Find the newest valid project archive produced by one session in a chain."""
    wanted = {str(item) for item in session_ids if str(item)}
    if not wanted:
        return None
    candidates: list[tuple[int, Path]] = []
    for path in Path(root).joinpath('zips').rglob('v[0-9][0-9][0-9][0-9].zip'):
        try:
            with zipfile.ZipFile(path) as archive:
                metadata = json.loads(archive.read('_archive/manifest.json'))
            if str(metadata.get('session_id', '')) in wanted:
                candidates.append((path.stat().st_mtime_ns, path))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def restore_project_archive(archive_path: Path, destination: Path) -> dict:
    """Restore validated project files to a new tool workspace without ZIP traversal."""
    source = Path(archive_path)
    files = _zip_files(source.read_bytes())
    if not files:
        return {'archive': str(source), 'files': [], 'text_files': {}, 'project_check': {}}
    target_root = Path(destination)
    target_root.mkdir(parents=True, exist_ok=True)
    text_files: dict[str, str] = {}
    for relative, content in sorted(files.items()):
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        text = _text_content(content)
        if text is not None:
            text_files[relative] = text
    check = {}
    try:
        with zipfile.ZipFile(source) as archive:
            check = json.loads(archive.read('_archive/project_check.json'))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
        check = {}
    return {
        'archive': str(source),
        'files': sorted(files),
        'text_files': text_files,
        'project_check': check if isinstance(check, dict) else {},
    }


def workspace_snapshot(directory: Path) -> dict[str, tuple[int, int]]:
    """Collect only regular files in this chat's workspace; never follow links."""
    result = {}
    if not directory.is_dir():
        return result
    for path in directory.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        relative = safe_relative_path(path.relative_to(directory).as_posix())
        if relative and not relative.startswith('_archive/'):
            stat = path.stat()
            result[relative] = (stat.st_mtime_ns, stat.st_size)
    return result


def changed_workspace_files(directory: Path, before: dict[str, tuple[int, int]]) -> dict[str, bytes]:
    snapshot = workspace_snapshot(directory)
    changed = {key: size for key, size in snapshot.items() if before.get(key) != size}
    if len(changed) > MAX_FILES or sum(size for _, size in changed.values()) > MAX_TEXT_BYTES:
        raise ValueError('Workspace changes exceed archive safety limits')
    return {key: (directory / key).read_bytes() for key in changed}


def _text_content(content: bytes) -> str | None:
    if b'\0' in content[:4096]:
        return None
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return None


def _preferred_godot_scene(files: dict[str, bytes]) -> str:
    scenes = sorted(path for path in files if path.lower().endswith('.tscn'))
    if not scenes:
        return ''
    return min(scenes, key=lambda path: (
        Path(path).name.lower() not in {'main.tscn', 'game.tscn'},
        '/main.' not in '/' + path.lower(),
        len(PurePosixPath(path).parts),
        path.lower(),
    ))


def _generated_godot_project(project_name: str, main_scene: str) -> bytes:
    clean_name = re.sub(r'["\r\n]+', ' ', str(project_name or 'Generated project')).strip()[:80]
    text = (
        '; Generated by OllamaVibeDesk because a Godot scene was present but project.godot was missing.\n'
        'config_version=5\n\n'
        '[application]\n\n'
        f'config/name="{clean_name or "Generated project"}"\n'
        f'run/main_scene="res://{main_scene}"\n'
    )
    return text.encode('utf-8')


def complete_project_structure(files: dict[str, bytes], project_name: str) -> tuple[dict[str, bytes], list[dict]]:
    """Add only deterministic metadata that is unambiguously missing."""
    completed = dict(files)
    generated: list[dict] = []
    scene = _preferred_godot_scene(completed)
    if scene and 'project.godot' not in completed:
        completed['project.godot'] = _generated_godot_project(project_name, scene)
        generated.append({
            'path': 'project.godot',
            'reason': 'Godot scene detected and project.godot was missing',
            'main_scene': scene,
        })
    return completed, generated


def inspect_project(files: dict[str, bytes], inferred_files: dict | None = None,
                    generated_files: list[dict] | None = None) -> dict:
    """Return an inspectable structural report; never execute generated code."""
    inferred_files = dict(inferred_files or {})
    generated_files = list(generated_files or [])
    paths = sorted(files)
    suffixes = {PurePosixPath(path).suffix.lower() for path in paths}
    if 'project.godot' in files or suffixes & {'.tscn', '.tres', '.gd', '.gdshader'}:
        kind = 'godot'
    elif '.csproj' in suffixes or '.cs' in suffixes:
        kind = 'dotnet'
    elif '.py' in suffixes:
        kind = 'python'
    elif 'package.json' in files or suffixes & {'.js', '.ts'}:
        kind = 'javascript'
    elif 'index.html' in files or '.html' in suffixes:
        kind = 'web'
    else:
        kind = 'generic'

    issues: list[dict] = []
    entries: list[str] = []

    def issue(severity: str, code: str, message: str, path: str = '') -> None:
        item = {'severity': severity, 'code': code, 'message': message}
        if path:
            item['path'] = path
        issues.append(item)

    for path, content in sorted(files.items()):
        text = _text_content(content)
        if text is None:
            continue
        lower = path.lower()
        try:
            if lower.endswith('.py'):
                ast.parse(text, filename=path)
            elif lower.endswith('.json'):
                json.loads(text)
            elif lower.endswith('.toml'):
                tomllib.loads(text)
            elif lower.endswith('.xml'):
                ET.fromstring(text)
            elif lower.endswith('.tscn') and not re.match(r'^\s*\[gd_scene\b', text):
                issue('error', 'invalid_godot_scene_header', 'Godot scene does not start with a [gd_scene] header.', path)
            elif lower.endswith('.tres') and not re.match(r'^\s*\[gd_resource\b', text):
                issue('error', 'invalid_godot_resource_header', 'Godot resource does not start with a [gd_resource] header.', path)
        except (SyntaxError, ValueError, TypeError, ET.ParseError) as exc:
            issue('error', 'syntax_error', f'{type(exc).__name__}: {exc}', path)

    if kind == 'godot':
        scene = _preferred_godot_scene(files)
        if scene:
            entries.append(scene)
        else:
            issue('warning', 'missing_scene', 'No Godot .tscn scene was found.')
        project_text = _text_content(files.get('project.godot', b'')) if 'project.godot' in files else None
        if not project_text:
            issue('error', 'missing_project_godot', 'Godot files exist but project.godot is missing.')
        else:
            if not re.search(r'(?m)^config_version\s*=\s*\d+', project_text):
                issue('error', 'invalid_project_godot', 'project.godot has no config_version.', 'project.godot')
            main_match = re.search(r'(?m)^run/main_scene\s*=\s*"res://([^"]+)"', project_text)
            if main_match:
                main_path = main_match.group(1)
                if main_path not in files:
                    issue('error', 'missing_main_scene', f'Configured main scene is absent: {main_path}', 'project.godot')
                elif main_path not in entries:
                    entries.insert(0, main_path)
            elif scene:
                issue('warning', 'main_scene_not_configured', 'project.godot does not configure run/main_scene.', 'project.godot')
        for source_path, content in sorted(files.items()):
            text = _text_content(content)
            if text is None or PurePosixPath(source_path).suffix.lower() not in {'.godot', '.tscn', '.tres', '.gd'}:
                continue
            for reference in sorted(set(re.findall(r'(?:path\s*=\s*|load\s*\(\s*)["\']res://([^"\']+)', text))):
                if reference not in files:
                    issue('warning', 'missing_resource_reference', f'Referenced resource is absent: {reference}', source_path)
    elif kind == 'python':
        entries = [path for path in ('main.py', 'app.py', '__main__.py') if path in files]
        if not entries:
            issue('warning', 'entry_point_unknown', 'No conventional Python entry point (main.py, app.py or __main__.py) was found.')
    elif kind == 'javascript':
        if 'package.json' in files:
            entries.append('package.json')
        entries.extend(path for path in ('index.js', 'index.ts', 'src/index.js', 'src/index.ts') if path in files)
        if not entries:
            issue('warning', 'entry_point_unknown', 'No conventional JavaScript/TypeScript entry point was found.')
    elif kind == 'web':
        if 'index.html' in files:
            entries.append('index.html')
        else:
            issue('warning', 'missing_index_html', 'Web files exist but index.html is missing.')
    elif kind == 'dotnet':
        entries = [path for path in paths if path.lower().endswith('.csproj')]
        if not entries:
            issue('warning', 'missing_csproj', 'C# files exist but no .csproj project file was found.')
    else:
        issue('warning', 'project_type_unknown', 'No supported project structure or entry point could be identified.')

    errors = sum(item['severity'] == 'error' for item in issues)
    warnings = sum(item['severity'] == 'warning' for item in issues)
    status = 'invalid' if errors else 'needs_review' if warnings else 'structure_complete'
    return {
        'status': status,
        'project_type': kind,
        'entry_points': entries,
        'file_count': len(files),
        'inferred_files': inferred_files,
        'generated_files': generated_files,
        'issues': issues,
        'summary': {'errors': errors, 'warnings': warnings},
        'execution_tested': False,
    }


def project_report_markdown(report: dict) -> str:
    lines = [
        '# OllamaVibeDesk project check', '',
        f"- Status: **{report['status']}**",
        f"- Detected type: **{report['project_type']}**",
        f"- Files: **{report['file_count']}**",
        '- Execution tested: **no**',
    ]
    if report['entry_points']:
        lines.extend(['', '## Entry points', *[f'- `{path}`' for path in report['entry_points']]])
    if report['generated_files']:
        lines.extend(['', '## Safely generated metadata', *[
            f"- `{item['path']}` — {item['reason']}" for item in report['generated_files']
        ]])
    if report['inferred_files']:
        lines.extend(['', '## Inferred filenames', *[
            f"- `{path}` — {item.get('reason', 'content signature')} ({item.get('confidence', 'unknown')})"
            for path, item in sorted(report['inferred_files'].items())
        ]])
    if report['issues']:
        lines.extend(['', '## Findings', *[
            f"- **{item['severity'].upper()}** `{item['code']}`"
            + (f" in `{item['path']}`" if item.get('path') else '')
            + f": {item['message']}" for item in report['issues']
        ]])
    else:
        lines.extend(['', '## Findings', '- No structural or syntax problem was detected.'])
    lines.extend(['', '> This is a static structure check. Installation and execution were not performed.', ''])
    return '\n'.join(lines)


def create_archives(answer: str, root: Path, project_hint: str, model: str, session_id: str,
                    workspace_files: dict[str, bytes] | None = None, *,
                    include_unclosed: bool = True, partial_source: bool = False) -> list[Path]:
    plans = parse_projects(answer, project_hint, include_unclosed=include_unclosed)
    if workspace_files:
        safe_files = {}
        for path, data in workspace_files.items():
            name = safe_relative_path(path)
            if not name or name.startswith('_archive/') or not isinstance(data, bytes):
                raise ValueError('Invalid workspace file path or content')
            safe_files[name] = data
        if len(plans) == 1:
            plans[0]['files'].update(safe_files)
        else:
            plans.append({'name': project_hint or 'project', 'version_label': '', 'files': safe_files, 'inferred_files': {}})
    results = []
    if not plans:
        return results
    root = Path(root) / 'zips'
    for plan in plans:
        directory = root / slug(plan['name']) / slug(model)
        directory.mkdir(parents=True, exist_ok=True)
        existing = sorted(directory.glob('v[0-9][0-9][0-9][0-9].zip'))
        previous = existing[-1] if existing else None
        number = max((int(path.stem[1:]) for path in existing), default=0) + 1
        inherited = _zip_files(previous.read_bytes()) if previous else {}
        # Model-supplied paths are relative to the project root; changed files replace older versions.
        files = {**inherited, **{name: content.encode('utf-8') if isinstance(content, str) else content for name, content in plan['files'].items()}}
        files, generated_files = complete_project_structure(files, plan['name'])
        if len(files) > MAX_FILES or sum(len(content) for content in files.values()) > MAX_TEXT_BYTES:
            raise ValueError('Project exceeds archive safety limits')
        report = inspect_project(files, plan.get('inferred_files'), generated_files)
        if partial_source:
            report['issues'].append({
                'severity': 'warning',
                'code': 'partial_model_response',
                'message': 'The model response was incomplete; only fully closed code blocks and completed workspace files were included.',
            })
            report['summary']['warnings'] += 1
            if report['status'] == 'structure_complete':
                report['status'] = 'needs_review'
        metadata = {'project': plan['name'], 'model': model, 'session_id': session_id,
                    'version': number, 'model_version_label': plan['version_label'],
                    'previous_archive': previous.name if previous else None,
                    'changed_files': sorted(plan['files']), 'inherited_files': sorted(set(inherited) - set(plan['files'])),
                    'inferred_files': plan.get('inferred_files', {}),
                    'generated_files': generated_files,
                    'project_check': {'status': report['status'], 'project_type': report['project_type'],
                                      'entry_points': report['entry_points'], **report['summary']},
                    'note': 'Model code plus explicitly listed generated metadata; structure was checked, execution was not.'}
        target = directory / f'v{number:04d}.zip'
        temp = directory / f'.{target.name}.{uuid.uuid4().hex}.tmp'
        try:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path, content in sorted(files.items()):
                    archive.writestr(path, content)
                archive.writestr('_archive/manifest.json', json.dumps(metadata, ensure_ascii=False, indent=2))
                archive.writestr('_archive/project_check.json', json.dumps(report, ensure_ascii=False, indent=2))
                archive.writestr('_archive/PROJECT_CHECK.md', project_report_markdown(report))
                if 'README.md' not in files:
                    archive.writestr('README.md', 'Files in this archive come from model output. Read _archive/PROJECT_CHECK.md before running.\n')
            with zipfile.ZipFile(temp) as archive:
                if archive.testzip():
                    raise RuntimeError('Archive integrity check failed')
            temp.replace(target)
            results.append(target)
        finally:
            temp.unlink(missing_ok=True)
    return results

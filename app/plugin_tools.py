"""Small, opt-in Ollama tool catalog; command execution needs human approval."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import locale
import ctypes
import ipaddress
import socket
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

POLICY_KEYS = ('commandline', 'powershell', 'sensors', 'location', 'vision', 'webcam',
               'web', 'printer', '3d_printer', 'robotics')
POLICY_MODES = ('ask', 'deny', 'allow', 'allow_unattended')
UNATTENDED_DEVICE_PLUGINS = frozenset({'printer', '3d_printer', 'robotics'})
TOOL_PLUGINS = {'run_commandline': 'commandline', 'run_powershell': 'powershell',
                'get_system_sensors': 'sensors', 'get_device_location': 'location',
                'capture_webcam_photo': 'webcam',
                'search_web': 'web', 'fetch_web_page': 'web',
                'list_printers': 'printer', 'get_print_queue': 'printer', 'print_file': 'printer',
                'get_3d_printer_status': '3d_printer', 'submit_3d_print': '3d_printer',
                'cancel_3d_print': '3d_printer',
                'get_robot_status': 'robotics', 'send_robot_command': 'robotics',
                'emergency_stop_robot': 'robotics'}
PHYSICAL_CONFIRMATION_TOOLS = frozenset({'print_file', 'submit_3d_print', 'send_robot_command'})


def plugin_policy(config: dict, key: str) -> str:
    value = str(config.get(f'plugin_{key}_policy', 'ask') or '').strip().lower()
    if value == 'allow_unattended' and key not in UNATTENDED_DEVICE_PLUGINS:
        return 'ask'
    return value if value in POLICY_MODES else 'ask'


def physical_tool_needs_confirmation(name: str, policy: str) -> bool:
    """Explicit unattended consent applies only to selected physical actions."""
    return name in PHYSICAL_CONFIRMATION_TOOLS and policy != 'allow_unattended'


def tool_schemas(config: dict) -> list[dict]:
    empty = {'type': 'object', 'properties': {}}
    catalog = (
        ('run_commandline', 'Execute a local terminal command. The current chat has its own working directory.',
         {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}),
        ('run_powershell', 'Execute a PowerShell command in the chat working directory.',
         {'type': 'object', 'properties': {'command': {'type': 'string'}}, 'required': ['command']}),
        ('get_system_sensors', 'Read available CPU, RAM, battery, temperature and fan readings without inventing absent sensors.', empty),
        ('get_device_location', 'Read the device location or clearly labeled offline region clues; never invent coordinates.', empty),
        ('capture_webcam_photo', 'Capture one current webcam image for the vision-capable model.', empty),
        ('search_web', 'Search the public internet. The query is sent to an external search provider.',
         {'type': 'object', 'properties': {'query': {'type': 'string'},
          'max_results': {'type': 'integer', 'minimum': 1, 'maximum': 8}}, 'required': ['query']}),
        ('fetch_web_page', 'Fetch readable text from one public HTTP(S) page. Private and local network addresses are blocked.',
         {'type': 'object', 'properties': {'url': {'type': 'string'}}, 'required': ['url']}),
        ('list_printers', 'List printers visible to the operating system.', empty),
        ('get_print_queue', 'Read current print jobs and spooler status without submitting or cancelling any job.', empty),
        ('print_file', 'Print one existing file from the chat workspace or OUTPUTS on the default system printer.',
         {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}),
        ('get_3d_printer_status', 'Read job and printer status from the configured OctoPrint-compatible endpoint.', empty),
        ('submit_3d_print', 'Upload a G-code, STL or 3MF file from the chat workspace or OUTPUTS to the configured 3D printer. start=true physically starts the job.',
         {'type': 'object', 'properties': {'path': {'type': 'string'}, 'start': {'type': 'boolean'}}, 'required': ['path']}),
        ('cancel_3d_print', 'Cancel the current job on the configured 3D printer.', empty),
        ('get_robot_status', 'Read telemetry/status from the configured local robot, arm, drone or RC bridge.', empty),
        ('send_robot_command', 'Send a bounded JSON action to the configured local robot bridge. The bridge must validate and enforce its own motion limits and dead-man timeout.',
         {'type': 'object', 'properties': {'action': {'type': 'string'}, 'parameters': {'type': 'object'}}, 'required': ['action']}),
        ('emergency_stop_robot', 'Request an immediate stop from the configured robot, arm, drone or RC bridge.', empty),
    )
    tools = []
    for name, description, parameters in catalog:
        key = TOOL_PLUGINS[name]
        if not config.get(f'plugin_{key}_enabled', False) or plugin_policy(config, key) == 'deny':
            continue
        if name == 'run_powershell' and not (shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')):
            continue
        if name == 'capture_webcam_photo' and (not config.get('plugin_vision_enabled', False)
                or plugin_policy(config, 'vision') == 'deny'):
            continue
        tools.append({'type': 'function', 'function': {'name': name, 'description': description, 'parameters': parameters}})
    return tools


def parse_tool_call(call: dict, allowed_names: set[str]) -> tuple[str, dict]:
    function = call.get('function') if isinstance(call, dict) else None
    if not isinstance(function, dict):
        raise ValueError('Invalid tool call')
    name = str(function.get('name', '') or '')
    if name not in allowed_names or name not in TOOL_PLUGINS:
        raise ValueError('Tool is not enabled')
    arguments = function.get('arguments', {})
    if isinstance(arguments, str):
        arguments = json.loads(arguments)
    if not isinstance(arguments, dict):
        raise ValueError('Invalid tool arguments')
    if name in ('run_commandline', 'run_powershell'):
        command = arguments.get('command', '')
        if not isinstance(command, str) or not command.strip() or len(command) > 2000 or '\0' in command:
            raise ValueError('Invalid or oversized command')
        return name, {'command': command.strip()}
    if name == 'search_web':
        query = arguments.get('query', '')
        if not isinstance(query, str) or not query.strip() or len(query) > 500 or '\0' in query:
            raise ValueError('Invalid web search query')
        try:
            max_results = max(1, min(8, int(arguments.get('max_results', 5))))
        except (TypeError, ValueError):
            raise ValueError('Invalid result count') from None
        return name, {'query': query.strip(), 'max_results': max_results}
    if name == 'fetch_web_page':
        url = arguments.get('url', '')
        if not isinstance(url, str) or len(url) > 2000 or urlparse(url).scheme not in {'http', 'https'}:
            raise ValueError('Invalid public HTTP(S) URL')
        return name, {'url': url.strip()}
    if name in {'print_file', 'submit_3d_print'}:
        path = arguments.get('path', '')
        if not isinstance(path, str) or not path.strip() or len(path) > 1000 or '\0' in path:
            raise ValueError('Invalid file path')
        result = {'path': path.strip()}
        if name == 'submit_3d_print':
            result['start'] = bool(arguments.get('start', False))
        return name, result
    if name == 'send_robot_command':
        action = arguments.get('action', '')
        parameters = arguments.get('parameters', {})
        if (not isinstance(action, str) or not action.strip() or len(action) > 64
                or not action.replace('_', '').replace('-', '').isalnum()):
            raise ValueError('Invalid robot action')
        if not isinstance(parameters, dict) or len(json.dumps(parameters, ensure_ascii=False)) > 4000:
            raise ValueError('Invalid or oversized robot parameters')
        return name, {'action': action.strip(), 'parameters': parameters}
    if arguments:
        raise ValueError('This tool accepts no arguments')
    return name, {}


def parse_command_call(call: dict, allowed_names: set[str]) -> tuple[str, str]:
    name, arguments = parse_tool_call(call, allowed_names)
    if 'command' not in arguments:
        raise ValueError('Tool is not a command')
    return name, arguments['command']


def run_approved_command(name: str, command: str, cwd: Path) -> str:
    cwd = Path(cwd)
    cwd.mkdir(parents=True, exist_ok=True)
    if name == 'run_commandline':
        args = ['cmd.exe', '/d', '/s', '/c', command] if os.name == 'nt' else ['/bin/sh', '-c', command]
    elif name == 'run_powershell':
        exe = shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')
        if not exe:
            return 'PowerShell is unavailable.'
        args = [exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', command]
    else:
        return 'Unknown tool.'
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, errors='replace', timeout=20)
        return f'Exit code: {done.returncode}\n{(done.stdout + done.stderr)[:8000]}'
    except subprocess.TimeoutExpired:
        return 'Command timed out after 20 seconds.'
    except OSError as exc:
        return f'Command could not start: {exc}'


class _ReadableHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {'script', 'style', 'noscript', 'svg'}:
            self._ignored += 1
        elif tag in {'p', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'}:
            self.parts.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in {'script', 'style', 'noscript', 'svg'} and self._ignored:
            self._ignored -= 1
        elif tag in {'p', 'li', 'h1', 'h2', 'h3', 'h4', 'tr'}:
            self.parts.append('\n')

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)

    def text(self, limit: int = 16000) -> str:
        value = re.sub(r'\n\s*\n+', '\n\n', re.sub(r'[ \t]+', ' ', ''.join(self.parts))).strip()
        return value[:limit]


class _DuckResults(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._active: dict | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        classes = set(str(values.get('class', '')).split())
        if tag == 'a' and 'result__a' in classes:
            href = str(values.get('href', '') or '')
            parsed = urlparse(href)
            if 'uddg' in parse_qs(parsed.query):
                href = unquote(parse_qs(parsed.query)['uddg'][0])
            self._active = {'title': '', 'url': href}

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._active['title'] += data

    def handle_endtag(self, tag: str) -> None:
        if tag == 'a' and self._active is not None:
            title = re.sub(r'\s+', ' ', self._active['title']).strip()
            url = self._active['url']
            if title and urlparse(url).scheme in {'http', 'https'}:
                self.results.append({'title': title[:300], 'url': url[:2000]})
            self._active = None


def search_public_web(query: str, max_results: int = 5) -> str:
    try:
        response = requests.get(
            'https://html.duckduckgo.com/html/', params={'q': str(query)}, timeout=(5, 15),
            headers={'User-Agent': 'OllamaVibeDesk/1.0 (+local user-authorized search)'},
        )
        response.raise_for_status()
        if len(response.content) > 2_000_000:
            raise RuntimeError('Search response exceeded 2 MB')
        parser = _DuckResults()
        parser.feed(response.text)
        results = parser.results[:max(1, min(8, int(max_results)))]
        return json.dumps({'query': query, 'provider': 'DuckDuckGo HTML', 'results': results,
                           'note': 'Search snippets are leads, not verified facts.'}, ensure_ascii=False)
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return json.dumps({'query': query, 'results': [], 'error': str(exc),
                           'note': 'Internet search failed; continue with an offline alternative.'}, ensure_ascii=False)


def _validate_public_url(url: str) -> str:
    parsed = urlparse(str(url or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Only public HTTP(S) URLs without embedded credentials are allowed')
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443,
                                                               type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError(f'Host could not be resolved: {exc}') from None
    if not addresses:
        raise ValueError('Host did not resolve')
    for address in addresses:
        ip = ipaddress.ip_address(address.split('%')[0])
        if not ip.is_global:
            raise ValueError('Private, local, reserved and link-local web addresses are blocked')
    return parsed.geturl()


def fetch_public_web_page(url: str) -> str:
    try:
        current = _validate_public_url(url)
        response = None
        for _ in range(4):
            response = requests.get(current, timeout=(5, 20), allow_redirects=False, stream=True,
                                    headers={'User-Agent': 'OllamaVibeDesk/1.0 (+local user-authorized fetch)'})
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get('Location', '')
                response.close()
                current = _validate_public_url(urljoin(current, location))
                continue
            response.raise_for_status()
            break
        if response is None or response.is_redirect:
            raise RuntimeError('Too many redirects')
        content = bytearray()
        for chunk in response.iter_content(65536):
            content.extend(chunk)
            if len(content) > 1_000_000:
                raise RuntimeError('Page exceeded the 1 MB research limit')
        content_type = response.headers.get('Content-Type', '')
        response.close()
        text = bytes(content).decode(response.encoding or 'utf-8', errors='replace')
        if 'html' in content_type.lower() or '<html' in text[:1000].lower():
            parser = _ReadableHTML()
            parser.feed(text)
            text = parser.text()
        else:
            text = re.sub(r'\s+', ' ', text).strip()[:16000]
        return json.dumps({'url': current, 'content_type': content_type, 'text': text,
                           'truncated': len(text) >= 16000}, ensure_ascii=False)
    except (requests.RequestException, ValueError, RuntimeError, UnicodeError) as exc:
        return json.dumps({'url': url, 'error': str(exc),
                           'note': 'Page fetch failed; continue without this source.'}, ensure_ascii=False)


def _allowed_file(path: str, roots: list[Path], suffixes: set[str] | None = None) -> Path:
    raw = Path(str(path or ''))
    candidates = [raw] if raw.is_absolute() else [Path(root) / raw for root in roots]
    permitted = [Path(root).resolve() for root in roots]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if (resolved.is_file() and not resolved.is_symlink()
                and any(resolved.is_relative_to(root) for root in permitted)):
            if suffixes and resolved.suffix.lower() not in suffixes:
                raise ValueError(f'Unsupported file type: {resolved.suffix or "none"}')
            if resolved.stat().st_size > 100_000_000:
                raise ValueError('File exceeds 100 MB')
            return resolved
    raise ValueError('File is missing or outside the permitted workspace/OUTPUTS roots')


def list_system_printers() -> str:
    try:
        if os.name == 'nt':
            exe = shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')
            if not exe:
                return json.dumps({'printers': [], 'error': 'PowerShell is unavailable.'})
            done = subprocess.run([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                                   'Get-Printer | Select-Object Name,DriverName,PortName,PrinterStatus,Default | ConvertTo-Json -Compress'],
                                  capture_output=True, text=True, errors='replace', timeout=15)
            return json.dumps({'raw': done.stdout[:12000], 'exit_code': done.returncode}, ensure_ascii=False)
        done = subprocess.run(['lpstat', '-p', '-d'], capture_output=True, text=True, errors='replace', timeout=10)
        return json.dumps({'raw': (done.stdout + done.stderr)[:12000], 'exit_code': done.returncode}, ensure_ascii=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return json.dumps({'printers': [], 'error': str(exc)}, ensure_ascii=False)


def get_print_queue() -> str:
    """Read spooler state without changing or releasing queued print jobs."""
    try:
        if os.name == 'nt':
            exe = shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')
            if not exe:
                return json.dumps({'jobs': [], 'error': 'PowerShell is unavailable.'})
            script = ("$spooler=Get-Service Spooler -ErrorAction SilentlyContinue | "
                      "Select-Object Name,Status; "
                      "$jobs=@(Get-Printer -ErrorAction SilentlyContinue | ForEach-Object { "
                      "$printer=$_.Name; Get-PrintJob -PrinterName $printer -ErrorAction SilentlyContinue | "
                      "Select-Object @{Name='PrinterName';Expression={$printer}},Id,DocumentName,JobStatus,TotalPages,PagesPrinted }); "
                      "[pscustomobject]@{Spooler=$spooler;Jobs=$jobs} | ConvertTo-Json -Compress -Depth 5")
            command = [exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script]
        else:
            command = ['lpstat', '-r', '-o']
        done = subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=15)
        return json.dumps({'raw': (done.stdout + done.stderr)[:16000], 'exit_code': done.returncode}, ensure_ascii=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return json.dumps({'jobs': [], 'error': str(exc)}, ensure_ascii=False)


def print_output_file(path: str, roots: list[Path]) -> str:
    try:
        file_path = _allowed_file(path, roots, {'.pdf', '.txt', '.png', '.jpg', '.jpeg', '.bmp'})
        if os.name == 'nt':
            exe = shutil.which('powershell.exe') or shutil.which('powershell') or shutil.which('pwsh')
            if not exe:
                raise RuntimeError('PowerShell is unavailable')
            env = dict(os.environ, OVD_PRINT_FILE=str(file_path))
            subprocess.Popen([exe, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
                              'Start-Process -FilePath $env:OVD_PRINT_FILE -Verb Print'], env=env,
                             cwd=str(file_path.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(['lp', str(file_path)], cwd=str(file_path.parent),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return json.dumps({'submitted': True, 'path': str(file_path),
                           'note': 'The operating-system print queue accepted the request; physical completion is not verified.'}, ensure_ascii=False)
    except (OSError, ValueError, RuntimeError) as exc:
        return json.dumps({'submitted': False, 'error': str(exc)}, ensure_ascii=False)


def _device_headers(api_key: str = '') -> dict[str, str]:
    return {'X-Api-Key': api_key} if api_key else {}


def get_3d_printer_status(base_url: str, api_key: str = '') -> str:
    try:
        job = requests.get(base_url.rstrip('/') + '/api/job', headers=_device_headers(api_key), timeout=(3, 10))
        printer = requests.get(base_url.rstrip('/') + '/api/printer', headers=_device_headers(api_key), timeout=(3, 10))
        job.raise_for_status(); printer.raise_for_status()
        return json.dumps({'job': job.json(), 'printer': printer.json()}, ensure_ascii=False)[:20000]
    except (requests.RequestException, ValueError) as exc:
        return json.dumps({'error': str(exc), 'note': '3D printer unavailable; continue without it.'}, ensure_ascii=False)


def submit_3d_print(path: str, start: bool, roots: list[Path], base_url: str, api_key: str = '') -> str:
    try:
        file_path = _allowed_file(path, roots, {'.gcode', '.gco', '.gc', '.stl', '.3mf'})
        with file_path.open('rb') as handle:
            response = requests.post(base_url.rstrip('/') + '/api/files/local', headers=_device_headers(api_key),
                                     data={'select': 'true', 'print': 'true' if start else 'false'},
                                     files={'file': (file_path.name, handle)}, timeout=(5, 60))
        response.raise_for_status()
        return json.dumps({'uploaded': True, 'started': bool(start), 'file': file_path.name,
                           'response': response.json() if response.content else {}}, ensure_ascii=False)[:20000]
    except (OSError, requests.RequestException, ValueError) as exc:
        return json.dumps({'uploaded': False, 'started': False, 'error': str(exc)}, ensure_ascii=False)


def cancel_3d_print(base_url: str, api_key: str = '') -> str:
    try:
        response = requests.post(base_url.rstrip('/') + '/api/job', headers={**_device_headers(api_key), 'Content-Type': 'application/json'},
                                 json={'command': 'cancel'}, timeout=(3, 10))
        response.raise_for_status()
        return json.dumps({'cancel_requested': True})
    except requests.RequestException as exc:
        return json.dumps({'cancel_requested': False, 'error': str(exc)}, ensure_ascii=False)


def robot_bridge_request(base_url: str, operation: str, action: str = '', parameters: dict | None = None) -> str:
    endpoint = base_url.rstrip('/')
    try:
        if operation == 'status':
            response = requests.get(endpoint + '/status', timeout=(2, 8))
        elif operation == 'stop':
            response = requests.post(endpoint + '/stop', json={'source': 'OllamaVibeDesk'}, timeout=(2, 8))
        else:
            response = requests.post(endpoint + '/command', json={
                'action': action, 'parameters': parameters or {}, 'source': 'OllamaVibeDesk',
                'deadman_timeout_ms': 2000,
            }, timeout=(2, 10))
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            payload = {'text': response.text[:12000]}
        return json.dumps({'operation': operation, 'response': payload}, ensure_ascii=False)[:20000]
    except requests.RequestException as exc:
        return json.dumps({'operation': operation, 'error': str(exc),
                           'note': 'Robot bridge unavailable; stop or use a non-physical alternative.'}, ensure_ascii=False)


def read_system_sensors() -> str:
    import psutil
    memory = psutil.virtual_memory()
    data = {'cpu_percent': psutil.cpu_percent(interval=None),
            'ram': {'used_bytes': memory.used, 'available_bytes': memory.available},
            'battery': None, 'temperatures_celsius': {}, 'fans_rpm': {}}
    if hasattr(psutil, 'sensors_battery'):
        try:
            battery = psutil.sensors_battery()
            if battery:
                data['battery'] = {'percent': battery.percent, 'plugged_in': battery.power_plugged}
        except (OSError, RuntimeError):
            pass
    for method, field in (('sensors_temperatures', 'temperatures_celsius'), ('sensors_fans', 'fans_rpm')):
        if hasattr(psutil, method):
            try:
                sensors = getattr(psutil, method)()
                for group, readings in list(sensors.items())[:12]:
                    data[field][group] = [{'label': str(item.label)[:80],
                        'value': getattr(item, 'current', None)} for item in readings[:12]]
            except (OSError, RuntimeError):
                pass
    data['note'] = 'Empty/null means unavailable; missing sensor values must not be estimated.'
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def configured_region() -> str:
    """Read Windows' user-configured region; this is not a live device fix."""
    if os.name == 'nt':
        try:
            buffer = ctypes.create_unicode_buffer(12)
            function = ctypes.windll.kernel32.GetUserDefaultGeoName
            function.argtypes = (ctypes.c_wchar_p, ctypes.c_int)
            function.restype = ctypes.c_int
            if function(buffer, len(buffer)):
                return buffer.value.upper()
        except (AttributeError, OSError, ValueError):
            pass
    return ''


def offline_location_clues(language_hint: str = '') -> dict:
    """System preferences suggest a region, never a verified physical position."""
    country = configured_region()
    try:
        system_locale = locale.getlocale()[0] or ''
    except (ValueError, TypeError):
        system_locale = ''
    parts = system_locale.replace('-', '_').split('_')
    locale_country = parts[1].upper() if len(parts) > 1 and len(parts[1]) == 2 else ''
    language = parts[0].lower() if parts else ''
    application_language = str(language_hint or '').split('-')[0].split('_')[0].lower()
    if language in ('c', 'posix', ''):
        language = application_language
    timezone = datetime.now().astimezone().tzname() or ''
    inferred_country = country or locale_country
    language_regions = {'de': ['DE', 'AT', 'CH', 'LI', 'LU', 'BE'],
                        'fr': ['FR', 'BE', 'CH', 'CA', 'LU'],
                        'es': ['ES', 'MX', 'AR', 'CO', 'CL'],
                        'pt': ['PT', 'BR', 'AO'], 'nl': ['NL', 'BE']}
    return {'type': 'offline_region_clues', 'configured_country': country or None,
            'locale_region': locale_country or None, 'system_language': language or None,
            'application_language': application_language or None,
            'timezone': timezone or None, 'possible_country': inferred_country or None,
            'language_possible_regions': language_regions.get(language, []),
            'accuracy': 'unknown; system preferences do not prove where the device is',
            'latitude': None, 'longitude': None,
            'note': 'The configured region, language and timezone can be wrong or differ from the physical location. Never claim exact coordinates.'}


def read_device_location(timeout_ms: int = 11000, language_hint: str = '') -> str:
    """One-shot Qt Positioning request, with offline region clues if unavailable."""
    from PyQt6.QtCore import QEventLoop, QTimer
    from PyQt6.QtPositioning import QGeoPositionInfo, QGeoPositionInfoSource
    source = QGeoPositionInfoSource.createDefaultSource(None)
    if source is None:
        return json.dumps(offline_location_clues(language_hint), ensure_ascii=False)
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    result: dict = {}
    done = {'value': False}

    def received(position):
        coordinate = position.coordinate()
        if coordinate.isValid():
            result.update(type='device_position', latitude=coordinate.latitude(), longitude=coordinate.longitude(),
                          accuracy_meters=position.attribute(QGeoPositionInfo.Attribute.HorizontalAccuracy)
                          if position.hasAttribute(QGeoPositionInfo.Attribute.HorizontalAccuracy) else None,
                          source=source.sourceName())
        done['value'] = True
        loop.quit()

    def failed(_error):
        done['value'] = True
        loop.quit()

    source.positionUpdated.connect(received)
    source.errorOccurred.connect(failed)
    timer.timeout.connect(loop.quit)
    timer.start(max(1000, min(15000, int(timeout_ms))))
    source.requestUpdate(max(1000, min(10000, int(timeout_ms) - 500)))
    if not done['value']:
        loop.exec()
    if not result:
        result = offline_location_clues(language_hint)
        result['note'] += ' Device positioning did not return a valid fix.'
    return json.dumps(result, ensure_ascii=False, allow_nan=False)


def encode_image(path: str) -> str:
    candidate = Path(path)
    if candidate.stat().st_size > 5_000_000:
        raise ValueError('Image exceeds 5 MB')
    return base64.b64encode(candidate.read_bytes()).decode('ascii')

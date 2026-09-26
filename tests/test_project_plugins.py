"""Integration checks for project releases and opt-in Ollama tools."""
import json
import base64
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.project_archives import (create_archives, parse_projects, safe_relative_path,
                                  workspace_snapshot, changed_workspace_files, inspect_project,
                                  latest_archive_for_sessions, restore_project_archive)
from app.plugin_tools import (parse_command_call, parse_tool_call, tool_schemas, run_approved_command,
                              plugin_policy, offline_location_clues, read_system_sensors, read_device_location,
                              PHYSICAL_CONFIRMATION_TOOLS, physical_tool_needs_confirmation,
                              get_print_queue, fetch_public_web_page, robot_bridge_request)
from app.config import normalize_config
from app.ollama_client import OllamaClient
from app.main import (ChatWorker, assistant_answer_is_usable_for_auto_answer,
                      build_assistant_visible_content, code_extension_for_language,
                      promote_thinking_code)


class ProjectPluginTests(unittest.TestCase):
    def test_latest_project_archive_can_be_restored_for_context_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'projects'
            older = create_archives(
                'File: main.py\n```python\nprint("old")\n```',
                root, 'program', 'model', 'old-session',
            )[0]
            newer = create_archives(
                'File: main.py\n```python\nprint("current")\n```\nFile: config.json\n```json\n{"ready": true}\n```',
                root, 'program', 'model', 'current-session',
            )[0]
            self.assertEqual(latest_archive_for_sessions(root, {'current-session'}), newer)
            self.assertIsNone(latest_archive_for_sessions(root, {'missing-session'}))
            destination = Path(folder) / 'workspace'
            checkpoint = restore_project_archive(newer, destination)
            self.assertEqual((destination / 'main.py').read_text(encoding='utf-8'), 'print("current")\n')
            self.assertEqual(json.loads((destination / 'config.json').read_text(encoding='utf-8')), {'ready': True})
            self.assertIn('main.py', checkpoint['text_files'])
            self.assertNotEqual(older, newer)

    def test_auto_answer_rejects_file_status_fragment_but_accepts_real_code(self):
        self.assertFalse(assistant_answer_is_usable_for_auto_answer('index.html 1 2000'))
        self.assertFalse(assistant_answer_is_usable_for_auto_answer('File: index.html\nLines: 1/2000'))
        self.assertTrue(assistant_answer_is_usable_for_auto_answer('Die Datei index.html wurde vollständig erstellt und kann nun getestet werden.'))
        self.assertTrue(assistant_answer_is_usable_for_auto_answer('```html\n<h1>Working</h1>\n```'))

    def test_long_reasoning_preview_does_not_hide_the_code_answer(self):
        answer = 'File: main.py\n```python\nprint("visible code")\n```'
        visible = build_assistant_visible_content(answer, ('reasoning detail\n' * 5000), 'de')
        self.assertIn('print("visible code")', visible)
        self.assertIn('Denkvorschau gekürzt', visible)
        self.assertLess(len(visible), 30_000)

    def test_code_in_reasoning_preview_is_not_shortened_away(self):
        code = "```python\n" + "print('line')\n" * 1800 + "print('CODE_END_MARKER')\n```"
        visible = build_assistant_visible_content("The explanation follows.", code, "de")
        self.assertIn("CODE_END_MARKER", visible)
        self.assertIn("```python", visible)

    def test_complete_code_in_reasoning_is_promoted_to_answer(self):
        thinking = "I will implement the requested program.\n```python\nprint('COMPLETE_PROGRAM')\n```"
        promoted = promote_thinking_code("Here is the implementation.", thinking, "de")
        self.assertIn("COMPLETE_PROGRAM", promoted)
        self.assertIn("```python", promoted)
        self.assertIn("Denkstrom", promoted)

    def test_independent_projects_model_versions_and_inherited_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = ('Project: Clock\nFile: src/main.py\n```python\nprint(1)\n```\n'
                     'File: requirements.txt\n```text\nrequests\n```\n'
                     'Project: Paint\n### File: index.html\n```html\n<h1>Paint</h1>\n```')
            paths = create_archives(first, root, 'discussion', 'model-a:7b', 'chat-1')
            self.assertEqual(len(paths), 2)
            self.assertEqual(paths[0].name, 'v0001.zip')
            with zipfile.ZipFile(paths[0]) as archive:
                self.assertEqual(archive.read('src/main.py'), b'print(1)\n')
                self.assertEqual(archive.read('requirements.txt'), b'requests\n')
                self.assertEqual(json.loads(archive.read('_archive/manifest.json'))['model'], 'model-a:7b')
            second = create_archives('Project: Clock\nFile: src/main.py\n```python\nprint(2)\n```', root, 'discussion', 'model-a:7b', 'chat-2')[0]
            with zipfile.ZipFile(second) as archive:
                self.assertEqual(archive.read('requirements.txt'), b'requests\n')
                self.assertEqual(archive.read('src/main.py'), b'print(2)\n')
            other = create_archives('Project: Clock\n```python\nprint(3)\n```', root, 'discussion', 'model-b:7b', 'chat-3')[0]
            self.assertEqual(other.name, 'v0001.zip')
            self.assertNotEqual(other.parent, second.parent)

    def test_paths_and_empty_answers(self):
        for path in ('../secret.txt', '/etc/passwd', 'C:\\Users\\x.txt', 'CON.txt', 'a//b.py'):
            self.assertIsNone(safe_relative_path(path))
        self.assertFalse(parse_projects('No code here', 'topic'))

    def test_incomplete_answer_exports_only_closed_blocks_as_partial_archive(self):
        answer = '''Project: partial_app
File: finished.py
```python
print("complete")
```
File: cut_off.py
```python
def unfinished(
'''
        project = parse_projects(answer, 'topic', include_unclosed=False)[0]
        self.assertEqual(set(project['files']), {'finished.py'})
        with tempfile.TemporaryDirectory() as folder:
            release = create_archives(
                answer, Path(folder), 'topic', 'model', 'chat',
                include_unclosed=False, partial_source=True,
            )[0]
            with zipfile.ZipFile(release) as archive:
                self.assertIn('finished.py', archive.namelist())
                self.assertNotIn('cut_off.py', archive.namelist())
                report = json.loads(archive.read('_archive/project_check.json'))
                self.assertIn('partial_model_response', {item['code'] for item in report['issues']})
                self.assertEqual(report['status'], 'needs_review')

    def test_formatted_and_fenced_file_markers_keep_real_extensions(self):
        answer = '''Project: organic_rotator
**File: project.godot**
```ini
config_version=5
```
```text
File: scenes/Main.tscn
```
```gdscene
[gd_scene format=3]
```
### **File: scripts/organic_object.gd**
```gdscript
extends Node3D
```
'''
        projects = parse_projects(answer, 'topic')
        self.assertEqual(set(projects[0]['files']), {
            'project.godot', 'scenes/Main.tscn', 'scripts/organic_object.gd'
        })
        self.assertNotIn('source.txt', projects[0]['files'])
        self.assertEqual(code_extension_for_language('gdscript', 'extends Node3D')[1], 'gd')
        self.assertEqual(code_extension_for_language('gdscene', '[gd_scene format=3]')[1], 'tscn')

    def test_unlabeled_text_blocks_infer_godot_files_and_complete_project(self):
        answer = '''Project: organic_rotator
```text
[gd_scene load_steps=2 format=3]

[node name="Main" type="Node3D"]
```
```text
extends Node3D

func _process(delta):
    rotate_y(delta * 0.2)
```
'''
        projects = parse_projects(answer, 'topic')
        self.assertEqual(set(projects[0]['files']), {'main.tscn', 'main.gd'})
        self.assertEqual(projects[0]['inferred_files']['main.tscn']['confidence'], 'high')
        with tempfile.TemporaryDirectory() as folder:
            release = create_archives(answer, Path(folder), 'topic', 'model', 'chat')[0]
            with zipfile.ZipFile(release) as archive:
                names = set(archive.namelist())
                self.assertIn('project.godot', names)
                self.assertIn('_archive/PROJECT_CHECK.md', names)
                report = json.loads(archive.read('_archive/project_check.json'))
                manifest = json.loads(archive.read('_archive/manifest.json'))
                self.assertEqual(report['project_type'], 'godot')
                self.assertEqual(report['status'], 'structure_complete')
                self.assertEqual(report['entry_points'][0], 'main.tscn')
                self.assertEqual(manifest['generated_files'][0]['path'], 'project.godot')
                self.assertIn('run/main_scene="res://main.tscn"', archive.read('project.godot').decode())

    def test_project_check_reports_syntax_and_missing_resource_errors(self):
        files = {
            'project.godot': b'config_version=5\n[application]\nrun/main_scene="res://Main.tscn"\n',
            'Main.tscn': b'[gd_scene load_steps=2 format=3]\n[ext_resource path="res://missing.gd" type="Script" id="1"]\n',
            'settings.json': b'{broken json',
        }
        report = inspect_project(files)
        codes = {item['code'] for item in report['issues']}
        self.assertEqual(report['status'], 'invalid')
        self.assertIn('syntax_error', codes)
        self.assertIn('missing_resource_reference', codes)

    def test_content_inference_keeps_ambiguous_text_as_txt(self):
        project = parse_projects('```text\njust some notes without source syntax\n```', 'notes')[0]
        self.assertEqual(set(project['files']), {'source.txt'})
        self.assertEqual(project['inferred_files']['source.txt']['extension'], 'txt')

    def test_explicit_but_wrong_txt_suffix_is_corrected_only_with_strong_evidence(self):
        answer = '''File: scenes/Main.tscn.txt
```text
[gd_scene format=3]
```
File: scripts/rotate.txt
```text
extends Node3D
func _ready():
    pass
```
File: requirements.txt
```text
requests
```
'''
        project = parse_projects(answer, 'godot app')[0]
        self.assertEqual(set(project['files']), {
            'scenes/Main.tscn', 'scripts/rotate.gd', 'requirements.txt'
        })
        self.assertEqual(project['inferred_files']['scenes/Main.tscn']['original_path'], 'scenes/Main.tscn.txt')
        self.assertNotIn('requirements.txt', project['inferred_files'])

    def test_command_workspace_binary_assets_are_archived(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / 'generated_code' / 'projects' / 'chat-1'
            directory.mkdir(parents=True)
            before = workspace_snapshot(directory)
            (directory / 'src').mkdir()
            (directory / 'src' / 'main.py').write_text('print("hello")', encoding='utf-8')
            (directory / 'icon.png').write_bytes(b'\x89PNG\r\n\x1a\n')
            files = changed_workspace_files(directory, before)
            release = create_archives('Program ready.', Path(folder) / 'generated_code', 'My Program', 'model', 'chat-1', files)[0]
            with zipfile.ZipFile(release) as archive:
                self.assertEqual(archive.read('icon.png'), b'\x89PNG\r\n\x1a\n')
                self.assertEqual(archive.read('src/main.py'), b'print("hello")')
            self.assertEqual(changed_workspace_files(directory, workspace_snapshot(directory)), {})

    def test_tools_disabled_until_enabled_and_arguments_validated(self):
        self.assertEqual(tool_schemas({}), [])
        schemas = tool_schemas({'plugin_commandline_enabled': True})
        self.assertEqual([item['function']['name'] for item in schemas], ['run_commandline'])
        call = {'function': {'name': 'run_commandline', 'arguments': {'command': 'echo ready'}}}
        self.assertEqual(parse_command_call(call, {'run_commandline'}), ('run_commandline', 'echo ready'))
        with self.assertRaises(ValueError):
            parse_command_call(call, set())
        with self.assertRaises(ValueError):
            parse_command_call({'function': {'name': 'run_commandline', 'arguments': {'command': ''}}}, {'run_commandline'})
        self.assertNotIn('tools', OllamaClient('http://localhost')._payload('m', [], tools=[]))
        self.assertIn('tools', OllamaClient('http://localhost')._payload('m', [], tools=schemas))

    def test_optional_web_print_3d_and_robot_tools_are_strictly_parsed(self):
        config = normalize_config({
            'plugin_web_enabled': True, 'plugin_printer_enabled': True,
            'plugin_3d_printer_enabled': True, 'plugin_robotics_enabled': True,
        })
        names = {item['function']['name'] for item in tool_schemas(config)}
        self.assertTrue({'search_web', 'fetch_web_page', 'list_printers', 'get_print_queue', 'print_file',
                         'get_3d_printer_status', 'submit_3d_print', 'cancel_3d_print',
                         'get_robot_status', 'send_robot_command', 'emergency_stop_robot'} <= names)
        self.assertEqual(parse_tool_call(
            {'function': {'name': 'search_web', 'arguments': {'query': 'local LLM', 'max_results': 99}}}, names),
            ('search_web', {'query': 'local LLM', 'max_results': 8}))
        self.assertEqual(parse_tool_call(
            {'function': {'name': 'submit_3d_print', 'arguments': {'path': 'part.gcode', 'start': True}}}, names),
            ('submit_3d_print', {'path': 'part.gcode', 'start': True}))
        self.assertEqual(parse_tool_call(
            {'function': {'name': 'send_robot_command', 'arguments': {'action': 'move_arm', 'parameters': {'x': 1}}}}, names),
            ('send_robot_command', {'action': 'move_arm', 'parameters': {'x': 1}}))
        self.assertTrue({'print_file', 'submit_3d_print', 'send_robot_command'} <= PHYSICAL_CONFIRMATION_TOOLS)
        with self.assertRaises(ValueError):
            parse_tool_call({'function': {'name': 'send_robot_command',
                                           'arguments': {'action': '../unsafe', 'parameters': {}}}}, names)

    def test_web_fetch_blocks_private_network_and_robot_bridge_fails_cleanly(self):
        with patch('app.plugin_tools.socket.getaddrinfo', return_value=[
                (2, 1, 6, '', ('127.0.0.1', 80))]):
            result = json.loads(fetch_public_web_page('http://localhost/private'))
        self.assertIn('blocked', result['error'])
        with patch('app.plugin_tools.requests.get', side_effect=__import__('requests').ConnectionError('offline')):
            bridge = json.loads(robot_bridge_request('http://127.0.0.1:8765', 'status'))
        self.assertIn('error', bridge)
        self.assertIn('alternative', bridge['note'])

    def test_plugin_permissions_and_real_sensor_data(self):
        config = normalize_config({'plugin_location_enabled': True, 'plugin_sensors_enabled': True,
            'plugin_commandline_enabled': True, 'plugin_commandline_policy': 'deny',
            'plugin_webcam_enabled': True, 'plugin_vision_enabled': True,
            'plugin_location_policy': 'always', 'plugin_sensors_policy': 'allow'})
        self.assertEqual(plugin_policy(config, 'location'), 'ask')
        self.assertEqual(plugin_policy(config, 'sensors'), 'allow')
        unattended = normalize_config({'plugin_printer_policy': 'allow_unattended',
                                       'plugin_3d_printer_policy': 'allow_unattended',
                                       'plugin_robotics_policy': 'allow_unattended',
                                       'plugin_webcam_policy': 'allow_unattended'})
        for device in ('printer', '3d_printer', 'robotics'):
            self.assertEqual(plugin_policy(unattended, device), 'allow_unattended')
        self.assertEqual(plugin_policy(unattended, 'webcam'), 'ask')
        self.assertFalse(physical_tool_needs_confirmation('get_print_queue', 'allow'))
        self.assertTrue(physical_tool_needs_confirmation('print_file', 'allow'))
        self.assertFalse(physical_tool_needs_confirmation('print_file', 'allow_unattended'))
        self.assertFalse(physical_tool_needs_confirmation('submit_3d_print', 'allow_unattended'))
        self.assertFalse(physical_tool_needs_confirmation('send_robot_command', 'allow_unattended'))
        names = [entry['function']['name'] for entry in tool_schemas(config)]
        self.assertEqual(names, ['get_system_sensors', 'get_device_location', 'capture_webcam_photo'])
        self.assertEqual(parse_tool_call({'function': {'name': 'get_system_sensors', 'arguments': '{}'}}, set(names)),
                         ('get_system_sensors', {}))
        with self.assertRaises(ValueError):
            parse_tool_call({'function': {'name': 'get_device_location', 'arguments': {'latitude': 55}}}, set(names))
        readings = json.loads(read_system_sensors())
        self.assertGreater(readings['ram']['available_bytes'], 0)
        self.assertIn('temperatures_celsius', readings)

    def test_print_queue_is_a_read_only_spooler_query(self):
        from subprocess import CompletedProcess
        with patch('app.plugin_tools.os.name', 'nt'), \
                patch('app.plugin_tools.shutil.which', return_value='powershell.exe'), \
                patch('app.plugin_tools.subprocess.run', return_value=CompletedProcess([], 0, '{"Jobs":[]}', '')) as run:
            result = json.loads(get_print_queue())
        self.assertEqual(result['exit_code'], 0)
        command = run.call_args.args[0]
        self.assertIn('Get-PrintJob', command[-1])
        self.assertNotIn('Start-Process', command[-1])
        self.assertNotIn('Remove-PrintJob', command[-1])

    def test_unattended_device_choices_survive_config_reload(self):
        from app import config as config_module
        choices = normalize_config({
            'plugin_printer_policy': 'allow_unattended',
            'plugin_3d_printer_policy': 'allow_unattended',
            'plugin_robotics_policy': 'allow_unattended',
        })
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(config_module, 'CONFIG_PATH', Path(folder) / 'config.json'), \
                patch.object(config_module, 'ensure_directories', lambda: None):
            config_module.save_config(choices)
            reloaded = config_module.load_config()
        for device in ('printer', '3d_printer', 'robotics'):
            self.assertEqual(reloaded[f'plugin_{device}_policy'], 'allow_unattended')

    def test_offline_location_is_labeled_inference_without_coordinates(self):
        with patch('app.plugin_tools.locale.getlocale', return_value=('de_DE', 'UTF-8')):
            clues = offline_location_clues()
            self.assertEqual(clues['locale_region'], 'DE')
            self.assertIn('AT', clues['language_possible_regions'])
            self.assertIsNone(clues['latitude'])
            self.assertIn('do not prove', clues['accuracy'])
            with patch('PyQt6.QtPositioning.QGeoPositionInfoSource.createDefaultSource', return_value=None):
                self.assertEqual(json.loads(read_device_location())['type'], 'offline_region_clues')
        with patch('app.plugin_tools.locale.getlocale', return_value=('C', 'UTF-8')):
            with patch('app.plugin_tools.configured_region', return_value='DE'):
                clues = offline_location_clues('de')
            self.assertIn('DE', clues['language_possible_regions'])
            self.assertEqual(clues['possible_country'], 'DE')
            self.assertIsNone(clues['latitude'])

    def test_positioning_source_returns_measured_coordinate(self):
        from PyQt6.QtCore import QCoreApplication
        from PyQt6.QtPositioning import QGeoPositionInfoSource
        app = QCoreApplication.instance() or QCoreApplication([])
        self.assertIsNotNone(app)
        class Signal:
            def connect(self, callback):
                self.callback = callback
        class Coordinate:
            def isValid(self): return True
            def latitude(self): return 53.0
            def longitude(self): return 9.0
        class Position:
            def coordinate(self): return Coordinate()
            def hasAttribute(self, _attr): return False
        class Source:
            def __init__(self):
                self.positionUpdated, self.errorOccurred = Signal(), Signal()
            def sourceName(self): return 'test-source'
            def requestUpdate(self, _ms): self.positionUpdated.callback(Position())
        with patch.object(QGeoPositionInfoSource, 'createDefaultSource', return_value=Source()):
            result = json.loads(read_device_location(timeout_ms=1000))
        self.assertEqual(result['type'], 'device_position')
        self.assertEqual(result['latitude'], 53.0)
        self.assertEqual(result['source'], 'test-source')

    def test_model_webcam_tool_includes_photo_only_after_approval(self):
        schemas = tool_schemas(normalize_config({'plugin_webcam_enabled': True, 'plugin_vision_enabled': True}))
        requests = []
        call = {'function': {'name': 'capture_webcam_photo', 'arguments': {}}}

        def response(_client, _model, messages, _prompt, **_kwargs):
            requests.append(list(messages))
            return ({'message': {'tool_calls': [call]}} if len(requests) == 1
                    else {'message': {'content': 'I can see the approved photo.'}})

        with patch.object(OllamaClient, 'chat_response', response):
            worker = ChatWorker('http://localhost', 'vision', [{'role': 'user', 'content': 'Look'}], '', tools=schemas)
            def approve(request):
                request['approved'] = True
                request['result'] = '/tmp/approved-photo.jpg'
                request['event'].set()
            worker.tool_request.connect(approve)
            worker.run()
        self.assertEqual(requests[1][-1]['images_paths'], ['/tmp/approved-photo.jpg'])

    def test_approved_web_search_result_is_returned_to_model(self):
        schemas = tool_schemas(normalize_config({'plugin_web_enabled': True}))
        requests = []
        call = {'function': {'name': 'search_web', 'arguments': {
            'query': 'official Python documentation', 'max_results': 3,
        }}}

        def response(_client, _model, messages, _prompt, **_kwargs):
            requests.append(list(messages))
            return ({'message': {'tool_calls': [call]}} if len(requests) == 1
                    else {'message': {'content': 'I used the approved search result.'}})

        search_result = json.dumps({'results': [{'title': 'Python', 'url': 'https://python.org'}]})
        with patch.object(OllamaClient, 'chat_response', response), \
                patch('app.main.search_public_web', return_value=search_result) as search:
            worker = ChatWorker('http://localhost', 'model', [{'role': 'user', 'content': 'Research'}], '',
                                tools=schemas)

            def approve(request):
                request['approved'] = True
                request['event'].set()

            worker.tool_request.connect(approve)
            worker.run()
        search.assert_called_once_with('official Python documentation', 3)
        self.assertEqual(requests[1][-1]['role'], 'tool')
        self.assertIn('python.org', requests[1][-1]['content'])

    def test_unanswered_tool_request_is_denied_and_model_continues(self):
        schemas = tool_schemas({'plugin_commandline_enabled': True})
        requests = []
        call = {'function': {'name': 'run_commandline', 'arguments': {'command': 'echo never-run'}}}

        def response(_client, _model, messages, _prompt, **_kwargs):
            requests.append(list(messages))
            if len(requests) == 1:
                return {'message': {'content': '', 'tool_calls': [call]}}
            return {'message': {'content': 'I can explain the next steps instead.'}}

        with tempfile.TemporaryDirectory() as folder, patch.object(OllamaClient, 'chat_response', response), \
                patch('app.main.run_approved_command', side_effect=AssertionError('Unapproved command ran')):
            worker = ChatWorker('http://localhost', 'model', [{'role': 'user', 'content': 'Help'}], '',
                                tools=schemas, command_dir=Path(folder))
            chunks = []
            worker.chunk.connect(chunks.append)
            worker.tool_request.connect(lambda request: request['event'].set())
            worker.run()
            self.assertIn('alternative', requests[1][-1]['content'])
            self.assertIn('next steps', chunks[-1]['content'])

    def test_approved_command_writes_only_after_explicit_call(self):
        with tempfile.TemporaryDirectory() as folder:
            output = run_approved_command('run_commandline', 'echo ready > hello.txt', Path(folder))
            self.assertIn('Exit code: 0', output)
            self.assertIn('ready', (Path(folder) / 'hello.txt').read_text())

    def test_image_attached_only_when_selected_and_tool_error_falls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'picture.jpg'
            image.write_bytes(b'example image bytes')
            payload = OllamaClient('http://localhost')._payload('vision',
                [{'role': 'user', 'content': 'Describe', 'images_paths': [str(image)]}])
            self.assertEqual(base64.b64decode(payload['messages'][0]['images'][0]), image.read_bytes())
            self.assertNotIn('images_paths', payload['messages'][0])
            self.assertNotIn('images', OllamaClient('http://localhost')._payload('vision',
                [{'role': 'user', 'content': 'Describe'}])['messages'][0])
        schemas = tool_schemas({'plugin_commandline_enabled': True})
        worker = ChatWorker('http://localhost', 'unsupported-model', [{'role': 'user', 'content': 'Hello'}], '', tools=schemas)
        chunks = []
        worker.chunk.connect(chunks.append)
        with patch.object(OllamaClient, 'chat_response', side_effect=RuntimeError('model does not support tools')), \
                patch.object(OllamaClient, 'stream_chat', return_value=iter([{'content': 'Answer without tools'}])):
            worker.run()
        self.assertEqual(chunks[0]['content'], 'Answer without tools')


if __name__ == '__main__':
    unittest.main()

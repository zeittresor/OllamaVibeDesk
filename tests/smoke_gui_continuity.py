"""Actual offscreen Qt window + local HTTP server; never uses personal chats/settings."""
from __future__ import annotations
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QMessageBox, QSizePolicy
from PyQt6.QtCore import QPoint, QSize
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QImage
from app import main as m
from app.config import DEFAULT_CONFIG, PREFERRED_OLLAMA_MODEL
from app.models import ChatMessage
from app.hardware import HardwareProfile
from app.adaptive_context import collect_runtime as real_collect_runtime


class Handler(BaseHTTPRequestHandler):
    mode = 'ok'
    chats = []
    def log_message(self, *args): pass
    def send(self, status, data):
        body = json.dumps(data).encode() + b'\n'
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        self.send(200, {'models':[{'name':'test:latest','context_length':4096,'size_vram':0}]})
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path == '/api/show':
            self.send(200, {'model_info':{'general.architecture':'test','test.context_length':32768}}); return
        Handler.chats.append(data)
        if Handler.mode == 'oom' and len(Handler.chats) == 1:
            self.send(500, {'error':'CUDA out of memory'}); return
        if Handler.mode == 'always_oom':
            self.send(500, {'error':'CUDA out of memory'}); return
        if Handler.mode == 'slow':
            time.sleep(.25)
        if Handler.mode == 'cut_code':
            if len(Handler.chats) == 1:
                self.send(200, {'message':{'content':'Project: Sample\nFile: app.py\n```python\nprint("hel'},
                                'done':True, 'done_reason':'length', 'prompt_eval_count':120}); return
            self.send(200, {'message':{'content':'hello")\n```\n'}, 'done':True,
                            'done_reason':'stop', 'prompt_eval_count':140}); return
        if Handler.mode == 'always_cut_code':
            self.send(200, {'message':{'content':'File: app.py\n```python\nprint(1'},
                            'done':True, 'done_reason':'length'}); return
        if Handler.mode == 'metadata_fragment':
            if len(Handler.chats) == 1:
                self.send(200, {'message':{'content':'index.html 1 2000'},
                                'done':True, 'done_reason':'stop'}); return
            self.send(200, {'message':{'content':'Die vollständige sichtbare Antwort mit dem angeforderten Programm.'},
                            'done':True, 'done_reason':'stop'}); return
        if Handler.mode == 'context_review_restart':
            self.send(200, {'message': {'content': 'RESTART'}, 'done': True,
                            'done_reason': 'stop', 'prompt_eval_count': 90, 'eval_count': 1}); return
        if Handler.mode in ('thinking_then_answer', 'thinking_only'):
            if Handler.mode == 'thinking_only' or len(Handler.chats) == 1:
                self.send(200, {'message':{'thinking':'Plan for the task, without final text.', 'content':''},
                                'done':True, 'done_reason':'length', 'prompt_eval_count':120, 'eval_count':200}); return
            self.send(200, {'message':{'content':'Die fertige Antwort mit Code.'}, 'done':True,
                            'prompt_eval_count':130, 'eval_count':21}); return
        self.send(200, {'message':{'content':'Photovoltaik Solarpanel: Messung und offene Fragen.'}, 'done':True,
                        'prompt_eval_count':120, 'eval_count':15})


def wait_for(app, condition, timeout=12):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition(): return
        time.sleep(.01)
    raise AssertionError('GUI operation did not complete before timeout')


def main():
    assert m.suggested_window_size(QSize(1920, 1080)) == QSize(1728, 972)
    assert m.suggested_window_size(QSize(3840, 2160)) == QSize(2560, 1440)
    assert m.suggested_window_size(QSize(1366, 768)).width() <= 1366
    original_refresh_models = m.MainWindow.refresh_models
    app = QApplication.instance() or QApplication([])
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    cfg = dict(DEFAULT_CONFIG, tts_backend='disabled', auto_answer_enabled=False,
               auto_read_user_inputs=False, auto_read_assistant_responses=False,
               ollama_base_url=f'http://127.0.0.1:{server.server_port}', last_model='test:latest')
    def controlled_runtime(base_url, model):
        data = real_collect_runtime(base_url, model)
        data.update(ram_total=32*1024**3, ram_available=18*1024**3, gpus=[])
        return data
    try:
        with tempfile.TemporaryDirectory() as tmp, patch.multiple(m,
            CHATS_DIR=Path(tmp), KNOWLEDGE_DIR=Path(tmp) / 'knowledge_base',
            OUTPUTS_DIR=Path(tmp) / 'OUTPUTS', GENERATED_CODE_DIR=Path(tmp) / 'OUTPUTS' / 'code_blocks',
            PROJECTS_DIR=Path(tmp) / 'OUTPUTS' / 'projects',
            PROJECT_WORKSPACES_DIR=Path(tmp) / 'OUTPUTS' / 'projects' / 'workspaces',
            ATTACHMENTS_DIR=Path(tmp) / 'app_data' / 'attachments',
            load_config=lambda: dict(cfg), save_config=lambda _: None,
            ensure_directories=lambda: None, collect_runtime=controlled_runtime,
            detect_hardware=lambda: HardwareProfile(4,32,'',0,4096,1)), \
            patch.object(m.MainWindow, 'refresh_models', lambda self: self.model_combo.addItem('test:latest')):
            window = m.MainWindow(); window.showMaximized(); app.processEvents()
            assert window.isMaximized()
            window.showNormal(); app.processEvents()
            standard_prompt = window._auto_answer_llm_prompt()
            window.config['auto_answer_guidance_preset'] = 'programming_tasks'
            window.config['auto_answer_guidance_strength'] = 65
            window.config['auto_answer_guidance_apply_to_llm'] = True
            guided_prompt = window._auto_answer_llm_prompt()
            assert guided_prompt != standard_prompt and 'Programmieraufgaben' in guided_prompt
            window.config['auto_answer_guidance_preset'] = 'standard'
            window.config['last_model'] = PREFERRED_OLLAMA_MODEL
            with patch.object(m.OllamaClient, 'get_models', return_value=['test:latest', PREFERRED_OLLAMA_MODEL]):
                original_refresh_models(window)
            assert window.model_combo.currentText() == PREFERRED_OLLAMA_MODEL
            window.model_combo.setCurrentText('test:latest')
            window.config['last_model'] = ''
            with patch.object(m.OllamaClient, 'get_models', return_value=['test:latest', PREFERRED_OLLAMA_MODEL]):
                original_refresh_models(window)
            assert window.model_combo.currentText() == PREFERRED_OLLAMA_MODEL
            window.model_combo.setCurrentText('test:latest')
            assert window.main_tabs.count() == 3 and window.chat_splitter.count() == 2
            assert not window.main_tabs.tabBar().isVisible()
            assert not window.config.get('knowledge_source_path')
            window.action_enable_knowledge.setChecked(True); app.processEvents()
            linked_wiki = Path(window.config['knowledge_source_path'])
            assert linked_wiki == Path(tmp) / 'knowledge_base' / 'tiddlywiki'
            assert (linked_wiki / 'brain.html').is_file()
            window.action_enable_knowledge.setChecked(False); app.processEvents()
            window.plugins_btn.click(); app.processEvents()
            assert window.main_tabs.currentIndex() == 1
            assert window.plugin_scroll.widgetResizable()
            assert window.plugin_scroll.widget() is not None
            assert window.plugins_back_btn.text() == '← Zurück zum Hauptbereich'
            assert window.plugins_back_btn.accessibleName() == 'Zurück zum Hauptbereich'
            window.plugins_back_btn.click(); app.processEvents()
            assert window.main_tabs.currentIndex() == 0
            window.settings_btn.click(); app.processEvents()
            assert window.main_tabs.currentIndex() == 2
            assert window.settings_form is not None and not window.settings_form.isWindow()
            assert window.settings_nav.count() == 10
            settings_form = window.settings_form
            assert len(settings_form.section_headers) == 10
            assert len(settings_form.section_separators) == 10
            assert all(heading.font().italic() for heading in settings_form.section_headers)
            for previous_line, next_header in zip(settings_form.section_separators, settings_form.section_headers[1:]):
                line_bottom = previous_line.mapTo(settings_form.content, QPoint(0, 0)).y() + previous_line.height()
                title_top = next_header.mapTo(settings_form.content, QPoint(0, 0)).y()
                assert title_top - line_bottom >= 22, (line_bottom, title_top)
            # Every navigation category aligns its own visible heading with the
            # top of the right-hand viewport, including the final category.
            for row in (3, 9, 0):
                window.settings_nav.setCurrentRow(row)
                for _ in range(3):
                    app.processEvents()
                anchor = window.settings_anchors[row]
                anchor_top = anchor.mapTo(settings_form.scroll.viewport(), QPoint(0, 0)).y()
                assert -2 <= anchor_top <= 2, (row, anchor_top)
            # Re-clicking an already selected category realigns it as well.
            window.settings_nav.setCurrentRow(3); app.processEvents(); app.processEvents()
            settings_form.scroll.verticalScrollBar().setValue(
                settings_form.scroll.verticalScrollBar().value() + 100
            )
            window.settings_nav.itemClicked.emit(window.settings_nav.item(3))
            app.processEvents(); app.processEvents()
            anchor_top = window.settings_anchors[3].mapTo(
                settings_form.scroll.viewport(), QPoint(0, 0)
            ).y()
            assert -2 <= anchor_top <= 2, anchor_top
            assert window.settings_back_btn.text() == '← Zurück zum Hauptbereich'
            assert not window.settings_form.audio_postproduction_enabled.isChecked()
            assert not window.settings_form.audio_postproduction_controls.isEnabled()
            assert not window.settings_form.auto_answer_context_restart.isChecked()
            assert not window.settings_form.auto_answer_context_review_percent.isEnabled()
            assert window.settings_form.auto_answer_context_review_percent.value() == 78
            assert window.settings_form.auto_answer_context_hard_percent.value() == 92
            window.settings_back_btn.click(); app.processEvents()
            assert window.main_tabs.currentIndex() == 0 and window.settings_form is None
            window.settings_btn.click(); app.processEvents()
            settings_form = window.settings_form
            settings_form.audio_postproduction_enabled.setChecked(True)
            settings_form.audio_postproduction_echo.setValue(37)
            settings_form.auto_answer_context_restart.setChecked(True)
            settings_form.auto_answer_context_review_percent.setValue(80)
            settings_form.auto_answer_context_hard_percent.setValue(93)
            settings_form.save_btn.click(); app.processEvents()
            assert window.main_tabs.currentIndex() == 0 and window.settings_form is None
            assert window.config['audio_postproduction_enabled'] is True
            assert window.config['audio_postproduction_echo'] == 37
            assert window.config['auto_answer_context_restart_enabled'] is True
            assert window.config['auto_answer_context_review_percent'] == 80
            assert window.config['auto_answer_context_hard_percent'] == 93
            window.settings_btn.click(); app.processEvents()
            assert window.settings_form.audio_postproduction_echo.value() == 37
            assert window.settings_form.auto_answer_context_restart.isChecked()
            assert window.settings_form.auto_answer_context_hard_percent.value() == 93
            window.settings_back_btn.click(); app.processEvents()
            assert window.auto_answer_frame.height() >= 56
            assert 'ELIZA' not in window.auto_answer_checkbox.text()
            assert window.token_counter_label.isVisible()
            assert window.token_reset_btn.isVisible()
            assert window.token_reset_btn.text() == 'Kontext neu starten'
            assert window.token_reset_btn.geometry().right() <= window.auto_answer_frame.contentsRect().right()
            assert window.auto_answer_state.text() in ('AUS', 'OFF')
            assert window.activity_indicator.isVisible()
            assert window.activity_indicator.face.phase == 'idle'
            window.worker_thread = QThread(window)
            window.worker_activity_kind = 'reasoning'
            window.worker_last_activity_at = time.monotonic()
            window._update_activity_indicator()
            assert window.activity_indicator.face.phase == 'reasoning'
            assert window.activity_indicator.face.timer.isActive()
            window.worker_last_activity_at = time.monotonic() - 92
            window._update_activity_indicator()
            assert window.activity_indicator.face.phase == 'stalled'
            assert '92' in window.activity_indicator.toolTip()
            window.worker_thread = None
            window._update_activity_indicator()
            window.auto_answer_checkbox.setChecked(True)
            assert window.auto_answer_state.text() in ('AKTIV', 'ACTIVE')
            assert 'background: transparent' in window.auto_answer_frame.styleSheet()
            window.apply_theme('Arctic')
            assert '#3b82f6' in window.auto_answer_frame.styleSheet()
            window.apply_theme('Midnight')
            window.auto_answer_checkbox.setChecked(False)
            window.resize(1420, 920); app.processEvents()
            window.chat_splitter.setSizes([230, 1100]); app.processEvents()
            sidebar_before_drag = window.chat_splitter.sizes()[0]
            window.chat_splitter.setSizes([800, 500]); app.processEvents()
            assert window.chat_splitter.sizes()[0] >= sidebar_before_drag + 80, (
                'Sidebar cannot be resized at this display scale',
                sidebar_before_drag, window.chat_splitter.sizes())
            assert window.model_combo.width() >= window.model_combo.minimumWidth()
            window.resize(1900, 920); app.processEvents()
            window.chat_splitter.setSizes([480, 1300]); app.processEvents()
            assert window.activity_indicator.width() >= 140, window.activity_indicator.width()
            assert window.sidebar.minimumWidth() < window.sidebar.maximumWidth()
            assert window.chat_splitter.widget(0) is window.sidebar
            assert window.model_combo.maximumWidth() >= 600
            assert window.model_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
            window.plugin_checks['sensors'].setChecked(True)
            sensor_request = lambda: {'name': 'get_system_sensors', 'arguments': {}, 'event': threading.Event(), 'approved': False}
            approved = sensor_request()
            window.plugin_policies['sensors'].setCurrentIndex(2)
            with patch.object(QMessageBox, 'exec', side_effect=AssertionError('Always allow still prompted')):
                window._on_worker_tool_request(approved)
            assert approved['approved'] and approved['event'].is_set()
            window.plugin_policies['sensors'].setCurrentIndex(1)
            rejected = sensor_request()
            window._on_worker_tool_request(rejected)
            assert not rejected['approved'] and rejected['event'].is_set()
            window.plugin_policies['sensors'].setCurrentIndex(0)
            asked = sensor_request()
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes):
                window._on_worker_tool_request(asked)
            assert asked['approved'] and asked['event'].is_set()
            # Existing Always allow reads printer and spooler status directly;
            # actions still ask. The new fourth mode explicitly skips that
            # extra prompt and lets the unattended worker finish its turn.
            window.plugin_checks['printer'].setChecked(True)
            window.plugin_policies['printer'].setCurrentIndex(2)
            assert window.plugin_policies['printer'].count() == 4
            for read_name in ('list_printers', 'get_print_queue'):
                status_request = {'name': read_name, 'arguments': {},
                                  'event': threading.Event(), 'approved': False}
                with patch.object(QMessageBox, 'exec', side_effect=AssertionError('Status read prompted')):
                    window._on_worker_tool_request(status_request)
                assert status_request['approved'] and status_request['event'].is_set()
            print_request = {'name': 'print_file', 'arguments': {'path': 'report.pdf'},
                             'event': threading.Event(), 'approved': False}
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.No):
                window._on_worker_tool_request(print_request)
            assert not print_request['approved'] and print_request['event'].is_set()
            print_request = {'name': 'print_file', 'arguments': {'path': 'report.pdf'},
                             'event': threading.Event(), 'approved': False}
            with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Yes):
                window._on_worker_tool_request(print_request)
            assert print_request['approved'] and print_request['event'].is_set()
            for key, action, parameters in (
                ('printer', 'print_file', {'path': 'report.pdf'}),
                ('3d_printer', 'submit_3d_print', {'path': 'part.gcode', 'start': True}),
                ('robotics', 'send_robot_command', {'action': 'move_arm', 'parameters': {'x': 1}}),
            ):
                window.plugin_checks[key].setChecked(True)
                combo = window.plugin_policies[key]
                combo.setCurrentIndex(combo.findData('allow_unattended'))
                request = {'name': action, 'arguments': parameters,
                           'event': threading.Event(), 'approved': False}
                with patch.object(QMessageBox, 'exec', side_effect=AssertionError('Unattended action prompted')):
                    window._on_worker_tool_request(request)
                assert request['approved'] and request['event'].is_set()
                assert window.config[f'plugin_{key}_policy'] == 'allow_unattended'
            # Simulate one full Auto Answer tool turn. No real printer is used:
            # the mocked spooler receives one request, then the model answers.
            model_turns = []
            def printer_turn(_client, _model, messages, _prompt, **_kwargs):
                model_turns.append(list(messages))
                if len(model_turns) == 1:
                    return {'message': {'tool_calls': [
                        {'function': {'name': 'print_file', 'arguments': {'path': 'report.pdf'}}}
                    ]}}
                return {'message': {'content': 'Der Druckauftrag wurde übergeben.'}}
            worker = m.ChatWorker('http://localhost', 'test:latest',
                                  [{'role': 'user', 'content': 'Bitte ausdrucken'}], '',
                                  tools=m.tool_schemas(window.config), command_dir=Path(tmp),
                                  output_root=Path(tmp), plugin_config=window.config)
            worker.tool_request.connect(window._on_worker_tool_request)
            failures = []
            worker.failed.connect(failures.append)
            with patch.object(m.OllamaClient, 'chat_response', printer_turn), \
                    patch.object(m, 'print_output_file', return_value='{"submitted": true}') as print_mock, \
                    patch.object(QMessageBox, 'exec', side_effect=AssertionError('Unattended tool loop prompted')):
                worker.run()
            assert not failures, failures
            print_mock.assert_called_once()
            assert len(model_turns) == 2 and model_turns[1][-1]['tool_name'] == 'print_file'
            assert 'submitted' in model_turns[1][-1]['content']
            window.plugin_checks['location'].setChecked(True)
            window.plugin_policies['location'].setCurrentIndex(2)
            denied_location = {'name': 'get_device_location', 'arguments': {}, 'event': threading.Event(), 'approved': False}
            with patch.object(window, '_check_os_permission', return_value=False):
                window._on_worker_tool_request(denied_location)
            assert not denied_location['approved'] and 'operating system' in denied_location['reason']
            window.plugin_checks['vision'].setChecked(True)
            window.plugin_checks['webcam'].setChecked(True)
            window.plugin_policies['vision'].setCurrentIndex(2)
            window.plugin_policies['webcam'].setCurrentIndex(2)
            photo_request = {'name': 'capture_webcam_photo', 'arguments': {}, 'event': threading.Event(), 'approved': False}
            with patch.object(window, '_check_os_permission', return_value=True), \
                    patch.object(window, '_capture_tool_photo', return_value='/tmp/photo.jpg'):
                window._on_worker_tool_request(photo_request)
            assert photo_request['approved'] and photo_request['result'] == '/tmp/photo.jpg'
            window._toggle_sidebar(); app.processEvents()
            assert not window.sidebar.isVisible() and window.config['sidebar_hidden']
            window._toggle_sidebar(); app.processEvents()
            assert window.sidebar.isVisible() and not window.config['sidebar_hidden']
            window.config['plugin_vision_enabled'] = True
            window._attach_chat_image(QImage(32, 32, QImage.Format.Format_RGB32))
            assert len(window.pending_image_paths) == 1
            image_file = Path(window.pending_image_paths[0])
            assert image_file.is_file()
            image_message = ChatMessage.now('user', 'Inspect image')
            image_message.image_paths = [str(image_file)]
            window.current_session.messages.append(image_message)
            assert window.session_messages_for_api()[-1]['images_paths'] == [str(image_file)]
            image_message.image_paths = [str(Path(tmp) / 'private.jpg')]
            (Path(tmp) / 'private.jpg').write_bytes(b'private')
            assert 'images_paths' not in window.session_messages_for_api()[-1]
            image_message.image_paths = [str(image_file)]
            assert window._clone_message_for_rollover(image_message).image_paths == [str(image_file)]
            window.current_session.messages.pop()
            window._clear_chat_images()
            assert not image_file.exists()
            window.config['plugin_vision_enabled'] = False
            window.config['auto_answer_short_answers'] = False
            # Auto Answer must be auditable from the visible transcript. It may
            # not receive the hidden rollover memory or local knowledge store.
            window.current_session.messages = [
                ChatMessage.now('user', 'VISIBLE USER REQUEST'),
                ChatMessage.now('assistant', 'VISIBLE ASSISTANT ANSWER'),
            ]
            window.current_session.continuity_memory = [{
                'source': 'old-session', 'index': 0, 'role': 'assistant',
                'time': '', 'text': 'HIDDEN ROLLOVER SECRET',
            }]
            window.knowledge_base.remember_exchange(
                'knowledge-session', 'Secret memory', 'private clue',
                'HIDDEN KNOWLEDGE SECRET',
            )
            window.config['persistent_knowledge_enabled'] = True
            auto_prompt = window._auto_answer_llm_messages('VISIBLE ASSISTANT ANSWER')[0]['content']
            assert 'VISIBLE USER REQUEST' in auto_prompt
            assert 'VISIBLE ASSISTANT ANSWER' in auto_prompt
            assert 'HIDDEN ROLLOVER SECRET' not in auto_prompt
            assert 'HIDDEN KNOWLEDGE SECRET' not in auto_prompt
            window.config['persistent_knowledge_enabled'] = False
            # Manual and automatic chats both retain >8 messages.
            session = window.current_session
            session.messages = [ChatMessage.now('user' if i%2==0 else 'assistant', f'Entry {i}: SQLite database migration. ' * 30) for i in range(30)]
            session.messages[0].content = 'Goal: keep the migration reversible and retain backup.'
            session.messages.append(ChatMessage.now('user','How do we verify the backup?'))
            assert len(window.session_messages_for_api()) == 31
            window.auto_answer_rounds_current = 7
            window.pending_context_attachments = [{'test':'preserve'}]
            old_id = session.session_id; original = session.to_dict()
            window._ensure_safe_session_capacity(pending_messages=window.session_messages_for_api(),system_prompt='',force=True)
            assert window.current_session.session_id != old_id
            assert window.current_session.continuation_of == old_id
            assert window.current_session.continuity_memory
            assert 'Goal:' in m.memory_prompt(window.current_session.continuity_memory)
            assert window.auto_answer_rounds_current == 7
            assert window.pending_context_attachments == [{'test':'preserve'}]
            stored = window.store.load(old_id)
            assert [x.content for x in stored.messages] == [x['content'] for x in original['messages']]
            first_title = window.current_session.title
            window.current_session.messages.extend([ChatMessage.now('user','Photovoltaik Solarpanel Dachfläche'),ChatMessage.now('assistant','Photovoltaik Solarpanel Dachfläche')])
            window._update_session_title()
            assert window.current_session.title != first_title
            assert window.current_session.title_history
            # Historical titles remain separate, selectable rows after save/reload.
            window.current_session.title_history = [
                {'title':'SQLite Migration', 'message_index':0, 'time':'2026-09-21T10:00:00'},
                {'title':'Photovoltaik Solarpanel', 'message_index':2, 'time':'2026-09-21T11:00:00'}]
            window.store.save(window.current_session)
            active_id = window.current_session.session_id
            window.refresh_sessions_ui()
            rows = [window.session_list.item(i) for i in range(window.session_list.count())]
            bookmarks = [r for r in rows if r.data(int(m.Qt.ItemDataRole.UserRole)+1) is not None and r.data(m.Qt.ItemDataRole.UserRole)==active_id]
            assert len(bookmarks)==2
            assert any(r.data(m.Qt.ItemDataRole.UserRole)==old_id for r in rows)
            window._on_session_clicked(bookmarks[0]); app.processEvents()
            assert window.current_session.session_id==active_id and window.navigation_message_index==0
            assert window.session_list.currentItem().data(int(m.Qt.ItemDataRole.UserRole)+1)==0
            assert window.chat_scroll.verticalScrollBar().value() < 100
            window._on_session_clicked(bookmarks[1]); app.processEvents()
            assert window.navigation_message_index==2
            window._append_user_message('Resume at the end')
            assert window.navigation_message_index is None
            # End-to-end GUI preflight -> HTTP stream -> finish -> unlock.
            window.create_new_session(); window._append_user_message('Photovoltaik Solarpanel')
            Handler.chats = []; Handler.mode='ok'
            window._begin_assistant_request()
            wait_for(app, lambda: not window.preflight_active and window.worker_thread is None and len(Handler.chats)>0)
            assert window.current_session.messages[-1].content.startswith('Photovoltaik')
            assert window.send_btn.isEnabled()
            assert window.last_ollama_stats['prompt_eval_count'] == 120
            assert window.current_session.token_input_total == 120
            assert window.current_session.token_output_total == 15
            assert 'rein 120' in window.token_counter_label.text()
            assert 'raus 15' in window.token_counter_label.text()
            persisted_usage = window.store.load(window.current_session.session_id)
            assert persisted_usage.token_input_total == 120
            assert persisted_usage.token_output_total == 15
            # The separate Auto-Answer model contributes to the same visible,
            # persisted counters when Ollama returns native usage values.
            window.auto_answer_llm_session_id = window.current_session.session_id
            window._on_auto_answer_llm_usage({'prompt_eval_count': 7, 'eval_count': 3})
            assert window.current_session.token_input_total == 127
            assert window.current_session.token_output_total == 18
            window.auto_answer_llm_session_id = ''
            # Optional autonomous rollover is based on current context
            # occupancy, not the cumulative usage counter. Ambiguous model
            # output never grants restart permission.
            window.create_new_session()
            review_session = window.current_session
            review_session.messages = [
                ChatMessage.now('user', 'ORIGINAL REVIEW TASK'),
                ChatMessage.now('assistant', 'First coherent answer'),
                ChatMessage.now('user', 'Continue'),
                ChatMessage.now('assistant', 'Second coherent answer'),
            ]
            window.store.save(review_session)
            window.auto_answer_checkbox.setChecked(True)
            window.config['auto_answer_context_restart_enabled'] = True
            window.config['auto_answer_context_review_percent'] = 78
            window.config['auto_answer_context_hard_percent'] = 92
            with patch.object(window, '_auto_context_occupancy', return_value=(7000, 8192, 85)), \
                 patch.object(window, '_start_auto_context_review', return_value=True) as start_review:
                assert window._maybe_auto_context_restart('Second coherent answer')
                start_review.assert_called_once_with('Second coherent answer', 85)
            window.auto_answer_llm_session_id = review_session.session_id
            window.pending_auto_context_continue_source = 'Second coherent answer'
            window._on_auto_context_review_finished('RESTART because it is long')
            assert not window.pending_auto_context_restart_source
            window._on_auto_context_review_finished('RESTART')
            assert window.pending_auto_context_restart_source == 'Second coherent answer'
            window.pending_auto_context_restart_source = ''
            window.pending_auto_context_continue_source = ''
            with patch.object(window, '_auto_context_occupancy', return_value=(7600, 8192, 93)), \
                 patch.object(window, 'reset_chat_context', return_value=True) as automatic_reset, \
                 patch.object(m.QTimer, 'singleShot') as single_shot:
                assert window._maybe_auto_context_restart('Second coherent answer')
                automatic_reset.assert_called_once_with(automatic=True, reason='auto_context_hard_limit')
                assert single_shot.called
            window.config['auto_answer_context_restart_enabled'] = False
            with patch.object(window, '_auto_context_occupancy', side_effect=AssertionError('disabled feature measured context')):
                assert not window._maybe_auto_context_restart('Second coherent answer')
            window.auto_answer_checkbox.setChecked(False)
            # Full threaded review -> strict RESTART -> fresh selectable
            # continuation, without a confirmation dialog.
            window.create_new_session()
            review_source = window.current_session
            review_source.messages = [
                ChatMessage.now('user', 'Keep the original engineering goal'),
                ChatMessage.now('assistant', 'A' * 1200),
                ChatMessage.now('user', 'Continue coherently'),
                ChatMessage.now('assistant', 'B' * 1200),
            ]
            window.store.save(review_source)
            old_review_id = review_source.session_id
            window.config['auto_answer_context_restart_enabled'] = True
            window.config['auto_answer_context_review_percent'] = 50
            window.config['auto_answer_context_hard_percent'] = 99
            window.auto_answer_checkbox.setChecked(True)
            window.pending_auto_answer_source = 'B' * 1200
            Handler.chats = []; Handler.mode = 'context_review_restart'
            with patch.object(window, '_auto_context_occupancy', side_effect=lambda: (
                    (2200, 3600, 61) if window.current_session.session_id == old_review_id else (100, 3600, 3))):
                window._on_auto_answer_timer()
                wait_for(app, lambda: window.current_session.session_id != old_review_id
                         and window.auto_answer_llm_thread is None)
            assert window.current_session.continuation_of == old_review_id
            assert window.current_session.rollover_diagnostics['reason'] == 'auto_context_model_decision'
            window.auto_answer_timer.stop()
            window.auto_answer_checkbox.setChecked(False)
            window.config['auto_answer_context_restart_enabled'] = False
            # Manual context restart retains the original task, three complete
            # rounds and the latest full project archive, but resets counters.
            window.create_new_session()
            reset_source = window.current_session
            reset_source.messages = [
                ChatMessage.now('user', 'ORIGINAL TASK'), ChatMessage.now('assistant', 'Initial answer'),
                ChatMessage.now('user', 'OLD ROUND'), ChatMessage.now('assistant', 'Old response'),
                ChatMessage.now('user', 'ROUND THREE'), ChatMessage.now('assistant', 'Response three'),
                ChatMessage.now('user', 'ROUND FOUR'), ChatMessage.now('assistant', 'Response four'),
                ChatMessage.now('user', 'ROUND FIVE'), ChatMessage.now('assistant', 'Response five'),
            ]
            reset_source.token_input_total = 9000
            reset_source.token_output_total = 2000
            reset_source.token_request_count = 5
            reset_source.token_totals_initialized = True
            window.store.save(reset_source)
            m.create_archives(
                'Project: reset_project\nFile: main.py\n```python\nprint("checkpoint")\n```',
                m.PROJECTS_DIR, 'reset project', 'test-model', reset_source.session_id,
            )
            old_reset_id = reset_source.session_id
            # A pending Auto-Answer timer cannot mutate the source chat while
            # the confirmation dialog is open, and is restored on cancel.
            window.auto_answer_checkbox.setChecked(True)
            window.auto_answer_timer.start(30000)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
                assert not window.reset_chat_context()
            assert window.auto_answer_timer.isActive()
            window.auto_answer_timer.stop()
            window.auto_answer_checkbox.setChecked(False)
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                assert window.reset_chat_context()
            transferred = [item.content for item in window.current_session.messages]
            assert window.current_session.continuation_of == old_reset_id
            assert window.current_session.token_input_total == 0
            assert window.current_session.token_output_total == 0
            assert transferred[0] == 'ORIGINAL TASK'
            assert 'OLD ROUND' not in transferred
            assert 'ROUND THREE' in transferred and 'ROUND FIVE' in transferred
            assert 'main.py' in window.current_session.project_checkpoint['files']
            restored_workspace = m.PROJECT_WORKSPACES_DIR / window.current_session.session_id
            assert (restored_workspace / 'main.py').read_text(encoding='utf-8') == 'print("checkpoint")\n'
            assert 'rein 0' in window.token_counter_label.text(), window.token_counter_label.text()
            # A filename/counter fragment is not a valid final answer. The app
            # requests one user-facing answer before Auto Answer can continue.
            window.create_new_session(); window._append_user_message('Erstelle eine Webseite')
            Handler.chats = []; Handler.mode='metadata_fragment'
            window._begin_assistant_request()
            wait_for(app, lambda: len(Handler.chats)==2 and not window.preflight_active and window.worker_thread is None)
            fragment_recovery = window.current_session.messages[-1].content
            assert 'index.html 1 2000' in fragment_recovery
            assert 'vollständige sichtbare Antwort' in fragment_recovery
            assert m.assistant_answer_is_usable_for_auto_answer(fragment_recovery)
            # Ollama can stop inside a line of code; the app finishes the line
            # before extracting files or creating a project archive.
            window.create_new_session(); window._append_user_message('Schreib ein Python Programm')
            Handler.chats=[]; Handler.mode='cut_code'
            with patch.object(m, 'save_generated_code_blocks', return_value=[]) as saved, \
                 patch.object(m, 'create_archives', return_value=[]) as archived:
                window._begin_assistant_request()
                wait_for(app, lambda: len(Handler.chats)==2 and not window.preflight_active and window.worker_thread is None)
                finished_code = window.current_session.messages[-1].content
                assert 'print("hello")\n```' in finished_code, finished_code
                assert saved.call_args.args[0] == finished_code
                assert archived.call_args.args[0] == finished_code
                assert not window.current_answer_incomplete
            window.create_new_session(); window._append_user_message('Schreib ein Python Programm')
            Handler.chats=[]; Handler.mode='always_cut_code'
            with patch.object(m, 'save_generated_code_blocks') as saved, \
                 patch.object(m, 'create_archives') as archived:
                window._begin_assistant_request()
                wait_for(app, lambda: len(Handler.chats)>=2 and not window.preflight_active and window.worker_thread is None)
                assert window.current_answer_incomplete
                assert 'unvollständig' in window.current_session.messages[-1].display_content
                saved.assert_not_called()
                archived.assert_not_called()
            # A completed audio event while the previous worker still exists
            # must defer the next automatic turn until its cleanup.
            window.auto_answer_checkbox.setChecked(True)
            window.config['auto_answer_max_rounds'] = 0
            window.pending_auto_answer_source = 'Continue the dialogue'
            window.worker_thread = QThread(window)
            window._on_audio_status(window.t('audio_finished', 'Sprachausgabe beendet.'))
            assert window.pending_auto_answer_after_cleanup == 'Continue the dialogue'
            window.cleanup_worker(); app.processEvents()
            assert window.auto_answer_timer.isActive(), 'Auto Answer was lost during cleanup'
            window.auto_answer_timer.stop()
            window.pending_auto_answer_source = ''
            window.auto_answer_checkbox.setChecked(False)
            # Empty or failed Auto-Answer LLM output falls back to a local
            # phrase, without waiting for a person or dropping the turn.
            window.create_new_session()
            window.auto_answer_checkbox.setChecked(True)
            window.auto_answer_llm_session_id = window.current_session.session_id
            window.auto_answer_llm_fallback_source = 'Photovoltaik'
            with patch.object(window, '_begin_assistant_request') as begin:
                window._on_auto_answer_llm_finished('')
                assert begin.called and window.current_session.messages[-1].generated
            window.auto_answer_llm_fallback_source = 'Photovoltaik'
            with patch.object(window, '_begin_assistant_request') as begin:
                window._on_auto_answer_llm_failed('context length exceeded')
                assert begin.called and window.current_session.messages[-1].generated
            window.context_failure_caps.clear()
            window.auto_answer_checkbox.setChecked(False)
            # Several fully automatic turns must continue through worker
            # teardown; only the configured round limit stops the test run.
            window.create_new_session()
            window.config['auto_answer_max_rounds'] = 3
            window.config['auto_answer_eliza_share'] = 100
            window.config['auto_answer_llm_share'] = 0
            window._append_user_message('Photovoltaik')
            Handler.chats=[]; Handler.mode='ok'
            window.auto_answer_checkbox.setChecked(True)
            window._begin_assistant_request()
            wait_for(app, lambda: window.auto_answer_rounds_current == 3 and
                     not window.preflight_active and window.worker_thread is None, timeout=18)
            assert len(Handler.chats) == 4, len(Handler.chats)
            assert len([item for item in window.current_session.messages if item.generated]) == 3
            wait_for(app, lambda: window.activity_indicator.face.phase == 'paused', timeout=5)
            assert window.activity_indicator.face.phase == 'paused'
            # Re-enabling after a finished answer must resume that same chat.
            window.auto_answer_checkbox.setChecked(False)
            window.config['auto_answer_max_rounds'] = 1
            window.auto_answer_checkbox.setChecked(True)
            wait_for(app, lambda: len(Handler.chats) == 5 and window.auto_answer_rounds_current == 1
                     and not window.preflight_active and window.worker_thread is None, timeout=12)
            assert window.current_session.messages[-2].generated
            assert window.current_session.messages[-1].role == 'assistant'
            # A missing TTS-completion signal must not strand a ready turn.
            window.auto_answer_checkbox.setChecked(False)
            window.auto_answer_checkbox.setChecked(True)
            window.auto_answer_timer.stop()
            window.pending_auto_answer_after_cleanup = ''
            window.pending_auto_answer_source = 'Continue after silent audio'
            window.auto_audio_wait_since = time.monotonic() - 3
            window._update_activity_indicator()
            assert window.auto_answer_timer.isActive()
            window.auto_answer_checkbox.setChecked(False)
            window.config['auto_answer_max_rounds'] = 0
            window.create_new_session()
            window._append_user_message('Erzähle mir etwas über Photovoltaik')
            window.config['auto_answer_max_rounds'] = 1
            Handler.chats=[]; Handler.mode='slow'
            window._begin_assistant_request()
            wait_for(app, lambda: window.worker_thread is not None)
            window.auto_answer_checkbox.setChecked(True)
            wait_for(app, lambda: len(Handler.chats) == 2 and window.worker_thread is None
                     and not window.preflight_active, timeout=12)
            assert window.auto_answer_rounds_current == 1
            assert window.current_session.messages[-2].generated
            window.auto_answer_checkbox.setChecked(False)
            window.config['auto_answer_max_rounds'] = 0
            Handler.mode='ok'
            # Thinking-only output retries once without reasoning, and only a real
            # answer can be narrated or drive another automatic round.
            window.create_new_session(); window._append_user_message('Solve the task')
            Handler.chats=[]; Handler.mode='thinking_then_answer'
            window._begin_assistant_request()
            wait_for(app, lambda: len(Handler.chats)==2 and not window.preflight_active and window.worker_thread is None)
            assert Handler.chats[1].get('think') is False
            assert window.current_session.messages[-1].content == 'Die fertige Antwort mit Code.'
            window.create_new_session(); window._append_user_message('Solve the task')
            Handler.chats=[]; Handler.mode='thinking_only'
            window.config['tts_backend'] = 'system'
            with patch.object(window, 'read_aloud_message', side_effect=AssertionError('UI warning was spoken')):
                window._begin_assistant_request()
                wait_for(app, lambda: len(Handler.chats)==2 and not window.preflight_active and window.worker_thread is None)
            assert window.current_session.messages[-1].content == ''
            assert 'keine abschließende' in window.current_session.messages[-1].display_content
            assert not window.pending_auto_answer_source and not window.pending_auto_answer_after_cleanup
            window.config['tts_backend'] = 'disabled'
            # Ordinary long code must be reachable using the outer chat scrollbar.
            code = '```python\n' + ''.join(f'print({n})  # line {n}\n' for n in range(230)) + '# FINAL_MARKER\n```'
            bubble = window.current_assistant_bubble
            # Streaming stays stable while the fence is open; the final rich
            # Markdown pass happens only after the worker has completed.
            streaming_code = '```python\nprint("STREAM_MARKER")\nprint("still visible")'
            bubble.set_streaming_content(streaming_code)
            app.processEvents()
            assert 'STREAM_MARKER' in bubble.browser.toPlainText()
            bubble.set_content(code); app.processEvents()
            wait_for(app, lambda: bubble.browser.height() > 1600)
            assert 'FINAL_MARKER' in bubble.browser.toPlainText()
            assert bubble.browser.verticalScrollBar().maximum() == 0, (bubble.browser.height(), bubble.browser.document().size().height(), bubble.browser.verticalScrollBar().maximum())
            assert window.chat_scroll.verticalScrollBar().maximum() > 1000
            window.chat_scroll.verticalScrollBar().setValue(window.chat_scroll.verticalScrollBar().maximum())
            assert window.chat_scroll.verticalScrollBar().value() == window.chat_scroll.verticalScrollBar().maximum()
            Handler.mode='ok'
            # One OOM retry with reduced context; no infinite loop on repeated OOM.
            for mode in ('oom','always_oom'):
                window.create_new_session(); window._append_user_message('Small prompt')
                window.context_failure_caps.clear(); window.context_decisions.clear()
                Handler.chats=[]; Handler.mode=mode
                window._begin_assistant_request()
                wait_for(app, lambda: len(Handler.chats)>=2 and not window.preflight_active and window.worker_thread is None)
                assert len(Handler.chats) == 2
                assert Handler.chats[0]['options']['num_ctx'] == 4096
                assert Handler.chats[1]['options']['num_ctx'] == 2048
                assert window.send_btn.isEnabled()
            # Oversize input is retained and never submitted/truncated.
            window.create_new_session(); window._append_user_message('uncompressible ' * 20000)
            Handler.chats=[]; Handler.mode='ok'
            window._begin_assistant_request()
            wait_for(app, lambda: not window.preflight_active and window.worker_thread is None)
            assert not Handler.chats
            assert len(window.current_session.messages[-1].content)>200000
            # Auto-LLM uses its own model budget and terminates after cancellation.
            worker = m.AutoAnswerLLMWorker(cfg['ollama_base_url'], 'test:latest', [{'role':'user','content':'x'}], '', 64, 2048)
            terminal = []
            worker.finished.connect(terminal.append)
            worker.cancel(); worker.run()
            assert terminal == ['']
            Handler.chats=[]
            # Critical memory pressure pauses instead of sending a doomed request.
            window.create_new_session(); window._append_user_message('Keep this input')
            with patch.object(m, 'collect_runtime', lambda *_: {'local':True, 'ram_total':32*1024**3, 'ram_available':1}):
                window._begin_assistant_request()
                wait_for(app, lambda: not window.preflight_active)
                assert not Handler.chats and window.send_btn.isEnabled()
            # Stop a probe; late results must not start a model request.
            window.create_new_session(); window._append_user_message('Cancel this request')
            window._begin_assistant_request(); window.stop_generation()
            wait_for(app, lambda: window.send_btn.isEnabled())
            for _ in range(20): app.processEvents(); time.sleep(.01)
            assert not Handler.chats
            window.close(); app.processEvents()
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
    print('GUI continuity smoke passed: handover, title changes, full history, OOM backoff, oversized input, cancellation')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

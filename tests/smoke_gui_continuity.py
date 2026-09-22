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
from PyQt6.QtWidgets import QApplication
from app import main as m
from app.config import DEFAULT_CONFIG
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
            CHATS_DIR=Path(tmp), load_config=lambda: dict(cfg), save_config=lambda _: None,
            ensure_directories=lambda: None, collect_runtime=controlled_runtime,
            detect_hardware=lambda: HardwareProfile(4,32,'',0,4096,1)), \
            patch.object(m.MainWindow, 'refresh_models', lambda self: self.model_combo.addItem('test:latest')):
            window = m.MainWindow(); window.show(); app.processEvents()
            window.config['auto_answer_short_answers'] = False
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

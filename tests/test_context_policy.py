from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.adaptive_context import choose_context, GIB, is_memory_error, is_local_endpoint
from app.context_budget import request_token_budget, estimate_token_count, estimate_chat_payload_tokens
from app.continuity import build_memory, memory_prompt, select_carry
from app.models import ChatMessage, ChatSession
from app.config import normalize_config
from app.chat_titles import infer_topic_title


def snapshot():
    return {"local": True, "ram_total": 32*GIB, "ram_available": 18*GIB,
        "gpus": [(16*GIB, 6*GIB)], "running": {"context_length": 4096, "size_vram": 8*GIB},
        "info": {"model_info": {"general.architecture": "qwen3", "qwen3.context_length": 32768,
            "qwen3.block_count": 32, "qwen3.attention.head_count": 32,
            "qwen3.attention.head_count_kv": 8, "qwen3.embedding_length": 4096}}}


class ContextPolicyTests(unittest.TestCase):
    def test_growth_only_on_demand(self):
        s = snapshot()
        self.assertEqual(choose_context(s, 1000)['num_ctx'], 4096)
        self.assertEqual(choose_context(s, 7000)['num_ctx'], 8192)

    def test_pressure_reduces_context(self):
        s = snapshot(); s['gpus'] = [(16*GIB, .3*GIB)]
        result = choose_context(s, 14000, previous=8192)
        self.assertLessEqual(result['num_ctx'], 4096)
        self.assertTrue(result['pressure'])
        s = snapshot(); s['ram_available'] = GIB
        self.assertLessEqual(choose_context(s, 14000, previous=8192)['num_ctx'], 4096)

    def test_critical_pressure_blocks_submission(self):
        s = snapshot(); s['ram_available'] = .1 * GIB
        self.assertTrue(choose_context(s, 1000)['blocked'])

    def test_remote_never_uses_client_memory(self):
        s = snapshot(); s['local'] = False; s['ram_available'] = 0
        self.assertEqual(choose_context(s, 16000)['num_ctx'], 4096)
        self.assertFalse(choose_context(s, 16000)['pressure'])
        self.assertTrue(is_local_endpoint('http://[::1]:11434'))
        self.assertFalse(is_local_endpoint('http://192.168.1.2:11434'))

    def test_missing_telemetry_and_multi_gpu_are_conservative(self):
        self.assertEqual(choose_context({}, 10000)['num_ctx'], 4096)
        s = snapshot(); s['gpus'] *= 2
        self.assertEqual(choose_context(s, 16000)['num_ctx'], 4096)
        s = snapshot(); s['info'] = {}
        self.assertEqual(choose_context(s, 16000)['num_ctx'], 4096)

    def test_caps_and_manual(self):
        s = snapshot()
        self.assertEqual(choose_context(s, 1000, 16384, automatic=False)['num_ctx'], 16384)
        self.assertEqual(choose_context(s, 16000, failure_cap=2048)['num_ctx'], 2048)
        self.assertLessEqual(choose_context(s, 100000, 262144, automatic=False)['num_ctx'], 32768)

    def test_small_window_always_has_margin(self):
        self.assertLess(request_token_budget(2048), 2048)
        self.assertGreater(estimate_token_count('日本語' * 100), 200)

    def test_migration_preserves_custom_limits(self):
        cfg = normalize_config({'context_message_limit': 8, 'rollover_carry_messages': 5})
        self.assertEqual((cfg['context_message_limit'], cfg['rollover_carry_messages']), (0, 0))
        cfg = normalize_config({'context_message_limit': 26, 'rollover_carry_messages': 12})
        self.assertEqual((cfg['context_message_limit'], cfg['rollover_carry_messages']), (26, 12))
        cfg = normalize_config({'context_policy_version': 24, 'context_message_limit': 8})
        self.assertEqual(cfg['context_message_limit'], 8)

    def test_memory_preserves_goal_provenance_and_uncertainty(self):
        msgs = [ChatMessage.now('user', 'Goal: retain the uncertain hypothesis; never call it verified.')] + [
            ChatMessage.now('assistant', f'Open question {i}: sample {i} has not been tested. ' * 12) for i in range(30)]
        memory = build_memory([], msgs, 'source01', 1300)
        self.assertIn('Goal:', memory_prompt(memory))
        self.assertIn('not verified', memory_prompt(memory))
        self.assertLessEqual(estimate_token_count(memory_prompt(memory)), 1300)
        self.assertEqual(memory[0]['source'], 'source01')
        again = build_memory(memory, msgs[-2:], 'source02', 1300)
        self.assertEqual(len({(r['role'], r['text']) for r in again}), len(again))

    def test_memory_survives_many_sections(self):
        memory = build_memory([], [ChatMessage.now('user', 'Original goal: test, do not assume consensus.')], 'root', 900)
        for section in range(10):
            msgs = [ChatMessage.now('assistant', f'Section {section}, unresolved result {i}: ' + 'evidence pending '*40) for i in range(12)]
            memory = build_memory(memory, msgs, f'section{section}', 900)
            self.assertIn('Original goal', memory_prompt(memory))
            self.assertLessEqual(estimate_token_count(memory_prompt(memory)), 900)
        self.assertIn('Section 9', memory_prompt(memory))

    def test_carry_keeps_full_pending_input_and_originals(self):
        msgs = [ChatMessage.now('user' if i % 2 == 0 else 'assistant', f'{i} '+ 'word '*100) for i in range(20)]
        msgs.append(ChatMessage.now('user', 'latest question ' * 100))
        before = [m.content for m in msgs]
        carry = select_carry(msgs, 'system', 1500)
        self.assertEqual(carry[0].role, 'user')
        self.assertEqual(carry[-1].content, msgs[-1].content)
        self.assertEqual(before, [m.content for m in msgs])
        self.assertLessEqual(estimate_chat_payload_tokens([{'content':m.content} for m in carry], 'system'), 1500)

    def test_title_changes_on_topic_shift(self):
        old = [ChatMessage.now('user', 'Datenbank Migration SQLite Indizes')]*6
        new = [ChatMessage.now('user', 'Jetzt Photovoltaik Solarpanel Dachfläche'), ChatMessage.now('assistant', 'Photovoltaik Solarpanel Dachfläche')]
        self.assertNotEqual(infer_topic_title(old), infer_topic_title(old + new))
        self.assertIn('Photovoltaik', infer_topic_title(old + new))

    def test_metadata_roundtrip(self):
        s = ChatSession('id','title','now','now', continuity_memory=[{'text':'goal'}], carried_messages=5, root_topic='root', title_history=[{'title':'focus'}], rollover_diagnostics={'num_ctx':8192})
        self.assertEqual(ChatSession.from_dict(s.to_dict()).to_dict(), s.to_dict())

    def test_memory_errors(self):
        self.assertTrue(is_memory_error('Ollama HTTP 500: model requires more system memory'))
        self.assertFalse(is_memory_error('model not found'))

if __name__ == '__main__':
    unittest.main()

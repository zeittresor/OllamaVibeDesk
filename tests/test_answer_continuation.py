from __future__ import annotations

import unittest

from app.answer_continuation import stream_complete_answer, unclosed_code_fence


class FakeClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def stream_chat(self, model, messages, system_prompt, options, think):
        self.calls.append((messages, options, think))
        content, reason = self.replies.pop(0)
        yield {"content": content}
        yield {"stats": {"done_reason": reason, "eval_count": len(content)}}


class AnswerContinuationTests(unittest.TestCase):
    def request(self, client, **overrides):
        emitted = []
        arguments = dict(model="test:latest", messages=[{"role": "user", "content": "Schreib ein Programm"}],
                         system_prompt="", max_tokens=512, num_ctx=4096, think="off",
                         emit=emitted.append, cancelled=lambda: False)
        arguments.update(overrides)
        result = stream_complete_answer(client, **arguments)
        return result, emitted

    def test_code_cut_inside_line_is_completed_without_duplicate(self):
        client = FakeClient([("File: app.py\n```python\nprint('fer", "length"),
                             ("fertig')\n```\n", "stop")])
        (answer, incomplete), emitted = self.request(client)
        self.assertFalse(incomplete)
        self.assertEqual(answer, "File: app.py\n```python\nprint('fertig')\n```\n")
        self.assertEqual(''.join(e.get('content', '') for e in emitted), answer)
        self.assertEqual(client.calls[1][2], False)
        self.assertFalse(unclosed_code_fence(answer))

    def test_fence_still_open_without_length_gets_one_more_segment(self):
        client = FakeClient([("```gdscript\nfunc ready():\n", "stop"),
                             ("    pass\n```", "stop")])
        (answer, incomplete), _ = self.request(client)
        self.assertFalse(incomplete)
        self.assertIn("    pass\n```", answer)

    def test_exhaustion_is_explicit_and_never_claims_completion(self):
        client = FakeClient([("```python\nprint(1", "length"), ("+2", "length")])
        (answer, incomplete), emitted = self.request(client, max_continuations=1)
        self.assertTrue(incomplete)
        self.assertTrue(emitted[-1].get('incomplete'))
        self.assertEqual(answer, "```python\nprint(1+2")

    def test_tool_api_nonstream_response_is_continued_without_reinvoking_tools(self):
        client = FakeClient([("done')\n```", "stop")])
        initial = {"message": {"content": "File: main.py\n```python\nprint('"},
                   "done_reason": "length", "eval_count": 300}
        (answer, incomplete), emitted = self.request(client, initial_response=initial)
        self.assertFalse(incomplete)
        self.assertIn("print('done')", answer)
        self.assertEqual(len(client.calls), 1)
        self.assertFalse(any('tools' in item[1] for item in client.calls))
        self.assertEqual(''.join(p.get('content', '') for p in emitted), answer)

    def test_reasoning_without_visible_answer_uses_existing_retry_path(self):
        client = FakeClient([("<think>still reasoning", "length")])
        (answer, incomplete), _ = self.request(client)
        self.assertEqual(answer, "<think>still reasoning")
        self.assertFalse(incomplete)
        self.assertEqual(len(client.calls), 1)

"""Regression tests for dominant user-language selection."""
from __future__ import annotations

import unittest

from app.conversation_language import detect_primary_language
from app.models import ChatMessage


class ConversationLanguageTests(unittest.TestCase):
    def test_german_dominates_code_and_generated_english(self):
        messages = [
            ChatMessage.now("user", "Bitte erkläre mir die Einstellungen und korrigiere diesen Fehler."),
            ChatMessage.now("assistant", "The assistant answer is irrelevant."),
            ChatMessage.now("user", "```python\nprint('the model')\n```"),
            ChatMessage.now("user", "Please continue", generated=True),
        ]
        self.assertEqual(detect_primary_language(messages, "en"), "de")

    def test_newest_message_breaks_a_close_tie(self):
        messages = [
            {"role": "user", "content": "Please explain the answer."},
            {"role": "user", "content": "Bitte erkläre die Antwort."},
        ]
        self.assertEqual(detect_primary_language(messages, "en"), "de")

    def test_script_languages_are_detected_without_external_packages(self):
        self.assertEqual(detect_primary_language([{"role": "user", "content": "これは日本語の質問です"}], "de"), "ja")
        self.assertEqual(detect_primary_language([{"role": "user", "content": "Это вопрос на русском языке"}], "de"), "ru")

    def test_short_or_technical_input_uses_interface_fallback(self):
        self.assertEqual(detect_primary_language([{"role": "user", "content": "Qwen3 API"}], "de"), "de")


if __name__ == "__main__":
    unittest.main()

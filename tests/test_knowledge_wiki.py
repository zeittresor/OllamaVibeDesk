"""Regression checks for the portable knowledge base and TiddlyWiki cache."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.knowledge import (
    LocalKnowledgeBase,
    WIKI_PLACEHOLDER_MARKER,
    WIKI_STORE_END,
    WIKI_STORE_START,
)
from tools.prepare_tiddlywiki import prepare_template, valid_template_bytes

ROOT = Path(__file__).resolve().parents[1]


def fake_tiddlywiki() -> bytes:
    shell = (
        '<!doctype html><html><body>'
        '<script class="tiddlywiki-tiddler-store" type="application/json">[]</script>'
        '<script>const boot="$:/boot/boot.js";</script>'
        '</body></html>'
    ).encode('utf-8')
    return shell + (b' ' * (100_100 - len(shell)))


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.data), chunk_size):
            yield self.data[offset:offset + chunk_size]


class KnowledgeWikiTests(unittest.TestCase):
    def test_placeholder_is_automatically_replaced_and_entries_are_embedded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'knowledge_base'
            store = LocalKnowledgeBase(root)
            wiki = store.create_wiki_workspace()
            brain = wiki / 'brain.html'
            self.assertIn(WIKI_PLACEHOLDER_MARKER, brain.read_text(encoding='utf-8'))

            cache = root.parent / 'cache' / 'tiddlywiki_empty.html'
            cache.parent.mkdir(parents=True)
            cache.write_bytes(fake_tiddlywiki())
            store.create_wiki_workspace()
            self.assertNotIn(WIKI_PLACEHOLDER_MARKER, brain.read_text(encoding='utf-8'))

            store.remember_exchange(
                'session-1', 'Portable knowledge', 'Remember <one>',
                'Safe response </script><script>alert(1)</script>', wiki_path=wiki,
            )
            store.remember_exchange(
                'session-2', 'Portable knowledge', 'Remember two',
                'Second response', wiki_path=wiki,
            )
            source = brain.read_text(encoding='utf-8')
            self.assertEqual(source.count(WIKI_STORE_START), 1)
            self.assertEqual(source.count(WIKI_STORE_END), 1)
            self.assertNotIn('</script><script>alert(1)', source)
            match = re.search(
                re.escape(WIKI_STORE_START) + r'.*?<script[^>]*>(.*?)</script>.*?' + re.escape(WIKI_STORE_END),
                source,
                flags=re.DOTALL,
            )
            self.assertIsNotNone(match)
            tiddlers = json.loads(match.group(1))
            self.assertEqual(len(tiddlers), 2)
            self.assertEqual(len({item['title'] for item in tiddlers}), 2)
            self.assertIn('Remember two', tiddlers[1]['text'])
            self.assertEqual(len(list((wiki / 'tiddlers').glob('*.tid'))), 2)

    def test_template_download_is_validated_and_atomic(self):
        data = fake_tiddlywiki()
        self.assertTrue(valid_template_bytes(data))
        self.assertFalse(valid_template_bytes(b'<html>not a wiki</html>'))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'cache' / 'tiddlywiki_empty.html'
            with patch('tools.prepare_tiddlywiki.requests.get', return_value=_FakeResponse(data)):
                success, _message = prepare_template(target)
            self.assertTrue(success)
            self.assertEqual(target.read_bytes(), data)
            self.assertFalse(target.with_name(target.name + '.part').exists())

    def test_windows_installer_uses_the_validated_template_preparer(self):
        script = (ROOT / 'install_windows.bat').read_text(encoding='utf-8')
        self.assertIn('tools\\prepare_tiddlywiki.py', script)
        self.assertNotIn("Invoke-WebRequest -Uri 'https://tiddlywiki.com/empty.html'", script)

    def test_long_import_names_are_bounded_and_text_reads_are_limited(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / (('very-long-name-' * 12) + '.txt')
            source.write_text('x' * 100_000, encoding='utf-8')
            store = LocalKnowledgeBase(root / 'knowledge_base')
            result = store.import_file(source, persist_to_memory=True)
            stored = Path(result['entry']['stored_path'])
            self.assertLessEqual(len(stored.name), 112)
            self.assertEqual(len(result['entry']['content']), 50_000)

    def test_retrieval_context_respects_code_output_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            store = LocalKnowledgeBase(Path(folder) / 'knowledge_base')
            for index in range(5):
                store.remember_exchange(
                    session_id=f'session-{index}',
                    session_title=f'Programming memory {index}',
                    user_text='python programming',
                    assistant_text=('python programming implementation details ' * 100),
                )
            context, hits = store.build_retrieval_context('python programming', limit=5, max_chars=900)
            self.assertLessEqual(len(context), 900)
            self.assertGreaterEqual(len(hits), 1)
            self.assertLess(len(hits), 5)


if __name__ == '__main__':
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auto_answer_data import ensure_auto_answer_data, load_bundle, read_list
from app.auto_answer_engine import expand_phrase_templates, generate_from_clean_text, is_question_text
from app.config import DEFAULT_CONFIG
from app.hardware import detect_hardware
from app.knowledge import LocalKnowledgeBase, uuid_hash
from app.models import ChatMessage
from app.themes import THEMES


def main() -> int:
    ensure_auto_answer_data()
    assert DEFAULT_CONFIG["auto_answer_eliza_share"] + DEFAULT_CONFIG["auto_answer_llm_share"] <= 100
    assert "Amiga ECS" in THEMES
    assert len(THEMES) >= 10
    german, german_questions = load_bundle("de")
    assert german["phrases"]["de"]
    assert german["topic_words"]["de"]
    assert german["eliza"]["de"]
    assert german_questions["replies"]["de"]
    # Auto-Answer runtime data must never mix languages through fallback.
    for kind in ("phrases", "topic_words", "question_replies", "eliza"):
        assert read_list(kind, "xx", fallback_to_english=False) == []
    # One candidate per template keeps each phrase equally weighted, while two
    # placeholders should use two different topics whenever enough are available.
    expanded = expand_phrase_templates(["Talk about @@@ and @@@", "Plain"], ["space", "music", "history"])
    assert len(expanded) == 2
    rendered = next(text for text, source in expanded if source.startswith("Talk"))
    assert rendered.count("@@@") == 0
    assert len({word for word in ["space", "music", "history"] if word in rendered}) == 2
    assert is_question_text("Really?")
    assert is_question_text("本当ですか？")
    assert is_question_text("حقًا؟")
    assert not is_question_text("A statement.")
    auto = generate_from_clean_text(
        "A statement.", "de", german, german_questions,
        eliza_share_percent=0, source_mode="phrases",
    )
    assert auto["text"]
    assert auto["source_kind"] in {"phrase", "question_reply", "eliza"}
    restored = ChatMessage.from_dict({"role": "assistant", "content": "ok", "future_field": 42})
    assert restored.role == "assistant" and restored.content == "ok"
    profile = detect_hardware()
    assert profile.recommended_num_ctx >= 2048
    with tempfile.TemporaryDirectory() as temp_dir:
        source = Path(temp_dir) / "note.txt"
        source.write_text("persistent knowledge", encoding="utf-8")
        first_id = uuid_hash(source, "persistent knowledge")
        second_id = uuid_hash(source, "persistent knowledge")
        assert first_id == second_id
        store = LocalKnowledgeBase(Path(temp_dir) / "brain")
        imported = store.import_file(source, persist_to_memory=True)
        store.import_file(source, persist_to_memory=True)
        assert imported["entry"]["id"] == first_id
        assert len(store.load_entries()) == 1
    for path in ROOT.joinpath("lang").glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    print("core smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

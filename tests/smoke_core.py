from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auto_answer_data import ensure_auto_answer_data, load_bundle, read_list
from app.auto_answer_engine import expand_phrase_templates, generate_from_clean_text, is_question_text
from app.config import DEFAULT_CONFIG, normalize_config
from app.hardware import detect_hardware
from app.knowledge import LocalKnowledgeBase, uuid_hash
from app.models import ChatMessage
from app.personalities import load_personalities, resolve_configured_personality_prompt
from app.themes import THEMES
from app.tts_profiles import VOICE_STYLE_IDS, effective_voice_controls, normalize_voice_style
from app.version import VERSION
from app.speech_models import (
    PYTHON_REALTIME_TTS_MODEL,
    VIBEVOICE_ASR_MODELS,
    VIBEVOICE_TTS_MODELS,
    get_vibevoice_asr_model,
    get_vibevoice_tts_model,
)


def main() -> int:
    ensure_auto_answer_data()
    assert DEFAULT_CONFIG["auto_answer_eliza_share"] + DEFAULT_CONFIG["auto_answer_llm_share"] <= 100
    assert VERSION == ROOT.joinpath("version.txt").read_text(encoding="utf-8").strip()
    assert len(VOICE_STYLE_IDS) >= 8
    assert normalize_voice_style("unknown") == "natural"
    rate, pitch, volume, effect, intensity = effective_voice_controls("robotic", 100, 0, 0, 100)
    assert (rate, pitch, volume, effect, intensity) == (-1, -1, 100, "robotic", 100)
    repaired = normalize_config({
        "tts_backend": "broken",
        "windows_sapi_rate": 999,
        "auto_answer_eliza_share": 90,
        "auto_answer_llm_share": 90,
        "autoplay_tts": "false",
    })
    assert repaired["tts_backend"] == "disabled"
    assert repaired["windows_sapi_rate"] == 10
    assert repaired["auto_answer_eliza_share"] + repaired["auto_answer_llm_share"] == 100
    assert repaired["autoplay_tts"] is False
    assert DEFAULT_CONFIG["vibevoice_model_path"] == PYTHON_REALTIME_TTS_MODEL
    assert len(VIBEVOICE_TTS_MODELS) == 2
    assert len(VIBEVOICE_ASR_MODELS) == 2
    assert get_vibevoice_asr_model("vibevoice_asr_7b").backend == "vibevoice"
    assert get_vibevoice_tts_model("vibevoice_realtime_0_5b").backend == "vibevoice-tts"
    try:
        get_vibevoice_tts_model("vibevoice_asr_bitnet")
    except ValueError:
        pass
    else:
        raise AssertionError("ASR model was accepted as TTS")
    constrained = normalize_config({
        "tts_backend": "crispasr_openai",
        "vibevoice_crisp_tts_model": "vibevoice_1_5b",
        "tts_voice": "sapi::wrong",
        "asr_model": "vibevoice_asr_bitnet",
        "asr_language": "de",
        "vibevoice_model_path": "P2Enjoy/VibeVoice-ASR-BitNet-slim",
    })
    assert constrained["tts_voice"] == "default"
    assert constrained["asr_language"] == "auto"
    assert constrained["vibevoice_model_path"] == PYTHON_REALTIME_TTS_MODEL
    assert "Amiga ECS" in THEMES
    assert len(THEMES) >= 10
    user_personalities = load_personalities("user")
    assistant_personalities = load_personalities("assistant")
    assert len(user_personalities) == 20
    assert len(assistant_personalities) == 20
    assert {item.gender for item in user_personalities} >= {"female", "male", "neutral"}
    assert {item.gender for item in assistant_personalities} >= {"female", "male", "neutral"}
    configured = dict(DEFAULT_CONFIG)
    configured["user_personality_id"] = user_personalities[0].personality_id
    configured["assistant_personality_id"] = assistant_personalities[0].personality_id
    assert resolve_configured_personality_prompt(configured, "user", "de")
    assert resolve_configured_personality_prompt(configured, "assistant", "de")
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

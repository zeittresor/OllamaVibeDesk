from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.auto_answer_data import ensure_auto_answer_data, load_bundle, read_list
from app.auto_answer_engine import (
    expand_phrase_templates,
    generate_from_clean_text,
    is_question_text,
)
from app.chat_titles import (
    build_continuation_title,
    infer_continuation_index,
    strip_continuation_suffix,
)
from app.config import DEFAULT_CONFIG, PREFERRED_OLLAMA_MODEL, normalize_config
from app.guidance_presets import guidance_llm_instruction, guidance_phrases, load_presets
from app.context_budget import rollover_output_reserve, would_exceed_rollover_budget
from app.hardware import detect_hardware
from app.knowledge import LocalKnowledgeBase, uuid_hash
from app.models import ChatMessage, ChatSession
from app.personalities import load_personalities, resolve_configured_personality_prompt, normalized_parameters, render_personality_prompt
from app.reasoning import (
    configured_reasoning_effort,
    normalize_reasoning_effort,
    resolve_reasoning_effort,
)
from app.speech_models import (
    PYTHON_REALTIME_TTS_MODEL,
    VIBEVOICE_ASR_MODELS,
    VIBEVOICE_TTS_MODELS,
    get_vibevoice_asr_model,
    get_vibevoice_tts_model,
)
from app.themes import THEMES
from app.tts_profiles import (
    VOICE_STYLE_IDS,
    effective_voice_controls,
    normalize_voice_style,
)
from app.version import VERSION


def main() -> int:
    ensure_auto_answer_data()
    assert DEFAULT_CONFIG["auto_answer_eliza_share"] + DEFAULT_CONFIG["auto_answer_llm_share"] <= 100
    assert DEFAULT_CONFIG['last_model'] == PREFERRED_OLLAMA_MODEL
    assert DEFAULT_CONFIG['chat_max_tokens'] == 65536
    assert DEFAULT_CONFIG['auto_answer_max_rounds'] == 0
    assert (DEFAULT_CONFIG['auto_answer_eliza_share'], DEFAULT_CONFIG['auto_answer_llm_share']) == (15, 50)
    assert DEFAULT_CONFIG['auto_answer_guidance_preset'] == 'standard'
    assert DEFAULT_CONFIG['auto_answer_guidance_strength'] == 65
    assert normalize_config({'last_model': 'my:own', 'chat_max_tokens': 1024,
                             'auto_answer_eliza_share': 20, 'auto_answer_llm_share': 30})['last_model'] == 'my:own'
    assert ROOT.joinpath("version.txt").read_text(encoding="utf-8").strip() == VERSION
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
    migrated_reasoning = normalize_config({"auto_thinking_for_code_requests": False})
    assert migrated_reasoning["reasoning_default_effort"] == "off"
    reasoning_config = normalize_config({
        "reasoning_default_effort": "auto",
        "model_reasoning_efforts": {
            "qwen3:8b": "high",
            "bad\nmodel": "medium",
            "llama3.2": "invalid",
        },
    })
    assert configured_reasoning_effort(reasoning_config, "qwen3:8b") == "high"
    assert resolve_reasoning_effort(reasoning_config, "new-model", is_code_request=True) == "medium"
    assert resolve_reasoning_effort(reasoning_config, "new-model", is_code_request=False) == "off"
    assert "bad\nmodel" not in reasoning_config["model_reasoning_efforts"]
    assert normalize_reasoning_effort(True) == "medium"
    assert rollover_output_reserve(8192, 8192) == int(8192 * 0.20)
    assert not would_exceed_rollover_budget(100, 8192, 8192)
    assert would_exceed_rollover_budget(7000, 8192, 8192)
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
    assert len(user_personalities) == 35
    assert len(assistant_personalities) == 35
    assert {item.gender for item in user_personalities} >= {"female", "male", "neutral"}
    assert {item.gender for item in assistant_personalities} >= {"female", "male", "neutral"}
    configured = dict(DEFAULT_CONFIG)
    configured["user_personality_id"] = user_personalities[0].personality_id
    configured["assistant_personality_id"] = assistant_personalities[0].personality_id
    assert resolve_configured_personality_prompt(configured, "user", "de")
    assert resolve_configured_personality_prompt(configured, "assistant", "de")
    assert normalized_parameters({"sensuality": -4})["sensuality"] == 0
    assert normalized_parameters({"sensuality": 130})["sensuality"] == 100
    for role, example in (("user", user_personalities[0]), ("assistant", assistant_personalities[0])):
        example.parameters["sensuality"] = 0
        no_optional = render_personality_prompt(example, "de").lower()
        assert "sinnlich" not in no_optional and "flirt" not in no_optional and "sensuality" not in no_optional, role
        example.parameters["sensuality"] = 40
        assert "40/100" in render_personality_prompt(example, "de"), role
    german, german_questions = load_bundle("de")
    assert german["phrases"]["de"]
    assert german["topic_words"]["de"]
    assert german["eliza"]["de"]
    assert german_questions["replies"]["de"]
    assert len(load_presets("de")) == 25
    assert len(guidance_phrases("de", "programming_tasks")) >= 8
    assert guidance_llm_instruction("de", "programming_tasks", 65)
    assert not guidance_phrases("de", "standard")
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
    continuation_messages = [
        {"role": "user", "content": "Wir sprechen zuerst über die Installation."},
        {"role": "assistant", "content": "Die Installation ist abgeschlossen."},
        {"role": "user", "content": "Fortsetzungschats brauchen thematische Namen und Reasoning in Low, Medium oder High."},
        {"role": "assistant", "content": "Reasoning und die Namen der Fortsetzungschats werden modellbezogen verbessert."},
    ]
    continuation_title, topic = build_continuation_title(
        continuation_messages,
        "Installation",
        2,
        " (Fortsetzung {number})",
    )
    assert "Reasoning" in topic and "Fortsetzungschats" in topic
    assert continuation_title.endswith("(Fortsetzung 2)")
    assert strip_continuation_suffix(continuation_title) == topic
    assert infer_continuation_index("Thema (Fortsetzung)") == 1
    restored_session = ChatSession.from_dict({
        "session_id": "safe-session",
        "title": continuation_title,
        "continuation_index": 2,
        "continuation_of": "parent-session",
        "topic_title": topic,
        "messages": [],
    })
    assert restored_session.continuation_index == 2
    assert restored_session.continuation_of == "parent-session"
    assert restored_session.to_dict()["topic_title"] == topic
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

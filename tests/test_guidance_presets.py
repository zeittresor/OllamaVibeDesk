from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auto_answer_data import load_bundle
from app.auto_answer_engine import generate_from_clean_text
from app.config import DEFAULT_CONFIG, normalize_config
from app import guidance_presets


class GuidancePresetTests(unittest.TestCase):
    def test_all_languages_have_the_same_twenty_five_presets(self):
        expected_ids = None
        catalogs = sorted((ROOT / "resources" / "auto_answer" / "guidance").glob("*.json"))
        self.assertEqual(len(catalogs), 12)
        for path in catalogs:
            presets = guidance_presets.load_presets(path.stem)
            preset_ids = [preset.preset_id for preset in presets]
            self.assertEqual(len(preset_ids), 25, path.stem)
            expected_ids = expected_ids or preset_ids
            self.assertEqual(preset_ids, expected_ids, path.stem)
            for preset in presets:
                phrases = guidance_presets.guidance_phrases(path.stem, preset.preset_id)
                self.assertGreaterEqual(len(phrases), 8)
                self.assertTrue(all("{goal}" not in phrase for phrase in phrases))
                instruction = guidance_presets.guidance_llm_instruction(path.stem, preset.preset_id, 65)
                self.assertTrue(instruction)
                self.assertNotIn("{goal}", instruction)
                self.assertNotIn("{strength}", instruction)

    def test_standard_mode_preserves_previous_behavior(self):
        self.assertEqual(guidance_presets.guidance_phrases("de", "standard"), [])
        self.assertEqual(guidance_presets.guidance_llm_instruction("de", "standard", 100), "")
        self.assertEqual(DEFAULT_CONFIG["auto_answer_guidance_preset"], "standard")
        self.assertEqual(DEFAULT_CONFIG["auto_answer_guidance_strength"], 65)
        normalized = normalize_config({
            "auto_answer_eliza_share": 15,
            "auto_answer_llm_share": 50,
            "auto_answer_guidance_preset": "invalid preset!",
            "auto_answer_guidance_strength": 999,
        })
        self.assertEqual(normalized["auto_answer_guidance_preset"], "standard")
        self.assertEqual(normalized["auto_answer_guidance_strength"], 100)
        self.assertEqual(
            normalized["auto_answer_eliza_share"] + normalized["auto_answer_llm_share"],
            65,
        )

    def test_phrase_guidance_is_optional_and_questions_keep_priority(self):
        phrase_data, question_data = load_bundle("de")
        guidance = guidance_presets.guidance_phrases("de", "programming_tasks")
        guided = generate_from_clean_text(
            "Lass uns fortfahren.",
            "de",
            phrase_data,
            question_data,
            source_mode="phrases",
            guidance_phrases=guidance,
            guidance_preset_id="programming_tasks",
            guidance_strength=100,
            rng=random.Random(4),
        )
        self.assertEqual(guided["source_kind"], "guidance")
        unguided = generate_from_clean_text(
            "Lass uns fortfahren.",
            "de",
            phrase_data,
            question_data,
            source_mode="phrases",
            guidance_phrases=guidance,
            guidance_preset_id="programming_tasks",
            guidance_strength=0,
            rng=random.Random(4),
        )
        self.assertNotEqual(unguided["source_kind"], "guidance")
        question = generate_from_clean_text(
            "Funktioniert der Installer jetzt?",
            "de",
            phrase_data,
            question_data,
            source_mode="phrases",
            guidance_phrases=guidance,
            guidance_preset_id="programming_tasks",
            guidance_strength=100,
            rng=random.Random(4),
        )
        self.assertEqual(question["source_kind"], "question_reply")

    def test_per_language_phrase_override_can_be_reset(self):
        with tempfile.TemporaryDirectory(prefix="ovd_guidance_") as temp_dir, patch.object(
            guidance_presets, "OVERRIDE_DIR", Path(temp_dir)
        ):
            custom = ["Bitte fokussiere jetzt den konkreten Testlauf.", "Nenne den nächsten prüfbaren Schritt."]
            target = guidance_presets.write_guidance_phrases("de", "programming_tasks", custom)
            self.assertTrue(target.is_file())
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), custom)
            self.assertEqual(guidance_presets.guidance_phrases("de", "programming_tasks"), custom)
            guidance_presets.reset_guidance_phrases("de", "programming_tasks")
            self.assertFalse(target.exists())
            self.assertNotEqual(guidance_presets.guidance_phrases("de", "programming_tasks"), custom)


if __name__ == "__main__":
    unittest.main()

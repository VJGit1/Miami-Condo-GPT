"""Unit tests for spoken-text shaping and Groq model selection. No network calls."""

import unittest

from voice_groq import VoiceConfigError, pick_speech_models, spoken_text


class TestVoice(unittest.TestCase):

    def test_spoken_text_skips_map_and_keeps_two_sentences(self):
        raw = (
            "<p>Sales rose in 2023. The median price was higher. A third sentence stays out.</p>"
            "<div id='map' data-markers='[1]'></div>"
            "<script>function initMap(){}</script>"
        )
        spoken = spoken_text(raw)
        self.assertEqual(spoken, "Sales rose in 2023. The median price was higher.")
        self.assertNotIn("map", spoken.lower())
        self.assertNotIn("initMap", spoken)

    def test_spoken_text_caps_length(self):
        spoken = spoken_text("word " * 80)
        self.assertLessEqual(len(spoken), 200)
        self.assertNotIn("  ", spoken)

    def test_pick_speech_models_prefers_turbo_and_english(self):
        stt, tts = pick_speech_models(
            [
                "whisper-large-v3",
                "whisper-large-v3-turbo",
                "canopylabs/orpheus-arabic-saudi",
                "canopylabs/orpheus-v1-english",
            ]
        )
        self.assertEqual(stt, "whisper-large-v3-turbo")
        self.assertEqual(tts, "canopylabs/orpheus-v1-english")

    def test_pick_speech_models_requires_both(self):
        with self.assertRaises(VoiceConfigError):
            pick_speech_models(["whisper-large-v3-turbo"])


if __name__ == "__main__":
    unittest.main()

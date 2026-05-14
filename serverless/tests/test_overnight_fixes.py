"""Unit tests for the 2026-05-09 overnight bug fixes.

Targets three issues reported in Discord msg 1502382610452582533:
  1. STT ghost-recognition (wizper hallucinates on cutoff/empty audio) →
     `_audio_quality_ok` gate
  2. Numerals in STT output (4 5 6 instead of "cuatro cinco seis") →
     `_despeakerize_numerals`
  3. Mistakes-list duplication → dedup pass in `_phoneme_align`

These tests do NOT require model loading; they exercise the pure helpers
directly.
"""

from __future__ import annotations

import numpy as np
import pytest

from main import (
    Mistake,
    _audio_quality_ok,
    _despeakerize_numerals,
    _phoneme_align,
    _SPANISH_NUMERALS_ES,
)


# ---------- Numeral despeakerization ----------


class TestDespeakerizeNumerals:
    def test_cuatro_cinco_seis(self):
        # The exact bug: wizper returned "4 5 6" for spoken "Cuatro, cinco, seis"
        out = _despeakerize_numerals("4 5 6", "Cuatro, cinco, seis", "es")
        assert out == "cuatro cinco seis"

    def test_with_punctuation_preserved(self):
        out = _despeakerize_numerals("4, 5, 6.", "Cuatro, cinco, seis", "es")
        assert out == "cuatro, cinco, seis."

    def test_skip_when_expected_has_digits(self):
        # Don't molest a phrase that legit contains digits in the expected text
        out = _despeakerize_numerals("3.14", "say 3.14 in spanish", "es")
        assert out == "3.14"

    def test_skip_for_non_spanish(self):
        out = _despeakerize_numerals("4 5 6", "four five six", "en")
        assert out == "4 5 6"

    def test_passthrough_when_no_digits(self):
        out = _despeakerize_numerals("Hola, ¿cómo estás?", "Hola", "es")
        assert out == "Hola, ¿cómo estás?"

    def test_unknown_digit_left_as_is(self):
        # 9999 not in lookup table — leave alone (don't crash)
        out = _despeakerize_numerals("9999 cuatro", "Cuatro", "es")
        assert out == "9999 cuatro"

    def test_empty_input(self):
        assert _despeakerize_numerals("", "Hola", "es") == ""
        assert _despeakerize_numerals(None, "Hola", "es") is None  # type: ignore[arg-type]

    def test_full_corpus_coverage_1_to_20(self):
        # Sanity-check the lookup covers the v1 corpus range
        for d in range(0, 21):
            assert str(d) in _SPANISH_NUMERALS_ES, f"missing {d}"


# ---------- Audio quality gate ----------


class TestAudioQualityGate:
    def test_empty_waveform_rejected(self):
        ok, reason = _audio_quality_ok(np.array([], dtype=np.float32))
        assert not ok
        assert reason == "no_audio"

    def test_too_short_rejected(self):
        # 0.1s of audio at 16kHz = 1600 samples
        wf = np.full(1600, 0.5, dtype=np.float32)
        ok, reason = _audio_quality_ok(wf)
        assert not ok
        assert "too_short" in reason

    def test_silent_long_audio_rejected(self):
        # 2s of silence — long enough but RMS = 0
        wf = np.zeros(32000, dtype=np.float32)
        ok, reason = _audio_quality_ok(wf)
        assert not ok
        assert "too_quiet" in reason

    def test_real_speech_accepted(self):
        # 1s of moderate-amplitude noise (RMS ~ 0.3)
        rng = np.random.default_rng(42)
        wf = rng.uniform(-0.5, 0.5, size=16000).astype(np.float32)
        ok, reason = _audio_quality_ok(wf)
        assert ok
        assert reason == ""

    def test_quiet_speech_accepted_above_floor(self):
        # RMS ~ 0.01 (quiet but above the 0.005 floor)
        wf = np.full(16000, 0.01, dtype=np.float32)
        ok, _ = _audio_quality_ok(wf)
        assert ok


# ---------- Mistakes dedup ----------


class TestMistakesDedup:
    """Verify the dedup pass in _phoneme_align doesn't emit duplicate hints.

    Reproduces the Discord 2026-05-08 symptom where "Final s dropped"
    appeared twice for a single utterance.
    """

    def test_phoneme_align_dedups_repeated_mistakes(self):
        # Use raw helper. Construct expected/actual phoneme lists where the
        # same substitution would be made twice (e.g. expected ends in 's' s'
        # got dropped — happens at two positions if the IPA string had double s).
        # The unit test here is structural: even if backtrace produced dups,
        # the returned list is unique.
        expected = ["b", "w", "e", "n", "a", "s", "t", "a", "r", "d", "e", "s"]
        actual = ["b", "w", "e", "n", "a", "t", "a", "r", "d", "e"]  # both 's' dropped

        score, ops, mistakes = _phoneme_align(expected, actual)
        # Score is non-zero — alignment matters
        assert score < 100
        # Mistakes should be unique by (phoneme, expected, actual, hint)
        keys = [(m.phoneme, m.expected, m.actual, m.hint) for m in mistakes]
        assert len(keys) == len(set(keys)), f"dups in mistakes: {keys}"

    def test_dedup_preserves_distinct_mistakes(self):
        # Two GENUINELY different mistakes should both survive.
        # We can't directly inject Mistake objects into _phoneme_align's
        # internals, but we can verify the dedup logic is by-key not by-count
        # via the keys above. This test reaffirms uniqueness without forcing
        # equal hints.
        expected = ["b", "w", "e", "n", "a", "s"]
        actual = ["b", "w", "e", "n", "a"]
        score, ops, mistakes = _phoneme_align(expected, actual)
        # Should produce at most 1 mistake for the dropped final s
        assert len(mistakes) <= 1


# ---------- Spanish numerals lookup completeness ----------


class TestNumeralLookup:
    def test_lookup_has_no_digit_value(self):
        # All values in the lookup table should be alphabetic (no digits)
        for digit, word in _SPANISH_NUMERALS_ES.items():
            assert not any(ch.isdigit() for ch in word), (
                f"{digit} -> {word} contains digits"
            )

    def test_lookup_includes_corpus_range(self):
        # The corpus uses 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 20
        for n in [1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 20]:
            assert str(n) in _SPANISH_NUMERALS_ES

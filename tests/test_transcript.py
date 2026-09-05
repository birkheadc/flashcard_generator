from __future__ import annotations

from flashcard_generator.transcript import normalize_transcript


def test_normalizes_crlf_line_endings():
    assert normalize_transcript("First.\r\nSecond.") == "First.\nSecond."


def test_strips_leading_and_trailing_blank_lines():
    assert normalize_transcript("\n\nFirst.\nSecond.\n\n\n") == "First.\nSecond."


def test_preserves_internal_structure():
    raw = "First section.\n\nSecond section.\n\nThird section."
    assert normalize_transcript(raw) == raw


def test_empty_text_stays_empty():
    assert normalize_transcript("") == ""
    assert normalize_transcript("\n\n") == ""

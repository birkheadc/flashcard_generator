from __future__ import annotations


def normalize_transcript(raw_text: str) -> str:
    """Normalize a transcript's raw text for storage/display: consistent
    line endings, no leading/trailing blank lines. Deliberately does not
    split the text into sections — see ROADMAP.md Phase 4: matching is done
    by freely highlighting a span of the raw transcript, not by picking
    from pre-cut sections, since automatic splitting only makes sense in
    the context of forced alignment (Phase 9), not manual matching.
    """
    return raw_text.replace("\r\n", "\n").strip("\n")

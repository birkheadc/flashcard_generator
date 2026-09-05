from __future__ import annotations

from flashcard_generator.items import ClozeSpan
from flashcard_generator.template import (
    DEFAULT_BACK_TEMPLATE,
    DEFAULT_FIELDS,
    DEFAULT_FRONT_TEMPLATE,
    DEFAULT_TEMPLATE_NAME,
    NoteTemplate,
    cloze_index_count,
    cloze_wrapped_text,
    render_card,
    render_cloze_field,
)


def test_note_template_defaults_mirror_genanki_cloze_model():
    template = NoteTemplate()
    assert template.name == DEFAULT_TEMPLATE_NAME
    assert template.fields == DEFAULT_FIELDS
    assert template.front_template == DEFAULT_FRONT_TEMPLATE
    assert template.back_template == DEFAULT_BACK_TEMPLATE


def test_cloze_wrapped_text_wraps_the_marked_span():
    assert cloze_wrapped_text("저는 학생 입니다", [ClozeSpan(3, 5)]) == "저는 {{c1::학생}} 입니다"


def test_cloze_wrapped_text_wraps_japanese_span():
    assert cloze_wrapped_text("これはサンプルです", [ClozeSpan(3, 7)]) == "これは{{c1::サンプル}}です"


def test_cloze_wrapped_text_returns_unchanged_without_spans():
    assert cloze_wrapped_text("hello world", []) == "hello world"


def test_cloze_wrapped_text_skips_invalid_spans():
    assert cloze_wrapped_text("hi", [ClozeSpan(6, 11)]) == "hi"
    assert cloze_wrapped_text("hello", [ClozeSpan(3, 3)]) == "hello"


def test_cloze_wrapped_text_numbers_multiple_spans_in_reading_order():
    # Passed out of position order to confirm numbering follows the text,
    # not the order spans are given in — ROADMAP.md Phase 5.5.
    spans = [ClozeSpan(8, 13), ClozeSpan(0, 3)]
    assert cloze_wrapped_text("one two three", spans) == "{{c1::one}} two {{c2::three}}"


def test_cloze_wrapped_text_skips_span_overlapping_an_earlier_one():
    spans = [ClozeSpan(0, 5), ClozeSpan(3, 8)]
    assert cloze_wrapped_text("hello world", spans) == "{{c1::hello}} world"


def test_render_cloze_field_blanks_on_front_reveals_on_back():
    wrapped = "저는 {{c1::학생}} 입니다"
    assert render_cloze_field(wrapped, reveal=False) == "저는 [...] 입니다"
    assert render_cloze_field(wrapped, reveal=True) == "저는 학생 입니다"


def test_render_cloze_field_passes_through_text_without_a_cloze():
    assert render_cloze_field("plain text", reveal=False) == "plain text"
    assert render_cloze_field("plain text", reveal=True) == "plain text"


def test_render_cloze_field_only_blanks_the_active_index():
    wrapped = "저는 {{c1::학생}} 이고 {{c2::학교}}에 갑니다"
    assert (
        render_cloze_field(wrapped, active_index=1, reveal=False)
        == "저는 [...] 이고 학교에 갑니다"
    )
    assert (
        render_cloze_field(wrapped, active_index=2, reveal=False)
        == "저는 학생 이고 [...]에 갑니다"
    )
    # Revealing the active card's own cloze shows everything, same as
    # today's single-cloze case.
    assert (
        render_cloze_field(wrapped, active_index=1, reveal=True)
        == "저는 학생 이고 학교에 갑니다"
    )


def test_render_card_substitutes_cloze_placeholder():
    values = {"Text": "저는 {{c1::학생}} 입니다"}
    assert render_card("{{cloze:Text}}", values, reveal=False) == "저는 [...] 입니다"
    assert render_card("{{cloze:Text}}", values, reveal=True) == "저는 학생 입니다"


def test_render_card_substitutes_plain_field_placeholders():
    values = {"Text": "hello", "Audio": "[audio clip]"}
    rendered = render_card("{{Text}}<br>{{Audio}}", values, reveal=False)
    assert rendered == "hello<br>[audio clip]"


def test_render_card_treats_missing_fields_as_empty():
    rendered = render_card("{{Missing}}", {}, reveal=False)
    assert rendered == ""


def test_render_card_default_templates_end_to_end():
    template = NoteTemplate()
    values = {"Text": "これは{{c1::サンプル}}です", "Audio": "🔊 0:00–0:02"}
    front = render_card(template.front_template, values, reveal=False)
    back = render_card(template.back_template, values, reveal=True)
    assert front == "これは[...]です"
    assert back == "これはサンプルです<br>🔊 0:00–0:02"


def test_render_card_shows_only_the_active_clozes_card():
    # Real Anki generates one card per distinct cloze number; a card's
    # front only ever blanks its OWN number, revealing every other one
    # (they belong to other cards) — not blanking every cloze at once.
    wrapped = cloze_wrapped_text("one two three", [ClozeSpan(0, 3), ClozeSpan(8, 13)])
    values = {"Text": wrapped}
    front_c1 = render_card("{{cloze:Text}}", values, active_index=1, reveal=False)
    back_c1 = render_card("{{cloze:Text}}", values, active_index=1, reveal=True)
    assert front_c1 == "[...] two three"
    assert back_c1 == "one two three"

    front_c2 = render_card("{{cloze:Text}}", values, active_index=2, reveal=False)
    assert front_c2 == "one two [...]"


def test_cloze_index_count_counts_distinct_cloze_numbers():
    wrapped = cloze_wrapped_text("one two three", [ClozeSpan(0, 3), ClozeSpan(8, 13)])
    assert cloze_index_count({"Text": wrapped, "Audio": "[a]"}) == 2


def test_cloze_index_count_zero_without_any_cloze():
    assert cloze_index_count({"Text": "plain text", "Audio": "[a]"}) == 0


def test_cloze_index_count_one_for_a_single_cloze():
    wrapped = cloze_wrapped_text("hello world", [ClozeSpan(6, 11)])
    assert cloze_index_count({"Text": wrapped}) == 1

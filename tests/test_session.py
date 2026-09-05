from __future__ import annotations

from flashcard_generator.clips import Clip
from flashcard_generator.items import ClozeSpan, Item, ItemList
from flashcard_generator.session import default_session_path, load_session, save_session
from flashcard_generator.template import NoteTemplate


def test_default_session_path_is_under_home():
    path = default_session_path()
    assert path.name == "session.json"
    assert ".flashcard_generator" in path.parts


def test_save_then_load_round_trips_audio_path_and_items(tmp_path):
    session_path = tmp_path / "nested" / "session.json"
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.5), text="first"))
    items.add(Item(clip=Clip(2.0, 3.0), text="こんにちは"))

    save_session(session_path, "/some/audio.wav", items)
    data = load_session(session_path)

    assert data is not None
    assert data.audio_path == "/some/audio.wav"
    assert [i.text for i in data.items] == ["first", "こんにちは"]
    assert [i.clip.start_seconds for i in data.items] == [0.0, 2.0]
    assert [i.clip.end_seconds for i in data.items] == [1.5, 3.0]


def test_save_creates_parent_directories(tmp_path):
    session_path = tmp_path / "a" / "b" / "c" / "session.json"

    save_session(session_path, "/audio.wav", ItemList())

    assert session_path.exists()


def test_load_returns_none_when_file_missing(tmp_path):
    assert load_session(tmp_path / "does_not_exist.json") is None


def test_load_returns_none_for_corrupted_json(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text("not valid json{{{", encoding="utf-8")

    assert load_session(session_path) is None


def test_load_returns_none_when_required_fields_missing(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text('{"items": []}', encoding="utf-8")  # missing audio_path

    assert load_session(session_path) is None


def test_load_returns_none_for_invalid_clip_span(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text(
        '{"audio_path": "/a.wav", "items": '
        '[{"start_seconds": 5.0, "end_seconds": 1.0, "text": "bad"}]}',
        encoding="utf-8",
    )

    assert load_session(session_path) is None


def test_save_then_load_round_trips_transcript_text(tmp_path):
    session_path = tmp_path / "session.json"
    transcript_text = "First section.\n\nSecond section."

    save_session(session_path, "/audio.wav", ItemList(), transcript_text)
    data = load_session(session_path)

    assert data.transcript_text == transcript_text


def test_save_without_transcript_text_round_trips_empty_string(tmp_path):
    session_path = tmp_path / "session.json"

    save_session(session_path, "/audio.wav", ItemList())
    data = load_session(session_path)

    assert data.transcript_text == ""


# -- cloze spans & note template (Phase 5, multi-cloze/library in 5.5) ------


def test_save_then_load_round_trips_cloze_spans(tmp_path):
    session_path = tmp_path / "session.json"
    items = ItemList()
    items.add(
        Item(
            clip=Clip(0.0, 1.0),
            text="저는 학생 입니다",
            cloze_spans=[ClozeSpan(0, 2), ClozeSpan(3, 5)],
        )
    )
    items.add(Item(clip=Clip(1.0, 2.0), text="no cloze here"))

    save_session(session_path, "/audio.wav", items)
    data = load_session(session_path)

    assert data.items[0].cloze_spans == [ClozeSpan(0, 2), ClozeSpan(3, 5)]
    assert data.items[0].has_cloze
    assert data.items[1].cloze_spans == []
    assert not data.items[1].has_cloze


def test_save_then_load_round_trips_extra_fields(tmp_path):
    session_path = tmp_path / "session.json"
    items = ItemList()
    items.add(
        Item(
            clip=Clip(0.0, 1.0),
            text="hello",
            extra_fields={"Definition": "a formal way of saying hello"},
        )
    )
    items.add(Item(clip=Clip(1.0, 2.0), text="no extra fields"))

    save_session(session_path, "/audio.wav", items)
    data = load_session(session_path)

    assert data.items[0].extra_fields == {"Definition": "a formal way of saying hello"}
    assert data.items[1].extra_fields == {}


def test_load_defaults_to_no_extra_fields_for_older_session_files(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text(
        '{"audio_path": "/a.wav", "items": '
        '[{"start_seconds": 0.0, "end_seconds": 1.0, "text": "hi"}]}',
        encoding="utf-8",
    )

    data = load_session(session_path)

    assert data is not None
    assert data.items[0].extra_fields == {}


def test_load_defaults_to_no_cloze_for_older_session_files(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text(
        '{"audio_path": "/a.wav", "items": '
        '[{"start_seconds": 0.0, "end_seconds": 1.0, "text": "hi"}]}',
        encoding="utf-8",
    )

    data = load_session(session_path)

    assert data is not None
    assert data.items[0].cloze_spans == []
    assert not data.items[0].has_cloze


def test_load_migrates_pre_5_5_single_span_format(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text(
        '{"audio_path": "/a.wav", "items": '
        '[{"start_seconds": 0.0, "end_seconds": 1.0, "text": "hello world", '
        '"cloze_start": 6, "cloze_end": 11}]}',
        encoding="utf-8",
    )

    data = load_session(session_path)

    assert data is not None
    assert data.items[0].cloze_spans == [ClozeSpan(6, 11)]
    assert data.items[0].has_cloze


def test_save_then_load_round_trips_note_template(tmp_path):
    session_path = tmp_path / "session.json"
    template = NoteTemplate(
        name="My Template",
        fields=["Text", "Audio", "Notes"],
        front_template="{{cloze:Text}}",
        back_template="{{cloze:Text}}<br>{{Audio}}<br>{{Notes}}",
    )

    save_session(session_path, "/audio.wav", ItemList(), template=template)
    data = load_session(session_path)

    assert data.template.name == "My Template"
    assert data.template.fields == ["Text", "Audio", "Notes"]
    assert data.template.front_template == "{{cloze:Text}}"
    assert data.template.back_template == "{{cloze:Text}}<br>{{Audio}}<br>{{Notes}}"


def test_load_defaults_to_default_template_for_older_session_files(tmp_path):
    session_path = tmp_path / "session.json"
    session_path.write_text('{"audio_path": "/a.wav", "items": []}', encoding="utf-8")

    data = load_session(session_path)

    assert data.template.fields == NoteTemplate().fields
    assert data.template.front_template == NoteTemplate().front_template
    assert data.template.back_template == NoteTemplate().back_template


def test_save_overwrites_previous_contents(tmp_path):
    session_path = tmp_path / "session.json"
    items = ItemList()
    items.add(Item(clip=Clip(0.0, 1.0), text="old"))
    save_session(session_path, "/a.wav", items)

    items2 = ItemList()
    items2.add(Item(clip=Clip(5.0, 6.0), text="new"))
    save_session(session_path, "/b.wav", items2)

    data = load_session(session_path)
    assert data.audio_path == "/b.wav"
    assert [i.text for i in data.items] == ["new"]

from __future__ import annotations

from flashcard_generator.clips import Clip
from flashcard_generator.items import Item, ItemList
from flashcard_generator.session import default_session_path, load_session, save_session


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

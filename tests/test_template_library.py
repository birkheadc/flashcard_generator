from __future__ import annotations

from flashcard_generator.template import NoteTemplate
from flashcard_generator.template_library import (
    default_template_library_path,
    load_template_library,
    save_template_library,
)


def test_default_template_library_path_is_under_home():
    path = default_template_library_path()
    assert path.name == "templates.json"
    assert ".flashcard_generator" in path.parts


def test_load_returns_empty_list_when_file_missing(tmp_path):
    assert load_template_library(tmp_path / "does_not_exist.json") == []


def test_save_then_load_round_trips_templates(tmp_path):
    path = tmp_path / "templates.json"
    templates = [
        NoteTemplate(name="Cloze Basic", fields=["Text", "Audio"]),
        NoteTemplate(
            name="Cloze Extended",
            fields=["Text", "Audio", "Notes"],
            front_template="{{cloze:Text}}",
            back_template="{{cloze:Text}}<br>{{Notes}}",
        ),
    ]

    save_template_library(path, templates)
    loaded = load_template_library(path)

    assert [t.name for t in loaded] == ["Cloze Basic", "Cloze Extended"]
    assert loaded[1].fields == ["Text", "Audio", "Notes"]
    assert loaded[1].back_template == "{{cloze:Text}}<br>{{Notes}}"


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "a" / "b" / "templates.json"

    save_template_library(path, [NoteTemplate(name="Solo")])

    assert path.exists()


def test_load_returns_empty_list_for_corrupted_json(tmp_path):
    path = tmp_path / "templates.json"
    path.write_text("not valid json{{{", encoding="utf-8")

    assert load_template_library(path) == []


def test_save_overwrites_previous_contents(tmp_path):
    path = tmp_path / "templates.json"
    save_template_library(path, [NoteTemplate(name="First")])

    save_template_library(path, [NoteTemplate(name="Second")])

    loaded = load_template_library(path)
    assert [t.name for t in loaded] == ["Second"]

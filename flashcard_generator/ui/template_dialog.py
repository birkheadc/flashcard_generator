from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..template import NoteTemplate, cloze_index_count, render_card
from ..template_library import load_template_library, save_template_library
from . import theme
from .icons import icon


class NoteTemplateDialog(QDialog):
    """Note type / template editor (DESIGN.md §8), modeled conceptually on
    Anki's own note-type editor per OUTLINE.md §2.3, but scoped to this
    app's needs: a field list, front/back template editors, and a live
    preview sharing `template.render_card` with the item editor's own card
    preview — one rendering implementation, not two that can drift apart.

    Edits apply to the in-progress `template` immediately (emitted via
    `template_changed` on every change), consistent with the app's "no
    save/open UI, one continuous session" model (DESIGN.md §10) — there's
    no separate Apply/OK step for the *session's* active template.

    ROADMAP.md Phase 5.5 adds a saved-template library on top of that: a
    "Saved Templates" list backed by `template_library.py`
    (`~/.flashcard_generator/templates.json`, independent of any one
    session, like Anki's own note types are independent of any one deck).
    New/Load/Save/Delete act on that list explicitly — those *do* need a
    deliberate action, unlike the live-editing above, so a stray click
    can't silently overwrite a saved preset.
    """

    template_changed = Signal(NoteTemplate)

    def __init__(
        self,
        template: NoteTemplate,
        preview_field_values: dict[str, str],
        library_path: Path,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Note Template")
        self._template = NoteTemplate(
            name=template.name,
            fields=list(template.fields),
            front_template=template.front_template,
            back_template=template.back_template,
        )
        self._preview_field_values = preview_field_values
        self._library_path = library_path
        self._library: list[NoteTemplate] = load_template_library(library_path)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_editor_side())
        splitter.addWidget(self._build_preview_side())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = QPushButton("Close")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        self._reload_library_list()
        self._refresh_preview()

        # Sized (and resized) only after the layout above is fully built,
        # so the splitter and its panels have real size hints to work
        # from — resizing an empty dialog before its layout exists left
        # the left panel's minimum height understated, which showed up as
        # the "Saved Templates" list and the New/Load/Save/Delete row
        # visibly overlapping (not just a cramped window).
        self.resize(max(820, self.sizeHint().width()), max(700, self.minimumSizeHint().height()))

    # -- editor side ----------------------------------------------------

    def _build_editor_side(self) -> QWidget:
        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)

        library_label = QLabel("Saved Templates")
        library_label.setObjectName("sectionLabel")
        panel_layout.addWidget(library_label)

        self._library_list = QListWidget(panel)
        self._library_list.setFixedHeight(90)
        self._library_list.currentRowChanged.connect(self._update_library_buttons_enabled)
        panel_layout.addWidget(self._library_list)

        library_buttons = QHBoxLayout()
        new_button = QPushButton("New")
        new_button.setIcon(icon("mdi6.file-plus-outline"))
        new_button.clicked.connect(self._on_new_template_clicked)
        library_buttons.addWidget(new_button)
        self._load_button = QPushButton("Load")
        self._load_button.setIcon(icon("mdi6.folder-open-outline"))
        self._load_button.clicked.connect(self._on_load_template_clicked)
        library_buttons.addWidget(self._load_button)
        self._save_button = QPushButton("Save")
        self._save_button.setIcon(icon("mdi6.content-save-outline"))
        self._save_button.clicked.connect(self._on_save_template_clicked)
        library_buttons.addWidget(self._save_button)
        self._delete_button = QPushButton("Delete")
        self._delete_button.setIcon(icon("mdi6.trash-can-outline", color=theme.ACTION_DANGER))
        self._delete_button.clicked.connect(self._on_delete_template_clicked)
        library_buttons.addWidget(self._delete_button)
        library_buttons.addStretch()
        panel_layout.addLayout(library_buttons)

        name_label = QLabel("Template Name")
        name_label.setObjectName("sectionLabel")
        panel_layout.addWidget(name_label)
        self._name_edit = QLineEdit(self._template.name, panel)
        self._name_edit.textEdited.connect(self._on_name_edited)
        panel_layout.addWidget(self._name_edit)

        fields_label = QLabel("Fields")
        fields_label.setObjectName("sectionLabel")
        panel_layout.addWidget(fields_label)

        self._field_list = QListWidget(panel)
        for name in self._template.fields:
            self._add_field_item(name)
        self._field_list.itemChanged.connect(self._on_field_renamed)
        panel_layout.addWidget(self._field_list)

        field_buttons = QHBoxLayout()
        add_field_button = QPushButton("Add Field")
        add_field_button.clicked.connect(self._on_add_field)
        field_buttons.addWidget(add_field_button)
        self._remove_field_button = QPushButton("Remove Field")
        self._remove_field_button.clicked.connect(self._on_remove_field)
        field_buttons.addWidget(self._remove_field_button)
        field_buttons.addStretch()
        panel_layout.addLayout(field_buttons)

        front_label = QLabel("Front Template")
        front_label.setObjectName("sectionLabel")
        panel_layout.addWidget(front_label)
        self._front_edit = QPlainTextEdit(self._template.front_template, panel)
        self._front_edit.setFixedHeight(60)
        self._front_edit.textChanged.connect(self._on_template_text_changed)
        panel_layout.addWidget(self._front_edit)

        back_label = QLabel("Back Template")
        back_label.setObjectName("sectionLabel")
        panel_layout.addWidget(back_label)
        self._back_edit = QPlainTextEdit(self._template.back_template, panel)
        self._back_edit.setFixedHeight(60)
        self._back_edit.textChanged.connect(self._on_template_text_changed)
        panel_layout.addWidget(self._back_edit)

        hint = QLabel(
            "Use {{cloze:FieldName}} for the field holding the marked cloze "
            "span(s), or {{FieldName}} to insert any field as-is — same "
            "placeholder syntax genanki/Anki use."
        )
        hint.setWordWrap(True)
        hint.setObjectName("hintLabel")
        panel_layout.addWidget(hint)

        return panel

    def _build_preview_side(self) -> QWidget:
        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)

        preview_label = QLabel("Live Preview")
        preview_label.setObjectName("sectionLabel")
        panel_layout.addWidget(preview_label)

        sample_label = QLabel("Sample Data")
        sample_label.setObjectName("hintLabel")
        panel_layout.addWidget(sample_label)
        # One editable row per field, so a field with no real data source
        # yet (anything beyond the cloze-text field and "Audio" — Item
        # doesn't model arbitrary per-item fields, per ROADMAP.md Phase
        # 5.5's note on this) can still be previewed: type sample content
        # here and the render below updates live. Rebuilt by
        # _rebuild_sample_data_inputs whenever the field list changes.
        self._sample_data_container = QWidget(panel)
        self._sample_data_layout = QVBoxLayout(self._sample_data_container)
        self._sample_data_layout.setContentsMargins(0, 0, 0, 0)
        self._sample_data_layout.setSpacing(4)
        panel_layout.addWidget(self._sample_data_container)
        self._rebuild_sample_data_inputs()

        # Anki generates one card per distinct cloze number, not one card
        # with every blank filled in — shown only when the Text field's
        # current sample/real data actually has more than one.
        self._multi_cloze_hint_label = QLabel("", panel)
        self._multi_cloze_hint_label.setObjectName("hintLabel")
        self._multi_cloze_hint_label.setWordWrap(True)
        self._multi_cloze_hint_label.setVisible(False)
        panel_layout.addWidget(self._multi_cloze_hint_label)

        front_caption = QLabel("Front")
        front_caption.setObjectName("hintLabel")
        panel_layout.addWidget(front_caption)
        self._preview_front = QLabel(panel)
        self._preview_front.setWordWrap(True)
        self._preview_front.setTextFormat(Qt.TextFormat.RichText)
        self._preview_front.setObjectName("cardPreviewFace")
        panel_layout.addWidget(self._preview_front)

        back_caption = QLabel("Back")
        back_caption.setObjectName("hintLabel")
        panel_layout.addWidget(back_caption)
        self._preview_back = QLabel(panel)
        self._preview_back.setWordWrap(True)
        self._preview_back.setTextFormat(Qt.TextFormat.RichText)
        self._preview_back.setObjectName("cardPreviewFace")
        panel_layout.addWidget(self._preview_back)

        panel_layout.addStretch(1)
        return panel

    # -- saved-template library (Phase 5.5) ----------------------------------

    def _reload_library_list(self) -> None:
        # Signals are blocked while rebuilding, including the setCurrentRow
        # below — so the button-enabled state (normally kept in sync by
        # currentRowChanged) is refreshed explicitly at the end instead,
        # rather than left for every caller to remember.
        self._library_list.blockSignals(True)
        self._library_list.clear()
        for saved in self._library:
            self._library_list.addItem(saved.name)
        for row, saved in enumerate(self._library):
            if saved.name == self._template.name:
                self._library_list.setCurrentRow(row)
                break
        self._library_list.blockSignals(False)
        self._update_library_buttons_enabled()

    def _update_library_buttons_enabled(self) -> None:
        has_selection = self._library_list.currentRow() >= 0
        self._load_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)
        self._save_button.setEnabled(bool(self._name_edit.text().strip()))

    def _on_new_template_clicked(self) -> None:
        self._template = NoteTemplate(name="New Template")
        self._reload_editor_from_template()
        self._library_list.setCurrentRow(-1)
        self._emit_changed()

    def _on_load_template_clicked(self) -> None:
        row = self._library_list.currentRow()
        if row < 0:
            return
        saved = self._library[row]
        self._template = NoteTemplate(
            name=saved.name,
            fields=list(saved.fields),
            front_template=saved.front_template,
            back_template=saved.back_template,
        )
        self._reload_editor_from_template()
        self._emit_changed()

    def _on_save_template_clicked(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            return
        self._template.name = name
        saved_copy = NoteTemplate(
            name=name,
            fields=list(self._template.fields),
            front_template=self._template.front_template,
            back_template=self._template.back_template,
        )
        existing_index = next((i for i, t in enumerate(self._library) if t.name == name), None)
        if existing_index is not None:
            self._library[existing_index] = saved_copy
        else:
            self._library.append(saved_copy)
        save_template_library(self._library_path, self._library)
        self._reload_library_list()

    def _on_delete_template_clicked(self) -> None:
        row = self._library_list.currentRow()
        if row < 0:
            return
        del self._library[row]
        save_template_library(self._library_path, self._library)
        self._reload_library_list()

    def _on_name_edited(self, text: str) -> None:
        self._template.name = text
        self._update_library_buttons_enabled()
        self._emit_changed()

    def _reload_editor_from_template(self) -> None:
        self._name_edit.blockSignals(True)
        self._name_edit.setText(self._template.name)
        self._name_edit.blockSignals(False)

        self._field_list.blockSignals(True)
        self._field_list.clear()
        for name in self._template.fields:
            self._add_field_item(name)
        self._field_list.blockSignals(False)

        self._front_edit.blockSignals(True)
        self._front_edit.setPlainText(self._template.front_template)
        self._front_edit.blockSignals(False)

        self._back_edit.blockSignals(True)
        self._back_edit.setPlainText(self._template.back_template)
        self._back_edit.blockSignals(False)

        self._rebuild_sample_data_inputs()
        self._update_library_buttons_enabled()

    # -- field list -------------------------------------------------------

    def _add_field_item(self, name: str) -> None:
        item = QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self._field_list.addItem(item)

    def _on_add_field(self) -> None:
        existing = {self._field_list.item(i).text() for i in range(self._field_list.count())}
        name = "Field"
        n = 1
        while name in existing:
            n += 1
            name = f"Field {n}"
        self._add_field_item(name)
        self._apply_fields_from_list()

    def _on_remove_field(self) -> None:
        row = self._field_list.currentRow()
        if row < 0 or self._field_list.count() <= 1:
            return
        self._field_list.takeItem(row)
        self._apply_fields_from_list()

    def _on_field_renamed(self, _item: QListWidgetItem) -> None:
        self._apply_fields_from_list()

    def _apply_fields_from_list(self) -> None:
        self._template.fields = [
            self._field_list.item(i).text().strip() or f"Field{i + 1}"
            for i in range(self._field_list.count())
        ]
        self._rebuild_sample_data_inputs()
        self._emit_changed()

    # -- templates ----------------------------------------------------------

    def _on_template_text_changed(self) -> None:
        self._template.front_template = self._front_edit.toPlainText()
        self._template.back_template = self._back_edit.toPlainText()
        self._emit_changed()

    # -- shared -------------------------------------------------------------

    def _emit_changed(self) -> None:
        self._refresh_preview()
        self.template_changed.emit(self._template)

    def _refresh_preview(self) -> None:
        cloze_count = cloze_index_count(self._preview_field_values)
        if cloze_count > 1:
            self._multi_cloze_hint_label.setText(
                f"This will make {cloze_count} cards — showing card 1 only."
            )
        self._multi_cloze_hint_label.setVisible(cloze_count > 1)

        self._preview_front.setText(
            render_card(
                self._template.front_template,
                self._preview_field_values,
                active_index=1,
                reveal=False,
            )
        )
        self._preview_back.setText(
            render_card(
                self._template.back_template,
                self._preview_field_values,
                active_index=1,
                reveal=True,
            )
        )

    def _rebuild_sample_data_inputs(self) -> None:
        while self._sample_data_layout.count():
            child = self._sample_data_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        for name in self._template.fields:
            row = QWidget(self._sample_data_container)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            label = QLabel(name, row)
            label.setFixedWidth(80)
            row_layout.addWidget(label)
            field_input = QLineEdit(self._preview_field_values.get(name, ""), row)
            field_input.setPlaceholderText(f"Sample {name.lower()} content…")
            field_input.textEdited.connect(
                lambda text, field_name=name: self._on_sample_value_edited(field_name, text)
            )
            row_layout.addWidget(field_input)
            self._sample_data_layout.addWidget(row)

    def _on_sample_value_edited(self, field_name: str, text: str) -> None:
        self._preview_field_values[field_name] = text
        self._refresh_preview()

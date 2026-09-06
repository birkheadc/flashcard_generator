from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

"""Shared visual language for the app, transcribed from the design tokens in
design_reference/tokens/*.css (the Claude Design mockup at
design_reference/Bootstrapper.dc.html). Names here mirror the CSS custom
property names 1:1 where practical, so this file can be diffed against the
source tokens directly.

Per DESIGN.md §11: a neutral, low-chroma base so the few colors that carry
real information (readiness state) stay the most saturated things on screen.
"""

# -- tokens/colors.css ---------------------------------------------------

# Paper — warm neutral surfaces, lightest to deepest.
PAPER_0 = "#ffffff"
PAPER_1 = "#faf7f0"
PAPER_2 = "#f3ede1"
PAPER_3 = "#e9e0cf"
PAPER_4 = "#ddd2bd"

# Ink — text and strokes.
INK_0 = "#14120f"
INK_1 = "#2a2723"
INK_2 = "#57514a"
INK_3 = "#8a8279"
INK_4 = "#b3aa9e"
INK_5 = "#d5ccbe"

# Cyprus — primary accent, the app's "action" color.
CYPRUS_700 = "#093c39"
CYPRUS_600 = "#0a4642"
CYPRUS_500 = "#0f5c57"
CYPRUS_400 = "#197a73"
CYPRUS_300 = "#5aa39c"
CYPRUS_100 = "#dcebe9"
CYPRUS_050 = "#eef6f5"

# Semantics — review grades.
GRADE_GOOD = "#2e7d4f"
GRADE_GOOD_100 = "#dff0e5"
GRADE_HARD = "#b07515"
GRADE_HARD_100 = "#f8ebd2"
GRADE_AGAIN = "#b4432b"
GRADE_AGAIN_100 = "#f7e2dc"
GRADE_NEW = "#3b6fb0"
GRADE_NEW_100 = "#e1eaf6"

# Semantic aliases (mirrors the CSS's own aliasing of raw tokens).
SURFACE_APP = PAPER_1
SURFACE_CARD = PAPER_0
SURFACE_SUNKEN = PAPER_2
SURFACE_SELECTED = CYPRUS_100  # matches the mockup's own selected-row fill

TEXT_TITLE = INK_0
TEXT_BODY = INK_1
TEXT_MUTED = INK_2
TEXT_SUBTLE = INK_3
TEXT_DISABLED = INK_4
TEXT_ACCENT = CYPRUS_500

BORDER_HAIRLINE = INK_5
BORDER_STRONG = INK_4
BORDER_FIELD = PAPER_4
BORDER_FOCUS = CYPRUS_400

ACTION_PRIMARY = CYPRUS_500
ACTION_PRIMARY_HOVER = CYPRUS_600
ACTION_PRIMARY_PRESS = CYPRUS_700
ACTION_DANGER = GRADE_AGAIN

# Old, pre-tokens names kept as aliases so waveform_widget.py/waveform_view.py
# (which paint with these directly) don't need touching.
ACCENT = ACTION_PRIMARY
ACCENT_SOFT = CYPRUS_100
ACCENT_BORDER = BORDER_FOCUS

# -- tokens/typography.css -------------------------------------------------

FONT_UI = '"Source Sans 3", "Segoe UI", system-ui, sans-serif'
# The token file's own serif stack, extended with CJK-safe fallbacks per
# DESIGN.md §11 — Source Serif 4 alone doesn't cover Japanese/Korean, and
# the item-text field is CJK text as often as not.
FONT_READ = '"Source Serif 4", Georgia, "Noto Serif JP", "Noto Serif KR", serif'
FONT_MONO = '"JetBrains Mono", ui-monospace, Menlo, Consolas, monospace'

# Source Sans 3 / Source Serif 4 / JetBrains Mono are unlikely to already be
# installed on the machine this runs on, so the family names above would
# otherwise silently fall back to a system font. All three are SIL Open Font
# License 1.1 (see ui/fonts/OFL-*.txt) — free to bundle — so the .ttf files
# are vendored here instead of fetched at runtime (this is meant to work on
# a laptop with no reliable network, per OUTLINE.md §1).
_FONTS_DIR = Path(__file__).parent / "fonts"
_FONT_FILES = [
    "SourceSans3-Regular.ttf",
    "SourceSans3-SemiBold.ttf",
    "SourceSans3-Bold.ttf",
    "SourceSerif4-Regular.ttf",
    "SourceSerif4-SemiBold.ttf",
    "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Medium.ttf",
    "JetBrainsMono-Bold.ttf",
]
_fonts_loaded = False


def ensure_fonts_loaded() -> None:
    """Register the bundled font files with Qt and make Source Sans 3 the
    application's actual default font. Safe to call repeatedly (e.g. once
    per MainWindow in tests) — only does the work once per process.
    Requires a QApplication to already exist.

    A `font-family` QSS rule on a container widget does NOT reliably
    cascade to children like QPushButton/QTableWidget/QHeaderView in Qt —
    unlike real CSS, Qt Style Sheets inheritance is inconsistent for
    compound widgets, so those fall back silently to the platform default
    (e.g. DejaVu Sans on Linux) unless a rule targets them directly. Setting
    QApplication.setFont() instead changes the actual base font every
    widget inherits, which per-widget QSS rules (the mono clock label, the
    serif text edit, ...) still override as normal.
    """
    global _fonts_loaded
    if _fonts_loaded:
        return
    for filename in _FONT_FILES:
        QFontDatabase.addApplicationFont(str(_FONTS_DIR / filename))

    app = QApplication.instance()
    if app is not None:
        font = QFont()
        font.setFamilies(["Source Sans 3", "Segoe UI", "sans-serif"])
        font.setPixelSize(TEXT_UI)
        app.setFont(font)

    _fonts_loaded = True

TEXT_MICRO = 10
TEXT_META = 11
TEXT_UI = 13
TEXT_UI_LG = 15
TEXT_H3 = 17

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_SEMIBOLD = 600
WEIGHT_BOLD = 700

# -- tokens/spacing.css ------------------------------------------------

SPACE_2 = 4
SPACE_3 = 6
SPACE_4 = 8
SPACE_5 = 12
SPACE_6 = 16

TOOLBAR_HEIGHT = 44
STATUSBAR_HEIGHT = 26
CONTROL_HEIGHT_SM = 24
CONTROL_HEIGHT = 28

# -- tokens/surfaces.css -------------------------------------------------

RADIUS_1 = 3
RADIUS_2 = 5
RADIUS_3 = 7
RADIUS_4 = 10
RADIUS_PILL = 999

BORDER_WIDTH = 1

STYLESHEET = f"""
QWidget#centralWidget {{
    background: {PAPER_0};
    color: {TEXT_BODY};
    font-family: {FONT_UI};
    font-size: {TEXT_UI}px;
}}

QLabel#sectionLabel {{
    color: {TEXT_SUBTLE};
    font-size: {TEXT_MICRO}px;
    font-weight: {WEIGHT_SEMIBOLD};
    letter-spacing: 1px;
}}

QLabel#metaLabel {{
    color: {TEXT_DISABLED};
    font-family: {FONT_MONO};
    font-size: {TEXT_META}px;
}}

QLabel#hintLabel {{
    color: {TEXT_SUBTLE};
    font-size: {TEXT_META}px;
}}

QLabel#clockLabel {{
    color: {TEXT_TITLE};
    font-family: {FONT_MONO};
    font-size: {TEXT_UI}px;
    font-weight: {WEIGHT_BOLD};
}}

QFrame#panelHeader {{
    background: {PAPER_1};
    border-bottom: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
}}

QFrame#panelFooter {{
    background: {PAPER_1};
    border-top: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
}}

QWidget#waveformPanel, QWidget#transcriptPanel, QWidget#itemsPanel, QWidget#editorPanel, QWidget#previewPanel {{
    background: {PAPER_0};
    border: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
}}

QWidget#editorPanel, QWidget#previewPanel {{
    background: {PAPER_1};
}}

QWidget#scrollBody {{
    background: transparent;
}}

QToolBar#mainToolbar {{
    background: {PAPER_1};
    border-bottom: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    padding: {SPACE_2}px {SPACE_4}px;
    spacing: {SPACE_2}px;
}}

QToolBar#mainToolbar QToolButton {{
    background: {PAPER_0};
    border: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    border-radius: {RADIUS_2}px;
    padding: {SPACE_2}px {SPACE_4}px;
    color: {TEXT_BODY};
    min-height: {CONTROL_HEIGHT}px;
}}

QToolBar#mainToolbar QToolButton:hover:!disabled {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT_BORDER};
}}

QToolBar#mainToolbar QToolButton:disabled {{
    color: {TEXT_DISABLED};
    background: {PAPER_2};
    border-color: {BORDER_HAIRLINE};
}}

QToolBar#mainToolbar QToolButton#primaryToolButton {{
    background: {ACTION_PRIMARY};
    border-color: {ACTION_PRIMARY};
    color: {PAPER_0};
    font-weight: {WEIGHT_SEMIBOLD};
}}

QToolBar#mainToolbar QToolButton#primaryToolButton:hover:!disabled {{
    background: {ACTION_PRIMARY_HOVER};
}}

QPushButton {{
    background: {PAPER_0};
    border: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    border-radius: {RADIUS_2}px;
    padding: {SPACE_2}px {SPACE_5}px;
    color: {TEXT_BODY};
    min-height: {CONTROL_HEIGHT}px;
}}

QPushButton:hover:!disabled {{
    background: {ACCENT_SOFT};
    border-color: {ACCENT_BORDER};
}}

QPushButton:pressed:!disabled {{
    background: {CYPRUS_100};
    border-color: {ACTION_PRIMARY_PRESS};
}}

QPushButton:disabled {{
    color: {TEXT_DISABLED};
    background: {PAPER_2};
}}

QPushButton#primaryButton {{
    background: {ACTION_PRIMARY};
    border-color: {ACTION_PRIMARY};
    color: {PAPER_0};
    font-weight: {WEIGHT_SEMIBOLD};
}}

QPushButton#primaryButton:hover:!disabled {{
    background: {ACTION_PRIMARY_HOVER};
}}

QPushButton#dangerButton {{
    color: {ACTION_DANGER};
}}

QPushButton#zoomStepButton {{
    padding: 0;
    min-height: {CONTROL_HEIGHT_SM}px;
    border-radius: {RADIUS_1}px;
}}

QPushButton#rowIconButton {{
    padding: 0;
    border: none;
    border-radius: {RADIUS_1}px;
    background: transparent;
}}

QPushButton#rowIconButton:hover {{
    /* Deliberately not ACCENT_SOFT/SURFACE_SELECTED (same color) — a
    selected row already has that fill, so a same-color hover would be
    invisible on it. This needs to stand out against both, but a saturated
    accent (formerly CYPRUS_300) clashed with the red danger icon and read
    as a stray status color rather than a hover state, so it's a neutral
    paper tone instead. */
    background: {PAPER_4};
}}

QLabel#stateBadge {{
    border-radius: {RADIUS_PILL}px;
    border: {BORDER_WIDTH}px solid transparent;
    padding: 0px {SPACE_4}px;
    font-size: {TEXT_MICRO}px;
    font-weight: {WEIGHT_SEMIBOLD};
}}

QLabel#stateBadge[tone="good"] {{
    background: {GRADE_GOOD_100};
    color: {GRADE_GOOD};
    border-color: {GRADE_GOOD};
}}

QLabel#stateBadge[tone="hard"] {{
    background: {GRADE_HARD_100};
    color: {GRADE_HARD};
    border-color: {GRADE_HARD};
}}

QTableWidget {{
    background: {PAPER_0};
    border: none;
    outline: none;
    gridline-color: {BORDER_HAIRLINE};
    font-size: {TEXT_UI}px;
}}

QTableWidget::item {{
    padding: {SPACE_2}px {SPACE_4}px;
    border-bottom: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    color: {TEXT_BODY};
}}

QTableWidget::item:selected {{
    background: {SURFACE_SELECTED};
    color: {TEXT_TITLE};
}}

QHeaderView::section {{
    background: {PAPER_1};
    border: none;
    border-bottom: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    padding: {SPACE_2}px {SPACE_4}px;
    color: {TEXT_SUBTLE};
    font-size: {TEXT_MICRO}px;
    font-weight: {WEIGHT_SEMIBOLD};
    letter-spacing: 1px;
}}

QSlider::groove:horizontal {{
    height: 2px;
    background: {INK_4};
    border-radius: 1px;
}}

QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: {ACTION_PRIMARY};
}}

QSlider::sub-page:horizontal {{
    background: {ACTION_PRIMARY};
    border-radius: 1px;
}}

QPlainTextEdit {{
    background: {PAPER_0};
    border: {BORDER_WIDTH}px solid {BORDER_FIELD};
    border-radius: {RADIUS_3}px;
    padding: {SPACE_4}px {SPACE_5}px;
    color: {TEXT_BODY};
    font-family: {FONT_READ};
}}

QPlainTextEdit:focus {{
    border-color: {BORDER_FOCUS};
}}

QPlainTextEdit:disabled {{
    background: {PAPER_2};
    color: {TEXT_DISABLED};
}}

QLabel#cardPreviewFace {{
    background: {PAPER_0};
    border: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    border-radius: {RADIUS_3}px;
    padding: {SPACE_4}px {SPACE_5}px;
    color: {TEXT_BODY};
    font-family: {FONT_READ};
}}

QSplitter::handle {{
    background: transparent;
}}

QStatusBar#mainStatusBar {{
    background: {PAPER_2};
    border-top: {BORDER_WIDTH}px solid {BORDER_HAIRLINE};
    color: {TEXT_SUBTLE};
    font-family: {FONT_MONO};
    font-size: {TEXT_META}px;
}}
"""


def section_label_text(text: str) -> str:
    """Uppercased small-caps-style section header text (Qt QSS has no
    text-transform, so the casing has to happen in the string itself)."""
    return text.upper()

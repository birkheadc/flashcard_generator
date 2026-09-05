from __future__ import annotations

import qtawesome as qta
from PySide6.QtGui import QIcon

from . import theme


def icon(name: str, *, color: str = theme.TEXT_BODY, color_disabled: str = theme.TEXT_DISABLED) -> QIcon:
    """A themed QIcon from the bundled Material Design Icons set (via
    qtawesome), colored to match the app's palette rather than qtawesome's
    black default, and dimmed the same way disabled text already is when
    the icon lands on a disabled QAction/QPushButton."""
    return qta.icon(name, color=color, color_disabled=color_disabled)

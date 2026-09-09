from __future__ import annotations

from flashcard_generator.ui import theme


def test_apply_app_theme_runs_without_error(qapp):
    theme.apply_app_theme(qapp)

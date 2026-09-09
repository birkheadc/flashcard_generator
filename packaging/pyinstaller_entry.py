"""PyInstaller entry point.

Analysis needs a real script path, and flashcard_generator/main.py can't be
that script directly: it uses the package-relative import
`from .ui.main_window import MainWindow`, which only resolves when Python
treats it as part of the flashcard_generator package (as `python -m
flashcard_generator.main` does, per dev.sh) — not when run as a bare
top-level script, which is how PyInstaller executes its entry script.
"""

from flashcard_generator.main import main

if __name__ == "__main__":
    main()

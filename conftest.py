import os

# Run Qt without a real display/GPU during tests. Must happen before PySide6
# is imported by anything (pytest-qt included), so this has to live in the
# rootdir conftest.py rather than under tests/.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

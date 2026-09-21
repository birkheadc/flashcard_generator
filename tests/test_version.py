import tomllib
from pathlib import Path

from flashcard_generator import __version__


def test_pyproject_version_matches_package_version():
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    )
    assert pyproject["project"]["version"] == __version__

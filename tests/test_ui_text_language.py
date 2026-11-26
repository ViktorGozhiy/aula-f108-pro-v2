import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CYRILLIC = re.compile("[\u0400-\u04ff]")
SHIPPED_DIRECTORIES = ("src/aula_f108", "packaging")
TEXT_SUFFIXES = {".py", ".json", ".desktop", ".rules", ".sh"}


def test_shipped_files_hold_no_cyrillic():
    """The interface is English only."""
    found = []
    for directory in SHIPPED_DIRECTORIES:
        for path in sorted((REPO / directory).rglob("*")):
            if path.suffix in TEXT_SUFFIXES:
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                    if CYRILLIC.search(line):
                        found.append(f"{path.relative_to(REPO)}:{number}")
    assert not found

"""Access to the captured data in tests/fixtures."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def load_hex(name: str) -> bytes:
    """Return the bytes of a fixture file that holds one hex string."""
    return bytes.fromhex((FIXTURES / name).read_text().strip())

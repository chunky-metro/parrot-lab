"""Make `main` importable from tests/ without an __init__ shuffle."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

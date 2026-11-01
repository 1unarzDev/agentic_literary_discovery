"""Keep tests importable when pytest is provided by uv's transient environment."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

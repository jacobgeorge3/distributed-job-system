"""Pytest configuration. Adds api-service to path for imports."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api-service"))

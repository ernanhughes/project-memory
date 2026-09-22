"""Make the instrument package importable under pytest."""

import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent
if str(BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(BENCHMARK_DIR))

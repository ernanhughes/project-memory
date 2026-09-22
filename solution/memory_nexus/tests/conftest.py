"""Import the Nexus package and the instrument under pytest."""

import sys
from pathlib import Path

SOLUTION_ROOT = Path(__file__).resolve().parent.parent.parent
INSTRUMENT_ROOT = SOLUTION_ROOT.parent / "experiments" / "benchmark"
for candidate in (str(SOLUTION_ROOT), str(INSTRUMENT_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

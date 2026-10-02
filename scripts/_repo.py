"""Put the repo root on sys.path so ``python scripts/*.py`` can ``import tcspc``."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

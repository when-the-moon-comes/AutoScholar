from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for _p in (str(SRC), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SIBLING_SRC_ROOTS = (
    REPO_ROOT.parent / "QuantPlatformKit" / "src",
    REPO_ROOT.parent / "UsEquityStrategies" / "src",
)

for path in reversed(SIBLING_SRC_ROOTS):
    if path.exists() and str(path) not in sys.path:
        sys.path.insert(0, str(path))

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from strategy_registry import get_platform_profile_status_matrix


def main() -> None:
    print(json.dumps(get_platform_profile_status_matrix(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from application.operator_support import format_paper_account_state
from application.state_store_service import FirestorePaperStateStore, LocalJsonPaperStateStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Print one paper account state.")
    parser.add_argument("--paper-account-group", required=True)
    parser.add_argument("--backend", choices=("local_json", "firestore"), default="local_json")
    parser.add_argument(
        "--state-dir",
        default=str(REPO_ROOT / ".paper_signal" / "state"),
    )
    parser.add_argument("--project-id")
    parser.add_argument("--firestore-collection", default="paper_signal_states")
    parser.add_argument("--lang", default="en")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.backend == "local_json":
        store = LocalJsonPaperStateStore(args.state_dir)
    else:
        from google.cloud import firestore

        client = firestore.Client(project=args.project_id) if args.project_id else firestore.Client()
        store = FirestorePaperStateStore(client=client, collection_name=args.firestore_collection)

    state = store.load(args.paper_account_group)
    if state is None:
        raise SystemExit(f"paper account state not found: {args.paper_account_group}")

    if args.json:
        print(
            json.dumps(
                {
                    "paper_account_group": state.paper_account_group,
                    "cash": state.cash,
                    "nav": state.nav,
                    "positions": dict(state.positions),
                    "metadata": dict(state.metadata),
                },
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return

    print(format_paper_account_state(state, lang=args.lang))


if __name__ == "__main__":
    main()

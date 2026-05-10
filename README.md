# PaperSignalPlatform

Brokerless paper-trading and signal-notification runtime for shared `us_equity`
strategy profiles.

`PaperSignalPlatform` is a sibling runtime repository to:

- `InteractiveBrokersPlatform`
- `CharlesSchwabPlatform`
- `LongBridgePlatform`

The difference is intentional: this repository must never place real orders.
It owns only:

- paper-account config parsing
- paper execution contracts
- Telegram/log/artifact transport
- local operator inspection helpers

Strategy semantics stay in `UsEquityStrategies`. Shared contracts stay in
`QuantPlatformKit`.

## Design rules

1. Strategy code must remain platform-agnostic and live in `UsEquityStrategies`.
2. This repository must not contain broker SDKs or real order submitters.
3. New strategy onboarding must follow the shared four-runtime authoring
   standard upstream in `UsEquityStrategies`: one shared profile, portable by
   default across `ibkr`, `schwab`, `longbridge`, and `paper_signal`, with no
   platform-local strategy fork in this repository.
4. Paper execution, notification, and state persistence stay local to this
   runtime repo.

## Current scope

This scaffold sets up:

- `paper_signal` platform registry and rollout policy
- shared strategy loading from `UsEquityStrategies`
- paper account-group config contract
- notification/state/execution service boundaries
- richer Telegram notification rendering and local operator inspection helpers
- minimal paper cycles for the currently supported direct-runtime, pure
  feature-snapshot, and hybrid snapshot+history input modes

Current live state of the scaffold:

- shared `paper_signal` adapters now exist upstream in `UsEquityStrategies`
- supported paper profiles follow the shared `runtime_enabled` catalog; no
  platform-local strategy, paper-only strategy fork, or brokerless notifier
  strategy is kept in this repository
- supported input paths include direct runtime inputs, feature snapshots, and
  hybrid snapshot+history inputs built only for shared upstream profiles
- the cycle supports `signal -> next-session pending plan -> simulated execution`
- operator scripts can print current paper account state and preview the latest
  notification from local or GCS artifacts
- operator scripts can also build one daily or weekly summary for stdout or
  Telegram delivery
- operator scripts can build one monthly or incident-oriented review pack from
  reconciliation artifacts for stdout or Telegram delivery
- operator scripts can plan or auto-open narrow incident review runs from
  incident dashboard findings by reusing the shared review-pack artifact flow
- review artifacts stay local so later operator review does not depend on
  transient job logs
- unsupported input modes still return scaffold-only status until their paper cycle
  wiring lands

## Runtime model

- `STRATEGY_PROFILE` selects one shared profile
- `PAPER_ACCOUNT_GROUP` selects one paper account config
- `PaperSignalPlatform` loads the shared entrypoint and runtime adapter
- supported input modes build normalized inputs, evaluate the shared strategy,
  then simulate rebalance/fills locally
- output goes to Telegram + structured artifacts/state, never to a broker

## Shared strategy compatibility

`PaperSignalPlatform` follows the same cross-platform strategy contract as the
three live broker runtimes.

Greenfield strategy authoring should happen once in `UsEquityStrategies` with
structural portability across all four runtimes from day one. The only
platform-local decision is rollout enablement, not strategy math or input
contract shape.

For a strategy to be considered ready here, it should:

1. be defined in `UsEquityStrategies`
2. return a standard `StrategyDecision`
3. declare canonical required inputs
4. expose a `paper_signal` runtime adapter upstream
5. stay portable across `ibkr`, `schwab`, `longbridge`, and `paper_signal`

Until a profile has a `paper_signal` adapter upstream, this runtime should
reject it instead of carrying a platform-local workaround.

## Repository layout

```text
PaperSignalPlatform/
  application/
    cycle_result.py
    notification_renderers.py
    notification_service.py
    operator_incident_dashboard.py
    operator_review_pack.py
    operator_support.py
    operator_summary.py
    paper_execution_service.py
    reconciliation_service.py
    runtime_dependencies.py
    state_store_service.py
  configs/
    paper_account_groups.example.json
  docs/
    architecture.md
  notifications/
    telegram.py
  scripts/
    print_incident_trigger_dashboard.py
    print_operator_review_pack.py
    print_operator_summary.py
    preview_cycle_notification.py
    print_paper_account_state.py
    print_strategy_profile_status.py
  tests/
    test_notification_renderers.py
    test_operator_summary.py
    test_operator_support.py
    test_profile_key_governance.py
    test_runtime_config_support.py
    test_strategy_loader.py
  requirements.txt
  runtime_config_support.py
  strategy_loader.py
  strategy_registry.py
  strategy_runtime.py
```

## Environment variables

| Variable | Required | Notes |
| --- | --- | --- |
| `STRATEGY_PROFILE` | Yes | Shared profile name from `UsEquityStrategies` |
| `PAPER_ACCOUNT_GROUP` | Yes | Selects one paper account group |
| `PAPER_ACCOUNT_GROUP_CONFIG_JSON` | Yes* | Inline paper account config JSON |
| `PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME` | Yes* | Secret Manager alternative to the inline JSON |
| `TELEGRAM_TOKEN` | No | Telegram bot token |
| `GLOBAL_TELEGRAM_CHAT_ID` | No | Default Telegram chat id |
| `NOTIFY_LANG` | No | Default `en` |
| `GOOGLE_CLOUD_PROJECT` | No | Required only when using Secret Manager |
| `PAPER_SIGNAL_STATE_STORE_BACKEND` | No | Default `local_json`; supported: `memory`, `local_json`, `firestore` |
| `PAPER_SIGNAL_ARTIFACT_STORE_BACKEND` | No | Default `local_json`; supported: `local_json`, `gcs` |
| `PAPER_SIGNAL_STATE_DIR` | No | Default repo-local `.paper_signal/state` |
| `PAPER_SIGNAL_ARTIFACT_DIR` | No | Default repo-local `.paper_signal/artifacts` |
| `PAPER_SIGNAL_FIRESTORE_COLLECTION` | No | Default `paper_signal_states` |
| `PAPER_SIGNAL_GCS_BUCKET` | No | Required when artifact backend is `gcs` |
| `PAPER_SIGNAL_MARKET_DATA_PROVIDER` | No | Default `yfinance` |
| `PAPER_SIGNAL_HISTORY_LOOKBACK_DAYS` | No | Default `420` |

\* Provide one of `PAPER_ACCOUNT_GROUP_CONFIG_JSON` or
`PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME`.

## Paper account-group config

Example: [configs/paper_account_groups.example.json](/home/ubuntu/Projects/PaperSignalPlatform/configs/paper_account_groups.example.json)

Each group declares paper-only runtime identity and simulation defaults:

- `service_name`
- `account_alias`
- `base_currency`
- `market_calendar`
- `starting_equity`
- `slippage_bps`
- `commission_bps`
- `fill_model`
- `artifact_bucket_prefix`
- optional `telegram_chat_id`

There is intentionally no broker credential field.
When using `PAPER_SIGNAL_ARTIFACT_STORE_BACKEND=gcs`, `artifact_bucket_prefix`
is treated as the object prefix inside `PAPER_SIGNAL_GCS_BUCKET`.

## Next step

Current tested minimal routes are input-mode routes for shared upstream
profiles. This repository must not own profile-specific strategy code.

The currently wired paper cycles support:

1. run after close
2. queue a next-session paper rebalance
3. execute the queued rebalance on the next run using stored paper state
4. write one reconciliation artifact and emit one notification

Operator tooling now available:

1. `scripts/print_paper_account_state.py` for the latest persisted paper book
2. `scripts/preview_cycle_notification.py` for the latest per-run Telegram body
3. `scripts/print_operator_summary.py` for one daily or weekly cross-book summary
4. `scripts/print_operator_review_pack.py` for one monthly or incident-oriented review pack
5. `scripts/print_incident_trigger_dashboard.py` for one high-signal abnormal-status dashboard before opening an incident review

Next changes should be:

1. keep new profile authoring and research evidence upstream in `UsEquityStrategies`
   and `UsEquitySnapshotPipelines`

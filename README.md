# PaperSignalPlatform

Brokerless paper-trading and signal-notification runtime for shared `us_equity`
strategy profiles.

`PaperSignalPlatform` is a sibling runtime repository to:

- `InteractiveBrokersPlatform`
- `CharlesSchwabPlatform`
- `LongBridgePlatform`

The difference is intentional: this repository must never place real orders.
It owns only:

- runtime entrypoints
- paper-account config parsing
- paper execution contracts
- Telegram/log/artifact transport
- Cloud Run / Scheduler deployment wiring

Strategy semantics stay in `UsEquityStrategies`. Shared contracts stay in
`QuantPlatformKit`.

## Design rules

1. Strategy code must remain platform-agnostic and live in `UsEquityStrategies`.
2. This repository must not contain broker SDKs or real order submitters.
3. New strategy onboarding must add a `paper_signal` runtime adapter upstream in
   `UsEquityStrategies`, not a platform-local strategy implementation here.
4. Paper execution, notification, and state persistence stay local to this
   runtime repo.

## Current scope

This scaffold sets up:

- `paper_signal` platform registry and rollout policy
- shared strategy loading from `UsEquityStrategies`
- paper account-group config contract
- Cloud Run entrypoint scaffold
- notification/state/execution service boundaries
- richer Telegram notification rendering and local operator inspection helpers
- minimal paper cycles for the currently supported direct-runtime, pure
  feature-snapshot, and hybrid snapshot+history input modes

Current live state of the scaffold:

- shared `paper_signal` adapters now exist upstream in `UsEquityStrategies`
- `global_etf_rotation`, `tqqq_growth_income`, and `soxl_soxx_trend_income` can run end-to-end in this repo
- `russell_1000_multi_factor_defensive`, `tech_communication_pullback_enhancement`, and `mega_cap_leader_rotation_top50_balanced` now run through the shared `feature_snapshot` path
- the hybrid `feature_snapshot + market_history + benchmark_history + portfolio_snapshot` route is wired for `dynamic_mega_leveraged_pullback`
- `dynamic_mega_leveraged_pullback` is rollout-enabled in `PaperSignalPlatform` after local validation, while remaining `research_only` in the shared catalog for live broker runtimes
- the cycle supports `signal -> next-session pending plan -> simulated execution`
- operator scripts can print current paper account state and preview the latest
  notification from local or GCS artifacts
- operator scripts can also build one daily or weekly summary for stdout or
  Telegram delivery
- operator scripts can build one monthly or incident-oriented review pack from
  reconciliation artifacts for stdout or Telegram delivery
- unsupported input modes still return scaffold-only status until their paper cycle
  wiring lands

## Runtime model

- `STRATEGY_PROFILE` selects one shared profile
- `PAPER_ACCOUNT_GROUP` selects one paper account config
- `PaperSignalPlatform` loads the shared entrypoint and runtime adapter
- supported input modes build normalized inputs, evaluate the shared strategy,
  then simulate rebalance/fills locally
- output goes to Telegram + structured artifacts/state, never to a broker

## Recommended GCP boundary

If this runtime uses Google Cloud services, it should live in its own dedicated
GCP project instead of sharing the same project with live trading runtimes.

Recommended split:

- one dedicated GCP project for `PaperSignalPlatform`
- `Cloud Run`, `Cloud Scheduler`, `Firestore`, `GCS`, and Telegram secrets live there
- no broker secrets, broker gateways, or live trading IAM roles in that project

That keeps paper signal operations, budgets, logs, IAM, and alerts isolated
from live trading infrastructure.

## Shared strategy compatibility

`PaperSignalPlatform` follows the same cross-platform strategy contract as the
three live broker runtimes.

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
    gcp_deployment.md
  deploy/
    cloud_run_job.env.example
    cloud_run_review_pack_job.env.example
    cloud_run_summary_job.env.example
  entrypoints/
    cloud_run.py
  notifications/
    telegram.py
  scripts/
    deploy_cloud_run_job.sh
    deploy_cloud_scheduler_job.sh
    deploy_operator_review_pack_job.sh
    deploy_operator_review_pack_scheduler.sh
    deploy_operator_summary_job.sh
    deploy_operator_summary_scheduler.sh
    print_operator_review_pack.py
    print_operator_summary.py
    preview_cycle_notification.py
    print_paper_account_state.py
    print_strategy_profile_status.py
  tests/
    test_cloud_run_entrypoint.py
    test_notification_renderers.py
    test_operator_summary.py
    test_operator_support.py
    test_profile_key_governance.py
    test_runtime_config_support.py
    test_strategy_loader.py
  main.py
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

## Deploy shape

Recommended deploy model:

- Cloud Run Job or Cloud Run service
- one deployment per `STRATEGY_PROFILE x PAPER_ACCOUNT_GROUP`
- Cloud Scheduler triggers the run
- use [docs/gcp_deployment.md](/home/ubuntu/Projects/PaperSignalPlatform/docs/gcp_deployment.md) and [deploy/cloud_run_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_job.env.example) as the starting point

The platform remains brokerless even when deployed next to live runtimes.
When Google Cloud is used, prefer a separate paper-only GCP project rather than
reusing the live trading one.

## Next step

Current tested minimal routes:

1. `global_etf_rotation`
2. `tqqq_growth_income`
3. `soxl_soxx_trend_income`
4. `russell_1000_multi_factor_defensive`
5. `tech_communication_pullback_enhancement`
6. `mega_cap_leader_rotation_top50_balanced`
7. `dynamic_mega_leveraged_pullback`

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

Scheduled summary delivery:

1. use [deploy/cloud_run_summary_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_summary_job.env.example) as the template
2. deploy the Cloud Run Job with [scripts/deploy_operator_summary_job.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_operator_summary_job.sh)
3. attach the Scheduler trigger with [scripts/deploy_operator_summary_scheduler.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_operator_summary_scheduler.sh)

Scheduled review-pack delivery:

1. use [deploy/cloud_run_review_pack_job.env.example](/home/ubuntu/Projects/PaperSignalPlatform/deploy/cloud_run_review_pack_job.env.example) as the template
2. deploy the Cloud Run Job with [scripts/deploy_operator_review_pack_job.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_operator_review_pack_job.sh)
3. attach the Scheduler trigger with [scripts/deploy_operator_review_pack_scheduler.sh](/home/ubuntu/Projects/PaperSignalPlatform/scripts/deploy_operator_review_pack_scheduler.sh)

Next changes should be:

1. onboard the remaining shared snapshot profiles that are still research-only in rollout
2. standardize one incident playbook on top of the new review-pack jobs

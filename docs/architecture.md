# PaperSignalPlatform Architecture

## Position in the stack

- `QuantPlatformKit`: shared contracts, shared runtime helpers, shared ports
- `UsEquityStrategies`: shared strategy semantics and runtime adapters
- `PaperSignalPlatform`: brokerless deployment runtime for paper execution,
  Telegram, and artifacts

## What belongs here

- runtime config/env parsing
- paper account identity and simulation parameters
- normalized state store and artifact store ports
- paper execution translation and fill-model ownership
- request orchestration
- final Telegram wording and audit artifacts
- operator summaries and review packs derived from persisted artifacts
- incident trigger dashboards derived from persisted artifacts
- incident action plans that reuse review-pack jobs instead of creating a second
  review implementation path
- isolated paper-only GCP deployment conventions

## What does not belong here

- broker SDK imports
- broker secrets
- real order submission
- platform-local strategy math
- hard-coded symbol pools by profile
- a second private strategy catalog

## Strategy onboarding rule

When adding a new strategy for this platform:

1. add or update the shared profile in `UsEquityStrategies`
2. keep the profile structurally portable across `ibkr`, `schwab`,
   `longbridge`, and `paper_signal` by default
3. add the `paper_signal` runtime adapter upstream alongside the live-runtime
   adapters
4. keep strategy outputs in standard `StrategyDecision` form
5. only then enable the profile here through rollout policy

Do not patch around missing shared adapters by adding a local strategy
implementation in this repository.

Paper-only rollout overrides are allowed when a profile stays
`research_only` in the shared catalog but has been validated locally for this
brokerless runtime. That override must stay local to `PaperSignalPlatform`
instead of changing live broker rollout policy upstream.

## Paper execution rule

The future paper execution service should own:

- position sizing translation from `AllocationIntent`
- simulated fills
- slippage / commission application
- portfolio state transitions
- NAV / drawdown accounting

The shared strategy layer should not know any of those details.

## Current implementation checkpoint

The first concrete paths are now wired for:

- `market_history`
- `benchmark_history + portfolio_snapshot`
- `derived_indicators + portfolio_snapshot`
- `feature_snapshot`
- `feature_snapshot + market_history + benchmark_history + portfolio_snapshot`

Current shared profiles covered by those routes:

- `global_etf_rotation`
- `tqqq_growth_income`
- `soxl_soxx_trend_income`
- `russell_1000_multi_factor_defensive`
- `tech_communication_pullback_enhancement`
- `mega_cap_leader_rotation_dynamic_top20`
- `mega_cap_leader_rotation_aggressive`
- `mega_cap_leader_rotation_top50_balanced`
- `dynamic_mega_leveraged_pullback`

1. load shared entrypoint/runtime adapter
2. fetch daily bars from a brokerless market-data provider
3. evaluate the shared strategy at the close
4. queue a next-session pending paper plan
5. on the next run, execute the queued plan with simulated fills
6. mark the paper account to the close, persist state, write artifacts, publish
   a notification

Other input modes still stay on scaffold-only status until their normalized
paper input builders are implemented, but the main shared snapshot and hybrid
routes are no longer blocked on platform runtime wiring.

`dynamic_mega_leveraged_pullback`, `mega_cap_leader_rotation_dynamic_top20`,
and `mega_cap_leader_rotation_aggressive` are the first paper-only rollout
overrides: they remain `research_only` in `UsEquityStrategies`, but this
runtime enables them locally because the brokerless paper cycle is now covered
by tests.

Durable runtime backends now supported:

- `Firestore` for latest paper-account state
- `GCS` for reconciliation JSON artifacts
- `local_json` remains available for local development and tests
- optional scheduled incident auto-open now reuses the deployed review-pack job
  through Cloud Run Jobs API overrides, so the dashboard, review pack, and
  auto-open path stay on one shared artifact contract

When deploying with Google Cloud, use a dedicated paper-only project instead of
sharing the same project with live broker runtimes. This repo should never need
broker IAM roles or broker secrets.

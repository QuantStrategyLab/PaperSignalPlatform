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

Paper-only rollout overrides should not carry local strategy logic. If a
profile is not ready in the shared catalog, keep the research and validation in
the upstream strategy and snapshot repositories before enabling it here.

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

These are input-mode routes for shared upstream profiles, not local strategy
implementations.

1. load shared entrypoint/runtime adapter
2. fetch daily bars from a brokerless market-data provider
3. evaluate the shared strategy at the close
4. queue a next-session pending paper plan
5. on the next run, execute the queued plan with simulated fills
6. mark the paper account to the close, persist state, write artifacts, publish
   a notification

Other input modes still stay on scaffold-only status until their normalized
paper input builders are implemented. PaperSignal follows the shared
`runtime_enabled` catalog and does not enable local paper-only strategy
overrides.

Durable runtime backends now supported:

- `Firestore` for latest paper-account state
- `GCS` for reconciliation JSON artifacts
- `local_json` remains available for local development and tests
- local review-pack and dashboard flows reuse the same artifact contract

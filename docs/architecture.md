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
2. add a `paper_signal` runtime adapter upstream
3. keep strategy outputs in standard `StrategyDecision` form
4. only then enable the profile here through rollout policy

Do not patch around missing shared adapters by adding a local strategy
implementation in this repository.

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

Current shared profiles covered by those routes:

- `global_etf_rotation`
- `tqqq_growth_income`
- `soxl_soxx_trend_income`

1. load shared entrypoint/runtime adapter
2. fetch daily bars from a brokerless market-data provider
3. evaluate the shared strategy at the close
4. queue a next-session pending paper plan
5. on the next run, execute the queued plan with simulated fills
6. mark the paper account to the close, persist state, write artifacts, publish
   a notification

Other input modes stay on scaffold-only status until their normalized paper
input builders are implemented.

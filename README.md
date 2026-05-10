# PaperSignalPlatform

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

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

---

<a id="中文"></a>
## 中文

`PaperSignalPlatform` 是共享 `us_equity` 策略 profile 的 brokerless paper-trading 和 signal-notification runtime。

它是这些 live broker runtime 的兄弟仓库：

- `InteractiveBrokersPlatform`
- `CharlesSchwabPlatform`
- `LongBridgePlatform`

区别是刻意设计的：这个仓库永远不能真实下单。它只负责：

- paper account 配置解析
- paper execution contract
- Telegram / log / artifact transport
- 本地 operator inspection helpers

策略语义放在 `UsEquityStrategies`，共享 contract 放在 `QuantPlatformKit`。

## 设计规则

1. 策略代码必须保持平台无关，并保留在 `UsEquityStrategies`。
2. 本仓库不能包含 broker SDK 或真实下单器。
3. 新策略接入必须遵循 `UsEquityStrategies` 上游的四 runtime authoring standard：同一个共享 profile 默认可移植到 `ibkr`、`schwab`、`longbridge` 和 `paper_signal`，不在本仓库创建平台本地策略 fork。
4. Paper execution、notification 和 state persistence 留在本 runtime 仓库内。

## 当前范围

这个 scaffold 提供：

- `paper_signal` platform registry 和 rollout policy
- 从 `UsEquityStrategies` 加载共享策略
- paper account-group config contract
- notification / state / execution service boundaries
- 更完整的 Telegram notification rendering 和本地 operator inspection helpers
- 对当前支持的 direct-runtime、pure feature-snapshot、hybrid snapshot+history input modes 执行最小 paper cycle

当前状态：

- 共享 `paper_signal` adapters 已经存在于上游 `UsEquityStrategies`
- 支持的 paper profiles 跟随共享 `runtime_enabled` catalog
- 不保留平台本地策略、paper-only 策略 fork 或 brokerless notifier 策略
- cycle 支持 `signal -> next-session pending plan -> simulated execution`
- operator scripts 可以查看当前 paper account state，并预览本地或 GCS artifacts 中的最新通知
- operator scripts 也可以生成 daily / weekly summary、monthly / incident review pack，以及异常状态 dashboard

## Runtime 模型

- `STRATEGY_PROFILE` 选择一个共享 profile
- `PAPER_ACCOUNT_GROUP` 选择一个 paper account config
- `PaperSignalPlatform` 加载共享 entrypoint 和 runtime adapter
- 支持的 input modes 会构建 normalized inputs，评估共享策略，然后在本地模拟 rebalance / fills
- 输出写到 Telegram、结构化 artifacts 和 state，永远不发送给 broker

## 共享策略兼容性

`PaperSignalPlatform` 遵循和三个 live broker runtimes 相同的 cross-platform strategy contract。

一个策略要在这里被视为 ready，应满足：

1. 在 `UsEquityStrategies` 中定义
2. 返回标准 `StrategyDecision`
3. 声明 canonical required inputs
4. 在上游暴露 `paper_signal` runtime adapter
5. 保持可移植到 `ibkr`、`schwab`、`longbridge` 和 `paper_signal`

如果某个 profile 还没有上游 `paper_signal` adapter，本 runtime 应拒绝它，而不是在本仓库维护平台本地 workaround。

## 环境变量

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `STRATEGY_PROFILE` | 是 | 来自 `UsEquityStrategies` 的共享 profile 名 |
| `PAPER_ACCOUNT_GROUP` | 是 | 选择一个 paper account group |
| `PAPER_ACCOUNT_GROUP_CONFIG_JSON` | 是* | 内联 paper account config JSON |
| `PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME` | 是* | Secret Manager 形式的替代配置来源 |
| `TELEGRAM_TOKEN` | 否 | Telegram bot token |
| `GLOBAL_TELEGRAM_CHAT_ID` | 否 | 默认 Telegram chat id |
| `NOTIFY_LANG` | 否 | 默认 `en` |
| `GOOGLE_CLOUD_PROJECT` | 否 | 仅使用 Secret Manager 时需要 |
| `PAPER_SIGNAL_STATE_STORE_BACKEND` | 否 | 默认 `local_json`；支持 `memory`、`local_json`、`firestore` |
| `PAPER_SIGNAL_ARTIFACT_STORE_BACKEND` | 否 | 默认 `local_json`；支持 `local_json`、`gcs` |
| `PAPER_SIGNAL_MARKET_DATA_PROVIDER` | 否 | 默认 `yfinance` |

\* `PAPER_ACCOUNT_GROUP_CONFIG_JSON` 和 `PAPER_ACCOUNT_GROUP_CONFIG_SECRET_NAME` 二选一。

## 下一步

当前已测试的最小路径是共享上游 profile 的 input-mode route。本仓库不应拥有 profile-specific strategy code。

已接线的 paper cycles 支持：

1. 收盘后运行
2. 排队 next-session paper rebalance
3. 下一次运行时使用持久化 paper state 执行 queued rebalance
4. 写出 reconciliation artifact 并发送一条通知

后续 profile authoring 和 research evidence 应继续放在 `UsEquityStrategies` 和 `UsEquitySnapshotPipelines` 上游。

# Paper Signal Notifier Pattern (COIN Example)

This is a decoupled brokerless notifier path for the `COIN` short-hold
dual-direction `vt_50` signal. It is also the reference pattern for paper-signal
Cloud Run jobs that host non-IBKR strategy signals.

Code structure:

- generic notifier core: `signal_notifier/signal_notifier_core.py`
- COIN market-data + message adapter: `signal_notifier/coin_short_hold_notify.py`
- strategy-specific entry script: `scripts/send_coin_short_hold_signal.py`

Recommended deployment boundary:

- keep brokerless notifier jobs in `PaperSignalPlatform`, not in IBKR runtime
- keep a separate Telegram bot token for this project
- store state and snapshots in GCS so duplicate suppression works across runs
- deploy each strategy as its own Cloud Run Job in the same project

It does not depend on:

- IBKR connectivity
- account-group config
- broker execution
- the Cloud Run trading runtime
- the platform `notifications.telegram` module

It only:

1. downloads `COIN`, `BTC`, `CONL`, and `CONI` daily closes
2. computes the next-session signal
3. prints the message
4. optionally sends Telegram
5. optionally writes a JSON snapshot

## Script

Use:

```bash
python3 scripts/send_coin_short_hold_signal.py --stdout-only
```

Or send to Telegram:

```bash
export COIN_NOTIFY_TELEGRAM_TOKEN=...
export COIN_NOTIFY_TELEGRAM_CHAT_ID=...
python3 scripts/send_coin_short_hold_signal.py
```

## Optional env vars

- `COIN_NOTIFY_TELEGRAM_TOKEN`
- `COIN_NOTIFY_TELEGRAM_CHAT_ID`
- `COIN_NOTIFY_LANG`
- `COIN_NOTIFY_OUTPUT_PATH`
- `COIN_NOTIFY_STATE_PATH`

Fallbacks are supported:

- token: `TELEGRAM_TOKEN`
- chat id: `GLOBAL_TELEGRAM_CHAT_ID` or `TELEGRAM_CHAT_ID`
- lang: `NOTIFY_LANG`

## Example JSON snapshot

```bash
python3 scripts/send_coin_short_hold_signal.py \
  --json-out /tmp/coin_signal.json \
  --stdout-only
```

## Stateful scheduling

For a daily cron or Cloud Run Job, keep a state file so duplicate signals do not
spam Telegram:

```bash
python3 scripts/send_coin_short_hold_signal.py \
  --state-file /var/tmp/coin_signal_state.json \
  --skip-unchanged
```

Behavior:

- the current snapshot is always written to `--state-file`
- Telegram is skipped when the signal identity has not changed
- use `--force-send` to override that suppression

`--state-file` and `--json-out` both support local paths and `gs://...` URIs.

Example with GCS:

```bash
python3 scripts/send_coin_short_hold_signal.py \
  --state-file gs://papersignalquant-signal-artifacts/paper-signal/coin-short-hold/state.json \
  --json-out gs://papersignalquant-signal-artifacts/paper-signal/coin-short-hold/latest.json \
  --skip-unchanged
```

## Timing

Run the deployed reminder 15 minutes before the regular U.S. equity close:
`45 15 * * 1-5` in `America/New_York`. This keeps the schedule aligned with
U.S. daylight saving time. Cloud Scheduler fixed cron does not account for
early-close market days.

If you need a fully final end-of-day signal instead of a pre-close reminder,
run it after the U.S. equity close. The signal is intended for the next trading
session.

## Cloud Run Job

Use the generic notify-only deployment scripts:

```bash
./scripts/deploy_signal_notifier_job.sh deploy/signal_notifier_job.env.example
./scripts/deploy_signal_notifier_scheduler.sh deploy/signal_notifier_job.env.example
```

For image builds, prefer:

```bash
./scripts/build_signal_notifier_image.sh deploy/signal_notifier_job.env.example
./scripts/deploy_signal_notifier_job.sh deploy/signal_notifier_job.env.example
```

The deployment scripts are reusable for other notify-only strategies. For a new
job, copy the env file and update at least:

- `JOB_NAME`
- `SCHEDULER_JOB_NAME`
- `IMAGE`
- `SCRIPT_PATH`
- `STATE_URI`
- `SNAPSHOT_URI`

Optional:

- `EXTRA_COPY_PATHS` in the build env if a notifier needs extra local modules
- `TELEGRAM_TOKEN_SECRET_NAME` once the dedicated notify-only bot is ready

Recommended rollout:

1. start with `STDOUT_ONLY=true`
2. verify state and snapshot JSON appear in GCS
3. create a dedicated notify-only Telegram bot
4. store the bot token in Secret Manager
5. set `TELEGRAM_TOKEN_SECRET_NAME` and `SIGNAL_NOTIFY_TELEGRAM_CHAT_ID`
6. switch `STDOUT_ONLY=false`

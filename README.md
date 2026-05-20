# Volume Scanner

Nifty / BankNifty ATM CE/PE options volume alert scanner. Polls Shoonya
(Finvasia) via NorenRestApiPy with daily OAuth, detects volume bursts,
spikes, and consecutive-candle patterns, and pushes Telegram alerts.

**Doesn't trade.** Alert-only, no broker order placement.

## What it detects

- Single-bar volume bursts at 3x / 5x / 10x / 15x / 20x average
- Multi-bar consecutive spikes (momentum)
- Volume compression (drying up — preceded breakouts)
- Recovery patterns (return to normal after a spike)

Each alert includes the pattern type, magnitude ratio, severity, RSI zone and
slope, and a setup-context summary.

## Repo layout

```
nifty_volume_alert_scanner_advanced.py   Main scanner script
nifty_scanner.service                    systemd unit (Ubuntu 22.04)
MIGRATION_VPS.md                         Migrate /opt/Volumebot → /opt/volume_scanner
dashboard_client.py                      Heartbeat/log_trade/log_error to shared SQLite
*.txt / *.md guides                      User-authored docs (config, alerts, setup)
```

## Quick start (VPS)

```bash
sudo git clone https://github.com/jignesh1707/volume_scanner.git /opt/volume_scanner
sudo useradd --system --shell /bin/bash trading 2>/dev/null || true
sudo apt-get install -y python3-pip
sudo pip3 install -r /opt/volume_scanner/requirements.txt
sudo -u trading nano /opt/volume_scanner/.env       # see .env.example for the 5 SHOONYA_* keys
sudo -u trading bash -c 'cd /opt/volume_scanner && python3 login_shoonya.py'   # daily; prompts for 6-digit TOTP
sudo cp /opt/volume_scanner/nifty_scanner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nifty_scanner
sudo journalctl -u nifty_scanner -f
```

> Shoonya tokens expire EOD — rerun `login_shoonya.py` and restart the
> service each morning. See [`MIGRATION_VPS.md`](MIGRATION_VPS.md) § 8.

If migrating from an existing `/opt/Volumebot` install, follow
[`MIGRATION_VPS.md`](MIGRATION_VPS.md) instead.

## Part of a 4-bot stack

Designed to coexist on the VPS with:
- [TickRenko](https://github.com/jignesh1707/TickRenko)
- [volumebot](https://github.com/jignesh1707/volumebot)
- [sl_hunter_bot](https://github.com/jignesh1707/sl_hunter_bot)

The scanner heartbeats to the shared dashboard at `/opt/shared/dashboard.db`
so its alert count and live status show up on Telegram alongside the other
three bots.

## Telegram channel

Alerts go to the channel configured by `telegram_bot_token` /
`telegram_chat_id` inside the script. SMS support is stubbed but not enabled.

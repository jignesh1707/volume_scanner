# Volume Scanner — VPS Migration: /opt/Volumebot → /opt/volume_scanner

The Nifty Volume Scanner currently lives at `/opt/Volumebot` on the VPS, which
collides with the **VolumeBot** install at `/opt/volumebot` (case-sensitive
but visually confusing). This doc moves it to `/opt/volume_scanner` and
applies the hardened systemd unit.

> **2026-05-19 update:** broker layer rewritten to use NorenRestApiPy with
> April-2026 OAuth. Daily morning login via `python login_shoonya.py` is now
> required — see § 8 below.

Run all steps **as root on the VPS**.

---

## 1. Snapshot the current state

```bash
sudo systemctl status nifty_scanner       # confirm it's currently running
ls -ld /opt/Volumebot                     # confirm the source path
journalctl -u nifty_scanner -n 30 --no-pager
```

If anything looks unfamiliar, stop and investigate before continuing.

## 2. Stop the service

```bash
sudo systemctl stop nifty_scanner
```

## 3. Move the install directory

```bash
sudo mv /opt/Volumebot /opt/volume_scanner
```

If you keep state under `/opt/Volumebot/state/` or similar, the `mv` preserves
everything (inodes intact, just renamed).

## 4. Reinstall the systemd unit

The unit file under the repo now points at `/opt/volume_scanner` and adds
hardening (`ProtectSystem=strict`, `ReadWritePaths`, etc.). Copy it in:

```bash
sudo cp /opt/volume_scanner/nifty_scanner.service /etc/systemd/system/nifty_scanner.service
sudo systemctl daemon-reload
```

## 5. Verify file ownership and log file

The script writes `/var/log/nifty_volume_alerts.log`. Make sure the `trading`
user can write to it:

```bash
sudo touch /var/log/nifty_volume_alerts.log
sudo chown trading:trading /var/log/nifty_volume_alerts.log
sudo chmod 0640 /var/log/nifty_volume_alerts.log
```

(If the file already exists from the old install, just re-chown.)

## 6. Start and follow logs

```bash
sudo systemctl start nifty_scanner
sudo systemctl status nifty_scanner
sudo journalctl -u nifty_scanner -f
```

You should see the scanner reconnect to its data source and resume sending
Telegram alerts. If you get `Permission denied` errors on the log file,
re-check step 5 — the new `ProtectSystem=strict` may be biting.

## 7. Clean-up

After a day of healthy operation, you can safely remove the old service
file if any remnant is left:

```bash
ls -l /etc/systemd/system/nifty_scanner.service   # confirm it points at the new path
```

## 8. Daily Shoonya login (required each morning)

Shoonya susertokens expire EOD. Before market open, run the interactive
helper:

```bash
sudo -u trading bash -c 'cd /opt/volume_scanner && python3 login_shoonya.py'
sudo systemctl restart nifty_scanner
```

The helper writes `session_scanner.json` next to the script. The scanner
loads that file at startup; if it's missing or stale, the service falls
back to `SHOONYA_AUTH_CODE` in `.env` for a one-shot GenAcsTok exchange.

Required `.env` vars (in `/opt/volume_scanner/.env`):

```
SHOONYA_USER=...
SHOONYA_APIKEY=...
# Optional — only used if session_scanner.json is missing/stale:
SHOONYA_AUTH_CODE=
```

Install the new pip dependency once:

```bash
sudo -u trading pip install --user NorenRestApiPy
```

## 9. ATM symbol upkeep

`CONFIG['symbols']` in `nifty_volume_alert_scanner_advanced.py` is hardcoded
to a specific weekly expiry + strike (Shoonya format
`<NAME><DD><MMM><YY><C|P><STRIKE>`, exchange `NFO`). Update the strike each
Monday and the expiry each week. If the symbol doesn't exactly match the
Shoonya master, the scanner logs a `searchscrip` warning and uses the first
fuzzy hit — fix the entry when you see that warning.

---

## Rollback (if something breaks)

```bash
sudo systemctl stop nifty_scanner
sudo mv /opt/volume_scanner /opt/Volumebot
# Restore the previous systemd unit content (git history of nifty_scanner.service)
sudo systemctl daemon-reload
sudo systemctl start nifty_scanner
```

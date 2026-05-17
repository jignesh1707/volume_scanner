# Volume Scanner — VPS Migration: /opt/Volumebot → /opt/volume_scanner

The Nifty Volume Scanner currently lives at `/opt/Volumebot` on the VPS, which
collides with the **VolumeBot** install at `/opt/volumebot` (case-sensitive
but visually confusing). This doc moves it to `/opt/volume_scanner` and
applies the hardened systemd unit.

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

---

## Rollback (if something breaks)

```bash
sudo systemctl stop nifty_scanner
sudo mv /opt/volume_scanner /opt/Volumebot
# Restore the previous systemd unit content (git history of nifty_scanner.service)
sudo systemctl daemon-reload
sudo systemctl start nifty_scanner
```

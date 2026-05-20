# Sound Alerts for Trading Volume Scanner

Add audio alert files here for different severity levels. The scanner will play these sounds when alerts are triggered.

## Required Files

Place these sound files in this directory:

| Severity | Filename | Purpose | Recommended Type |
|----------|----------|---------|------------------|
| EXTREME | `siren_extreme.wav` | Loud siren for extreme alerts | WAV or MP3 |
| LARGE | `alarm_large.wav` | Loud alarm for large alerts | WAV or MP3 |
| MEDIUM | `alert_medium.mp3` | Medium alert tone | WAV or MP3 |
| SMALL | `ding_small.mp3` | Soft ding for small alerts | WAV or MP3 |

## Where to Find Sound Files

### Free Options:
1. **Freesound.org** — Search for "siren", "alarm", "alert"
   - Filter by Creative Commons (free to use)
   - Download as MP3 or WAV

2. **Zapsplat.com** — Royalty-free sound effects
   - Search: "siren", "alert", "alarm", "notification"

3. **Pixabay.com/sounds** — Free to use sounds
   - Search: "alert siren"

4. **Windows Built-in** — Use existing system sounds:
   - `C:\Windows\Media\` (system alert sounds)
   - Or use `Alarm01.wav`, `Alarm02.wav`, etc.

### Recommended Downloads:
- **Siren**: Search "police siren" or "alarm siren" on Freesound
- **Alarm**: Search "loud alarm" or "emergency alarm"
- **Alert**: Search "notification beep" or "alert tone"
- **Ding**: Search "notification ding" or "bell sound"

## Audio Format Support

- ✅ WAV (Recommended on Windows)
- ✅ MP3 (Works on all platforms)
- ✅ OGG, FLAC (Linux/Mac)

Keep files under 500KB for fast loading.

## Testing Sounds

The scanner will test all sounds when it starts. Check the log file:
```
nifty_alerts_notifications.log
```

If a sound file is missing, the scanner will log a warning but continue running.

## Controlling Sound Playback

Edit `advanced_notifications.py` to:
- **Disable sounds**: Set `'enabled': False` in the `'sound'` config
- **Change volume**: Adjust `volume_extreme`, `volume_large`, etc. (note: actual volume control depends on OS)
- **Change files**: Update the `'sounds'` dict with new file paths

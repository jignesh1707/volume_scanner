# Nifty Volume Alert Scanner — File Structure

## Project Layout on Your VPS

```
/opt/nifty_scanner/                          ← main project folder on VPS
│
├── nifty_volume_alert_scanner_advanced.py   ← THE BRAIN  (scanner)
├── advanced_notifications.py               ← THE MOUTH  (alerts)
│
├── sounds/                                 ← sound files for VPS audio
│   ├── siren_extreme.wav                   ← plays on 20x+ spike
│   ├── alarm_large.wav                     ← plays on 10x–20x spike
│   ├── alert_medium.wav                    ← plays on 5x–10x spike
│   └── ding_small.wav                      ← plays on 3x–5x spike
│
└── (runtime files — never edit these)
    └── __pycache__/                        ← Python auto-generated, ignore

/etc/systemd/system/
└── nifty_scanner.service                   ← makes scanner run as daemon

/var/log/nifty_scanner/
└── nifty_volume_alerts.log                 ← live log file
```

---

## What Each File Does

### `nifty_volume_alert_scanner_advanced.py`

The main scanner. Runs every 30 seconds, fetches 1-min candles from
Finvasia, computes volume against a 50-candle rolling baseline, detects
spikes and patterns, then calls the notification system.

**Classes and functions inside it:**

```
CONFIG  (dict)
│   All tunable parameters — broker credentials, symbols,
│   volume thresholds, scan interval, debug flag.
│   THIS is what you edit for day-to-day changes.
│
AdvancedVolumeTracker  (class)
│   One instance per symbol (NIFTY_CALL, NIFTY_PUT, etc).
│   Holds rolling history of volume, RSI, price in deques.
│
│   add_candle()           ← called every scan cycle, stores new data
│   get_avg_volume()       ← returns average of last 50 candles (baseline)
│   get_current_volume()   ← latest candle volume
│   get_avg_rsi()          ← average RSI over stored history
│   get_current_rsi()      ← latest RSI value
│   get_current_price()    ← latest close price
│   analyze_volume_spike() ← main logic: computes ratio, severity, pattern
│   detect_pattern()       ← classifies BURST / MOMENTUM / SURGE / RECOVERY / COMPRESSION
│   generate_description() ← builds the human-readable alert headline
│   should_alert()         ← enforces 5-min cooldown to prevent spam
│
BrokerAPI  (class)
│   Talks to Finvasia (Shoonya) REST API.
│
│   fetch_intraday_data()  ← fetches 1-min candles, last 5 hours
│   get_ltp()              ← gets live price and volume for a symbol
│
calculate_rsi()  (function)
│   Standard Wilder RSI, 14-period by default.
│
send_telegram_alert()  (function)
│   Legacy single-channel sender. Kept for fallback.
│   Replaced by advanced_notifications.py when integrated.
│
format_detailed_alert()  (function)
│   Builds the Telegram message string.
│   Replaced by advanced_notifications.py when integrated.
│
AdvancedVolumeScanner  (class)
    Orchestrator. Creates one tracker per symbol, runs the scan loop.
│
│   initialize_trackers()  ← creates NIFTY_CALL, NIFTY_PUT, etc trackers
│   scan_symbol()          ← fetches data, runs analysis, fires alert
│   run()                  ← infinite loop, calls scan_symbol every 30s
```

---

### `advanced_notifications.py`

The notification router. Takes an alert from the scanner and sends it
to the right Telegram channel based on volume severity, plus plays a
sound and shows a desktop popup.

**Classes and functions inside it:**

```
NOTIFICATION_CONFIG  (dict)
│   Telegram bot token, 4 channel IDs, sound file paths,
│   Discord webhooks (optional), email settings (optional).
│   THIS is what you edit to set up your Telegram channels.
│
TelegramNotifier  (class)
│   Sends to the correct channel based on severity label.
│   EXTREME → channel 1,  LARGE → channel 2,  etc.
│   send_alert()
│
DiscordNotifier  (class)
│   Optional. Sends colour-coded embeds to Discord webhooks.
│   send_alert()
│
SystemNotifier  (class)
│   Linux notify-send desktop popups. Critical level for EXTREME/LARGE.
│   send_alert()
│
SoundNotifier  (class)
│   Plays wav/mp3 files via paplay (PulseAudio) or aplay (ALSA).
│   Non-blocking — uses subprocess.Popen so scanner doesn't pause.
│   play_sound()
│
EmailNotifier  (class)
│   Gmail SMTP. Fires only on EXTREME by default.
│   send_alert()
│
NotificationManager  (class)
│   Calls all four notifiers in sequence for every alert.
│   send_multi_channel_alert()
│
determine_severity()  (function)
│   Maps volume ratio → severity label.
│   ⚠️  BUG IN CURRENT CODE: fix pattern_boosts (0 → 1.0) — see guide.
│
│   3x–5x   →  SMALL
│   5x–10x  →  MEDIUM
│   10x–20x →  LARGE
│   20x+    →  EXTREME
│
send_volume_alert()  (function)
    Integration entry point. The scanner calls this once per alert.
    Builds message, calls NotificationManager.
```

---

### `nifty_scanner.service`

Systemd unit file. Tells Linux to run the scanner as a background
daemon, restart it if it crashes, and start it automatically on reboot.

---

### Sound Files (`sounds/`)

Plain audio files. You download these yourself from mixkit.co or
freesound.org. The scanner doesn't generate them.

| File | Plays when |
|---|---|
| `siren_extreme.wav` | Volume ratio ≥ 20x |
| `alarm_large.wav` | Volume ratio 10x–20x |
| `alert_medium.wav` | Volume ratio 5x–10x |
| `ding_small.wav` | Volume ratio 3x–5x |

---

### Docs folder (on your local machine / GitHub)

```
docs/
├── HOW_TO_IMPLEMENT_AND_USE.md   ← full setup + usage guide
├── FILE_STRUCTURE.md             ← this file
├── ALERT_CONDITIONS_GUIDE.txt    ← what each pattern means
├── ADVANCED_CONFIG_GUIDE.txt     ← how to tune thresholds
├── TELEGRAM_SETUP.txt            ← step-by-step Telegram channel setup
├── BROKER_TOKEN_GUIDE.txt        ← how to find option token IDs
└── MULTI_CHANNEL_ALERTS_SETUP.txt ← sound + desktop notification setup
```

---

## What You Edit and How Often

| File | What you change | How often |
|---|---|---|
| `nifty_volume_alert_scanner_advanced.py` | ATM symbol strings (call/put) | Monthly at expiry rollover |
| `nifty_volume_alert_scanner_advanced.py` | `scan_interval_sec`, thresholds | When tuning |
| `advanced_notifications.py` | Channel IDs, bot token | Once at setup |
| `advanced_notifications.py` | `pattern_boosts` bug fix (0 → 1.0) | Once |
| Sound files | Download new ones if you want different sounds | Rarely |

**Never edit:** `calculate_rsi()`, the deque sizes, broker endpoint URLs.

---

## Data Flow (How It All Connects)

```
Finvasia API
    │
    │  1-min candles (last 5 hours, ~300 candles)
    ▼
fetch_intraday_data()
    │
    │  latest candle: timestamp, close, volume
    ▼
AdvancedVolumeTracker.add_candle()
    │
    ├── get_avg_volume()   → average of previous 50 candles (baseline)
    ├── calculate_rsi()    → RSI from last 20 closes
    ├── detect_pattern()   → BURST / MOMENTUM / SURGE / RECOVERY / COMPRESSION
    └── analyze_volume_spike() → ratio, severity, description
    │
    │  if spike_detected AND cooldown passed
    ▼
send_volume_alert()   ←  in advanced_notifications.py
    │
    ├── determine_severity()  →  SMALL / MEDIUM / LARGE / EXTREME
    │
    ├── TelegramNotifier  →  correct channel for that severity
    ├── SoundNotifier     →  correct wav file for that severity
    ├── SystemNotifier    →  desktop popup
    ├── EmailNotifier     →  gmail (EXTREME only, if enabled)
    └── DiscordNotifier   →  webhook (if enabled)
```

---
---

# How to Push This to GitHub

## First Time — Create the Repo and Push

### Step 1 — Install Git on your local machine (if not already)

On Ubuntu/Debian:
```bash
sudo apt-get install git
```

On Windows: download from https://git-scm.com/download/win

On macOS:
```bash
xcode-select --install
```

Check it works:
```bash
git --version
```

---

### Step 2 — Create a GitHub account and new repo

1. Go to https://github.com and sign in (or create account)
2. Click the **+** button top right → **New repository**
3. Fill in:
   - Repository name: `nifty-volume-scanner`
   - Description: `ATM Nifty options volume alert scanner with multi-channel Telegram notifications`
   - Set to **Private** (your broker credentials will be in here — keep it private)
   - Do NOT tick "Add a README" — you already have one
4. Click **Create repository**
5. GitHub shows you a page with setup commands. Keep this tab open.

---

### Step 3 — Set up your local project folder

On your local machine (laptop/desktop, NOT the VPS):

```bash
# Create folder
mkdir nifty-volume-scanner
cd nifty-volume-scanner

# Copy your files into this folder
# (adjust paths to wherever you downloaded them)
cp ~/Downloads/nifty_volume_alert_scanner_advanced.py .
cp ~/Downloads/advanced_notifications.py .
cp ~/Downloads/nifty_scanner.service .
cp ~/Downloads/HOW_TO_IMPLEMENT_AND_USE.md .
cp ~/Downloads/FILE_STRUCTURE.md .

# Create docs folder and move guides there
mkdir docs
mv HOW_TO_IMPLEMENT_AND_USE.md docs/
mv FILE_STRUCTURE.md docs/
cp ~/Downloads/ALERT_CONDITIONS_GUIDE.txt docs/
cp ~/Downloads/TELEGRAM_SETUP.txt docs/
cp ~/Downloads/BROKER_TOKEN_GUIDE.txt docs/
cp ~/Downloads/ADVANCED_CONFIG_GUIDE.txt docs/
cp ~/Downloads/MULTI_CHANNEL_ALERTS_SETUP.txt docs/
```

---

### Step 4 — Create a .gitignore file

This stops you accidentally pushing your API keys or log files.

```bash
nano .gitignore
```

Paste this exactly:

```
# Never push credentials — configure these directly on VPS
*.env
.env

# Python cache
__pycache__/
*.pyc
*.pyo

# Log files
*.log
/var/log/

# Sound files (too large for git, download separately)
sounds/

# OS files
.DS_Store
Thumbs.db

# IDE files
.vscode/
.idea/
```

Save: Ctrl+O, Enter, Ctrl+X

---

### Step 5 — IMPORTANT: Scrub credentials before pushing

Open both Python files and replace your real credentials with placeholders:

In `nifty_volume_alert_scanner_advanced.py`:
```python
'broker_api_key': 'YOUR_FINVASIA_API_KEY',     # ← placeholder
'broker_token':   'YOUR_FINVASIA_TOKEN',         # ← placeholder
'telegram_bot_token': 'YOUR_TELEGRAM_BOT_TOKEN', # ← placeholder
'telegram_chat_id':   'YOUR_TELEGRAM_CHAT_ID',   # ← placeholder
```

In `advanced_notifications.py`:
```python
'bot_token': 'YOUR_TELEGRAM_BOT_TOKEN',          # ← placeholder
'EXTREME': { 'chat_id': 'YOUR_EXTREME_CHANNEL_ID' },
'LARGE':   { 'chat_id': 'YOUR_LARGE_CHANNEL_ID'  },
'MEDIUM':  { 'chat_id': 'YOUR_MEDIUM_CHANNEL_ID' },
'SMALL':   { 'chat_id': 'YOUR_SMALL_CHANNEL_ID'  },
```

Your real credentials stay only on the VPS. Never in GitHub.

---

### Step 6 — Initialise Git and make first commit

```bash
# Inside your nifty-volume-scanner folder:

git init
git add .
git status    # shows all files that will be committed — check this carefully
```

Make sure `.env` files and `*.log` files are NOT listed. If they are,
check your `.gitignore`.

```bash
git commit -m "Initial commit — Nifty volume alert scanner"
```

---

### Step 7 — Connect to GitHub and push

Copy the commands GitHub showed you after creating the repo. They look like:

```bash
git remote add origin https://github.com/YOUR_USERNAME/nifty-volume-scanner.git
git branch -M main
git push -u origin main
```

Run those three lines. GitHub asks for your username and password.

**Note:** GitHub no longer accepts your account password for git push.
You need a Personal Access Token instead:
1. GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click Generate new token
3. Give it a name, set expiry (90 days is fine), tick **repo** scope
4. Copy the token — it looks like `ghp_xxxxxxxxxxxxxxxx`
5. Use this token as your "password" when git asks

---

### Step 8 — Verify it uploaded

Go to `https://github.com/YOUR_USERNAME/nifty-volume-scanner`

You should see your files. Check that no real API keys or channel IDs
appear anywhere in the code.

---

## Day-to-Day — Pushing Updates

After you make any change to the code:

```bash
cd nifty-volume-scanner

git add .
git commit -m "describe what you changed"
git push
```

Examples of good commit messages:
```
git commit -m "Fix severity bug — change pattern_boosts 0 to 1.0"
git commit -m "Switch to 1-min candles with 50-min baseline"
git commit -m "Update NIFTY symbols to June expiry"
git commit -m "Add RSI slope detection to alert message"
```

---

## Pulling Updates to Your VPS

After pushing from your laptop, pull the changes onto the VPS:

```bash
ssh user@YOUR_VPS_IP
cd /opt/nifty_scanner

# First time only — link VPS folder to GitHub
git init
git remote add origin https://github.com/YOUR_USERNAME/nifty-volume-scanner.git
git pull origin main

# After first time — just run this
git pull
sudo systemctl restart nifty_scanner
```

This keeps your VPS always in sync with GitHub.

---

## Repo Structure That Will Appear on GitHub

```
nifty-volume-scanner/
│
├── nifty_volume_alert_scanner_advanced.py   ← main scanner
├── advanced_notifications.py               ← notification system
├── nifty_scanner.service                   ← systemd service file
├── .gitignore                              ← protects credentials
│
└── docs/
    ├── HOW_TO_IMPLEMENT_AND_USE.md
    ├── FILE_STRUCTURE.md
    ├── ALERT_CONDITIONS_GUIDE.txt
    ├── TELEGRAM_SETUP.txt
    ├── BROKER_TOKEN_GUIDE.txt
    ├── ADVANCED_CONFIG_GUIDE.txt
    └── MULTI_CHANNEL_ALERTS_SETUP.txt
```

---

## Security Checklist Before Every Push

Run this command to search for any real credentials accidentally left in:

```bash
grep -r "YOUR_" . --include="*.py"   # should show placeholders only
grep -rE "[0-9]{9,10}:" . --include="*.py"   # looks for bot token patterns
grep -r "\-100" . --include="*.py"   # looks for channel IDs
```

If any of those return real values, fix them before pushing.

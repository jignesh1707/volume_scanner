
NIFTY VOLUME ALERT SCANNER
HOW TO IMPLEMENT & HOW TO USE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Written for Jack — assumes you have a Linux VPS (Ubuntu 20+) and a Finvasia
(Shoonya) trading account. Read this top to bottom once. Then follow the
numbered steps.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 0  —  HOW THE WHOLE THING WORKS (READ FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Two Python files. That's the whole system.

  nifty_volume_alert_scanner_advanced.py   ← the brain
  advanced_notifications.py               ← the mouth

The scanner fetches 1-min candles for your ATM CE and PE every 30 seconds
from Finvasia. It compares the latest candle's volume against the rolling
average of the previous 50 candles (= last 50 minutes). When it finds a
spike, it classifies it:

  3x–5x  average  →  SMALL   →  📊 channel
  5x–10x average  →  MEDIUM  →  ⚡ channel
  10x–20x average →  LARGE   →  ⚠️ channel
  20x+    average →  EXTREME →  🚨 channel

Each category goes to a different Telegram channel with a different
notification sound on your phone. That's the core idea.

The scanner also detects these patterns inside the spike:
  BURST              → volume spike in exactly ONE candle
  MOMENTUM_2/3       → 2 or 3 consecutive elevated candles
  CONSECUTIVE_SURGE  → 3+ candles sustained above 2x average
  RECOVERY           → volume returned to normal after a spike
  COMPRESSION        → volume drying up below 70% of average

Pattern is shown inside the alert message. It does NOT change which channel
the alert goes to — only the raw volume ratio does that.

NOTE: There is a known bug in the current code where BURST, RECOVERY, and
COMPRESSION alerts always go to SMALL channel regardless of size. This is
because the severity multiplier uses 0 instead of 1.0 for those patterns.
Step 3 of this guide fixes it with one line.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1  —  ONE-TIME SETUP  (DO THIS ONCE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STEP 1  —  VPS PREPARATION
───────────────────────────

SSH into your VPS. Run these once:

  sudo apt-get update
  sudo apt-get install -y python3 python3-pip libnotify-bin pulseaudio
  pip3 install requests
  sudo mkdir -p /opt/nifty_scanner/sounds
  sudo mkdir -p /var/log/nifty_scanner
  sudo useradd -m -s /bin/bash trading
  sudo chown -R trading:trading /opt/nifty_scanner
  sudo chown -R trading:trading /var/log/nifty_scanner

Copy your two Python files to the VPS:

  scp nifty_volume_alert_scanner_advanced.py user@YOUR_VPS_IP:/opt/nifty_scanner/
  scp advanced_notifications.py              user@YOUR_VPS_IP:/opt/nifty_scanner/


STEP 2  —  TELEGRAM: CREATE 4 CHANNELS + 1 BOT
────────────────────────────────────────────────

You need one bot and four channels.

  A. Create the bot
     ───────────────
     Open Telegram → search @BotFather → send /newbot
     Give it any name, e.g. "NiftyVolumeBot"
     Copy the token it gives you. Looks like:
       7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     Save this. You will use it in both Python files.

  B. Create 4 channels
     ──────────────────
     In Telegram (phone or desktop):
       New Channel → name it → set Private
     
     Create these 4 channels with these exact names (you can rename later):
       NIFTY_SMALL      ← for 3x–5x volume spikes
       NIFTY_MEDIUM     ← for 5x–10x volume spikes
       NIFTY_LARGE      ← for 10x–20x volume spikes
       NIFTY_EXTREME    ← for 20x+ volume spikes

  C. Add the bot to each channel as admin
     ─────────────────────────────────────
     Open each channel → tap the channel name at top → Administrators
     → Add Administrator → search your bot name → add it
     Give it "Post Messages" permission. That's all it needs.

  D. Get each channel's Chat ID
     ───────────────────────────
     Do this for each of the 4 channels:
       1. Send any message inside the channel (e.g. "test")
       2. Open a browser and go to:
            https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
          Replace <YOUR_BOT_TOKEN> with your actual token.
       3. Look for "chat":{"id": in the JSON.
          Channel IDs always start with -100, e.g. -1001234567890
       4. Write it down.

     If getUpdates shows nothing, forward the channel message to your bot
     first, then try again.

  E. Get YOUR personal chat ID (for testing)
     ─────────────────────────────────────────
     Send any message to your bot directly (not a channel, your personal chat).
     Same getUpdates URL. Find the "chat":{"id": that does NOT start with -100.
     That's your personal ID.


STEP 3  —  FIX THE SEVERITY BUG (ONE LINE)
────────────────────────────────────────────

Open advanced_notifications.py in any editor:

  nano /opt/nifty_scanner/advanced_notifications.py

Find this section (around line 410):

  pattern_boosts = {
      'BURST': 0,              # Neutral
      'MOMENTUM_2_CANDLES': 1.2,
      'MOMENTUM_3_CANDLES': 1.5,
      'CONSECUTIVE_SURGE': 2.0,
      'RECOVERY_TO_NORMAL': 0,    # Neutral
      'VOLUME_COMPRESSION': 0,    # Neutral
  }

Change the three 0 values to 1.0:

  pattern_boosts = {
      'BURST': 1.0,            # was 0, now neutral (passes through ratio unchanged)
      'MOMENTUM_2_CANDLES': 1.2,
      'MOMENTUM_3_CANDLES': 1.5,
      'CONSECUTIVE_SURGE': 2.0,
      'RECOVERY_TO_NORMAL': 1.0,  # was 0
      'VOLUME_COMPRESSION': 1.0,  # was 0
  }

Save. That's it. Now channel routing works correctly for all 5 patterns.


STEP 4  —  FILL IN YOUR CREDENTIALS
─────────────────────────────────────

  A. In advanced_notifications.py
     ───────────────────────────────
     Find NOTIFICATION_CONFIG at the top. Fill in:

       'bot_token': 'YOUR_BOT_TOKEN_HERE',

       'channels': {
           'EXTREME': { 'chat_id': '-1001234567890' },   ← NIFTY_EXTREME ID
           'LARGE':   { 'chat_id': '-1001234567891' },   ← NIFTY_LARGE ID
           'MEDIUM':  { 'chat_id': '-1001234567892' },   ← NIFTY_MEDIUM ID
           'SMALL':   { 'chat_id': '-1001234567893' },   ← NIFTY_SMALL ID
       }

  B. In nifty_volume_alert_scanner_advanced.py
     ────────────────────────────────────────────
     Find CONFIG at the top. Fill in:

       'broker_api_key': 'your_finvasia_api_key',
       'broker_token':   'your_finvasia_user_id',

     Update your ATM symbols. Check current Nifty spot, find ATM strike,
     update these lines with the correct expiry and strike:

       'NIFTY': {
           'call': 'NIFTY26MAY23900CE',   ← update this
           'put':  'NIFTY26MAY23900PE',   ← update this
           'exch': 'NFO',
       },

     How to find exact symbol strings: login to Shoonya web terminal →
     search option chain → right-click any strike → "Symbol Info" or
     check the API symbol master file at:
       https://api.shoonya.com/NFO_symbols.txt.gz


STEP 5  —  ADD SOUND FILES (OPTIONAL BUT RECOMMENDED)
────────────────────────────────────────────────────────

Download free sound files. Recommended source: mixkit.co (completely free,
no account needed). Search each of these:

  "emergency alarm loop"  → save as  siren_extreme.wav
  "classic alarm clock"   → save as  alarm_large.wav
  "interface notification" → save as  alert_medium.wav
  "software notification"  → save as  ding_small.wav

Upload them to your VPS:

  scp siren_extreme.wav  user@YOUR_VPS_IP:/opt/nifty_scanner/sounds/
  scp alarm_large.wav    user@YOUR_VPS_IP:/opt/nifty_scanner/sounds/
  scp alert_medium.wav   user@YOUR_VPS_IP:/opt/nifty_scanner/sounds/
  scp ding_small.wav     user@YOUR_VPS_IP:/opt/nifty_scanner/sounds/

Test one plays on VPS:

  paplay /opt/nifty_scanner/sounds/siren_extreme.wav

If you get "no such file" for paplay, try:  aplay siren_extreme.wav
If your VPS has no speaker (common on cloud VPS), sounds won't work — that's
fine, Telegram notifications still work perfectly.


STEP 6  —  CONNECT THE TWO FILES
──────────────────────────────────

Open nifty_volume_alert_scanner_advanced.py:

  nano /opt/nifty_scanner/nifty_volume_alert_scanner_advanced.py

Find the import block at the very top (around line 10–18). Add this line
at the end of the imports:

  from advanced_notifications import send_volume_alert, NotificationManager, NOTIFICATION_CONFIG

Then find the scan_symbol() method. Find this block (around line 550–566):

  # Format and send alert
  msg = format_detailed_alert(
      symbol=f"{symbol_key} {option_type}",
      ...
  )
  is_urgent = analysis['severity'] in ['EXTREME', 'LARGE']
  send_telegram_alert(msg, is_urgent=is_urgent)

Replace the whole block with:

  send_volume_alert(
      symbol=f"{symbol_key} {option_type}",
      option_type=option_type,
      analysis=analysis,
      current_volume=volume,
      avg_volume=avg_vol,
      current_rsi=rsi,
      avg_rsi=avg_rsi,
      ltp=ltp,
      price=price,
  )

Save the file.


STEP 7  —  TEST BEFORE GOING LIVE
───────────────────────────────────

Test the notification system alone first:

  cd /opt/nifty_scanner
  python3 advanced_notifications.py

This runs a test alert with fake data. Check your Telegram:
  → You should get a message in one of the 4 channels
  → If it went to the wrong channel, double-check your channel IDs

Test the scanner in dry-run mode (no broker credentials needed):

  python3 nifty_volume_alert_scanner_advanced.py

You should see log lines like:
  2026-05-12 09:15:30 [INFO] 🚀 Advanced Nifty ATM Volume Scanner Started
  2026-05-12 09:15:30 [INFO] Scan cycle at 09:15:30

If it crashes immediately, check:
  → Are both files in the same directory?
  → Did you add the import line?
  → Are there syntax errors? Run: python3 -m py_compile advanced_notifications.py


STEP 8  —  INSTALL AS A SERVICE (RUNS 24/7 ON VPS)
─────────────────────────────────────────────────────

Copy the systemd service file:

  sudo cp nifty_scanner.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable nifty_scanner
  sudo systemctl start nifty_scanner

Check it's running:

  sudo systemctl status nifty_scanner

Watch live logs:

  sudo journalctl -u nifty_scanner -f

Stop it:

  sudo systemctl stop nifty_scanner

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 2  —  TELEGRAM NOTIFICATION SETTINGS ON YOUR PHONE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is how you actually get different sounds on your phone for each category.
Telegram lets you set a custom notification sound per chat/channel.

For each of your 4 channels:
  1. Open the channel in Telegram (on your phone)
  2. Tap the channel name at the top
  3. Tap the bell icon (Notifications)
  4. Tap "Sound"
  5. Choose a different sound for each:

  NIFTY_EXTREME  → choose the loudest alarm sound available
  NIFTY_LARGE    → choose a distinct alarm
  NIFTY_MEDIUM   → choose a softer alert tone
  NIFTY_SMALL    → choose the quietest or just vibrate

Also for NIFTY_EXTREME, go back to Notifications settings and:
  → Turn on "Override System Settings" → set volume to maximum
  → Turn on "Popup Notifications"

This means even if your phone is on silent, the EXTREME channel will
still make noise and show a popup. That's the "can't miss it" channel.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 3  —  MONTHLY MAINTENANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Nifty monthly expiry is the last Thursday of every month.

The day BEFORE expiry, update your ATM symbols:

  nano /opt/nifty_scanner/nifty_volume_alert_scanner_advanced.py

Change these lines:

  'call': 'NIFTY26MAY23900CE',   ← change to next month's expiry + new ATM
  'put':  'NIFTY26MAY23900PE',

Example: if Nifty is at 24050 on rollover day, ATM strike is 24050
(or nearest 50-point strike, so 24050 or 24000).

New symbol format:  NIFTY26JUN24050CE

After saving, restart:

  sudo systemctl restart nifty_scanner
  sudo journalctl -u nifty_scanner -f    ← confirm it starts cleanly


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 4  —  HOW TO READ THE ALERTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Every alert shows this information:

  ─────────────────────────────────────────────────
  🔥 SINGLE CANDLE BURST - Volume spike in ONE candle
  Magnitude: 5x (5.2x average) | ⚡ Severity: MEDIUM
  ─────────────────────────────────────────────────
  Symbol:  NIFTY CE
  LTP:     ₹45.50  |  Close: ₹45.25
  ─────────────────────────────────────────────────
  VOLUME:
    Current:  1,450,000
    Avg (4h):   293,000
    Ratio:    5.2x
    Level:    5x
  PATTERN:  BURST
  ─────────────────────────────────────────────────
  RSI (30-min):  68.5  🟡 NEUTRAL
  Avg RSI (4h):  52.3
  Severity:      MEDIUM
  Time:          14:30:45
  ─────────────────────────────────────────────────

LINE BY LINE:

  "BURST"              → spike in one candle only. Not sustained yet.
  "MOMENTUM_2_CANDLES" → 2 consecutive candles above 2x average. Trend forming.
  "CONSECUTIVE_SURGE"  → 3+ candles. Strong directional move.
  "RECOVERY"           → volume normalised after spike. Move may be done.
  "COMPRESSION"        → volume below 70% average. Market is quiet.

  Ratio 5.2x  → this candle had 5.2 times the normal volume
  Level "5x"  → triggered the 5x threshold → went to MEDIUM channel

  RSI 68.5 🟡 NEUTRAL  → RSI between 40–60 = neutral zone
  RSI < 30 🟢 OVERSOLD → option oversold, underlying likely beat down
  RSI > 70 🔴 OVERBOUGHT → option in overbought territory

  Avg RSI 52.3 → where RSI has been sitting for the last 4 hours


WHAT CHANNEL = WHAT TO EXPECT:

  📊 SMALL  (3x–5x)
    Slight elevation. Market is waking up or random noise.
    Don't act on this alone. Just awareness.

  ⚡ MEDIUM (5x–10x)
    Something is happening. A real move may be starting.
    Check direction. Is price moving with the volume?

  ⚠️ LARGE  (10x–20x)
    Significant activity. Institutions or big players involved.
    High-probability signal. Worth acting on with RSI confirmation.

  🚨 EXTREME (20x+)
    Panic, liquidation, or major event.
    Sharpest moves happen here. Also most dangerous. Expect volatility.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 5  —  HOW YOU PERSONALLY USE THIS (YOUR SETUP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on what you described earlier about your approach:

  RSI below 40 + rising + CE volume spike  → something is telling you calls
  RSI above 60 + falling + PE volume spike → something is telling you puts
  Volume dead on both sides                → compression, quiet time

The scanner already sends you exactly that context in every alert:
  → RSI value with zone label (OVERSOLD / NEUTRAL / OVERBOUGHT)
  → Volume pattern (BURST / MOMENTUM / SURGE)
  → Which side spiked (CE or PE, they scan independently)
  → When both sides go quiet, you'll get a COMPRESSION alert from both

The scanner is giving you the raw information. You make the decision.

PRACTICAL WORKFLOW:
  1. SMALL channel message arrives → glance at it, continue what you're doing
  2. MEDIUM channel message arrives → look at your chart, see if price confirmed
  3. LARGE channel arrives → open terminal immediately, read the alert fully
  4. EXTREME channel arrives → your phone makes noise even on silent → act now

On quiet days (compression from both CE and PE):
  The scanner sends COMPRESSION alerts to SMALL channel.
  Both sides quiet = time decay working, no rush.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 6  —  TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROBLEM: No alerts arriving
  → Check scanner is running:  sudo systemctl status nifty_scanner
  → Check logs:  sudo journalctl -u nifty_scanner -n 50
  → Test Telegram manually:
       curl -X POST https://api.telegram.org/bot<TOKEN>/sendMessage \
         -d chat_id=<CHANNEL_ID> -d text="test"
  → Confirm bot is admin in all 4 channels

PROBLEM: All alerts go to SMALL channel regardless of volume size
  → You haven't applied the bug fix in Step 3 of this guide
  → Open advanced_notifications.py, find pattern_boosts, change 0 → 1.0

PROBLEM: Wrong channel IDs
  → Forward a message from each channel to @userinfobot in Telegram
  → It tells you the exact chat ID of that chat
  → Update NOTIFICATION_CONFIG with correct IDs

PROBLEM: Broker data not coming in
  → Confirm your Finvasia API key is active (check developer console at
    shoonya.finvasia.com)
  → Make sure your session token hasn't expired (tokens expire daily —
    you may need a daily re-auth cron job, check Finvasia API docs)
  → Check symbol strings match exactly what Finvasia expects
  → Try: python3 -c "import requests; print(requests.get('https://api.shoonya.com').status_code)"

PROBLEM: Scanner crashes on startup
  → python3 -m py_compile nifty_volume_alert_scanner_advanced.py
  → python3 -m py_compile advanced_notifications.py
  → Fix any syntax errors shown, then restart service

PROBLEM: Sound not playing
  → VPS may not have audio hardware (most cloud VPS don't)
  → Telegram custom sounds work fine without VPS audio
  → If you're on a local machine, test: paplay /opt/nifty_scanner/sounds/siren_extreme.wav


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 7  —  QUICK REFERENCE CARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VOLUME → CHANNEL MAPPING (after bug fix):

  3x – 5x    →  📊 SMALL    →  NIFTY_SMALL channel
  5x – 10x   →  ⚡ MEDIUM   →  NIFTY_MEDIUM channel
  10x – 20x  →  ⚠️ LARGE    →  NIFTY_LARGE channel
  20x+       →  🚨 EXTREME  →  NIFTY_EXTREME channel


PATTERNS (shown inside every alert message):

  BURST              → 1 candle spike. Reversal likely.
  MOMENTUM_2/3       → 2–3 candles elevated. Trend forming.
  CONSECUTIVE_SURGE  → 3+ candles strong. High conviction move.
  RECOVERY           → Volume returned to normal. Move may be done.
  COMPRESSION        → Volume below 70% avg. Market quiet.


RSI ZONES (shown in every alert):

  Below 30   →  🟢 OVERSOLD
  30 – 70    →  🟡 NEUTRAL
  Above 70   →  🔴 OVERBOUGHT


SERVICE COMMANDS:

  Start    →  sudo systemctl start nifty_scanner
  Stop     →  sudo systemctl stop nifty_scanner
  Restart  →  sudo systemctl restart nifty_scanner
  Status   →  sudo systemctl status nifty_scanner
  Logs     →  sudo journalctl -u nifty_scanner -f


FILES AND LOCATIONS:

  Scanner script    →  /opt/nifty_scanner/nifty_volume_alert_scanner_advanced.py
  Notifications     →  /opt/nifty_scanner/advanced_notifications.py
  Sound files       →  /opt/nifty_scanner/sounds/
  Service file      →  /etc/systemd/system/nifty_scanner.service
  Logs              →  /var/log/nifty_scanner/


THINGS TO UPDATE MONTHLY:

  Option symbol strings in nifty_volume_alert_scanner_advanced.py
  (call and put for NIFTY and BANKNIFTY, new expiry + ATM strike)
  Then: sudo systemctl restart nifty_scanner


THINGS TO NEVER CHANGE UNLESS YOU KNOW WHY:

  The deque maxlen values in AdvancedVolumeTracker
  The RSI calculation function
  The broker API endpoint URLs

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

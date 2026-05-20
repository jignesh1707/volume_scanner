#!/usr/bin/env python3
"""
Advanced Nifty ATM Options Volume Alert Scanner
Detailed condition reporting for different volume patterns
- Single candle spikes (burst)
- Multiple consecutive spikes (momentum)
- Magnitude levels (3x, 10x, etc)
- Recovery patterns
"""

import json
import os
import time
from datetime import datetime
from collections import deque
import logging
from typing import Dict, List, Tuple, Optional

from dotenv import load_dotenv

from advanced_notifications import (
    NOTIFICATION_CONFIG,
    NotificationManager,
    send_volume_alert,
)

# Load .env from the same directory as this script (systemd sets
# WorkingDirectory=/opt/volume_scanner, so a bare load_dotenv() resolves there).
load_dotenv()

# ==================== CONFIG ====================
CONFIG = {
    # Broker (Shoonya / Finvasia). Daily login is done out-of-band by
    # login_shoonya.py, which writes session_scanner.json next to this
    # script. The scanner only reads that file — if it's missing or stale
    # the service refuses to start and prints a clear instruction.
    'broker_user':         os.getenv('SHOONYA_USER', ''),
    'broker_session_file': os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'session_scanner.json',
    ),
    
    # Notifications are configured in advanced_notifications.py
    # (multi-channel Telegram routed by severity).

    # Scanning params
    'scan_interval_sec': 30,
    'lookback_hours': 4,
    'rsi_period': 14,
    
    # Alert thresholds - GRANULAR
    'volume_thresholds': {
        '3x': 3.0,      # Small spike
        '5x': 5.0,      # Medium spike
        '10x': 10.0,    # Large spike
        '15x': 15.0,    # Very large spike
        '20x': 20.0,    # Extreme spike
    },
    
    # Consecutive candle detection
    'consecutive_spike_threshold': 2.0,  # 2x average = consecutive spike
    'consecutive_candle_count': 3,       # Alert after 3 consecutive
    
    # Pattern detection
    'detect_burst_pattern': True,        # Single spike vs multi-candle
    'detect_recovery_pattern': True,     # Return to normal after spike
    'detect_volume_compression': True,   # Volume drying up
    
    # Symbols to scan (ATM CALL/PUT) — Shoonya tradingsymbol format:
    #   <NAME><DD><MMM><YY><C|P><STRIKE>     e.g. NIFTY27MAY26C24500
    # Exchange is NFO for index options (NOT NSE — NSE is for spot/equities).
    # Update strikes + expiry each week. Use finvasia_option_symbol() helper
    # in TickRenko/core/option_config.py if you want to script this.
    'symbols': {
        'NIFTY': {
            'call': 'NIFTY27MAY26C24500',
            'put':  'NIFTY27MAY26P24500',
            'exch': 'NFO',
        },
        'BANKNIFTY': {
            'call': 'BANKNIFTY27MAY26C55000',
            'put':  'BANKNIFTY27MAY26P55000',
            'exch': 'NFO',
        },
    },
    
    # Logging — log next to the script so it works on Windows and Linux (VPS) alike.
    'log_file': os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'nifty_volume_alerts.log',
    ),
    'debug': False,
}

# ==================== LOGGING ====================
def setup_logging():
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    log_file = CONFIG['log_file']
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Windows console defaults to cp1252 and can't print emoji — force UTF-8.
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, Exception):
            pass

    logging.basicConfig(
        level=logging.DEBUG if CONFIG['debug'] else logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== DATA STRUCTURES ====================
class AdvancedVolumeTracker:
    def __init__(self, symbol: str, lookback_hours: int = 4):
        self.symbol = symbol
        self.lookback_hours = lookback_hours
        
        # History tracking
        self.volume_history = deque(maxlen=100)  # (timestamp, volume)
        self.rsi_history = deque(maxlen=100)     # (timestamp, rsi, close)
        self.price_history = deque(maxlen=100)   # (timestamp, close)
        
        # Pattern tracking
        self.consecutive_spike_count = 0
        self.last_spike_time = None
        self.spike_pattern_start = None
        self.previous_volume = 0
        self.volume_trend = []  # Track direction of volume changes
        
        # Alert cooldowns
        self.last_alert_time = {}
        self.alert_cooldown_sec = 300
        
        # Spike state
        self.current_spike_level = None
        self.spike_started_time = None

        # Last analysis result (for cross-symbol checks)
        self.last_analysis = None
        
    def add_candle(self, timestamp: datetime, volume: float, close: float, rsi: float):
        """Add new candle and track patterns"""
        self.volume_history.append((timestamp, volume))
        self.rsi_history.append((timestamp, rsi, close))
        self.price_history.append((timestamp, close))
        
        # Track volume trend (up/down/flat)
        if self.previous_volume > 0:
            if volume > self.previous_volume * 1.1:
                self.volume_trend.append('UP')
            elif volume < self.previous_volume * 0.9:
                self.volume_trend.append('DOWN')
            else:
                self.volume_trend.append('FLAT')
        
        self.previous_volume = volume
        
        # Keep only last 20 trend points
        if len(self.volume_trend) > 20:
            self.volume_trend.pop(0)
    
    def get_avg_volume(self) -> float:
        """Get average volume from last 50 candles (excluding current)"""
        if len(self.volume_history) < 2:
            return 0
        # Take last 51 entries, drop current (last), use previous 50 as baseline
        history = list(self.volume_history)
        baseline = history[-51:-1] if len(history) > 51 else history[:-1]
        volumes = [v for _, v in baseline]
        return sum(volumes) / len(volumes) if volumes else 0
    
    def get_current_volume(self) -> float:
        """Get latest volume"""
        return self.volume_history[-1][1] if self.volume_history else 0
    
    def get_avg_rsi(self) -> float:
        """Get average RSI from lookback period (excluding current)"""
        if len(self.rsi_history) < 2:
            return 50
        rsis = [r for _, r, _ in list(self.rsi_history)[:-1]]
        return sum(rsis) / len(rsis) if rsis else 50
    
    def get_current_rsi(self) -> float:
        """Get latest RSI"""
        return self.rsi_history[-1][1] if self.rsi_history else 50

    def get_rsi_slope(self) -> str:
        """Direction of RSI over last 3 values: rising / falling / flat"""
        if len(self.rsi_history) < 3:
            return 'flat'
        values = [r for _, r, _ in list(self.rsi_history)[-3:]]
        if values[-1] > values[0] + 1.0:
            return 'rising'
        elif values[-1] < values[0] - 1.0:
            return 'falling'
        return 'flat'

    def get_rsi_zone(self) -> str:
        """Classify current RSI: oversold (<40) / neutral (40-60) / overbought (>60)"""
        rsi = self.get_current_rsi()
        if rsi < 40:
            return 'oversold'
        elif rsi > 60:
            return 'overbought'
        return 'neutral'

    def get_current_price(self) -> float:
        """Get latest close price"""
        return self.price_history[-1][1] if self.price_history else 0
    
    def analyze_volume_spike(self, current_volume: float) -> Dict:
        """
        Comprehensive spike analysis
        Returns: {
            'spike_detected': bool,
            'spike_level': str or None,  # '3x', '5x', '10x', etc
            'spike_ratio': float,
            'pattern': str,  # 'BURST', 'CONSECUTIVE', 'RECOVERY', 'COMPRESSION', None
            'severity': str,  # 'SMALL', 'MEDIUM', 'LARGE', 'EXTREME'
            'consecutive_count': int,
            'description': str
        }
        """
        avg_vol = self.get_avg_volume()
        if avg_vol == 0:
            return {
                'spike_detected': False,
                'spike_level': None,
                'spike_ratio': 0,
                'pattern': None,
                'severity': None,
                'consecutive_count': 0,
                'description': 'Insufficient data'
            }
        
        ratio = current_volume / avg_vol
        spike_level = None
        severity = None
        
        # Determine spike level (highest match)
        for level_str, threshold in sorted(CONFIG['volume_thresholds'].items(), 
                                          key=lambda x: x[1], reverse=True):
            if ratio >= threshold:
                spike_level = level_str
                break
        
        # Determine severity
        if ratio >= 20:
            severity = 'EXTREME'
        elif ratio >= 10:
            severity = 'LARGE'
        elif ratio >= 5:
            severity = 'MEDIUM'
        elif ratio >= 3:
            severity = 'SMALL'
        elif ratio >= 2:
            severity = 'NOTABLE'
        
        # Pattern detection
        pattern = self.detect_pattern(current_volume, avg_vol)
        
        spike_detected = spike_level is not None
        
        # Generate description
        description = self.generate_description(ratio, spike_level, pattern, severity)
        
        result = {
            'spike_detected': spike_detected,
            'spike_level': spike_level,
            'spike_ratio': ratio,
            'pattern': pattern,
            'severity': severity,
            'consecutive_count': self.consecutive_spike_count,
            'description': description
        }
        self.last_analysis = result
        return result
    
    def detect_pattern(self, current_volume: float, avg_vol: float) -> str:
        """Detect volume pattern type"""
        
        # Get last few volumes
        recent_volumes = list(self.volume_history)[-4:]
        if len(recent_volumes) < 2:
            return None
        
        recent_vols = [v for _, v in recent_volumes]
        
        # Check for consecutive spikes
        consecutive_above = 0
        for vol in recent_vols:
            if vol > avg_vol * CONFIG['consecutive_spike_threshold']:
                consecutive_above += 1
            else:
                break
        
        if consecutive_above >= CONFIG['consecutive_candle_count']:
            self.consecutive_spike_count = consecutive_above
            return 'CONSECUTIVE_SURGE'
        elif consecutive_above == 1 and current_volume > avg_vol * 2:
            # Single candle burst
            self.consecutive_spike_count = 0
            return 'BURST'
        elif consecutive_above > 1:
            self.consecutive_spike_count = consecutive_above
            return f'MOMENTUM_{consecutive_above}_CANDLES'
        
        # Check for recovery (volume was high, now normal)
        if len(recent_vols) >= 2:
            prev_vol = recent_vols[-2]
            if prev_vol > avg_vol * 2 and current_volume <= avg_vol * 1.2:
                return 'RECOVERY_TO_NORMAL'
        
        # Check for compression (volume drying up)
        if len(recent_vols) >= 3:
            recent_avg = sum(recent_vols) / len(recent_vols)
            if recent_avg < avg_vol * 0.7:
                return 'VOLUME_COMPRESSION'
        
        return None
    
    def generate_description(self, ratio: float, spike_level: str, 
                           pattern: str, severity: str) -> str:
        """Generate human-readable alert description"""
        
        parts = []
        
        if pattern == 'BURST':
            parts.append(f"🔥 SINGLE CANDLE BURST - Volume spike in ONE candle")
        elif pattern and 'MOMENTUM' in pattern:
            count = self.consecutive_spike_count
            parts.append(f"📈 VOLUME MOMENTUM - {count} consecutive candles with elevated volume")
        elif pattern == 'CONSECUTIVE_SURGE':
            parts.append(f"⚡ SUSTAINED SURGE - Multiple candles with {self.consecutive_spike_threshold:.1f}x+ average volume")
        elif pattern == 'RECOVERY_TO_NORMAL':
            parts.append(f"✅ RECOVERY - Volume returning to normal after spike")
        elif pattern == 'VOLUME_COMPRESSION':
            parts.append(f"📉 COMPRESSION - Volume drying up below average")
        
        if spike_level:
            parts.append(f"Magnitude: {spike_level} ({ratio:.1f}x average)")
        
        if severity:
            severity_emoji = {
                'EXTREME': '🚨',
                'LARGE': '⚠️',
                'MEDIUM': '⚡',
                'SMALL': '📊',
                'NOTABLE': '📍'
            }
            parts.append(f"{severity_emoji.get(severity, '')} Severity: {severity}")
        
        return ' | '.join(parts) if parts else f"Volume spike: {ratio:.1f}x"
    
    def should_alert(self, condition_key: str) -> bool:
        """Check cooldown for specific condition"""
        key = f"{condition_key}"
        now = time.time()
        last_time = self.last_alert_time.get(key, 0)
        
        if now - last_time < self.alert_cooldown_sec:
            return False
        
        self.last_alert_time[key] = now
        return True

# ==================== BROKER API ====================
class BrokerAPI:
    """
    Shoonya (Finvasia) API wrapper using NorenRestApiPy.

    Auth: read-only. login() loads the susertoken from session_scanner.json,
    which is written each morning by login_shoonya.py (interactive password +
    TOTP). If the file is missing or its saved_date isn't today, login()
    returns False and the caller is expected to exit with instructions.

    Methods consumed by the scanner:
      fetch_intraday_data(symbol, exchange, interval='1')
          -> [{'timestamp': iso, 'close': float, 'volume': float}, ...]
             oldest first.
      get_ltp(symbol, exchange) -> (ltp, volume)

    Shoonya needs numeric tokens, not tradingsymbol strings — _resolve_token()
    looks them up once via searchscrip and caches for the session.
    """

    def __init__(self, user: str, session_file: str = "session_scanner.json"):
        from NorenRestApiPy.NorenApi import NorenApi

        class _ScannerApi(NorenApi):
            def __init__(self):
                NorenApi.__init__(
                    self,
                    host='https://api.shoonya.com/NorenWClientTP/',
                    websocket='wss://api.shoonya.com/NorenWSTP/',
                )

        self._user = user
        self._session_file = session_file
        self._api = _ScannerApi()
        self._token_cache: Dict[Tuple[str, str], str] = {}
        self._authenticated = False

    def login(self) -> bool:
        """Load today's susertoken from session_scanner.json."""
        try:
            with open(self._session_file) as fh:
                session = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.critical(
                "Shoonya: %s not found or unreadable. Run `python login_shoonya.py` first.",
                self._session_file,
            )
            return False

        if session.get("saved_date") != time.strftime("%Y-%m-%d"):
            logger.critical(
                "Shoonya session is stale (saved %s). Run `python login_shoonya.py` to refresh.",
                session.get("saved_date", "unknown"),
            )
            return False

        susertoken = session.get("susertoken", "")
        if not susertoken:
            logger.critical("Shoonya session file has no susertoken; re-run login_shoonya.py.")
            return False

        self._api.susertoken = susertoken
        self._api.username = self._user
        self._api.actid = self._user
        self._authenticated = True
        logger.info("✓ Loaded Shoonya session from %s", self._session_file)
        return True

    def _resolve_token(self, symbol: str, exchange: str) -> Optional[str]:
        key = (exchange, symbol)
        if key in self._token_cache:
            return self._token_cache[key]
        try:
            resp = self._api.searchscrip(exchange=exchange, searchtext=symbol)
        except Exception as exc:
            logger.error(f"searchscrip failed for {symbol}: {exc}")
            return None
        if not resp or resp.get("stat") != "Ok":
            logger.warning(f"searchscrip returned no match for {symbol}: {resp}")
            return None
        for v in resp.get("values", []):
            if v.get("tsym") == symbol:
                token = v.get("token", "")
                self._token_cache[key] = token
                return token
        # Fallback to first match — log it so user can correct the CONFIG entry.
        values = resp.get("values", [])
        if values:
            token = values[0].get("token", "")
            logger.warning(
                "No exact match for %s — using first hit %s (token %s). "
                "Fix CONFIG['symbols'] if this is wrong.",
                symbol, values[0].get("tsym"), token,
            )
            self._token_cache[key] = token
            return token
        return None

    def fetch_intraday_data(self, symbol: str, exchange: str,
                            interval: str = '1') -> List[Dict]:
        if not self._authenticated:
            return []
        token = self._resolve_token(symbol, exchange)
        if not token:
            return []
        try:
            now = time.time()
            from_ts = now - (5 * 3600)  # 5h lookback (covers lookback_hours=4)
            resp = self._api.get_time_price_series(
                exchange=exchange,
                token=token,
                starttime=from_ts,
                endtime=now,
                interval=interval,
            )
        except Exception as exc:
            logger.error(f"get_time_price_series failed for {symbol}: {exc}")
            return []
        if not resp:
            return []

        candles: List[Dict] = []
        for row in resp:
            try:
                candles.append({
                    'timestamp': datetime.fromtimestamp(float(row['ssboe'])).isoformat(),
                    'close':     float(row['intc']),
                    'volume':    float(row.get('intv', 0) or 0),
                })
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug(f"Skipping malformed bar for {symbol}: {exc}")
        # Shoonya returns newest-first; flip to oldest-first.
        candles.reverse()
        return candles

    def get_ltp(self, symbol: str, exchange: str) -> Tuple[float, float]:
        if not self._authenticated:
            return 0.0, 0.0
        token = self._resolve_token(symbol, exchange)
        if not token:
            return 0.0, 0.0
        try:
            resp = self._api.get_quotes(exchange=exchange, token=token)
        except Exception as exc:
            logger.error(f"get_quotes failed for {symbol}: {exc}")
            return 0.0, 0.0
        if resp and resp.get("stat") == "Ok":
            ltp    = float(resp.get("lp", 0) or 0)
            volume = float(resp.get("v",  0) or 0)
            return ltp, volume
        return 0.0, 0.0

# ==================== INDICATORS ====================
def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculate RSI"""
    if len(closes) < period + 1:
        return 50
    
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100 if avg_gain > 0 else 50
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

# ==================== NOTIFICATIONS ====================
def derive_setup_context(rsi_zone: str, rsi_slope: str, pattern: str, option_type: str) -> str:
    """One-line setup context from RSI zone + slope + pattern + side. Pure information."""
    if pattern == 'VOLUME_COMPRESSION':
        return "Volume quiet on this side — wait for expansion"
    if pattern == 'RECOVERY_TO_NORMAL':
        return "Volume normalising after spike — momentum fading"

    opt = option_type.upper()

    if opt in ('CE', 'CALL'):
        if rsi_zone == 'oversold' and rsi_slope == 'rising':
            return "RSI rising from oversold + volume spike → CE setup forming"
        if rsi_zone == 'neutral' and rsi_slope == 'rising':
            return "RSI rising through neutral + CE volume spike → watch for breakout"
        if rsi_zone == 'overbought':
            return "RSI overbought + CE spike → late-entry risk, caution"
        if rsi_slope == 'falling':
            return "CE volume spike but RSI falling — possible short-lived move"

    if opt in ('PE', 'PUT'):
        if rsi_zone == 'overbought' and rsi_slope == 'falling':
            return "RSI falling from overbought + volume spike → PE setup forming"
        if rsi_zone == 'neutral' and rsi_slope == 'falling':
            return "RSI falling through neutral + PE volume spike → watch for breakdown"
        if rsi_zone == 'oversold':
            return "RSI oversold + PE spike → late-entry risk, caution"
        if rsi_slope == 'rising':
            return "PE volume spike but RSI rising — possible short-lived move"

    return f"Volume spike — RSI {rsi_zone}, {rsi_slope}"


# ==================== SCANNER ====================
class _NullDash:
    def heartbeat(self, **_): pass
    def log_trade(self, **_): pass
    def log_error(self, **_): pass
    def mark_stopped(self, *_a, **_kw): pass


def _build_dashboard():
    """Best-effort: return a real DashboardClient or a no-op fallback."""
    try:
        from dashboard_client import DashboardClient  # type: ignore
        return DashboardClient(bot_name="nifty_scanner")
    except Exception:
        return _NullDash()


class AdvancedVolumeScanner:
    def __init__(self, config: Dict):
        self.config = config
        self.broker = BrokerAPI(
            user=config['broker_user'],
            session_file=config['broker_session_file'],
        )
        self.trackers = {}
        self._compression_cooldown = {}
        self.dash = _build_dashboard()
        self.notifier = NotificationManager(NOTIFICATION_CONFIG)
        self._alerts_today = 0
        self._last_day = ""
        self.initialize_trackers()
    
    def initialize_trackers(self):
        """Initialize trackers for all symbols"""
        for symbol_key, symbol_data in self.config['symbols'].items():
            call_sym = symbol_data['call']
            put_sym = symbol_data['put']
            
            self.trackers[f"{symbol_key}_CALL"] = AdvancedVolumeTracker(call_sym, self.config['lookback_hours'])
            self.trackers[f"{symbol_key}_PUT"] = AdvancedVolumeTracker(put_sym, self.config['lookback_hours'])
        
        logger.info(f"Initialized {len(self.trackers)} trackers")
    
    def scan_symbol(self, symbol_key: str, option_type: str):
        """Scan single symbol with advanced analysis"""
        tracker_key = f"{symbol_key}_CALL" if option_type == "CALL" else f"{symbol_key}_PUT"
        symbol_data = self.config['symbols'][symbol_key]
        symbol = symbol_data['call'] if option_type == "CALL" else symbol_data['put']
        tracker = self.trackers[tracker_key]
        
        # Fetch latest candle
        candles = self.broker.fetch_intraday_data(symbol, symbol_data['exch'], interval='1')
        if not candles:
            logger.warning(f"No candle data for {symbol}")
            return
        
        latest = candles[-1]
        ts = datetime.fromisoformat(latest['timestamp'])
        close = float(latest['close'])
        volume = float(latest['volume'])
        
        # Calculate RSI
        closes = [float(c['close']) for c in candles[-20:]]
        rsi = calculate_rsi(closes, self.config['rsi_period'])
        
        # Add to tracker
        tracker.add_candle(ts, volume, close, rsi)
        
        # Analyze volume
        analysis = tracker.analyze_volume_spike(volume)
        
        if analysis['spike_detected']:
            # Determine if we should alert
            alert_key = f"{tracker_key}_{analysis['spike_level']}_{analysis['pattern']}"

            if tracker.should_alert(alert_key):
                # Get stats
                avg_vol = tracker.get_avg_volume()
                avg_rsi = tracker.get_avg_rsi()
                ltp, _ = self.broker.get_ltp(symbol, symbol_data['exch'])
                price = tracker.get_current_price()

                rsi_zone = tracker.get_rsi_zone()
                rsi_slope = tracker.get_rsi_slope()
                setup_context = derive_setup_context(rsi_zone, rsi_slope, analysis['pattern'], option_type)

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
                    rsi_zone=rsi_zone,
                    rsi_slope=rsi_slope,
                    setup_context=setup_context,
                )
                self._alerts_today += 1
                try:
                    self.dash.log_trade(
                        symbol = symbol,
                        side   = "BUY" if option_type == "CALL" else "SELL",
                        qty    = 0,
                        price  = float(analysis.get('current_price') or 0),
                        pnl    = 0.0,
                        reason = f"ALERT {analysis['pattern']} "
                                 f"{analysis['spike_ratio']:.1f}x "
                                 f"{analysis['severity']}",
                    )
                except Exception:
                    pass

                logger.info(
                    f"ALERT: {symbol_key} {option_type} | "
                    f"Pattern: {analysis['pattern']} | "
                    f"Ratio: {analysis['spike_ratio']:.1f}x | "
                    f"Severity: {analysis['severity']}"
                )
    
    def _check_cross_symbol_compression(self, symbol_key: str):
        """Fire one alert when both CE and PE volume are simultaneously dead."""
        call_tracker = self.trackers.get(f"{symbol_key}_CALL")
        put_tracker = self.trackers.get(f"{symbol_key}_PUT")

        if not call_tracker or not put_tracker:
            return

        call_compressed = (
            call_tracker.last_analysis is not None
            and call_tracker.last_analysis.get('pattern') == 'VOLUME_COMPRESSION'
        )
        put_compressed = (
            put_tracker.last_analysis is not None
            and put_tracker.last_analysis.get('pattern') == 'VOLUME_COMPRESSION'
        )

        if not (call_compressed and put_compressed):
            return

        cooldown_key = f"{symbol_key}_BOTH_COMPRESSION"
        now = time.time()
        if now - self._compression_cooldown.get(cooldown_key, 0) < 300:
            return

        self._compression_cooldown[cooldown_key] = now
        self._send_compression_alert(symbol_key)

    def _send_compression_alert(self, symbol_key: str):
        """Send the 'both sides quiet' alert."""
        msg = (
            f"📉 <b>VOLUME COMPRESSION — BOTH SIDES</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Symbol:</b> {symbol_key} CE + PE\n"
            f"Both CE and PE volume below 70% of baseline\n"
            f"\n📌 <b>Setup:</b> Both sides quiet — premium sellers' time\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        self.notifier.send_multi_channel_alert(
            title=f"{symbol_key} CE+PE — Volume Compression",
            message=msg,
            severity='SMALL',
        )
        logger.info(f"COMPRESSION ALERT: {symbol_key} — both CE and PE volume dead")

    def run(self):
        """Main scanning loop"""
        logger.info("=" * 70)
        logger.info("🚀 Advanced Nifty ATM Volume Scanner Started")
        logger.info(f"Scan interval: {self.config['scan_interval_sec']}s")
        logger.info(f"Lookback: {self.config['lookback_hours']}h")
        logger.info(f"Volume thresholds: {list(self.config['volume_thresholds'].keys())}")
        logger.info("=" * 70)
        self.dash.heartbeat(status="alive",
                            message=f"Booted, {len(self.trackers)} trackers")

        while True:
            try:
                logger.info(f"Scan cycle at {datetime.now().strftime('%H:%M:%S')}")

                # Roll over the alerts-today counter at midnight IST
                today = datetime.now().strftime('%Y-%m-%d')
                if self._last_day and today != self._last_day:
                    self._alerts_today = 0
                self._last_day = today

                # Scan all symbols
                for symbol_key in self.config['symbols'].keys():
                    self.scan_symbol(symbol_key, "CALL")
                    self.scan_symbol(symbol_key, "PUT")
                    self._check_cross_symbol_compression(symbol_key)

                try:
                    self.dash.heartbeat(
                        status="alive",
                        message=f"Scanning {len(self.trackers)} trackers",
                        day_trades=self._alerts_today,
                        extra={"alerts_today": self._alerts_today,
                               "trackers": list(self.trackers.keys())},
                    )
                except Exception:
                    pass

                time.sleep(self.config['scan_interval_sec'])

            except KeyboardInterrupt:
                logger.info("Scanner stopped by user")
                try:
                    self.dash.mark_stopped("shutdown")
                except Exception:
                    pass
                break

            except Exception as e:
                logger.error(f"Scan cycle error: {e}", exc_info=True)
                try:
                    self.dash.log_error(f"Scan cycle error: {e}",
                                        severity="error")
                except Exception:
                    pass
                time.sleep(self.config['scan_interval_sec'])

# ==================== MAIN ====================
if __name__ == '__main__':
    if not CONFIG['broker_user']:
        logger.error("Missing SHOONYA_USER in /opt/volume_scanner/.env")
        exit(1)

    scanner = AdvancedVolumeScanner(CONFIG)
    if not scanner.broker.login():
        logger.error(
            "Shoonya login failed. Run `python login_shoonya.py` on the VPS "
            "to refresh the daily session, then restart this service."
        )
        exit(1)
    scanner.run()

#!/usr/bin/env python3
"""
Advanced Multi-Channel Notification System for Volume Alerts
- Multiple Telegram channels (different severity levels)
- Discord webhooks (with mentions and embeds)
- Desktop/system notifications (Linux)
- Sound alerts (plays audio files)
- Email notifications (critical only)
- Log files with timestamps
"""

import requests
import json
import time
import subprocess
import os
from datetime import datetime
from typing import Dict, Optional
import logging

# ==================== CONFIG ====================
NOTIFICATION_CONFIG = {
    # TELEGRAM CHANNELS (Multiple channels for different severities)
    'telegram': {
        'enabled': True,
        'bot_token': '8740544874:AAHOD7C_qVi99pZVUl9OzPttjiBv5UMOZt0',

        # Different channels for different alert levels
        'channels': {
            'EXTREME': {
                'chat_id': '-1003943315215',
                'name': '🚨 EXTREME ALERTS',
                'mention': '@here',
            },
            'LARGE': {
                'chat_id': '-1003925765182',
                'name': '⚠️ LARGE ALERTS',
                'mention': None,
            },
            'MEDIUM': {
                'chat_id': '-1003927494525',
                'name': '⚡ MEDIUM ALERTS',
                'mention': None,
            },
            'SMALL': {
                'chat_id': '-1003917720485',
                'name': '📊 SMALL ALERTS',
                'mention': None,
            },
        }
    },
    
    # DISCORD WEBHOOKS (Optional, for group notifications)
    'discord': {
        'enabled': False,
        'webhooks': {
            'EXTREME': 'https://discord.com/api/webhooks/YOUR_WEBHOOK_ID_EXTREME',
            'LARGE': 'https://discord.com/api/webhooks/YOUR_WEBHOOK_ID_LARGE',
            'MEDIUM': 'https://discord.com/api/webhooks/YOUR_WEBHOOK_ID_MEDIUM',
        }
    },
    
    # SYSTEM/DESKTOP NOTIFICATIONS (Linux/Mac/Windows)
    'system_notification': {
        'enabled': True,
        'timeout_ms': 10000,  # How long notification stays (10 seconds)
        'urgency_extreme': 'critical',  # Critical = maximum urgency
        'urgency_large': 'critical',
        'urgency_medium': 'normal',
        'urgency_small': 'low',
    },
    
    # SOUND ALERTS (Play audio files)
    'sound': {
        'enabled': True,
        'player': 'paplay',  # PulseAudio (use 'aplay' for ALSA, 'afplay' for macOS)
        'sounds': {
            'EXTREME': '/opt/nifty_scanner/sounds/siren_extreme.wav',      # Loud siren
            'LARGE': '/opt/nifty_scanner/sounds/alarm_large.wav',          # Loud alarm
            'MEDIUM': '/opt/nifty_scanner/sounds/alert_medium.mp3',        # Medium alert
            'SMALL': '/opt/nifty_scanner/sounds/ding_small.mp3',           # Soft ding
        },
        'volume_extreme': 100,  # 0-100
        'volume_large': 90,
        'volume_medium': 70,
        'volume_small': 50,
    },
    
    # EMAIL NOTIFICATIONS (For critical alerts only)
    'email': {
        'enabled': False,
        'send_on_severity': ['EXTREME'],  # Only EXTREME
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587,
        'from_email': 'your_email@gmail.com',
        'from_password': 'your_app_password',  # Use app-specific password
        'to_emails': ['alert@example.com'],
        'subject_prefix': '🚨 NIFTY VOLUME ALERT',
    },
    
    # LOGGING
    'logging': {
        # Log next to the script so it works on Windows and Linux (VPS) alike.
        'log_file': os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'nifty_alerts_notifications.log',
        ),
        'debug': False,
    }
}

# ==================== LOGGING ====================
def setup_logging():
    log_format = '%(asctime)s [%(levelname)s] %(message)s'
    log_file = NOTIFICATION_CONFIG['logging']['log_file']
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Windows console defaults to cp1252 and can't print emoji — force UTF-8.
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, Exception):
            pass

    logging.basicConfig(
        level=logging.DEBUG if NOTIFICATION_CONFIG['logging']['debug'] else logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ==================== TELEGRAM NOTIFICATIONS ====================
class TelegramNotifier:
    def __init__(self, config: Dict):
        self.config = config['telegram']
        self.enabled = self.config['enabled']
        self.bot_token = self.config['bot_token']
        self.session = requests.Session()
    
    def send_alert(self, message: str, severity: str = 'MEDIUM') -> bool:
        """Send alert to appropriate Telegram channel based on severity"""
        if not self.enabled:
            return False
        
        if severity not in self.config['channels']:
            severity = 'MEDIUM'
        
        channel_config = self.config['channels'][severity]
        chat_id = channel_config['chat_id']
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            # Add mention if configured
            if channel_config['mention']:
                message = f"{channel_config['mention']}\n{message}"
            
            payload = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML',
            }
            
            resp = self.session.post(url, json=payload, timeout=5)
            
            if resp.status_code == 200:
                logger.info(f"✓ Telegram alert sent to {channel_config['name']}")
                return True
            else:
                logger.error(f"Telegram error {resp.status_code}: {resp.text}")
                return False
        
        except Exception as e:
            logger.error(f"Telegram notification failed: {e}")
            return False

# ==================== DISCORD NOTIFICATIONS ====================
class DiscordNotifier:
    def __init__(self, config: Dict):
        self.config = config['discord']
        self.enabled = self.config['enabled']
        self.session = requests.Session()
    
    def send_alert(self, message: str, severity: str = 'MEDIUM', **kwargs) -> bool:
        """Send alert to Discord webhook"""
        if not self.enabled or severity not in self.config['webhooks']:
            return False
        
        webhook_url = self.config['webhooks'][severity]
        
        try:
            # Parse message for Discord embed
            symbol = kwargs.get('symbol', 'NIFTY')
            pattern = kwargs.get('pattern', 'UNKNOWN')
            ratio = kwargs.get('ratio', 0)
            
            # Color based on severity
            colors = {
                'EXTREME': 16711680,  # Red
                'LARGE': 16753920,    # Orange
                'MEDIUM': 16776960,   # Yellow
                'SMALL': 5287936,     # Green
            }
            
            embed = {
                'title': f'🚨 {severity} ALERT - {symbol}',
                'description': message,
                'color': colors.get(severity, 3447003),
                'fields': [
                    {
                        'name': 'Pattern',
                        'value': pattern,
                        'inline': True,
                    },
                    {
                        'name': 'Spike Ratio',
                        'value': f'{ratio:.1f}x',
                        'inline': True,
                    },
                    {
                        'name': 'Time',
                        'value': datetime.now().strftime('%H:%M:%S'),
                        'inline': True,
                    }
                ],
                'timestamp': datetime.utcnow().isoformat(),
            }
            
            payload = {
                'embeds': [embed]
            }
            
            resp = self.session.post(webhook_url, json=payload, timeout=5)
            
            if resp.status_code == 204:
                logger.info("✓ Discord alert sent")
                return True
            else:
                logger.error(f"Discord error: {resp.text}")
                return False
        
        except Exception as e:
            logger.error(f"Discord notification failed: {e}")
            return False

# ==================== SYSTEM NOTIFICATIONS ====================
class SystemNotifier:
    def __init__(self, config: Dict):
        self.config = config['system_notification']
        self.enabled = self.config['enabled']
    
    def send_alert(self, title: str, message: str, severity: str = 'MEDIUM') -> bool:
        """Send system notification (Linux notify-send)"""
        if not self.enabled:
            return False
        
        try:
            # Determine urgency
            urgency_map = {
                'EXTREME': self.config['urgency_extreme'],
                'LARGE': self.config['urgency_large'],
                'MEDIUM': self.config['urgency_medium'],
                'SMALL': self.config['urgency_small'],
            }
            urgency = urgency_map.get(severity, 'normal')
            
            # Use notify-send (Linux)
            subprocess.run(
                [
                    'notify-send',
                    '-u', urgency,
                    '-t', str(self.config['timeout_ms']),
                    title,
                    message,
                ],
                timeout=5,
                check=False,  # Don't raise on error
            )
            
            logger.info(f"✓ System notification sent ({severity})")
            return True
        
        except FileNotFoundError:
            logger.warning("notify-send not found (Linux notifications disabled)")
            return False
        except Exception as e:
            logger.error(f"System notification failed: {e}")
            return False

# ==================== SOUND ALERTS ====================
class SoundNotifier:
    def __init__(self, config: Dict):
        self.config = config['sound']
        self.enabled = self.config['enabled']
        self.player = self.config['player']
    
    def play_sound(self, severity: str = 'MEDIUM') -> bool:
        """Play sound alert based on severity"""
        if not self.enabled or severity not in self.config['sounds']:
            return False
        
        sound_file = self.config['sounds'][severity]
        
        # Check if sound file exists
        if not os.path.exists(sound_file):
            logger.warning(f"Sound file not found: {sound_file}")
            return False
        
        try:
            # Get volume
            volume_map = {
                'EXTREME': self.config['volume_extreme'],
                'LARGE': self.config['volume_large'],
                'MEDIUM': self.config['volume_medium'],
                'SMALL': self.config['volume_small'],
            }
            volume = volume_map.get(severity, 70)
            
            # Play sound (non-blocking)
            subprocess.Popen(
                [self.player, sound_file],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            logger.info(f"✓ Sound alert played ({severity}) - {sound_file}")
            return True
        
        except FileNotFoundError:
            logger.warning(f"Audio player '{self.player}' not found")
            return False
        except Exception as e:
            logger.error(f"Sound notification failed: {e}")
            return False

# ==================== EMAIL NOTIFICATIONS ====================
class EmailNotifier:
    def __init__(self, config: Dict):
        self.config = config['email']
        self.enabled = self.config['enabled']
    
    def send_alert(self, subject: str, message: str, severity: str = 'MEDIUM') -> bool:
        """Send email alert (critical only)"""
        if not self.enabled or severity not in self.config['send_on_severity']:
            return False
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(self.config['to_emails'])
            msg['Subject'] = f"{self.config['subject_prefix']} - {subject}"
            
            msg.attach(MIMEText(message, 'html'))
            
            # Send email
            with smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port']) as server:
                server.starttls()
                server.login(self.config['from_email'], self.config['from_password'])
                server.send_message(msg)
            
            logger.info("✓ Email alert sent")
            return True
        
        except Exception as e:
            logger.error(f"Email notification failed: {e}")
            return False

# ==================== UNIFIED NOTIFICATION MANAGER ====================
class NotificationManager:
    def __init__(self, config: Dict):
        self.telegram = TelegramNotifier(config)
        self.discord = DiscordNotifier(config)
        self.system = SystemNotifier(config)
        self.sound = SoundNotifier(config)
        self.email = EmailNotifier(config)
    
    def send_multi_channel_alert(
        self,
        title: str,
        message: str,
        severity: str = 'MEDIUM',
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send alert through all enabled channels
        Returns dict showing which channels succeeded
        """
        results = {}
        
        logger.info(f"🚨 SENDING {severity} ALERT ACROSS ALL CHANNELS")
        
        # Send to Telegram
        results['telegram'] = self.telegram.send_alert(message, severity)
        
        # Send to Discord
        results['discord'] = self.discord.send_alert(message, severity, **kwargs)
        
        # Send system notification
        results['system'] = self.system.send_alert(title, message, severity)
        
        # Play sound (async, non-blocking)
        results['sound'] = self.sound.play_sound(severity)
        
        # Send email (critical only)
        results['email'] = self.email.send_alert(title, message, severity)
        
        return results

# ==================== SEVERITY DETERMINATION ====================
def determine_severity(spike_ratio: float, pattern: str) -> str:
    """Determine alert severity based on spike ratio and pattern"""
    
    # Pattern-based severity boost
    pattern_boosts = {
        'BURST': 1.0,
        'MOMENTUM_2_CANDLES': 1.2,
        'MOMENTUM_3_CANDLES': 1.5,
        'CONSECUTIVE_SURGE': 2.0,
        'RECOVERY_TO_NORMAL': 1.0,
        'VOLUME_COMPRESSION': 1.0,
    }
    
    boosted_ratio = spike_ratio * pattern_boosts.get(pattern, 1.0)
    
    if boosted_ratio >= 20:
        return 'EXTREME'
    elif boosted_ratio >= 10:
        return 'LARGE'
    elif boosted_ratio >= 5:
        return 'MEDIUM'
    else:
        return 'SMALL'

# ==================== INTEGRATION EXAMPLE ====================
def send_volume_alert(
    symbol: str,
    option_type: str,
    analysis: Dict,
    current_volume: float,
    avg_volume: float,
    current_rsi: float,
    avg_rsi: float,
    ltp: float,
    price: float,
    rsi_zone: str = 'neutral',
    rsi_slope: str = 'flat',
    setup_context: str = '',
):
    """
    Integration point: Call this from your scanner
    
    Usage in nifty_volume_alert_scanner_advanced.py:
    ──────────────────────────────────────────────
    from advanced_notifications import send_volume_alert
    
    send_volume_alert(
        symbol=symbol,
        option_type=option_type,
        analysis=analysis,  # From analyze_volume_spike()
        current_volume=volume,
        avg_volume=avg_vol,
        current_rsi=rsi,
        avg_rsi=avg_rsi,
        ltp=ltp,
        price=price,
    )
    """
    
    # Determine severity
    severity = determine_severity(analysis['spike_ratio'], analysis['pattern'])
    
    # Format title
    title = f"{symbol} {option_type} - {severity} ALERT"
    
    # Format detailed message
    message = (
        f"<b>{analysis['description']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Symbol:</b> {symbol} {option_type}\n"
        f"<b>LTP:</b> ₹{ltp:.2f} | <b>Close:</b> ₹{price:.2f}\n"
        f"\n<b>VOLUME DATA:</b>\n"
        f"  Current: {current_volume:,.0f}\n"
        f"  Avg (4h): {avg_volume:,.0f}\n"
        f"  Ratio: <b>{analysis['spike_ratio']:.1f}x</b>\n"
    )
    
    if analysis['spike_level']:
        message += f"  Level: <b>{analysis['spike_level']}</b>\n"
    
    if analysis['pattern']:
        message += f"\n<b>PATTERN:</b> {analysis['pattern']}\n"
    
    if analysis['consecutive_count'] > 0:
        message += f"  Consecutive: {analysis['consecutive_count']}\n"
    
    zone_labels = {'oversold': '🟢 OVERSOLD', 'neutral': '🟡 NEUTRAL', 'overbought': '🔴 OVERBOUGHT'}
    slope_arrows = {'rising': '↑', 'falling': '↓', 'flat': '→'}
    message += (
        f"\n<b>RSI:</b> {current_rsi:.1f} "
        f"<b>{zone_labels.get(rsi_zone, rsi_zone)}</b> "
        f"{slope_arrows.get(rsi_slope, '')} ({rsi_slope})"
        f" | Avg: {avg_rsi:.1f}\n"
    )
    if setup_context:
        message += f"📌 <b>Setup:</b> {setup_context}\n"
    message += (
        f"<b>Severity:</b> {severity}\n"
        f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
    )
    
    # Send through all channels
    manager = NotificationManager(NOTIFICATION_CONFIG)
    results = manager.send_multi_channel_alert(
        title=title,
        message=message,
        severity=severity,
        symbol=symbol,
        pattern=analysis['pattern'],
        ratio=analysis['spike_ratio'],
    )
    
    # Log results
    logger.info(f"Alert distribution: {results}")
    
    return results

# ==================== MAIN ====================
if __name__ == '__main__':
    # Test notifications
    logger.info("Testing multi-channel notification system...")
    
    # Test with sample data
    test_analysis = {
        'description': 'SINGLE CANDLE BURST - Volume spike in ONE candle',
        'spike_detected': True,
        'spike_level': '5x',
        'spike_ratio': 5.2,
        'pattern': 'BURST',
        'severity': 'MEDIUM',
        'consecutive_count': 0,
    }
    
    send_volume_alert(
        symbol='NIFTY 26P 23900',
        option_type='CE',
        analysis=test_analysis,
        current_volume=1450000,
        avg_volume=293000,
        current_rsi=68.5,
        avg_rsi=52.3,
        ltp=45.50,
        price=45.25,
    )
    
    logger.info("Test notifications sent!")

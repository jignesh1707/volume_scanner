#!/usr/bin/env python3
"""
Sanity test: fire one alert at each severity so all 4 Telegram channels
(EXTREME / LARGE / MEDIUM / SMALL) get a test message.

Run:  python test_all_channels.py
"""

import time

from advanced_notifications import send_volume_alert

# spike_ratio thresholds in determine_severity() (with BURST pattern, boost=1.0):
#   >= 20 EXTREME, >= 10 LARGE, >= 5 MEDIUM, < 5 SMALL
CASES = [
    ('EXTREME', 25.0),
    ('LARGE',   12.0),
    ('MEDIUM',   6.0),
    ('SMALL',    4.0),
]

for label, ratio in CASES:
    analysis = {
        'description': f'TEST {label} ALERT — channel sanity check',
        'spike_detected': True,
        'spike_level': f'{ratio:.0f}x',
        'spike_ratio': ratio,
        'pattern': 'BURST',
        'severity': label,
        'consecutive_count': 0,
    }

    print(f'\n--- Firing {label} (ratio={ratio}x) ---')
    send_volume_alert(
        symbol='NIFTY TEST',
        option_type='CE',
        analysis=analysis,
        current_volume=1_000_000 * ratio,
        avg_volume=1_000_000,
        current_rsi=55.0,
        avg_rsi=50.0,
        ltp=100.0,
        price=100.0,
        rsi_zone='neutral',
        rsi_slope='flat',
        setup_context=f'Channel sanity test — {label}',
    )

    # Small delay so Telegram doesn't rate-limit 4 rapid posts.
    time.sleep(1.5)

print('\nDone. Check all 4 Telegram channels.')

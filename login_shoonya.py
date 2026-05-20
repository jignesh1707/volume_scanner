"""
login_shoonya.py
================
Interactive daily login for the Volume Scanner (Shoonya / Finvasia).

Run this each morning before (re)starting the scanner. The script:

  1. Reads credentials from .env (next to this script).
  2. Prompts for the 6-digit TOTP from your authenticator app.
  3. Calls NorenRestApiPy `login()` (POST /QuickAuth) to get a susertoken.
  4. Writes session_scanner.json next to this script; the scanner reads it
     at startup.

Shoonya susertokens expire EOD, so this must be run once per trading day.

Required .env keys:
    SHOONYA_USER          e.g. FA12345
    SHOONYA_PASSWORD      account password (plaintext; library SHA256s it)
    SHOONYA_VENDOR_CODE   e.g. FA12345_U
    SHOONYA_API_SECRET    "API Secret" from Shoonya Prism > API
    SHOONYA_IMEI          any non-empty device string, e.g. scanner1
"""

import json
import os
import sys
import time

import requests
from dotenv import load_dotenv
from NorenRestApiPy.NorenApi import NorenApi

SHOONYA_HOST     = "https://api.shoonya.com/NorenWClientTP/"
SHOONYA_WS       = "wss://api.shoonya.com/NorenWSTP/"
QUICKAUTH_URL    = SHOONYA_HOST + "QuickAuth"

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"))

USER        = os.getenv("SHOONYA_USER",        "")
PASSWORD    = os.getenv("SHOONYA_PASSWORD",    "")
VENDOR_CODE = os.getenv("SHOONYA_VENDOR_CODE", "")
API_SECRET  = os.getenv("SHOONYA_API_SECRET",  "")
IMEI        = os.getenv("SHOONYA_IMEI",        "scanner1")

SESSION_FILE = os.path.join(_HERE, "session_scanner.json")

required = {
    "SHOONYA_USER":        USER,
    "SHOONYA_PASSWORD":    PASSWORD,
    "SHOONYA_VENDOR_CODE": VENDOR_CODE,
    "SHOONYA_API_SECRET":  API_SECRET,
}
missing = [k for k, v in required.items() if not v]
if missing:
    print(f"ERROR: missing in .env: {', '.join(missing)}")
    sys.exit(1)

print("\n=== Shoonya Daily Login (Volume Scanner) ===\n")
totp = input("Enter 6-digit TOTP from authenticator app: ").strip()
if not (totp.isdigit() and len(totp) == 6):
    print("ERROR: TOTP must be exactly 6 digits.")
    sys.exit(1)

api = NorenApi(host=SHOONYA_HOST, websocket=SHOONYA_WS)

print("\nLogging in to Shoonya ...")
try:
    ret = api.login(
        userid=USER,
        password=PASSWORD,
        twoFA=totp,
        vendor_code=VENDOR_CODE,
        api_secret=API_SECRET,
        imei=IMEI,
    )
except ValueError as exc:
    # NorenApi.login() does json.loads(res.text) blindly; ValueError here
    # means Shoonya returned a non-JSON body (typically an empty 502/503
    # from their nginx when the upstream API is down). Probe to confirm
    # and print something actionable instead of "Expecting value: line 1
    # column 1 (char 0)".
    try:
        probe = requests.post(
            QUICKAUTH_URL, data='jData={"source":"API"}', timeout=10
        )
        if 500 <= probe.status_code < 600:
            print(f"\nERROR: Shoonya API returned HTTP {probe.status_code} ({probe.reason}).")
            print("       This is an outage on Shoonya's side — credentials are not the problem.")
            print("       Wait a few minutes and re-run. Check status: https://stat.shoonya.com/")
        else:
            print(f"\nERROR: Shoonya API returned HTTP {probe.status_code} with non-JSON body:")
            print(probe.text[:500] or "<empty body>")
    except Exception as probe_exc:
        print(f"\nERROR: login failed parsing response ({exc}); probe also failed ({probe_exc}).")
    sys.exit(1)
except Exception as exc:
    print(f"ERROR: login request failed: {exc}")
    sys.exit(1)

print(f"\nResponse:\n{json.dumps(ret or {}, indent=2)}")

if not ret or ret.get("stat") != "Ok":
    err = (ret or {}).get("emsg", "Unknown error")
    print(f"\nLOGIN FAILED: {err}")
    if "ip" in err.lower():
        print("Hint: Shoonya Prism > API > add your VPS static IPv4.")
    sys.exit(1)

session = {
    "susertoken": ret.get("susertoken", ""),
    "uid":        ret.get("actid", USER),
    "saved_date": time.strftime("%Y-%m-%d"),
}
with open(SESSION_FILE, "w") as fh:
    json.dump(session, fh, indent=2)

print(f"\nLOGIN SUCCESSFUL — session saved to {SESSION_FILE}")
print("Now run sync_shoonya.bat (or restart the scanner directly if local).")

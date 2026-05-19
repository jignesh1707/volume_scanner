"""
login_shoonya.py
================
Interactive daily login for the Volume Scanner (Shoonya / Finvasia).

Run this once each morning before (re)starting the scanner:

    cd /opt/volume_scanner
    python login_shoonya.py
    sudo systemctl restart nifty_scanner

Flow:
  1. Prints the Shoonya OAuth URL.
  2. You open it in a browser, log in, and copy the 'code' from the
     redirect URL.
  3. The code is exchanged via /NorenWClientAPI/GenAcsTok for a susertoken.
  4. The susertoken is saved to session_scanner.json next to this script;
     the scanner reads it at startup.

Shoonya access tokens expire EOD, so this must be run once per trading day.
"""

import hashlib
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()

USER   = os.getenv("SHOONYA_USER",   "")
APIKEY = os.getenv("SHOONYA_APIKEY", "")

SESSION_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "session_scanner.json",
)
ENDPOINT = "https://api.shoonya.com/NorenWClientAPI/GenAcsTok"

if not (USER and APIKEY):
    print("ERROR: SHOONYA_USER and SHOONYA_APIKEY must be set in .env")
    sys.exit(1)

oauth_url = f"https://api.shoonya.com/api/shoonya/v2/#QuickAuth?CODE={APIKEY}"

print("\n=== Shoonya Daily Login (Volume Scanner) ===\n")
print("Step 1: Open this URL in your browser and log in:\n")
print(f"    {oauth_url}\n")
print("Step 2: After login, copy the 'code' value from the redirect URL.")
print("        Example: https://...?code=XXXXXXX\n")

auth_code = input("Paste code here: ").strip()
if not auth_code:
    print("ERROR: no code entered.")
    sys.exit(1)

checksum = hashlib.sha256(f"{USER}{APIKEY}{auth_code}".encode()).hexdigest()
payload  = {"code": auth_code, "checksum": checksum}

print(f"\nExchanging code at {ENDPOINT} ...")
try:
    response = requests.post(
        ENDPOINT,
        data=f"jData={json.dumps(payload)}",
        timeout=15,
    )
    res_data = response.json()
except Exception as exc:
    print(f"ERROR: request failed: {exc}")
    sys.exit(1)

print(f"\nResponse:\n{json.dumps(res_data, indent=2)}")

if res_data.get("stat") == "Ok":
    session = {
        "access_token": res_data.get("access_token", ""),
        "susertoken":   res_data.get("susertoken",   ""),
        "uid":          res_data.get("USERID", USER),
        "saved_date":   time.strftime("%Y-%m-%d"),
    }
    with open(SESSION_FILE, "w") as fh:
        json.dump(session, fh, indent=2)
    print(f"\nLOGIN SUCCESSFUL — session saved to {SESSION_FILE}")
    print("Now restart the scanner:")
    print("    sudo systemctl restart nifty_scanner")
else:
    err = res_data.get("emsg", "Unknown error")
    print(f"\nLOGIN FAILED: {err}")
    if "ip" in err.lower():
        print("Hint: Shoonya Prism > API > add your VPS static IPv4.")
    sys.exit(1)

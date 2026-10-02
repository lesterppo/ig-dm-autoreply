#!/usr/bin/env python3
"""Export an encrypted Instagram session for the ig-vm CLI.

Runs on GitHub Actions (workflow_dispatch). Flow:
  1. Log in to Instagram with IG_USERNAME / IG_PASSWORD (instagrapi).
     If Instagram raises an email challenge and AWAIT_CHALLENGE_CODE=true,
     poll the repo for .challenge-code.json (same mechanism as dm_autoreply.py).
  2. Dump the session settings to a dict.
  3. Encrypt: random Fernet key encrypts the session JSON; the Fernet key is
     RSA-OAEP-encrypted with the operator's public key (PUBKEY_B64 env, base64
     of a PEM-encoded RSA public key). Only the holder of the private key
     (the operator's VM) can decrypt.
  4. Write automation/session.enc (uploaded as the `ig-session` artifact).

MODE=selftest skips the Instagram login and exports a dummy payload instead,
so the full dispatch -> artifact -> decrypt pipeline can be tested without
touching Instagram.

Env vars:
  IG_USERNAME, IG_PASSWORD   Instagram login (GitHub Secrets)
  PUBKEY_B64                 base64 of PEM RSA public key (workflow input)
  MODE                       "session" (default) or "selftest"
  AWAIT_CHALLENGE_CODE       "true" to poll for .challenge-code.json
  GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_REF_NAME  for challenge polling

Never prints secrets or session contents - only sizes and status.
"""

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session.enc")

# Stable device fingerprint (instagrapi 3.x) - same as dm_autoreply.py so a
# completed verification keeps counting across runs. Random identifiers,
# not secrets.
_STABLE_UUIDS = {
    "phone_id": "e6b4c29d-6908-435f-88ec-3bd9e17e8760",
    "uuid": "a3f1bdc7-41ee-4a4a-8c8b-4da97d54dddf",
    "client_session_id": "3481c650-7471-43d5-a963-2a4e3302f87d",
    "advertising_id": "973443aa-5f0c-4d46-a373-063813d4f7",
    "android_device_id": "android-409c26a6b623b92b",
    "request_id": "bb2d0c55-b1f2-4444-b5db-040b57a22cce",
    "tray_session_id": "c14b1c76-c0cf-4f38-ab1f-e09a775d00ce",
}


def log(msg):
    print(msg, flush=True)


_CHALLENGE_CODE_DEADLINE = 0.0


def _poll_challenge_code(username, choice):
    """instagrapi challenge_code_handler: poll repo for .challenge-code.json."""
    global _CHALLENGE_CODE_DEADLINE
    if _CHALLENGE_CODE_DEADLINE == 0.0:
        _CHALLENGE_CODE_DEADLINE = time.time() + 2700
        log("CHALLENGE: Instagram emailed a 6-digit verification code.")
        log("Waiting up to 45 minutes for .challenge-code.json in the repo...")
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF_NAME", "main")
    if not token or not repo:
        log("challenge poll: GITHUB_TOKEN or GITHUB_REPOSITORY missing")
        return None
    url = (f"https://api.github.com/repos/{repo}/contents/"
           f".challenge-code.json?ref={ref}")
    while time.time() < _CHALLENGE_CODE_DEADLINE:
        try:
            req = urllib.request.Request(url, headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "ig-session-export",
            })
            with urllib.request.urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode())
            raw = base64.b64decode(payload["content"]).decode()
            code = str(json.loads(raw).get("code") or "").strip()
            if code:
                log("challenge code received, submitting...")
                return code
        except urllib.error.HTTPError as e:
            if e.code != 404:
                log(f"challenge poll: HTTP {e.code}, retrying...")
        except Exception as e:  # noqa: BLE001 - transient, keep polling
            log(f"challenge poll error ({type(e).__name__}), retrying...")
        time.sleep(15)
    log("timed out waiting for the challenge code")
    return None


def get_session_dict():
    from instagrapi import Client

    username = os.environ.get("IG_USERNAME", "")
    password = os.environ.get("IG_PASSWORD", "")
    if not username or not password:
        log("missing IG_USERNAME / IG_PASSWORD")
        sys.exit(2)
    cl = Client(settings={"uuids": dict(_STABLE_UUIDS)})
    cl.delay_range = [1, 3]
    if os.environ.get("AWAIT_CHALLENGE_CODE", "").lower() == "true":
        cl.challenge_code_handler = _poll_challenge_code
    try:
        cl.login(username, password)
    except Exception as e:
        log(f"LOGIN FAILED: {type(e).__name__}")
        log("If Instagram raised a challenge, re-run with await_code=true and "
            "provide the emailed code via .challenge-code.json.")
        sys.exit(2)
    log(f"logged in ok (user id {cl.user_id})")
    return cl.get_settings()


def encrypt_payload(payload_dict, pubkey_b64):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.fernet import Fernet

    pubkey_pem = base64.b64decode(pubkey_b64)
    pubkey = serialization.load_pem_public_key(pubkey_pem)
    fernet_key = Fernet.generate_key()
    token = Fernet(fernet_key).encrypt(
        json.dumps(payload_dict).encode())
    enc_key = pubkey.encrypt(
        fernet_key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))
    return {
        "v": 1,
        "key": base64.b64encode(enc_key).decode(),
        "data": token.decode(),
    }


def main():
    pubkey_b64 = os.environ.get("PUBKEY_B64", "").strip()
    if not pubkey_b64:
        log("missing PUBKEY_B64")
        return 1
    mode = os.environ.get("MODE", "session").strip().lower()

    if mode == "selftest":
        payload = {"selftest": True,
                   "exported_at": int(time.time()),
                   "note": "pipeline test - no Instagram login performed"}
        log("selftest mode: skipping Instagram login")
    elif mode == "session":
        payload = get_session_dict()
    else:
        log(f"unknown MODE={mode!r} (want session|selftest)")
        return 1

    envelope = encrypt_payload(payload, pubkey_b64)
    with open(OUT_PATH, "w") as f:
        json.dump(envelope, f)
    size = os.path.getsize(OUT_PATH)
    log(f"wrote {OUT_PATH} ({size} bytes, encrypted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

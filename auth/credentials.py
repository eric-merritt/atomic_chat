"""Encrypted credential store for agent-authenticated requests.

Credentials are stored AES-encrypted in ~/.agent_credentials.enc
using a machine-local key derived from hostname + username.
Credentials are referenced by alias — the agent never sees raw secrets.

CLI usage:
    python credentials.py add mysite --url https://example.com --username foo --password bar
    python credentials.py add api_thing --url https://api.example.com --api-key sk-abc123
    python credentials.py add cookiesite --url https://example.com --cookie "session=xyz; token=abc"
    python credentials.py list
    python credentials.py remove mysite
    python credentials.py set-master-password
"""

import base64
import getpass
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

# Optional: use cryptography if installed, otherwise fall back to XOR obfuscation
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

CRED_FILE = Path.home() / ".agent_credentials.enc"
MASTER_FILE = Path.home() / ".agent_credentials_master"


def _machine_key() -> bytes:
    """Derive a machine-local key from hostname + username."""
    identity = f"{platform.node()}:{getpass.getuser()}:agent_cred_store_v1"
    return hashlib.sha256(identity.encode()).digest()


def _get_key() -> bytes:
    """Get encryption key: master password if set, otherwise machine key."""
    if MASTER_FILE.exists():
        salt = MASTER_FILE.read_bytes()
        # Master password is baked into the salt file as a hash
        return hashlib.sha256(salt).digest()
    return _machine_key()


def _encrypt(data: bytes, key: bytes) -> bytes:
    if _HAS_CRYPTO:
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, data, None)
        return nonce + ct
    else:
        # XOR fallback — not secure against targeted attacks,
        # but prevents casual reading of the file
        extended = (key * (len(data) // len(key) + 1))[:len(data)]
        xored = bytes(a ^ b for a, b in zip(data, extended))
        return b"XOR1" + xored


def _decrypt(blob: bytes, key: bytes) -> bytes:
    if blob[:4] == b"XOR1":
        data = blob[4:]
        extended = (key * (len(data) // len(key) + 1))[:len(data)]
        return bytes(a ^ b for a, b in zip(data, extended))
    if _HAS_CRYPTO:
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(key).decrypt(nonce, ct, None)
    raise RuntimeError("Credential file was encrypted with cryptography library which is not installed")


def load_credentials() -> dict[str, dict]:
    """Load all credentials from the store. Returns {alias: {url, type, ...}}."""
    if not CRED_FILE.exists():
        return {}
    try:
        blob = CRED_FILE.read_bytes()
        raw = _decrypt(blob, _get_key())
        return json.loads(raw)
    except Exception as e:
        print(f"Warning: Could not decrypt credentials: {e}", file=sys.stderr)
        return {}


def save_credentials(creds: dict[str, dict]) -> None:
    """Save credentials to the encrypted store."""
    raw = json.dumps(creds, indent=2).encode()
    blob = _encrypt(raw, _get_key())
    CRED_FILE.write_bytes(blob)
    CRED_FILE.chmod(0o600)


def add_credential(alias: str, url: str, cred_type: str = "basic", **kwargs) -> None:
    """Add or update a credential.

    cred_type: "basic" (username/password), "api_key", "cookie", "bearer"
    """
    creds = load_credentials()
    entry = {"url": url, "type": cred_type}
    entry.update(kwargs)
    creds[alias] = entry
    save_credentials(creds)


def remove_credential(alias: str) -> bool:
    creds = load_credentials()
    if alias in creds:
        del creds[alias]
        save_credentials(creds)
        return True
    return False


def get_credential(alias: str) -> dict | None:
    """Get a credential by alias. Returns the full entry dict or None."""
    creds = load_credentials()
    return creds.get(alias)


def list_credentials() -> list[dict]:
    """List credentials with secrets masked."""
    creds = load_credentials()
    result = []
    for alias, entry in creds.items():
        masked = {"alias": alias, "url": entry.get("url", ""), "type": entry.get("type", "")}
        if entry.get("username"):
            masked["username"] = entry["username"]
        if entry.get("password"):
            masked["password"] = entry["password"][:2] + "***"
        if entry.get("api_key"):
            masked["api_key"] = entry["api_key"][:6] + "***"
        if entry.get("cookie"):
            masked["cookie"] = entry["cookie"][:20] + "***"
        if entry.get("token"):
            masked["token"] = entry["token"][:6] + "***"
        result.append(masked)
    return result


def build_auth_headers(alias: str) -> dict[str, str]:
    """Build HTTP headers for a credential. Returns headers dict."""
    cred = get_credential(alias)
    if not cred:
        raise ValueError(f"No credential found for alias: {alias}")

    headers = {}
    cred_type = cred.get("type", "basic")

    if cred_type == "basic":
        username = cred.get("username", "")
        password = cred.get("password", "")
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {token}"
    elif cred_type == "bearer":
        headers["Authorization"] = f"Bearer {cred.get('token', '')}"
    elif cred_type == "api_key":
        # Common patterns — X-API-Key or Authorization
        key = cred.get("api_key", "")
        header_name = cred.get("header", "X-API-Key")
        headers[header_name] = key
    elif cred_type == "cookie":
        headers["Cookie"] = cred.get("cookie", "")

    return headers


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Agent credential store")
    sub = parser.add_subparsers(dest="command")

    add_p = sub.add_parser("add", help="Add a credential")
    add_p.add_argument("alias", help="Short name for this credential")
    add_p.add_argument("--url", required=True, help="Base URL for the site")
    add_p.add_argument("--username", help="Username (for basic auth)")
    add_p.add_argument("--password", help="Password (for basic auth, prompts if --username set but omitted)")
    add_p.add_argument("--api-key", help="API key")
    add_p.add_argument("--bearer-token", help="Bearer token")
    add_p.add_argument("--cookie", help="Cookie string")
    add_p.add_argument("--header", default="X-API-Key", help="Header name for API key (default: X-API-Key)")

    sub.add_parser("list", help="List stored credentials (masked)")

    rm_p = sub.add_parser("remove", help="Remove a credential")
    rm_p.add_argument("alias", help="Alias to remove")

    master_p = sub.add_parser("set-master-password", help="Set a master password for encryption")

    args = parser.parse_args()

    if args.command == "add":
        if args.api_key:
            add_credential(args.alias, args.url, "api_key",
                           api_key=args.api_key, header=args.header)
        elif args.bearer_token:
            add_credential(args.alias, args.url, "bearer",
                           token=args.bearer_token)
        elif args.cookie:
            add_credential(args.alias, args.url, "cookie",
                           cookie=args.cookie)
        elif args.username:
            password = args.password
            if not password:
                password = getpass.getpass(f"Password for {args.username}@{args.url}: ")
            add_credential(args.alias, args.url, "basic",
                           username=args.username, password=password)
        else:
            print("ERROR: Provide --username, --api-key, --bearer-token, or --cookie")
            sys.exit(1)
        print(f"Saved credential: {args.alias}")

    elif args.command == "list":
        creds = list_credentials()
        if not creds:
            print("No stored credentials.")
        else:
            for c in creds:
                print(f"  {c['alias']:20s}  {c['type']:8s}  {c['url']}")
                for k in ("username", "password", "api_key", "cookie", "token"):
                    if k in c:
                        print(f"    {k}: {c[k]}")

    elif args.command == "remove":
        if remove_credential(args.alias):
            print(f"Removed: {args.alias}")
        else:
            print(f"Not found: {args.alias}")

    elif args.command == "set-master-password":
        pw = getpass.getpass("New master password: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("Passwords don't match.")
            sys.exit(1)
        # Re-encrypt existing credentials with new key
        old_creds = load_credentials()
        salt = hashlib.sha256(pw.encode()).digest() + os.urandom(16)
        MASTER_FILE.write_bytes(salt)
        MASTER_FILE.chmod(0o600)
        save_credentials(old_creds)
        print("Master password set. Existing credentials re-encrypted.")

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli()

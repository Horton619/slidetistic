"""HTTPS GETs for the free-font downloader (F009).

python.org's Python (and so the PyInstaller engine) doesn't read the macOS keychain: plain urllib fails with
CERTIFICATE_VERIFY_FAILED (found 2026-10-12). Use the OS trust store via `truststore` (also right behind venue
proxies with their own certificate), then certifi's bundle, then Python's default.
"""
from __future__ import annotations

import ssl
import urllib.request

USER_AGENT = "SlideTistic (+https://veproductions.net)"


def _context() -> ssl.SSLContext:
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 — fall through to the next trust source
        pass
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


_CTX = None


def get(url: str, *, user_agent: str = USER_AGENT, timeout: float = 30) -> bytes:
    global _CTX
    _CTX = _CTX or _context()
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read()

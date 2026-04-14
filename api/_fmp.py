# _fmp.py — graceful 403 handling
# FMP free tier blocks many endpoints; we catch 403/401 and return None
# so callers (macro.py, etf_holdings.py, etc.) can fall back cleanly.

import json
import urllib.request
import urllib.parse
import os
from urllib.error import HTTPError

FMP_KEY = os.environ.get("FMP_API_KEY", "demo")
BASE    = "https://financialmodelingprep.com"


def fmp(path: str, **params) -> object:
    """Call FMP REST API. Returns parsed JSON or None on 403/empty."""
    params["apikey"] = FMP_KEY
    qs  = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 AlphaVault/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except HTTPError as e:
        if e.code in (401, 403):
            # Endpoint gated behind paid plan — return None silently
            return None
        raise

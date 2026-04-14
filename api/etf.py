"""Combined ETF endpoint: holdings + sectors
   GET /api/etf?ticker=SPY&type=holdings
   GET /api/etf?ticker=SPY&type=sectors
"""
from http.server import BaseHTTPRequestHandler
import json
from urllib.parse import urlparse, parse_qs

# Import the existing logic from etf_holdings and etf_sectors
import importlib, os, sys
sys.path.insert(0, os.path.dirname(__file__))

from etf_holdings import get_etf_holdings
from etf_sectors import get_etf_sectors


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or params.get("symbol") or [""])[0].strip()
        etype  = (params.get("type") or ["holdings"])[0].lower()
        limit  = int((params.get("limit") or ["25"])[0])

        if not ticker:
            self._respond(400, {"error": "ticker param required"})
            return

        if etype == "sectors":
            self._respond(200, get_etf_sectors(ticker))
        else:
            self._respond(200, get_etf_holdings(ticker, min(limit, 50)))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors(); self.end_headers()

    def _respond(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *a): pass

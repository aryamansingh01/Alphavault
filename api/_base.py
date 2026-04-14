from http.server import BaseHTTPRequestHandler
import json


class BaseHandler(BaseHTTPRequestHandler):
    def _ok(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, code=500):
        body = json.dumps({"error": str(msg)}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        # Strategy 1: direct injection from dev_server
        raw = getattr(self, "_injected_body", None)
        if raw:
            return json.loads(raw)

        # Strategy 2: read rfile
        try:
            raw = self.rfile.read()
        except Exception:
            raw = b""

        if raw:
            # 2a. rfile has full HTTP request — extract after blank line
            if b"\r\n\r\n" in raw:
                candidate = raw.split(b"\r\n\r\n", 1)[1].strip()
                if candidate:
                    return json.loads(candidate)
            # 2b. rfile has body only
            raw = raw.strip()
            if raw:
                return json.loads(raw)

        # Strategy 3: Content-Length (Vercel native)
        n = int(self.headers.get("Content-Length") or 0)
        if n > 0:
            self.rfile.seek(0)
            return json.loads(self.rfile.read(n))

        return {}

    def _qs(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        return {k: v[0] for k, v in q.items()}

    def _json(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

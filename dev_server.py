#!/usr/bin/env python3
import io, json, os, importlib.util, traceback, email
from flask import Flask, request, Response
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__, static_folder='.', static_url_path='')

class _MockServer:
    server_name = 'localhost'
    server_port = 3000

def _call_vercel_handler(module_path: str, flask_req):
    spec = importlib.util.spec_from_file_location("_api_mod", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    HandlerClass = mod.handler
    wfile = io.BytesIO()
    body = flask_req.get_data()

    req_line = f"{flask_req.method} {flask_req.full_path} HTTP/1.1\r\n"
    headers_str = "".join(f"{k}: {v}\r\n" for k, v in flask_req.headers.items())
    raw_req = (req_line + headers_str + "\r\n").encode()
    if body:
        raw_req += body
    rfile = io.BytesIO(raw_req)

    h = HandlerClass.__new__(HandlerClass)
    h.rfile = rfile
    h.wfile = wfile
    h.path = flask_req.full_path
    h.command = flask_req.method
    h.server = _MockServer()
    h.client_address = ("127.0.0.1", 0)
    h.request_version = "HTTP/1.1"
    h.requestline = f"{flask_req.method} {flask_req.full_path} HTTP/1.1"
    h.close_connection = True
    h.log_message = lambda fmt, *a: None
    h.log_request = lambda *a: None
    h.log_error = lambda fmt, *a: print(f"handler error: {fmt % a}")

    hdr_text = "".join(f"{k}: {v}\r\n" for k, v in flask_req.headers.items()) + "\r\n"
    h.headers = email.message_from_string(hdr_text)

    method_fn = getattr(h, f"do_{flask_req.method}", None)
    if method_fn:
        method_fn()
    else:
        h.send_response(405)
        h.end_headers()

    wfile.seek(0)
    raw_resp = wfile.read()

    if b"\r\n\r\n" in raw_resp:
        hdr_bytes, body_bytes = raw_resp.split(b"\r\n\r\n", 1)
        lines = hdr_bytes.decode("utf-8", errors="replace").split("\r\n")
        try:
            status_code = int(lines[0].split(" ")[1])
        except Exception:
            status_code = 200

        resp_headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                resp_headers[k.strip()] = v.strip()

        resp = Response(body_bytes, status=status_code)
        for k, v in resp_headers.items():
            if k.lower() not in ("content-length", "transfer-encoding"):
                resp.headers[k] = v
    else:
        resp = Response(raw_resp, status=200, content_type="application/json")

    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/api/<path:api_path>", methods=["GET", "POST", "OPTIONS"])
def api_route(api_path):
    if request.method == "OPTIONS":
        r = Response("")
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return r

    module_name = api_path.split("/")[0]
    mapping = {
        "portfolioanalytics": "portfolio_analytics",
        "efficientfrontier": "efficient_frontier",
        "etfholdings": "etf_holdings",
        "etfsectors": "etf_sectors",
        "stresstest": "stress_test",
        "options": "options",
    }
    file_name = mapping.get(module_name, module_name.replace("-", "_"))
    mod_path = os.path.join("api", f"{file_name}.py")

    if not os.path.exists(mod_path):
        return Response(json.dumps({"error": f"API not found: /api/{module_name}"}), status=404, content_type="application/json")

    try:
        print(f"→ {request.method} /api/{module_name}")
        return _call_vercel_handler(mod_path, request)
    except Exception as e:
        print(traceback.format_exc())
        return Response(json.dumps({"error": str(e)}), status=500, content_type="application/json")

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_static(path):
    if not path:
        return app.send_static_file("index.html")
    try:
        return app.send_static_file(path)
    except Exception:
        return app.send_static_file("index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    is_prod = os.environ.get("RENDER") or os.environ.get("NODE_ENV") == "production"
    print(f"AlphaVault running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=not is_prod, use_reloader=False)
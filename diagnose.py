#!/usr/bin/env python3
"""Run this to test all API endpoints before starting the server.
   Usage:  python diagnose.py
"""
import subprocess, sys, json

BASE = "http://localhost:3000"
TESTS = [
    ("GET",  "/api/quote?ticker=AAPL", None),
    ("GET",  "/api/macro",             None),
    ("POST", "/api/correlation",       ["AAPL","MSFT","NVDA"]),
    ("POST", "/api/drawdown",          ["AAPL","MSFT"]),
    ("POST", "/api/dividends",         [{"ticker":"AAPL","shares":10},{"ticker":"SCHD","shares":20}]),
    ("POST", "/api/portfolio_analytics",
             {"holdings":[{"ticker":"AAPL","weight":0.5},{"ticker":"MSFT","weight":0.5}]}),
    ("POST", "/api/efficient_frontier",
             {"holdings":[{"ticker":"AAPL","weight":0.3},{"ticker":"MSFT","weight":0.3},
                          {"ticker":"NVDA","weight":0.4}]}),
    ("POST", "/api/montecarlo",
             {"holdings":[{"ticker":"SPY","weight":1}],"years":20,"simulations":200,
              "nav":10000,"monthlyContrib":500}),
    ("POST", "/api/stress_test",
             {"holdings":[{"ticker":"AAPL","weight":0.5},{"ticker":"SPY","weight":0.5}]}),
]

import requests, time
print("\n  AlphaVault — API Diagnostics\n  " + "─"*40)
ok = 0
for method, path, body in TESTS:
    try:
        if method == "GET":
            r = requests.get(BASE + path, timeout=30)
        else:
            r = requests.post(BASE + path, json=body, timeout=30)
        status = "✅" if r.status_code == 200 else "❌"
        if r.status_code == 200: ok += 1
        try:   preview = str(list(r.json().keys()))[:60]
        except: preview = r.text[:60]
        print(f"  {status} {method:4} {path:40} {r.status_code}  {preview}")
    except Exception as e:
        print(f"  ⚠ {method:4} {path:40} FAILED: {e}")

print(f"\n  Result: {ok}/{len(TESTS)} endpoints passing\n")

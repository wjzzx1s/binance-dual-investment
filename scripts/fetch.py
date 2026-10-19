#!/usr/bin/env python3
"""Fetch a fresh snapshot of Binance BTC/USDT Dual Investment and options data.

The report in report/main.tex uses the snapshot committed in data/ (19 Oct 2026
16:10 UTC). Re-running this script overwrites that snapshot with a new one, so
the report numbers will no longer match unless analyze.py and make_report_data.py
are run again.

Public endpoints, no API key:
  * spot:        api.binance.com/api/v3/ticker/price
  * dual invest: www.binance.com/bapi/earn/v5/friendly/pos/dc/project/list
  * options:     eapi.binance.com/eapi/v1/exchangeInfo, /eapi/v1/mark
"""
import json
import datetime as dt
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

HEADERS = {
    "clienttype": "web",
    "lang": "en",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/140.0 Safari/537.36",
}


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_dual_investment():
    products = {}
    for typ, invest, target in [("DOWN", "USDT", "BTC"), ("UP", "BTC", "USDT")]:
        rows = []
        page = 1
        total = None
        while True:
            query = urllib.parse.urlencode({
                "investmentAsset": invest,
                "targetAsset": target,
                "projectType": typ,
                "sortType": "APY_DESC",
                "pageIndex": page,
                "pageSize": 100,
            })
            url = ("https://www.binance.com/bapi/earn/v5/friendly/pos/dc/"
                   f"project/list?{query}")
            payload = get_json(url, HEADERS)
            if payload.get("code") != "000000":
                raise RuntimeError(f"Dual Investment API error: {payload}")
            data = payload["data"]
            total = int(data["total"])
            rows.extend(data["list"])
            print(f"{typ}: page {page}, {len(rows)}/{total}")
            if len(rows) >= total:
                break
            page += 1
            time.sleep(0.3)
        products[typ] = rows
    return products


def main():
    spot = get_json("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT")
    products = fetch_dual_investment()
    snapshot = {
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "spot": spot,
        "products": products,
    }
    (DATA / "dual_investment_raw.json").write_text(json.dumps(snapshot, indent=1))
    print("wrote", DATA / "dual_investment_raw.json")

    for name, url in [
        ("option_exchangeinfo_raw.json", "https://eapi.binance.com/eapi/v1/exchangeInfo"),
        ("option_mark_raw.json", "https://eapi.binance.com/eapi/v1/mark"),
    ]:
        payload = get_json(url)
        (DATA / name).write_text(json.dumps(payload, indent=1))
        print("wrote", DATA / name)

    print("spot", spot["price"], "DOWN", len(products["DOWN"]), "UP", len(products["UP"]))


if __name__ == "__main__":
    main()

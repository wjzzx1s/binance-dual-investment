#!/usr/bin/env python3
"""Price Binance Dual Investment (Buy Low) against the option-implied surface.

Model: S_t GBM under Q, dS/S = r dt + sigma dW.
Given payoff per 1 USDT at T (the Binance-matching form):
    X_T = e^{theta (T-t)} [ (S_T/K) 1_{S_T<K} + 1_{S_T>=K} ]
fair theta solves E^Q[e^{-r(T-t)} X_T] = 1:
    V0 = (S/K) N(-d1) + e^{-r tau} N(d2)
    theta = -ln(V0) / tau
The fair simple APR on Binance's day count is a* = (365/n)(1/V0 - 1).
"""
import json
import math
from pathlib import Path
import datetime as dt
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parents[1])
ND = NormalDist()
YEAR_DAYS = 365.0


def norm(x):
    return ND.cdf(x)


def load_data():
    raw = json.load(open(f"{ROOT}/data/dual_investment_raw.json"))
    info = json.load(open(f"{ROOT}/data/option_exchangeinfo_raw.json"))
    marks = {m["symbol"]: m for m in json.load(open(f"{ROOT}/data/option_mark_raw.json"))}
    t0 = dt.datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00"))
    return raw, info, marks, t0


def build_surface(info, marks, S, t0):
    """Return list of (tau, strikes, ivs, r) sorted by tau, IV interpolated in log(K/S)."""
    by_exp = {}
    for s in info["optionSymbols"]:
        if s["underlying"] != "BTCUSDT":
            continue
        m = marks.get(s["symbol"])
        if not m:
            continue
        by_exp.setdefault(s["expiryDate"], []).append(
            (float(s["strikePrice"]), s["side"], float(m["markIV"]), float(m["riskFreeInterest"]))
        )
    surface = []
    for exp, rows in sorted(by_exp.items()):
        tau = (exp / 1000 - t0.timestamp()) / (YEAR_DAYS * 86400)
        if tau <= 0:
            continue
        strikes = sorted({r[0] for r in rows})
        iv_call = {r[0]: r[2] for r in rows if r[1] == "CALL"}
        iv_put = {r[0]: r[2] for r in rows if r[1] == "PUT"}
        ks, ivs = [], []
        for k in strikes:
            # OTM option is the cleaner quote; fall back to the other side.
            if k >= S and k in iv_call:
                iv = iv_call[k]
            elif k < S and k in iv_put:
                iv = iv_put[k]
            elif k in iv_call:
                iv = iv_call[k]
            elif k in iv_put:
                iv = iv_put[k]
            else:
                continue
            ks.append(k)
            ivs.append(iv)
        r = float(np.median([x[3] for x in rows]))
        surface.append({"tau": tau, "K": np.array(ks), "iv": np.array(ivs), "r": r, "exp": exp})
    return surface


def interp_iv(surface, K, tau):
    """Total-variance interpolation in tau, linear in log-moneyness at each expiry."""
    x = math.log(K / SPOT)
    taus = np.array([s["tau"] for s in surface])
    if tau <= taus[0]:
        s = surface[0]
        return float(np.interp(x, np.log(s["K"] / SPOT), s["iv"])), s["r"]
    if tau >= taus[-1]:
        s = surface[-1]
        return float(np.interp(x, np.log(s["K"] / SPOT), s["iv"])), s["r"]
    i = int(np.searchsorted(taus, tau))
    s1, s2 = surface[i - 1], surface[i]
    v1 = np.interp(x, np.log(s1["K"] / SPOT), s1["iv"])
    v2 = np.interp(x, np.log(s2["K"] / SPOT), s2["iv"])
    w1, w2 = v1 * v1 * s1["tau"], v2 * v2 * s2["tau"]
    w = w1 + (w2 - w1) * (tau - s1["tau"]) / (s2["tau"] - s1["tau"])
    r = s1["r"] + (s2["r"] - s1["r"]) * (tau - s1["tau"]) / (s2["tau"] - s1["tau"])
    return math.sqrt(max(w / tau, 0.0)), r


def fair_apr_binance(K, tau, sig, r, n):
    """Fair simple APR for Binance's payoff (reward paid in both branches)."""
    sq = math.sqrt(tau)
    d1 = (math.log(SPOT / K) + (r + 0.5 * sig * sig) * tau) / (sig * sq)
    d2 = d1 - sig * sq
    V0 = (SPOT / K) * norm(-d1) + math.exp(-r * tau) * norm(d2)
    return (YEAR_DAYS / n) * (1 / V0 - 1)


def implied_pricing_vol(K, tau, r, n, a_q):
    """Lower-root sigma such that the quoted APR is fair; None if quote < r."""
    lo, hi = 0.01, 2.0
    flo = fair_apr_binance(K, tau, lo, r, n) - a_q
    fhi = fair_apr_binance(K, tau, hi, r, n) - a_q
    if flo > 0 or fhi < 0:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        fm = fair_apr_binance(K, tau, mid, r, n) - a_q
        if fm < 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


raw, info, marks, t0 = load_data()
SPOT = float(raw["spot"]["price"])
surface = build_surface(info, marks, SPOT, t0)

rows = []
for p in raw["products"]["DOWN"]:
    K = float(p["strikePrice"])
    settle = int(p["settleTime"]) / 1000
    tau = (settle - t0.timestamp()) / (YEAR_DAYS * 86400)
    n = float(p["displayDuration"]) if p["displayDurationUnit"] == "DAY" else 1.0  # 8H => 1 accrual day
    iv, r = interp_iv(surface, K, tau)
    sq = math.sqrt(tau)
    d1 = (math.log(SPOT / K) + (r + 0.5 * iv * iv) * tau) / (iv * sq)
    d2 = d1 - iv * sq
    A = (SPOT / K) * norm(-d1)
    B = math.exp(-r * tau) * norm(d2)
    V0 = A + B
    a_q = float(p["apr"])
    R_q = a_q * n / YEAR_DAYS
    PV = (1 + R_q) * V0
    a_fair = (YEAR_DAYS / n) * (1 / V0 - 1)
    theta_fair = -math.log(V0) / tau
    theta_q = math.log(1 + R_q) / tau
    sig_star = implied_pricing_vol(K, tau, r, n, a_q)
    rows.append(
        dict(
            id=p["id"], settle=dt.datetime.fromtimestamp(settle, dt.UTC), tau=tau, n=n,
            K=K, S=SPOT, moneyness=K / SPOT - 1, iv=iv, r=r,
            d1=d1, d2=d2, A=A, B=B, V0=V0,
            apr_quote=a_q, flat_reward_q=R_q, pv_quote=PV, cost=1 - PV,
            apr_fair=a_fair, theta_fair=theta_fair, theta_quote=theta_q,
            ratio=a_q / a_fair, sigma_star=sig_star, sigma_ratio=(sig_star / iv if sig_star else float("nan")),
        )
    )

df = pd.DataFrame(rows).sort_values(["settle", "K"])
df.to_csv(f"{ROOT}/data/analysis_buy_low.csv", index=False)

print(f"spot={SPOT:,.2f}  t0={t0.isoformat()}  products={len(df)}")
print("\nATM IV term structure (interpolated at K=spot):")
for s in surface:
    iv, r = interp_iv(surface, SPOT, s["tau"])
    print(f"  {dt.datetime.fromtimestamp(s['exp']/1000, dt.UTC):%Y-%m-%d}  tau={s['tau']*365:6.2f}d  iv={iv:6.1%}  r={r:5.2%}")

print("\nHeadline products (closest strike to spot per expiry):")
idx = df.groupby("settle")["moneyness"].apply(lambda s: s.abs().idxmin())
cols = ["settle", "n", "K", "moneyness", "iv", "apr_quote", "apr_fair", "ratio", "cost"]
pd.set_option("display.width", 200)
print(df.loc[idx, cols].to_string(index=False, formatters={
    "settle": lambda x: x.strftime("%m-%d %H:%M"), "K": "{:,.0f}".format,
    "moneyness": "{:+.2%}".format, "iv": "{:.1%}".format, "apr_quote": "{:.1%}".format,
    "apr_fair": "{:.1%}".format, "ratio": "{:.2f}".format, "cost": "{:.3%}".format}))

print("\nCost (1-PV per 1 USDT) summary by tenor bucket:")
df["tenor"] = pd.cut(df.n, [0, 1, 4, 10, 30, 200], labels=["<=1d", "2-4d", "5-10d", "11-30d", ">30d"])
print(df.groupby("tenor", observed=True).agg(n=("id", "count"), cost_mean=("cost", "mean"),
      cost_med=("cost", "median"), ratio_med=("ratio", "median")).to_string(
      formatters={"cost_mean": "{:.3%}".format, "cost_med": "{:.3%}".format, "ratio_med": "{:.2f}".format}))

print("\nCost summary by |moneyness| bucket:")
df["mny"] = pd.cut(df.moneyness.abs(), [0, .005, .01, .02, .05, 1],
                   labels=["<0.5%", "0.5-1%", "1-2%", "2-5%", ">5%"])
print(df.groupby("mny", observed=True).agg(n=("id", "count"), cost_mean=("cost", "mean"),
      cost_med=("cost", "median"), ratio_med=("ratio", "median")).to_string(
      formatters={"cost_mean": "{:.3%}".format, "cost_med": "{:.3%}".format, "ratio_med": "{:.2f}".format}))

print("\nImplied pricing vol vs listed IV, by tenor bucket (simple-APR products only):")
d2 = df[df.n >= 2].copy()
d2["tenor"] = pd.cut(d2.n, [1, 4, 10, 30, 200], labels=["2-4d", "5-10d", "11-30d", ">30d"])
print(d2.groupby("tenor", observed=True).agg(n=("id", "count"), sig_star_med=("sigma_star", "median"),
      iv_med=("iv", "median"), vol_ratio_med=("sigma_ratio", "median")).to_string(
      formatters={"sig_star_med": "{:.1%}".format, "iv_med": "{:.1%}".format, "vol_ratio_med": "{:.2f}".format}))
print("no root / quote below r:", int(df.sigma_star.isna().sum()), "of", len(df))

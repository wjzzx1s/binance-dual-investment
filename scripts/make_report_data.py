#!/usr/bin/env python3
"""Build the CSV inputs and LaTeX rows used in report/main.tex."""
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

ROOT = str(Path(__file__).resolve().parents[1])
N = NormalDist().cdf
S = 81990.33


def theta_scaled(K, tau, sig, r):
    d1 = (math.log(S / K) + (r + 0.5 * sig * sig) * tau) / (sig * math.sqrt(tau))
    d2 = d1 - sig * math.sqrt(tau)
    V0 = (S / K) * N(-d1) + math.exp(-r * tau) * N(d2)
    return -math.log(V0) / tau


df = pd.read_csv(f"{ROOT}/data/analysis_buy_low.csv", parse_dates=["settle"])
d = df[df.n >= 2].copy()

# ---- theta vs sigma curves -------------------------------------------------
sig_grid = np.linspace(0.10, 0.60, 51)
rows = []
for sig in sig_grid:
    rows.append({
        "sigma_pct": 100 * sig,
        "atm_2d": 100 * theta_scaled(S, 2 / 365, sig, 0.053),
        "otm03_2d": 100 * theta_scaled(0.997 * S, 2 / 365, sig, 0.053),
        "atm_30d": 100 * theta_scaled(S, 30 / 365, sig, 0.053),
        "otm06_30d": 100 * theta_scaled(0.994 * S, 30 / 365, sig, 0.053),
    })
pd.DataFrame(rows).to_csv(f"{ROOT}/report/data/theta_sigma.csv", index=False)

# ---- term structure --------------------------------------------------------
rows = []
for settle, g in d.groupby("settle"):
    i = g.moneyness.abs().idxmin()
    r = g.loc[i]
    rows.append({
        "days": r.tau * 365,
        "iv_pct": 100 * r.iv,
        "quoted_pct": 100 * r.apr_quote,
        "fair_pct": 100 * r.apr_fair,
        "n": r.n,
        "K": r.K,
    })
pd.DataFrame(rows).sort_values("days").to_csv(f"{ROOT}/report/data/term_structure.csv", index=False)

# ---- scatter by tenor ------------------------------------------------------
for name, sub in [("short", d[d.n <= 4]), ("mid", d[(d.n > 4) & (d.n <= 30)]), ("long", d[d.n > 30])]:
    out = pd.DataFrame({
        "fair_pct": 100 * sub.apr_fair,
        "quote_pct": 100 * sub.apr_quote,
        "cost_pct": 100 * sub.cost,
        "days": sub.tau * 365,
        "mny_pct": 100 * sub.moneyness,
    })
    out.to_csv(f"{ROOT}/report/data/scatter_{name}.csv", index=False)

# ---- cost vs days ----------------------------------------------------------
pd.DataFrame({
    "days": d.tau * 365,
    "cost_pct": 100 * d.cost,
    "mny_pct": 100 * d.moneyness,
    "n": d.n,
}).to_csv(f"{ROOT}/report/data/cost_days.csv", index=False)

for name, sub in [("near", df[df.moneyness.abs() <= 0.02]),
                  ("mid", df[(df.moneyness.abs() > 0.02) & (df.moneyness.abs() <= 0.05)]),
                  ("far", df[df.moneyness.abs() > 0.05])]:
    pd.DataFrame({
        "days": sub.tau * 365,
        "cost_pct": 100 * sub.cost,
    }).to_csv(f"{ROOT}/report/data/cost_{name}.csv", index=False)

# ---- LaTeX case table ------------------------------------------------------
cases = [
    ("2026-10-20", 81750), ("2026-10-21", 81750), ("2026-10-23", 81500),
    ("2026-10-30", 81500), ("2026-11-27", 81500), ("2027-03-26", 81500),
    ("2026-11-27", 67500),
]
print("% case table rows")
for date, K in cases:
    sub = df[df.settle.dt.strftime("%Y-%m-%d") == date]
    r = sub[sub.K == K].iloc[0]
    print(f"{r.settle:%b {r.settle.day}} & {r.n:.0f} & {r.tau*365:.1f} & {r.K:,.0f} & "
          f"{100*r.moneyness:+.2f} & {100*r.iv:.1f} & {100*r.apr_quote:.1f} & {100*r.apr_fair:.1f} & "
          f"{r.ratio:.2f} & {100*r.cost:.2f} & {100*r.theta_fair:.0f} & "
          f"{'--' if np.isnan(r.sigma_star) else f'{100*r.sigma_star:.1f}'} \\\\")

# ---- LaTeX aggregate table ------------------------------------------------
print("% aggregate table rows")
for label, sub in [("2--4 d", d[d.n <= 4]), ("5--10 d", d[(d.n > 4) & (d.n <= 10)]),
                   ("11--30 d", d[(d.n > 10) & (d.n <= 30)]), (">30 d", d[d.n > 30]),
                   ("all", d)]:
    print(f"{label} & {len(sub)} & {100*sub.apr_quote.median():.1f} & {100*sub.apr_fair.median():.1f} & "
          f"{sub.ratio.median():.2f} & {100*sub.cost.median():.2f} & "
          f"{100*sub.sigma_star.median():.1f} & {100*sub.iv.median():.1f} \\\\")

print("% summary")
print("n", len(d), "cost med", 100*d.cost.median(), "cost max", 100*d.cost.max(),
      "ratio med", d.ratio.median(), "PV<1", (d.pv_quote < 1).mean(),
      "aq<r", (df.apr_quote < df.r).sum(), "no sigma*", df.sigma_star.isna().sum())
print("quoted range", 100*df.apr_quote.min(), 100*df.apr_quote.max())
print("days range", (df.tau*365).min(), (df.tau*365).max())
print("strikes", df.K.min(), df.K.max(), "mny", 100*df.moneyness.min(), 100*df.moneyness.max())
print("theta atm 2d r5.3 sig29", 100*theta_scaled(S, 2/365, 0.29, 0.053))
print("theta otm03 2d r5.3 sig29", 100*theta_scaled(0.997*S, 2/365, 0.29, 0.053))

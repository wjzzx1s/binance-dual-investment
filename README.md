# Binance Dual Investment: fair value of the embedded short put

This project prices the one-unit structured note

```
payoff at T = exp(theta*(T-t)) * [ (S_T/K) * 1{S_T<K} + 1{S_T>=K} ]
```

under risk-neutral geometric Brownian motion, and compares the result with the
live Binance BTC/USDT Dual Investment "Buy Low" book.

The bracket multiplies the exponential. Binance's Buy Low settlement is
`(1+R)[...]`; with `exp(theta*tau)=1+R` this is the form above. Putting the
bracket inside the exponent would be a different, non-Binance contract.

## Layout

```
data/        raw JSON snapshots + analysis_buy_low.csv (one row per product)
scripts/     fetch.py -> analyze.py -> make_report_data.py
report/      main.tex, main.pdf, data/*.csv used by pgfplots
figures/     spare output directory
```

## Reproduce

```bash
python3 -m venv .venv
.venv/bin/pip install numpy pandas matplotlib
make fetch       # optional: overwrites the snapshot with live data
make analyze     # data/analysis_buy_low.csv
make report      # report/main.pdf
```

`make fetch` is optional. The committed `data/` snapshot is from
**19 October 2026, 16:10:40 UTC** (BTC/USDT 81,990.33); re-fetching later will
change the numbers in the report unless the analysis and report data are rebuilt.

## Main result

The payoff is the Binance Buy Low settlement: the gross return factor
`exp(theta*tau)` multiplies the normalized payoff, i.e. the reward is paid in
both branches. With

```
V0 = (S_t/K) N(-d1) + exp(-r*tau) N(d2)
d1 = [ln(S_t/K) + (r + sigma^2/2) tau] / (sigma sqrt(tau)),  d2 = d1 - sigma sqrt(tau)
```

the fair continuously compounded rate and the fair simple APR are

```
theta* = -(1/tau) * ln(V0)
a*     = (365/n) * (1/V0 - 1) = (365/n) * (exp(theta* tau) - 1)
```

At the snapshot, all 383 quotes are below the option-implied value; median cost
is 0.91% of principal for n >= 2, and the median quoted APR is 47% of fair.

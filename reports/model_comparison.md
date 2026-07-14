# Model Comparison Report — uniSolar Layer 1
**Date:** 2026-07-07 09:21:02 UTC
**Models:** xgboost, rf, ridge, meta
**Validation Stations:** 38
**Total Records:** 2,434,312

## Overall Performance Summary

| Model | Stations | Records | RMSE | MAE | MBE | R² | Impr vs Raw | Impr vs Clear-Sky | Skill vs Persist |
|---|---|---|---|---|---|---|---|---|
| xgboost      |  38 | 608,578 | 104.25 |  55.50 |  +28.36 | 0.8224 |  +10.2% |  +59.5% |  +0.943 |
| rf           |  38 | 608,578 | 110.40 |  58.94 |  +31.37 | 0.8012 |   +4.9% |  +57.1% |  +0.936 |
| ridge        |  38 | 608,578 | 115.22 |  62.51 |  +28.88 | 0.7965 |   +0.8% |  +55.2% |  +0.931 |
| meta         |  38 | 608,578 | 115.39 |  62.04 |  +34.94 | 0.7818 |   +0.6% |  +55.2% |  +0.931 |
| Clear-Sky (Ineichen) | — | — | 257.47 | — | — | — | — |   +0.0% | — |
| Scaled Clear-Sky     | — | — | 131.54 | — | — | — | — |  +48.9% | — |
| Persistence (24h)    | — | — | 437.98 | — | — | — | — |  -70.1% | — |

**Best model:** `xgboost` (Mean RMSE = 104.25 W/m²)

_Skill vs Persist = 1 - MSE_model / MSE_persistence (SS=1 is perfect, SS=0 is no better than persistence)_

## Statistical Significance (Wilcoxon Signed-Rank)

Paired test on per-station RMSE values. H₀: models have equal error distributions.

| Pair | W-stat | p-value | Significant (p<0.05)? |
|---|---|---|---|
| xgboost vs rf | 0.0 | 0.0000 | ✓ Yes |
| xgboost vs ridge | 24.0 | 0.0000 | ✓ Yes |
| xgboost vs meta | 0.0 | 0.0000 | ✓ Yes |
| rf vs ridge | 178.0 | 0.0045 | ✓ Yes |
| rf vs meta | 12.0 | 0.0000 | ✓ Yes |
| ridge vs meta | 324.0 | 0.5090 | ✗ No |

## Seasonal Breakdown (RMSE per Model)

Seasons: DJF (Dec-Feb), MAM (Mar-May), JJA (Jun-Aug), SON (Sep-Nov)

| Model | DJF RMSE | MAM RMSE | JJA RMSE | SON RMSE | DJF MAE | MAM MAE | JJA MAE | SON MAE |
|---|---|---|---|---|---|---|---|---|
| xgboost      |  83.83 |  99.04 | 102.05 | 110.26 |  45.30 |  53.16 |  55.95 |  60.39 |
| rf           |  90.78 | 105.54 | 110.72 | 114.87 |  49.12 |  56.71 |  60.69 |  62.98 |
| ridge        |  99.82 | 117.35 | 112.10 | 114.72 |  55.28 |  64.40 |  61.73 |  62.99 |
| meta         |  91.92 | 107.19 | 114.32 | 124.34 |  50.07 |  58.28 |  62.97 |  68.56 |

## Inference Latency

| Model | Mean (s) | Std (s) | Min (s) | Max (s) | Records |
|---|---|---|---|---|---|
| meta         | 1.0234 | 0.0701 | 0.7487 | 1.1605 | 608,578 |
| rf           | 0.2132 | 0.0289 | 0.1831 | 0.3563 | 608,578 |
| ridge        | 0.1043 | 0.0059 | 0.0820 | 0.1206 | 608,578 |
| xgboost      | 0.4186 | 0.0283 | 0.3088 | 0.4808 | 608,578 |

_Timed per-station predict() call (includes feature engineering + model inference)._

## Country-Level Breakdown (Best Model)

| Country | Stations | Raw RMSE | Corr RMSE | Impr % | Corr MBE | Corr R² |
|---|---|---|---|---|---|---|
| BJ    |   1 |  96.92 |  86.82 |  +10.4% |  +18.71 | 0.9081 |
| ML    |  13 |  96.45 |  86.88 |   +9.8% |  +24.79 | 0.9116 |
| KE    |   8 | 116.32 | 102.81 |  +11.4% |  +22.39 | 0.8697 |
| NG    |   2 | 118.51 | 106.88 |   +9.9% |  +38.52 | 0.7625 |
| UG    |   1 | 119.88 | 109.34 |   +8.8% |  +16.29 | 0.8176 |
| MW    |   6 | 125.47 | 110.67 |  +11.7% |  +23.62 | 0.8521 |
| GH    |   7 | 145.82 | 133.65 |   +9.2% |  +46.08 | 0.5828 |

## Naive Physics Baselines — Description

| Baseline | Description |
|---|---|
| Clear-Sky (Ineichen) | `power_CLRSKY_SFC_SW_DWN` from NASA POWER. Pure physical clear-sky model. Ignores clouds entirely — only valid for clear-sky hours. |
| Scaled Clear-Sky | Clear-sky GHI × station-mean clearness index. Captures mean cloud climatology per station. |
| Persistence (24h) | GHI from 24 hours ago. 'If it was sunny yesterday, it will be sunny today.' Captures synoptic-scale persistence. |


# Forward-Chaining Temporal Validation
**Date:** 2026-07-07  
**Models:** XGBoost, Ridge, Stacking (XGBoost+Ridge → XGBoost meta)

Tests temporal generalization — trains on expanding time windows and tests on
future unseen periods. If the model overfits to temporal patterns, forward-chaining
RMSE would be significantly higher than grouped k-fold RMSE.

## Results (6 splits)

| Fold | Test range | XGBoost | Ridge | Stacking |
|------|------------|---------|-------|----------|
| 1 | 2017-09-30 → 2018-03-10 | 155.10 | 479.93 | 158.76 |
| 2 | 2018-03-10 → 2018-05-13 | 139.35 | 145.50 | 141.82 |
| 3 | 2018-05-13 → 2018-07-15 | 123.67 | 131.87 | 125.66 |
| 4 | 2018-07-15 → 2018-09-17 | 141.97 | 142.83 | 146.33 |
| 5 | 2018-09-17 → 2018-11-21 | 119.97 | 125.25 | 127.28 |
| 6 | 2018-11-21 → 2020-11-30 | 145.24 | 144.87 | 152.56 |

| Model | Weighted mean ± std |
|-------|-------------------|
| XGBoost | 137.55 ± 12.19 |
| Ridge | 195.04 ± 127.62 |
| Stacking (XGB+Ridge) | 142.07 ± 12.21 |

## Comparison with Cross-Validation

| Validation | XGBoost RMSE |
|------------|-------------|
| Forward-chaining 4-split | 134.99 ± 6.38 |
| Forward-chaining 6-split | 137.55 ± 12.19 |
| Grouped k-fold (spatial) | 141.49 ± 6.50 |

## Key Findings

- **XGBoost remains the best temporal model** (137.55). Stacking (142.07) underperforms
  because Ridge — the only second base model — has catastrophic temporal generalization
  on small training windows (Fold 1: 479.93).
- **6-split vs 4-split**: The extra folds expose the model to shorter training windows
  (Fold 1: only ~1.5 years of training data), increasing both RMSE (137.55 vs 134.99)
  and std (12.19 vs 6.38).
- **Fold 5 is the easiest** (XGBoost 119.97) — Sep-Nov 2018, dry-to-Harmattan transition
  with abundant training data.
- **Fold 1 is the hardest** (XGBoost 155.10) — shortest training window + Harmattan test.
- **Ridge fails on short data** — Fold 1 produces 479.93 RMSE. Once training data exceeds
  ~2 years, Ridge stabilizes to ~140 W/m², matching XGBoost.
- **Seasonal pattern**: Wet season (Folds 3-4) is mixed (123.67–141.97), not consistently
  easier than dry season as initially hypothesized.
- **RF and LSTM excluded**: RF too slow (300 trees × 600K records × 6 folds), LSTM has
  sequence boundary issues with temporal splits.

## Interpretation

Stacking does not bring temporal generalization benefits in this setting. The single
XGBoost model — simple, fast, robust — beats the ensemble on unseen future data. This
validates the production decision to serve XGBoost for real-time predictions and keep
stacking as the benchmark for the published 5-fold CV result.

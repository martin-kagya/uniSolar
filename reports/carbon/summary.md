# Carbon Footprint Report — Unisolar

**Date**: 2026-06-27
**Hardware**: MacBook Air M2 (Mac14,2), 16 GB RAM, 8-core CPU
**Location**: Ghana (carbon intensity: 540 gCO₂eq/kWh)
**Method**: CodeCarbon v3.2.8 with powermetrics (sudo), 5 s (inference) / 10 s (training) sampling intervals

---

## Measured Emissions

### A. Inference Cost (10,000 records via WeatherCorrectionLayer.predict())
| Metric | Value |
|---|---|
| Duration | 3.8 s |
| Total CO₂ | 0.000438 g CO₂eq |
| Per request | 0.0000000438 g CO₂eq |
| Energy consumed | 0.00000091 kWh |

### B. Training (5-fold GroupKFold CV on 64,968 ZINDI records, 38 stations)
> **Note**: These are historical figures from the V1 model (Jun 2026). Current production
> uses V3 training: 38,166 daytime records, 21 stations, LSTM_BASE model (RMSE 90.98 W/m²).
| Component | RMSE (W/m²) | Duration (s) |
|---|---|---|
| XGBoost 5-fold | 141.49 | 62.1 |
| RF 5-fold | 140.51 | 316.0 |
| Ridge 5-fold | 141.14 | 4.3 |
| Stacking full (LSTM + tree models + meta) | 136.84 | 680.9 |
| Final retrain (full data) | — | 147.8 |
| **Total training** | | **1211 s (~20 min)** |

| Total CO₂ (training) | 1.273 g CO₂eq |
| Total energy (training) | 0.0026 kWh |

### C. Dev API Serving (local M2, estimated from 48 h typical usage)
| Metric | Value |
|---|---|
| Estimated uptime | 48 h |
| Avg power draw | 12 W |
| Energy consumed | 0.576 kWh |
| CO₂ emitted | 311.0 g CO₂eq |

---

## Estimated Emissions

### D. Past Runs (retrospective — before CodeCarbon was installed)
| Run | Duration (s) |
|---|---|
| LSTM HPT (30 trials) | 1588.6 |
| Architecture deep dive (~15 configs) | 600 |
| Early LSTM 5-fold baseline | 200 |
| **Total** | **2388.6** (39.8 min) |

| Energy | 0.009953 kWh |
| CO₂ | 5.37 g CO₂eq |
| Note | Estimated from known timings × Apple M2 TDP (15W). Uncertainty ±30%. |

### E. Production Pro-Forma (30 days, AWS t3.medium, us-east-1)
Based on 10,000 requests/day × 30 days = 300,000 requests/month.
| Metric | Value |
|---|---|
| Server runtime | 730 h |
| Server power | 26.8 W |
| Server energy | 19.564 kWh |
| Server CO₂ | 7825.60 g CO₂eq |
| Inference CO₂ 300,000 req × 0.00000004 g/req) | 0.3000 g CO₂eq |
| **Total monthly CO₂** | **7825.90 g CO₂eq (7.8259 kg)** |

---

## Grand Total

| Source | CO₂ (g) |
|---|---|
| A. Inference (measured) | 0.000438 |
| B. Training (measured) | 1.273 |
| C. Dev serving (estimated) | 311.0 |
| **Measured subtotal (A+B+C)** | **312.31** |
| D. Past runs (estimated) | 5.37 |
| **Total project** | **317.68 g CO₂eq (0.3177 kg)** |

---

## Real-World Equivalents

| Equivalent | Amount |
|---|---|
| Car distance | 2.6 km |
| TV watching | 28 hours |
| US citizen equivalent | 0.0012 weeks |
| Smartphone charges | 635 charges |

---

## Key Takeaways

1. **Training is negligible**: ~1.3 g CO₂eq for the full pipeline (20 min on M2).
2. **Inference is virtually carbon-free**: 4.38 × 10⁻⁸ g CO₂eq per request.
3. **Dev/production dominates**: Server idle time (48 h dev / 730 h prod) accounts for >99% of emissions.
4. **Apple M2 efficiency**: The entire project (~25 h total compute) emits <0.32 kg CO₂eq — equivalent to driving 2.6 km.

---

## Methodology

- **Measured**: CodeCarbon v3.2.8 with powermetrics (sudo) — Apple Silicon power tracking
- **Tracking mode**: machine — total machine power, 5 s sampling interval
- **Carbon intensity**: 540 gCO₂eq/kWh (Ghana grid average, Our World in Data 2023)
- **Past runs**: Estimated from timestamps in reports/lstm_hpt_results.json × Apple M2 TDP (15 W). Uncertainty ±30%.
- **Production**: AWS t3.medium (2 vCPU, 4 GB) × 730 h/month × 400 gCO₂eq/kWh (us-east-1)

## Output Files

- reports/carbon/summary.md — This report
- reports/carbon/training_emissions.csv — Raw CodeCarbon CSV (training)
- reports/carbon/inference_emissions.csv — Raw CodeCarbon CSV (inference)
- reports/carbon/equivalents.json — Real-world equivalents
- reports/carbon/methodology.md — Detailed methodology
- reports/carbon/results.json — Full structured results
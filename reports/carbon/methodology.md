# Carbon Measurement Methodology — Unisolar

## Tooling
- **[CodeCarbon](https://github.com/mlco2/codecarbon) v3.2.8**
- macOS `powermetrics` (sudo) for Apple Silicon power measurement
- Fallback: TDP-based estimation using Apple M2 15W sustained

## Measurement Strategy

### Direct Measurement (CodeCarbon)
Scripts are wrapped with `EmissionsTracker` context managers:
```python
from codecarbon import EmissionsTracker

with EmissionsTracker(project_name="unisolar-training",
                      country_iso_code="GHA") as tracker:
    # training code
```

The tracker samples CPU, GPU, and RAM power every 10-15 seconds.

### Apple Silicon Power
On Mac14,2 (M2), CodeCarbon uses `powermetrics` for accurate CPU+GPU power.
Access is granted via:
```
kagya ALL = (root) NOPASSWD: /usr/bin/powermetrics
```

### Training Measurement
Full stacking pipeline measured with task-level breakdown:
1. XGBoost 5-fold CV
2. RandomForest 5-fold CV
3. Ridge 5-fold CV
4. Stacking ensemble (all base models + meta)
5. Final retrain on full data

### Inference Measurement
`WeatherCorrectionLayer.predict()` on 10,000 daytime records from ZINDI dataset.
Per-request cost = total CO₂ / 10,000.

### Past-Run Estimates
For runs completed before CodeCarbon was installed:
- Timings from `reports/lstm_hpt_results.json` (30 HPT trials: 1588.6 s total)
- Architecture deep dive: ~600 s (15 configs × ~40 s)
- Early baseline: ~200 s
- Power: 15W (Apple M2 TDP sustained)
- CO₂ = Power × Time × Carbon Intensity

### Production Pro-Forma
- Instance: AWS t3.medium (2 vCPU, 4 GB RAM)
- Region: us-east-1 (400 gCO₂eq/kWh)
- Uptime: 730 hours/month (24/7)
- Traffic: 10,000 requests/day × 30 days
- Server power: 26.8W (TDP + RAM estimate)

## Carbon Intensity
Primary: 540 gCO₂eq/kWh (Ghana grid, Our World in Data 2023).
Fallback: 475 gCO₂eq/kWh (global average, IEA 2019).

## Uncertainty
- **Measured**: ±5% (powermetrics hardware counters)
- **Estimated**: ±30% (TDP-based approximation)
- **Pro-forma**: ±50% (cloud instance specs vary with workload)

# UniSolar — Satellite GHI Bias Correction for West Africa

ML-driven bias correction of NASA POWER satellite irradiance for utility-scale solar
development in West Africa. Part of the **ZINDI Solar Challenge** and broader work on
solar resource assessment in data-sparse regions.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Problem](#the-problem)
3. [Architecture Overview](#architecture-overview)
4. [Production Pipeline](#production-pipeline)
5. [ML Model Selection](#ml-model-selection)
6. [Feature Engineering](#feature-engineering)
7. [Benchmarks](#benchmarks)
8. [Key Design Decisions](#key-design-decisions)
9. [Data Sources](#data-sources)
10. [System Architecture](#system-architecture)
11. [Scripts & Usage](#scripts--usage)
12. [Way Forward](#way-forward)

---

## Executive Summary

UniSolar is a production-grade solar resource assessment platform that corrects systematic biases in satellite-derived irradiance data for West African sites. The system combines machine learning bias correction with physics-based energy modeling to deliver lender-ready financial projections for utility-scale solar installations.

**Key Metrics:**
- **23 validated ground stations** across West Africa (Ghana, Mali, Benin, Nigeria)
- **54,518 daytime records** (all 23 stations) / **50,218** (21 stations, no Nigeria — training set)
- **RMSE improvement (23-stn eval)**: 112.31 → 88.23 W/m² (21.4%) with LSTM_BASE
- **RMSE improvement (21-stn CV)**: 110.16 → 90.98 W/m² (17.4%) — used for model selection
- **Production model**: LSTM_BASE (bidirectional, 32 hidden, 2 layers) + RF fallback
- **Architecture**: 6-layer pipeline with real-time NASA POWER data integration

---

## The Problem

NASA POWER satellite GHI systematically overestimates irradiance by **~12%** in West Africa due to:
- **Aerosol loading**: Saharan dust (Harmattan) and biomass burning
- **Coastal atmospheric dynamics**: Complex marine boundary layer effects
- **Spatial resolution**: 0.5° × 0.625° grid (~50-60 km at equator) misses local variability

This bias makes satellite data unreliable for solar project financing without ground-truth calibration. The core challenge is **spatial generalization**: a model trained on 23 stations must correct irradiance accurately at **unseen locations** across the Sahel.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        UniSolar Platform                            │
├─────────────────────────────────────────────────────────────────────┤
│  Frontend (React + Vite)    │    Backend (FastAPI + Python)         │
│  ├── MapViewport            │    ├── api/main.py (REST API)         │
│  ├── Sidebar (Controls)     │    ├── core/layers/                   │
│  ├── ResultsPanel           │    │   ├── weather_model.py (ML)      │
│  ├── ReportModal            │    │   ├── environmental_model.py     │
│  └── SizingHubModal         │    │   ├── physics_model.py           │
│                             │    │   ├── geometry_model.py          │
│                             │    │   ├── financial_model.py         │
│                             │    │   ├── sustainability_model.py    │
│                             │    │   └── ecg_tariff.py              │
│                             │    ├── core/services/gis.py           │
│                             │    └── core/database.py               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Production Pipeline

### 6-Layer Architecture

```
[Raw NASA POWER] → Layer 1: Weather Correction (ML)
                          ↓
                 36 engineered features
                          ↓
                   Ratio Predictor (LSTM_BASE or RF)
                          ↓
                 ghi_corrected = satellite × predicted_ratio
                          ↓
                 Layer 2: Environmental Losses
                 (Soiling, Degradation, Rain Cleaning)
                          ↓
                 Layer 0: Spatial Geometry
                 (Obstacle Shading, Row-to-Row)
                          ↓
                 Layer 3: Physics Engine (PVLib)
                 (Module specs, Inverter, Temperature)
                          ↓
                 Layer 4: Financial Modeling
                 (NPV, IRR, LCOE, Payback)
                          ↓
                 Layer 5: Sustainability Reporting
                 (CO2 Avoidance, Tree Equivalents)
                          ↓
                 [Lender-Ready Report]
```

### Layer Descriptions

| Layer | Module | Purpose | Key Technology |
|-------|--------|---------|----------------|
| **Layer 1** | `weather_model.py` | ML bias correction of satellite irradiance | LSTM/RF, 36 features, ratio target |
| **Layer 2** | `environmental_model.py` | Soiling (Kimber model), degradation, rain cleaning | AOD/PM2.5 modulated, manufacturer presets |
| **Layer 0** | `geometry_model.py` | Obstacle shading, row-to-row inter-row shading | PVLib infinite row model |
| **Layer 3** | `physics_model.py` | Deterministic energy yield simulation | PVLib ModelChain, Sandia modules |
| **Layer 4** | `financial_model.py` | NPV, IRR, LCOE, payback, lifetime savings | ECG May 2025 tariff reckoner |
| **Layer 5** | `sustainability_model.py` | CO2 avoidance, tree equivalents | Ghana grid emission factor (0.35 kg/kWh) |

---

## ML Model Selection

### Current Best: LSTM_BASE (Bidirectional LSTM)

The best-performing model is a bidirectional LSTM that captures temporal patterns in satellite irradiance sequences:

| Component | Value |
|-----------|-------|
| Architecture | Bidirectional LSTM + FC head |
| Hidden dim | 32 × 2 (bidirectional) |
| Layers | 2 |
| Sequence length | 4 timesteps |
| Dropout | 0.2 |
| Output | Sigmoid × 3.0 (bounded ratio) |
| Training | AdamW, lr=3e-4, early stopping (patience=6) |
| Ensemble | 2-seed average |

### Model Comparison

| Model | RMSE (W/m²) | Size | Inference | Notes |
|-------|-------------|------|-----------|-------|
| **LSTM_BASE** | **90.98 ± 5.22** | 168 KB | ~5ms | **Best performer** |
| LSTM_ATTN | 91.33 ± 5.37 | 234 KB | ~6ms | Attention variant |
| RF | 93.48 ± 14.79 | 240 MB | ~50ms | Stable, large |
| XGBoost | 94.06 ± 14.71 | 20 MB | ~20ms | Fast inference |
| Ridge | 100.08 ± 12.16 | 3 KB | <1ms | Linear baseline |

### Why Not Stacking?

Stacking (XGBoost + RF + Ridge + LSTM → meta-model) was tested but not deployed:
- Marginal improvement (~1-2 W/m²) over single LSTM
- 6× more model files to maintain
- ~5× slower inference (multiple model loads)
- LSTM alone captures enough signal

---

## Feature Engineering

### 36-Feature Set

```
Satellite:       ghi_satellite, dni_satellite, dhi_satellite
Lags:            ghi_satellite_lag1/2, dni_satellite_lag1, dhi_satellite_lag1
Meteorology:     temp_air, relative_humidity, wind_speed
Time:            hour, month, hour_sin/cos, month_sin/cos
Atmosphere:      pm25, aod_550, cloud_amt, albedo
Solar geometry:  clear_sky_ghi, clearness_index, solar_zenith, solar_elevation, airmass
Cloud var.:      clearness_index_lag1, clearness_index_std_3h, clearness_index_delta
Location:        latitude_f, longitude_f, dist_to_coast_km, elevation_m
Categorical:     cz_0.0, cz_1.0, cz_2.0 (climate zone one-hot)
Station:         station_bias (zeroed during k-fold, real during final training)
```

### LSTM Feature Subset (21 features)

The LSTM uses a reduced feature set focused on temporal dynamics:

```
ghi_satellite, dni_satellite, dhi_satellite
ghi_satellite_lag1, ghi_satellite_lag2
temp_air, relative_humidity, wind_speed
hour_sin, hour_cos, month_sin, month_cos
pm25, aod_550
clearness_index, clearness_index_lag1, clearness_index_std_3h, clearness_index_delta
solar_zenith, solar_elevation, clear_sky_ghi
```

### Key Feature Groups

| Group | Features | Purpose |
|-------|----------|---------|
| **Satellite Core** | GHI, DNI, DHI + lags | Raw irradiance measurements |
| **Atmospheric** | PM2.5, AOD, cloud amount | Aerosol/cloud interference |
| **Solar Geometry** | Zenith, elevation, airmass | Sun position physics |
| **Cloud Variability** | Rolling std, delta, lag1 | Temporal cloud dynamics |
| **Location** | Lat/lon, coast distance, elevation | Spatial generalization |
| **Temporal** | Hour/month cyclical encoding | Diurnal/seasonal patterns |

---

## Benchmarks

### Data Splits

Training data was built in three stages:

| Version | Stations | Daytime Records | Description |
|---------|----------|-----------------|-------------|
| V1 (Jun 30) | ~40+ DB + 21 ZINDI | ~70K | Mixed DB+ZINDI, inflated scores |
| V2 (Jul 27) | 23 validated | 54,518 | Clean data, honest evaluation |
| **V3 (Jul 27)** | **21 (no Nigeria)** | **50,218** | **Current production training set** |

### Training Data Quality

| Metric | All 23 Stations (eval) | No Nigeria (21, training) |
|--------|------------------------|---------------------------|
| Records (daytime) | 54,518 | 50,218 |
| Raw NASA RMSE | 112.31 W/m² | 110.16 W/m² |
| Raw NASA MAE | 78.76 W/m² | 77.02 W/m² |
| Raw NASA R² | 0.841 | 0.850 |

### 5-Fold Grouped CV — V3 (21 stations, no Nigeria)

Model selection was done on the 21-station no-Nigeria subset to avoid information leakage from Nigerian stations (where satellite systematically overestimates by 25-30%).

| Model | RMSE ± Std | Δ vs Raw | Improvement |
|-------|------------|----------|-------------|
| Raw NASA | 110.16 | — | — |
| Ridge | 100.08 ± 12.16 | −10.1 | 8.2% |
| XGBoost | 94.06 ± 14.71 | −16.1 | 14.6% |
| RF | 93.48 ± 14.79 | −16.7 | 15.1% |
| **LSTM_BASE** | **90.98 ± 5.22** | **−19.2** | **17.4%** |
| LSTM_ATTN | 91.33 ± 5.37 | −18.8 | 17.1% |

### Full Evaluation — All 23 Stations

When evaluated on all 23 clean stations (including Nigeria):

| Metric | Raw NASA | LSTM_BASE Corrected | Improvement |
|--------|----------|---------------------|-------------|
| RMSE | 112.31 W/m² | 88.23 W/m² | **+21.4%** |
| MAE | 78.76 W/m² | 56.85 W/m² | +27.8% |
| R² | 0.841 | 0.902 | — |

### Per-Station Error Breakdown (V3, no Nigeria)

| Station | Country | Records | Ratio | RMSE | R² |
|---------|---------|---------|-------|------|-----|
| navrongo_tier1 | GH | 3,927 | 1.023 | 85.9 | 0.921 |
| TA00344 | ML | 2,129 | 0.917 | 92.3 | 0.899 |
| TA00346 | ML | 2,118 | 0.962 | 98.6 | 0.888 |
| TA00328 | ML | 2,239 | 0.915 | 96.8 | 0.883 |
| TA00348 | ML | 2,103 | 1.292 | 102.2 | 0.878 |
| TA00109 | GH | 2,090 | 0.751 | 153.7 | 0.551 |
| TA00119 | GH | 2,114 | 0.768 | 153.1 | 0.489 |

**Station difficulty range**: RMSE from 86 W/m² (navrongo) to 154 W/m² (TA00109)

### Per-Station Calibration

Per-station bias corrections are applied at inference time:

```
Median correction: +1.85 W/m²
Range: +0.75 to +3.50 W/m²
```

Stored in `core/models/station_calibration.json`.

### Historical RMSE Progression

| Stage | RMSE | Notes |
|-------|------|-------|
| Raw NASA POWER | 178.78 | Original V1 data (inflated) |
| V1 XGBoost | 82.67 | Included easy DB stations (inflated) |
| V2 RF (23 stn) | 91.04 | Clean data, honest eval |
| V3 LSTM_BASE (21-stn CV) | 90.98 | Model selection set |
| **V3 LSTM_BASE (23-stn eval)** | **88.23** | **Full evaluation (21.4% over raw 112.31)** |

---

## Key Design Decisions

### 1. Ratio Target Over Clearness Index

**Decision**: Use `ratio = GHI_ground / GHI_satellite` instead of `kt = GHI / clear_sky_ghi`

**Rationale**:
- `kt` amplifies cloudy-day errors: `error = clear_sky_ghi × error_in_kt`
- `ratio` scales with signal: `error = GHI_satellite × error_in_ratio`
- Produces lower median per-station bias

### 2. Station Bias Zeroing in K-Fold

**Decision**: Zero `station_bias` for both training and validation during k-fold

**Rationale**:
- Tree models learned station-specific splits when bias was real in training but NaN in validation
- This caused ~8 W/m² of inflated CV results
- Fix: Always zero in k-fold, real only in final training

### 3. Clean Station Validation

**Decision**: Filter to 23 validated stations, removing faulty/broken sensors

**Rationale**:
- 4 stations excluded: TA00330 (ratio too high), TA00109/TA00122/TA00354 (>20% extreme ratios)
- 2 Nigerian stations (TA00692, TA00696) included in the 23-station eval set but excluded from the 21-station training set — satellite systematically overestimates by 25-30% in Nigeria
- Filter criteria: mean ratio 0.6–1.1, <20% extreme ratio records (<0.3 or >2.5)

### 4. ECG Tariff Integration

**Decision**: Use official ECG May 2025 Tariff Reckoner for financial modeling

**Rationale**:
- Tiered tariff structure reflects real Ghanaian electricity costs
- Includes all levies, VAT, and regulatory charges
- More accurate than flat-rate assumptions for project financing

### 5. PVLib for Physics Engine

**Decision**: Use PVLib ModelChain for energy yield simulation

**Rationale**:
- Industry-standard open-source library for PV simulation
- Sandia module database with 100+ real panel specifications
- CEC inverter database with 3000+ inverter models
- Handles temperature coefficients, shading, and electrical losses

---

## Data Sources

| Source | Type | Resolution | Coverage |
|--------|------|------------|----------|
| **NASA POWER** | Satellite reanalysis | 3-hourly, 0.5°×0.625° | Global |
| **CAMS EAC4** | Aerosol reanalysis | 3-hourly, ~80 km | Global |
| **ZINDI Challenge** | Ground truth | Hourly pyranometers | 21 stations, West Africa |
| **Ghana Tier-1** | Ground truth | Hourly | 2 stations, Ghana |
| **ECG Tariff** | Regulatory | Monthly billing tiers | Ghana nationwide |
| **SRTM DEM** | Topography | 30m resolution | Global |

### Training Data

| Dataset | Records | Stations | Period |
|---------|---------|----------|--------|
| ZINDI Challenge | 34,568 | 21 | 2017-2019 |
| Ghana Tier-1 (Navrongo + Sunyani) | 15,650 | 2 | 2017-2022 |
| **Combined (clean, daytime)** | **54,518** | **23** | **2017-2022** |
| No-Nigeria subset (training) | 50,218 | 21 | 2017-2022 |

**Excluded from training**: TA00338, TA00295, TA00064, TA00219 (faulty sensors), TA00330 (ratio too high), TA00109/TA00122/TA00354 (>20% extreme ratios). **Excluded from 21-station training set** (kept in 23-station eval): TA00692, TA00696 (Nigeria — satellite systematically overestimates by 25-30%).

---

## System Architecture

### Backend (FastAPI + Python)

```
api/main.py                 # REST API endpoints
├── POST /simulate          # Full pipeline execution
├── POST /size-system       # System sizing calculator
├── GET  /modules           # Available panel models
├── GET  /inverters         # Available inverter models
├── GET  /ecg-tariff-info   # ECG tariff lookup
└── POST /custom-module     # Add user-defined panels

core/layers/                # 6-layer pipeline
├── weather_model.py        # Layer 1: ML bias correction
├── environmental_model.py  # Layer 2: Soiling/degradation
├── geometry_model.py       # Layer 0: Spatial shading
├── physics_model.py        # Layer 3: PVLib energy yield
├── financial_model.py      # Layer 4: NPV/IRR/LCOE
├── sustainability_model.py # Layer 5: CO2 avoidance
└── ecg_tariff.py           # ECG tariff engine

core/services/
└── gis.py                  # GIS: coast distance, elevation, climate zones

core/models/                # Trained model artifacts
├── lstm_ratio.pt           # LSTM_BASE (production, 168 KB)
├── lstm_attn_ratio.pt      # LSTM_ATTN (attention variant, 234 KB)
├── rf_ghi.pkl              # Random Forest (240 MB, fallback)
├── rf_dni.pkl              # RF for DNI
├── xgboost_ghi.pkl         # XGBoost (20 MB)
├── xgboost_dni.pkl         # XGBoost for DNI
├── ridge_ghi.pkl           # Ridge (3 KB, baseline)
├── ridge_dni.pkl           # Ridge for DNI
├── default_ghi.pkl         # Default GHI model (RF)
├── default_dni.pkl         # Default DNI model (RF)
├── meta_ghi.pkl            # Stacking meta-model
├── meta_dni.pkl            # Stacking meta-model (DNI)
└── station_calibration.json # Per-station bias corrections
```

### Frontend (React + Vite)

```
frontend/src/
├── pages/
│   └── Dashboard.jsx       # Main application page
├── components/
│   └── dashboard/
│       ├── MapViewport.jsx      # Interactive map with panel placement
│       ├── Sidebar.jsx          # Configuration controls
│       ├── ResultsPanel.jsx     # Real-time results display
│       ├── ReportModal.jsx      # Lender-ready financial report
│       ├── SizingHubModal.jsx   # System sizing calculator
│       ├── AddressSearch.jsx    # Location search
│       └── AddPanelModal.jsx    # Custom panel editor
```

### Data Flow

```
User places panels on map
        ↓
Frontend sends POST /simulate
{
  latitude, longitude, capacity_kw,
  tilt, azimuth, panels[], features[],
  system_cost_kw, om_cost_kw,
  use_ecg_tariff, customer_type
}
        ↓
Backend fetches NASA POWER data (if not cached)
        ↓
Layer 1: ML predicts correction ratio
Layer 2: Environmental losses applied
Layer 0: Obstacle shading calculated
Layer 3: PVLib simulates energy yield
Layer 4: Financial metrics computed
Layer 5: CO2 avoidance calculated
        ↓
Response: { results, financials, probabilistic_results }
        ↓
Frontend displays: Annual Yield, NPV, Payback, IRR
```

---

## Scripts & Usage

### Training

| Command | Description |
|---------|-------------|
| `python scripts/retrain_unified.py --clean --kfold 5` | Clean data, 5-fold CV |
| `python scripts/retrain_unified.py --clean --lstm --models xgboost,rf,ridge` | Train LSTM + tree models |
| `python scripts/retrain_unified.py --clean --exclude-country NG` | Exclude Nigerian stations |
| `python scripts/retrain_unified.py --clean --stacking` | Train stacking ensemble |
| `python scripts/retrain_unified.py --clean --tune` | Hyperparameter tuning |

### Data Pipeline

| Command | Description |
|---------|-------------|
| `python scripts/build_clean_training_data.py` | Build clean parquet from NASA + ZINDI |
| `python scripts/build_clean_training_data.py --skip-fetch` | Use cached NASA data |
| `python scripts/fetch_cams_pm25.py` | Download CAMS PM2.5 data |
| `python data/ingest_nasa.py` | Fetch NASA POWER data |
| `python data/ingest_real_csv.py` | Ingest ground truth CSVs |

### Visualization

| Command | Description |
|---------|-------------|
| `python scripts/plot_narrative.py` | 6-panel stakeholder summary |
| `python scripts/plot_rolling_analysis.py` | Rolling mean + cumulative bias |
| `python scripts/compare_models.py` | Head-to-head model benchmark |

### Production Inference

```python
from core.layers.weather_model import WeatherCorrectionLayer

layer = WeatherCorrectionLayer(model_type='lstm')
layer.load_models()
df_corrected = layer.predict(df_satellite)

# df_corrected now has ghi_corrected and dni_corrected columns
```

---

## Way Forward

### Completed
- [x] Clean station validation (23 stations, 4 broken removed)
- [x] LSTM training on clean data (90.98 W/m² — new best)
- [x] Per-station calibration (median +1.85 W/m² correction)
- [x] Nigeria exclusion study (RF: 93.5 vs 91.0 with Nigeria)

### Next Steps
1. **Deploy LSTM in production** — replace RF as default in `weather_model.py`
2. **Station-quality weighting** — weight training by inverse station RMSE
3. **Hour-of-day calibration** — time-dependent bias corrections per station
4. **MERRA-2 aerosol speciation** — hourly dust/BC/OC from GES DISC
5. **Larger LSTM architecture** — hidden 32→64, layers 2→3, sequence 4→8
6. **Temporal averaging** — average ground truth ±1.5h around NASA timestamps

---

## Constraints

- **Memory**: LSTM full 5-fold CV requires ~500 MB. Larger architectures may need GPU.
- **Numpy/Torch compat**: PyTorch 2.2.0 compiled against NumPy 1.x — `.numpy()` calls fail, use `.tolist()` workaround.
- **Temporal coverage**: ZINDI ground truth ends Nov 30, 2018 for most stations.
- **Spatial coverage**: 21 stations concentrated in Ghana/Mali. Sparse in Niger/Chad/Senegal.

---

## Project History

Detailed project history and minutes available at `reports/minutes_20260616.md`.

---

## License

Proprietary — UniSolar Enterprise Edition

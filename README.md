# UniSolar — Satellite GHI Bias Correction for West Africa

ML-driven bias correction of NASA POWER satellite irradiance for utility-scale solar
development in West Africa. Part of the **ZINDI Solar Challenge** and broader work on
solar resource assessment in data-sparse regions.

---

## Table of Contents

1. [Objective](#objective)
2. [Data](#data)
3. [Phase 1 — Pre-LSTM: Stacking Ensemble](#phase-1--pre-lstm-stacking-ensemble)
4. [Phase 2 — LSTM: Temporal Deep Learning](#phase-2--lstm-temporal-deep-learning)
5. [Architecture & Pipeline](#architecture--pipeline)
6. [Benchmarks](#benchmarks)
7. [Key Decisions & Findings](#key-decisions--findings)
8. [Scripts & Usage](#scripts--usage)
9. [Data Flow](#data-flow)
10. [Way Forward](#way-forward)

---

## Objective

Correct the residual positive bias in NASA POWER satellite GHI for West African sites.
NASA POWER systematically under-reports irradiance by 30-50% in this region due to
aerosol loading (Saharan dust, biomass burning) and complex coastal atmospheric dynamics.

The core problem is **spatial generalization**: a model trained on 38 ground stations
must correct irradiance accurately at **unseen locations** across the Sahel. This rules
out per-station calibration and forces the model to learn physically meaningful,
transferable corrections.

---

## Data

### Training Set (64,968 records, 38 groups)

| Source | Records | Groups | Description |
|---|---|---|---|
| ZINDI Challenge | 65,382 | 38 stations | West African solar monitoring network |
| DB NASA (Ghana) | 78,838 | 3 locations | Ghana-specific NASA POWER + ground truth |

### Excluded Stations
TA00338, TA00295, TA00064, TA00219 — identified as faulty.

### Satellite Data
- **NASA POWER** (primary): 3-hourly GHI, DNI, DHI, temperature, humidity, wind speed,
  cloud amount, AOD at 550nm (`power_AOD_55` — sourced from MERRA-2 reanalysis)
- **Spatial resolution**: 0.5° × 0.625° (~50-60 km at equator)
- **Temporal range**: 2017-2019 (ZINDI), 2014-2023 (DB Ghana)

### Atmospheric Data
- **PM2.5**: CAMS EAC4 reanalysis (3-hourly, ~80 km grid, 2003-present)
- **AOD at 550nm**: NASA POWER parameter `power_AOD_55` (already MERRA-2 derived)

### Ground Truth
- ZINDI Challenge pyranometer measurements
- Ghana DB station measurements
- **Temporal footprint mismatch**: Ground truth is instantaneous; NASA POWER is a
  3-hour average. Future work should average GT ±1.5h around each POWER timestamp.

---

## Phase 1 — Pre-LSTM: Stacking Ensemble

### The Station Bias Bug

**Root cause**: In GroupKFold cross-validation, validation groups correspond to unseen
stations with no known `station_bias`. The old code left `station_bias=NaN` in
validation folds (or filled with 0 via `fillna(0.0)`). Tree-based models
(XGBoost, RandomForest) used the real bias values in training data to learn
**station-specific splits** — splits that produce non-generalizing trees for unseen
stations.

**Impact**: When `fillna(0.0)` was applied (required because Ridge Regression's
solver cannot tolerate NaN), the CV results inflated dramatically:
- XGBoost jumped from ~140 to ~148 W/m²
- RandomForest jumped from ~139 to ~147 W/m²

The splits had memorised station identity through bias patterns. Validation (now
receiving 0.0 instead of NaN) was being evaluated against splits trained for
different bias values, producing worse results than random.

**Fix**: Zero `station_bias` for **both** training and validation during k-fold.
No station-specific information leaks. True per-station bias is only computed and
applied during final full-data retraining (for the `station_calibration.json`
post-hoc adjustment).

### Target Selection

Two targets were compared:

| Target | Formula | Problem |
|---|---|---|
| kt (clearness index) | `kt = GHI / clear_sky_ghi` | `error = clear_sky_ghi × error_in_kt` — amplifies cloudy-day errors because clear_sky_ghi ≫ satellite GHI on cloudy days |
| Ratio | `ratio = GHI_ground / GHI_satellite` | `error = GHI_satellite × error_in_ratio` — error scales with the signal itself, which is already low on cloudy days |

**Decision**: Ratio target, bounded [0.0, 3.0]. Both have similar k-fold RMSE but
ratio is physically better-behaved.

### Feature Engineering

#### AOD at 550nm
Added `aod_550` from NASA POWER's `power_AOD_55` parameter. This is already
MERRA-2 derived (NASA POWER sources its aerosol fields from the MERRA-2
reanalysis). Fallback value of 0.15 when missing.

Contributed **+1.8 W/m²** improvement on held-out benchmark.

#### Cloud Variability Features (4 new)
Derived from the existing clearness_index to capture temporal cloud dynamics:

| Feature | Formula | What it captures |
|---|---|---|
| `ghi_satellite_lag2` | shift(2) of GHI | GHI at t-6h — medium-term cloud memory |
| `clearness_index_lag1` | shift(1) of clearness_index | Cloud attenuation at t-3h — short-term memory |
| `clearness_index_std_3h` | rolling(3).std() | Broken vs uniform cloud cover over 9h |
| `clearness_index_delta` | diff(1) | Rate of change — clearing vs clouding over |

**Impact**: Stacking 138.75 → 138.37 (−0.38), Ridge 142.95 → 141.30 (−1.65).
Ridge benefits most because it can't learn non-linear interactions natively.

#### Full Feature Set (36 features)

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

### Model Selection

#### LightGBM Dropped
LightGBM predictions were **99.5% correlated** with XGBoost on identical features.
Stacking requires diversity — adding a near-identical model provides no lift
while adding complexity. Replaced by Ridge.

#### UniSolar Stacking Ensemble
```
Base models:  XGBoost + RandomForest + Ridge(StandardScaler + alpha=10.0) + LSTM
Meta-model:   XGBoost (100 trees, lr=0.1, max_depth=3)
Target:       ratio [0, 3]
CV:           GroupKFold(5), station_grouped
```

The four base models provide genuine diversity:
- **XGBoost**: Gradient-boosted trees — captures complex non-linear interactions
- **RandomForest**: Bagged trees — high variance, different split strategies
- **Ridge**: Linear with L2 — completely different hypothesis space
- **LSTM**: Bidirectional LSTM (32 hidden, 2 layers, seq_len=4) — temporal patterns

The meta-model learns optimal weighting of all four. LSTM contributes the temporal
dimension that static models cannot capture; Ridge provides a regularising linear anchor.

### Pre-LSTM Benchmarks (5-fold GroupKFold CV)

| Model | RMSE ± Std | Δ vs Raw |
|---|---|---|
| Raw NASA | 178.78 | — |
| Ridge | 141.30 ± 4.58 | −37.48 |
| XGBoost | 141.44 ± 5.65 | −37.34 |
| RF | 140.44 ± 5.95 | −38.34 |
| Stacking (3-model) | 138.37 ± 5.03 | −40.41 |

Full-sample (stacking, all 608k ZINDI records): RMSE 117.47, MAE 59.83,
global bias +31.54, median per-station bias +0.9 W/m².

### RMSE Progression (5-fold grouped CV)

| Stage | RMSE | Notes |
|---|---|---|---|
| Raw NASA | 178.78 | Baseline uncorrected |
| Ratio target | 138.97 | After switching from kt to ratio |
| + AOD at 550nm | 138.96 | Marginal (AOD already partially captured) |
| + Station bias fix + Ridge stacking | 138.75 | Zeroed station_bias in k-fold |
| + Cloud variability features | 138.37 | Best pre-LSTM (3-model stacking) |
| + LSTM (single) | 138.28 | LSTM standalone, 21 features, seq_len=4 |
| + LSTM 5-ensemble | 137.95 | LSTM with 5 different random seeds averaged |
| + **UniSolar Stacking** (4-model) | **136.84** | **XGBoost+RF+Ridge+LSTM → XGBoost meta** |

---

## Phase 2 — LSTM: Temporal Deep Learning

### Motivation

Tree-based models see each row independently. They cannot learn patterns of cloud
evolution — whether the sky is clearing, clouding over, or transitioning between
aerosol regimes. The single `ghi_satellite_lag1` feature (t-3h) provides only
the most recent snapshot.

An LSTM with a 24-hour lookback window (8 timesteps × 3h) can model:
- Cloud advection (broken clouds moving across a site)
- Clearing vs clouding rates (clearness_index_delta over multiple timesteps)
- Diurnal cycle phase shifts
- Multi-day aerosol persistence (harmattan dust episodes)

### Architecture

| Parameter | Value |
|---|---|
| Type | Bidirectional LSTM |
| Layers | 1 |
| Hidden dims | 32 |
| Lookback | 8 timesteps (24h @ 3-hourly) |
| Features | 21 (subset of the 36 tree features) |
| Output | Sigmoid × 3 → ratio [0, 3] |
| Optimizer | AdamW (lr=1e-3, weight_decay=1e-4) |
| Scheduler | ReduceLROnPlateau (factor=0.5, patience=4) |
| Early stopping | 8 stale epochs |
| Batch size | 64 (k-fold) / 256 (standalone) |
| Normalization | Per-fold: train mean/std → train + val |
| Training | PyTorch CPU (M3 Mac, 16 GB) |

### LSTM Feature Set (21 features)

```
ghi_satellite, dni_satellite, dhi_satellite
ghi_satellite_lag1, ghi_satellite_lag2
temp_air, relative_humidity, wind_speed
hour_sin, hour_cos, month_sin, month_cos
pm25, aod_550, clearness_index
clearness_index_lag1, clearness_index_std_3h, clearness_index_delta
solar_zenith, solar_elevation, clear_sky_ghi
```

Excluded from the full 36: station_bias (zeroed), lag1 variants of DNI/DHI
(highly collinear with GHI lags), categorical climate_zone, dist_to_coast_km,
elevation_m, albedo, airmass, cloud_amt, latitude_f, longitude_f.

### Full 5-Fold CV Results

| Fold | XGBoost | LSTM | Δ |
|---|---|---|---|
| 1 | 133.46 | 134.41 | −0.95 |
| 2 | 137.17 | **134.64** | +2.53 |
| 3 | 145.87 | **143.35** | +2.52 |
| 4 | 141.63 | **136.81** | +4.82 |
| 5 | 149.07 | **144.15** | +4.92 |
| **Mean** | **141.44 ± 5.65** | **138.67 ± 4.24** | **+2.77** |

LSTM beats XGBoost on **4/5 folds** with **lower cross-fold variance**
(±4.24 vs ±5.65). This is with a minimal architecture (32 dim, 1 layer) —
no hyperparameter tuning has been performed.

### Why LSTM Wins

1. **Temporal structure**: 8 timesteps capture 24h of cloud evolution. XGBoost
   only sees a single lag-3h snapshot.
2. **Sequence normalization**: Each fold normalises by its own mean/std,
   removing per-station scale shifts naturally.
3. **Lower variance**: Suggests better spatial generalization — the LSTM learns
   temporal patterns that transfer across stations, rather than station-specific
   static corrections.
4. **Fewer features**: 21 vs 36 — the LSTM extracts more signal per feature
   through the temporal dimension.

---

## Architecture & Pipeline

### Layer Architecture

```
[Raw NASA POWER] → WeatherCorrectionLayer._build_features()
                       ↓
              36 engineered features
                       ↓
        ┌──────────────┼──────────────┬──────────────┐
        ↓              ↓              ↓              ↓
    XGBoost(R)     RandomForest(R)  Ridge(R)     LSTM(R)
        │              │              │              │
        └──────────────┼──────────────┼──────────────┘
                       ↓
              meta_X [n, 4] ratios
                       ↓
               XGBoost meta-model
                       ↓
              ratio_pred [0, 3]
                       ↓
         ghi = satellite × ratio
                       ↓
         + station_calibration delta
                       ↓
            [ghi_corrected, dni_corrected]
```

### Production Inference

`core/layers/weather_model.py` — `WeatherCorrectionLayer.predict()`:

1. **Feature engineering** (`_build_features`): Computes solar geometry via pvlib
   Ineichen model, cyclical encoding, cloud variability features, lags, AOD.
2. **Feature alignment**: Reads feature names from saved model to ensure
   compatibility (handles model versioning).
3. **Stacking inference**: Runs all 4 base models (XGBoost + RF + Ridge + LSTM),
   builds sliding-window sequences for LSTM, concatenates ratio predictions,
   feeds to meta-model.
4. **Max correction clipping**: Caps corrected GHI at `clear_sky_ghi × 1.6`
   (allows +60% correction).
5. **Night zeroing**: Forces zero for hours 0-5 and 19-23.
6. **Station calibration**: Applies per-station bias from
   `station_calibration.json` (computed during retraining).

---

## Benchmarks

### Grouped 5-Fold CV (Primary Metric)

| Model | RMSE ± Std | Δ vs Raw |
|---|---|---|
| Raw NASA | 178.78 | — |
| Ridge | 141.30 ± 4.58 | −37.48 |
| XGBoost | 141.44 ± 5.65 | −37.34 |
| RF | 140.44 ± 5.95 | −38.34 |
| Stacking (3-model: XGBoost+RF+Ridge) | 138.37 ± 5.03 | −40.41 |
| LSTM | 138.28 ± 5.98 | −40.50 |
| **UniSolar Stacking (4-model: XGBoost+RF+Ridge+LSTM)** | **136.84 ± 5.19** | **−41.94** |

### Full-Sample Performance (Stacking, 608k ZINDI records)

| Metric | Value |
|---|---|
| RMSE | 117.47 |
| MAE | 59.83 |
| Global bias | +31.54 |
| Median per-station bias | +0.9 W/m² |

### Robustness

- Cross-validation is **station-grouped** (GroupKFold): no station appears in
  both train and validation within a fold.
- Station bias is **zeroed** during k-fold: prevents station identity leakage.
- Sample weights by **GHI bin frequency**: upweights high-irradiance periods
  (less common, more important for energy yield).

---

## Key Decisions & Findings

### 1. Station Bias Must Be Zeroed in K-Fold

The single most impactful bug fix. When station_bias is real in training but
NaN/0 in validation, tree models learn non-generalizing splits. The fix is:
always zero in k-fold, real only in final training. This corrected ~8 W/m²
of inflated CV results.

### 2. Ratio > kt for Target

kt amplifies cloudy-day errors by multiplying through clear_sky_ghi (large).
Ratio multiplies by GHI_satellite (small on cloudy days). Both targets
produce similar k-fold RMSE but ratio is physically better-behaved and
produces lower median per-station bias.

### 3. Ridge over LightGBM for Diversity

Three tree models (XGBoost, RF, LightGBM) on identical features produce
99.5% correlated predictions — stacking cannot improve. Ridge provides
genuinely different linear predictions that the meta-model can weight
productively.

### 4. Cloud Features Help Linears Most

Ridge benefited most from cloud variability features (−1.65 W/m²) because
it cannot learn non-linear interactions natively. Tree models already
capture some of this through splits, so their improvement was smaller
(−0.54 RF, −0.39 XGBoost).

### 5. LSTM in Stacking Achieves Best Results

The UniSolar Stacking (XGBoost+RF+Ridge+LSTM → XGBoost meta) achieves
**136.84 W/m²** — the best result across all architectures. LSTM contributes
the temporal dimension that static models cannot capture; the meta-model
learns to weight all four predictors optimally. An LSTM 5-ensemble average
(137.95 standalone, −0.33 vs single) is the next expected improvement.

### 6. `power_AOD_55` Is Already MERRA-2

NASA POWER's AOD parameter is sourced from MERRA-2 reanalysis, not from
MODIS or VIIRS satellite retrievals. There is no improvement to be gained
by fetching "raw MERRA-2" — it's the same data, just at different temporal
aggregation. The real upgrade would be MERRA-2 aerosol speciation
(dust, sea salt, BC, OC, sulfate from M2T1NXAER).

### 7. Temporal Footprint Mismatch

NASA POWER GHI is a 3-hour average around each timestamp. Ground truth
is instantaneous. Averaging GT ±1.5h around each POWER timestamp would
better align the targets with the predictors. Not yet implemented but
zero-cost and likely worth +0.5-1 W/m².

### 8. Forward-Chaining Validation Limited

Ground truth data ends November 30, 2018 for most ZINDI stations (only
TA00587 and TA00696 have 2019 data). This makes forward-chaining
TimeSeriesSplit validation less informative — the temporal test windows
are too small to evaluate seasonal generalization properly.

---

## Scripts & Usage

### Training

| Command | What it does |
|---|---|
| `python scripts/retrain_unified.py --kfold 5` | Run grouped 5-fold CV on specified models |
| `python scripts/retrain_unified.py --stacking` | Train stacking ensemble + run CV |
| `python scripts/retrain_unified.py --tune` | Run hyperparameter tuning before final training |
| `python scripts/retrain_unified.py --zindi-only` | Train on ZINDI data only (exclude DB Ghana) |
| `python scripts/retrain_unified.py --forward-chaining N` | Temporal validation with N splits |
| `python scripts/train_lstm.py` | LSTM benchmark vs XGBoost (5-fold) |
| `python scripts/train_lstm.py --seq-len 12 --epochs 60` | Custom LSTM parameters |

### Evaluation & Visualization

| Command | What it produces |
|---|---|
| `python scripts/plot_narrative.py` | 6-panel stakeholder summary (reports/figures/) |
| `python scripts/plot_narrative.py --station TA00360` | Per-station narrative plots |
| `python scripts/plot_rolling_analysis.py --station TA00360` | Rolling mean + cumulative bias |
| `python scripts/plot_rolling_analysis.py --window 14d` | Custom rolling window |
| `python scripts/compare_models.py` | Head-to-head benchmark of saved models |

### Data Pipeline

| Command | What it does |
|---|---|
| `python scripts/fetch_cams_pm25.py` | Download CAMS EAC4 PM2.5 for all locations |
| `python data/ingest_nasa.py` | Fetch NASA POWER data into SQLite DB |
| `python data/ingest_solcast.py` | Fetch Solcast data (alternative satellite source) |
| `python data/ingest_real_csv.py` | Ingest real ground truth from CSV files |

### Production Inference

```python
from core.layers.weather_model import WeatherCorrectionLayer

layer = WeatherCorrectionLayer(model_type='meta')
layer.load_models()
df_corrected = layer.predict(df_satellite)

# df_corrected now has ghi_corrected and dni_corrected columns
```

---

## Data Flow

### File Structure

```
root/
├── core/
│   ├── layers/
│   │   └── weather_model.py    # Feature engineering + production inference
│   ├── models/
│   │   ├── xgboost_ghi.pkl     # Base model (GHI ratio)
│   │   ├── xgboost_dni.pkl     # Base model (DNI ratio)
│   │   ├── rf_ghi.pkl          # Base model (GHI ratio)
│   │   ├── rf_dni.pkl          # Base model (DNI ratio)
│   │   ├── ridge_ghi.pkl       # Base model (GHI ratio)
│   │   ├── ridge_dni.pkl       # Base model (DNI ratio)
│   │   ├── meta_ghi.pkl        # Stacking meta-model (GHI ratio)
│   │   ├── meta_dni.pkl        # Stacking meta-model (DNI ratio)
│   │   └── station_calibration.json  # Per-station bias post-hoc
│   ├── services/
│   │   └── gis.py              # GIS proxy computation (coast dist, elevation)
│   └── database.py             # SQLAlchemy ORM
├── scripts/
│   ├── retrain_unified.py      # Main training pipeline
│   ├── train_lstm.py           # LSTM benchmarks
│   ├── plot_narrative.py       # Stakeholder summary plots
│   ├── plot_rolling_analysis.py# Rolling analysis per station
│   ├── compare_models.py       # Model comparison
│   └── fetch_cams_pm25.py      # CAMS data fetch
├── data/
│   ├── processed/
│   │   ├── training_nasa_power.parquet  # Training data (DB NASA)
│   │   ├── nasa_for_db.parquet          # NASA POWER cache
│   │   ├── cams_pm25.parquet            # CAMS PM2.5 cache
│   │   └── training_info.json           # Training metadata
│   ├── ingest_nasa.py          # NASA data pipeline
│   ├── ingest_solcast.py       # Solcast data pipeline
│   ├── ingest_ground_truth.py  # Ground truth simulation
│   └── ingest_real_csv.py      # CSV ingestion
├── api/
│   └── main.py                 # FastAPI server
├── reports/
│   ├── figures/                # Current plots (9)
│   └── minutes_20260616.md     # Project history
└── frontend/                   # React UI (UniSolar platform)
```

### Data Processing Pipeline

```
NASA POWER API ──→ ingest_nasa.py ──→ SQLite DB (raw)
                                              ↓
CAMS EAC4 API ──→ fetch_cams_pm25.py ──→ cams_pm25.parquet
                                              ↓
ZINDI CSV ──→ retrain_unified.load_zindi() ──→ merged DataFrame
DB SQLite ──→ retrain_unified.load_db_nasa() ──→ merged DataFrame
                                              ↓
                                     add_engineered_features()
                                              ↓
                                    GroupKFold(5) CV
                                              ↓
                                    Train final models
                                              ↓
                                    station_calibration.json
                                              ↓
                                    meta_ghi.pkl (production)
```

---

## Way Forward

### 1. LSTM Ensemble Averaging for Additional Variance Reduction
LSTM is already the 4th base model in UniSolar Stacking (RMSE 136.84). The next
step is to replace the single LSTM with a 5-seed ensemble average, which reduced
RMSE from 138.28 → 137.95 (−0.33) in standalone testing. Expected to add −0.2
to −0.5 W/m² to the full stacking ensemble.

### 2. Station Quality Audit (Zero-Cost)
Cleaning noisy ground truth labels is the highest-leverage zero-cost improvement.
3 faulty stations were mentioned previously — removing or correcting them would
improve every model equally.

### 3. Larger LSTM Architecture
- Hidden dims: 32 → 64 or 128
- Layers: 1 → 2
- Sequence: 8 → 16 timesteps (48h lookback)
- Systematic hyperparameter search

### 4. MERRA-2 Aerosol Speciation
Current `power_AOD_55` is bulk AOD at 550nm (already MERRA-2). Fetching hourly
aerosol components directly from GES DISC MERRA-2 (M2T1NXAER) would provide:
dust, sea salt, black carbon, organic carbon, sulfate — each with different
optical properties. Most relevant for Sahel dust events and biomass burning
season. Requires NASA Earthdata authentication.

### 5. GT Temporal Averaging
Average ground truth ±1.5h around each NASA POWER timestamp to match temporal
footprints. Zero-cost, likely +0.5-1 W/m².

### 6. Grid Search on Cloud Features
The stacking ensemble's grid search was last run before cloud variability features
were added. Retuning would find optimal hyperparameters for the new feature set.

---

## Constraints

- **Memory**: LSTM full 5-fold CV was killed multiple times on 16 GB M3 Mac.
  Resolved by running LSTM and XGBoost as separate processes. Larger LSTM
  architectures may require GPU or reduced batch size.
- **Temporal coverage**: ZINDI ground truth ends Nov 30, 2018 for most stations.
  Only TA00587 and TA00696 have 2019 data. This limits forward-chaining validation.
- **Spatial coverage**: 38 stations across West Africa, concentrated in Ghana and
  Nigeria. Sparse coverage in Mali, Niger, Chad (where Saharan dust is heaviest).

---

## Project History

Detailed project history and minutes available at `reports/minutes_20260616.md`.

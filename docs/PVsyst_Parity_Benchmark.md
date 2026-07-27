# PVsyst Parity Benchmark

## Reference System

| Parameter         | Value                   |
|-------------------|-------------------------|
| Location          | Accra, Ghana (5.6°N, 0.19°W) |
| Array size        | 10 kWp                  |
| Module            | Canadian Solar CS6X-340M (or Sandia equivalent) |
| Tilt / Azimuth    | 10° / 180° (south)      |
| GCR               | 0.40                    |
| Inverter           | SMA Sunny Boy 10 kW (98% eff) |
| Weather data      | NASA POWER 2023 (hourly GHI, DNI, DHI, temp, wind) |
| System losses     | Soiling 2%, wiring 2%, mismatch 2%, LID 2%, shading per simulation |
| Ground reflectance| 0.25 (albedo)           |
| Bifacial gain     | Not modeled (front-side only) |

## Methodology Comparison

### PVsyst 7.4

- **Engine**: One-diode model (explicit 5-parameter); Sandia Array Performance Model (SAPM) for module behavior.
- **Weather**: TMY or hourly measured/satellite data; default is Meteonorm.
- **Irradiance model**: Full 3D scene shading with near-shading horizon, diffuse irradiance decomposition (Hay-Davies), and electrical shading simulation.
- **Losses**: Detailed row-to-row shading with electrical mismatch; inverter clipping; module quality loss; degradation; soiling (user-specified).
- **Validation**: Monthly/annual reports; specific yield in kWh/kWp; performance ratio.

### UniSolar 6-Layer Pipeline

| Layer | Model | Source |
|-------|-------|--------|
| L1 Weather | XGBoost ML correction on NASA POWER | `weather_model.py` |
| L2 Environmental | Dynamic soiling + rain scaling + degradation | `environmental_model.py` |
| L3 Physics | PVLib ModelChain (SAPM / CEC) | `physics_model.py` |
| L4 Sustainability | Carbon avoidance | `sustainability_model.py` |
| L5 Financial | DCF / NPV / IRR / LCOE / DSCR | `financial_model.py` |
| L6 Geometry | Row pitch = `width × cos(tilt) / GCR` | `geometry_model.py` |

**Key difference**: UniSolar uses PVLib's SAPM internally (identical to PVsyst's one-diode model). The 6-layer pipeline adds ML weather correction and financial modeling beyond PVsyst's scope.

## Expected Parity Results

Based on literature review of PVsyst vs PVLib comparisons and typical Ghana solar resource data:

| Metric | PVsyst (Typical) | UniSolar (Expected) | Tolerance |
|--------|------------------|---------------------|-----------|
| Annual yield | 1,400–1,600 kWh/kWp | 1,200–1,800 kWh/kWp | ±15% |
| Performance ratio | 75–82% | 72–85% | ±5pp |
| LCOE | 0.08–0.12 GH₵/kWh | 0.06–0.14 GH₵/kWh | ±20% |
| Monthly shape | Peak March/April, dip July/Aug | Same | Qualitative match |

### Why Differences Are Expected

1. **Weather data**: PVsyst uses Meteonorm or on-site measurements; UniSolar uses NASA POWER with XGBoost correction. NASA POWER is satellite-derived and can differ ±10% from ground truth.
2. **Soiling model**: PVsyst uses user-specified fixed soiling; UniSolar uses a dynamic model with rain-dependent cleaning.
3. **Shading**: PVsyst performs detailed 3D near-shading; UniSolar uses `pvlib.shading.shaded_fraction1d` (1D infinite-row model).
4. **Temperature model**: Both use Sandia temperature model but with potentially different air mass models.
5. **Inverter model**: Both use Sandia/CEC inverter database but may select different representative units.

## Recommended Validation Protocol

### Step 1: Run UniSolar Reference System

```bash
curl -X POST http://127.0.0.1:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": 5.6,
    "longitude": -0.19,
    "tilt": 10,
    "azimuth": 180,
    "system_capacity_kw": 10,
    "gcr": 0.4,
    "year": 2023,
    "use_ecg_tariff": true,
    "include_obstacles": false,
    "include_environmental": true,
    "module_name": "Canadian_Solar_Inc__CS6X_340M__2015_",
    "inverter_name": "SMA_America__STP_10000TL_US_10__480V_"
  }'
```

### Step 2: Export Results

```json
{
  "annual_energy_kwh": "...",
  "kwh_per_kw": "...",
  "performance_ratio": "...",
  "capacity_factor_pct": "...",
  "lcoe_usd_per_kwh": "..."
}
```

### Step 3: Run PVsyst Reference System

In PVsyst 7.4:
1. Create new project → Accra, Ghana (or nearest weather station)
2. Import same weather data (NASA POWER 2023 hourly)
3. Define same array: 10 kWp, 10° tilt, 180° azimuth, GCR 0.4
4. Select same module and inverter
5. Run simulation → report annual yield, PR, monthly breakdown

### Step 4: Compare

| Check | Accept Criterion |
|-------|------------------|
| Annual yield difference | < 15% |
| Performance ratio difference | < 5 percentage points |
| Monthly energy shape correlation | R² > 0.90 |
| LCOE difference | < 20% |

## Test Suite Coverage

Our 78 Python tests validate each layer independently:

| Test File | Tests | What It Validates |
|-----------|-------|-------------------|
| `test_geometry_model.py` | 12 | Row pitch formula, GCR relationships, frontend parity |
| `test_physics_model.py` | 12 | PVLib model chain, Sandia/CEC databases, yield sanity (800–2500 kWh/kWp), inverter efficiency |
| `test_environmental_model.py` | 10 | Degradation presets, soiling dynamics, rain cleaning |
| `test_financial_model.py` | 22 | NPV, IRR, LCOE, payback, DSCR, CAPEX, O&M |
| `test_ecg_tariff.py` | 8 | ECG tariff table lookups, interpolation |
| `test_monte_carlo.py` | 11 | P50/P90 uncertainty, cross-layer consistency |

## Hand-Calculated Reference Values

These are deterministic values for the reference system that serve as ground truth:

```
System: 10 kWp, Ghana, 2023, ECG residential tariff

Row pitch:       2.1 × cos(10°) / 0.40 = 5.17 m
Capex:           10 × 12,000 = GH₵ 120,000
Annual O&M:      10 × 320 = GH₵ 3,200
Year-1 savings:  15,000 × 1.90 = GH₵ 28,500
Year-1 net:      28,500 − 3,200 = GH₵ 25,300
LCOE:            120,000 / (15,000 × 25 × 0.882) = GH₵ 0.036/kWh
DSCR annuity:    78,000 × 0.12 × 1.12^10 / (1.12^10 − 1) = GH₵ 13,980/yr
Min DSCR:        25,300 / 13,980 = 1.81x
Degradation Y25: 0.995^25 = 0.882
```

## Next Steps

1. **Run UniSolar reference system** and capture output JSON
2. **Install PVsyst demo** (free 30-day trial) and configure identical system
3. **Compare** annual yield, PR, monthly shape
4. **Document** any systematic biases and apply correction factors if needed
5. **Create golden-file snapshots** for 5 Ghana reference sites

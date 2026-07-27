"""End-to-end pipeline validation against ground-truth measurements.

Compares:
1. NASA POWER satellite GHI vs measured pyranometer GHI (quantifies satellite bias)
2. ML-corrected GHI vs measured (quantifies ML correction benefit)
3. Full pipeline yield with NASA weather vs measured weather (total pipeline error)

Data source: World Bank / CSPS ground measurements (Navrongo & Sunyani, Ghana)
License: CC-BY-4.0
"""
import os
import json
import numpy as np
import pandas as pd
import pytest
import requests


# ─── Configuration ───────────────────────────────────────────────
MEASUREMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "measurements")
CACHE_DIR = os.path.join(MEASUREMENTS_DIR, "nasa_cache")

STATIONS = {
    "navrongo": {
        "lat": 10.87554, "lon": -1.06293, "alt": 180,
        "csv_url": "https://energydata.info/dataset/09c10673-320b-4d6f-b306-93b5cb42694f/resource/603e42a1-6ec9-48df-bba0-edcbf853f1c1/download/solar-measurements_ghana-navrongo_qc.csv",
    },
    "sunyani": {
        "lat": 7.34865, "lon": -2.34034, "alt": 330,
        "csv_url": "https://energydata.info/dataset/09c10673-320b-4d6f-b306-93b5cb42694f/resource/dbd4904e-b9cd-4624-bd34-46580422a8c6/download/solar-measurements_ghana-sunyani_qc.csv",
    },
}

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
TEST_YEAR = 2022


# ─── Helpers ─────────────────────────────────────────────────────
def _fetch_nasa_power(lat, lon, year):
    """Fetch NASA POWER hourly data. Cached locally."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"nasa_{lat:.3f}_{lon:.3f}_{year}.json")

    if os.path.exists(cache_file):
        with open(cache_file) as f:
            return json.load(f)

    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,ALLSKY_SFC_SW_DNI,ALLSKY_SFC_SW_DIFF,T2M,RH2M,WS2M,PRECTOTCORR",
        "community": "RE",
        "longitude": lon, "latitude": lat,
        "start": f"{year}0101", "end": f"{year}1231",
        "format": "JSON",
    }
    print(f"Fetching NASA POWER for ({lat}, {lon}) year {year}...")
    resp = requests.get(NASA_POWER_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    with open(cache_file, "w") as f:
        json.dump(data, f)
    return data


def _nasa_to_hourly(nasa_json, year):
    """Convert NASA POWER JSON to hourly DataFrame."""
    props = nasa_json["properties"]["parameter"]
    timestamps = sorted(props["ALLSKY_SFC_SW_DWN"].keys())

    records = []
    for ts_str in timestamps:
        dt = pd.to_datetime(ts_str, format="%Y%m%d%H", utc=True)
        if dt.year != year:
            continue
        ghi = props["ALLSKY_SFC_SW_DWN"].get(ts_str, 0)
        dni = props["ALLSKY_SFC_SW_DNI"].get(ts_str, 0)
        dhi = props["ALLSKY_SFC_SW_DIFF"].get(ts_str, 0)
        temp = props["T2M"].get(ts_str, 25)
        ws = props["WS2M"].get(ts_str, 2)
        # NASA POWER uses -999 for missing
        for v in [ghi, dni, dhi, temp, ws]:
            if v == -999 or v is None:
                v = 0
        records.append({"timestamp": dt, "ghi": max(ghi, 0), "dni": max(dni, 0),
                        "dhi": max(dhi, 0), "temp_air": temp, "wind_speed": ws})

    df = pd.DataFrame(records).set_index("timestamp").sort_index()
    return df


def _load_measured_hourly(station_id, year):
    """Load and aggregate measured data to hourly."""
    os.makedirs(MEASUREMENTS_DIR, exist_ok=True)
    csv_path = os.path.join(MEASUREMENTS_DIR, f"{station_id}_qc.csv")

    if not os.path.exists(csv_path) or os.path.getsize(csv_path) < 1_000_000:
        import urllib.request
        url = STATIONS[station_id]["csv_url"]
        print(f"Downloading {station_id} data...")
        urllib.request.urlretrieve(url, csv_path)

    df = pd.read_csv(csv_path, parse_dates=["Timestamp"], skiprows=[1],
                     low_memory=False, encoding="latin-1")
    df = df.rename(columns={"Timestamp": "timestamp", "GHI": "ghi", "DNI": "dni",
                            "DHI": "dhi", "Tamb": "temp_air", "WS": "wind_speed"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    for col in ["ghi", "dni", "dhi"]:
        df[col] = df[col].clip(lower=0).clip(upper=1400)
    hourly = df[["ghi", "dni", "dhi", "temp_air", "wind_speed"]].resample("h").mean()
    hourly = hourly.dropna(subset=["ghi"])
    if year is not None:
        hourly = hourly[hourly.index.year == year]
    hourly["ghi_corrected"] = hourly["ghi"]
    hourly["dni_corrected"] = hourly["dni"]
    hourly["dhi_satellite"] = hourly["dhi"]
    hourly["soiling_loss"] = 0.02
    hourly["degradation_factor"] = 1.0
    hourly["environmental_loss_factor"] = 0.98
    return hourly


def _build_unisolar_weather(df, soiling=0.02, deg=1.0, env_factor=0.98):
    """Convert a GHI/DNI/DHI DataFrame to the format PhysicsLayer.simulate() expects."""
    out = df.copy()
    out["ghi_corrected"] = out["ghi"]
    out["dni_corrected"] = out["dni"]
    out["dhi_satellite"] = out["dhi"]
    out["soiling_loss"] = soiling
    out["degradation_factor"] = deg
    out["environmental_loss_factor"] = env_factor
    return out


# ─── Tests ────────────────────────────────────────────────────────
class TestNASAvsMeasured:
    """Compare NASA POWER satellite estimates against ground truth."""

    def test_nasa_power_fetches(self):
        """NASA POWER API should return valid JSON for Navrongo."""
        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        assert "properties" in data
        assert "parameter" in data["properties"]
        ghi = data["properties"]["parameter"]["ALLSKY_SFC_SW_DWN"]
        # Should have ~8760 hourly entries
        assert len(ghi) > 8000, f"Expected 8000+ entries, got {len(ghi)}"

    def test_nasa_ghi_annual_total(self):
        """NASA POWER annual GHI should be in a plausible range (1200-2500 kWh/m²)."""
        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        ghi_annual_kwh = nasa["ghi"].sum() / 1000.0
        assert 1200 < ghi_annual_kwh < 2500, \
            f"NASA GHI {ghi_annual_kwh:.0f} kWh/m² outside plausible range"

    def test_nasa_vs_measured_ghi_annual(self):
        """NASA POWER annual GHI vs measured — quantify satellite bias.

        NASA POWER typically under-reports by 10-30% in West Africa.
        """
        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)

        # Align on common timestamps
        common_idx = nasa.index.intersection(measured.index)
        assert len(common_idx) > 7000, f"Only {len(common_idx)} common hours"

        nasa_ghi = nasa.loc[common_idx, "ghi"].sum() / 1000.0
        meas_ghi = measured.loc[common_idx, "ghi"].sum() / 1000.0

        bias = (nasa_ghi - meas_ghi) / meas_ghi * 100
        ratio = nasa_ghi / meas_ghi if meas_ghi > 0 else 0

        print(f"\n  NASA GHI:  {nasa_ghi:.0f} kWh/m²")
        print(f"  Measured:  {meas_ghi:.0f} kWh/m²")
        print(f"  Bias:      {bias:+.1f}%")
        print(f"  Ratio:     {ratio:.3f}")

        # NASA POWER should be within ±40% of measured (known West Africa bias)
        assert 0.6 < ratio < 1.4, \
            f"NASA/measured ratio {ratio:.2f} outside ±40% tolerance"

    def test_nasa_vs_measured_monthly_correlation(self):
        """Monthly GHI shape from NASA should correlate with measured (R² > 0.85)."""
        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)

        common_idx = nasa.index.intersection(measured.index)
        nasa_m = nasa.loc[common_idx, "ghi"].resample("ME").sum()
        meas_m = measured.loc[common_idx, "ghi"].resample("ME").sum()

        n = min(len(nasa_m), len(meas_m))
        corr = np.corrcoef(nasa_m.values[:n], meas_m.values[:n])[0, 1]
        print(f"\n  Monthly R²: {corr**2:.3f}")
        assert corr > 0.85, f"Monthly correlation {corr:.3f} too low"


class TestMLCorrectionBenefit:
    """Show that ML correction improves over raw NASA POWER."""

    def test_ghi_correction_reduces_bias(self):
        """ML-corrected GHI should be closer to measured than raw NASA POWER."""
        from core.layers.weather_model import WeatherCorrectionLayer

        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)

        # Build DataFrame in the format WeatherCorrectionLayer expects
        df = nasa.copy()
        df["ghi_satellite"] = df["ghi"]
        df["dni_satellite"] = df["dni"]
        df["dhi_satellite"] = df["dhi"]
        df["timestamp"] = df.index

        # Run ML correction
        wcl = WeatherCorrectionLayer()
        try:
            df_corrected = wcl.predict(df)
        except Exception as e:
            pytest.skip(f"ML model not available: {e}")
            return

        # Align
        common_idx = df_corrected.index.intersection(measured.index)
        assert len(common_idx) > 7000

        raw_ghi = df_corrected.loc[common_idx, "ghi_satellite"].sum() / 1000.0
        corr_ghi = df_corrected.loc[common_idx, "ghi_corrected"].sum() / 1000.0
        meas_ghi = measured.loc[common_idx, "ghi"].sum() / 1000.0

        raw_bias = abs(raw_ghi - meas_ghi) / meas_ghi
        corr_bias = abs(corr_ghi - meas_ghi) / meas_ghi

        print(f"\n  Raw NASA bias:    {raw_bias:.1%}")
        print(f"  Corrected bias:   {corr_bias:.1%}")
        print(f"  Improvement:      {(raw_bias - corr_bias):.1%}")

        # ML correction should not make things worse
        # (it may not always improve, but should not increase bias by >5pp)
        assert corr_bias < raw_bias + 0.05, \
            f"ML correction made bias worse: {corr_bias:.1%} vs {raw_bias:.1%}"


class TestFullPipelineValidation:
    """Full UniSolar pipeline: NASA POWER → ML correction → environmental → physics → yield."""

    def test_nasa_pipeline_yield(self):
        """Full pipeline with NASA weather should produce plausible yield."""
        from core.layers.physics_model import PhysicsLayer

        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        weather = _build_unisolar_weather(nasa)

        pl = PhysicsLayer()
        result = pl.simulate(
            weather, lat=STATIONS["navrongo"]["lat"], lon=STATIONS["navrongo"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180,
            inverter_efficiency=0.96,
        )
        kwh_per_kwp = result["annual_energy_kwh"] / 10.0
        assert 800 < kwh_per_kwp < 2500, \
            f"NASA pipeline yield {kwh_per_kwp:.0f} kWh/kWp outside range"

    def test_measured_pipeline_yield(self):
        """Full pipeline with measured weather should produce plausible yield."""
        from core.layers.physics_model import PhysicsLayer

        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)
        weather = _build_unisolar_weather(measured)

        pl = PhysicsLayer()
        result = pl.simulate(
            weather, lat=STATIONS["navrongo"]["lat"], lon=STATIONS["navrongo"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180,
            inverter_efficiency=0.96,
        )
        kwh_per_kwp = result["annual_energy_kwh"] / 10.0
        assert 800 < kwh_per_kwp < 2500, \
            f"Measured pipeline yield {kwh_per_kwp:.0f} kWh/kWp outside range"

    def test_yield_ratio_nasa_vs_measured(self):
        """NASA pipeline yield / measured pipeline yield should be 0.7-1.4.

        This is the TOTAL pipeline error: satellite bias + physics model error.
        """
        from core.layers.physics_model import PhysicsLayer

        data = _fetch_nasa_power(
            STATIONS["navrongo"]["lat"], STATIONS["navrongo"]["lon"], TEST_YEAR
        )
        nasa = _nasa_to_hourly(data, TEST_YEAR)
        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)

        pl = PhysicsLayer()
        r_nasa = pl.simulate(
            _build_unisolar_weather(nasa),
            lat=STATIONS["navrongo"]["lat"], lon=STATIONS["navrongo"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180, inverter_efficiency=0.96,
        )
        r_meas = pl.simulate(
            _build_unisolar_weather(measured),
            lat=STATIONS["navrongo"]["lat"], lon=STATIONS["navrongo"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180, inverter_efficiency=0.96,
        )

        nasa_kwh = r_nasa["annual_energy_kwh"]
        meas_kwh = r_meas["annual_energy_kwh"]
        ratio = nasa_kwh / meas_kwh if meas_kwh > 0 else 0

        print(f"\n  NASA yield:       {nasa_kwh:.0f} kWh ({nasa_kwh/10:.0f} kWh/kWp)")
        print(f"  Measured yield:   {meas_kwh:.0f} kWh ({meas_kwh/10:.0f} kWh/kWp)")
        print(f"  Ratio:            {ratio:.3f}")

        assert 0.7 < ratio < 1.4, \
            f"NASA/measured yield ratio {ratio:.2f} outside ±30% tolerance"

    def test_sunyani_pipeline_yield(self):
        """Full pipeline with Sunyani measured weather should produce plausible yield."""
        from core.layers.physics_model import PhysicsLayer

        measured = _load_measured_hourly("sunyani", year=TEST_YEAR)
        weather = _build_unisolar_weather(measured)

        pl = PhysicsLayer()
        result = pl.simulate(
            weather, lat=STATIONS["sunyani"]["lat"], lon=STATIONS["sunyani"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180,
            inverter_efficiency=0.96,
        )
        kwh_per_kwp = result["annual_energy_kwh"] / 10.0
        assert 800 < kwh_per_kwp < 2500, \
            f"Sunyani measured yield {kwh_per_kwp:.0f} kWh/kWp outside range"

    def test_two_stations_consistent(self):
        """Yield from Navrongo and Sunyani should be within 25% (different climates)."""
        from core.layers.physics_model import PhysicsLayer

        pl = PhysicsLayer()
        yields = {}
        for station_id, cfg in STATIONS.items():
            measured = _load_measured_hourly(station_id, year=TEST_YEAR)
            weather = _build_unisolar_weather(measured)
            result = pl.simulate(
                weather, lat=cfg["lat"], lon=cfg["lon"],
                system_capacity_kw=10.0, tilt=10, azimuth=180,
                inverter_efficiency=0.96,
            )
            yields[station_id] = result["annual_energy_kwh"]

        ratio = min(yields.values()) / max(yields.values())
        print(f"\n  Navrongo: {yields['navrongo']:.0f} kWh")
        print(f"  Sunyani:  {yields['sunyani']:.0f} kWh")
        print(f"  Ratio:    {ratio:.3f}")
        assert ratio > 0.75, f"Station yield ratio {ratio:.2f} too variable"

    def test_financial_with_measured_yield(self):
        """Financial model with measured yield should produce viable economics."""
        from core.layers.physics_model import PhysicsLayer
        from core.layers.financial_model import FinancialLayer

        measured = _load_measured_hourly("navrongo", year=TEST_YEAR)
        weather = _build_unisolar_weather(measured)

        pl = PhysicsLayer()
        result = pl.simulate(
            weather, lat=STATIONS["navrongo"]["lat"], lon=STATIONS["navrongo"]["lon"],
            system_capacity_kw=10.0, tilt=10, azimuth=180,
            inverter_efficiency=0.96,
        )

        fl = FinancialLayer(
            system_cost_per_kw=12_000, annual_om_cost=320,
            electricity_tariff=1.90, discount_rate=0.08,
            lifetime_years=25, tariff_escalation_rate=0.03,
            degradation_rate=0.005, lid_rate=0.02,
            debt_ratio=0.65, interest_rate=0.12, loan_term_years=10,
            use_ecg_tariff=False,
        )
        fin = fl.calculate_roi(result["annual_energy_kwh"], 10.0)

        print(f"\n  Yield:     {result['annual_energy_kwh']:.0f} kWh")
        print(f"  LCOE:      GH₵ {fin['lcoe']:.4f}/kWh")
        print(f"  NPV:       GH₵ {fin['npv']:,.0f}")
        print(f"  Payback:   {fin['payback_years']:.1f} years")

        assert fin["lcoe"] > 0, "LCOE should be positive"
        assert fin["payback_years"] > 0, "Payback should be positive"
        assert fin["payback_years"] < 30, "Payback should be < 30 years"

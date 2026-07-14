"""
validate_era5.py
================
Validates UniSolar against ERA5 reanalysis as an independent benchmark.

Compares three systems against ZINDI ground truth per station:
  1. Raw NASA POWER (baseline)
  2. UniSolar Stacking (trained model)
  3. ERA5 reanalysis (shortwave radiation)

Usage:
    python scripts/validate_era5.py
    python scripts/validate_era5.py --output reports/era5_validation.md
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from core.layers.weather_model import WeatherCorrectionLayer

EXCLUDED = {'TA00295', 'TA00064', 'TA00219', 'TA00338'}

RENAMES = {
    "power_ALLSKY_SFC_SW_DWN": "ghi_satellite",
    "power_ALLSKY_SFC_SW_DNI": "dni_satellite",
    "power_ALLSKY_SFC_SW_DIFF": "dhi_satellite",
    "power_T2M": "temp_air",
    "power_RH2M": "relative_humidity",
    "power_WS2M": "wind_speed",
}

ERA5_GHI = "era5_shortwave_radiation"


def load_data():
    """Load ZINDI train, NASA POWER, and ERA5 data; return merged DataFrame."""
    train_path = "/Users/kagya/Desktop/ZINDI-PROJECT/Train.csv"
    power_path = "/Users/kagya/Desktop/ZINDI-PROJECT/data/nasa_power.parquet"
    era5_path = "/Users/kagya/Desktop/ZINDI-PROJECT/data/era5_openmeteo.parquet"

    train = pd.read_csv(train_path, parse_dates=["timestamp"])
    power = pd.read_parquet(power_path)
    power["timestamp"] = pd.to_datetime(power["timestamp"])
    era5 = pd.read_parquet(era5_path)

    # Filter faulty stations
    train = train[~train["station"].isin(EXCLUDED)]

    # Hour-floor for merging
    train["_hour"] = train["timestamp"].dt.floor("h")
    power["_hour"] = power["timestamp"].dt.floor("h")
    era5["_hour"] = era5["timestamp"].dt.floor("h")

    # Deduplicate POWER (multiple rows per hour per station in raw data)
    power = power.drop_duplicates(subset=["station", "_hour"])

    power_cols = list(RENAMES.keys()) + ["power_CLRSKY_SFC_SW_DWN",
                                          "power_CLOUD_AMT", "power_AOD_55"]
    power_cols = [c for c in power_cols if c in power.columns]

    era5_cols = [ERA5_GHI, "era5_direct_radiation", "era5_diffuse_radiation",
                 "era5_cloudcover", "era5_temperature_2m", "era5_relativehumidity_2m",
                 "era5_windspeed_10m", "era5_surface_pressure",
                 "era5_dewpoint_2m", "era5_precipitation",
                 "era5_cloudcover_low", "era5_cloudcover_mid", "era5_cloudcover_high"]

    merged = train.merge(
        power[["station", "_hour"] + power_cols],
        on=["station", "_hour"], how="inner"
    ).merge(
        era5[["station", "_hour"] + era5_cols],
        on=["station", "_hour"], how="inner"
    )
    merged.drop(columns=["_hour"], inplace=True)
    return merged


def prepare_for_inference(df_st, lat, lon):
    """Build a DataFrame ready for WeatherCorrectionLayer.predict()."""
    df = df_st.copy()
    for src, dst in RENAMES.items():
        df[dst] = df[src]
    df["albedo"] = 0.2
    df["latitude"] = lat
    df["longitude"] = lon

    aod = df.get("power_AOD_55", pd.Series(0.15, index=df.index)).fillna(0.15)
    aod = pd.to_numeric(aod, errors="coerce").fillna(0.15)
    pm25 = aod * 60.0
    df["pm25"] = np.clip(pm25, 5.0, 400.0)
    df["aod_550"] = aod.astype("float32")
    df["cloud_amt"] = df.get("power_CLOUD_AMT", pd.Series(0.5, index=df.index)).fillna(0.5)

    df["hour"] = df["timestamp"].dt.hour.astype(int)
    df["month"] = df["timestamp"].dt.month.astype(int)

    gis = WeatherCorrectionLayer()
    d, e, z = gis._get_proxies(lat, lon)
    df["dist_to_coast_km"] = d
    df["elevation_m"] = e
    df["climate_zone"] = z

    return df


def compute_metrics(y_true, y_pred, label):
    """Return dict of metrics."""
    mask = ~np.isnan(y_true) & ~np.isnan(y_pred)
    y_t, y_p = y_true[mask], y_pred[mask]
    if len(y_t) < 10:
        return {"label": label, "records": 0, "rmse": np.nan, "mae": np.nan,
                "mbe": np.nan, "r2": np.nan}
    return {
        "label": label,
        "records": len(y_t),
        "rmse": float(np.sqrt(mean_squared_error(y_t, y_p))),
        "mae": float(mean_absolute_error(y_t, y_p)),
        "mbe": float(np.mean(y_p - y_t)),
        "r2": float(r2_score(y_t, y_p)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="reports/era5_validation.md")
    parser.add_argument("--station", type=str, default=None,
                        help="Single station to validate (default: all)")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print("Loading data...")
    df = load_data()
    print(f"  Merged dataset: {len(df):,} records, {df['station'].nunique()} stations")

    stations = sorted(df["station"].unique())
    if args.station:
        stations = [s for s in stations if s == args.station]
        if not stations:
            print(f"Station {args.station} not found.")
            return

    print(f"Loading UniSolar stacking model ('meta')...")
    layer = WeatherCorrectionLayer(model_type="meta")
    layer.load_models()

    all_rows = []
    for station in stations:
        df_st = df[df["station"] == station].copy()
        df_st = df_st.dropna(subset=["power_ALLSKY_SFC_SW_DWN", ERA5_GHI, "radiation (W/m2)"])
        if len(df_st) < 100:
            continue

        lat = df_st["latitude"].iloc[0]
        lon = df_st["longitude"].iloc[0]
        country = df_st["country"].iloc[0]

        y_true = df_st["radiation (W/m2)"].values

        # 1) Raw NASA POWER
        raw_ghi = df_st["power_ALLSKY_SFC_SW_DWN"].values

        # 2) ERA5
        era5_ghi = df_st[ERA5_GHI].values

        # 3) UniSolar stacking
        try:
            df_input = prepare_for_inference(df_st, lat, lon)
            df_out = layer.predict(df_input.copy())
            uni_ghi = df_out["ghi_corrected"].values
        except Exception as e:
            print(f"  Error on {station}: {e}")
            continue

        for label, pred in [("Raw NASA POWER", raw_ghi),
                             ("ERA5", era5_ghi),
                             ("UniSolar Stacking", uni_ghi)]:
            m = compute_metrics(y_true, pred, label)
            m["station"] = station
            m["country"] = country
            m["lat"] = round(lat, 2)
            m["lon"] = round(lon, 2)
            all_rows.append(m)

    if not all_rows:
        print("No results generated.")
        return

    df_res = pd.DataFrame(all_rows)

    # --- Build report ---
    lines = []
    lines.append("# ERA5 Validation Report — UniSolar Layer 1")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Stations:** {df_res['station'].nunique()}")
    lines.append(f"**Total Records:** {df_res['records'].sum():,}")
    lines.append("")
    lines.append("Compares UniSolar Stacking against raw NASA POWER and ERA5 reanalysis "
                 "shortwave radiation, using ZINDI ground truth as reference.")
    lines.append("")

    # Overall summary
    lines.append("## Overall Performance Summary")
    lines.append("")
    lines.append("| System | Stations | Records | RMSE | MAE | MBE | R² |")
    lines.append("|---|---|---|---|---|---|---|")

    summary = df_res.groupby("label").agg(
        stations=("station", "nunique"),
        records=("records", "sum"),
        rmse=("rmse", "mean"),
        mae=("mae", "mean"),
        mbe=("mbe", "mean"),
        r2=("r2", "mean"),
    ).sort_values("rmse")

    for label, r in summary.iterrows():
        lines.append(
            f"| {label:<20s} | {r['stations']:>3.0f} | {r['records']:>7,.0f} | "
            f"{r['rmse']:>6.2f} | {r['mae']:>6.2f} | {r['mbe']:>+7.2f} | {r['r2']:>6.4f} |"
        )
    lines.append("")

    best = summary["rmse"].idxmin()
    lines.append(f"**Best overall:** `{best}` (mean RMSE = {summary.loc[best, 'rmse']:.2f} W/m²)")
    lines.append("")

    # Pairwise comparison (UniSolar vs ERA5)
    lines.append("## UniSolar vs ERA5 — Per-Station Leaderboard")
    lines.append("")
    lines.append("| Station | Country | Records | UniSolar RMSE | ERA5 RMSE | Δ (ERA5−Uni) | Winner |")
    lines.append("|---|---|---|---|---|---|---|")

    uni = df_res[df_res["label"] == "UniSolar Stacking"].set_index("station")
    era = df_res[df_res["label"] == "ERA5"].set_index("station")

    station_wins = {"UniSolar": 0, "ERA5": 0}
    for st in sorted(uni.index.intersection(era.index)):
        u_rmse = uni.loc[st, "rmse"]
        e_rmse = era.loc[st, "rmse"]
        delta = e_rmse - u_rmse
        winner = "UniSolar" if delta > 0 else "ERA5" if delta < 0 else "Tie"
        station_wins[winner] = station_wins.get(winner, 0) + 1
        lines.append(
            f"| {st} | {uni.loc[st, 'country']} | {uni.loc[st, 'records']:>6,.0f} | "
            f"{u_rmse:>10.2f} | {e_rmse:>10.2f} | {delta:>+10.2f} | {winner:<10s} |"
        )

    lines.append("")
    total = uni.index.intersection(era.index)
    lines.append(f"**UniSolar wins:** {station_wins.get('UniSolar', 0)} / {len(total)} stations")
    lines.append(f"**ERA5 wins:** {station_wins.get('ERA5', 0)} / {len(total)} stations")
    lines.append("")

    # Error distribution
    lines.append("## Error Distribution (MBE per station)")
    lines.append("")
    lines.append("| Station | Raw NASA MBE | ERA5 MBE | UniSolar MBE |")
    lines.append("|---|---|---|---|")

    raw = df_res[df_res["label"] == "Raw NASA POWER"].set_index("station")
    for st in sorted(raw.index.intersection(uni.index).intersection(era.index)):
        lines.append(
            f"| {st} | {raw.loc[st, 'mbe']:>+13.2f} | "
            f"{era.loc[st, 'mbe']:>9.2f} | {uni.loc[st, 'mbe']:>13.2f} |"
        )
    lines.append("")

    # Station metadata
    lines.append("## Station Information")
    lines.append("")
    lines.append("| Station | Country | Lat | Lon | Records |")
    lines.append("|---|---|---|---|---|")
    info = df_res[df_res["label"] == "UniSolar Stacking"].set_index("station")
    for st in sorted(info.index):
        lines.append(
            f"| {st} | {info.loc[st, 'country']} | {info.loc[st, 'lat']} | "
            f"{info.loc[st, 'lon']} | {info.loc[st, 'records']:>7,.0f} |"
        )
    lines.append("")

    with open(args.output, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Console summary
    print()
    print("=" * 70)
    print("ERA5 VALIDATION SUMMARY")
    print("=" * 70)
    print(f"{'System':<22s} {'RMSE':>8s} {'MAE':>8s} {'MBE':>9s} {'R²':>8s}")
    print("-" * 60)
    for label, r in summary.iterrows():
        print(f"{label:<22s} {r['rmse']:>7.2f}  {r['mae']:>7.2f}  {r['mbe']:>+8.2f}  {r['r2']:>7.4f}")
    print("-" * 60)
    print(f"Best: {best} ({summary.loc[best, 'rmse']:.2f} W/m²)")
    print(f"UniSolar beats ERA5 on {station_wins.get('UniSolar', 0)}/{len(total)} stations")
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()

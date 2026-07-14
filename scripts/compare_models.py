"""
compare_models.py
=================
Benchmarks all trained models against naive baselines on ZINDI data.
Includes seasonal breakdowns, significance testing, and inference timing.

Usage
-----
    python scripts/compare_models.py
    python scripts/compare_models.py --station TA00118
    python scripts/compare_models.py --output reports/model_comparison.md
"""

import argparse
import os
import sys
import time
import numpy as np
import pandas as pd
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from scipy.stats import wilcoxon

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from core.layers.weather_model import WeatherCorrectionLayer

MODELS = ["xgboost", "rf", "ridge", "meta"]
SEASONS = {"DJF": [12, 1, 2], "MAM": [3, 4, 5], "JJA": [6, 7, 8], "SON": [9, 10, 11]}


def load_zindi_data():
    """Load and prepare ZINDI benchmark dataset."""
    train_path = "/Users/kagya/Desktop/ZINDI-PROJECT/Train.csv"
    power_path = "/Users/kagya/Desktop/ZINDI-PROJECT/data/nasa_power.parquet"

    if not os.path.exists(train_path) or not os.path.exists(power_path):
        print("ZINDI data not found.")
        return pd.DataFrame()

    train = pd.read_csv(train_path)
    train["timestamp"] = pd.to_datetime(train["timestamp"])
    power = pd.read_parquet(power_path)
    power["timestamp"] = pd.to_datetime(power["timestamp"])

    train["_merge_hour"] = train["timestamp"].dt.floor("h")
    power["_merge_hour"] = power["timestamp"].dt.floor("h")

    power_cols = [
        "power_ALLSKY_SFC_SW_DWN", "power_CLRSKY_SFC_SW_DWN",
        "power_ALLSKY_SFC_SW_DNI", "power_ALLSKY_SFC_SW_DIFF",
        "power_T2M", "power_RH2M", "power_WS2M", "power_AOD_55",
    ]
    power_dedup = power.drop_duplicates(subset=["station", "_merge_hour"])

    merged = train.merge(
        power_dedup[["station", "_merge_hour"] + power_cols],
        on=["station", "_merge_hour"], how="inner"
    )
    merged = merged.drop(columns=["_merge_hour"])
    return merged


def prepare_input(df_st, lat, lon):
    """Format a station DataFrame for WeatherCorrectionLayer.predict()."""
    df = df_st.copy()
    df["ghi_satellite"] = df["power_ALLSKY_SFC_SW_DWN"]
    df["dni_satellite"] = df["power_ALLSKY_SFC_SW_DNI"]
    df["dhi_satellite"] = df["power_ALLSKY_SFC_SW_DIFF"]
    df["temp_air"] = df["power_T2M"]
    df["relative_humidity"] = df["power_RH2M"]
    df["wind_speed"] = df["power_WS2M"]
    df["aod_550"] = df["power_AOD_55"]
    df["albedo"] = 0.2
    df["latitude"] = lat
    df["longitude"] = lon

    aod = df["aod_550"].fillna(0.2)
    pm25 = np.where(df.get("climate_zone", pd.Series(1, index=df.index)) == 2,
                    aod * 37.5, aod * 60.0)
    df["pm25"] = np.clip(pm25, 5.0, 400.0)

    df["hour"] = df["timestamp"].dt.hour.astype(int)
    df["month"] = df["timestamp"].dt.month.astype(int)

    gis = WeatherCorrectionLayer()
    d, e, z = gis._get_proxies(lat, lon)
    df["dist_to_coast_km"] = d
    df["elevation_m"] = e
    df["climate_zone"] = z

    return df, df["radiation (W/m2)"].values


def naive_baselines(df_st, actual_ghi):
    """
    Compute RMSE for three naive baselines per station.
    Returns dict of {baseline_name: rmse}.
    """
    df = df_st.copy()
    actual = actual_ghi

    baselines = {}

    # 1. Clear-sky model (Iniechen-Perez from NASA POWER)
    ghi_clear = df["power_CLRSKY_SFC_SW_DWN"].values
    mask_day = ghi_clear > 0
    if mask_day.sum() > 0:
        baselines["clear_sky"] = np.sqrt(mean_squared_error(actual[mask_day], ghi_clear[mask_day]))
    else:
        baselines["clear_sky"] = np.nan

    # 2. Scaled clear-sky: mean clearness index per station
    ghi_sat = df["power_ALLSKY_SFC_SW_DWN"].values
    kt = np.where(ghi_clear > 10, ghi_sat / ghi_clear, np.nan)
    mean_kt = np.nanmean(kt)
    scaled_clear = ghi_clear * mean_kt
    baselines["scaled_clear_sky"] = np.sqrt(mean_squared_error(actual, scaled_clear))

    # 3. Persistence (24h lag within station)
    df = df.sort_values("timestamp").reset_index(drop=True)
    ghi_persist = df["power_ALLSKY_SFC_SW_DWN"].shift(24, fill_value=np.nan).values
    valid = ~np.isnan(ghi_persist)
    if valid.sum() > 0:
        baselines["persistence_24h"] = np.sqrt(mean_squared_error(actual[valid], ghi_persist[valid]))
    else:
        baselines["persistence_24h"] = np.nan

    return baselines


def month_to_season(month):
    if month in [12, 1, 2]:
        return "DJF"
    elif month in [3, 4, 5]:
        return "MAM"
    elif month in [6, 7, 8]:
        return "JJA"
    else:
        return "SON"


def main():
    parser = argparse.ArgumentParser(description="Compare all trained models")
    parser.add_argument("--station", type=str, default="all",
                        help="ZINDI station to benchmark (default: all)")
    parser.add_argument("--output", type=str, default="reports/model_comparison.md",
                        help="Output markdown report path")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print("Loading ZINDI validation data...")
    df_all = load_zindi_data()
    if df_all.empty:
        print("No ZINDI data available. Exiting.")
        return

    stations_all = df_all["station"].unique()
    excluded = {'TA00295', 'TA00064', 'TA00219', 'TA00338'}
    stations = [s for s in stations_all if s not in excluded]
    if args.station != "all":
        stations = [s for s in stations if s == args.station]
        if not stations:
            print(f"Station {args.station} not found.")
            return

    print(f"Benchmarking {len(stations)} stations across {len(MODELS)} models + naive baselines...")

    # Load all models
    models = {}
    for model_type in MODELS:
        model_path = f"core/models/{model_type}_ghi.pkl"
        if not os.path.exists(model_path):
            print(f"  Skipping {model_type} (model file not found)")
            continue
        try:
            layer = WeatherCorrectionLayer(model_type=model_type)
            layer.load_models()
            models[model_type] = layer
            print(f"  Loaded {model_type}")
        except Exception as e:
            print(f"  Could not load {model_type}: {e}")

    if not models:
        print("No models could be loaded. Train models first.")
        return

    # Per-station evaluation
    all_results = []
    timing_results = []

    for station in sorted(stations):
        df_st = df_all[df_all["station"] == station].copy()
        df_st = df_st.dropna(subset=["radiation (W/m2)"])
        if len(df_st) < 100:
            continue

        lat = df_st["latitude"].iloc[0]
        lon = df_st["longitude"].iloc[0]
        country = df_st["country"].iloc[0]

        df_input, actual_ghi = prepare_input(df_st, lat, lon)

        # Naive baselines
        baselines = naive_baselines(df_input, actual_ghi)

        for model_type, layer in models.items():
            try:
                t0 = time.perf_counter()
                df_out = layer.predict(df_input.copy())
                elapsed = time.perf_counter() - t0
                timing_results.append({"model": model_type, "seconds": elapsed})

                corrected_ghi = df_out["ghi_corrected"].values
                raw_ghi = df_out["ghi_satellite"].values

                rmse_c = np.sqrt(mean_squared_error(actual_ghi, corrected_ghi))
                rmse_r = np.sqrt(mean_squared_error(actual_ghi, raw_ghi))
                mae_c = mean_absolute_error(actual_ghi, corrected_ghi)
                mae_r = mean_absolute_error(actual_ghi, raw_ghi)
                mbe_c = np.mean(corrected_ghi - actual_ghi)
                r2_c = r2_score(actual_ghi, corrected_ghi)

                row = {
                    "station": station, "country": country,
                    "lat": lat, "lon": lon,
                    "model": model_type, "records": len(df_out),
                    "raw_rmse": rmse_r, "corrected_rmse": rmse_c,
                    "raw_mae": mae_r, "corrected_mae": mae_c,
                    "corrected_mbe": mbe_c, "corrected_r2": r2_c,
                    "improvement_pct": (rmse_r - rmse_c) / rmse_r * 100 if rmse_r > 0 else 0,
                }

                # Seasonal breakdown
                df_out["season"] = df_out["month"].apply(month_to_season)
                for season_name in SEASONS:
                    mask = df_out["season"] == season_name
                    if mask.sum() < 10:
                        continue
                    rmse_s = np.sqrt(mean_squared_error(actual_ghi[mask], corrected_ghi[mask]))
                    mae_s = mean_absolute_error(actual_ghi[mask], corrected_ghi[mask])
                    mbe_s = np.mean(corrected_ghi[mask] - actual_ghi[mask])
                    row[f"rmse_{season_name}"] = rmse_s
                    row[f"mae_{season_name}"] = mae_s
                    row[f"mbe_{season_name}"] = mbe_s

                # Naive baselines for this station
                for bl_name, bl_rmse in baselines.items():
                    row[f"baseline_{bl_name}"] = bl_rmse

                all_results.append(row)
            except Exception as e:
                print(f"  Error {station}/{model_type}: {e}")

    df_results = pd.DataFrame(all_results)
    if df_results.empty:
        print("No results generated.")
        return

    df_timing = pd.DataFrame(timing_results)

    # Generate report
    lines = []
    lines.append("# Model Comparison Report — uniSolar Layer 1")
    lines.append(f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Models:** {', '.join(MODELS)}")
    lines.append(f"**Validation Stations:** {df_results['station'].nunique()}")
    lines.append(f"**Total Records:** {df_results['records'].sum():,}")
    lines.append("")

    # ===================================================================
    # 1. Overall Performance (including naive baselines)
    # ===================================================================
    lines.append("## Overall Performance Summary")
    lines.append("")
    lines.append(
        "| Model | Stations | Records | RMSE | MAE | MBE | R² | Impr vs Raw | Impr vs Clear-Sky | Skill vs Persist |"
    )
    lines.append(
        "|---|---|---|---|---|---|---|---|---|"
    )

    summary = df_results.groupby("model").agg(
        stations=("station", "nunique"),
        records=("records", "sum"),
        raw_rmse=("raw_rmse", "mean"),
        corr_rmse=("corrected_rmse", "mean"),
        imp=("improvement_pct", "mean"),
        corr_mae=("corrected_mae", "mean"),
        corr_mbe=("corrected_mbe", "mean"),
        corr_r2=("corrected_r2", "mean"),
        bl_clear_sky=("baseline_clear_sky", "mean"),
        bl_persist=("baseline_persistence_24h", "mean"),
    ).sort_values("corr_rmse")

    for model_type, r in summary.iterrows():
        imp_vs_raw = (r["raw_rmse"] - r["corr_rmse"]) / r["raw_rmse"] * 100 if r["raw_rmse"] > 0 else 0
        imp_vs_clear = ((r["bl_clear_sky"] - r["corr_rmse"]) / r["bl_clear_sky"] * 100
                        if not np.isnan(r["bl_clear_sky"]) and r["bl_clear_sky"] > 0 else np.nan)
        skill_vs_persist = (1 - r["corr_rmse"] ** 2 / r["bl_persist"] ** 2
                           if not np.isnan(r["bl_persist"]) and r["bl_persist"] > 0 else np.nan)
        imp_vs_clear_str = f"{imp_vs_clear:>+6.1f}%" if not np.isnan(imp_vs_clear) else "   N/A"
        skill_str = f"{skill_vs_persist:>+7.3f}" if not np.isnan(skill_vs_persist) else "    N/A"
        lines.append(
            f"| {model_type:<12s} | {r['stations']:>3.0f} | {r['records']:>7,.0f} | "
            f"{r['corr_rmse']:>6.2f} | {r['corr_mae']:>6.2f} | {r['corr_mbe']:>+7.2f} | "
            f"{r['corr_r2']:>6.4f} | {imp_vs_raw:>+6.1f}% | {imp_vs_clear_str} | {skill_str} |"
        )

    # Naive baseline rows
    bl_names = {"clear_sky": "Clear-Sky (Ineichen)", "scaled_clear_sky": "Scaled Clear-Sky",
                "persistence_24h": "Persistence (24h)"}
    for bl_key, bl_label in bl_names.items():
        if f"baseline_{bl_key}" not in df_results.columns:
            continue
        bl_vals = df_results.groupby("model")[f"baseline_{bl_key}"].mean()
        bl_mean = bl_vals.mean() if not bl_vals.empty else np.nan
        if np.isnan(bl_mean):
            continue
        imp_vs_clear = ((summary["bl_clear_sky"].mean() - bl_mean) / summary["bl_clear_sky"].mean() * 100
                        if not np.isnan(summary["bl_clear_sky"].mean()) and summary["bl_clear_sky"].mean() > 0 else np.nan)
        imp_str = f"{imp_vs_clear:>+6.1f}%" if not np.isnan(imp_vs_clear) else "   N/A"
        lines.append(
            f"| {bl_label:<20s} | — | — | {bl_mean:>6.2f} | — | — | — | — | {imp_str} | — |"
        )

    lines.append("")
    best_model = summary["corr_rmse"].idxmin()
    lines.append(f"**Best model:** `{best_model}` (Mean RMSE = {summary.loc[best_model, 'corr_rmse']:.2f} W/m²)")
    lines.append("")
    lines.append("_Skill vs Persist = 1 - MSE_model / MSE_persistence (SS=1 is perfect, SS=0 is no better than persistence)_")
    lines.append("")

    # ===================================================================
    # 2. Significance Test (Wilcoxon signed-rank, per-station RMSE)
    # ===================================================================
    lines.append("## Statistical Significance (Wilcoxon Signed-Rank)")
    lines.append("")
    lines.append("Paired test on per-station RMSE values. H₀: models have equal error distributions.")
    lines.append("")
    lines.append("| Pair | W-stat | p-value | Significant (p<0.05)? |")
    lines.append("|---|---|---|---|")

    model_order = summary.index.tolist()
    for i, m1 in enumerate(model_order):
        for m2 in model_order[i + 1:]:
            r1 = df_results[df_results["model"] == m1].set_index("station")["corrected_rmse"]
            r2 = df_results[df_results["model"] == m2].set_index("station")["corrected_rmse"]
            common = r1.index.intersection(r2.index)
            if len(common) < 5:
                continue
            diff = r1.loc[common].values - r2.loc[common].values
            if np.std(diff) < 1e-10:
                continue
            stat, p = wilcoxon(diff, alternative="two-sided")
            sig = "✓ Yes" if p < 0.05 else "✗ No"
            lines.append(f"| {m1} vs {m2} | {stat:.1f} | {p:.4f} | {sig} |")

    lines.append("")

    # ===================================================================
    # 3. Seasonal Breakdown
    # ===================================================================
    lines.append("## Seasonal Breakdown (RMSE per Model)")
    lines.append("")
    lines.append("Seasons: DJF (Dec-Feb), MAM (Mar-May), JJA (Jun-Aug), SON (Sep-Nov)")
    lines.append("")
    lines.append("| Model | DJF RMSE | MAM RMSE | JJA RMSE | SON RMSE | DJF MAE | MAM MAE | JJA MAE | SON MAE |")
    lines.append("|---|---|---|---|---|---|---|---|---|")

    for model_type in model_order:
        sub = df_results[df_results["model"] == model_type]
        vals = []
        for season_name in SEASONS:
            if f"rmse_{season_name}" in sub.columns:
                vals.append(f"{sub[f'rmse_{season_name}'].mean():>6.2f}")
            else:
                vals.append("   N/A")
        for season_name in SEASONS:
            if f"mae_{season_name}" in sub.columns:
                vals.append(f"{sub[f'mae_{season_name}'].mean():>6.2f}")
            else:
                vals.append("   N/A")
        lines.append(f"| {model_type:<12s} | {' | '.join(vals)} |")

    lines.append("")

    # ===================================================================
    # 4. Inference Latency
    # ===================================================================
    lines.append("## Inference Latency")
    lines.append("")
    lines.append("| Model | Mean (s) | Std (s) | Min (s) | Max (s) | Records |")
    lines.append("|---|---|---|---|---|---|")

    timing_summary = df_timing.groupby("model").agg(
        mean=("seconds", "mean"),
        std=("seconds", "std"),
        min=("seconds", "min"),
        max=("seconds", "max"),
    )
    for model_type, r in timing_summary.iterrows():
        rec = df_results[df_results["model"] == model_type]["records"].sum()
        lines.append(
            f"| {model_type:<12s} | {r['mean']:.4f} | {r['std']:.4f} | "
            f"{r['min']:.4f} | {r['max']:.4f} | {rec:,} |"
        )

    lines.append("")
    lines.append("_Timed per-station predict() call (includes feature engineering + model inference)._")
    lines.append("")

    # ===================================================================
    # 5. Country-Level Breakdown (best model only)
    # ===================================================================
    if best_model in df_results["model"].values:
        lines.append("## Country-Level Breakdown (Best Model)")
        lines.append("")
        lines.append("| Country | Stations | Raw RMSE | Corr RMSE | Impr % | Corr MBE | Corr R² |")
        lines.append("|---|---|---|---|---|---|---|")

        ctry = df_results[df_results["model"] == best_model].groupby("country").agg(
            n=("station", "nunique"),
            raw=("raw_rmse", "mean"),
            corr=("corrected_rmse", "mean"),
            imp=("improvement_pct", "mean"),
            mbe=("corrected_mbe", "mean"),
            r2=("corrected_r2", "mean"),
        ).sort_values("corr")

        for country, r in ctry.iterrows():
            lines.append(
                f"| {country:<5s} | {r['n']:>3.0f} | {r['raw']:>6.2f} | {r['corr']:>6.2f} | "
                f"{r['imp']:>+6.1f}% | {r['mbe']:>+7.2f} | {r['r2']:>6.4f} |"
            )
        lines.append("")

    # ===================================================================
    # 6. Naive Baselines Detail
    # ===================================================================
    lines.append("## Naive Physics Baselines — Description")
    lines.append("")
    lines.append("| Baseline | Description |")
    lines.append("|---|---|")
    lines.append("| Clear-Sky (Ineichen) | `power_CLRSKY_SFC_SW_DWN` from NASA POWER. Pure physical clear-sky model. Ignores clouds entirely — only valid for clear-sky hours. |")
    lines.append("| Scaled Clear-Sky | Clear-sky GHI × station-mean clearness index. Captures mean cloud climatology per station. |")
    lines.append("| Persistence (24h) | GHI from 24 hours ago. 'If it was sunny yesterday, it will be sunny today.' Captures synoptic-scale persistence. |")
    lines.append("")

    # Write report
    with open(args.output, "w") as f:
        f.write("\n".join(lines) + "\n")

    # Console summary
    print("\n" + "=" * 70)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Model':<20s} {'RMSE':>8s} {'MAE':>8s} {'Skill vs Persist':>18s}")
    print("-" * 56)
    for model_type, r in summary.iterrows():
        skill = 1 - r["corr_rmse"] ** 2 / r["bl_persist"] ** 2 if r["bl_persist"] > 0 else np.nan
        skill_str = f"{skill:.3f}" if not np.isnan(skill) else " N/A"
        print(f"{model_type:<20s} {r['corr_rmse']:>7.2f} W/m² {r['corr_mae']:>7.2f} W/m²  {skill_str:>8s}")
    for bl_key, bl_label in bl_names.items():
        if f"baseline_{bl_key}" not in df_results.columns:
            continue
        bl_vals = df_results.groupby("model")[f"baseline_{bl_key}"].mean()
        bl_mean = bl_vals.mean() if not bl_vals.empty else np.nan
        if np.isnan(bl_mean):
            continue
        print(f"{'  └ ' + bl_label:<20s} {bl_mean:>7.2f} W/m²")
    print("-" * 56)
    print(f"✓ Best: {best_model} (RMSE={summary.loc[best_model, 'corr_rmse']:.2f} W/m²)")
    print(f"✓ Report saved to {args.output}")


if __name__ == "__main__":
    main()

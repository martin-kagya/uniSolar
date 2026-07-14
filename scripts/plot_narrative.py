"""
plot_narrative.py
=================
Clear, compelling plots that tell the story of improvement — designed for
presentation to stakeholders who need to see the impact at a glance.

Usage:
    python scripts/plot_narrative.py
    python scripts/plot_narrative.py --station TA00360
"""

import argparse, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.gridspec import GridSpec
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from scipy import stats

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer

OUTPUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BEST_MODEL = "meta"
C = {"raw": "#E74C3C", "corrected": "#2ECC71", "ground": "#3498DB", "perfect": "#555555"}


def load_zindi_data():
    train_path = "/Users/kagya/Desktop/ZINDI-PROJECT/Train.csv"
    power_path = "/Users/kagya/Desktop/ZINDI-PROJECT/data/nasa_power.parquet"
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


# ─── Plot 1: Density scatter + regression line (before/after) ───
def plot_scatter_regression(actual, raw, corrected, station, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    max_val = np.percentile(np.concatenate([actual, raw, corrected]), 99.5) * 1.05

    for ax, pred, label, color in [
        (ax1, raw, "Raw NASA POWER", C["raw"]),
        (ax2, corrected, f"Corrected ({BEST_MODEL.upper()})", C["corrected"]),
    ]:
        hb = ax.hexbin(actual, pred, gridsize=60, bins='log', cmap='Blues',
                       alpha=0.7, mincnt=1)
        # Regression line
        slope, intercept, r_val, p_val, std_err = stats.linregress(actual, pred)
        x_line = np.linspace(0, max_val, 100)
        ax.plot(x_line, slope * x_line + intercept, '--', color='darkred', lw=2,
                label=f"Fit: y={slope:.2f}x+{intercept:.0f}")
        ax.plot([0, max_val], [0, max_val], '-', color=C["perfect"], lw=1.5, alpha=0.6, label="Perfect")
        ax.set_xlim(0, max_val)
        ax.set_ylim(0, max_val)
        ax.set_xlabel("Ground Truth GHI (W/m²)", fontsize=12)
        ax.set_ylabel("Predicted GHI (W/m²)", fontsize=12)
        rmse = np.sqrt(mean_squared_error(actual, pred))
        mae = mean_absolute_error(actual, pred)
        r2 = r2_score(actual, pred)
        bias = np.mean(pred - actual)
        ax.annotate(f"RMSE = {rmse:.0f} W/m²\nMAE  = {mae:.0f} W/m²\nR²   = {r2:.3f}\nBias = {bias:+.0f} W/m²",
                    xy=(0.05, 0.88), xycoords='axes fraction', fontsize=11,
                    va='top', bbox=dict(boxstyle='round,pad=0.4', facecolor='white', edgecolor=color, alpha=0.9))
        ax.set_title(label, fontsize=13, fontweight='bold', color=color)
        ax.legend(fontsize=9, loc='lower right')
        ax.set_aspect('equal')
        ax.grid(alpha=0.15)

    fig.colorbar(hb, ax=[ax1, ax2], label='log(count)', shrink=0.6)
    fig.suptitle(f"Before vs After — {station}", fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


# ─── Plot 2: Cumulative error distribution (ECDF) ───
def plot_error_ecdf(actual, raw, corrected, save_path):
    raw_err = np.abs(raw - actual)
    corr_err = np.abs(corrected - actual)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for err, label, color, style in [
        (raw_err, "Raw NASA", C["raw"], "-"),
        (corr_err, f"Corrected ({BEST_MODEL.upper()})", C["corrected"], "-"),
    ]:
        sorted_err = np.sort(err)
        ecdf = np.arange(1, len(sorted_err) + 1) / len(sorted_err)
        ax.plot(sorted_err, ecdf, lw=2.5, color=color, label=label, ls=style)
        # Mark key percentiles
        for p in [50, 80, 90, 95]:
            val = np.percentile(err, p)
            ax.axvline(x=val, color=color, ls=':', lw=0.8, alpha=0.4)
            ax.annotate(f"{p}%", (val, p/100), fontsize=8, color=color,
                       ha='left', va='bottom', fontweight='bold',
                       xytext=(3, 3), textcoords='offset points')

    ax.set_xlabel("Absolute Error |Predicted − Actual| (W/m²)", fontsize=12)
    ax.set_ylabel("Cumulative Fraction", fontsize=12)
    ax.set_title("Error Cumulative Distribution — How Often Are We Within X W/m²?",
                fontsize=13, fontweight='bold')
    ax.legend(fontsize=10, loc='lower right')
    ax.grid(alpha=0.3)
    ax.set_xlim(0, np.percentile(np.concatenate([raw_err, corr_err]), 99))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.0f%%'))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.1))

    # Annotate key thresholds
    for p, label, color in [(50, "Median", C["perfect"]), (90, "90th %ile", C["perfect"])]:
        for err_arr, lbl, clr in [(raw_err, "Raw", C["raw"]), (corr_err, "Corr", C["corrected"])]:
            val = np.percentile(err_arr, p)
            ax.annotate(f"{lbl}: {val:.0f}", xy=(val, p/100), fontsize=8,
                       color=clr, ha='left', fontweight='bold',
                       xytext=(4, -8 if lbl == "Corr" else 4), textcoords='offset points')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


# ─── Plot 3: Bias profile by GHI level (shows systematic error correction) ───
def plot_bias_by_ghi_level(actual, raw, corrected, save_path):
    raw_err = raw - actual
    corr_err = corrected - actual

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)

    for ax, err, label, color in [
        (ax1, raw_err, "Raw NASA", C["raw"]),
        (ax2, corr_err, f"Corrected ({BEST_MODEL.upper()})", C["corrected"]),
    ]:
        # Binned bias
        bins = np.arange(0, 1100, 50)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        means, stderr, _ = stats.binned_statistic(actual, err, statistic='mean', bins=bins)
        stds, _, _ = stats.binned_statistic(actual, err, statistic='std', bins=bins)
        counts, _, _ = stats.binned_statistic(actual, err, statistic='count', bins=bins)

        valid = ~np.isnan(means)
        ax.fill_between(bin_centers[valid],
                        means[valid] - stds[valid],
                        means[valid] + stds[valid],
                        alpha=0.15, color=color)
        ax.plot(bin_centers[valid], means[valid], 'o-', color=color, lw=2, markersize=4)
        ax.axhline(y=0, color='k', ls='--', lw=1)
        ax.set_xlabel("Ground Truth GHI (W/m²)", fontsize=12)
        ax.set_title(label, fontsize=13, fontweight='bold', color=color)
        ax.grid(alpha=0.25)
        ax.set_ylim(-150, 150)
        ax.annotate(f"Systematic bias\nat high GHI",
                   xy=(800, means[-1] if not np.isnan(means[-1]) else 50),
                   fontsize=9, color=color, fontweight='bold',
                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
        # Add histogram of actual GHI on top
        ax_hist = ax.twinx()
        ax_hist.hist(actual, bins=bins, alpha=0.08, color='gray', density=True)
        ax_hist.set_ylabel('')

    fig.suptitle("Bias vs Solar Intensity — Does the Error Depend on How Sunny It Is?",
                fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


# ─── Plot 4: Hourly bias profile (shows time-of-day pattern) ───
def plot_hourly_bias(actual, raw, corrected, timestamps, save_path):
    hours = pd.to_datetime(timestamps).hour
    raw_err = raw - actual
    corr_err = corrected - actual

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

    for ax, err, label, color in [
        (ax1, raw_err, "Raw NASA", C["raw"]),
        (ax2, corr_err, f"Corrected ({BEST_MODEL.upper()})", C["corrected"]),
    ]:
        hourly_bias = []
        hourly_std = []
        for h in range(24):
            mask = hours == h
            if mask.sum() > 0:
                hourly_bias.append(np.mean(err[mask]))
                hourly_std.append(np.std(err[mask]) / np.sqrt(mask.sum()))
            else:
                hourly_bias.append(0)
                hourly_std.append(0)
        hrs = np.arange(24)
        ax.fill_between(hrs,
                        np.array(hourly_bias) - np.array(hourly_std) * 1.96,
                        np.array(hourly_bias) + np.array(hourly_std) * 1.96,
                        alpha=0.2, color=color)
        ax.plot(hrs, hourly_bias, 'o-', color=color, lw=2, markersize=5)
        ax.axhline(y=0, color='k', ls='--', lw=1)
        ax.set_xlabel("Hour of Day", fontsize=12)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_title(label, fontsize=13, fontweight='bold', color=color)
        ax.grid(alpha=0.25)
        ax.set_ylim(-60, 60)

    ax1.set_ylabel("Mean Bias (W/m²)", fontsize=12)
    fig.suptitle("Hourly Bias — When Does the Model Help Most?",
                fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


# ─── Plot 5: Improvement by country (stacked bar + scatter) ───
def plot_improvement_breakdown(df_results, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

    # Per-country
    ctry = df_results.groupby("country").agg(
        n=("station", "nunique"),
        raw=("raw_rmse", "mean"),
        corr=("corrected_rmse", "mean"),
        imp=("improvement_pct", "mean"),
    ).sort_values("imp", ascending=False)

    x = np.arange(len(ctry))
    w = 0.3
    ax1.bar(x - w/2, ctry["raw"].values, w, label="Raw NASA", color=C["raw"], alpha=0.85)
    ax1.bar(x + w/2, ctry["corr"].values, w, label=f"Corrected", color=C["corrected"], alpha=0.85)
    for i, (rv, cv, iv) in enumerate(zip(ctry["raw"].values, ctry["corr"].values, ctry["imp"].values)):
        impr_text = f"{iv:.1f}%"
        ax1.annotate(impr_text, (i + w/2, cv + 3), fontsize=10, ha='center',
                    color=C["corrected"], fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{c}\n(n={int(n)})" for c, n in zip(ctry.index, ctry["n"])], fontsize=11)
    ax1.set_ylabel("Mean RMSE (W/m²)", fontsize=12)
    ax1.set_title("Country-Level RMSE", fontsize=13, fontweight='bold')
    ax1.legend(fontsize=10)
    ax1.grid(axis='y', alpha=0.3)

    # Per-station sorted by improvement
    st = df_results.groupby("station").agg(
        raw=("raw_rmse", "first"),
        corr=("corrected_rmse", "first"),
        imp=("improvement_pct", "first"),
        country=("country", "first"),
    ).sort_values("imp", ascending=False).head(15)

    x2 = np.arange(len(st))
    ax2.bar(x2 - w/2, st["raw"].values, w, label="Raw NASA", color=C["raw"], alpha=0.85)
    ax2.bar(x2 + w/2, st["corr"].values, w, label=f"Corrected", color=C["corrected"], alpha=0.85)
    for i, (rv, cv, iv) in enumerate(zip(st["raw"].values, st["corr"].values, st["imp"].values)):
        ax2.annotate(f"{iv:.0f}%", (i + w/2, cv + 2), fontsize=7, ha='center',
                    color=C["corrected"], fontweight='bold')
    ax2.set_xticks(x2)
    ax2.set_xticklabels([f"{s[:7]}" for s in st.index], fontsize=8, rotation=45, ha='right')
    ax2.set_ylabel("RMSE (W/m²)", fontsize=12)
    ax2.set_title("Top-15 Improved Stations", fontsize=13, fontweight='bold')
    ax2.legend(fontsize=10)
    ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


# ─── Plot 6: Dual time series — one station, before/after stacked ───
def plot_dual_time_series(actual, raw, corrected, timestamps, station, save_path, max_points=400):
    df = pd.DataFrame({"ts": pd.to_datetime(timestamps), "a": actual, "r": raw, "c": corrected})
    df = df.sort_values("ts").set_index("ts")

    if len(df) > max_points:
        df = df.resample('6h').mean().dropna()

    raw_err = df["r"] - df["a"]
    corr_err = df["c"] - df["a"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 7), gridspec_kw={'height_ratios': [2, 1]})

    # Time series
    ax1.plot(df.index, df["r"], lw=0.8, alpha=0.6, color=C["raw"], label="Raw NASA")
    ax1.plot(df.index, df["c"], lw=0.8, alpha=0.6, color=C["corrected"], label=f"Corrected")
    ax1.plot(df.index, df["a"], lw=0.8, alpha=0.6, color=C["ground"], label="Ground Truth")

    # Shade the improvement band: when corrected is closer to ground than raw
    closer = np.abs(corr_err) < np.abs(raw_err)
    ax1.fill_between(df.index, df["a"], df["c"],
                     where=closer, alpha=0.08, color=C["corrected"],
                     label=f"{BEST_MODEL.upper()} improves")
    ax1.fill_between(df.index, df["a"], df["r"],
                     where=~closer, alpha=0.06, color=C["raw"],
                     label="Raw better (rare)")

    ax1.set_ylabel("GHI (W/m²)", fontsize=12)
    ax1.set_title(f"Time Series — {station}", fontsize=14, fontweight='bold')
    ax1.legend(fontsize=9, loc='upper right', ncol=3)
    ax1.grid(alpha=0.2)

    # Error bands
    ax2.fill_between(df.index, 0, raw_err, alpha=0.4, color=C["raw"], step='mid', label="Raw error")
    ax2.fill_between(df.index, 0, corr_err, alpha=0.4, color=C["corrected"], step='mid', label="Corrected error")
    ax2.axhline(y=0, color='k', lw=0.5)
    ax2.set_ylabel("Error (W/m²)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=12)
    ax2.legend(fontsize=9, loc='upper right')
    ax2.grid(alpha=0.2)

    # Annotate total bias
    raw_bias_total = raw_err.sum() / 1000
    corr_bias_total = corr_err.sum() / 1000
    ax2.annotate(f"Raw bias: {raw_bias_total:+.0f} kW·h/m²\nCorr bias: {corr_bias_total:+.0f} kW·h/m²",
                xy=(0.02, 0.95), xycoords='axes fraction', fontsize=10,
                va='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate narrative performance plots")
    parser.add_argument("--station", type=str, default=None, help="Single station only")
    args = parser.parse_args()

    print("Loading ZINDI data...")
    df_all = load_zindi_data()
    excluded = {'TA00295', 'TA00064', 'TA00219', 'TA00338'}
    stations_all = df_all["station"].unique()
    stations = [s for s in stations_all if s not in excluded]
    if args.station:
        stations = [s for s in stations if s == args.station]
        if not stations:
            print(f"Station {args.station} not found or excluded.")
            return
        n_ts = 1
    else:
        n_ts = 3  # first 3 for time series

    print(f"Loading model '{BEST_MODEL}'...")
    layer = WeatherCorrectionLayer(model_type=BEST_MODEL)
    layer.load_models()

    all_results = []
    all_actual, all_raw, all_corrected = [], [], []
    all_timestamps = []
    all_stations_names = []

    for station in sorted(stations):
        df_st = df_all[df_all["station"] == station].copy()
        df_st = df_st.dropna(subset=["radiation (W/m2)"])
        if len(df_st) < 100:
            continue
        lat = df_st["latitude"].iloc[0]
        lon = df_st["longitude"].iloc[0]
        country = df_st["country"].iloc[0]
        df_input, actual_ghi = prepare_input(df_st, lat, lon)
        df_out = layer.predict(df_input.copy())
        corrected_ghi = df_out["ghi_corrected"].values
        raw_ghi = df_out["ghi_satellite"].values

        all_actual.extend(actual_ghi)
        all_raw.extend(raw_ghi)
        all_corrected.extend(corrected_ghi)
        all_timestamps.extend(df_st["timestamp"].values)
        all_stations_names.extend([station] * len(actual_ghi))

        rmse_c = np.sqrt(mean_squared_error(actual_ghi, corrected_ghi))
        rmse_r = np.sqrt(mean_squared_error(actual_ghi, raw_ghi))
        all_results.append({
            "station": station, "country": country,
            "raw_rmse": rmse_r, "corrected_rmse": rmse_c,
            "improvement_pct": (rmse_r - rmse_c) / rmse_r * 100,
        })

        # Per-station scatter + regression
        sc_path = os.path.join(OUTPUT_DIR, f"narrative_scatter_{station}.png")
        plot_scatter_regression(actual_ghi, raw_ghi, corrected_ghi, station, sc_path)

        # Time series for a few
        if len(stations) > 1 and station in sorted(stations)[:n_ts]:
            ts_path = os.path.join(OUTPUT_DIR, f"narrative_timeseries_{station}.png")
            plot_dual_time_series(actual_ghi, raw_ghi, corrected_ghi,
                                df_st["timestamp"], station, ts_path)

    all_actual = np.array(all_actual)
    all_raw = np.array(all_raw)
    all_corrected = np.array(all_corrected)
    all_timestamps = np.array(all_timestamps)
    all_stations_arr = np.array(all_stations_names)
    df_results = pd.DataFrame(all_results)
    print(f"  Total: {len(all_actual):,} records, {df_results['station'].nunique()} stations")

    # Global plots
    print("\nGenerating summary plots...")

    # Singleton time series (first station)
    ts_station = sorted(stations)[0]
    ts_df = df_all[df_all["station"] == ts_station].copy().dropna(subset=["radiation (W/m2)"])
    if not ts_df.empty:
        lat, lon = ts_df["latitude"].iloc[0], ts_df["longitude"].iloc[0]
        inp, act = prepare_input(ts_df, lat, lon)
        out = layer.predict(inp.copy())
        ts_path = os.path.join(OUTPUT_DIR, "narrative_timeseries_summary.png")
        plot_dual_time_series(act, out["ghi_satellite"].values, out["ghi_corrected"].values,
                            ts_df["timestamp"], ts_station, ts_path)

    plot_scatter_regression(all_actual, all_raw, all_corrected,
                          "All Stations Combined",
                          os.path.join(OUTPUT_DIR, "narrative_scatter_global.png"))
    plot_error_ecdf(all_actual, all_raw, all_corrected,
                   os.path.join(OUTPUT_DIR, "narrative_error_ecdf.png"))
    plot_bias_by_ghi_level(all_actual, all_raw, all_corrected,
                          os.path.join(OUTPUT_DIR, "narrative_bias_by_ghi.png"))
    plot_hourly_bias(all_actual, all_raw, all_corrected, all_timestamps,
                    os.path.join(OUTPUT_DIR, "narrative_hourly_bias.png"))
    plot_improvement_breakdown(df_results,
                              os.path.join(OUTPUT_DIR, "narrative_improvement_breakdown.png"))

    # Final summary stats
    raw_rmse = np.sqrt(mean_squared_error(all_actual, all_raw))
    corr_rmse = np.sqrt(mean_squared_error(all_actual, all_corrected))
    raw_r2 = r2_score(all_actual, all_raw)
    corr_r2 = r2_score(all_actual, all_corrected)
    impr = (raw_rmse - corr_rmse) / raw_rmse * 100

    print(f"\n{'='*60}")
    print(f"GLOBAL SUMMARY — All {df_results['station'].nunique()} stations")
    print(f"{'='*60}")
    print(f"  {'':>25s} {'Raw NASA':>12s} {'Corrected':>12s} {'Change':>10s}")
    print(f"  {'-'*60}")
    print(f"  {'RMSE (W/m²)':>25s} {raw_rmse:>10.2f}   {corr_rmse:>10.2f}   {impr:>+8.1f}%")
    print(f"  {'MAE (W/m²)':>25s} {mean_absolute_error(all_actual, all_raw):>10.2f}   {mean_absolute_error(all_actual, all_corrected):>10.2f}   {((mean_absolute_error(all_actual, all_raw) - mean_absolute_error(all_actual, all_corrected)) / mean_absolute_error(all_actual, all_raw) * 100):>+8.1f}%")
    print(f"  {'Bias (W/m²)':>25s} {np.mean(all_raw - all_actual):>+10.2f}   {np.mean(all_corrected - all_actual):>+10.2f}")
    print(f"  {'R²':>25s} {raw_r2:>10.4f}   {corr_r2:>10.4f}")
    print(f"  {'R (Pearson)':>25s} {np.corrcoef(all_actual, all_raw)[0,1]:>10.4f}   {np.corrcoef(all_actual, all_corrected)[0,1]:>10.4f}")
    print(f"  {'Median |Error| (W/m²)':>25s} {np.median(np.abs(all_raw - all_actual)):>10.1f}   {np.median(np.abs(all_corrected - all_actual)):>10.1f}")
    print(f"  {'90th %ile |Error| (W/m²)':>25s} {np.percentile(np.abs(all_raw - all_actual), 90):>10.1f}   {np.percentile(np.abs(all_corrected - all_actual), 90):>10.1f}")
    print(f"  {'Cumulative bias (kW·h/m²)':>25s} {(all_raw - all_actual).sum() / 1000:>+10.1f}   {(all_corrected - all_actual).sum() / 1000:>+10.1f}")
    print(f"{'='*60}")
    print(f"\nAll narrative plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

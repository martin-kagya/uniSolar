"""
plot_rolling_analysis.py
=======================
Plots smoothed rolling mean of raw/corrected/actual GHI plus cumulative
bias error for a selected station and time window.

Usage:
    python scripts/plot_rolling_analysis.py --station TA00360
    python scripts/plot_rolling_analysis.py --station TA00360 --window 7d --start 2019-01
"""

import argparse, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer

OUTPUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BEST_MODEL = "meta"
COLORS = {"raw": "#E74C3C", "corrected": "#2ECC71", "ground": "#3498DB", "perfect": "#555555"}


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


def main():
    parser = argparse.ArgumentParser(description="Rolling mean + cumulative bias plot")
    parser.add_argument("--station", type=str, default="TA00360", help="ZINDI station")
    parser.add_argument("--window", type=str, default="7D", help="Rolling window (e.g. 7D, 14D, 30D)")
    parser.add_argument("--start", type=str, default=None, help="Start date filter (e.g. 2019-01)")
    parser.add_argument("--end", type=str, default=None, help="End date filter")
    parser.add_argument("--days", type=int, default=180, help="Number of days to show from start")
    args = parser.parse_args()

    print(f"Loading data for station {args.station}...")
    df_all = load_zindi_data()
    excluded = {'TA00295', 'TA00064', 'TA00219', 'TA00338'}
    if args.station in excluded:
        print(f"Station {args.station} is excluded.")
        return
    df_st = df_all[df_all["station"] == args.station].copy()
    if df_st.empty:
        print(f"Station {args.station} not found.")
        return
    df_st = df_st.dropna(subset=["radiation (W/m2)"])
    if len(df_st) < 100:
        print(f"Station {args.station} has too few records ({len(df_st)}).")
        return

    lat = df_st["latitude"].iloc[0]
    lon = df_st["longitude"].iloc[0]
    print(f"  Location: {lat:.2f}, {lon:.2f}, {df_st['country'].iloc[0]}, {len(df_st)} records")

    # Date filter
    if args.start:
        df_st = df_st[df_st["timestamp"] >= args.start].copy()
    if args.end:
        df_st = df_st[df_st["timestamp"] <= args.end].copy()
    elif args.start and args.days:
        end_date = pd.Timestamp(args.start) + pd.Timedelta(days=args.days)
        df_st = df_st[df_st["timestamp"] <= end_date].copy()
    print(f"  After date filter: {len(df_st)} records")
    if len(df_st) < 50:
        print(f"  Too few records after date filter.")
        return
    print(f"  Date range: {df_st['timestamp'].min()} to {df_st['timestamp'].max()}")

    print(f"Loading model '{BEST_MODEL}'...")
    layer = WeatherCorrectionLayer(model_type=BEST_MODEL)
    layer.load_models()

    df_input, actual_ghi = prepare_input(df_st, lat, lon)
    df_out = layer.predict(df_input.copy())
    corrected_ghi = df_out["ghi_corrected"].values
    raw_ghi = df_out["ghi_satellite"].values
    timestamps = df_st["timestamp"].values

    # Build DataFrame for convenience (DatetimeIndex for offset-based rolling)
    plot_df = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        "actual": actual_ghi,
        "raw": raw_ghi,
        "corrected": corrected_ghi,
    }).sort_values("timestamp").set_index("timestamp")

    # Compute integer periods from offset string (number of rows in window)
    freq_ns = plot_df.index.to_series().diff().median()
    try:
        window_periods = max(1, int(pd.Timedelta(args.window) / freq_ns))
    except Exception:
        window_periods = 24 * 7  # fallback

    # Rolling mean
    roll_raw = plot_df["raw"].rolling(window_periods, min_periods=1, center=True).mean()
    roll_corr = plot_df["corrected"].rolling(window_periods, min_periods=1, center=True).mean()
    roll_actual = plot_df["actual"].rolling(window_periods, min_periods=1, center=True).mean()

    # Cumulative bias
    raw_bias = plot_df["raw"] - plot_df["actual"]
    corr_bias = plot_df["corrected"] - plot_df["actual"]
    cum_raw_bias = raw_bias.cumsum() / 1000  # in kW·h/m²
    cum_corr_bias = corr_bias.cumsum() / 1000

    # Rolling RMSE
    roll_raw_rmse = raw_bias.rolling(window_periods, min_periods=1).apply(
        lambda x: np.sqrt(np.mean(x**2)), raw=False)
    roll_corr_rmse = corr_bias.rolling(window_periods, min_periods=1).apply(
        lambda x: np.sqrt(np.mean(x**2)), raw=False)

    ts = plot_df.index
    title_extra = f" (rolling {args.window}, {window_periods} periods)"

    fig = plt.figure(figsize=(18, 12))
    gs = GridSpec(4, 1, figure=fig, height_ratios=[2.5, 1, 1, 1], hspace=0.3)

    # --- Panel 1: Smoothed time series ---
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(ts, roll_actual, label="Ground Truth", color=COLORS["ground"], lw=2, alpha=0.9)
    ax1.plot(ts, roll_raw, label="Raw NASA POWER", color=COLORS["raw"], lw=1.5, alpha=0.8)
    ax1.plot(ts, roll_corr, label=f"Corrected ({BEST_MODEL.upper()})", color=COLORS["corrected"], lw=1.5, alpha=0.8)
    ax1.fill_between(ts, roll_raw, roll_actual, alpha=0.08, color=COLORS["raw"])
    ax1.fill_between(ts, roll_corr, roll_actual, alpha=0.08, color=COLORS["corrected"])
    ax1.set_ylabel("GHI (W/m²)", fontsize=12)
    ax1.set_title(f"Smoothed GHI Time Series — {args.station}{title_extra}", fontsize=14, fontweight='bold')
    ax1.legend(fontsize=10, loc='upper right', ncol=3)
    ax1.grid(alpha=0.25)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    # --- Panel 2: Rolling RMSE ---
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(ts, roll_raw_rmse, label="Raw rolling RMSE", color=COLORS["raw"], lw=1.5, alpha=0.8)
    ax2.plot(ts, roll_corr_rmse, label="Corrected rolling RMSE", color=COLORS["corrected"], lw=1.5, alpha=0.8)
    ax2.set_ylabel("Rolling RMSE\n(W/m²)", fontsize=11)
    ax2.set_title(f"Rolling RMSE{title_extra}", fontsize=12, fontweight='bold')
    ax2.legend(fontsize=9, loc='upper right')
    ax2.grid(alpha=0.25)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    # --- Panel 3: Instantaneous bias ---
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.bar(ts, raw_bias, width=pd.Timedelta(args.window) / len(ts) / 10,
            alpha=0.3, color=COLORS["raw"], label="Raw error")
    ax3.bar(ts, corr_bias, width=pd.Timedelta(args.window) / len(ts) / 10,
            alpha=0.3, color=COLORS["corrected"], label="Corrected error")
    ax3.plot(ts, raw_bias.rolling(window_periods, min_periods=1, center=True).mean(),
             color=COLORS["raw"], lw=1.5, alpha=0.8, label=f"Raw {args.window} avg")
    ax3.plot(ts, corr_bias.rolling(window_periods, min_periods=1, center=True).mean(),
             color=COLORS["corrected"], lw=1.5, alpha=0.8, label=f"Corr {args.window} avg")
    ax3.axhline(y=0, color='k', lw=0.5)
    ax3.set_ylabel("Bias (W/m²)", fontsize=11)
    ax3.set_title(f"Instantaneous Bias{title_extra}", fontsize=12, fontweight='bold')
    ax3.legend(fontsize=9)
    ax3.grid(alpha=0.25)

    # --- Panel 4: Cumulative bias ---
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.fill_between(ts, 0, cum_raw_bias, alpha=0.3, color=COLORS["raw"], step='mid')
    ax4.fill_between(ts, 0, cum_corr_bias, alpha=0.3, color=COLORS["corrected"], step='mid')
    ax4.plot(ts, cum_raw_bias, label=f"Raw (final: {cum_raw_bias.iloc[-1]:+.1f} kW·h/m²)",
             color=COLORS["raw"], lw=2)
    ax4.plot(ts, cum_corr_bias, label=f"Corrected (final: {cum_corr_bias.iloc[-1]:+.1f} kW·h/m²)",
             color=COLORS["corrected"], lw=2)
    ax4.axhline(y=0, color='k', lw=0.5)
    ax4.set_ylabel("Cumulative Bias\n(kW·h/m²)", fontsize=11)
    ax4.set_xlabel("Date", fontsize=12)
    ax4.set_title(f"Cumulative Bias (Predicted − Actual){title_extra}", fontsize=12, fontweight='bold')
    ax4.legend(fontsize=9)
    ax4.grid(alpha=0.25)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax4.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    plt.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, f"rolling_analysis_{args.station}.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\nSaved {save_path}")

    # Print numerical summary
    print(f"\n=== Numerical Summary — {args.station} ===")
    print(f"  Period: {ts.min()} to {ts.max()} ({len(ts)} records)")
    for label, arr in [("Raw NASA", raw_ghi), ("Corrected", corrected_ghi), ("Ground Truth", actual_ghi)]:
        print(f"  {label:>14s}: mean={np.mean(arr):6.1f}, std={np.std(arr):6.1f}")
    print(f"  Raw RMSE:       {np.sqrt(np.mean(raw_bias**2)):.2f} W/m²")
    print(f"  Corrected RMSE: {np.sqrt(np.mean(corr_bias**2)):.2f} W/m²")
    print(f"  Raw MAE:        {np.mean(np.abs(raw_bias)):.2f} W/m²")
    print(f"  Corrected MAE:  {np.mean(np.abs(corr_bias)):.2f} W/m²")
    print(f"  Raw cumulative bias:  {cum_raw_bias.iloc[-1]:+.1f} kW·h/m²")
    print(f"  Corrected cumulative bias: {cum_corr_bias.iloc[-1]:+.1f} kW·h/m²")
    print(f"  Raw R²:  {1 - np.sum(raw_bias**2) / np.sum((actual_ghi - np.mean(actual_ghi))**2):.4f}")
    print(f"  Corr R²: {1 - np.sum(corr_bias**2) / np.sum((actual_ghi - np.mean(actual_ghi))**2):.4f}")


if __name__ == "__main__":
    main()

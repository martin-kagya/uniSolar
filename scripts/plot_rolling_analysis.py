"""
plot_rolling_analysis.py
=======================
Plots smoothed rolling mean of raw/corrected/actual GHI plus cumulative
bias error for a selected station and time window.

Uses clean validated data and trained models directly (no ZINDI CSV, no
WeatherCorrectionLayer).

Usage:
    python scripts/plot_rolling_analysis.py --station TA00360
    python scripts/plot_rolling_analysis.py --station TA00360 --window 7d --start 2019-01
    python scripts/plot_rolling_analysis.py --station TA00360 --model rf
"""

import argparse, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
import joblib, torch
import torch.nn as nn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer

OUTPUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CLEAN_PATH = os.path.join(ROOT, "data", "processed", "training_clean.parquet")

COLORS = {"raw": "#E74C3C", "corrected": "#2ECC71", "ground": "#3498DB", "perfect": "#555555"}

FEATURES = [
    "ghi_satellite", "dni_satellite", "dhi_satellite",
    "ghi_satellite_lag1", "dni_satellite_lag1", "dhi_satellite_lag1",
    "ghi_satellite_lag2",
    "temp_air", "relative_humidity", "wind_speed",
    "hour", "month",
    "hour_sin", "hour_cos", "month_sin", "month_cos",
    "pm25", "albedo", "cloud_amt", "aod_550",
    "dist_to_coast_km", "elevation_m",
    "clearness_index", "clear_sky_ghi",
    "clearness_index_lag1", "clearness_index_std_3h", "clearness_index_delta",
    "solar_zenith", "solar_elevation", "airmass",
    "station_bias",
    "latitude_f", "longitude_f",
    "cz_0.0", "cz_1.0", "cz_2.0",
]

LSTM_FEATURES = [
    'ghi_satellite', 'dni_satellite', 'dhi_satellite',
    'ghi_satellite_lag1', 'ghi_satellite_lag2',
    'temp_air', 'relative_humidity', 'wind_speed',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'pm25', 'aod_550', 'clearness_index',
    'clearness_index_lag1', 'clearness_index_std_3h', 'clearness_index_delta',
    'solar_zenith', 'solar_elevation', 'clear_sky_ghi',
]


def load_clean_data():
    """Load clean parquet and apply all feature engineering."""
    if not os.path.exists(CLEAN_PATH):
        print(f"  [ERROR] Clean data not found at {CLEAN_PATH}.")
        return pd.DataFrame()
    df = pd.read_parquet(CLEAN_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[(df["ghi_satellite"] > 0) | (df["ghi_ground"] > 0)].copy()
    df["ghi_ground"] = pd.to_numeric(df["ghi_ground"], errors="coerce")
    df = df[df["ghi_ground"].notna() & (df["ghi_ground"] >= 0)]

    df["hour"] = df["timestamp"].dt.hour.astype(int)
    df["month"] = df["timestamp"].dt.month.astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    if "dni_ground" not in df.columns or df["dni_ground"].isnull().all():
        r = df["ghi_ground"] / np.maximum(df["ghi_satellite"], 1.0)
        df["dni_ground"] = (df["dni_satellite"] * r).clip(lower=0)
    else:
        df["dni_ground"] = df["dni_ground"].fillna(0)

    cams_path = os.path.join(ROOT, "data", "processed", "cams_pm25.parquet")
    if os.path.exists(cams_path):
        cams = pd.read_parquet(cams_path)
        cams.rename(columns={"name": "station"}, inplace=True)
        cams["timestamp"] = pd.to_datetime(cams["timestamp"])
        df = df.sort_values("timestamp")
        cams = cams.sort_values("timestamp")
        df = pd.merge_asof(
            df, cams[["station", "timestamp", "pm25_cams"]],
            on="timestamp", by="station", direction="nearest",
            tolerance=pd.Timedelta("90min")
        )
        df["pm25"] = df["pm25_cams"].fillna(np.nan)
    if "pm25" not in df.columns or df["pm25"].isnull().all():
        df["pm25"] = ((12 + (df["latitude"] - 5).clip(0, 15) * 5)).clip(8, 250)
    else:
        df["pm25"] = df["pm25"].fillna(((12 + (df["latitude"] - 5).clip(0, 15) * 5)).clip(8, 250))
    df["pm25"] = df["pm25"].clip(0, 500)
    df["albedo"] = 0.2
    df["cloud_amt"] = 0.5

    _l = WeatherCorrectionLayer()
    us = df[["station", "latitude", "longitude"]].drop_duplicates("station")
    def gis(r):
        d, e, z = _l._get_proxies(r["latitude"], r["longitude"])
        return pd.Series({"dist_to_coast_km": d, "elevation_m": e, "climate_zone": z})
    gm = us.apply(gis, axis=1); gm.index = us["station"].values
    df = df.join(gm, on="station")

    import pvlib
    df["solar_zenith"] = np.nan
    df["solar_elevation"] = np.nan
    df["airmass"] = np.nan
    df["clearness_index"] = np.nan
    for (lat, lon), gidx in df.groupby(
        [df["latitude"].round(2), df["longitude"].round(2)], sort=False
    ).indices.items():
        idx = df.index[gidx]
        elev = float(df.loc[idx[0], "elevation_m"]) if "elevation_m" in df.columns else 100.0
        times = pd.DatetimeIndex(df.loc[idx, "timestamp"])
        loc = pvlib.location.Location(latitude=lat, longitude=lon, altitude=elev)
        sp = loc.get_solarposition(times)
        df.loc[idx, "solar_zenith"] = sp["apparent_zenith"].values
        df.loc[idx, "solar_elevation"] = sp["apparent_elevation"].values
        df.loc[idx, "airmass"] = pvlib.atmosphere.get_relative_airmass(
            np.maximum(sp["apparent_zenith"].values, 0.01)
        )
        cs = loc.get_clearsky(times, model="ineichen")
        df.loc[idx, "clear_sky_ghi"] = cs["ghi"].values
        df.loc[idx, "clearness_index"] = np.clip(
            df.loc[idx, "ghi_satellite"].values / np.maximum(cs["ghi"].values, 1.0),
            0.0, 1.2
        )

    df = df.sort_values(["station", "timestamp"]).reset_index(drop=True)
    for src, dst in [("ghi_satellite", "ghi_satellite_lag1"),
                     ("dni_satellite", "dni_satellite_lag1"),
                     ("dhi_satellite", "dhi_satellite_lag1")]:
        df[dst] = df.groupby("station")[src].shift(1).fillna(df[src])
    df["ghi_satellite_lag2"] = df.groupby("station")["ghi_satellite"].shift(2).fillna(df["ghi_satellite"])
    df["clearness_index_lag1"] = df.groupby("station")["clearness_index"].shift(1).fillna(df["clearness_index"])
    df["clearness_index_std_3h"] = df.groupby("station")["clearness_index"].transform(
        lambda x: x.rolling(3, min_periods=1).std()
    ).fillna(0.0)
    df["clearness_index_delta"] = df.groupby("station")["clearness_index"].diff(1).fillna(0.0)
    df["station_bias"] = 0.0
    df["latitude_f"] = df["latitude"].astype(float)
    df["longitude_f"] = df["longitude"].astype(float)
    for cz in [0.0, 1.0, 2.0]:
        df[f"cz_{cz}"] = (df["climate_zone"] == cz).astype(float)

    if "aod_550" not in df.columns:
        df["aod_550"] = 0.15

    df["station_bias"] = 0.0
    print(f"  CLEAN: {len(df):,} records, {df['station'].nunique()} stations")
    return df


def load_models(model_name):
    """Load trained models from disk. Returns (model, metadata)."""
    if model_name == "rf":
        return joblib.load(os.path.join(ROOT, "core", "models", "rf_ghi.pkl")), {}
    elif model_name == "xgboost":
        return joblib.load(os.path.join(ROOT, "core", "models", "xgboost_ghi.pkl")), {}
    elif model_name == "ridge":
        return joblib.load(os.path.join(ROOT, "core", "models", "ridge_ghi.pkl")), {}
    elif model_name == "lstm":
        ckpt = torch.load(os.path.join(ROOT, "core", "models", "lstm_ratio.pt"),
                          map_location="cpu", weights_only=False)

        class LSTMRatioModel(nn.Module):
            def __init__(self, input_dim, hidden_dim=32, n_layers=2, dropout=0.2):
                super().__init__()
                self.lstm = nn.LSTM(input_dim, hidden_dim, n_layers, batch_first=True,
                                    bidirectional=True, dropout=dropout if n_layers > 1 else 0)
                self.fc = nn.Sequential(
                    nn.Linear(hidden_dim * 2, hidden_dim), nn.ReLU(),
                    nn.Dropout(dropout), nn.Linear(hidden_dim, 1))
            def forward(self, x):
                _, (h, _) = self.lstm(x)
                pooled = torch.cat([h[-2], h[-1]], 1)
                return torch.sigmoid(self.fc(pooled)) * 3.0

        model = LSTMRatioModel(input_dim=len(LSTM_FEATURES))
        model.load_state_dict(ckpt["model_state"])
        model.eval()
        meta = {"mean": ckpt["mean"], "std": ckpt["std"]}
        return model, meta
    else:
        raise ValueError(f"Unknown model: {model_name}")


def predict(model, meta, df, model_name):
    """Predict corrected GHI using trained model."""
    raw = df["ghi_satellite"].values.copy()
    if model_name in ("rf", "xgboost", "ridge"):
        X = df[FEATURES].values.astype(np.float32)
        pred_ratio = np.clip(model.predict(X), 0.0, 3.0)
    elif model_name == "lstm":
        seq_len = 4
        X_raw = df[LSTM_FEATURES].values.astype(np.float32)
        n = len(X_raw)
        seqs = []
        for i in range(n):
            start = max(0, i - seq_len + 1)
            pad = seq_len - (i - start + 1)
            seq = np.concatenate([np.tile(X_raw[start], (pad, 1)), X_raw[start:i+1]], axis=0)
            seqs.append(seq)
        X = np.array(seqs)
        m = meta["mean"]
        s = meta["std"]
        X = (X - m) / s
        X_list = np.array(X).tolist()
        preds = []
        bs = 2048
        for i in range(0, len(X_list), bs):
            xb = torch.tensor(X_list[i:i+bs])
            with torch.no_grad():
                preds.append(np.array(model(xb).squeeze().cpu().tolist()))
        pred_ratio = np.clip(np.concatenate(preds), 0.0, 3.0)
    else:
        raise ValueError(f"Unknown model: {model_name}")
    return raw, raw * pred_ratio


def main():
    parser = argparse.ArgumentParser(description="Rolling mean + cumulative bias plot")
    parser.add_argument("--station", type=str, default="TA00360", help="Station ID")
    parser.add_argument("--window", type=str, default="7D", help="Rolling window (e.g. 7D, 14D, 30D)")
    parser.add_argument("--start", type=str, default=None, help="Start date filter (e.g. 2019-01)")
    parser.add_argument("--end", type=str, default=None, help="End date filter")
    parser.add_argument("--days", type=int, default=180, help="Number of days to show from start")
    parser.add_argument("--model", type=str, default="lstm", help="Model: lstm, rf, xgboost, ridge")
    args = parser.parse_args()

    print(f"Loading clean data...")
    df_all = load_clean_data()
    if df_all.empty:
        print("No data available."); return

    df_st = df_all[df_all["station"] == args.station].copy()
    if df_st.empty:
        print(f"Station {args.station} not found."); return
    if len(df_st) < 100:
        print(f"Station {args.station} has too few records ({len(df_st)})."); return

    lat = df_st["latitude"].iloc[0]
    lon = df_st["longitude"].iloc[0]
    country = df_st["country"].iloc[0] if "country" in df_st.columns else "?"
    print(f"  Location: {lat:.2f}, {lon:.2f}, {country}, {len(df_st)} records")

    if args.start:
        df_st = df_st[df_st["timestamp"] >= args.start].copy()
    if args.end:
        df_st = df_st[df_st["timestamp"] <= args.end].copy()
    elif args.start and args.days:
        end_date = pd.Timestamp(args.start) + pd.Timedelta(days=args.days)
        df_st = df_st[df_st["timestamp"] <= end_date].copy()
    print(f"  After date filter: {len(df_st)} records")
    if len(df_st) < 50:
        print(f"  Too few records after date filter."); return
    print(f"  Date range: {df_st['timestamp'].min()} to {df_st['timestamp'].max()}")

    print(f"Loading model '{args.model}'...")
    model, meta = load_models(args.model)

    raw_ghi, corrected_ghi = predict(model, meta, df_st, args.model)
    actual_ghi = df_st["ghi_ground"].values
    timestamps = df_st["timestamp"].values

    plot_df = pd.DataFrame({
        "timestamp": pd.to_datetime(timestamps),
        "actual": actual_ghi,
        "raw": raw_ghi,
        "corrected": corrected_ghi,
    }).sort_values("timestamp").set_index("timestamp")

    freq_ns = plot_df.index.to_series().diff().median()
    try:
        window_periods = max(1, int(pd.Timedelta(args.window) / freq_ns))
    except Exception:
        window_periods = 24 * 7

    roll_raw = plot_df["raw"].rolling(window_periods, min_periods=1, center=True).mean()
    roll_corr = plot_df["corrected"].rolling(window_periods, min_periods=1, center=True).mean()
    roll_actual = plot_df["actual"].rolling(window_periods, min_periods=1, center=True).mean()

    raw_bias = plot_df["raw"] - plot_df["actual"]
    corr_bias = plot_df["corrected"] - plot_df["actual"]
    cum_raw_bias = raw_bias.cumsum() / 1000
    cum_corr_bias = corr_bias.cumsum() / 1000

    roll_raw_rmse = raw_bias.rolling(window_periods, min_periods=1).apply(
        lambda x: np.sqrt(np.mean(x**2)), raw=False)
    roll_corr_rmse = corr_bias.rolling(window_periods, min_periods=1).apply(
        lambda x: np.sqrt(np.mean(x**2)), raw=False)

    ts = plot_df.index
    title_extra = f" (rolling {args.window}, {window_periods} periods)"

    fig = plt.figure(figsize=(18, 12))
    gs = GridSpec(4, 1, figure=fig, height_ratios=[2.5, 1, 1, 1], hspace=0.3)

    ax1 = fig.add_subplot(gs[0])
    ax1.plot(ts, roll_actual, label="Ground Truth", color=COLORS["ground"], lw=2, alpha=0.9)
    ax1.plot(ts, roll_raw, label="Raw NASA POWER", color=COLORS["raw"], lw=1.5, alpha=0.8)
    ax1.plot(ts, roll_corr, label=f"ML Corrected ({args.model.upper()})", color=COLORS["corrected"], lw=1.5, alpha=0.8)
    ax1.fill_between(ts, roll_raw, roll_actual, alpha=0.08, color=COLORS["raw"])
    ax1.fill_between(ts, roll_corr, roll_actual, alpha=0.08, color=COLORS["corrected"])
    ax1.set_ylabel("GHI (W/m²)", fontsize=12)
    ax1.set_title(f"Smoothed GHI Time Series — {args.station}{title_extra}", fontsize=14, fontweight='bold')
    ax1.legend(fontsize=10, loc='upper right', ncol=3); ax1.grid(alpha=0.25)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.plot(ts, roll_raw_rmse, label="Raw rolling RMSE", color=COLORS["raw"], lw=1.5, alpha=0.8)
    ax2.plot(ts, roll_corr_rmse, label="ML rolling RMSE", color=COLORS["corrected"], lw=1.5, alpha=0.8)
    ax2.set_ylabel("Rolling RMSE\n(W/m²)", fontsize=11)
    ax2.set_title(f"Rolling RMSE{title_extra}", fontsize=12, fontweight='bold')
    ax2.legend(fontsize=9, loc='upper right'); ax2.grid(alpha=0.25)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.bar(ts, raw_bias, width=pd.Timedelta(args.window) / len(ts) / 10,
            alpha=0.3, color=COLORS["raw"], label="Raw error")
    ax3.bar(ts, corr_bias, width=pd.Timedelta(args.window) / len(ts) / 10,
            alpha=0.3, color=COLORS["corrected"], label="ML error")
    ax3.plot(ts, raw_bias.rolling(window_periods, min_periods=1, center=True).mean(),
             color=COLORS["raw"], lw=1.5, alpha=0.8, label=f"Raw {args.window} avg")
    ax3.plot(ts, corr_bias.rolling(window_periods, min_periods=1, center=True).mean(),
             color=COLORS["corrected"], lw=1.5, alpha=0.8, label=f"ML {args.window} avg")
    ax3.axhline(y=0, color='k', lw=0.5)
    ax3.set_ylabel("Bias (W/m²)", fontsize=11)
    ax3.set_title(f"Instantaneous Bias{title_extra}", fontsize=12, fontweight='bold')
    ax3.legend(fontsize=9); ax3.grid(alpha=0.25)

    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.fill_between(ts, 0, cum_raw_bias, alpha=0.3, color=COLORS["raw"], step='mid')
    ax4.fill_between(ts, 0, cum_corr_bias, alpha=0.3, color=COLORS["corrected"], step='mid')
    ax4.plot(ts, cum_raw_bias, label=f"Raw (final: {cum_raw_bias.iloc[-1]:+.1f} kW·h/m²)",
             color=COLORS["raw"], lw=2)
    ax4.plot(ts, cum_corr_bias, label=f"ML (final: {cum_corr_bias.iloc[-1]:+.1f} kW·h/m²)",
             color=COLORS["corrected"], lw=2)
    ax4.axhline(y=0, color='k', lw=0.5)
    ax4.set_ylabel("Cumulative Bias\n(kW·h/m²)", fontsize=11)
    ax4.set_xlabel("Date", fontsize=12)
    ax4.set_title(f"Cumulative Bias (Predicted − Actual){title_extra}", fontsize=12, fontweight='bold')
    ax4.legend(fontsize=9); ax4.grid(alpha=0.25)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%b\n%d'))
    ax4.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))

    plt.tight_layout()
    save_path = os.path.join(OUTPUT_DIR, f"rolling_analysis_{args.station}.png")
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"\nSaved {save_path}")

    print(f"\n=== Numerical Summary — {args.station} ({args.model.upper()}) ===")
    print(f"  Period: {ts.min()} to {ts.max()} ({len(ts)} records)")
    for label, arr in [("Raw NASA", raw_ghi), ("ML Corrected", corrected_ghi), ("Ground Truth", actual_ghi)]:
        print(f"  {label:>14s}: mean={np.mean(arr):6.1f}, std={np.std(arr):6.1f}")
    print(f"  Raw RMSE:       {np.sqrt(np.mean(raw_bias**2)):.2f} W/m²")
    print(f"  ML RMSE:        {np.sqrt(np.mean(corr_bias**2)):.2f} W/m²")
    print(f"  Raw MAE:        {np.mean(np.abs(raw_bias)):.2f} W/m²")
    print(f"  ML MAE:         {np.mean(np.abs(corr_bias)):.2f} W/m²")
    print(f"  Raw cumulative bias:  {cum_raw_bias.iloc[-1]:+.1f} kW·h/m²")
    print(f"  ML cumulative bias:   {cum_corr_bias.iloc[-1]:+.1f} kW·h/m²")
    print(f"  Raw R²:  {1 - np.sum(raw_bias**2) / np.sum((actual_ghi - np.mean(actual_ghi))**2):.4f}")
    print(f"  ML R²:   {1 - np.sum(corr_bias**2) / np.sum((actual_ghi - np.mean(actual_ghi))**2):.4f}")


if __name__ == "__main__":
    main()

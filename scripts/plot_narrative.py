"""
plot_narrative.py
=================
Clear, compelling plots that tell the story of improvement — designed for
presentation to stakeholders who need to see the impact at a glance.

Uses clean validated data and trained models directly (no ZINDI CSV, no
WeatherCorrectionLayer).

Usage:
    python scripts/plot_narrative.py
    python scripts/plot_narrative.py --station TA00360
    python scripts/plot_narrative.py --model lstm
"""

import argparse, os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from scipy import stats
import joblib, torch
import torch.nn as nn

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer

OUTPUT_DIR = os.path.join(ROOT, "reports", "figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CLEAN_PATH = os.path.join(ROOT, "data", "processed", "training_clean.parquet")

C = {"raw": "#E74C3C", "corrected": "#2ECC71", "ground": "#3498DB", "perfect": "#555555"}

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

    # Zero station_bias for clean evaluation
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
    """Predict corrected GHI using trained model. Returns (raw_ghi, corrected_ghi)."""
    raw = df["ghi_satellite"].values.copy()
    if model_name in ("rf", "xgboost", "ridge"):
        feat_cols = FEATURES
        X = df[feat_cols].values.astype(np.float32)
        pred_ratio = np.clip(model.predict(X), 0.0, 3.0)
    elif model_name == "lstm":
        seq_len = 4
        X_raw = df[LSTM_FEATURES].values.astype(np.float32)
        # Build sequences: pad start by repeating first row
        n = len(X_raw)
        seqs = []
        for i in range(n):
            start = max(0, i - seq_len + 1)
            pad = seq_len - (i - start + 1)
            seq = np.concatenate([np.tile(X_raw[start], (pad, 1)), X_raw[start:i+1]], axis=0)
            seqs.append(seq)
        X = np.array(seqs)  # (n, seq_len, features)
        # Normalize with saved mean/std
        m = meta["mean"]  # (1, 1, 21)
        s = meta["std"]   # (1, 1, 21)
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

    corrected = raw * pred_ratio
    return raw, corrected


def plot_scatter_regression(actual, raw, corrected, station, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    max_val = np.percentile(np.concatenate([actual, raw, corrected]), 99.5) * 1.05

    for ax, pred, label, color in [
        (ax1, raw, "Raw NASA POWER", C["raw"]),
        (ax2, corrected, f"ML Corrected (LSTM)", C["corrected"]),
    ]:
        hb = ax.hexbin(actual, pred, gridsize=60, bins='log', cmap='Blues',
                       alpha=0.7, mincnt=1)
        slope, intercept, r_val, p_val, std_err = stats.linregress(actual, pred)
        x_line = np.linspace(0, max_val, 100)
        ax.plot(x_line, slope * x_line + intercept, '--', color='darkred', lw=2,
                label=f"Fit: y={slope:.2f}x+{intercept:.0f}")
        ax.plot([0, max_val], [0, max_val], '-', color=C["perfect"], lw=1.5, alpha=0.6, label="Perfect")
        ax.set_xlim(0, max_val); ax.set_ylim(0, max_val)
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
        ax.set_aspect('equal'); ax.grid(alpha=0.15)

    fig.colorbar(hb, ax=[ax1, ax2], label='log(count)', shrink=0.6)
    fig.suptitle(f"Before vs After — {station}", fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_error_ecdf(actual, raw, corrected, save_path):
    raw_err = np.abs(raw - actual)
    corr_err = np.abs(corrected - actual)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    for err, label, color, style in [
        (raw_err, "Raw NASA", C["raw"], "-"),
        (corr_err, f"ML Corrected (LSTM)", C["corrected"], "-"),
    ]:
        sorted_err = np.sort(err)
        ecdf = np.arange(1, len(sorted_err) + 1) / len(sorted_err)
        ax.plot(sorted_err, ecdf, lw=2.5, color=color, label=label, ls=style)
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


def plot_bias_by_ghi_level(actual, raw, corrected, save_path):
    raw_err = raw - actual
    corr_err = corrected - actual

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)

    for ax, err, label, color in [
        (ax1, raw_err, "Raw NASA", C["raw"]),
        (ax2, corr_err, f"ML Corrected (LSTM)", C["corrected"]),
    ]:
        bins = np.arange(0, 1100, 50)
        bin_centers = (bins[:-1] + bins[1:]) / 2
        means, _, _ = stats.binned_statistic(actual, err, statistic='mean', bins=bins)
        stds, _, _ = stats.binned_statistic(actual, err, statistic='std', bins=bins)
        valid = ~np.isnan(means)
        ax.fill_between(bin_centers[valid],
                        means[valid] - stds[valid],
                        means[valid] + stds[valid],
                        alpha=0.15, color=color)
        ax.plot(bin_centers[valid], means[valid], 'o-', color=color, lw=2, markersize=4)
        ax.axhline(y=0, color='k', ls='--', lw=1)
        ax.set_xlabel("Ground Truth GHI (W/m²)", fontsize=12)
        ax.set_title(label, fontsize=13, fontweight='bold', color=color)
        ax.grid(alpha=0.25); ax.set_ylim(-150, 150)
        ax_hist = ax.twinx()
        ax_hist.hist(actual, bins=bins, alpha=0.08, color='gray', density=True)
        ax_hist.set_ylabel('')

    fig.suptitle("Bias vs Solar Intensity — Does the Error Depend on How Sunny It Is?",
                fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_hourly_bias(actual, raw, corrected, timestamps, save_path):
    hours = pd.to_datetime(timestamps).hour
    raw_err = raw - actual
    corr_err = corrected - actual

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), sharey=True)

    for ax, err, label, color in [
        (ax1, raw_err, "Raw NASA", C["raw"]),
        (ax2, corr_err, f"ML Corrected (LSTM)", C["corrected"]),
    ]:
        hourly_bias = []
        hourly_std = []
        for h in range(24):
            mask = hours == h
            if mask.sum() > 0:
                hourly_bias.append(np.mean(err[mask]))
                hourly_std.append(np.std(err[mask]) / np.sqrt(mask.sum()))
            else:
                hourly_bias.append(0); hourly_std.append(0)
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
        ax.grid(alpha=0.25); ax.set_ylim(-60, 60)

    ax1.set_ylabel("Mean Bias (W/m²)", fontsize=12)
    fig.suptitle("Hourly Bias — When Does the Model Help Most?",
                fontsize=13, fontweight='bold')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_improvement_breakdown(df_results, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))
    w = 0.3

    ctry = df_results.groupby("country").agg(
        n=("station", "nunique"),
        raw=("raw_rmse", "mean"),
        corr=("corrected_rmse", "mean"),
        imp=("improvement_pct", "mean"),
    ).sort_values("imp", ascending=False)

    x = np.arange(len(ctry))
    ax1.bar(x - w/2, ctry["raw"].values, w, label="Raw NASA", color=C["raw"], alpha=0.85)
    ax1.bar(x + w/2, ctry["corr"].values, w, label="ML Corrected", color=C["corrected"], alpha=0.85)
    for i, (rv, cv, iv) in enumerate(zip(ctry["raw"].values, ctry["corr"].values, ctry["imp"].values)):
        ax1.annotate(f"{iv:.1f}%", (i + w/2, cv + 3), fontsize=10, ha='center',
                    color=C["corrected"], fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"{c}\n(n={int(n)})" for c, n in zip(ctry.index, ctry["n"])], fontsize=11)
    ax1.set_ylabel("Mean RMSE (W/m²)", fontsize=12)
    ax1.set_title("Country-Level RMSE", fontsize=13, fontweight='bold')
    ax1.legend(fontsize=10); ax1.grid(axis='y', alpha=0.3)

    st = df_results.groupby("station").agg(
        raw=("raw_rmse", "first"), corr=("corrected_rmse", "first"),
        imp=("improvement_pct", "first"), country=("country", "first"),
    ).sort_values("imp", ascending=False).head(15)

    x2 = np.arange(len(st))
    ax2.bar(x2 - w/2, st["raw"].values, w, label="Raw NASA", color=C["raw"], alpha=0.85)
    ax2.bar(x2 + w/2, st["corr"].values, w, label="ML Corrected", color=C["corrected"], alpha=0.85)
    for i, (rv, cv, iv) in enumerate(zip(st["raw"].values, st["corr"].values, st["imp"].values)):
        ax2.annotate(f"{iv:.0f}%", (i + w/2, cv + 2), fontsize=7, ha='center',
                    color=C["corrected"], fontweight='bold')
    ax2.set_xticks(x2)
    ax2.set_xticklabels([f"{s[:7]}" for s in st.index], fontsize=8, rotation=45, ha='right')
    ax2.set_ylabel("RMSE (W/m²)", fontsize=12)
    ax2.set_title("Top-15 Improved Stations", fontsize=13, fontweight='bold')
    ax2.legend(fontsize=10); ax2.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def plot_dual_time_series(actual, raw, corrected, timestamps, station, save_path, max_points=400):
    df = pd.DataFrame({"ts": pd.to_datetime(timestamps), "a": actual, "r": raw, "c": corrected})
    df = df.sort_values("ts").set_index("ts")

    if len(df) > max_points:
        df = df.resample('6h').mean().dropna()

    raw_err = df["r"] - df["a"]
    corr_err = df["c"] - df["a"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 7), gridspec_kw={'height_ratios': [2, 1]})

    ax1.plot(df.index, df["r"], lw=0.8, alpha=0.6, color=C["raw"], label="Raw NASA")
    ax1.plot(df.index, df["c"], lw=0.8, alpha=0.6, color=C["corrected"], label="ML Corrected")
    ax1.plot(df.index, df["a"], lw=0.8, alpha=0.6, color=C["ground"], label="Ground Truth")

    closer = np.abs(corr_err) < np.abs(raw_err)
    ax1.fill_between(df.index, df["a"], df["c"],
                     where=closer, alpha=0.08, color=C["corrected"],
                     label="ML improves")
    ax1.fill_between(df.index, df["a"], df["r"],
                     where=~closer, alpha=0.06, color=C["raw"],
                     label="Raw better (rare)")

    ax1.set_ylabel("GHI (W/m²)", fontsize=12)
    ax1.set_title(f"Time Series — {station}", fontsize=14, fontweight='bold')
    ax1.legend(fontsize=9, loc='upper right', ncol=3); ax1.grid(alpha=0.2)

    ax2.fill_between(df.index, 0, raw_err, alpha=0.4, color=C["raw"], step='mid', label="Raw error")
    ax2.fill_between(df.index, 0, corr_err, alpha=0.4, color=C["corrected"], step='mid', label="ML error")
    ax2.axhline(y=0, color='k', lw=0.5)
    ax2.set_ylabel("Error (W/m²)", fontsize=12)
    ax2.set_xlabel("Date", fontsize=12)
    ax2.legend(fontsize=9, loc='upper right'); ax2.grid(alpha=0.2)

    raw_bias_total = raw_err.sum() / 1000
    corr_bias_total = corr_err.sum() / 1000
    ax2.annotate(f"Raw bias: {raw_bias_total:+.0f} kW·h/m²\nML bias: {corr_bias_total:+.0f} kW·h/m²",
                xy=(0.02, 0.95), xycoords='axes fraction', fontsize=10,
                va='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {save_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate narrative performance plots")
    parser.add_argument("--station", type=str, default=None, help="Single station only")
    parser.add_argument("--model", type=str, default="lstm", help="Model: lstm, rf, xgboost, ridge")
    args = parser.parse_args()

    print(f"Loading clean data...")
    df_all = load_clean_data()
    if df_all.empty:
        print("No data available."); return

    stations = sorted(df_all["station"].unique())
    if args.station:
        stations = [s for s in stations if s == args.station]
        if not stations:
            print(f"Station {args.station} not found."); return

    print(f"Loading model '{args.model}'...")
    model, meta = load_models(args.model)

    all_results = []
    all_actual, all_raw, all_corrected = [], [], []
    all_timestamps = []

    for station in stations:
        df_st = df_all[df_all["station"] == station].copy()
        if len(df_st) < 100: continue
        lat = df_st["latitude"].iloc[0]
        lon = df_st["longitude"].iloc[0]
        country = df_st["country"].iloc[0] if "country" in df_st.columns else "?"

        raw_ghi, corrected_ghi = predict(model, meta, df_st, args.model)
        actual_ghi = df_st["ghi_ground"].values

        all_actual.extend(actual_ghi)
        all_raw.extend(raw_ghi)
        all_corrected.extend(corrected_ghi)
        all_timestamps.extend(df_st["timestamp"].values)

        rmse_c = np.sqrt(mean_squared_error(actual_ghi, corrected_ghi))
        rmse_r = np.sqrt(mean_squared_error(actual_ghi, raw_ghi))
        all_results.append({
            "station": station, "country": country,
            "raw_rmse": rmse_r, "corrected_rmse": rmse_c,
            "improvement_pct": (rmse_r - rmse_c) / rmse_r * 100,
        })

        sc_path = os.path.join(OUTPUT_DIR, f"narrative_scatter_{station}.png")
        plot_scatter_regression(actual_ghi, raw_ghi, corrected_ghi, station, sc_path)

        if len(stations) > 1 and station in sorted(stations)[:3]:
            ts_path = os.path.join(OUTPUT_DIR, f"narrative_timeseries_{station}.png")
            plot_dual_time_series(actual_ghi, raw_ghi, corrected_ghi,
                                df_st["timestamp"], station, ts_path)

    all_actual = np.array(all_actual)
    all_raw = np.array(all_raw)
    all_corrected = np.array(all_corrected)
    all_timestamps = np.array(all_timestamps)
    df_results = pd.DataFrame(all_results)
    print(f"  Total: {len(all_actual):,} records, {df_results['station'].nunique()} stations")

    print("\nGenerating summary plots...")

    ts_station = sorted(stations)[0]
    ts_df = df_all[df_all["station"] == ts_station].copy()
    if not ts_df.empty:
        r, c = predict(model, meta, ts_df, args.model)
        ts_path = os.path.join(OUTPUT_DIR, "narrative_timeseries_summary.png")
        plot_dual_time_series(ts_df["ghi_ground"].values, r, c,
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

    raw_rmse = np.sqrt(mean_squared_error(all_actual, all_raw))
    corr_rmse = np.sqrt(mean_squared_error(all_actual, all_corrected))
    impr = (raw_rmse - corr_rmse) / raw_rmse * 100

    print(f"\n{'='*60}")
    print(f"GLOBAL SUMMARY — {args.model.upper()} — {df_results['station'].nunique()} stations")
    print(f"{'='*60}")
    print(f"  {'Raw RMSE (W/m²)':>25s}: {raw_rmse:.2f}")
    print(f"  {'Corrected RMSE (W/m²)':>25s}: {corr_rmse:.2f}")
    print(f"  {'Improvement':>25s}: {impr:+.1f}%")
    print(f"  {'Raw MAE (W/m²)':>25s}: {mean_absolute_error(all_actual, all_raw):.2f}")
    print(f"  {'Corrected MAE (W/m²)':>25s}: {mean_absolute_error(all_actual, all_corrected):.2f}")
    print(f"  {'Raw R²':>25s}: {r2_score(all_actual, all_raw):.4f}")
    print(f"  {'Corrected R²':>25s}: {r2_score(all_actual, all_corrected):.4f}")
    print(f"{'='*60}")
    print(f"\nAll narrative plots saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

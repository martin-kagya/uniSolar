"""
retrain_unified.py
==================
Retrains all models on NASA POWER sourced data (DB + ZINDI).
All satellite data now comes from NASA POWER — no Solcast contamination.

Usage:
    python scripts/retrain_unified.py
    python scripts/retrain_unified.py --models xgboost,rf  (subset)
"""

import argparse, os, sys, time, json, warnings
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, TimeSeriesSplit, RandomizedSearchCV
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import xgboost as xgb
import joblib
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings('ignore')

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer

EPS = 1.0

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

MODEL_PARAMS = {
    "xgboost": {
        "n_estimators": 600, "learning_rate": 0.03, "max_depth": 10,
        "subsample": 0.7, "colsample_bytree": 0.7, "reg_lambda": 0.1,
        "objective": "reg:squarederror", "n_jobs": -1,
    },
    "rf": {
        "n_estimators": 300, "min_samples_split": 10, "n_jobs": -1,
    },
    "ridge": {
        "alpha": 10.0, "solver": "auto",
    },
}

TUNE_PARAMS = {
    "n_estimators": [200, 400, 600, 800],
    "learning_rate": [0.01, 0.03, 0.05, 0.1],
    "max_depth": [5, 7, 10, 12],
    "subsample": [0.6, 0.7, 0.8, 0.9],
    "colsample_bytree": [0.6, 0.7, 0.8],
    "reg_lambda": [0.0, 0.1, 1.0, 5.0],
}

DB_NASA_PATH = os.path.join(ROOT, "data", "processed", "training_nasa_power.parquet")
CLEAN_PATH = os.path.join(ROOT, "data", "processed", "training_clean.parquet")
ZINDI_DIR = "/Users/kagya/Desktop/ZINDI-PROJECT"

BASE_MODELS = ["xgboost", "rf", "ridge", "lstm", "lstm_attn"]

# LSTM config (best from HPT)
LSTM_HIDDEN = 32
LSTM_LAYERS = 2
LSTM_SEQ_LEN = 4
LSTM_LR = 3e-4
LSTM_DROPOUT = 0.2
LSTM_EPOCHS = 40
LSTM_PATIENCE = 6
LSTM_BATCH_SIZE = 128
LSTM_N_SEEDS = 5

LSTM_FEATURES = [
    'ghi_satellite', 'dni_satellite', 'dhi_satellite',
    'ghi_satellite_lag1', 'ghi_satellite_lag2',
    'temp_air', 'relative_humidity', 'wind_speed',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'pm25', 'aod_550', 'clearness_index',
    'clearness_index_lag1', 'clearness_index_std_3h', 'clearness_index_delta',
    'solar_zenith', 'solar_elevation', 'clear_sky_ghi',
]


class SeqDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.FloatTensor(X)
        self.y = torch.FloatTensor(y).unsqueeze(1)
    def __len__(self): return len(self.X)
    def __getitem__(self, i): return self.X[i], self.y[i]


def make_lstm_model(variant="base"):
    """Create LSTM variant. Variants: 'base' (last hidden), 'attn' (attention over timesteps)."""
    class LSTMModel(nn.Module):
        def __init__(self):
            super().__init__()
            h, l, d = LSTM_HIDDEN, LSTM_LAYERS, LSTM_DROPOUT
            nf = len(LSTM_FEATURES)
            self.lstm = nn.LSTM(nf, h, l, batch_first=True, bidirectional=True,
                                dropout=d if l > 1 else 0)
            if variant == "attn":
                self.attn = nn.MultiheadAttention(h * 2, 4, batch_first=True)
            self.fc = nn.Sequential(
                nn.Linear(h * 2, h),
                nn.ReLU(), nn.Dropout(d), nn.Linear(h, 1),
            )
        def forward(self, x):
            out, (h, _) = self.lstm(x)             # out: (B, T, H*2)
            if variant == "attn":
                a, _ = self.attn(out, out, out)
                pooled = (out + a).mean(dim=1)      # residual + global pool
            else:
                pooled = torch.cat([h[-2], h[-1]], 1)  # last hidden from both directions
            return torch.sigmoid(self.fc(pooled)) * 3.0
    return LSTMModel()


def lstm_sequences(df, features, seq_len):
    """Build sequences, returning (X, y, original_indices)."""
    seqs, tgts, idx = [], [], []
    for g in df['group'].unique():
        gdf = df[df['group'] == g].sort_values('timestamp')
        X = gdf[features].values.astype(np.float32)
        y = np.clip(gdf['ghi_ground'].values / np.maximum(gdf['ghi_satellite'].values, 10.0), 0.0, 3.0).astype(np.float32)
        gidx = gdf.index.values
        if len(X) < seq_len: continue
        for i in range(len(X) - seq_len + 1):
            seqs.append(X[i:i+seq_len])
            tgts.append(y[i+seq_len-1])
            idx.append(gidx[i+seq_len-1])
    return np.array(seqs), np.array(tgts), np.array(idx)


def train_lstm_fold(tr, va, variant="base", seed=42):
    """Train LSTM on fold, return predictions for va.
    
    variant: 'base' (last hidden concat), 'attn' (attention over timesteps).
    seed: random seed for model initialization reproducibility.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    tr = tr.copy(); va = va.copy()
    tr['station_bias'] = 0.0; va['station_bias'] = 0.0

    X_tr, y_tr, _ = lstm_sequences(tr, LSTM_FEATURES, LSTM_SEQ_LEN)
    X_va, y_va, va_idx = lstm_sequences(va, LSTM_FEATURES, LSTM_SEQ_LEN)

    if len(X_tr) < 100 or len(X_va) < 10:
        return pd.Series(np.nan, index=va.index)

    m = X_tr.mean(axis=(0, 1), keepdims=True)
    s = X_tr.std(axis=(0, 1), keepdims=True) + 1e-8
    X_tr = (X_tr - m) / s
    X_va = (X_va - m) / s

    tl = DataLoader(SeqDataset(X_tr, y_tr), LSTM_BATCH_SIZE, shuffle=True)
    vl = DataLoader(SeqDataset(X_va, y_va), LSTM_BATCH_SIZE)

    model = make_lstm_model(variant)
    opt = optim.AdamW(model.parameters(), lr=LSTM_LR, weight_decay=1e-4)
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=3)
    crit = nn.MSELoss()

    best_val = float('inf')
    stale = 0
    for ep in range(LSTM_EPOCHS):
        model.train()
        for Xb, yb in tl:
            opt.zero_grad()
            crit(model(Xb), yb).backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            vloss = sum(crit(model(Xb), yb).item() * len(Xb) for Xb, yb in vl) / len(vl.dataset)
        sched.step(vloss)
        if vloss < best_val:
            best_val = vloss; stale = 0
        else:
            stale += 1
            if stale >= LSTM_PATIENCE: break

    model.eval()
    preds = []
    with torch.no_grad():
        for Xb, _ in vl:
            preds.append(np.array(model(Xb).detach().cpu().tolist()))
    pred_ratio = np.clip(np.concatenate(preds).ravel(), 0.0, 3.0)

    result = pd.Series(np.nan, index=va.index)
    result.loc[va_idx] = pred_ratio
    return result


# Transformer config (pure self-attention, no CNN)
TRANSFORMER_DIM = 64
TRANSFORMER_HEADS = 4
TRANSFORMER_LAYERS = 2
TRANSFORMER_DROPOUT = 0.2
TRANSFORMER_LR = 3e-4
TRANSFORMER_EPOCHS = 40
TRANSFORMER_PATIENCE = 6
TRANSFORMER_BATCH_SIZE = 128


def make_transformer_model():
    """Pure Transformer with learned positional encoding.
    
    Well-suited for short sequences where RNNs excel but attention
    can learn to weight each timestep.
    """
    class TransformerModel(nn.Module):
        def __init__(self):
            super().__init__()
            nf = len(LSTM_FEATURES)
            self.proj = nn.Linear(nf, TRANSFORMER_DIM)
            self.pos = nn.Parameter(torch.randn(1, LSTM_SEQ_LEN, TRANSFORMER_DIM) * 0.1)
            layer = nn.TransformerEncoderLayer(
                TRANSFORMER_DIM, TRANSFORMER_HEADS,
                dim_feedforward=TRANSFORMER_DIM * 4,
                dropout=TRANSFORMER_DROPOUT, batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, TRANSFORMER_LAYERS)
            self.head = nn.Sequential(
                nn.Linear(TRANSFORMER_DIM, 32),
                nn.GELU(), nn.Dropout(TRANSFORMER_DROPOUT),
                nn.Linear(32, 1),
            )
        def forward(self, x):
            x = self.proj(x) + self.pos   # (B, T, D)
            x = self.encoder(x)           # (B, T, D)
            x = x.mean(dim=1)             # (B, D) global avg pool
            return torch.sigmoid(self.head(x).squeeze(-1)) * 3.0
    return TransformerModel()


def train_transformer_fold(tr, va):
    """Train Transformer on fold, return predictions for va."""
    tr = tr.copy(); va = va.copy()
    tr['station_bias'] = 0.0; va['station_bias'] = 0.0

    X_tr, y_tr, _ = lstm_sequences(tr, LSTM_FEATURES, LSTM_SEQ_LEN)
    X_va, y_va, va_idx = lstm_sequences(va, LSTM_FEATURES, LSTM_SEQ_LEN)

    if len(X_tr) < 100 or len(X_va) < 10:
        return pd.Series(np.nan, index=va.index)

    m = X_tr.mean(axis=(0, 1), keepdims=True)
    s = X_tr.std(axis=(0, 1), keepdims=True) + 1e-8
    X_tr = (X_tr - m) / s
    X_va = (X_va - m) / s

    tl = DataLoader(SeqDataset(X_tr, y_tr), TRANSFORMER_BATCH_SIZE, shuffle=True)
    vl = DataLoader(SeqDataset(X_va, y_va), TRANSFORMER_BATCH_SIZE)

    model = make_transformer_model()
    opt = optim.AdamW(model.parameters(), lr=TRANSFORMER_LR, weight_decay=1e-4)
    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=3)
    crit = nn.MSELoss()

    best_val = float('inf')
    stale = 0
    for ep in range(TRANSFORMER_EPOCHS):
        model.train()
        for Xb, yb in tl:
            opt.zero_grad()
            crit(model(Xb), yb).backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        model.eval()
        with torch.no_grad():
            vloss = sum(crit(model(Xb), yb).item() * len(Xb) for Xb, yb in vl) / len(vl.dataset)
        sched.step(vloss)
        if vloss < best_val:
            best_val = vloss; stale = 0
        else:
            stale += 1
            if stale >= TRANSFORMER_PATIENCE: break

    model.eval()
    preds = []
    with torch.no_grad():
        for Xb, _ in vl:
            preds.append(np.array(model(Xb).detach().cpu().tolist()))
    pred_ratio = np.clip(np.concatenate(preds).ravel(), 0.0, 3.0)

    result = pd.Series(np.nan, index=va.index)
    result.loc[va_idx] = pred_ratio
    return result


def add_engineered_features(df):
    """Add one-hot climate_zone, lat/lon, cyclical encoding, cloud variability."""
    if "clear_sky_ghi" not in df.columns and "clearness_index" in df.columns:
        df["clear_sky_ghi"] = np.maximum(
            df["ghi_satellite"] / np.maximum(df["clearness_index"], 0.01), 1.0)

    # AOD at 550nm as explicit feature
    if "power_AOD_55" in df.columns:
        df["aod_550"] = df["power_AOD_55"].astype("float32")
    elif "aod_550" not in df.columns:
        df["aod_550"] = 0.15

    # Cloud variability features (if clearness_index available)
    if "clearness_index" in df.columns and "group" in df.columns:
        df = df.sort_values(["group", "timestamp"]).reset_index(drop=True)
        if "ghi_satellite_lag2" not in df.columns:
            df["ghi_satellite_lag2"] = df.groupby("group")["ghi_satellite"].shift(2).fillna(df["ghi_satellite"])
        if "clearness_index_lag1" not in df.columns:
            df["clearness_index_lag1"] = df.groupby("group")["clearness_index"].shift(1).fillna(df["clearness_index"])
        if "clearness_index_std_3h" not in df.columns:
            df["clearness_index_std_3h"] = df.groupby("group")["clearness_index"].transform(
                lambda x: x.rolling(3, min_periods=1).std()
            ).fillna(0.0)
        if "clearness_index_delta" not in df.columns:
            df["clearness_index_delta"] = df.groupby("group")["clearness_index"].diff(1).fillna(0.0)

    # One-hot climate_zone
    if "climate_zone" in df.columns:
        for i in range(3):
            df[f"cz_{i}.0"] = (df["climate_zone"] == i).astype("float32")
    # Lat/lon features
    if "latitude" in df.columns:
        df["latitude_f"] = df["latitude"].astype("float32")
    if "longitude" in df.columns:
        df["longitude_f"] = df["longitude"].astype("float32")
    # Cyclical encoding (if not already)
    if "hour" in df.columns and "hour_sin" not in df.columns:
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    if "month" in df.columns and "month_sin" not in df.columns:
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    return df


def load_db_nasa():
    if not os.path.exists(DB_NASA_PATH):
        print(f"  [SKIP] DB NASA data not found. Run fetch_nasa_for_db.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(DB_NASA_PATH)
    ratio = df["ghi_ground"] / np.maximum(df["ghi_satellite"], 1.0)
    df["dni_ground"] = df.get("dni_ground", pd.Series(0, index=df.index)).fillna(
        (df["dni_satellite"] * ratio).clip(lower=0)
    )
    df["source_weight"] = 1.0
    df["group"] = df["location_id"].apply(lambda x: f"DB_loc_{x}")
    print(f"  DB NASA: {len(df):,} records, {df['group'].nunique()} locations")
    return add_engineered_features(df)


def load_zindi():
    tp = os.path.join(ZINDI_DIR, "Train.csv")
    np_ = os.path.join(ZINDI_DIR, "data", "nasa_power.parquet")
    if not os.path.exists(tp) or not os.path.exists(np_):
        return pd.DataFrame()

    t = pd.read_csv(tp, parse_dates=["timestamp"])
    n = pd.read_parquet(np_); n["timestamp"] = pd.to_datetime(n["timestamp"])
    df = t.merge(n, on=["station", "timestamp"], how="inner")
    df = df[~df["station"].isin({"TA00295", "TA00064", "TA00219", "TA00338"})]
    df = df[(df["power_ALLSKY_SFC_SW_DWN"] > 0) | (df["radiation (W/m2)"] > 0)]
    df.rename(columns={
        "power_ALLSKY_SFC_SW_DWN": "ghi_satellite",
        "power_ALLSKY_SFC_SW_DNI": "dni_satellite",
        "power_ALLSKY_SFC_SW_DIFF": "dhi_satellite",
        "power_T2M": "temp_air", "power_RH2M": "relative_humidity",
        "power_WS2M": "wind_speed", "radiation (W/m2)": "ghi_ground",
    }, inplace=True)
    df["hour"] = df["timestamp"].dt.hour.astype(int)
    df["month"] = df["timestamp"].dt.month.astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)
    df["ghi_ground"] = pd.to_numeric(df["ghi_ground"], errors="coerce")
    df = df[df["ghi_ground"].notna() & (df["ghi_ground"] >= 0)]
    df = df[df["ghi_ground"] > 50]  # Remove dawn/dusk noise
    r = df["ghi_ground"] / np.maximum(df["ghi_satellite"], 1.0)
    df["dni_ground"] = (df["dni_satellite"] * r).clip(lower=0)
    # CAMS PM2.5 reanalysis (3-hourly, ~80 km grid)
    cams_path = os.path.join(ROOT, "data", "processed", "cams_pm25.parquet")
    if os.path.exists(cams_path):
        cams = pd.read_parquet(cams_path)
        cams.rename(columns={"name": "station"}, inplace=True)
        cams["timestamp"] = pd.to_datetime(cams["timestamp"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")
        cams = cams.sort_values("timestamp")
        df = pd.merge_asof(
            df, cams[["station", "timestamp", "pm25_cams"]],
            on="timestamp", by="station", direction="nearest",
            tolerance=pd.Timedelta("90min")
        )
        df["pm25"] = df["pm25_cams"].fillna(np.nan)
    if "pm25" not in df.columns or df["pm25"].isnull().all():
        aod = df.get("power_AOD_55", pd.Series(0.15, index=df.index)).fillna(0.15)
        lat = df["latitude"]
        df["pm25"] = ((12 + (lat - 5).clip(0, 15) * 5) * (1 + 2.5 * aod)).clip(8, 250)
    df["pm25"] = df["pm25"].clip(0, 500)
    df["albedo"] = 0.2
    df["cloud_amt"] = df.get("power_CLOUD_AMT", pd.Series(0.5, index=df.index)).fillna(0.5)
    _l = WeatherCorrectionLayer()
    us = df[["station", "latitude", "longitude"]].drop_duplicates("station")
    def gis(r):
        d, e, z = _l._get_proxies(r["latitude"], r["longitude"])
        return pd.Series({"dist_to_coast_km": d, "elevation_m": e, "climate_zone": z})
    gm = us.apply(gis, axis=1); gm.index = us["station"].values
    df = df.join(gm, on="station")
    df["source_weight"] = 2.0
    df["group"] = df["station"]

    # Solar geometry + Ineichen clear-sky (pvlib) — per-station
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
        # Ineichen clear-sky GHI/DNI → clearness index target
        cs = loc.get_clearsky(times, model="ineichen")
        df.loc[idx, "clear_sky_ghi"] = cs["ghi"].values
        df.loc[idx, "clear_sky_dni"] = cs["dni"].values
        df.loc[idx, "clearness_index"] = np.clip(
            df.loc[idx, "ghi_satellite"].values / np.maximum(cs["ghi"].values, 1.0),
            0.0, 1.2
        )

    # Lag-1 features (NASA 3-hourly vs hourly ground temporal offset)
    df = df.sort_values(["station", "timestamp"]).reset_index(drop=True)
    for src, dst in [("ghi_satellite", "ghi_satellite_lag1"),
                     ("dni_satellite", "dni_satellite_lag1"),
                     ("dhi_satellite", "dhi_satellite_lag1")]:
        df[dst] = df.groupby("station")[src].shift(1).fillna(df[src])

    # Cloud variability features
    df["ghi_satellite_lag2"] = df.groupby("station")["ghi_satellite"].shift(2).fillna(df["ghi_satellite"])
    df["clearness_index_lag1"] = df.groupby("station")["clearness_index"].shift(1).fillna(df["clearness_index"])
    df["clearness_index_std_3h"] = df.groupby("station")["clearness_index"].transform(
        lambda x: x.rolling(3, min_periods=1).std()
    ).fillna(0.0)
    df["clearness_index_delta"] = df.groupby("station")["clearness_index"].diff(1).fillna(0.0)

    print(f"  ZINDI: {len(df):,} records, {df['group'].nunique()} stations")
    return add_engineered_features(df)


def load_clean():
    """Load clean validated training data and apply all feature engineering."""
    if not os.path.exists(CLEAN_PATH):
        print(f"  [SKIP] Clean data not found at {CLEAN_PATH}. Run build_clean_training_data.py first.")
        return pd.DataFrame()
    df = pd.read_parquet(CLEAN_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Filter to daytime
    df = df[(df["ghi_satellite"] > 0) | (df["ghi_ground"] > 0)].copy()
    df["ghi_ground"] = pd.to_numeric(df["ghi_ground"], errors="coerce")
    df = df[df["ghi_ground"].notna() & (df["ghi_ground"] >= 0)]

    # Hour/month features
    df["hour"] = df["timestamp"].dt.hour.astype(int)
    df["month"] = df["timestamp"].dt.month.astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
    df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    # Ensure dni_ground exists (ZINDI stations lack it)
    if "dni_ground" not in df.columns or df["dni_ground"].isnull().all():
        r = df["ghi_ground"] / np.maximum(df["ghi_satellite"], 1.0)
        df["dni_ground"] = (df["dni_satellite"] * r).clip(lower=0)
    else:
        df["dni_ground"] = df["dni_ground"].fillna(0)

    # PM2.5 — try CAMS, fallback to proxy
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
        lat = df["latitude"]
        df["pm25"] = ((12 + (lat - 5).clip(0, 15) * 5)).clip(8, 250)
    else:
        # Fill remaining NaN from CAMS merge with lat-based proxy
        lat = df["latitude"]
        proxy = ((12 + (lat - 5).clip(0, 15) * 5)).clip(8, 250)
        df["pm25"] = df["pm25"].fillna(proxy)
    df["pm25"] = df["pm25"].clip(0, 500)
    df["albedo"] = 0.2
    df["cloud_amt"] = 0.5

    # GIS proxies
    _l = WeatherCorrectionLayer()
    us = df[["station", "latitude", "longitude"]].drop_duplicates("station")
    def gis(r):
        d, e, z = _l._get_proxies(r["latitude"], r["longitude"])
        return pd.Series({"dist_to_coast_km": d, "elevation_m": e, "climate_zone": z})
    gm = us.apply(gis, axis=1); gm.index = us["station"].values
    df = df.join(gm, on="station")

    df["source_weight"] = 2.0
    df["group"] = df["station"]

    # Solar geometry + Ineichen clear-sky (pvlib) — per-station
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
        df.loc[idx, "clear_sky_dni"] = cs["dni"].values
        df.loc[idx, "clearness_index"] = np.clip(
            df.loc[idx, "ghi_satellite"].values / np.maximum(cs["ghi"].values, 1.0),
            0.0, 1.2
        )

    # Lag-1 features
    df = df.sort_values(["station", "timestamp"]).reset_index(drop=True)
    for src, dst in [("ghi_satellite", "ghi_satellite_lag1"),
                     ("dni_satellite", "dni_satellite_lag1"),
                     ("dhi_satellite", "dhi_satellite_lag1")]:
        df[dst] = df.groupby("station")[src].shift(1).fillna(df[src])

    # Cloud variability features
    df["ghi_satellite_lag2"] = df.groupby("station")["ghi_satellite"].shift(2).fillna(df["ghi_satellite"])
    df["clearness_index_lag1"] = df.groupby("station")["clearness_index"].shift(1).fillna(df["clearness_index"])
    df["clearness_index_std_3h"] = df.groupby("station")["clearness_index"].transform(
        lambda x: x.rolling(3, min_periods=1).std()
    ).fillna(0.0)
    df["clearness_index_delta"] = df.groupby("station")["clearness_index"].diff(1).fillna(0.0)

    print(f"  CLEAN: {len(df):,} records, {df['group'].nunique()} stations")
    return add_engineered_features(df)


def make_model(model_type):
    p = MODEL_PARAMS[model_type].copy()
    if model_type == "xgboost": return xgb.XGBRegressor(**p)
    if model_type == "rf": return RandomForestRegressor(**p)
    if model_type == "ridge": return make_pipeline(StandardScaler(), Ridge(**p))
    raise ValueError(f"Unknown model type: {model_type}")


def fit_model(m, X, y, sample_weight=None):
    """Fit a model, handling Pipeline sample_weight routing."""
    kwargs = {"sample_weight": sample_weight} if sample_weight is not None else {}
    if hasattr(m, 'steps'):  # Is a Pipeline
        step_name = m.steps[-1][0]
        kwargs = {f"{step_name}__sample_weight": sample_weight} if sample_weight is not None else {}
    return m.fit(X, y, **kwargs)


def sample_weights_by_ghi_bin(df, bins=None):
    """Compute sample weights inversely proportional to GHI bin frequency."""
    if bins is None:
        bins = [0, 200, 500, 800, 5000]
    labels = pd.cut(df["ghi_satellite"].values, bins=bins, labels=False)
    weights = np.ones(len(df))
    n_bins = len(bins) - 1
    for b in range(n_bins):
        mask = labels == b
        if mask.sum() > 0:
            weights[mask] = len(df) / (n_bins * mask.sum())
    return weights


def y_ratio(ground, satellite):
    """Ratio target: ratio = ground / satellite, bounded [0.0, 3.0]."""
    return np.clip(ground / np.maximum(satellite, 10.0), 0.0, 3.0)


def grouped_kfold(df, features, model_type, n_folds=5):
    """Grouped k-fold — station_bias is zeroed (unseen in k-fold)."""
    groups = df["group"].values
    gkf = GroupKFold(n_splits=n_folds)
    rmses = []
    for ti, vi in gkf.split(df, y=df["ghi_ground"] - df["ghi_satellite"], groups=groups):
        tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr["station_bias"] = 0.0
        va["station_bias"] = 0.0

        m = make_model(model_type)
        sw = tr.get("source_weight", pd.Series(1.0, index=tr.index)).values
        y_tr = y_ratio(tr["ghi_ground"].values, tr["ghi_satellite"].values)
        fit_model(m, tr[features], y_tr, sample_weight=sw)
        pred_ratio = np.clip(m.predict(va[features]), 0.0, 3.0)
        pred = va["ghi_satellite"].values * pred_ratio
        rmses.append(np.sqrt(mean_squared_error(va["ghi_ground"].values, pred)))
    return np.mean(rmses), np.std(rmses), rmses


def tune_xgboost(X, y, sample_weight=None, n_iter=30):
    """Run RandomizedSearchCV on full dataset to find best hyperparams."""
    base = xgb.XGBRegressor(objective="reg:squarederror", n_jobs=1)
    search = RandomizedSearchCV(base, TUNE_PARAMS, n_iter=n_iter, cv=3,
                                scoring="neg_mean_absolute_error",
                                verbose=0, n_jobs=-1, random_state=42)
    search.fit(X, y, sample_weight=sample_weight)
    print(f"  Best params: {search.best_params_}")
    print(f"  Best CV MAE: {-search.best_score_:.2f}")
    return search.best_estimator_


def stacking_kfold(df, features, n_folds=5):
    """
    Grouped k-fold for stacking ensemble.

    Level 1: Out-of-fold ratio predictions from all BASE_MODELS + LSTM.
    Level 2: Meta-model trained on OOF predictions, evaluated via grouped CV.
    LSTM NaN positions are filled with XGBoost OOF predictions.
    """
    groups = df["group"].values
    gkf = GroupKFold(n_splits=n_folds)
    y_t = y_ratio(df["ghi_ground"].values, df["ghi_satellite"].values)

    include_lstm = "lstm" in BASE_MODELS

    # Step 1 – OOF predictions from each base model
    oof_preds = np.zeros((len(df), len(BASE_MODELS)))
    for ti, vi in gkf.split(df, y=df["ghi_ground"] - df["ghi_satellite"], groups=groups):
        tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr["station_bias"] = 0.0
        va["station_bias"] = 0.0
        sw = tr.get("source_weight", pd.Series(1.0, index=tr.index)).values
        for i, mt in enumerate(BASE_MODELS):
            if mt == "lstm":
                ps = [train_lstm_fold(tr, va, variant="base", seed=s).values
                      for s in range(LSTM_N_SEEDS)]
                oof_preds[vi, i] = np.nanmean(ps, axis=0)
            elif mt == "lstm_attn":
                p = train_lstm_fold(tr, va, variant="attn")
                oof_preds[vi, i] = p.values
            else:
                m = make_model(mt)
                fit_model(m, tr[features], y_t[ti], sample_weight=sw)
                oof_preds[vi, i] = np.clip(m.predict(va[features]), 0.0, 3.0)

    # Fill DL model NaNs with XGBoost OOF predictions (rows with no sequence)
    xgb_idx = BASE_MODELS.index("xgboost")
    for dl_model in ("lstm", "lstm_attn", "transformer"):
        if dl_model in BASE_MODELS:
            dl_idx = BASE_MODELS.index(dl_model)
            nan_mask = np.isnan(oof_preds[:, dl_idx])
            if nan_mask.any():
                oof_preds[nan_mask, dl_idx] = oof_preds[nan_mask, xgb_idx]

    # Step 2 – grouped CV on meta-model
    meta_rmses = []
    for ti, vi in gkf.split(oof_preds, y=df["ghi_ground"] - df["ghi_satellite"], groups=groups):
        meta = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1,
                                max_depth=3, n_jobs=1)
        meta.fit(oof_preds[ti], y_t[ti])
        pred_ratio = np.clip(meta.predict(oof_preds[vi]), 0.0, 3.0)
        pred_ghi = df["ghi_satellite"].values[vi] * pred_ratio
        meta_rmses.append(np.sqrt(mean_squared_error(df["ghi_ground"].values[vi], pred_ghi)))

    return np.mean(meta_rmses), np.std(meta_rmses), meta_rmses


def forward_chaining(df, features, model_type, n_splits=5):
    """
    Forward-chaining temporal validation.

    Trains on expanding time windows, tests on the next temporal segment.
    Unlike GroupKFold, this tests temporal generalization (extrapolation
    to unseen time periods).

    Returns (mean_rmse, std_rmse, [fold_rmses], [fold_test_sizes]).
    """
    df = df.sort_values("timestamp").reset_index(drop=True)
    tscv = TimeSeriesSplit(n_splits=n_splits)
    rmses = []
    fold_sizes = []
    fold_times = []
    for ti, vi in tscv.split(df):
        tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr["station_bias"] = 0.0
        va["station_bias"] = 0.0
        m = make_model(model_type)
        sw = tr.get("source_weight", pd.Series(1.0, index=tr.index)).values
        y_tr = y_ratio(tr["ghi_ground"].values, tr["ghi_satellite"].values)
        fit_model(m, tr[features], y_tr, sample_weight=sw)
        pred_ratio = np.clip(m.predict(va[features]), 0.0, 3.0)
        pred = va["ghi_satellite"].values * pred_ratio
        rmses.append(np.sqrt(mean_squared_error(va["ghi_ground"].values, pred)))
        fold_sizes.append(len(va))
        fold_times.append((va["timestamp"].min(), va["timestamp"].max()))
    w = np.array(fold_sizes, dtype=float)
    w /= w.sum()
    weighted_mean = np.sum(np.array(rmses) * w)
    return weighted_mean, np.std(rmses), rmses, fold_times


def forward_chaining_stacking(df, features, n_splits=5, fc_models=None):
    """
    Forward-chaining temporal validation for the stacking ensemble.

    For each temporal fold:
      1. Train base models on full train set, predict on train (meta features) and test
      2. Train meta-model on train set base predictions
      3. Meta-model predicts on test set

    Args:
        fc_models: list of model types to use as base models (default: xgboost + ridge)

    Returns (mean_rmse, std_rmse, [fold_rmses], [fold_test_ranges]).
    """
    if fc_models is None:
        fc_models = ["xgboost", "ridge"]
    df = df.sort_values("timestamp").reset_index(drop=True)
    tscv = TimeSeriesSplit(n_splits=n_splits)

    rmses = []
    fold_sizes = []
    fold_times = []
    y_t = y_ratio(df["ghi_ground"].values, df["ghi_satellite"].values)

    for ti, vi in tscv.split(df):
        tr_all, va = df.iloc[ti].copy(), df.iloc[vi].copy()
        tr_all["station_bias"] = 0.0
        va["station_bias"] = 0.0

        train_base = np.zeros((len(tr_all), len(fc_models)))
        test_base = np.zeros((len(va), len(fc_models)))
        for i, mt in enumerate(fc_models):
            m = make_model(mt)
            y_tr = y_ratio(tr_all["ghi_ground"].values, tr_all["ghi_satellite"].values)
            sw = tr_all.get("source_weight", pd.Series(1.0, index=tr_all.index)).values
            t0 = time.time()
            fit_model(m, tr_all[features], y_tr, sample_weight=sw)
            train_base[:, i] = np.clip(m.predict(tr_all[features]), 0.0, 3.0)
            test_base[:, i] = np.clip(m.predict(va[features]), 0.0, 3.0)

        meta = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, n_jobs=1)
        meta.fit(train_base, y_t[ti])

        meta_pred_ratio = np.clip(meta.predict(test_base), 0.0, 3.0)
        meta_pred = va["ghi_satellite"].values * meta_pred_ratio
        rmses.append(np.sqrt(mean_squared_error(va["ghi_ground"].values, meta_pred)))
        fold_sizes.append(len(va))
        fold_times.append((va["timestamp"].min(), va["timestamp"].max()))

    w = np.array(fold_sizes, dtype=float)
    w /= w.sum()
    weighted_mean = np.sum(np.array(rmses) * w)
    return weighted_mean, np.std(rmses), rmses, fold_times


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=str, default="xgboost,rf,ridge")
    ap.add_argument("--kfold", type=int, default=5)
    ap.add_argument("--tune", action="store_true", help="Run hyperparameter tuning")
    ap.add_argument("--zindi-only", action="store_true", help="Train on ZINDI data only (no DB)")
    ap.add_argument("--clean", action="store_true", help="Use clean validated training data (23 stations)")
    ap.add_argument("--exclude-country", type=str, default="", help="Exclude stations from this country code (e.g. NG)")
    ap.add_argument("--lstm", action="store_true", help="Include LSTM in k-fold CV and final training")
    ap.add_argument("--stacking", action="store_true", help="Train stacking ensemble (base models + meta)")
    ap.add_argument("--forward-chaining", type=int, default=0,
                    help="Number of forward-chaining temporal splits (0=disabled)")
    ap.add_argument("--lstm-seq-len", type=int, default=4,
                    help="LSTM sequence length in timesteps")
    args = ap.parse_args()
    model_list = [m.strip() for m in args.models.split(",")]
    if args.clean:
        mode = "Clean (23 validated stations)"
    elif args.zindi_only:
        mode = "ZINDI-only"
    else:
        mode = "Combined (DB+ZINDI)"
    global LSTM_SEQ_LEN
    LSTM_SEQ_LEN = args.lstm_seq_len

    # Load
    print("=" * 65, "\nLOADING DATA\n", "=" * 65, sep="")
    dfs = []
    if args.clean:
        c = load_clean()
        if not c.empty: dfs.append(c)
    else:
        if not args.zindi_only:
            d = load_db_nasa()
            if not d.empty: dfs.append(d)
        z = load_zindi()
        if not z.empty: dfs.append(z)
    if not dfs:
        print("No data. Aborting."); return
    df = pd.concat(dfs, ignore_index=True)
    for f in FEATURES + ["ghi_ground", "dni_ground", "group", "source_weight", "clear_sky_ghi"]:
        if f not in df.columns: df[f] = 0.0
    df.dropna(subset=FEATURES + ["ghi_ground", "dni_ground"], inplace=True)

    # Daytime only
    mask = (df["ghi_satellite"] > 0) | (df["ghi_ground"] > 0)
    df = df[mask].copy()

    # Exclude countries
    if args.exclude_country:
        excl = args.exclude_country.upper()
        before = len(df)
        df = df[df["country"].str.upper() != excl].copy()
        print(f"  Excluded country={excl}: {before:,} -> {len(df):,} records, {df['group'].nunique()} groups")

    print(f"\n  {mode}: {len(df):,} records, {df['group'].nunique()} groups")
    raw_rmse = np.sqrt(((df['ghi_ground'] - df['ghi_satellite'])**2).mean())
    print(f"  Raw NASA RMSE: {raw_rmse:.2f}")

    # K-fold
    kfold_results = {}
    if args.kfold > 0:
        print(f"\n{'=' * 65}")
        print(f"GROUPED {args.kfold}-FOLD CROSS-VALIDATION ({mode})")
        print("=" * 65)
        for mt in model_list:
            m, s, folds = grouped_kfold(df, FEATURES, mt, args.kfold)
            kfold_results[mt] = m
            print(f"  {mt.upper():12s}: {m:.2f} ± {s:.2f} W/m²", end="")
            imp = raw_rmse - m
            print(f"  (Δ vs raw: {imp:+.1f})")
            for i, r in enumerate(folds):
                print(f"    Fold {i+1}: {r:.2f}")

    # LSTM k-fold
    lstm_kfold_rmse = None
    if args.lstm and args.kfold > 0:
        print(f"\n{'=' * 65}")
        print(f"GROUPED {args.kfold}-FOLD CROSS-VALIDATION — LSTM ({mode})")
        print("=" * 65)
        groups = df["group"].values
        gkf = GroupKFold(n_splits=args.kfold)
        lstm_rmses = []
        for ti, vi in gkf.split(df, y=df["ghi_ground"] - df["ghi_satellite"], groups=groups):
            tr, va = df.iloc[ti].copy(), df.iloc[vi].copy()
            for variant_label, variant in [("base", "base"), ("attn", "attn")]:
                ps = [train_lstm_fold(tr, va, variant=variant, seed=s).values
                      for s in range(LSTM_N_SEEDS)]
                pred_ratio = np.nanmean(ps, axis=0)
                valid = pred_ratio.notna()
                if valid.sum() == 0:
                    continue
                pred = va.loc[valid.index[valid], "ghi_satellite"].values * pred_ratio[valid].values
                rmse = np.sqrt(mean_squared_error(va.loc[valid.index[valid], "ghi_ground"].values, pred))
                lstm_rmses.append(rmse)
        if lstm_rmses:
            lstm_kfold_rmse = np.mean(lstm_rmses[:len(lstm_rmses)//2])  # base variant folds
            attn_rmse = np.mean(lstm_rmses[len(lstm_rmses)//2:]) if len(lstm_rmses) > args.kfold else None
            print(f"  LSTM_BASE    : {np.mean(lstm_rmses[:args.kfold]):.2f} W/m²  (Δ vs raw: {raw_rmse - np.mean(lstm_rmses[:args.kfold]):+.1f})")
            if attn_rmse is not None:
                print(f"  LSTM_ATTN    : {attn_rmse:.2f} W/m²  (Δ vs raw: {raw_rmse - attn_rmse:+.1f})")
            for i, r in enumerate(lstm_rmses[:args.kfold]):
                print(f"    Base Fold {i+1}: {r:.2f}")
            for i, r in enumerate(lstm_rmses[args.kfold:args.kfold*2]):
                print(f"    Attn Fold {i+1}: {r:.2f}")

    # Stacking ensemble k-fold
    stacking_rmse = None
    if args.stacking and args.kfold > 0:
        print(f"\n{'=' * 65}")
        print(f"STACKING ENSEMBLE ({mode})")
        print("=" * 65)
        m, s, folds = stacking_kfold(df, FEATURES, args.kfold)
        stacking_rmse = m
        print(f"  STACKING    : {m:.2f} ± {s:.2f} W/m²  (Δ vs best single: {min(kfold_results.values())-m:+.1f})")
        for i, r in enumerate(folds):
            print(f"    Fold {i+1}: {r:.2f}")

    # Forward-chaining temporal validation
    if args.forward_chaining > 0:
        print(f"\n{'=' * 65}")
        print(f"FORWARD-CHAINING TEMPORAL VALIDATION ({args.forward_chaining} splits)")
        print("=" * 65)

        if args.stacking:
            m, s, folds, ftimes = forward_chaining_stacking(df, FEATURES, args.forward_chaining)
            print(f"  STACKING    : {m:.2f} ± {s:.2f} W/m²  ({len(folds)} folds)")
            for i, r in enumerate(folds):
                t0, t1 = ftimes[i]
                print(f"    Fold {i+1}: test {t0.date()} → {t1.date()}  rmse={r:.2f}")

        for mt in model_list:
            m, s, folds, ftimes = forward_chaining(df, FEATURES, mt, args.forward_chaining)
            print(f"  {mt.upper():12s}: {m:.2f} ± {s:.2f} W/m²  ({len(folds)} folds)")
            for i, r in enumerate(folds):
                t0, t1 = ftimes[i]
                print(f"    Fold {i+1}: test {t0.date()} → {t1.date()}  rmse={r:.2f}")

    # Train final models
    print(f"\n{'=' * 65}")
    print(f"TRAINING FINAL MODELS ON ALL DATA ({mode})")
    print("=" * 65)

    # Station bias on full data for final model training
    station_resid_full = df.groupby("group").apply(
        lambda g: np.median(g["ghi_ground"].values - g["ghi_satellite"].values),
        include_groups=False
    ).to_dict()
    df = df.copy()
    df["station_bias"] = df["group"].map(station_resid_full)
    df["station_bias"] = df["station_bias"].fillna(0.0)

    X = df[FEATURES]
    y_ghi = y_ratio(df["ghi_ground"].values, df["ghi_satellite"].values)
    y_dni = y_ratio(df["dni_ground"].values, df["dni_satellite"].values)
    sw = df["source_weight"].values

    if args.stacking:
        include_lstm = "lstm" in BASE_MODELS

        def _train_lstm_full(variant, n_seeds=LSTM_N_SEEDS):
            """Train LSTM on full data. Returns (checkpoint_dict, full_preds)."""
            df_seq = df.copy().reset_index(drop=True)
            df_seq['station_bias'] = 0.0
            X_seq, y_seq, _ = lstm_sequences(df_seq, LSTM_FEATURES, LSTM_SEQ_LEN)
            m_s = X_seq.mean(axis=(0, 1), keepdims=True)
            s_s = X_seq.std(axis=(0, 1), keepdims=True) + 1e-8
            X_seq_n = (X_seq - m_s) / s_s
            sl = DataLoader(SeqDataset(X_seq_n, y_seq), LSTM_BATCH_SIZE, shuffle=True)

            all_preds = []
            best_model = None
            best_loss = float('inf')
            for seed in range(n_seeds):
                torch.manual_seed(seed)
                np.random.seed(seed)
                model = make_lstm_model(variant)
                opt = optim.AdamW(model.parameters(), lr=LSTM_LR, weight_decay=1e-4)
                sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=3)
                crit = nn.MSELoss()
                best_val = float('inf'); stale = 0
                for ep in range(LSTM_EPOCHS):
                    model.train()
                    for Xb, yb in sl:
                        opt.zero_grad()
                        crit(model(Xb), yb).backward()
                        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                        opt.step()
                    model.eval()
                    with torch.no_grad():
                        vloss = sum(crit(model(Xb), yb).item() * len(Xb) for Xb, yb in sl) / len(sl.dataset)
                    sched.step(vloss)
                    if vloss < best_val: best_val = vloss; stale = 0
                    else: stale += 1
                    if stale >= LSTM_PATIENCE: break
                if best_val < best_loss:
                    best_loss = best_val
                    best_model = model

                # Collect full-data predictions from this seed (group-by-group)
                full = np.ones(len(df_seq))
                with torch.no_grad():
                    for g in df_seq['group'].unique():
                        gdf = df_seq[df_seq['group'] == g].sort_values('timestamp')
                        Xb, _, _ = lstm_sequences(gdf, LSTM_FEATURES, LSTM_SEQ_LEN)
                        if len(Xb) == 0: continue
                        Xb = (Xb - m_s) / s_s
                        pr = np.array(model(torch.FloatTensor(Xb)).detach().cpu().tolist()).ravel()
                        gidx = gdf.index.values
                        full[gidx[LSTM_SEQ_LEN-1:]] = np.clip(pr, 0.0, 3.0)
                all_preds.append(full)
            avg_preds = np.mean(all_preds, axis=0)
            ckpt = {'model_state': best_model.state_dict(), 'mean': m_s, 'std': s_s}
            return ckpt, avg_preds

        lstm_full_preds = {}
        for mt in BASE_MODELS:
            t0 = time.time()
            if mt == "lstm":
                ckpt, full = _train_lstm_full("base", n_seeds=LSTM_N_SEEDS)
                torch.save(ckpt, "core/models/lstm_ratio.pt")
                lstm_full_preds[mt] = full
                print(f"  LSTM         : ({time.time()-t0:.0f}s)  core/models/lstm_ratio.pt")
            elif mt == "lstm_attn":
                ckpt, full = _train_lstm_full("attn", n_seeds=1)
                torch.save(ckpt, "core/models/lstm_attn_ratio.pt")
                lstm_full_preds[mt] = full
                print(f"  LSTM_ATTN    : ({time.time()-t0:.0f}s)  core/models/lstm_attn_ratio.pt")
            else:
                ghi_model = make_model(mt)
                dni_model = make_model(mt)
                fit_model(ghi_model, X, y_ghi, sample_weight=sw)
                fit_model(dni_model, X, y_dni, sample_weight=sw)
                joblib.dump(ghi_model, f"core/models/{mt}_ghi.pkl")
                joblib.dump(dni_model, f"core/models/{mt}_dni.pkl")
                ghi_sz = os.path.getsize(f"core/models/{mt}_ghi.pkl") / 1024 / 1024
                print(f"  {mt.upper():12s}: ({time.time()-t0:.0f}s)  {ghi_sz:.1f} MB")

        # Meta-model: collect ratio predictions from all base models
        meta_cols_ghi, meta_cols_dni = [], []
        for mt in BASE_MODELS:
            if mt in lstm_full_preds:
                meta_cols_ghi.append(lstm_full_preds[mt])
                meta_cols_dni.append(lstm_full_preds[mt])
            else:
                meta_cols_ghi.append(np.clip(joblib.load(f"core/models/{mt}_ghi.pkl").predict(X), 0.0, 3.0))
                meta_cols_dni.append(np.clip(joblib.load(f"core/models/{mt}_dni.pkl").predict(X), 0.0, 3.0))

        meta_X_ghi = np.column_stack(meta_cols_ghi)
        meta_X_dni = np.column_stack(meta_cols_dni)
        t0 = time.time()
        meta_ghi = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, n_jobs=1)
        meta_dni = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=3, n_jobs=1)
        meta_ghi.fit(meta_X_ghi, y_ghi)
        meta_dni.fit(meta_X_dni, y_dni)
        joblib.dump(meta_ghi, "core/models/meta_ghi.pkl")
        joblib.dump(meta_dni, "core/models/meta_dni.pkl")
        print(f"  META         : ({time.time()-t0:.0f}s)  core/models/meta_ghi.pkl")

        best = "meta"
    else:
        for mt in model_list:
            t0 = time.time()
            print(f"\n  {mt.upper()}...", end=" ", flush=True)

            if args.tune and mt == "xgboost":
                print("\n    Tuning GHI...")
                ghi_model = tune_xgboost(X, y_ghi, sample_weight=sw, n_iter=30)
                print("    Tuning DNI...")
                dni_model = tune_xgboost(X, y_dni, sample_weight=sw, n_iter=30)
            else:
                ghi_model = make_model(mt)
                dni_model = make_model(mt)
                fit_model(ghi_model, X, y_ghi, sample_weight=sw)
                fit_model(dni_model, X, y_dni, sample_weight=sw)

            elapsed = time.time() - t0

            # Save
            ghi_path = f"core/models/{mt}_ghi.pkl"
            dni_path = f"core/models/{mt}_dni.pkl"
            os.makedirs("core/models", exist_ok=True)
            joblib.dump(ghi_model, ghi_path)
            joblib.dump(dni_model, dni_path)
            ghi_sz = os.path.getsize(ghi_path) / 1024 / 1024
            dni_sz = os.path.getsize(dni_path) / 1024 / 1024
            print(f"({elapsed:.0f}s)  {ghi_path} ({ghi_sz:.1f} MB), {dni_path} ({dni_sz:.1f} MB)")

        # Best -> default (prefer Ridge when within 1 RMSE of best — linear models generalize better)
        print(f"\n  Copying best model as default...")
        import shutil
        if kfold_results:
            best_raw = min(kfold_results, key=kfold_results.get)
            best_score = kfold_results[best_raw]
            candidates = [k for k, v in kfold_results.items() if v <= best_score + 1.0]
            if "ridge" in candidates:
                best = "ridge"
            else:
                best = best_raw
        else:
            best = "xgboost"
        shutil.copy2(f"core/models/{best}_ghi.pkl", "core/models/default_ghi.pkl")
        shutil.copy2(f"core/models/{best}_dni.pkl", "core/models/default_dni.pkl")
        kfold_str = f"{kfold_results.get(best, 0):.2f}" if isinstance(kfold_results.get(best), (int, float)) else str(kfold_results.get(best, 'N/A'))
        print(f"  Default → {best} (k-fold: {kfold_str})")

    # LSTM standalone final training
    if args.lstm and not args.stacking:
        print(f"\n  Training LSTM final models...")
        for variant_label, variant in [("base", "base"), ("attn", "attn")]:
            t0 = time.time()
            ckpt, _ = _train_lstm_full(variant, n_seeds=LSTM_N_SEEDS) if args.stacking else (None, None)
            if not args.stacking:
                # Train LSTM on full data
                df_seq = df.copy().reset_index(drop=True)
                df_seq['station_bias'] = 0.0
                X_seq, y_seq, _ = lstm_sequences(df_seq, LSTM_FEATURES, LSTM_SEQ_LEN)
                m_s = X_seq.mean(axis=(0, 1), keepdims=True)
                s_s = X_seq.std(axis=(0, 1), keepdims=True) + 1e-8
                X_seq_n = (X_seq - m_s) / s_s
                sl = DataLoader(SeqDataset(X_seq_n, y_seq), LSTM_BATCH_SIZE, shuffle=True)

                best_model = None
                best_loss = float('inf')
                for seed in range(LSTM_N_SEEDS):
                    torch.manual_seed(seed)
                    np.random.seed(seed)
                    model = make_lstm_model(variant)
                    opt = optim.AdamW(model.parameters(), lr=LSTM_LR, weight_decay=1e-4)
                    sched = optim.lr_scheduler.ReduceLROnPlateau(opt, mode='min', factor=0.5, patience=3)
                    crit = nn.MSELoss()
                    best_val = float('inf'); stale = 0
                    for ep in range(LSTM_EPOCHS):
                        model.train()
                        for Xb, yb in sl:
                            opt.zero_grad()
                            crit(model(Xb), yb).backward()
                            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                            opt.step()
                        model.eval()
                        with torch.no_grad():
                            vloss = sum(crit(model(Xb), yb).item() * len(Xb) for Xb, yb in sl) / len(sl.dataset)
                        sched.step(vloss)
                        if vloss < best_val: best_val = vloss; stale = 0
                        else: stale += 1
                        if stale >= LSTM_PATIENCE: break
                    if best_val < best_loss:
                        best_loss = best_val
                        best_model = model
                ckpt = {'model_state': best_model.state_dict(), 'mean': m_s, 'std': s_s}
            suffix = "attn_" if variant == "attn" else ""
            path = f"core/models/lstm{'_attn' if variant=='attn' else ''}_ratio.pt"
            torch.save(ckpt, path)
            print(f"  LSTM_{variant.upper():8s}: ({time.time()-t0:.0f}s)  {path}")

    # Per-station calibration
    print(f"\n  Computing per-station calibration...")
    df = df.reset_index(drop=True)
    if args.stacking:
        meta_cols = []
        for mt in BASE_MODELS:
            if mt in ("lstm", "lstm_attn"):
                variant = "attn" if mt == "lstm_attn" else "base"
                ckpt = torch.load(f"core/models/{mt}_ratio.pt", map_location='cpu', weights_only=False)
                model = make_lstm_model(variant)
                model.load_state_dict(ckpt['model_state'])
                model.eval()
                m_s, s_s = ckpt['mean'], ckpt['std']
                with torch.no_grad():
                    lstm_preds_all = []
                    for g in df['group'].unique():
                        gdf = df[df['group'] == g].sort_values('timestamp')
                        Xb, _, _ = lstm_sequences(gdf, LSTM_FEATURES, LSTM_SEQ_LEN)
                        if len(Xb) > 0:
                            Xb = (Xb - m_s) / s_s
                            pr = np.array(model(torch.FloatTensor(Xb)).detach().cpu().tolist()).ravel()
                            lstm_preds_all.extend(pr)
                full = np.ones(len(df))
                for g in df['group'].unique():
                    gdf = df[df['group'] == g].sort_values('timestamp')
                    gidx = gdf.index.values
                    if len(gidx) >= LSTM_SEQ_LEN:
                        full[gidx[LSTM_SEQ_LEN-1:]] = lstm_preds_all[:len(gidx)-LSTM_SEQ_LEN+1]
                        lstm_preds_all = lstm_preds_all[len(gidx)-LSTM_SEQ_LEN+1:]
                meta_cols.append(np.clip(full, 0.0, 3.0))
            else:
                meta_cols.append(np.clip(joblib.load(f"core/models/{mt}_ghi.pkl").predict(df[FEATURES]), 0.0, 3.0))
        base_preds = np.column_stack(meta_cols)
        y_pred_all = df["ghi_satellite"].values * np.clip(
            joblib.load("core/models/meta_ghi.pkl").predict(base_preds), 0.0, 3.0)
    else:
        best_model = joblib.load(f"core/models/default_ghi.pkl")
        y_pred_all = df["ghi_satellite"].values * np.clip(best_model.predict(df[FEATURES]), 0.0, 3.0)
    y_true_all = df["ghi_ground"].values
    station_deltas = {}
    for station, grp in df.groupby("group"):
        idx = grp.index
        delta = np.median(y_true_all[idx] - y_pred_all[idx])
        lat = round(grp["latitude"].iloc[0], 2)
        lon = round(grp["longitude"].iloc[0], 2)
        key = f"{lat},{lon}"
        station_deltas[key] = round(delta, 2)
    cal_path = "core/models/station_calibration.json"
    with open(cal_path, "w") as f:
        json.dump(station_deltas, f, indent=2)
    print(f"  Calibration saved → {cal_path} ({len(station_deltas)} stations)")
    median_delta = np.median(list(station_deltas.values()))
    print(f"  Median per-station bias correction: {median_delta:+.1f} W/m²")

    # Save metadata
    meta = {
        "records": len(df),
        "groups": df["group"].nunique(),
        "features": FEATURES,
        "lstm_features": LSTM_FEATURES,
        "raw_rmse": round(raw_rmse, 2),
        "default_model": best,
        "stacking": args.stacking,
        "stacking_rmse": round(stacking_rmse, 2) if stacking_rmse else None,
        "base_models": BASE_MODELS,
        "tuned": args.tune,
        "zindi_only": args.zindi_only,
    }
    with open("data/processed/training_info.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata → data/processed/training_info.json")

    print(f"\n{'=' * 65}")
    print("DONE")
    print("=" * 65)


if __name__ == "__main__":
    main()

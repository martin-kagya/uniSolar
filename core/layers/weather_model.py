import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy.orm import Session
from core.database import WeatherData
import json
import joblib
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from core.services.gis import GISService
import pvlib

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None



class RatioLSTM(nn.Module):
    """Bidirectional LSTM for ratio prediction. Matches make_lstm_model variant."""
    def __init__(self, input_dim=21, hidden_dim=32, num_layers=2, dropout=0.2, variant="base"):
        super().__init__()
        self.variant = variant
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True,
                            bidirectional=True, dropout=dropout if num_layers > 1 else 0)
        if variant == "attn":
            self.attn = nn.MultiheadAttention(hidden_dim * 2, 4, batch_first=True)
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden_dim, 1),
        )

    def forward(self, x):
        out, (h, _) = self.lstm(x)
        if self.variant == "attn":
            a, _ = self.attn(out, out, out)
            pooled = (out + a).mean(dim=1)
        else:
            pooled = torch.cat([h[-2], h[-1]], 1)
        return torch.sigmoid(self.fc(pooled)).squeeze(-1) * 3.0


def lstm_sequences(df, features, seq_len):
    """Create sequences for LSTM input from a sorted single-group DataFrame."""
    vals = df[features].values
    X, y = [], []
    for i in range(len(vals) - seq_len + 1):
        X.append(vals[i:i+seq_len])
    if 'ghi_ground' in df.columns and 'ghi_satellite' in df.columns:
        gs = df['ghi_satellite'].values
        gg = df['ghi_ground'].values
        for i in range(seq_len - 1, len(vals)):
            ratio = np.clip(gg[i] / max(gs[i], 10.0), 0.0, 3.0)
            y.append(ratio)
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32) if y else None, vals


class WeatherCorrectionLayer:
    """
    Layer 1: Corrects Satellite Irradiance Data using Machine Learning.
    Input: Raw Satellite Data (NASA POWER)
    Output: Bias-Corrected Irradiance (GHI, DNI) that matches Ground Truth.
    """
    
    def __init__(self, model_type='xgboost', model_path_ghi=None, model_path_dni=None):
        self.model_type = model_type
        self.model_ghi = None
        self.model_dni = None
        
        if model_path_ghi is None:
            self.model_path_ghi = f'core/models/{model_type}_ghi.pkl'
        else:
            self.model_path_ghi = model_path_ghi
            
        if model_path_dni is None:
            self.model_path_dni = f'core/models/{model_type}_dni.pkl'
        else:
            self.model_path_dni = model_path_dni
        
        # Ensure model directory exists
        os.makedirs(os.path.dirname(self.model_path_ghi), exist_ok=True)
        
        # Stacking ensemble: only active when model_type='meta'
        self._is_stacking = (model_type == 'meta')
        self._base_models_ghi = {}
        self._base_models_dni = {}
        self._meta_ghi = None
        self._meta_dni = None
        self._base_model_names = ["xgboost", "rf", "ridge"]
        self._lstm_model = None
        self._lstm_norm = None
        self._lstm_features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite',
            'ghi_satellite_lag1', 'ghi_satellite_lag2',
            'temp_air', 'relative_humidity', 'wind_speed',
            'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
            'pm25', 'aod_550', 'clearness_index',
            'clearness_index_lag1', 'clearness_index_std_3h', 'clearness_index_delta',
            'solar_zenith', 'solar_elevation', 'clear_sky_ghi',
        ]
        self._lstm_seq_len = 4
        
        # Load CAMS PM2.5 reanalysis for prediction look-up
        self._cams_pm25 = None
        cams_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "data", "processed", "cams_pm25.parquet")
        if os.path.exists(cams_path):
            try:
                cams = pd.read_parquet(cams_path)
                cams.rename(columns={"name": "station"}, inplace=True)
                cams["timestamp"] = pd.to_datetime(cams["timestamp"])
                self._cams_pm25 = cams.sort_values("timestamp")
            except Exception:
                self._cams_pm25 = None
        
    def load_data(self, session: Session, location_id: int = None, require_ground_truth: bool = True):
        """Loads data from DB and prepares DataFrame."""
        from core.database import Location
        
        query = session.query(WeatherData)
        if location_id:
            query = query.filter_by(location_id=location_id)
            
        # Only fetch rows where we have Ground Truth (for training)
        if require_ground_truth:
            query = query.filter(WeatherData.ghi_ground.isnot(None))
        
        data = query.all()
        
        if not data and require_ground_truth:
            raise ValueError("No training data found (Ground Truth missing).")
        
        if not data:
            return pd.DataFrame()
            
        df = pd.DataFrame([d.__dict__ for d in data])
        # Cleanup sqlalchemy state field
        if '_sa_instance_state' in df.columns:
            df = df.drop('_sa_instance_state', axis=1)
            
        # Only drop NaNs and apply alignment if we're in training mode (require_ground_truth)
        if require_ground_truth:
            # TEMPORAL ALIGNMENT FIX
            # Detected 1-hour shift: Satellite(t) matches Ground(t+1)
            # We shift Ground Truth BACK by -1 to align with Satellite index
            df = df.sort_values(['location_id', 'timestamp'])
            for loc_id in df['location_id'].unique():
                 mask = df['location_id'] == loc_id
                 df.loc[mask, 'ghi_ground'] = df.loc[mask, 'ghi_ground'].shift(-1)
                 df.loc[mask, 'dni_ground'] = df.loc[mask, 'dni_ground'].shift(-1)
            
            df = df.dropna(subset=['ghi_ground', 'dni_ground'])
        
        location_map = {}
        for loc in session.query(Location).all():
            # Use cached values if available, otherwise fallback (which shouldn't happen after migration)
            dist = loc.dist_to_coast_km 
            elev = loc.elevation
            zone = loc.climate_zone
            
            # Fallback if migration hasn't run or data missing
            if dist is None or zone is None:
                 dist, elev, zone = self._get_proxies(loc.latitude, loc.longitude)
            
            location_map[loc.id] = {
                'dist_to_coast_km': dist,
                'elevation_m': elev if elev else 100, # Default elevation
                'climate_zone': zone
            }
        
        df['dist_to_coast_km'] = df['location_id'].map(lambda x: location_map[x]['dist_to_coast_km'])
        df['elevation_m'] = df['location_id'].map(lambda x: location_map[x]['elevation_m'])
        df['climate_zone'] = df['location_id'].map(lambda x: location_map[x]['climate_zone'])
            
        # Feature Engineering: Time
        df['hour'] = df['timestamp'].apply(lambda x: x.hour)
        df['month'] = df['timestamp'].apply(lambda x: x.month)
        
        # FILTER: Remove rows with missing NASA data (-999)
        df = df[df['ghi_satellite'] != -999]
        df = df[df['dni_satellite'] != -999]
        
        return df

    def _get_proxies(self, lat, lon):
        """Returns distance_to_coast_km, elevation_m, and climate_zone using GIS Service."""
        gis = GISService()
        
        dist_coast = gis.get_distance_to_coast(lat, lon)
        elevation = gis.get_elevation(lat, lon)
        zone = gis.get_climate_zone(lat, lon, elevation)
        
        # Defaults if GIS fails
        if elevation is None: elevation = 100.0
        
        return dist_coast, elevation, zone

    def _build_features(self, df, training=False):
        """Single source of truth for all feature engineering.

        Uses pvlib Ineichen model for physically-grounded clearness_index,
        solar geometry, and cloud cover from available data.

        Args:
            df: Input DataFrame with at minimum ghi_satellite + timestamp or latitude
            training: If True, capture training-time stats (currently unused).
        """
        df = df.copy()

        # Time features
        if 'timestamp' in df.columns:
            df['hour'] = pd.to_datetime(df['timestamp']).dt.hour.astype(int)
            df['month'] = pd.to_datetime(df['timestamp']).dt.month.astype(int)
        else:
            if 'hour' not in df.columns: df['hour'] = 12
            if 'month' not in df.columns: df['month'] = 6

        # Cyclical encoding
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        # Lag-1 features for temporal alignment (NASA 3-hourly vs hourly ground)
        if 'station' in df.columns and 'ghi_satellite' in df.columns:
            df = df.sort_values(['station', 'timestamp']).reset_index(drop=True)
            lag_cols = [('ghi_satellite', 'ghi_satellite_lag1'),
                        ('dni_satellite', 'dni_satellite_lag1'),
                        ('dhi_satellite', 'dhi_satellite_lag1')]
            for src, dst in lag_cols:
                if dst not in df.columns:
                    df[dst] = df.groupby('station')[src].shift(1).fillna(df[src])
        else:
            for col in ['ghi_satellite_lag1', 'dni_satellite_lag1', 'dhi_satellite_lag1']:
                if col not in df.columns:
                    df[col] = df.get(col.replace('_lag1', ''), 0.0)

        # Default scalar features
        if 'pm25' not in df.columns:
            # Try CAMS PM2.5 reanalysis if station+timestamp available
            if (hasattr(self, '_cams_pm25') and self._cams_pm25 is not None
                    and 'station' in df.columns and 'timestamp' in df.columns):
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.sort_values("timestamp")
                df = pd.merge_asof(
                    df, self._cams_pm25[["station", "timestamp", "pm25_cams"]],
                    on="timestamp", by="station", direction="nearest",
                    tolerance=pd.Timedelta("90min")
                )
                df["pm25"] = df["pm25_cams"].fillna(25.0)
            else:
                df['pm25'] = 25.0
        if 'albedo' not in df.columns: df['albedo'] = 0.2
        if 'cloud_amt' not in df.columns: df['cloud_amt'] = 0.5
        for f in ['pm25', 'albedo', 'dist_to_coast_km', 'elevation_m', 'cloud_amt']:
            if f in df.columns:
                df[f] = pd.to_numeric(df[f], errors='coerce').fillna(0.0)

        # AOD at 550nm — force float32 regardless of source dtype
        if 'aod_550' in df.columns:
            df['aod_550'] = pd.to_numeric(df['aod_550'], errors='coerce').fillna(0.15).astype('float32')
        elif 'power_AOD_55' in df.columns:
            df['aod_550'] = df['power_AOD_55'].astype('float32')
        else:
            df['aod_550'] = 0.15

        # GIS proxies (computed once, not row-by-row)
        if 'dist_to_coast_km' not in df.columns or df['dist_to_coast_km'].isnull().any():
            lat = df['latitude'].iloc[0] if 'latitude' in df.columns else 5.6
            lon = df['longitude'].iloc[0] if 'longitude' in df.columns else -0.2
            dist, elev, zone = self._get_proxies(lat, lon)
            df['dist_to_coast_km'] = dist
            df['elevation_m'] = elev
            df['climate_zone'] = zone

        # Lat/lon features (float32 for tree models)
        if 'latitude' in df.columns:
            df['latitude_f'] = df['latitude'].astype('float32')
        if 'longitude' in df.columns:
            df['longitude_f'] = df['longitude'].astype('float32')

        # One-hot climate zone
        if 'climate_zone' in df.columns:
            for i in range(3):
                df[f'cz_{i}.0'] = (df['climate_zone'] == i).astype('float32')
        else:
            df['climate_zone'] = 0
            df['cz_0.0'] = 1.0
            df['cz_1.0'] = 0.0
            df['cz_2.0'] = 0.0

        # Solar geometry + Ineichen clear-sky (pvlib) — always computed when lat/lon + timestamp available
        if 'timestamp' in df.columns and 'latitude' in df.columns:
            if 'solar_zenith' not in df.columns:
                df['solar_zenith'] = np.nan
                df['solar_elevation'] = np.nan
                df['airmass'] = np.nan
                df['clearness_index'] = np.nan
                df['clear_sky_ghi'] = np.nan
                df['clear_sky_dni'] = np.nan
                for (lat, lon), gidx in df.groupby(
                    [df['latitude'].round(2), df['longitude'].round(2)], sort=False
                ).indices.items():
                    idx = df.index[gidx]
                    elev = float(df.loc[idx[0], 'elevation_m']) if 'elevation_m' in df.columns else 100.0
                    times = pd.DatetimeIndex(df.loc[idx, 'timestamp'])
                    loc = pvlib.location.Location(latitude=lat, longitude=lon, altitude=elev)
                    sp = loc.get_solarposition(times)
                    df.loc[idx, 'solar_zenith'] = sp['apparent_zenith'].values
                    df.loc[idx, 'solar_elevation'] = sp['apparent_elevation'].values
                    df.loc[idx, 'airmass'] = pvlib.atmosphere.get_relative_airmass(
                        np.maximum(sp['apparent_zenith'].values, 0.01)
                    )
                    cs = loc.get_clearsky(times, model='ineichen')
                    df.loc[idx, 'clear_sky_ghi'] = cs['ghi'].values
                    df.loc[idx, 'clear_sky_dni'] = cs['dni'].values
                    df.loc[idx, 'clearness_index'] = np.clip(
                        df.loc[idx, 'ghi_satellite'].values / np.maximum(cs['ghi'].values, 1.0),
                        0.0, 1.2
                    )
        else:
            if 'solar_zenith' not in df.columns: df['solar_zenith'] = 30.0
            if 'solar_elevation' not in df.columns: df['solar_elevation'] = 60.0
            if 'airmass' not in df.columns: df['airmass'] = 1.5
            if 'clearness_index' not in df.columns: df['clearness_index'] = 0.7
            if 'clear_sky_ghi' not in df.columns: df['clear_sky_ghi'] = 500.0
            if 'clear_sky_dni' not in df.columns: df['clear_sky_dni'] = 800.0

        # Cloud variability features (requires clearness_index which is computed above)
        if 'station' in df.columns and 'timestamp' in df.columns:
            df = df.sort_values(['station', 'timestamp']).reset_index(drop=True)
            if 'ghi_satellite_lag2' not in df.columns:
                df['ghi_satellite_lag2'] = df.groupby('station')['ghi_satellite'].shift(2).fillna(df['ghi_satellite'])
            if 'clearness_index_lag1' not in df.columns:
                df['clearness_index_lag1'] = df.groupby('station')['clearness_index'].shift(1).fillna(df['clearness_index'])
            if 'clearness_index_std_3h' not in df.columns:
                df['clearness_index_std_3h'] = df.groupby('station')['clearness_index'].transform(
                    lambda x: x.rolling(3, min_periods=1).std()
                ).fillna(0.0)
            if 'clearness_index_delta' not in df.columns:
                df['clearness_index_delta'] = df.groupby('station')['clearness_index'].diff(1).fillna(0.0)
        else:
            if 'ghi_satellite_lag2' not in df.columns: df['ghi_satellite_lag2'] = df.get('ghi_satellite', 0.0)
            if 'clearness_index_lag1' not in df.columns: df['clearness_index_lag1'] = df.get('clearness_index', 0.7)
            if 'clearness_index_std_3h' not in df.columns: df['clearness_index_std_3h'] = 0.0
            if 'clearness_index_delta' not in df.columns: df['clearness_index_delta'] = 0.0

        # Station bias (from station_calibration.json, already loaded by predict())
        if not training and hasattr(self, '_station_calibration'):
            if self._station_calibration and 'latitude' in df.columns and 'longitude' in df.columns:
                lat = round(df['latitude'].iloc[0], 2)
                lon = round(df['longitude'].iloc[0], 2)
                key = f'{lat},{lon}'
                if key in self._station_calibration:
                    df['station_bias'] = self._station_calibration[key]

        return df

    def train(self, df):
        """Trains models to predict ratio = GHI / GHI_satellite.
        GHI correction: ghi_corrected = ghi_satellite * predicted_ratio
        """
        features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite',
            'ghi_satellite_lag1', 'dni_satellite_lag1', 'dhi_satellite_lag1',
            'ghi_satellite_lag2',
            'temp_air', 'relative_humidity', 'wind_speed',
            'hour', 'month',
            'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
            'pm25', 'albedo', 'cloud_amt', 'aod_550',
            'dist_to_coast_km', 'elevation_m',
            'clearness_index', 'clear_sky_ghi',
            'clearness_index_lag1', 'clearness_index_std_3h', 'clearness_index_delta',
            'solar_zenith', 'solar_elevation', 'airmass',
            'latitude_f', 'longitude_f',
            'cz_0.0', 'cz_1.0', 'cz_2.0',
        ]

        mask = (df['ghi_satellite'] > 0) | (df['ghi_ground'] > 0)
        df_clean = self._build_features(df[mask], training=True)

        y_ghi = np.clip(df_clean['ghi_ground'].values / np.maximum(df_clean['ghi_satellite'].values, 10.0), 0.0, 3.0)
        y_dni = np.clip(df_clean['dni_ground'].values / np.maximum(df_clean['dni_satellite'].values, 10.0), 0.0, 3.0)

        X = df_clean[features]

        if self.model_type == 'xgboost':
            print("Training GHI Ratio Model (XGBoost)...")
            self.model_ghi = xgb.XGBRegressor(n_estimators=500, learning_rate=0.03, max_depth=7, objective='reg:squarederror')
            self.model_ghi.fit(X, y_ghi)

            print("Training DNI Ratio Model (XGBoost)...")
            self.model_dni = xgb.XGBRegressor(n_estimators=500, learning_rate=0.03, max_depth=7, objective='reg:squarederror')
            self.model_dni.fit(X, y_dni)

        elif self.model_type == 'rf':
            print("Training GHI Ratio Model (Random Forest)...")
            self.model_ghi = RandomForestRegressor(n_estimators=200, max_depth=10, n_jobs=1)
            self.model_ghi.fit(X, y_ghi)

            print("Training DNI Ratio Model (Random Forest)...")
            self.model_dni = RandomForestRegressor(n_estimators=200, max_depth=10, n_jobs=1)
            self.model_dni.fit(X, y_dni)

        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")

        self.save_models()
        print("Models trained and saved.")

    def save_models(self):
        joblib.dump(self.model_ghi, self.model_path_ghi)
        joblib.dump(self.model_dni, self.model_path_dni)
        
    def load_models(self):
        if self._is_stacking:
            base_dir = os.path.dirname(self.model_path_ghi)
            for mt in self._base_model_names:
                gh = os.path.join(base_dir, f"{mt}_ghi.pkl")
                dn = os.path.join(base_dir, f"{mt}_dni.pkl")
                if os.path.exists(gh):
                    self._base_models_ghi[mt] = joblib.load(gh)
                if os.path.exists(dn):
                    self._base_models_dni[mt] = joblib.load(dn)
            for lstm_variant in ("lstm", "lstm_attn"):
                ckpt_path = os.path.join(base_dir, f"{lstm_variant}_ratio.pt")
                if os.path.exists(ckpt_path):
                    ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
                    model = RatioLSTM(variant="attn" if lstm_variant == "lstm_attn" else "base")
                    model.load_state_dict(ckpt['model_state'])
                    model.eval()
                    setattr(self, f'_lstm_{lstm_variant}', model)
                    setattr(self, f'_lstm_{lstm_variant}_norm',
                        (torch.FloatTensor(ckpt['mean']), torch.FloatTensor(ckpt['std'])))
            meta_g = os.path.join(base_dir, "meta_ghi.pkl")
            meta_d = os.path.join(base_dir, "meta_dni.pkl")
            if os.path.exists(meta_g):
                self._meta_ghi = joblib.load(meta_g)
            if os.path.exists(meta_d):
                self._meta_dni = joblib.load(meta_d)
            # For feature-list detection, use the first base model
            self.model_ghi = self._base_models_ghi.get(self._base_model_names[0])
            self.model_dni = self._base_models_dni.get(self._base_model_names[0])
        else:
            if os.path.exists(self.model_path_ghi):
                self.model_ghi = joblib.load(self.model_path_ghi)
            if os.path.exists(self.model_path_dni):
                self.model_dni = joblib.load(self.model_path_dni)
            
    def predict(self, df, max_correction_ratio=1.6):
        """
        Applies correction to new data.
        Returns DataFrame with 'ghi_corrected' and 'dni_corrected'.

        Uses ratio target: ghi_corrected = ghi_satellite * predicted_ratio

        Args:
            df: Input DataFrame with satellite data
            max_correction_ratio: Default 1.6 (allows +60% correction).
                                  NASA POWER often under-reports by 30-50% in West Africa.
        """
        if self.model_ghi is None or self.model_dni is None:
            self.load_models()

        # Load per-station calibration BEFORE _build_features (needed for station_bias)
        if not hasattr(self, '_calibration_loaded'):
            self._station_calibration = {}
            cal_path = 'core/models/station_calibration.json'
            if os.path.exists(cal_path):
                with open(cal_path) as f:
                    self._station_calibration = json.load(f)
            self._calibration_loaded = True

        # Copy first, then build features on the copy (never mutate caller's df)
        df_out = df.copy()
        df_out = self._build_features(df_out, training=False)

        # Fill any NaN in numeric columns (Ridge crashes on NaN; tree models ignore but safer)
        for c in df_out.select_dtypes(include=['float64', 'float32']).columns:
            if df_out[c].isnull().any():
                df_out[c] = df_out[c].fillna(0.0)

        # Ensure consistent column types (fixes mixed str/str_ dtype issues)
        df_out.columns = df_out.columns.astype(str)

        eps = 1.0

        base_features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite',
            'ghi_satellite_lag1', 'dni_satellite_lag1', 'dhi_satellite_lag1',
            'ghi_satellite_lag2',
            'temp_air', 'relative_humidity', 'wind_speed',
            'hour', 'month',
            'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
            'pm25', 'albedo', 'cloud_amt', 'aod_550',
            'dist_to_coast_km', 'elevation_m',
            'clearness_index', 'clear_sky_ghi',
            'clearness_index_lag1', 'clearness_index_std_3h', 'clearness_index_delta',
            'solar_zenith', 'solar_elevation', 'airmass',
            'station_bias',
            'latitude_f', 'longitude_f',
            'cz_0.0', 'cz_1.0', 'cz_2.0',
        ]

        # --- Dynamic feature list: honour whatever the saved model was trained on ---
        if hasattr(self.model_ghi, 'feature_name_') and self.model_ghi.feature_name_:
            features = list(self.model_ghi.feature_name_)
        elif hasattr(self.model_ghi, 'feature_names_in_'):
            features = list(self.model_ghi.feature_names_in_)
        else:
            features = list(base_features)

        # Ensure every expected feature column exists
        for f in features:
            if f not in df_out.columns:
                df_out[f] = 0.0

        X = df_out[features]

        # Cast all feature columns to numeric (XGBoost rejects object dtypes)
        for c in X.columns:
            if X[c].dtype == 'object':
                X[c] = pd.to_numeric(X[c], errors='coerce').fillna(0.0)

        # Predict ratio (bounded [0.0, 3.0])
        if self._is_stacking and self._meta_ghi is not None:
            X_clean = X.fillna(0.0)
            base_cols = [np.clip(self._base_models_ghi[mt].predict(X_clean), 0.0, 3.0)
                         for mt in self._base_model_names if mt in self._base_models_ghi]

            # LSTM columns: shared sequence building, separate predictions
            lstm_features = self._lstm_features
            seq_len = self._lstm_seq_len
            lf = [f for f in lstm_features if f in df_out.columns]
            vals = df_out[lf].values
            dl_cols = []
            for lstm_variant in ("lstm", "lstm_attn"):
                model = getattr(self, f'_lstm_{lstm_variant}', None)
                norm = getattr(self, f'_lstm_{lstm_variant}_norm', None)
                if model is not None and norm is not None and len(vals) >= seq_len:
                    m_s, s_s = norm
                    seqs = np.zeros((len(vals) - seq_len + 1, seq_len, len(lf)), dtype=np.float32)
                    for i in range(len(vals) - seq_len + 1):
                        seqs[i] = vals[i:i+seq_len]
                    seqs = (seqs - m_s.numpy()) / s_s.numpy()
                    with torch.no_grad():
                        pr = model(torch.FloatTensor(seqs)).numpy().ravel()
                    preds = np.full(len(df_out), pr[0])  # fill lead with first valid
                    preds[seq_len-1:] = np.clip(pr, 0.0, 3.0)
                    dl_cols.append(preds)

            all_cols = base_cols + dl_cols
            meta_X = np.column_stack(all_cols)
            ghi_ratio_pred = np.clip(self._meta_ghi.predict(meta_X), 0.0, 3.0)
            if self._meta_dni is not None:
                base_cols_dni = [np.clip(self._base_models_dni[mt].predict(X_clean), 0.0, 3.0)
                                 for mt in self._base_model_names if mt in self._base_models_dni]
                meta_X_dni = np.column_stack(base_cols_dni + dl_cols)
                dni_ratio_pred = np.clip(self._meta_dni.predict(meta_X_dni), 0.0, 3.0)
            else:
                dni_ratio_pred = ghi_ratio_pred
        else:
            ghi_ratio_pred = np.clip(self.model_ghi.predict(X), 0.0, 3.0)
            dni_ratio_pred = np.clip(self.model_dni.predict(X), 0.0, 3.0)

        # Apply correction: corrected = satellite * predicted_ratio
        ghi_ml_corrected = df_out['ghi_satellite'].values * ghi_ratio_pred
        dni_ml_corrected = df_out['dni_satellite'].values * dni_ratio_pred

        if max_correction_ratio is not None:
            clear_sky_ghi = df_out['clear_sky_ghi'].values
            clear_sky_dni = df_out['clear_sky_dni'].values
            ghi_max = np.maximum(clear_sky_ghi * max_correction_ratio, 120.0)
            dni_max = np.maximum(clear_sky_dni * max_correction_ratio, 250.0)

            is_night = (df_out['hour'] < 5) | (df_out['hour'] > 19)

            ghi_corrected = np.where(is_night, 0.0, np.clip(ghi_ml_corrected, 0.0, ghi_max))
            dni_corrected = np.where(is_night, 0.0, np.clip(dni_ml_corrected, 0.0, dni_max))
        else:
            ghi_corrected = ghi_ml_corrected
            dni_corrected = dni_ml_corrected

        df_out['ghi_corrected'] = np.maximum(ghi_corrected, 0)
        df_out['dni_corrected'] = np.maximum(dni_corrected, 0)

        # Per-station calibration from retrain_unified (station_calibration.json)
        if self._station_calibration and 'latitude' in df_out.columns:
            lat = round(df_out['latitude'].iloc[0], 2)
            lon = round(df_out['longitude'].iloc[0], 2)
            key = f"{lat},{lon}"
            if key in self._station_calibration:
                delta = self._station_calibration[key]
                df_out['ghi_corrected'] += delta
                df_out['dni_corrected'] += delta

        return df_out


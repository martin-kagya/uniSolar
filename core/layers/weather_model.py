import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestRegressor
from sqlalchemy.orm import Session
from core.database import WeatherData
import joblib
import os
from sklearn.model_selection import RandomizedSearchCV
from core.services.gis import GISService



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
        
    def train(self, df):
        """Trains the XGBoost models for GHI and DNI correction."""
        features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite', 
            'temp_air', 'relative_humidity', 'wind_speed', 
            'hour', 'month',
            'pm25', 'albedo',
            'dist_to_coast_km', 'elevation_m', 'climate_zone'
        ]
        
        # Target 1: Additive Residual (Ground - Satellite)
        # This allows for correcting "blind" satellite readings (e.g. dawn/dusk)
        # We only filter for nighttime where both are zero for cleaner training
        mask = (df['ghi_satellite'] > 0) | (df['ghi_ground'] > 0)
        df_clean = df[mask].copy()
        
        y_ghi_res = df_clean['ghi_ground'] - df_clean['ghi_satellite']
        y_dni_res = df_clean['dni_ground'] - df_clean['dni_satellite']
        
        X = df_clean[features]
        
        if self.model_type == 'xgboost':
            print("Training GHI Residual Model (XGBoost)...")
            self.model_ghi = xgb.XGBRegressor(n_estimators=500, learning_rate=0.03, max_depth=7, objective='reg:squarederror')
            self.model_ghi.fit(X, y_ghi_res)
            
            print("Training DNI Residual Model (XGBoost)...")
            self.model_dni = xgb.XGBRegressor(n_estimators=500, learning_rate=0.03, max_depth=7, objective='reg:squarederror')
            self.model_dni.fit(X, y_dni_res)
            
        elif self.model_type == 'lightgbm':
            print("Training GHI Residual Model (LightGBM)...")
            self.model_ghi = lgb.LGBMRegressor(n_estimators=1000, learning_rate=0.03, max_depth=9)
            self.model_ghi.fit(X, y_ghi_res, categorical_feature=['climate_zone'])
            
            print("Training DNI Residual Model (LightGBM)...")
            self.model_dni = lgb.LGBMRegressor(n_estimators=1000, learning_rate=0.03, max_depth=9)
            self.model_dni.fit(X, y_dni_res, categorical_feature=['climate_zone'])
            
        elif self.model_type == 'rf':
            print("Training GHI Correction Model (Random Forest)...")
            self.model_ghi = RandomForestRegressor(n_estimators=200, max_depth=10, n_jobs=1)
            # Ensure we pass the DataFrame X to preserve feature names
            self.model_ghi.fit(X, y_ghi_res)
            
            print("Training DNI Correction Model (Random Forest)...")
            self.model_dni = RandomForestRegressor(n_estimators=200, max_depth=10, n_jobs=1)
            self.model_dni.fit(X, y_dni_res)
            
        else:
            raise ValueError(f"Unknown model_type: {self.model_type}")
        
        self.save_models()
        print("Models trained and saved.")

    def train_optimized(self, df, n_iter=10):
        """
        Trains models using RandomizedSearchCV to find best hyperparameters.
        """
        features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite', 
            'temp_air', 'relative_humidity', 'wind_speed', 
            'hour', 'month',
            'pm25', 'albedo',
            'dist_to_coast_km', 'elevation_m', 'climate_zone'
        ]
        
        # Residuals with daytime mask
        mask = (df['ghi_satellite'] > 0) | (df['ghi_ground'] > 0)
        df_clean = df[mask].copy()
        
        y_ghi_res = df_clean['ghi_ground'] - df_clean['ghi_satellite']
        y_dni_res = df_clean['dni_ground'] - df_clean['dni_satellite']
        
        X = df_clean[features]
        
        # ... (hyperparam grids)
        
        # Hyperparameter Grid
        param_grid = {
            'n_estimators': [100, 300, 500, 800, 1000],
            'learning_rate': [0.005, 0.01, 0.03, 0.05, 0.1],
            'max_depth': [3, 5, 6, 7, 9],
            'subsample': [0.6, 0.7, 0.8, 0.9],
            'colsample_bytree': [0.6, 0.7, 0.8, 0.9],
            'reg_alpha': [0, 0.01, 0.1, 1],
            'reg_lambda': [0, 0.01, 0.1, 1]
        }
        
        if self.model_type == 'xgboost':
            estimator_cls = xgb.XGBRegressor
            base_params = {'objective': 'reg:squarederror', 'n_jobs': 1}
        elif self.model_type == 'lightgbm':
            estimator_cls = lgb.LGBMRegressor
            base_params = {'n_jobs': 1, 'verbose': -1}
        elif self.model_type == 'rf':
            # RF usually doesn't need as much tuning or has different params, but let's allow it
            estimator_cls = RandomForestRegressor
            base_params = {'n_jobs': -1}
            # Adjust param grid for RF? For now, we reuse the grid which might have XGB specific params like colsample_bytree
            # Ideally we should have separate grids.
            # Let's handle RF simply or skip optimized for RF in this quick impl?
            # Let's just create a generic grid or handle separately.
            pass
            
        if self.model_type in ['xgboost', 'lightgbm']:
            print(f"Tuning GHI Residual Model ({self.model_type}, n_iter={n_iter})...")
            est_ghi = estimator_cls(**base_params)
            search_ghi = RandomizedSearchCV(estimator=est_ghi, param_distributions=param_grid, n_iter=n_iter, scoring='neg_mean_absolute_error', cv=3, verbose=1, random_state=42)
            search_ghi.fit(X, y_ghi_res)
            self.model_ghi = search_ghi.best_estimator_
            
            print(f"Tuning DNI Residual Model ({self.model_type}, n_iter={n_iter})...")
            est_dni = estimator_cls(**base_params)
            search_dni = RandomizedSearchCV(estimator=est_dni, param_distributions=param_grid, n_iter=n_iter, scoring='neg_mean_absolute_error', cv=3, verbose=1, random_state=42)
            search_dni.fit(X, y_dni_res)
            self.model_dni = search_dni.best_estimator_

        elif self.model_type == 'rf':
             # Simple RF grid
             rf_grid = {
                 'n_estimators': [100, 200, 300],
                 'max_depth': [5, 10, 15, None],
                 'min_samples_split': [2, 5, 10]
             }
             print(f"Tuning GHI Model (Random Forest, n_iter={n_iter})...")
             est_ghi = RandomForestRegressor(n_jobs=1)
             search_ghi = RandomizedSearchCV(estimator=est_ghi, param_distributions=rf_grid, n_iter=n_iter, scoring='neg_root_mean_squared_error', cv=3, verbose=1, random_state=42)
             search_ghi.fit(X, y_ghi_res)
             self.model_ghi = search_ghi.best_estimator_
             
             print(f"Tuning DNI Model (Random Forest, n_iter={n_iter})...")
             est_dni = RandomForestRegressor(n_jobs=1)
             search_dni = RandomizedSearchCV(estimator=est_dni, param_distributions=rf_grid, n_iter=n_iter, scoring='neg_root_mean_squared_error', cv=3, verbose=1, random_state=42)
             search_dni.fit(X, y_dni_res)
             self.model_dni = search_dni.best_estimator_
        
        self.save_models()
        print("Optimized models saved.")
        
    def save_models(self):
        joblib.dump(self.model_ghi, self.model_path_ghi)
        joblib.dump(self.model_dni, self.model_path_dni)
        
    def load_models(self):
        if os.path.exists(self.model_path_ghi):
            self.model_ghi = joblib.load(self.model_path_ghi)
        if os.path.exists(self.model_path_dni):
            self.model_dni = joblib.load(self.model_path_dni)
            
    def predict(self, df, max_correction_ratio=1.6):
        """
        Applies correction to new data.
        Returns DataFrame with 'ghi_corrected' and 'dni_corrected'.
        
        Args:
            df: Input DataFrame with satellite data
            max_correction_ratio: Optional. Default 1.6 (allows +60% correction).
                                  NASA POWER often under-reports by 30-50% in West Africa.
        """
        if not self.model_ghi or not self.model_dni:
            self.load_models()
            
        features = [
            'ghi_satellite', 'dni_satellite', 'dhi_satellite', 
            'temp_air', 'relative_humidity', 'wind_speed', 
            'hour', 'month',
            'pm25', 'albedo',
            'dist_to_coast_km', 'elevation_m', 'climate_zone'
        ]
        
        # Ensure features exist or are correct
        for f in features:
            # Force recalculation of time features to ensure correct types (int)
            if f == 'hour': 
                if 'timestamp' in df.columns:
                    df['hour'] = pd.to_datetime(df['timestamp']).dt.hour.astype(int)
                else:
                    df['hour'] = 12 # Fallback
            
            if f == 'month':
                if 'timestamp' in df.columns:
                    df['month'] = pd.to_datetime(df['timestamp']).dt.month.astype(int)
                else:
                    df['month'] = 6 # Fallback

            if f == 'pm25' and f not in df.columns: df['pm25'] = 25.0
            if f == 'albedo' and f not in df.columns: df['albedo'] = 0.2
            
            # Ensure types
            if f in ['pm25', 'albedo', 'dist_to_coast_km', 'elevation_m', 'weather_loss']:
                 if f in df.columns:
                      df[f] = pd.to_numeric(df[f], errors='coerce').fillna(0.0)
                 
            # Climate Proxies
            if f in ['dist_to_coast_km', 'elevation_m', 'climate_zone']:
                      # We need lat/lon to compute proxies if they aren't provided
                      lat = df['latitude'].iloc[0] if 'latitude' in df.columns else 5.6
                      lon = df['longitude'].iloc[0] if 'longitude' in df.columns else -0.2
                      dist, elev, zone = self._get_proxies(lat, lon)
                      df['dist_to_coast_km'] = dist
                      df['elevation_m'] = elev
                      df['climate_zone'] = zone
        
        X = df[features]
        
        df_out = df.copy()
        
        # Get predicted residuals
        ghi_res_pred = self.model_ghi.predict(X)
        dni_res_pred = self.model_dni.predict(X)
        
        ghi_satellite = df['ghi_satellite'].values
        dni_satellite = df['dni_satellite'].values
        
        # Apply additive residual
        # Corrected = Satellite + PredictedResidual
        ghi_ml_corrected = ghi_satellite + ghi_res_pred
        dni_ml_corrected = dni_satellite + dni_res_pred
        
        import numpy as np
        
        if max_correction_ratio is not None:
            # Shift from ratio cap to absolute bounds logic
            # We still use max_correction_ratio to define a "reasonable" upper limit
            ghi_max = np.maximum(ghi_satellite * max_correction_ratio, 120.0) # Higher twilight floor
            dni_max = np.maximum(dni_satellite * max_correction_ratio, 250.0) # DNI can be very high even in twilight
            
            # Clamp to prevent night predictions from exploding and safety upper bound
            is_night = (df['hour'] < 5) | (df['hour'] > 19)
            
            ghi_corrected = np.where(is_night, 0.0, np.clip(ghi_ml_corrected, 0.0, ghi_max))
            dni_corrected = np.where(is_night, 0.0, np.clip(dni_ml_corrected, 0.0, dni_max))
        else:
            ghi_corrected = ghi_ml_corrected
            dni_corrected = dni_ml_corrected
        
        df_out['ghi_corrected'] = ghi_corrected
        df_out['dni_corrected'] = dni_corrected
        
        df_out['ghi_corrected'] = df_out['ghi_corrected'].clip(lower=0)
        df_out['dni_corrected'] = df_out['dni_corrected'].clip(lower=0)
        
        # Automatic Regional Calibration (post-ML correction)
        df_out = self.apply_calibration(df_out)
        
        return df_out
    def apply_calibration(self, df, location_id=None):
        """
        Applies scientific calibration to align Satellite data with ground-truth and GSA.
        Focuses on Aerosol (Harmattan) and Coastal (Mist/Salt) attenuation.
        """
        # 1. Scientific Harmattan Calibration (North of 5°N)
        # Based on NASA MERRA-2 AOD benchmarks for West Africa.
        # Attenuation increases with Latitude due to Saharan dust proximity.
        if 'latitude' in df.columns:
             lats = df['latitude']
             
             # A. AOD-based fallback if MERRA-2 data is provided in DF
             if 'aod_550' in df.columns and df['aod_550'].notna().any():
                  # Use AOD directly for a more scientific scaling
                  # High AOD (1.5) -> -12% attenuation
                  # Low AOD (0.2) -> 0%
                  # Fill NaNs with a base AOD of 0.2 (Clear sky)
                  aod = df['aod_550'].fillna(0.2).clip(0.2, 1.5)
                  attenuation = (aod - 0.2) / 1.3 * 0.12
                  df['ghi_corrected'] *= (1.0 - attenuation)
                  df['dni_corrected'] *= (1.0 - attenuation)
                  print(f"Applying AOD-driven attenuation (Mean: {attenuation.mean()*100:.1f}%)...")
             else:
                  # B. Latitude-driven proxy (Linear model for West Africa)
                  # 5°N (Coast) -> 0% penalty
                  # 14°N (Sahel/Burkina) -> -16% penalty (Matches GSA 2023 divergence)
                  penalty_rate = (lats - 5.0).clip(0, 10).map(lambda x: x * 0.018) # ~1.8% per deg
                  
                  if (penalty_rate > 0).any():
                       df['ghi_corrected'] *= (1.0 - penalty_rate)
                       df['dni_corrected'] *= (1.0 - penalty_rate)
                       print(f"Applying Latitude-driven proxy calibration (Max: {penalty_rate.max()*100:.1f}%)...")

        # 2. Coastal Boundary Layer Calibration
        # Scientific Basis: Salt aerosols and high humidity mist cause Rayleigh/Mie scattering 
        # that satellites over-predict.
        if 'dist_to_coast_km' in df.columns:
             dist = df['dist_to_coast_km']
             
             # Exponential decay of coastal influence
             # Factor = BasePenalty * exp(-dist / DecayConstant)
             # BasePenalty: 14% (Immediate shoreline - Axim/Monrovia)
             # DecayConstant: 12km (Sharper drop-off than inland aerosols)
             coastal_penalty = 0.14 * np.exp(-dist / 12.0)
             
             if (coastal_penalty > 0.01).any():
                  df['ghi_corrected'] *= (1.0 - coastal_penalty)
                  df['dni_corrected'] *= (1.0 - coastal_penalty)
                  print(f"Applying Coastal influence calibration (Max: {coastal_penalty.max()*100:.1f}%)...")
                  
        # 3. Physics Alignment (Global)
        # We ensure no negative values and reasonable clipping
        df['ghi_corrected'] = df['ghi_corrected'].clip(lower=0)
        df['dni_corrected'] = df['dni_corrected'].clip(lower=0)
        
        print("Layer 1: Scientific Calibration Applied.")
        return df


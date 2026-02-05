import sys
import os
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.physics_model import PhysicsLayer

def check_relative_yields():
    print("Running Comparative Analysis (2024)...")
    
    engine = init_db('solar_platform.db')
    session = get_session(engine)
    
    # Locations to check
    # Note: We need to ensure we have 2024 data for all. 
    # We ingested Techiman/Kumasi 2024. We assume Bolga 2024 exists or we ingest it.
    # Let's ingest Bolga 2024 first in the script if missing? 
    # Better to assume user flow or just try.
    
    targets = ['Bolgatanga', 'Techiman', 'Kumasi', 'Accra']
    
    weather_layer = WeatherCorrectionLayer(model_type='lightgbm')
    env_layer = EnvironmentalLayer(rain_threshold_mm=1.0) 
    physics_layer = PhysicsLayer()
    
    results = []
    
    for name in targets:
        loc = session.query(Location).filter(Location.name.like(f'%{name}%')).first()
        if not loc:
            print(f"Skipping {name} (Not found in DB)")
            continue
            
        # Fetch Data
        query = session.query(WeatherData).filter(
            WeatherData.location_id == loc.id,
            WeatherData.timestamp >= datetime(2024, 1, 1),
            WeatherData.timestamp < datetime(2025, 1, 1)
        )
        data = query.all()
        count = len(data)
        
        if count < 8700: # Allow slight missing
            print(f"Skipping {name} (Insufficient Data: {count})")
            continue
            
        print(f"Simulating {name} ({count} records)...")
        
        df = pd.DataFrame([d.__dict__ for d in data])
        if '_sa_instance_state' in df.columns:
             df = df.drop('_sa_instance_state', axis=1)
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        
        df['latitude'] = loc.latitude
        df['longitude'] = loc.longitude
        
        # Defaults
        if 'pm25' not in df.columns or df['pm25'].isnull().all(): df['pm25'] = 25.0
        if 'albedo' not in df.columns or df['albedo'].isnull().all(): df['albedo'] = 0.2
        
        df['hour'] = df.index.hour
        df['month'] = df.index.month
        
        # 1. Weather Correction (Check GHI bias)
        df_corr = weather_layer.predict(df)
        
        ghi_sat_sum = df_corr['ghi_satellite'].sum()
        ghi_corr_sum = df_corr['ghi_corrected'].sum()
        correction_ratio = ghi_corr_sum / ghi_sat_sum
        
        # 2. Env
        if 'rain_mm' not in df_corr.columns: df_corr['rain_mm'] = 0.0
        df_env = env_layer.process(df_corr)
        
        # 3. Physics
        sim = physics_layer.simulate(df_env, loc.latitude, loc.longitude, 1.0, 10, 180)
        yield_val = sim['annual_energy_kwh']
        
        results.append({
            'Location': name,
            'Lat': loc.latitude,
            'GHI_Sat_Annual': ghi_sat_sum / 1000.0,
            'GHI_Corr_Annual': ghi_corr_sum / 1000.0,
            'Correction_Factor': correction_ratio,
            'Yield_kWh_kWp': yield_val
        })
        
    # Display
    res_df = pd.DataFrame(results).sort_values('Lat', ascending=False) # North to South
    print("\n" + "="*80)
    print("COMPARATIVE YIELDS 2024 (North -> South)")
    print("="*80)
    print(res_df.to_string(index=False, float_format="%.2f"))
    print("="*80)

if __name__ == "__main__":
    check_relative_yields()

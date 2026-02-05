import sys
import os
import pandas as pd
from sqlalchemy.orm import Session
from datetime import datetime

# Add parent directory to path to import core modules
sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.physics_model import PhysicsLayer

def predict_techiman():
    print("Running Yield Prediction for Techiman (2024)...")
    
    # Init DB
    engine = init_db('solar_platform.db')
    session = get_session(engine)
    
    # Find Techiman
    loc = session.query(Location).filter(Location.name.like('%Techiman%')).first()
    if not loc:
        print("Error: Techiman location not found in DB.")
        return

    print(f"Target Location: {loc.name} (ID: {loc.id}, Lat: {loc.latitude}, Lon: {loc.longitude})")
    
    # Init Layers
    # Using LightGBM and Tuned Environmental Layer
    weather_layer = WeatherCorrectionLayer(model_type='lightgbm')
    env_layer = EnvironmentalLayer(rain_threshold_mm=1.0) 
    physics_layer = PhysicsLayer()
    
    # 1. Fetch Data
    query = session.query(WeatherData).filter(
        WeatherData.location_id == loc.id,
        WeatherData.timestamp >= datetime(2024, 1, 1),
        WeatherData.timestamp < datetime(2025, 1, 1)
    )
    data = query.all()
    
    if not data:
        print("No data found for Techiman in 2023.")
        return
        
    print(f"Loaded {len(data)} hourly records.")
    
    # Convert to DataFrame
    df = pd.DataFrame([d.__dict__ for d in data])
    if '_sa_instance_state' in df.columns:
        df = df.drop('_sa_instance_state', axis=1)
        
    # Ensure Timestamp Index
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    # Add Location Cols
    df['latitude'] = loc.latitude
    df['longitude'] = loc.longitude
    
    # Fill Defaults
    if 'pm25' not in df.columns or df['pm25'].isnull().all():
         df['pm25'] = 25.0
    if 'albedo' not in df.columns or df['albedo'].isnull().all():
         df['albedo'] = 0.2
         
    # Feature Engineering
    df['hour'] = df.index.hour
    df['month'] = df.index.month

    # 2. Weather Correction
    print("Applying Weather Correction (ML Model)...")
    df_corrected = weather_layer.predict(df)
    
    # 3. Environmental Losses
    print("Applying Environmental Losses (Dust/Rain)...")
    if 'rain_mm' not in df_corrected.columns:
        df_corrected['rain_mm'] = 0.0
        
    df_env = env_layer.process(df_corrected, system_start_date=data[0].timestamp)
    
    # 4. Physics Simulation
    print("Running Physics Simulation (1 kWp System)...")
    sim_result = physics_layer.simulate(
        weather_df=df_env,
        lat=loc.latitude,
        lon=loc.longitude,
        system_capacity_kw=1.0, 
        tilt=10, 
        azimuth=180 
    )
    
    annual_energy = sim_result['annual_energy_kwh']
    specific_yield = annual_energy / 1.0 # kWh/kWp
    
    print("\n" + "="*40)
    print("PREDICTION RESULTS: TECHIMAN")
    print("="*40)
    print(f"Location:       {loc.name}")
    print(f"Coordinates:    {loc.latitude}, {loc.longitude}")
    print(f"Year:           2024")
    print("-" * 40)
    print(f"Annual Yield:   {specific_yield:.2f} kWh/kWp")
    print("="*40)
    
    # Monthly Breakdown
    print("\nMonthly Yield (kWh/kWp):")
    monthly = sim_result['ac_series'].resample('ME').sum() / 1000.0
    print(monthly)

if __name__ == "__main__":
    predict_techiman()

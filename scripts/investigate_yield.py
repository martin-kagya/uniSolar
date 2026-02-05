
import pandas as pd
import sys
import os
import numpy as np

# Ensure core is in path
sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer

def simulate_location(loc_id, name):
    print(f"\n--- Simulating {name} (ID: {loc_id}) ---")
    engine = init_db()
    session = get_session(engine)
    
    # 1. Load Data
    loc = session.get(Location, loc_id)
    recs = session.query(WeatherData).filter_by(location_id=loc_id).all()
    df = pd.DataFrame([r.__dict__ for r in recs])
    
    if df.empty:
        print(f"No weather data for {name}")
        return None
        
    df['latitude'] = loc.latitude
    df['longitude'] = loc.longitude
        
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    # Feature Engineering (Minimal)
    for col in ['hour', 'month']:
        if col not in df.columns:
            if col == 'hour': df['hour'] = df['timestamp'].dt.hour
            if col == 'month': df['month'] = df['timestamp'].dt.month
            
    df['pm25'] = pd.to_numeric(df.get('pm25', 25.0), errors='coerce').fillna(25.0)
    df['albedo'] = 0.20
    
    # 2. Weather Correction (L1)
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    df_l1 = l1.predict(df)
    
    # APPLY CALIBRATION
    df_l1 = l1.apply_calibration(df_l1, location_id=loc_id)
    
    # 3. Environmental (L2)
    l2 = EnvironmentalLayer()
    df_l2 = l2.process(df_l1)
    
    # 4. Physics (L3)
    l3 = PhysicsLayer()
    capacity_kw = 1.0 # Simulate 1kW system for Specific Yield directly
    
    # Run Simulation
    # Note: PhysicsLayer expects index to be timestamp
    df_l3_input = df_l2.copy()
    df_l3_input = df_l3_input.set_index('timestamp')
    
    res = l3.simulate(df_l3_input, lat=loc.latitude, lon=loc.longitude, system_capacity_kw=capacity_kw, tilt=10, azimuth=180)
    
    
    # Calculate duration
    duration_days = (df['timestamp'].max() - df['timestamp'].min()).days
    if duration_days < 1: duration_days = 1 # Avoid div by zero for tiny tests
    years = duration_days / 365.25
    
    # Metrics
    total_energy_kwh = res['annual_energy_kwh']
    specific_yield_total = total_energy_kwh / capacity_kw
    specific_yield_annual = specific_yield_total / years
    
    # Analysis
    avg_ghi = df_l1['ghi_corrected'].mean()
    avg_temp = df_l1['temp_air'].mean()
    avg_soiling = df_l2['soiling_loss'].mean()
    
    print(f"Results for {name}:")
    print(f"  Duration: {years:.2f} years")
    print(f"  Total Energy: {total_energy_kwh:.2f} kWh")
    print(f"  Specific Yield (Annualized): {specific_yield_annual:.2f} kWh/kWp/yr")
    print(f"  Avg GHI (Corrected): {avg_ghi:.2f} W/m2 ({avg_ghi*8.76:.2f} kWh/m2/yr)")
    print(f"  Avg Ambient Temp: {avg_temp:.2f} C")
    print(f"  Avg Soiling Loss: {avg_soiling:.2%}")
    
    session.close()
    return {
        'name': name,
        'specific_yield_annual': specific_yield_annual,
        'ghi_kwh_m2': avg_ghi * 8.76,
        'temp_avg': avg_temp,
        'soiling_avg': avg_soiling,
        'duration_years': years
    }

def main():
    locations = [(2, 'Bolgatanga'), (7, 'Axim')]
    results = []
    
    for loc_id, name in locations:
        res = simulate_location(loc_id, name)
        if res:
            results.append(res)
            
    if len(results) == 2:
        bolga = results[0]
        axim = results[1]
        
        print("\n--- Comparison ---")
        diff_yield = bolga['specific_yield_annual'] - axim['specific_yield_annual']
        pct_diff = (diff_yield / axim['specific_yield_annual']) * 100
        
        print(f"Annualized Yield Difference (Bolgatanga - Axim): {diff_yield:.2f} kWh/kWp ({pct_diff:.2f}%)")
        
        if diff_yield < 0:
            print("CONFIRMED: Bolgatanga has lower specific yield.")
        else:
            print("DISPROVED: Bolgatanga has higher specific yield.")
            
        # Analysis of Drivers
        print("\nDrivers:")
        print(f"  GHI: Bolga is {(bolga['ghi_kwh_m2']/axim['ghi_kwh_m2'] - 1)*100:.2f}% relative to Axim")
        print(f"  Temp: Bolga is {bolga['temp_avg'] - axim['temp_avg']:.2f} C hotter")
        print(f"  Soiling: Bolga has {bolga['soiling_avg'] - axim['soiling_avg']:.2%} more soiling")

if __name__ == "__main__":
    main()

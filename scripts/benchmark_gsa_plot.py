
import pandas as pd
import sys
import os
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

sys.path.insert(0, os.getcwd())

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer
from data.ingest_nasa import fetch_nasa_data, process_and_store

def run_benchmark():
    print("=" * 60)
    print("GSA BENCHMARK SUITE")
    print("=" * 60)
    
    # 1. Load Reference Data
    ref_df = pd.read_csv('data/gsa_reference.csv')
    print(f"Loaded {len(ref_df)} reference locations.")
    
    engine = init_db()
    session = get_session(engine)
    
    results = []
    
    # 2. Loop Through Locations
    for idx, row in ref_df.iterrows():
        name = row['name']
        lat = row['latitude']
        lon = row['longitude']
        gsa_yield = row['gsa_specific_yield']
        
        print(f"\n[{idx+1}/{len(ref_df)}] Processing {name}...")
        
        # A. Get Location ID (Create if needed)
        # Check fuzzy match on lat/lon or create new
        # We assume strict lat/lon for simplicity here
        loc = session.query(Location).filter_by(latitude=lat, longitude=lon).first()
        if not loc:
            loc = Location(name=name, latitude=lat, longitude=lon, 
                           dist_to_coast_km=row['dist_coast_km']) # Pre-fill from CSV if provided
            session.add(loc)
            session.commit()
        
        # B. Ensure Weather Data Exists (Fetch 2023 if missing)
        # Check if we have ~365 days of data for 2023
        count = session.query(WeatherData).filter(
            WeatherData.location_id == loc.id,
            WeatherData.timestamp >= datetime(2023, 1, 1),
            WeatherData.timestamp <= datetime(2023, 12, 31)
        ).count()
        
        if count < 8000:
            print("  Fetching NASA data for 2023...")
            raw_data = fetch_nasa_data(lat, lon, 2023)
            if raw_data:
                process_and_store(session, loc.id, raw_data, 2023)
        else:
            print("  Weather data available.")
            
        # C. Run Simulation Pipeline
        query = session.query(WeatherData).filter(
            WeatherData.location_id == loc.id,
            WeatherData.timestamp >= datetime(2023, 1, 1),
            WeatherData.timestamp <= datetime(2023, 12, 31)
        )
        data = [r.__dict__ for r in query.all()]
        if not data:
             print("  NO DATA found. Skipping.")
             continue
             
        df = pd.DataFrame(data)
        
        # Add required cols if missing
        df['latitude'] = lat
        df['longitude'] = lon
        df['dist_to_coast_km'] = row['dist_coast_km'] # Use the CSV value to be sure about validation
        
        for col in ['pm25', 'albedo']:
             if col not in df.columns: df[col] = 0.0 # defaults handled in model
        
        # L1: Weather (with calibration)
        l1 = WeatherCorrectionLayer(model_type='xgboost')
        l1.load_models() # Make sure models exist
        df_l1 = l1.predict(df) 
        
        # L2: Environmental
        l2 = EnvironmentalLayer()
        df_l2 = l2.process(df_l1)
        
        # L3: Physics
        l3 = PhysicsLayer()
        # Simulate 1kW system
        df_l3 = df_l2.set_index('timestamp')
        res = l3.simulate(df_l3, lat=lat, lon=lon, system_capacity_kw=1.0)
        
        sim_yield = res['annual_energy_kwh']
        
        # D. Store Result
        diff = sim_yield - gsa_yield
        pct_diff = (diff / gsa_yield) * 100
        
        print(f"  GSA: {gsa_yield:.0f}, Sim: {sim_yield:.0f} ({pct_diff:+.1f}%)")
        
        results.append({
            'name': name,
            'gsa_yield': gsa_yield,
            'sim_yield': sim_yield,
            'pct_diff': pct_diff
        })
        
    session.close()
    
    # 3. Plotting
    if not results: return
    
    res_df = pd.DataFrame(results)
    
    plt.figure(figsize=(12, 6))
    
    x = np.arange(len(res_df))
    width = 0.35
    
    fig, ax = plt.subplots(figsize=(12, 6))
    rects1 = ax.bar(x - width/2, res_df['gsa_yield'], width, label='Global Solar Atlas', color='gray', alpha=0.6)
    rects2 = ax.bar(x + width/2, res_df['sim_yield'], width, label='UniSolar Model', color='#007acc')
    
    # Add labels
    ax.set_ylabel('Specific Yield (kWh/kWp)')
    ax.set_title('Benchmarking UniSolar vs Global Solar Atlas (Ghana)')
    ax.set_xticks(x)
    ax.set_xticklabels(res_df['name'])
    ax.legend()
    
    # Add error annotations
    for i, row in res_df.iterrows():
        height = max(row['gsa_yield'], row['sim_yield'])
        ax.annotate(f"{row['pct_diff']:+.1f}%",
                    xy=(i, height),
                    xytext=(0, 3),  # 3 points vertical offset
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=9, fontweight='bold',
                    color='green' if abs(row['pct_diff']) < 5 else 'red')
    
    plt.tight_layout()
    plt.savefig('reports/gsa_benchmark.png')
    print("\nBenchmark Plot saved to reports/gsa_benchmark.png")
    
    # Text Report
    print(res_df[['name', 'gsa_yield', 'sim_yield', 'pct_diff']].to_string())

if __name__ == "__main__":
    run_benchmark()

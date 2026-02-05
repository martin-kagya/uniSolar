#!/usr/bin/env python3
"""
Validation script for Wayokope location.
Compares monthly simulated energy vs validation data (minute resolution).
Filters to solar elevation > 0 (daylight hours only).
"""

import pandas as pd
import numpy as np
import pvlib
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer

LOCATION_ID = 8

def main():
    # Load validation data
    val = pd.read_excel('data/Full Dataset.xlsx')
    val['Date_Time'] = pd.to_datetime(val['Date_Time'])
    val = val.sort_values('Date_Time')
    capacity_kw = float(val['Nominal Power (kW)'].astype(float).max())
    
    print("="*60)
    print("WAYOKOPE VALIDATION REPORT")
    print("="*60)
    print(f"Location ID: {LOCATION_ID}")
    print(f"System Capacity: {capacity_kw} kW")
    print(f"Validation Period: {val['Date_Time'].min()} to {val['Date_Time'].max()}")
    print()
    
    # Load location
    engine = init_db()
    session = get_session(engine)
    loc = session.query(Location).get(LOCATION_ID)
    lat, lon = loc.latitude, loc.longitude
    print(f"Coordinates: {lat:.6f}°N, {lon:.6f}°E")
    print()
    
    # Validation: minute kW -> kWh, filter to solar elevation > 0
    p_kw = val.set_index('Date_Time')['Generated Power (kW)'].astype(float)
    val_kwh = (p_kw * (1/60.0)).rename('kwh')
    
    # Use actual solar elevation to determine daylight
    val_hourly_idx = val_kwh.resample('h').mean().index
    solpos = pvlib.solarposition.get_solarposition(val_hourly_idx, lat, lon)
    sun_up = solpos['elevation'] > 0
    val_hourly_sun = pd.Series(sun_up.values, index=val_hourly_idx)
    val_minute_sun = val_hourly_sun.reindex(val_kwh.index, method='ffill')
    val_daylight = val_kwh[val_minute_sun]
    val_monthly = val_daylight.resample('ME').sum().rename('val_kwh')
    
    print(f"Validation data points (all): {len(val_kwh):,} minutes")
    print(f"Validation data points (solar elevation > 0): {len(val_daylight):,} minutes")
    print()
    
    # Load DB weather and run pipeline
    print("Running full simulation pipeline...")
    recs = session.query(WeatherData).filter_by(location_id=LOCATION_ID).all()
    df = pd.DataFrame([r.__dict__ for r in recs])
    if '_sa_instance_state' in df.columns:
        df = df.drop('_sa_instance_state', axis=1)
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    # Feature engineering
    if 'hour' not in df.columns:
        df['hour'] = df['timestamp'].dt.hour
    if 'month' not in df.columns:
        df['month'] = df['timestamp'].dt.month
    if 'pm25' in df.columns:
        df['pm25'] = pd.to_numeric(df['pm25'], errors='coerce').fillna(25.0)
    else:
        df['pm25'] = 25.0
    
    # Albedo
    if LOCATION_ID == 2:
        df['albedo'] = 0.25
    elif LOCATION_ID in [5, 6]:
        df['albedo'] = 0.20
    else:
        df['albedo'] = 0.18
    
    # Layer 1: Weather Correction
    print("  Layer 1: Weather Correction (LightGBM)...")
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    df1 = l1.predict(df)
    
    # Layer 2: Environmental Losses
    print("  Layer 2: Environmental Losses...")
    l2 = EnvironmentalLayer(rain_threshold_mm=0.5, degradation_rate=0.005)
    df2 = l2.process(df1, system_start_date=df1['timestamp'].min())
    
    # Layer 3: Physics Simulation
    print("  Layer 3: Physics Simulation...")
    df2['timestamp'] = pd.to_datetime(df2['timestamp'])
    df2 = df2.set_index('timestamp')
    
    l3 = PhysicsLayer()
    res = l3.simulate(df2, lat=lat, lon=lon, system_capacity_kw=capacity_kw, tilt=10, azimuth=180)
    
    # Filter simulated to solar elevation > 0
    sim_kwh_hourly = (res['ac_series'] / 1000.0).rename('kwh')
    solpos_sim = pvlib.solarposition.get_solarposition(sim_kwh_hourly.index, lat, lon)
    sim_daylight = sim_kwh_hourly[solpos_sim['elevation'] > 0]
    sim_monthly = sim_daylight.resample('ME').sum().rename('sim_kwh')
    
    print(f"Simulated hours (all): {len(sim_kwh_hourly):,}")
    print(f"Simulated hours (solar elevation > 0): {len(sim_daylight):,}")
    print()
    
    # Compare monthly
    m = pd.concat([sim_monthly, val_monthly], axis=1).dropna()
    
    m['error_kwh'] = m['sim_kwh'] - m['val_kwh']
    m['abs_error_kwh'] = m['error_kwh'].abs()
    m['pct_error'] = (m['error_kwh'] / m['val_kwh'] * 100).where(m['val_kwh'] > 0)
    
    # Metrics
    rmse = float(np.sqrt(np.mean(m['error_kwh']**2)))
    mae = float(np.mean(m['abs_error_kwh']))
    mbe = float(np.mean(m['error_kwh']))
    
    nonzero = m['val_kwh'] > 0
    mape = float(np.mean(np.abs(m.loc[nonzero, 'error_kwh']) / m.loc[nonzero, 'val_kwh'])) if nonzero.any() else float('nan')
    
    # Scaling factor
    total_sim = m['sim_kwh'].sum()
    total_val = m['val_kwh'].sum()
    scale_factor = total_val / total_sim if total_sim > 0 else float('nan')
    
    print("="*60)
    print("MONTHLY COMPARISON (kWh) - SOLAR HOURS ONLY")
    print("="*60)
    print(f"{'Month':<12} {'Simulated':>12} {'Validation':>12} {'Error':>12} {'% Error':>10}")
    print("-"*60)
    for idx, row in m.iterrows():
        month_name = idx.strftime('%Y-%m')
        pct = row['pct_error'] if not pd.isna(row['pct_error']) else 0
        print(f"{month_name:<12} {row['sim_kwh']:>12.2f} {row['val_kwh']:>12.2f} {row['error_kwh']:>12.2f} {pct:>9.1f}%")
    
    print("-"*60)
    print(f"{'TOTAL':<12} {total_sim:>12.2f} {total_val:>12.2f} {(total_sim-total_val):>12.2f} {(scale_factor-1)*100:>9.1f}%")
    print()
    
    print("="*60)
    print("ERROR METRICS")
    print("="*60)
    print(f"RMSE (kWh/month):     {rmse:>10.2f}")
    print(f"MAE  (kWh/month):     {mae:>10.2f}")
    print(f"MBE  (kWh/month):     {mbe:>10.2f}  (bias)")
    print(f"MAPE:                 {mape*100:>9.2f}%")
    print(f"Scaling Factor:       {scale_factor:>10.3f}  (model predicts {1/scale_factor:.2f}x too high)")
    print()
    
    # Rating
    if np.isnan(mape):
        rating = 'Unknown'
        rating_num = 0
    elif mape < 0.10:
        rating = 'Excellent'
        rating_num = 5
    elif mape < 0.20:
        rating = 'Good'
        rating_num = 4
    elif mape < 0.35:
        rating = 'Fair'
        rating_num = 3
    elif mape < 0.50:
        rating = 'Poor'
        rating_num = 2
    else:
        rating = 'Very Poor'
        rating_num = 1
    
    print("="*60)
    print("RATING")
    print("="*60)
    print(f"Overall Rating: {rating} ({rating_num}/5)")
    print()
    print("Interpretation:")
    if rating_num >= 4:
        print("  Model performs well for this location.")
    elif rating_num == 3:
        print("  Model performance is acceptable but could be improved.")
    elif rating_num == 2:
        print("  Model has significant errors. Review system parameters and model assumptions.")
    else:
        print("  Model has major systematic errors. Likely issues:")
        print("    - System capacity mismatch")
        print("    - Unmodeled losses (curtailment, outages, soiling)")
        print("    - Incorrect system configuration (tilt, azimuth)")
        print("    - Model not calibrated for this location/system type")
    
    session.close()
    
    return {
        'rmse': rmse,
        'mae': mae,
        'mbe': mbe,
        'mape': mape,
        'rating': rating,
        'rating_num': rating_num,
        'scale_factor': scale_factor,
        'monthly_data': m
    }

if __name__ == "__main__":
    results = main()

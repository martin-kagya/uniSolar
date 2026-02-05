import pandas as pd
import numpy as np
from core.layers.physics_model import PhysicsLayer
from datetime import datetime

def debug_physics():
    physics = PhysicsLayer()
    
    # Create dummy weather for 1 day
    times = pd.date_range('2023-01-01', periods=24, freq='h')
    df = pd.DataFrame(index=times)
    df['ghi_corrected'] = [0,0,0,0,0,10,100,300,500,700,800,900,900,800,700,500,300,100,10,0,0,0,0,0]
    df['dni_corrected'] = [0,0,0,0,0,50,200,500,700,800,850,900,900,850,800,700,500,200,50,0,0,0,0,0]
    df['dhi_satellite'] = df['ghi_corrected'] * 0.2
    df['temp_air'] = 25.0
    df['wind_speed'] = 2.0
    df['environmental_loss_factor'] = 1.0
    
    lat, lon = 6.669085, -1.568097
    
    print(f"Running Debug Simulation for {lat}, {lon}...")
    try:
        result = physics.simulate(df, lat, lon, system_capacity_kw=10.0, tilt=15, azimuth=180)
        print(f"Annual Energy: {result['annual_energy_kwh']:.2f} kWh")
        print("AC Output Head:")
        print(result['ac_series'].head())
    except Exception as e:
        print(f"Simulation FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_physics()

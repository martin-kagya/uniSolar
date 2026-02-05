import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core.layers.environmental_model import EnvironmentalLayer

def verify_layer2():
    print("Verifying Layer 2 (Environmental Model)...")
    
    # 1. Create Dummy Data (1 Year)
    dates = pd.date_range(start='2023-01-01', end='2023-12-31 23:00:00', freq='H')
    df = pd.DataFrame({'timestamp': dates})
    
    # Add random precipitable_water to simulate wet season (May-Oct)
    # Wet months: 5, 6, 7, 8, 9, 10
    df['precipitable_water'] = df['timestamp'].apply(
        lambda x: np.random.uniform(3, 8) if x.month in [5, 6, 7, 8, 9, 10] else np.random.uniform(0, 3)
    )
    
    # 2. Instantiate Model
    # Start degrading from 2023-01-01
    env_layer = EnvironmentalLayer(rain_threshold_mm=0.5, degradation_rate=0.01) # 1% per year for visibility
    
    # 3. Process
    print("Processing Data...")
    df_out = env_layer.process(df, system_start_date=datetime(2023, 1, 1))
    
    # 4. Check Results
    print("\nSample Results:")
    print(df_out[['timestamp', 'soiling_loss', 'degradation_factor']].sample(5).sort_values('timestamp'))
    
    # Check Soiling Accumulation (Dry Season vs Wet Season)
    jan_soiling = df_out[df_out['timestamp'].dt.month == 1]['soiling_loss'].mean()
    aug_soiling = df_out[df_out['timestamp'].dt.month == 8]['soiling_loss'].mean()
    
    print(f"\nAverage Soiling Loss (Jan - Harmattan/Dry): {jan_soiling:.4f}")
    print(f"Average Soiling Loss (Aug - Wet): {aug_soiling:.4f}")
    
    if jan_soiling > aug_soiling:
        print("PASS: Dry season soiling is higher than wet season.")
    else:
        print("WARNING: Wet season soiling is unexpectedly high. Check rain simulation.")

    # Check Degradation
    start_degrad = df_out.iloc[0]['degradation_factor']
    end_degrad = df_out.iloc[-1]['degradation_factor']
    
    print(f"\nDegradation Factor Start: {start_degrad:.5f}")
    print(f"Degradation Factor End (1 year later): {end_degrad:.5f}")
    
    expected_end = 1.0 - 0.01
    if abs(end_degrad - expected_end) < 0.001:
        print(f"PASS: Degradation is correct (approx {expected_end}).")
    else:
        print(f"FAIL: Degradation calculation off. Expected {expected_end}, got {end_degrad}")

if __name__ == "__main__":
    verify_layer2()

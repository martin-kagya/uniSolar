import sys
import os
sys.path.insert(0, os.getcwd())
import pandas as pd
import numpy as np
from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer

def compare_ghi():
    engine = init_db()
    session = get_session(engine)
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    
    for loc_id in [1, 2]:
        name = "Accra" if loc_id == 1 else "Bolgatanga"
        query = session.query(WeatherData).filter_by(location_id=loc_id)
        df = pd.DataFrame([d.__dict__ for d in query.all()])
        if '_sa_instance_state' in df.columns: df = df.drop('_sa_instance_state', axis=1)
        
        # Test 1: With current 1.25 cap
        df_l1 = l1.predict(df, max_correction_ratio=1.25)
        # Test 2: WITHOUT cap
        df_no_cap = l1.predict(df, max_correction_ratio=None)
        
        ground_avg = df_l1['ghi_ground'].mean()
        corr_avg = df_l1['ghi_corrected'].mean()
        no_cap_avg = df_no_cap['ghi_corrected'].mean()
        
        ground_dni = df_l1['dni_ground'].mean()
        corr_dni = df_l1['dni_corrected'].mean()
        
        print(f"\n--- {name} (ID: {loc_id}) ---")
        print(f"NASA GHI Avg:      {df_l1['ghi_satellite'].replace(-999,0).mean():.2f}")
        print(f"Ground GHI Avg:    {ground_avg:.2f}")
        print(f"Corrected GHI Avg: {corr_avg:.2f} (Bias: {corr_avg - ground_avg:+.2f})")
        print(f"No-Cap GHI Avg:    {no_cap_avg:.2f} (Bias: {no_cap_avg - ground_avg:+.2f})")
        print(f"Ground DNI Avg:    {ground_dni:.2f}")
        print(f"Corrected DNI Avg: {corr_dni:.2f} (Bias: {corr_dni - ground_dni:+.2f})")
    
    session.close()
    
    session.close()

if __name__ == "__main__":
    compare_ghi()

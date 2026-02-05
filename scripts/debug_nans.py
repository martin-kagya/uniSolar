import sys
import os
import pandas as pd
from sqlalchemy import func
sys.path.insert(0, os.getcwd())
from core.database import init_db, get_session, WeatherData
from core.layers.weather_model import WeatherCorrectionLayer

def check_nans():
    print("Checking for NaNs...")
    engine = init_db()
    session = get_session(engine)
    
    # Check Location 1 (Accra)
    print("Loading Accra data...")
    data = session.query(WeatherData).filter_by(location_id=1).all()
    df = pd.DataFrame([d.__dict__ for d in data])
    if '_sa_instance_state' in df.columns: df = df.drop('_sa_instance_state', axis=1)
    
    print(f"Total Rows: {len(df)}")
    print("NaN Counts in Inputs:")
    print(df[['ghi_satellite', 'dni_satellite', 'temp_air', 'wind_speed']].isna().sum())
    
    # Run Prediction
    print("\nRunning Prediction...")
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    
    df_pred = l1.predict(df)
    
    print("NaN Counts in Outputs:")
    print(df_pred[['ghi_corrected', 'dni_corrected']].isna().sum())
    
    # Check a sample of NaNs if any
    if df_pred['ghi_corrected'].isna().sum() > 0:
        print("\nSample row with NaN output:")
        print(df_pred[df_pred['ghi_corrected'].isna()].iloc[0])

    session.close()

if __name__ == "__main__":
    check_nans()

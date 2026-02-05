import sys
import os
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error
sys.path.insert(0, os.getcwd())
try:
    from core.layers.weather_model import WeatherCorrectionLayer
    from core.database import init_db, get_session
except ImportError:
    # Fallback to appending parent dir if run from scripts/
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from core.layers.weather_model import WeatherCorrectionLayer
    from core.database import init_db, get_session

def benchmark_model():
    print("Benchmarking Model Performance...")
    
    # Load Data
    engine = init_db()
    session = get_session(engine)
    layer1 = WeatherCorrectionLayer(model_type='lightgbm')
    
    try:
        print("Loading data...")
        df = layer1.load_data(session) # Loads all valid ground truth data
    except Exception as e:
        print(f"Error loading data: {e}")
        return
    finally:
        session.close()

    print(f"Data loaded: {len(df)} records.")

    # Get Predictions
    print("Running inference...")
    results = layer1.predict(df)
    
    # Clean NaNs
    initial_len = len(results)
    results = results.dropna(subset=['ghi_ground', 'ghi_satellite', 'ghi_corrected'])
    if len(results) < initial_len:
        print(f"Dropped {initial_len - len(results)} rows with NaN values.")
        
    if len(results) == 0:
        print("No valid data remaining after dropping NaNs.")
        return

    # Calculate Metrics
    def get_metrics(y_true, y_pred):
        mse = mean_squared_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_true, y_pred)
        return rmse, mae

    # 1. Baseline (NASA Satellite vs Ground Truth)
    base_rmse, base_mae = get_metrics(results['ghi_ground'], results['ghi_satellite'])
    
    # 2. Corrected (Model vs Ground Truth)
    corr_rmse, corr_mae = get_metrics(results['ghi_ground'], results['ghi_corrected'])
    
    # 3. Improvement
    imp_rmse = (base_rmse - corr_rmse) / base_rmse * 100
    imp_mae = (base_mae - corr_mae) / base_mae * 100
    
    print("\n" + "="*60)
    print("MODEL PERFORMANCE BENCHMARK")
    print("="*60)
    print(f"{'Metric':<15} {'Baseline (NASA)':<20} {'Corrected (Model)':<20} {'Improvement':<15}")
    print("-" * 75)
    print(f"{'RMSE (W/m²)':<15} {base_rmse:<20.2f} {corr_rmse:<20.2f} {imp_rmse:+.1f}%")
    print(f"{'MAE (W/m²)':<15} {base_mae:<20.2f} {corr_mae:<20.2f} {imp_mae:+.1f}%")
    print("="*60)
    
    # Context
    mean_ghi = results['ghi_ground'].mean()
    print(f"\nAverage Daytime GHI: {mean_ghi:.2f} W/m²")
    print(f"Relative RMSE (rRMSE): {corr_rmse / mean_ghi * 100:.1f}%")
    
    print("\nVERDICT:")
    if imp_rmse > 20:
        print("✅ EXCELLENT: Huge improvement (>20%). The model is correcting major biases.")
    elif imp_rmse > 10:
        print("✅ GOOD: Significant improvement (>10%). The model is adding value.")
    elif imp_rmse > 0:
        print("⚠️ MARGINAL: Slight improvement. The satellite data was already quite good.")
    else:
        print("❌ POOR: The model made it worse. Check for overfitting or data issues.")

if __name__ == "__main__":
    benchmark_model()

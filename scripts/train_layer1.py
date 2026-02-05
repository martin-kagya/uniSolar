from core.database import init_db, get_session, Location
from core.layers.weather_model import WeatherCorrectionLayer
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error
import argparse


def main():
    parser = argparse.ArgumentParser(description='Train Layer 1 Model')
    parser.add_argument('--model', type=str, default='lightgbm', choices=['xgboost', 'lightgbm', 'rf'],
                        help='Model type to train (xgboost, lightgbm, rf)')
    parser.add_argument('--iter', type=int, default=50, help='Number of iterations for hyperparameter tuning')
    parser.add_argument('--locations', type=str, default='all', 
                        help='Comma-separated location IDs to train on (e.g., "1,2") or "all" for all locations')
    args = parser.parse_args()

    print("Initializing Database...")
    engine = init_db()
    session = get_session(engine)
    
    print(f"Initializing WeatherCorrectionLayer with model_type='{args.model}'...")
    layer1 = WeatherCorrectionLayer(model_type=args.model)
    
    # Parse location filter
    location_id = None
    if args.locations != 'all':
        location_ids = [int(x.strip()) for x in args.locations.split(',')]
        if len(location_ids) == 1:
            location_id = location_ids[0]
    
    print("Loading Training Data (NASA Satellite → Solcast Ground Truth)...")
    try:
        df = layer1.load_data(session, location_id=location_id)
        print(f"Loaded {len(df)} records.")
        
        # Show per-location breakdown
        print("\n" + "="*70)
        print("TRAINING DATA BREAKDOWN")
        print("="*70)
        location_map = {}
        for loc in session.query(Location).all():
            location_map[loc.id] = loc.name
        
        for loc_id in df['location_id'].unique():
            count = len(df[df['location_id'] == loc_id])
            loc_name = location_map.get(loc_id, f"Location {loc_id}")
            print(f"{loc_name:20s}: {count:6d} records ({count/len(df)*100:.1f}%)")
        print("="*70)
        
        # Use Optimized Training with Tuning
        print(f"\nTraining multi-location model (n_iter={args.iter})...")
        layer1.train_optimized(df, n_iter=args.iter)
        
        
        # Calculate Overall Metrics
        print("\n" + "="*70)
        print("OVERALL MODEL PERFORMANCE")
        print("="*70)
        
        full_results = layer1.predict(df)
        
        mse_ghi = mean_squared_error(df['ghi_ground'], full_results['ghi_corrected'])
        rmse_ghi = np.sqrt(mse_ghi)
        mae_ghi = mean_absolute_error(df['ghi_ground'], full_results['ghi_corrected'])
        
        mse_dni = mean_squared_error(df['dni_ground'], full_results['dni_corrected'])
        rmse_dni = np.sqrt(mse_dni)
        mae_dni = mean_absolute_error(df['dni_ground'], full_results['dni_corrected'])
        
        print(f"GHI: RMSE={rmse_ghi:.2f} W/m², MAE={mae_ghi:.2f} W/m²")
        print(f"DNI: RMSE={rmse_dni:.2f} W/m², MAE={mae_dni:.2f} W/m²")
        
        # Per-Location Performance
        print("\n" + "="*70)
        print("PER-LOCATION PERFORMANCE")
        print("="*70)
        print(f"{'Location':<20s} {'GHI RMSE':>12s} {'GHI MAE':>12s} {'DNI RMSE':>12s}")
        print("-"*70)
        
        for loc_id in sorted(df['location_id'].unique()):
            loc_df = full_results[full_results['location_id'] == loc_id]
            loc_name = location_map.get(loc_id, f"Location {loc_id}")
            
            loc_rmse_ghi = np.sqrt(mean_squared_error(loc_df['ghi_ground'], loc_df['ghi_corrected']))
            loc_mae_ghi = mean_absolute_error(loc_df['ghi_ground'], loc_df['ghi_corrected'])
            loc_rmse_dni = np.sqrt(mean_squared_error(loc_df['dni_ground'], loc_df['dni_corrected']))
            
            print(f"{loc_name:<20s} {loc_rmse_ghi:>10.2f} W/m² {loc_mae_ghi:>10.2f} W/m² {loc_rmse_dni:>10.2f} W/m²")
        
        print("="*70)

        # Basic Verification
        print("\nSample Predictions:")
        predictions = full_results.sample(min(5, len(full_results)))
        
        cols = ['location_id', 'timestamp', 'ghi_satellite', 'ghi_ground', 'ghi_corrected']
        print(predictions[cols].to_string(index=False))
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == "__main__":
    main()

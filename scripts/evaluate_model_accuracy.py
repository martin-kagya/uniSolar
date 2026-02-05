"""
Evaluate model accuracy against Solcast ground truth data.
Calculates MSE, RMSE, MAE, and R-squared metrics.
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from core.database import init_db, get_session
from core.layers.weather_model import WeatherCorrectionLayer
import sys

def evaluate_model_accuracy(model_type='lightgbm'):
    """
    Evaluate the specified model against Solcast ground truth.
    
    Args:
        model_type: Model to evaluate ('lightgbm', 'xgboost', or 'rf')
    
    Returns:
        Dictionary with metrics: MSE, RMSE, MAE, R²
    """
    print(f"=" * 60)
    print(f"Evaluating {model_type.upper()} Model Accuracy vs Solcast Ground Truth")
    print(f"=" * 60)
    
    # Initialize database and model
    engine = init_db()
    session = get_session(engine)
    
    # Load weather correction layer
    layer = WeatherCorrectionLayer(model_type=model_type)
    
    # Load data with ground truth (Solcast)
    print("\nLoading data with Solcast ground truth...")
    df = layer.load_data(session, require_ground_truth=True)
    
    if df.empty:
        print("ERROR: No data with ground truth found!")
        print("Make sure you have ingested Solcast data using:")
        print("  python -m data.ingest_solcast <csv_path> <lat> <lon>")
        session.close()
        return None
    
    print(f"Loaded {len(df)} records with ground truth data")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Get model predictions
    print(f"\nRunning {model_type.upper()} predictions...")
    try:
        layer.load_models()
        pred_df = layer.predict(df)
    except Exception as e:
        print(f"ERROR: Failed to load or run model: {e}")
        print("Make sure the model is trained. Run:")
        print(f"  python -m scripts.train_layer1 --model {model_type}")
        session.close()
        return None
    
    # Extract actual and predicted values
    y_true = df['ghi_ground'].values
    y_pred = pred_df['ghi_corrected'].values
    
    # Calculate metrics
    print("\nCalculating metrics...")
    mse = mean_squared_error(y_true, y_pred)
    rmse = np.sqrt(mse)
    mae = mean_absolute_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    
    # Calculate baseline metrics (raw satellite vs ground truth)
    baseline_mse = mean_squared_error(y_true, df['ghi_satellite'].values)
    baseline_rmse = np.sqrt(baseline_mse)
    baseline_mae = mean_absolute_error(y_true, df['ghi_satellite'].values)
    baseline_r2 = r2_score(y_true, df['ghi_satellite'].values)
    
    # Calculate improvement
    rmse_improvement = ((baseline_rmse - rmse) / baseline_rmse) * 100
    mae_improvement = ((baseline_mae - mae) / baseline_mae) * 100
    r2_improvement = ((r2 - baseline_r2) / abs(baseline_r2)) * 100 if baseline_r2 != 0 else 0
    
    # Print results
    print("\n" + "=" * 60)
    print("RESULTS - MODEL ACCURACY METRICS")
    print("=" * 60)
    print(f"\n{model_type.upper()} Model Performance:")
    print(f"  MSE:        {mse:,.2f} (W/m²)²")
    print(f"  RMSE:       {rmse:,.2f} W/m²")
    print(f"  MAE:        {mae:,.2f} W/m²")
    print(f"  R-squared:  {r2:.4f}")
    
    print(f"\nBaseline (Raw Satellite) Performance:")
    print(f"  MSE:        {baseline_mse:,.2f} (W/m²)²")
    print(f"  RMSE:       {baseline_rmse:,.2f} W/m²")
    print(f"  MAE:        {baseline_mae:,.2f} W/m²")
    print(f"  R-squared:  {baseline_r2:.4f}")
    
    print(f"\nImprovement Over Baseline:")
    print(f"  RMSE:       {rmse_improvement:+.2f}%")
    print(f"  MAE:        {mae_improvement:+.2f}%")
    print(f"  R-squared:  {r2_improvement:+.2f}%")
    
    # Additional statistics
    print(f"\nData Statistics:")
    print(f"  Mean Ground Truth:     {np.mean(y_true):.2f} W/m²")
    print(f"  Std Ground Truth:      {np.std(y_true):.2f} W/m²")
    print(f"  Mean Predicted:        {np.mean(y_pred):.2f} W/m²")
    print(f"  Std Predicted:         {np.std(y_pred):.2f} W/m²")
    print(f"  Mean Absolute Error %: {(mae / np.mean(y_true)) * 100:.2f}%")
    
    print("\n" + "=" * 60)
    
    session.close()
    
    return {
        'model': model_type,
        'mse': mse,
        'rmse': rmse,
        'mae': mae,
        'r2': r2,
        'baseline_mse': baseline_mse,
        'baseline_rmse': baseline_rmse,
        'baseline_mae': baseline_mae,
        'baseline_r2': baseline_r2,
        'rmse_improvement': rmse_improvement,
        'mae_improvement': mae_improvement,
        'r2_improvement': r2_improvement,
        'n_samples': len(df)
    }

def compare_all_models():
    """Compare all available models."""
    models = ['lightgbm', 'xgboost', 'rf']
    results = []
    
    for model in models:
        print(f"\n{'='*60}")
        print(f"Testing {model.upper()}")
        print(f"{'='*60}\n")
        
        try:
            metrics = evaluate_model_accuracy(model)
            if metrics:
                results.append(metrics)
        except Exception as e:
            print(f"Error evaluating {model}: {e}")
    
    if results:
        print("\n\n" + "=" * 80)
        print("SUMMARY: ALL MODELS COMPARISON")
        print("=" * 80)
        
        df_results = pd.DataFrame(results)
        print("\n" + df_results[['model', 'rmse', 'mae', 'r2']].to_string(index=False))
        
        print(f"\nBest Model (by RMSE): {df_results.loc[df_results['rmse'].idxmin(), 'model'].upper()}")
        print(f"Best Model (by R²):   {df_results.loc[df_results['r2'].idxmax(), 'model'].upper()}")
        print("=" * 80)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        model = sys.argv[1].lower()
        evaluate_model_accuracy(model)
    else:
        # Default: evaluate lightgbm or compare all
        print("Usage: python evaluate_model_accuracy.py [model_type]")
        print("  model_type: lightgbm, xgboost, rf, or 'all'\n")
        
        choice = input("Enter model to evaluate (lightgbm/xgboost/rf/all) [lightgbm]: ").strip().lower()
        if not choice:
            choice = 'lightgbm'
        
        if choice == 'all':
            compare_all_models()
        else:
            evaluate_model_accuracy(choice)

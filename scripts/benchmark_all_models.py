import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from core.database import init_db, get_session
from core.layers.weather_model import WeatherCorrectionLayer
from sklearn.metrics import mean_squared_error, mean_absolute_error
import os
from pathlib import Path

# Set plotting style
plt.style.use('ggplot')
sns.set_theme(style="whitegrid")

def benchmark_models():
    print("Initializing Database...")
    engine = init_db()
    session = get_session(engine)
    
    models_to_test = ['lightgbm', 'xgboost', 'rf']
    results_metrics = []
    
    # Load base data
    dummy_layer = WeatherCorrectionLayer(model_type='lightgbm')
    df = dummy_layer.load_data(session)
    
    output_dir = Path("reports/ppt_visuals")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Select a sample for plotting (first 200 daytime points of Accra)
    plot_df = df[df['location_id'] == 1].copy()
    plot_df = plot_df[plot_df['ghi_satellite'] > 10].head(200)
    
    plt.figure(figsize=(15, 8))
    plt.plot(range(len(plot_df)), plot_df['ghi_ground'], label='Ground Truth', color='black', lw=3, zorder=5)
    plt.plot(range(len(plot_df)), plot_df['ghi_satellite'], label='Raw Satellite', color='gray', alpha=0.5, linestyle='--')
    
    colors = {'lightgbm': 'green', 'xgboost': 'blue', 'rf': 'purple'}
    
    for mtype in models_to_test:
        print(f"Testing model: {mtype}...")
        try:
            layer = WeatherCorrectionLayer(model_type=mtype)
            layer.load_models()
            
            # Predict
            pred_df = layer.predict(df)
            
            # Metrics
            rmse = np.sqrt(mean_squared_error(df['ghi_ground'], pred_df['ghi_corrected']))
            mae = mean_absolute_error(df['ghi_ground'], pred_df['ghi_corrected'])
            
            # Use correlation to show "goodness of fit"
            corr = np.corrcoef(df['ghi_ground'], pred_df['ghi_corrected'])[0, 1]
            
            results_metrics.append({
                'Model': mtype.upper(),
                'RMSE (W/m²)': rmse,
                'MAE (W/m²)': mae,
                'Correlation': corr
            })
            
            # Add to plot
            m_plot_df = layer.predict(plot_df)
            plt.plot(range(len(m_plot_df)), m_plot_df['ghi_corrected'], label=f'{mtype.upper()} Corrected', color=colors[mtype], alpha=0.8)
            
        except Exception as e:
            print(f"Error testing {mtype}: {e}")

    # Save Performance Plot
    plt.title('Comparison of ML Models for Irradiance Correction (Sample Window)', fontsize=14)
    plt.xlabel('Time (Sample Hours)', fontsize=12)
    plt.ylabel('Irradiation GHI (W/m²)', fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "model_comparison_timeseries.png", dpi=300)
    print(f"Saved: {output_dir / 'model_comparison_timeseries.png'}")
    
    # Create Metrics Table Plot
    metrics_df = pd.DataFrame(results_metrics)
    print("\nBenchmark Results:")
    print(metrics_df.to_string(index=False))
    
    plt.figure(figsize=(10, 4))
    plt.axis('off')
    tbl = plt.table(cellText=metrics_df.values, colLabels=metrics_df.columns, loc='center', cellLoc='center')
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(12)
    tbl.scale(1.2, 2)
    plt.title('ML Model Performance Metrics (Full Dataset)', fontsize=14, pad=20)
    plt.savefig(output_dir / "model_performance_table.png", dpi=300)
    
    session.close()

if __name__ == "__main__":
    benchmark_models()

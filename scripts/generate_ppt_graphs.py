import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from core.database import init_db, get_session
from core.layers.weather_model import WeatherCorrectionLayer
import os
from pathlib import Path

# Set plotting style
plt.style.use('ggplot')
sns.set_theme(style="whitegrid")

def generate_graphs():
    print("Initializing Database...")
    engine = init_db()
    session = get_session(engine)
    
    print("Loading layer 1 model...")
    layer1 = WeatherCorrectionLayer(model_type='lightgbm')
    layer1.load_models()
    
    print("Loading evaluation data...")
    # Load all available training data (NASA Satellite vs Ground Truth)
    df = layer1.load_data(session)
    
    # Predict corrected values
    print("Generating predictions...")
    results = layer1.predict(df)
    
    # Select a representative sample or a specific location for cleaner visualization
    # Let's take Accra (Location ID 1) for the comparison
    accra_df = results[results['location_id'] == 1].head(500) # Take first 500 points for a clear scatter
    
    output_dir = Path("reports/ppt_visuals")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Plot: Raw Satellite vs Ground Irradiation (Bias Identification)
    plt.figure(figsize=(10, 8))
    sns.scatterplot(data=accra_df, x='ghi_satellite', y='ghi_ground', alpha=0.5, color='red', label='Raw Satellite Data')
    # Ideal line
    max_val = max(accra_df['ghi_satellite'].max(), accra_df['ghi_ground'].max())
    plt.plot([0, max_val], [0, max_val], 'k--', lw=2, label='Perfect Alignment (Ideal)')
    
    plt.title('Baseline: NASA Satellite vs Ground Truth (Irradiation)', fontsize=14)
    plt.xlabel('NASA Satellite GHI (W/m²)', fontsize=12)
    plt.ylabel('Ground Station GHI (W/m²)', fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "bias_identification.png", dpi=300)
    print(f"Saved: {output_dir / 'bias_identification.png'}")
    
    # 2. Plot: Corrected vs Ground Irradiation (Correction Proof)
    plt.figure(figsize=(10, 8))
    sns.scatterplot(data=accra_df, x='ghi_corrected', y='ghi_ground', alpha=0.5, color='green', label='ML Corrected Data')
    # Ideal line
    plt.plot([0, max_val], [0, max_val], 'k--', lw=2, label='Perfect Alignment (Ideal)')
    
    plt.title('Performance: ML-Corrected Satellite vs Ground Truth', fontsize=14)
    plt.xlabel('Corrected GHI (W/m²)', fontsize=12)
    plt.ylabel('Ground Station GHI (W/m²)', fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "correction_proof.png", dpi=300)
    print(f"Saved: {output_dir / 'correction_proof.png'}")
    
    # 3. Time Series Slice (Optional but nice for PPT)
    plt.figure(figsize=(15, 6))
    time_slice = accra_df.iloc[100:200] # Take a small window
    plt.plot(range(len(time_slice)), time_slice['ghi_ground'], label='Ground Truth', color='black', lw=2)
    plt.plot(range(len(time_slice)), time_slice['ghi_satellite'], label='Raw Satellite', color='red', alpha=0.6, linestyle='--')
    plt.plot(range(len(time_slice)), time_slice['ghi_corrected'], label='Corrected ML', color='green', alpha=0.8)
    
    plt.title('Diurnal Profile Correction (Accra Sample Window)', fontsize=14)
    plt.xlabel('Time (Hours)', fontsize=12)
    plt.ylabel('Irradiation (W/m²)', fontsize=12)
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "diurnal_correction.png", dpi=300)
    print(f"Saved: {output_dir / 'diurnal_correction.png'}")

    session.close()

if __name__ == "__main__":
    generate_graphs()

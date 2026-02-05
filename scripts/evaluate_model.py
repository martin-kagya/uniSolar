#!/usr/bin/env python3
"""
Comprehensive Model Evaluation Script
=====================================
Multi-resolution validation against Lake Volta ground truth data.
Generates visualizations, detailed metrics, and exports results.
"""

import pandas as pd
import numpy as np
import pvlib
import sys
import os
import warnings
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db, get_session, WeatherData, Location
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.physics_model import PhysicsLayer

# Output directory for reports
REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)

LOCATION_ID = 8  # Wayokope


def load_validation_data(filepath='data/Full Dataset.xlsx'):
    """Load and preprocess validation data."""
    df = pd.read_excel(filepath)
    df['Date_Time'] = pd.to_datetime(df['Date_Time'], errors='coerce')
    df = df.dropna(subset=['Date_Time'])
    df = df.sort_values('Date_Time')
    df['Generated Power (kW)'] = pd.to_numeric(df['Generated Power (kW)'], errors='coerce')
    return df


def run_simulation_pipeline(location_id):
    """Run the full 3-layer simulation pipeline."""
    engine = init_db()
    session = get_session(engine)
    loc = session.get(Location, location_id)
    lat, lon = loc.latitude, loc.longitude
    
    recs = session.query(WeatherData).filter_by(location_id=location_id).all()
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
    df['albedo'] = 0.20  # Forest/transition zone
    
    # Layer 1: Weather Correction
    print("  Layer 1: Weather Correction (LightGBM)...")
    l1 = WeatherCorrectionLayer(model_type='lightgbm')
    l1.load_models()
    df1 = l1.predict(df)
    
    # Layer 2: Environmental Losses
    print("  Layer 2: Environmental Losses...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        l2 = EnvironmentalLayer(rain_threshold_mm=0.5, degradation_rate=0.005)
        df2 = l2.process(df1, system_start_date=df1['timestamp'].min())
    
    # Layer 3: Physics Simulation
    print("  Layer 3: Physics Simulation...")
    df2['timestamp'] = pd.to_datetime(df2['timestamp'])
    df2 = df2.set_index('timestamp')
    
    l3 = PhysicsLayer()
    capacity_kw = 26.1  # Known from dataset
    res = l3.simulate(df2, lat=lat, lon=lon, system_capacity_kw=capacity_kw, tilt=10, azimuth=180)
    
    session.close()
    return res, lat, lon, capacity_kw


def compute_metrics(sim, val, label=""):
    """Compute comprehensive error metrics."""
    # Align and drop NaN
    combined = pd.concat([sim.rename('sim'), val.rename('val')], axis=1).dropna()
    if len(combined) == 0:
        return {}
    
    sim_vals = combined['sim'].values
    val_vals = combined['val'].values
    
    error = sim_vals - val_vals
    abs_error = np.abs(error)
    
    # Basic metrics
    rmse = np.sqrt(np.mean(error**2))
    mae = np.mean(abs_error)
    mbe = np.mean(error)  # Mean Bias Error
    
    # Percentage metrics (avoid division by zero)
    nonzero_mask = val_vals > 0
    if nonzero_mask.sum() > 0:
        mape = np.mean(abs_error[nonzero_mask] / val_vals[nonzero_mask]) * 100
    else:
        mape = np.nan
    
    # Normalized metrics (by mean of validation)
    val_mean = val_vals.mean()
    if val_mean > 0:
        nrmse = (rmse / val_mean) * 100
        nmae = (mae / val_mean) * 100
        nmbe = (mbe / val_mean) * 100
    else:
        nrmse = nmae = nmbe = np.nan
    
    # R² (Coefficient of Determination)
    ss_res = np.sum(error**2)
    ss_tot = np.sum((val_vals - val_vals.mean())**2)
    r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
    
    # Correlation coefficient
    corr = np.corrcoef(sim_vals, val_vals)[0, 1] if len(sim_vals) > 1 else np.nan
    
    return {
        'label': label,
        'n_samples': len(combined),
        'rmse': rmse,
        'mae': mae,
        'mbe': mbe,
        'mape': mape,
        'nrmse': nrmse,
        'nmae': nmae,
        'nmbe': nmbe,
        'r2': r2,
        'correlation': corr,
        'total_sim': sim_vals.sum(),
        'total_val': val_vals.sum(),
        'scale_factor': val_vals.sum() / sim_vals.sum() if sim_vals.sum() > 0 else np.nan
    }


def generate_text_report(metrics_dict, report_path):
    """Generate a text-based evaluation report."""
    lines = []
    lines.append("=" * 70)
    lines.append("LAKE VOLTA MODEL EVALUATION REPORT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("")
    
    for resolution, metrics in metrics_dict.items():
        lines.append(f"\n{'='*70}")
        lines.append(f"{resolution.upper()} RESOLUTION METRICS")
        lines.append("=" * 70)
        lines.append(f"Samples:           {metrics['n_samples']:,}")
        lines.append(f"Total Simulated:   {metrics['total_sim']:,.2f} kWh")
        lines.append(f"Total Validation:  {metrics['total_val']:,.2f} kWh")
        lines.append(f"Scaling Factor:    {metrics['scale_factor']:.3f} (model predicts {1/metrics['scale_factor']:.2f}x too high)")
        lines.append("")
        lines.append("Absolute Metrics:")
        lines.append(f"  RMSE:            {metrics['rmse']:,.2f} kWh/{resolution}")
        lines.append(f"  MAE:             {metrics['mae']:,.2f} kWh/{resolution}")
        lines.append(f"  MBE:             {metrics['mbe']:,.2f} kWh/{resolution} (bias)")
        lines.append("")
        lines.append("Percentage Metrics:")
        lines.append(f"  MAPE:            {metrics['mape']:.2f}%")
        lines.append(f"  nRMSE:           {metrics['nrmse']:.2f}%")
        lines.append(f"  nMAE:            {metrics['nmae']:.2f}%")
        lines.append(f"  nMBE:            {metrics['nmbe']:.2f}%")
        lines.append("")
        lines.append("Goodness of Fit:")
        lines.append(f"  R²:              {metrics['r2']:.4f}")
        lines.append(f"  Correlation:     {metrics['correlation']:.4f}")
    
    lines.append("")
    lines.append("=" * 70)
    lines.append("INTERPRETATION")
    lines.append("=" * 70)
    
    # Get monthly metrics for rating
    monthly = metrics_dict.get('monthly', {})
    if monthly:
        mape = monthly.get('mape', 100)
        if mape < 10:
            rating = "Excellent (5/5)"
        elif mape < 20:
            rating = "Good (4/5)"
        elif mape < 35:
            rating = "Fair (3/5)"
        elif mape < 50:
            rating = "Poor (2/5)"
        else:
            rating = "Very Poor (1/5)"
        lines.append(f"Overall Rating: {rating}")
        lines.append("")
        
        scale = monthly.get('scale_factor', 1)
        if scale < 0.8:
            lines.append("ISSUE: Model OVER-predicts generation by {:.0f}%".format((1/scale - 1) * 100))
            lines.append("Possible causes:")
            lines.append("  - Unmodeled losses (curtailment, inverter clipping, outages)")
            lines.append("  - Higher soiling/degradation than modeled")
            lines.append("  - System derate factors not captured")
            lines.append("  - Panel efficiency degradation")
        elif scale > 1.2:
            lines.append("ISSUE: Model UNDER-predicts generation by {:.0f}%".format((scale - 1) * 100))
    
    report_text = "\n".join(lines)
    
    with open(report_path, 'w') as f:
        f.write(report_text)
    
    return report_text


def export_comparison_csv(comparison_df, filepath):
    """Export comparison data to CSV."""
    comparison_df.to_csv(filepath)
    print(f"Exported comparison data to: {filepath}")


def main():
    print("=" * 70)
    print("LAKE VOLTA MODEL EVALUATION")
    print("=" * 70)
    
    # Load validation data
    print("\n1. Loading validation data...")
    val_df = load_validation_data('data/Full Dataset.xlsx')
    capacity_kw = val_df['Nominal Power (kW)'].astype(float).max()
    print(f"   Records: {len(val_df):,}")
    print(f"   Period: {val_df['Date_Time'].min()} to {val_df['Date_Time'].max()}")
    print(f"   Capacity: {capacity_kw} kW")
    
    # Run simulation
    print("\n2. Running simulation pipeline...")
    sim_result, lat, lon, _ = run_simulation_pipeline(LOCATION_ID)
    
    # Prepare validation series (minute kW -> hourly kWh)
    val_power = val_df.set_index('Date_Time')['Generated Power (kW)'].astype(float)
    val_hourly_kwh = val_power.resample('h').mean()  # Average kW for the hour = kWh
    
    # Prepare simulated series (Wh -> kWh)
    sim_hourly_wh = sim_result['ac_series']
    sim_hourly_kwh = sim_hourly_wh / 1000.0
    
    # Filter to daylight hours using solar elevation
    print("\n3. Filtering to daylight hours...")
    solpos = pvlib.solarposition.get_solarposition(sim_hourly_kwh.index, lat, lon)
    daylight_mask = solpos['elevation'] > 0
    
    sim_daylight = sim_hourly_kwh[daylight_mask]
    val_daylight = val_hourly_kwh[daylight_mask.reindex(val_hourly_kwh.index, fill_value=False)]
    
    # Multi-resolution aggregation
    print("\n4. Computing metrics at multiple resolutions...")
    
    # Hourly
    hourly_metrics = compute_metrics(sim_daylight, val_daylight, "hourly")
    
    # Daily
    sim_daily = sim_daylight.resample('D').sum()
    val_daily = val_daylight.resample('D').sum()
    daily_metrics = compute_metrics(sim_daily, val_daily, "daily")
    
    # Monthly
    sim_monthly = sim_daylight.resample('ME').sum()
    val_monthly = val_daylight.resample('ME').sum()
    monthly_metrics = compute_metrics(sim_monthly, val_monthly, "monthly")
    
    metrics_dict = {
        'hourly': hourly_metrics,
        'daily': daily_metrics,
        'monthly': monthly_metrics
    }
    
    # Generate report
    print("\n5. Generating report...")
    report_path = REPORT_DIR / "lake_volta_evaluation.txt"
    report_text = generate_text_report(metrics_dict, report_path)
    print(report_text)
    print(f"\nReport saved to: {report_path}")
    
    # Export comparison CSVs
    print("\n6. Exporting comparison data...")
    
    # Monthly comparison
    monthly_comparison = pd.DataFrame({
        'simulated_kwh': sim_monthly,
        'validation_kwh': val_monthly,
        'error_kwh': sim_monthly - val_monthly,
        'pct_error': ((sim_monthly - val_monthly) / val_monthly * 100).where(val_monthly > 0)
    })
    export_comparison_csv(monthly_comparison, REPORT_DIR / "monthly_comparison.csv")
    
    # Daily comparison
    daily_comparison = pd.DataFrame({
        'simulated_kwh': sim_daily,
        'validation_kwh': val_daily,
        'error_kwh': sim_daily - val_daily
    })
    export_comparison_csv(daily_comparison, REPORT_DIR / "daily_comparison.csv")
    
    # Time-of-day analysis
    print("\n7. Time-of-day analysis...")
    hourly_combined = pd.DataFrame({
        'sim': sim_daylight,
        'val': val_daylight
    }).dropna()
    hourly_combined['hour'] = hourly_combined.index.hour
    hourly_combined['error'] = hourly_combined['sim'] - hourly_combined['val']
    
    tod_stats = hourly_combined.groupby('hour').agg({
        'sim': 'mean',
        'val': 'mean',
        'error': ['mean', 'std']
    })
    tod_stats.columns = ['sim_mean', 'val_mean', 'error_mean', 'error_std']
    print("\nError by Hour of Day:")
    print(tod_stats.to_string())
    export_comparison_csv(tod_stats, REPORT_DIR / "hourly_error_stats.csv")
    
    # Seasonal analysis
    print("\n8. Seasonal analysis...")
    monthly_comparison['month'] = monthly_comparison.index.month
    
    # Ghana seasons: Dry (Nov-Mar), Wet (Apr-Oct)
    def get_season(month):
        if month in [11, 12, 1, 2, 3]:
            return 'Dry'
        else:
            return 'Wet'
    
    monthly_comparison['season'] = monthly_comparison['month'].apply(get_season)
    seasonal_stats = monthly_comparison.groupby('season').agg({
        'simulated_kwh': 'sum',
        'validation_kwh': 'sum',
        'error_kwh': ['sum', 'mean']
    })
    print("\nSeasonal Performance:")
    print(seasonal_stats.to_string())
    
    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)
    
    return metrics_dict, monthly_comparison


if __name__ == "__main__":
    results = main()

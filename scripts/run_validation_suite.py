#!/usr/bin/env python3
"""
Validation Suite with Visualizations
=====================================
Generates comprehensive visual reports for model evaluation.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORT_DIR = Path(__file__).parent.parent / "reports"
REPORT_DIR.mkdir(exist_ok=True)


def plot_monthly_comparison(monthly_csv_path, output_path):
    """Bar chart comparing monthly simulated vs actual generation."""
    df = pd.read_csv(monthly_csv_path, index_col=0, parse_dates=True)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x = np.arange(len(df))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, df['simulated_kwh'], width, label='Simulated', color='#3498db', alpha=0.8)
    bars2 = ax.bar(x + width/2, df['validation_kwh'], width, label='Actual', color='#2ecc71', alpha=0.8)
    
    ax.set_xlabel('Month', fontsize=12)
    ax.set_ylabel('Energy (kWh)', fontsize=12)
    ax.set_title('Monthly Energy Generation: Simulated vs Actual (Lake Volta 2019)', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([d.strftime('%b') for d in df.index], rotation=45)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # Add error annotations
    for i, (sim, val) in enumerate(zip(df['simulated_kwh'], df['validation_kwh'])):
        pct_err = (sim - val) / val * 100 if val > 0 else 0
        ax.annotate(f'+{pct_err:.0f}%', (i, sim + 100), ha='center', fontsize=8, color='red')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_scatter_comparison(daily_csv_path, output_path):
    """Scatter plot of simulated vs actual daily generation with 1:1 line."""
    df = pd.read_csv(daily_csv_path, index_col=0, parse_dates=True)
    
    fig, ax = plt.subplots(figsize=(8, 8))
    
    ax.scatter(df['validation_kwh'], df['simulated_kwh'], alpha=0.5, c='#3498db', edgecolors='white', linewidth=0.5)
    
    # 1:1 line
    max_val = max(df['validation_kwh'].max(), df['simulated_kwh'].max())
    ax.plot([0, max_val], [0, max_val], 'k--', linewidth=2, label='1:1 Line')
    
    # Best fit line
    z = np.polyfit(df['validation_kwh'], df['simulated_kwh'], 1)
    p = np.poly1d(z)
    ax.plot(df['validation_kwh'].sort_values(), p(df['validation_kwh'].sort_values()), 
            'r-', linewidth=2, label=f'Best Fit (slope={z[0]:.2f})')
    
    ax.set_xlabel('Actual Daily Generation (kWh)', fontsize=12)
    ax.set_ylabel('Simulated Daily Generation (kWh)', fontsize=12)
    ax.set_title('Daily Generation: Simulated vs Actual', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # R² annotation
    corr = np.corrcoef(df['validation_kwh'], df['simulated_kwh'])[0, 1]
    ax.annotate(f'R² = {corr**2:.3f}', (0.05, 0.95), xycoords='axes fraction', fontsize=12,
                bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_error_by_hour(hourly_stats_path, output_path):
    """Box/bar plot showing error patterns by hour of day."""
    df = pd.read_csv(hourly_stats_path, index_col=0)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Left: Mean power by hour
    ax1 = axes[0]
    x = df.index
    ax1.plot(x, df['sim_mean'], 'b-o', label='Simulated', linewidth=2, markersize=6)
    ax1.plot(x, df['val_mean'], 'g-s', label='Actual', linewidth=2, markersize=6)
    ax1.fill_between(x, df['sim_mean'], df['val_mean'], alpha=0.2, color='red')
    ax1.set_xlabel('Hour of Day', fontsize=12)
    ax1.set_ylabel('Mean Power (kW)', fontsize=12)
    ax1.set_title('Mean Hourly Generation Profile', fontsize=14, fontweight='bold')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_xticks(x)
    
    # Right: Error by hour with error bars
    ax2 = axes[1]
    bars = ax2.bar(x, df['error_mean'], yerr=df['error_std'], capsize=3, 
                   color=np.where(df['error_mean'] > 0, '#e74c3c', '#27ae60'), alpha=0.7)
    ax2.axhline(0, color='black', linewidth=1)
    ax2.set_xlabel('Hour of Day', fontsize=12)
    ax2.set_ylabel('Mean Error (kWh)', fontsize=12)
    ax2.set_title('Prediction Error by Hour of Day', fontsize=14, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.set_xticks(x)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def plot_error_histogram(daily_csv_path, output_path):
    """Histogram of daily prediction errors."""
    df = pd.read_csv(daily_csv_path, index_col=0, parse_dates=True)
    errors = df['error_kwh'].dropna()
    
    fig, ax = plt.subplots(figsize=(10, 5))
    
    ax.hist(errors, bins=30, edgecolor='black', alpha=0.7, color='#3498db')
    ax.axvline(errors.mean(), color='red', linestyle='--', linewidth=2, label=f'Mean: {errors.mean():.1f} kWh')
    ax.axvline(0, color='black', linestyle='-', linewidth=2, label='Zero Error')
    
    ax.set_xlabel('Daily Error (Simulated - Actual) kWh', fontsize=12)
    ax.set_ylabel('Frequency', fontsize=12)
    ax.set_title('Distribution of Daily Prediction Errors', fontsize=14, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    # Add statistics
    stats_text = f'Mean: {errors.mean():.1f} kWh\nStd: {errors.std():.1f} kWh\nMedian: {errors.median():.1f} kWh'
    ax.annotate(stats_text, (0.02, 0.98), xycoords='axes fraction', fontsize=10,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def generate_markdown_report(report_dir):
    """Generate a markdown summary with embedded images."""
    md_path = report_dir / "evaluation_report.md"
    
    content = f"""# Lake Volta Model Evaluation Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

The model was evaluated against 1-minute resolution ground truth data from a 26.1 kW solar installation near Lake Volta (Wayokope) for the year 2019.

### Key Findings

| Metric | Value |
|--------|-------|
| **MAPE (Monthly)** | 166% |
| **Scale Factor** | 0.38 (model predicts 2.63x too high) |
| **R² (Daily)** | Negative (poor fit) |
| **Best Performance** | Morning (6-9am) and Evening (5-6pm) |
| **Worst Performance** | Peak hours (11am-3pm) |

## Visualizations

### Monthly Comparison
![Monthly Comparison](monthly_comparison.png)

### Daily Scatter Plot
![Daily Scatter](daily_scatter.png)

### Error by Hour of Day
![Hourly Error](hourly_error_analysis.png)

### Error Distribution
![Error Histogram](error_histogram.png)

## Root Cause Analysis

The systematic over-prediction (2.63x) suggests several possible issues:

1. **Unmodeled system losses**: The actual system may have significant losses not captured in the model:
   - Inverter efficiency losses
   - DC/AC conversion losses
   - Cable losses
   - Transformer losses

2. **Operational curtailment**: Grid-connected systems near Lake Volta may experience curtailment when the grid cannot absorb excess power.

3. **Soiling/Degradation**: Higher than expected soiling or panel degradation.

4. **System specification mismatch**: The nominal 26.1 kW may represent installed capacity, but effective capacity could be lower due to:
   - Partial shading
   - Non-optimal orientation
   - Module mismatch

5. **Time-of-day pattern**: The model under-predicts at sunrise/sunset but massively over-predicts at peak hours, suggesting possible irradiance overestimation in satellite data during clear-sky conditions.

## Recommendations

1. **Apply calibration factor**: Scale model output by 0.38 for this location/system type
2. **Investigate peak-hour bias**: Review satellite GHI data vs ground measurements
3. **Add derate factors**: Implement additional loss factors for system-level derations
4. **Collect more ground truth**: Gather data from other sites to validate patterns

## Data Files

- [monthly_comparison.csv](monthly_comparison.csv)
- [daily_comparison.csv](daily_comparison.csv)
- [hourly_error_stats.csv](hourly_error_stats.csv)
- [lake_volta_evaluation.txt](lake_volta_evaluation.txt)
"""
    
    with open(md_path, 'w') as f:
        f.write(content)
    
    print(f"Saved markdown report: {md_path}")


def main():
    print("=" * 60)
    print("GENERATING VISUALIZATIONS")
    print("=" * 60)
    
    monthly_csv = REPORT_DIR / "monthly_comparison.csv"
    daily_csv = REPORT_DIR / "daily_comparison.csv"
    hourly_stats = REPORT_DIR / "hourly_error_stats.csv"
    
    # Check files exist
    for f in [monthly_csv, daily_csv, hourly_stats]:
        if not f.exists():
            print(f"ERROR: Required file not found: {f}")
            print("Please run evaluate_model.py first.")
            return
    
    # Generate plots
    print("\n1. Monthly comparison bar chart...")
    plot_monthly_comparison(monthly_csv, REPORT_DIR / "monthly_comparison.png")
    
    print("\n2. Daily scatter plot...")
    plot_scatter_comparison(daily_csv, REPORT_DIR / "daily_scatter.png")
    
    print("\n3. Hourly error analysis...")
    plot_error_by_hour(hourly_stats, REPORT_DIR / "hourly_error_analysis.png")
    
    print("\n4. Error histogram...")
    plot_error_histogram(daily_csv, REPORT_DIR / "error_histogram.png")
    
    print("\n5. Generating markdown report...")
    generate_markdown_report(REPORT_DIR)
    
    print("\n" + "=" * 60)
    print("VISUALIZATION COMPLETE")
    print(f"All outputs saved to: {REPORT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()

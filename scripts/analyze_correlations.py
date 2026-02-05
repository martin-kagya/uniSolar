import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from core.database import init_db, get_session, WeatherData

# Initialize DB
engine = init_db()
session = get_session(engine)

# Load Accra data (has Solcast ground truth)
print("Loading Accra data (with Solcast ground truth)...")
accra_data = session.query(WeatherData).filter_by(location_id=1).all()
df_accra = pd.DataFrame([d.__dict__ for d in accra_data])
if '_sa_instance_state' in df_accra.columns:
    df_accra = df_accra.drop('_sa_instance_state', axis=1)

# Filter to rows with ground truth
df_accra_gt = df_accra[df_accra['ghi_ground'].notna()].copy()

print(f"Accra records with ground truth: {len(df_accra_gt)}")

# Select relevant columns for correlation
features = [
    'ghi_satellite', 'dni_satellite', 'dhi_satellite',
    'ghi_ground', 'dni_ground',
    'temp_air', 'relative_humidity', 'wind_speed',
    'pm25', 'albedo'
]

# Filter to available columns and remove columns with all NaN
available_features = []
for f in features:
    if f in df_accra_gt.columns:
        if df_accra_gt[f].notna().sum() > 100:  # At least 100 non-null values
            available_features.append(f)

print(f"Available features: {available_features}")

df_corr = df_accra_gt[available_features].copy()

# Drop rows with ANY NaN in selected columns
df_corr = df_corr.dropna()

print(f"Records for correlation analysis: {len(df_corr)}")

# Calculate correlation matrix
corr_matrix = df_corr.corr()

# Create figure
fig, ax = plt.subplots(figsize=(14, 12))

# Create heatmap
sns.heatmap(
    corr_matrix, 
    annot=True, 
    fmt='.3f',
    cmap='RdYlGn',
    center=0,
    vmin=-1,
    vmax=1,
    square=True,
    linewidths=0.5,
    cbar_kws={"shrink": 0.8},
    ax=ax
)

plt.title('Feature Correlation Matrix\n(Accra - with Solcast Ground Truth)', 
          fontsize=16, fontweight='bold', pad=20)
plt.tight_layout()

# Save figure
output_path = '/Users/kagya/.gemini/antigravity/brain/f6a93f9b-0e80-43d8-81c4-fa47d1fd7c3d/correlation_matrix.png'
plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"\nCorrelation matrix saved to: {output_path}")

# Print key insights
print("\n" + "="*60)
print("KEY INSIGHTS")
print("="*60)

# Satellite vs Ground Truth correlations
print("\n1. SATELLITE vs GROUND TRUTH CORRELATION:")
if 'ghi_ground' in corr_matrix.columns:
    ghi_corr = corr_matrix.loc['ghi_satellite', 'ghi_ground']
    print(f"   GHI Satellite vs Ground: {ghi_corr:.4f}")
    
if 'dni_ground' in corr_matrix.columns:
    dni_corr = corr_matrix.loc['dni_satellite', 'dni_ground']
    print(f"   DNI Satellite vs Ground: {dni_corr:.4f}")

# Feature importance for prediction
print("\n2. FEATURES MOST CORRELATED WITH GROUND TRUTH:")
if 'ghi_ground' in corr_matrix.columns:
    ghi_correlations = corr_matrix['ghi_ground'].drop('ghi_ground').abs().sort_values(ascending=False)
    print("\n   For GHI prediction:")
    for feat, corr in ghi_correlations.head(5).items():
        print(f"   - {feat}: {corr:.4f}")

session.close()
plt.close()

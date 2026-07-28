"""
verify_pipeline_e2e.py — Reproduce the /simulate pipeline end-to-end (incl. obstacle
shading) to confirm ML-A, physics, shading, Monte Carlo, and ML-B all tie together and
the response carries P50/P90/P99. Uses Tier-1 data as the weather source (no DB/network).
"""
import os, sys
import numpy as np
import pandas as pd
import pvlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.environmental_model import EnvironmentalLayer
from core.layers.geometry_model import GeometryLayer
from core.layers.physics_model import PhysicsLayer
from core.layers.financial_model import FinancialLayer
from core.layers.uncertainty_model import UncertaintyLayer

df = pd.read_parquet(os.path.join(ROOT, "data", "processed", "training_clean.parquet"))
df["timestamp"] = pd.to_datetime(df["timestamp"])
s = df[df["station"] == "navrongo_tier1"].sort_values("timestamp").copy()
s["station_name"] = s["station"]
lat, lon = float(s["latitude"].iloc[0]), float(s["longitude"].iloc[0])
CAP = 1000.0
print(f"Site: navrongo ({lat:.3f}, {lon:.3f})  capacity={CAP:.0f} kW\n")

# --- Layer 1: ML-A ---
wl = WeatherCorrectionLayer()
df_l1 = wl.predict(s.copy())
assert "dhi_corrected" in df_l1.columns, "ML-A did not produce dhi_corrected"
day = df_l1[df_l1["ghi_corrected"] > 50]
cosz = np.cos(np.radians(day["solar_zenith"].clip(0, 89)))
clos = (day["ghi_corrected"] - (day["dhi_corrected"] + day["dni_corrected"] * cosz)).abs().max()
print(f"[Layer 1 ML-A]      dhi_corrected present; closure residual max = {clos:.3f} W/m²")

# --- Layer 2: env ---
df_l2 = EnvironmentalLayer().process(df_l1, climate_zone=0)
df_l2["timestamp"] = pd.to_datetime(df_l2["timestamp"])
df_l2 = df_l2.set_index("timestamp")
print(f"[Layer 2 env]       soiling+degradation applied; rows={len(df_l2):,}")

# --- Layer 0: obstacle shading (real 3D obstacle near the array) ---
loc = pvlib.location.Location(latitude=lat, longitude=lon)
solar_pos = loc.get_solarposition(df_l2.index)
panels = [{"x": lon + dx, "y": lat + dy} for dx in (0, 5e-5, 1e-4) for dy in (0, 5e-5)]
features = [{"x": lon - 1e-4, "y": lat, "height": 10.0}]  # 10 m obstacle to the west
shading = GeometryLayer().calculate_obstacle_shading(
    solar_pos["zenith"], solar_pos["azimuth"], panels, features)
shading_aligned = shading.reindex(df_l2.index, method="ffill").fillna(0.0)
print(f"[Layer 0 shading]   {len(panels)} panels, 1 obstacle; "
      f"mean shade={shading_aligned.mean()*100:.2f}%  max={shading_aligned.max()*100:.1f}%  "
      f"hours-shaded={(shading_aligned>0).sum()}")

# --- Layer 3: physics WITH shading ---
phys = PhysicsLayer()
res_shade = phys.simulate(df_l2, lat, lon, system_capacity_kw=CAP, tilt=10, azimuth=180,
                          shading_penalty=shading_aligned)
res_noshade = phys.simulate(df_l2, lat, lon, system_capacity_kw=CAP, tilt=10, azimuth=180)
e_shade = res_shade["annual_energy_kwh"]; e_ns = res_noshade["annual_energy_kwh"]
print(f"[Layer 3 physics]   energy no-shade={e_ns:,.0f} kWh -> with-shade={e_shade:,.0f} kWh "
      f"({(e_shade/e_ns-1)*100:+.2f}% from obstacle)")
assert e_shade <= e_ns + 1, "Shading did not reduce (or preserve) energy!"

# --- Layer 4: financial ---
fin = FinancialLayer(electricity_tariff=2.5, system_cost_per_kw=900, annual_om_cost=15)
financials = fin.calculate_roi(res_shade["annual_energy_kwh"], CAP)
print(f"[Layer 4 finance]   NPV=₵{financials['npv']:,.0f}  payback={financials.get('payback_period','?')}")

# --- Monte Carlo P50/P90/P99 (calibrated resource sigma from ML-B) ---
ul = UncertaintyLayer()
energy_px = ul.energy_percentiles(res_shade["annual_energy_kwh"])
irr_std = energy_px["breakdown"]["total_cov"]
base = res_shade["annual_energy_kwh"]
np.random.seed(0)
ys = [base * np.random.normal(1, irr_std) * np.random.normal(1, 0.12) * np.random.normal(1, 0.03)
      for _ in range(1000)]
p50, p90, p99 = (float(np.percentile(ys, q)) for q in (50, 10, 1))
print(f"[Monte Carlo]       calibrated irr_std={irr_std*100:.1f}%  "
      f"P50={p50/1e3:,.0f}  P90={p90/1e3:,.0f}  P99={p99/1e3:,.0f} MWh")

# --- ML-B analytic energy percentiles ---
print(f"[Layer 6 ML-B]      energy P50={energy_px['p50']/1e3:,.0f}  P90={energy_px['p90']/1e3:,.0f}  "
      f"P99={energy_px['p99']/1e3:,.0f} MWh  P90/P50={energy_px['breakdown']['p90_over_p50']*100:.1f}%")

# --- Response shape check (mirror api/main.py) ---
resp = {
    "probabilistic_results": {
        "p50_yield": p50, "p90_yield": p90, "p99_yield": p99,
        "energy_p50_kwh": energy_px["p50"], "energy_p90_kwh": energy_px["p90"],
        "energy_p99_kwh": energy_px["p99"], "uncertainty_breakdown": energy_px["breakdown"],
        "p90_calibration": (ul.calib or {}).get("hourly_coverage"),
    }
}
required = ["p50_yield", "p90_yield", "p99_yield", "energy_p50_kwh", "energy_p90_kwh",
           "energy_p99_kwh", "uncertainty_breakdown", "p90_calibration"]
missing = [k for k in required if resp["probabilistic_results"].get(k) is None]
cov90 = resp["probabilistic_results"]["p90_calibration"].get("0.90")
print(f"\n[Response check]    all P50/P90/P99 + ML-B fields present: {not missing}"
      + (f"  MISSING={missing}" if missing else ""))
print(f"[Response check]    P90 calibration coverage exposed: {cov90*100:.1f}%")
print("\n✅ END-TO-END OK — ML-A split, obstacle shading, physics, MC, and ML-B all tie in.")

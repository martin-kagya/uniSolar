"""
train_uncertainty.py — Fit + validate the ML-B uncertainty calibration (P50/P90/P99).

1. Regime-conditional split-conformal residual quantiles on irradiance (LOSO on Tier-1),
   with the empirical COVERAGE table — the proof the P90 is calibrated.
2. Systematic annual model-uncertainty CoV, derived from the wired-pipeline energy error
   vs measured ground truth (small-n Tier-1; documented).
3. Saves core/models/uncertainty_calib.json for UncertaintyLayer + reliability figure.

Usage: python scripts/train_uncertainty.py
"""
import os, sys, json
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.exp_foundation import add_geometry, TIER1, CLEAN
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.physics_model import PhysicsLayer

KT_BINS = [0, .3, .5, .65, .8, 1.3]
ELEV_BINS = [0, 15, 30, 50, 90]
TAUS = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]


def regime_key(kt, elev):
    return int(np.digitize(kt, KT_BINS) * 10 + np.digitize(elev, ELEV_BINS))


def main():
    df = pd.read_parquet(CLEAN); df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["station"].isin(TIER1)].copy()
    df = add_geometry(df)
    df = df[(df["clear_sky_ghi"] > 20) & (df["ghi_ground"] > 10) & (df["ghi_satellite"] > 0)].copy()
    df["reg"] = [regime_key(kt, e) for kt, e in zip(df["kt"], df["solar_elevation"])]
    df["resid"] = df["ghi_ground"] - df["ghi_satellite"]

    # ---- 1. LOSO conformal coverage (the proof) ----
    preds = {t: np.zeros(len(df)) for t in TAUS}
    for test_st in TIER1:
        cal = df[df["station"] != test_st]; te = (df["station"] == test_st).values
        gq = {t: np.quantile(cal["resid"], t) for t in TAUS}
        by = {t: cal.groupby("reg")["resid"].quantile(t) for t in TAUS}
        for t in TAUS:
            q = pd.Series(df.loc[te, "reg"].values).map(by[t]).fillna(gq[t]).values
            preds[t][te] = df.loc[te, "ghi_satellite"].values + q
    ground = df["ghi_ground"].values
    print("=" * 58)
    print("  ML-B CONFORMAL COVERAGE (LOSO on Tier-1) — the proof")
    print("=" * 58)
    coverage = {}
    for t in TAUS:
        emp = float(np.mean(ground <= preds[t])); coverage[f"{t:.2f}"] = emp
        print(f"  tau={t:.2f}  nominal={t*100:4.0f}%   empirical={emp*100:5.1f}%   |err|={abs(emp-t)*100:.1f}pp")

    # ---- residual quantiles per regime (fit on ALL Tier-1 for deployment) ----
    resid_q = {"global": {f"{t:.2f}": float(np.quantile(df["resid"], t)) for t in TAUS}}
    for reg, g in df.groupby("reg"):
        if len(g) >= 30:
            resid_q[str(int(reg))] = {f"{t:.2f}": float(np.quantile(g["resid"], t)) for t in TAUS}

    # ---- 2. systematic annual model-uncertainty CoV (energy vs ground truth) ----
    phys = PhysicsLayer()
    def sim(o, lat, lon):
        o = o.copy(); o["soiling_loss"] = 0.0; o["degradation_factor"] = 1.0
        o["environmental_loss_factor"] = 1.0
        o["timestamp"] = pd.to_datetime(o["timestamp"]); o = o.set_index("timestamp")
        return phys.simulate(o, lat, lon, system_capacity_kw=1000, tilt=10, azimuth=180)["annual_energy_kwh"]
    raw = pd.read_parquet(CLEAN); raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    errs = []
    for st in TIER1:
        s = raw[raw["station"] == st].sort_values("timestamp").copy(); s["station_name"] = s["station"]
        lat, lon = s["latitude"].iloc[0], s["longitude"].iloc[0]
        o = WeatherCorrectionLayer().predict(s.copy())
        e = sim(o, lat, lon)
        g = o.copy()
        g["ghi_corrected"] = g["ghi_ground"]; g["dni_corrected"] = g["dni_ground"]; g["dhi_corrected"] = g["dhi_ground"]
        egt = sim(g, lat, lon)
        errs.append(e / egt - 1.0)
        print(f"  energy {st:16s}: pipeline vs ground-truth = {(e/egt-1)*100:+.1f}%")
    sigma_model_cov = float(max(np.sqrt(np.mean(np.square(errs))), 0.02))
    print(f"\n  sigma_model_cov (annual systematic) = {sigma_model_cov*100:.1f}%  "
          f"(n={len(errs)} Tier-1 stations; small-n, documented)")

    calib = {
        "method": "regime-conditional split-conformal",
        "kt_bins": KT_BINS, "elev_bins": ELEV_BINS, "taus": TAUS,
        "residual_quantiles": resid_q,
        "hourly_coverage": coverage,
        "sigma_model_cov": sigma_model_cov,
        "iav_cov_prior": 0.035,
        "n_calib_stations": len(TIER1),
        "note": "Coverage validated LOSO on 2 Tier-1 stations (only stations with DNI/DHI). Small-n.",
    }
    out = os.path.join(ROOT, "core", "models", "uncertainty_calib.json")
    with open(out, "w") as f:
        json.dump(calib, f, indent=2)
    print(f"\n  [saved] {out}")

    # ---- example annual P50/P90/P99 ----
    from core.layers.uncertainty_model import UncertaintyLayer
    ul = UncertaintyLayer(out)
    ex = ul.energy_percentiles(1_400_000)  # e.g. navrongo-scale 1 MW
    print("\n  Example (P50=1,400,000 kWh, IAV prior): "
          f"P90={ex['p90']:,.0f}  P99={ex['p99']:,.0f}  "
          f"P90/P50={ex['breakdown']['p90_over_p50']*100:.1f}%  total_cov={ex['breakdown']['total_cov']*100:.1f}%")

    # ---- reliability figure ----
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    emp = [coverage[f"{t:.2f}"] for t in TAUS]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
    ax.plot(TAUS, emp, "o-", color="#2E86C1", lw=2, ms=8, label="ML-B (LOSO)")
    ax.set_xlabel("nominal quantile"); ax.set_ylabel("empirical coverage")
    ax.set_title("ML-B P90 is calibrated"); ax.legend(); ax.grid(alpha=.3)
    fig.tight_layout()
    fp = os.path.join(ROOT, "reports", "figures", "mlb_reliability.png")
    os.makedirs(os.path.dirname(fp), exist_ok=True); fig.savefig(fp, dpi=130)
    print(f"  [saved] {fp}")


if __name__ == "__main__":
    main()

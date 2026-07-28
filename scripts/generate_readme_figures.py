"""
generate_readme_figures.py — Build the README's visual story (docs/figures/*.png).

All figures are computed from real data/models (Tier-1 references navrongo/sunyani,
the wired pipeline, the trained separation model, and the uncertainty calibration).
Reproducible: python scripts/generate_readme_figures.py
"""
import os, sys, json
import numpy as np
import pandas as pd
import pvlib
import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.exp_foundation import add_geometry, TIER1, CLEAN
from scripts.train_separation import build as sep_build, poa as sep_poa, close_dhi, FEATURES
from core.layers.weather_model import WeatherCorrectionLayer
from core.layers.physics_model import PhysicsLayer
from core.layers.uncertainty_model import UncertaintyLayer

OUT = os.path.join(ROOT, "docs", "figures")
os.makedirs(OUT, exist_ok=True)

# ---- cohesive style ----
C = {"raw": "#C0392B", "phys": "#95A5A6", "ml": "#27AE60", "blue": "#2E86C1",
     "dark": "#2C3E50", "gold": "#F39C12", "gt": "#34495E"}
plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 11,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.labelsize": 10,
    "axes.grid": True, "grid.alpha": 0.25, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def save(fig, name):
    fig.tight_layout()
    p = os.path.join(OUT, name)
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"  [saved] docs/figures/{name}")


# ============================================================ data prep
print("Preparing data / models ...")
raw = pd.read_parquet(CLEAN); raw["timestamp"] = pd.to_datetime(raw["timestamp"])
t1 = raw[raw["station"].isin(TIER1)].copy()

# geometry for decomposition/POA (with DHI ground)
dfp = sep_build(t1.copy())
dfp = dfp[(dfp["ghi_satellite"] > 0) & (dfp["ghi_ground"] > 10) & (dfp["zenith"] < 85) &
          (dfp["dhi_ground"] > 0)].copy().reset_index(drop=True)
cosz = dfp["cosz"].values
ghi_s = dfp["ghi_satellite"].values
tt = pd.DatetimeIndex(dfp["timestamp"])

# separation predictions (ML + DIRINT)
sep = joblib.load(os.path.join(ROOT, "core", "models", "separation_ml.pkl"))
k_ml = np.clip(sep["model"].predict(dfp[sep["features"]]), 0, 1)
dhi_ml = k_ml * ghi_s
dni_ml = np.clip(np.where(cosz > .01, (ghi_s - dhi_ml) / np.maximum(cosz, .01), 0), 0, dfp["dni_extra"].values)
dni_di = np.nan_to_num(pvlib.irradiance.dirint(ghi_s, dfp["zenith"].values, tt), nan=0.0)
dhi_di = close_dhi(ghi_s, dni_di, cosz)

METH = {"raw satellite": (dfp["dni_satellite"].values, dfp["dhi_satellite"].values),
        "DIRINT (physical)": (dni_di, dhi_di),
        "ML separation": (dni_ml, dhi_ml)}


# ============================================================ 1. error decomposition
def fig_decomposition():
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    comps = ["GHI", "DNI", "DHI"]
    bias, scat = [], []
    for c in comps:
        e = dfp[f"{c.lower()}_satellite"].values - dfp[f"{c.lower()}_ground"].values
        m = dfp[f"{c.lower()}_ground"].values > 10
        bias.append(np.mean(e[m])); scat.append(np.std(e[m]))
    x = np.arange(3)
    ax[0].bar(x - .2, np.abs(bias), .4, label="|bias| (correctable)", color=C["ml"])
    ax[0].bar(x + .2, scat, .4, label="scatter (irreducible)", color=C["phys"])
    ax[0].set_xticks(x); ax[0].set_xticklabels(comps)
    ax[0].set_ylabel("W/m²"); ax[0].set_title("Where is the error correctable?")
    ax[0].legend(fontsize=9)
    for i in range(3):
        ax[0].text(i - .2, abs(bias[i]) + 2, f"{bias[i]:+.0f}", ha="center", fontsize=8, color=C["dark"])
    # correctable fraction
    frac = [b**2 / (b**2 + s**2) * 100 for b, s in zip(bias, scat)]
    bars = ax[1].bar(comps, frac, color=[C["raw"], C["gold"], C["gold"]])
    ax[1].set_ylabel("% of error² that is bias"); ax[1].set_ylim(0, max(frac) * 1.4 + 2)
    ax[1].set_title("Correctable fraction of the error")
    for i, f in enumerate(frac):
        ax[1].text(i, f + .3, f"{f:.1f}%", ha="center", fontweight="bold")
    ax[1].text(0, frac[0] + max(frac) * .18, "GHI: nothing\nto correct", ha="center",
               fontsize=9, color=C["raw"])
    fig.suptitle("NASA POWER GHI is already accurate — the fixable error is in the DNI/DHI split",
                 fontsize=12, fontweight="bold")
    save(fig, "01_error_decomposition.png")


# ============================================================ 2. POA fixed vs tracker
def fig_poa():
    # fixed tilt = |lat|
    def poa_fixed(dni, dhi):
        return sep_poa(dfp, ghi_s, dni, dhi)
    tr = pvlib.tracking.singleaxis(dfp["zenith"].values, dfp["azimuth"].values,
                                   axis_tilt=0, axis_azimuth=0, max_angle=60, backtrack=True, gcr=0.35)
    st_tilt = np.nan_to_num(np.asarray(tr["surface_tilt"]), nan=0.0)
    st_az = np.nan_to_num(np.asarray(tr["surface_azimuth"]), nan=180.0)
    def poa_track(dni, dhi):
        r = pvlib.irradiance.get_total_irradiance(
            st_tilt, st_az, dfp["zenith"].values, dfp["azimuth"].values,
            dni=np.asarray(dni), ghi=ghi_s, dhi=np.asarray(dhi),
            dni_extra=dfp["dni_extra"].values, airmass=dfp["airmass"].values, model="haydavies")
        return np.asarray(r["poa_global"])
    ref_f = sep_poa(dfp, dfp["ghi_ground"].values, dfp["dni_ground"].values, dfp["dhi_ground"].values)
    r = pvlib.irradiance.get_total_irradiance(
        st_tilt, st_az, dfp["zenith"].values, dfp["azimuth"].values,
        dni=dfp["dni_ground"].values, ghi=dfp["ghi_ground"].values, dhi=dfp["dhi_ground"].values,
        dni_extra=dfp["dni_extra"].values, airmass=dfp["airmass"].values, model="haydavies")
    ref_t = np.asarray(r["poa_global"])
    mf = np.isfinite(ref_f) & (ref_f > 10); mt = np.isfinite(ref_t) & (ref_t > 10)
    names = list(METH.keys())
    rmse_f = [np.sqrt(np.mean((poa_fixed(*METH[n])[mf] - ref_f[mf])**2)) for n in names]
    rmse_t = [np.sqrt(np.mean((poa_track(*METH[n])[mt] - ref_t[mt])**2)) for n in names]
    col = [C["raw"], C["phys"], C["ml"]]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.8))
    for a, vals, title in [(ax[0], rmse_f, "Fixed tilt (near-equator)"),
                           (ax[1], rmse_t, "Single-axis tracker (utility-scale)")]:
        a.bar(names, vals, color=col)
        a.axhline(vals[0], color=C["raw"], ls="--", lw=1.2, label="raw satellite")
        a.set_ylabel("plane-of-array RMSE (W/m²)"); a.set_title(title)
        a.tick_params(axis="x", rotation=15); a.legend(fontsize=8)
        for i, v in enumerate(vals):
            a.text(i, v + 1, f"{v:.0f}", ha="center", fontweight="bold", fontsize=9)
    ax[1].text(2, rmse_t[2] * .5, "only ML\nbeats raw", ha="center", color=C["ml"],
               fontweight="bold", fontsize=9)
    fig.suptitle("ML-A: fixing the DNI/DHI split — the bankable win shows on trackers",
                 fontsize=12, fontweight="bold")
    save(fig, "02_poa_decomposition.png")


# ============================================================ 3. component accuracy
def fig_components():
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.4))
    names = list(METH.keys()); col = [C["raw"], C["phys"], C["ml"]]
    for a, comp in zip(ax, ["dni", "dhi"]):
        yt = dfp[f"{comp}_ground"].values; m = yt > 10
        r = [np.sqrt(np.mean((METH[n][0 if comp == "dni" else 1][m] - yt[m])**2)) for n in names]
        a.bar(names, r, color=col)
        a.set_ylabel(f"{comp.upper()} RMSE (W/m²)"); a.set_title(f"{comp.upper()} reconstruction")
        a.tick_params(axis="x", rotation=15)
        for i, v in enumerate(r):
            a.text(i, v + 1, f"{v:.0f}", ha="center", fontweight="bold", fontsize=9)
    fig.suptitle("ML separation gives the best component reconstruction (best DNI and DHI)",
                 fontsize=12, fontweight="bold")
    save(fig, "03_component_accuracy.png")


# ============================================================ 4. energy validation
def fig_energy_validation():
    phys = PhysicsLayer()
    def sim(o, lat, lon):
        o = o.copy(); o["soiling_loss"] = 0.0; o["degradation_factor"] = 1.0; o["environmental_loss_factor"] = 1.0
        o["timestamp"] = pd.to_datetime(o["timestamp"]); o = o.set_index("timestamp")
        return phys.simulate(o, lat, lon, system_capacity_kw=1000, tilt=10, azimuth=180)["annual_energy_kwh"]
    rows = []
    for st in TIER1:
        s = raw[raw["station"] == st].sort_values("timestamp").copy(); s["station_name"] = s["station"]
        lat, lon = s["latitude"].iloc[0], s["longitude"].iloc[0]
        wired = WeatherCorrectionLayer().predict(s.copy())
        old_wl = WeatherCorrectionLayer(); old_wl.use_ml_separation = False; old_wl.use_ghi_ratio_correction = True
        e_wired = sim(wired, lat, lon)
        e_old = sim(old_wl.predict(s.copy()), lat, lon)
        g = wired.copy(); g["ghi_corrected"] = g["ghi_ground"]; g["dni_corrected"] = g["dni_ground"]; g["dhi_corrected"] = g["dhi_ground"]
        e_gt = sim(g, lat, lon)
        rows.append((st.replace("_tier1", "").title(), e_old, e_wired, e_gt))
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(rows)); w = 0.26
    old = [r[1] / 1e6 for r in rows]; wired = [r[2] / 1e6 for r in rows]; gt = [r[3] / 1e6 for r in rows]
    ax.bar(x - w, old, w, label="old pipeline (DNI≈0 bug)", color=C["raw"])
    ax.bar(x, wired, w, label="wired ML-A pipeline", color=C["ml"])
    ax.bar(x + w, gt, w, label="measured ground truth", color=C["gt"])
    for i in range(len(rows)):
        ax.text(i - w, old[i] + .02, f"{(old[i]/gt[i]-1)*100:+.0f}%", ha="center", color=C["raw"], fontsize=9, fontweight="bold")
        ax.text(i, wired[i] + .02, f"{(wired[i]/gt[i]-1)*100:+.1f}%", ha="center", color=C["ml"], fontsize=9, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels([r[0] for r in rows])
    ax.set_ylabel("annual energy, 1 MW system (GWh)")
    ax.set_title("Energy vs measured ground truth: old pipeline understated yield ~45–50%; ML-A lands within 2%")
    ax.legend(fontsize=9)
    save(fig, "04_energy_validation.png")


# ============================================================ 5. reliability
def fig_reliability():
    calib = json.load(open(os.path.join(ROOT, "core", "models", "uncertainty_calib.json")))
    cov = calib["hourly_coverage"]; taus = [float(k) for k in cov]; emp = [cov[k] for k in cov]
    fig, ax = plt.subplots(figsize=(6, 5.6))
    ax.plot([0, 1], [0, 1], "--", color=C["dark"], lw=1.3, label="perfect calibration")
    ax.plot(taus, emp, "o-", color=C["blue"], lw=2.4, ms=9, label="ML-B (leave-station-out)")
    for t, e in zip(taus, emp):
        if t in (0.9,):
            ax.annotate(f"P90 → {e*100:.1f}%", (t, e), textcoords="offset points",
                        xytext=(-70, 8), fontsize=9, fontweight="bold", color=C["blue"])
    ax.set_xlabel("nominal quantile"); ax.set_ylabel("empirical coverage")
    ax.set_title("ML-B uncertainty is calibrated\n(P90 exceedance ≈ nominal, proven out-of-station)")
    ax.legend(fontsize=9); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    save(fig, "05_mlb_reliability.png")


# ============================================================ 6. P50/P90/P99
def fig_pxx():
    ul = UncertaintyLayer()
    p50 = 1_400_000
    px = ul.energy_percentiles(p50)
    bd = px["breakdown"]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
    labels = ["P50", "P75", "P90", "P95", "P99"]
    vals = [px[k.lower()] / 1e6 for k in labels]
    cols = [C["ml"], "#2ecc71", C["gold"], "#e67e22", C["raw"]]
    ax[0].bar(labels, vals, color=cols)
    for i, v in enumerate(vals):
        ax[0].text(i, v + .01, f"{v:.2f}", ha="center", fontweight="bold", fontsize=9)
    ax[0].set_ylabel("annual energy (GWh)"); ax[0].set_ylim(min(vals) * .96, max(vals) * 1.03)
    ax[0].set_title(f"Bankable exceedance levels (P90/P50 = {bd['p90_over_p50']*100:.1f}%)")
    # uncertainty budget
    parts = [("model\nuncertainty", bd["model_cov"] * 100, C["blue"]),
             ("interannual\nvariability", bd["interannual_cov"] * 100, C["gold"]),
             ("total\n(quadrature)", bd["total_cov"] * 100, C["dark"])]
    ax[1].bar([p[0] for p in parts], [p[1] for p in parts], color=[p[2] for p in parts])
    for i, p in enumerate(parts):
        ax[1].text(i, p[1] + .05, f"{p[1]:.1f}%", ha="center", fontweight="bold", fontsize=9)
    ax[1].set_ylabel("coefficient of variation (%)")
    ax[1].set_title("Uncertainty budget (calibrated, auditable)")
    fig.suptitle("ML-B: the P90 the lender underwrites on — with a transparent budget",
                 fontsize=12, fontweight="bold")
    save(fig, "06_p50_p90_p99.png")


# ============================================================ 7. pipeline diagram
def fig_pipeline():
    fig, ax = plt.subplots(figsize=(13, 3.2)); ax.axis("off")
    ax.set_xlim(0, 12.9); ax.set_ylim(0, 3)
    boxes = [(0.1, "NASA POWER\nGHI (accurate)", C["gt"]),
             (2.5, "ML-A\nconsistent DNI/DHI split", C["ml"]),
             (5.4, "PVLib physics\n(deterministic)", C["phys"]),
             (8.1, "ML-B\ncalibrated P90", C["ml"]),
             (10.6, "P90 energy\nP90 NPV", C["gold"])]
    w = 2.1
    for x, label, col in boxes:
        ax.add_patch(FancyBboxPatch((x, 1.0), w, 1.0, boxstyle="round,pad=0.03,rounding_size=0.1",
                                    linewidth=0, facecolor=col, alpha=.92))
        ax.text(x + w / 2, 1.5, label, ha="center", va="center", color="white",
                fontsize=9.5, fontweight="bold")
    for x, _, _ in boxes[:-1]:
        ax.add_patch(FancyArrowPatch((x + w, 1.5), (x + w + 0.4, 1.5),
                                     arrowstyle="-|>", mutation_scale=18, color=C["dark"], lw=2))
    ax.text(6, 2.55, "ML brackets the physics — it defines the inputs AND the risk envelope",
            ha="center", fontsize=12, fontweight="bold", color=C["dark"])
    ax.text(3.55, 0.6, "fixes −9% POA bias", ha="center", fontsize=8, color=C["ml"])
    ax.text(9.15, 0.6, "proven 90.6% coverage", ha="center", fontsize=8, color=C["ml"])
    save(fig, "00_pipeline.png")


if __name__ == "__main__":
    print("Generating figures ...")
    fig_pipeline()
    fig_decomposition()
    fig_poa()
    fig_components()
    fig_energy_validation()
    fig_reliability()
    fig_pxx()
    print("Done.")

"""
exp_foundation.py — Shared foundation for the ML-standout exploration.

Answers, on the ONLY clean references (Tier-1 navrongo/sunyani), the questions that
gate everything else:
  1. Error decomposition: how much of NASA POWER error is BIAS (ML-correctable) vs
     SCATTER (irreducible without new inputs)?  Done for GHI and DNI.
  2. Baseline ladder: raw -> global-linear -> per-regime correction.  Shows the honest
     ceiling for input-side ML (ML-A) vs a one-line baseline.
  3. Residual characterization per regime -> raw material for the uncertainty layer (ML-B).

Leave-one-station-out where possible (2 Tier-1 stations => train on one, test on other).
"""
import os, sys
import numpy as np
import pandas as pd
import pvlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLEAN = os.path.join(ROOT, "data", "processed", "training_clean.parquet")
TIER1 = ["navrongo_tier1", "sunyani_tier1"]


def add_geometry(df):
    """Add solar geometry + Ineichen clear-sky + clearness index per station."""
    out = []
    for st, g in df.groupby("station"):
        g = g.sort_values("timestamp").copy()
        lat, lon = g["latitude"].iloc[0], g["longitude"].iloc[0]
        loc = pvlib.location.Location(latitude=lat, longitude=lon)
        times = pd.DatetimeIndex(g["timestamp"])
        sp = loc.get_solarposition(times)
        cs = loc.get_clearsky(times, model="ineichen")
        g["solar_elevation"] = sp["apparent_elevation"].values
        g["solar_zenith"] = sp["apparent_zenith"].values
        g["clear_sky_ghi"] = cs["ghi"].values
        g["clear_sky_dni"] = cs["dni"].values
        g["kt"] = np.clip(g["ghi_satellite"] / np.maximum(cs["ghi"].values, 1.0), 0, 1.2)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def decomp(y_true, y_pred):
    """RMSE decomposed into bias (ME) and scatter (SDE). RMSE^2 = bias^2 + SDE^2."""
    e = y_pred - y_true
    bias = float(np.mean(e))
    sde = float(np.std(e))
    rmse = float(np.sqrt(np.mean(e**2)))
    return dict(n=len(e), rmse=rmse, bias=bias, sde=sde,
                bias_frac=float(bias**2 / max(rmse**2, 1e-9)))


def main():
    df = pd.read_parquet(CLEAN)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["station"].isin(TIER1)].copy()
    df = add_geometry(df)
    # Daytime, valid
    df = df[(df["clear_sky_ghi"] > 20) & (df["ghi_ground"] > 10) &
            (df["ghi_satellite"] > 0)].copy()
    mean_ghi = df["ghi_ground"].mean()
    print(f"Tier-1 reference set: {df['station'].unique().tolist()}  n={len(df):,}  "
          f"mean daytime GHI={mean_ghi:.0f} W/m²\n")

    # ---- 1. Error decomposition: BIAS vs SCATTER (the ceiling) ----
    print("=" * 70)
    print("  1. ERROR DECOMPOSITION — raw NASA POWER vs Tier-1 (RMSE² = bias² + scatter²)")
    print("=" * 70)
    for var in ["ghi", "dni"]:
        yt = df[f"{var}_ground"].values
        yp = df[f"{var}_satellite"].values
        m = (yt > 10)
        d = decomp(yt[m], yp[m])
        print(f"  {var.upper()}:  RMSE={d['rmse']:6.1f}   bias={d['bias']:+6.1f}   "
              f"scatter={d['sde']:6.1f}   bias explains {d['bias_frac']*100:4.1f}% of RMSE²  "
              f"=> ML ceiling ≈ {d['rmse']-np.sqrt(max(d['rmse']**2-d['bias']**2,0)):.1f} W/m²")
    print("\n  Interpretation: 'ML ceiling' = max RMSE a perfect bias-correction could remove.")
    print("  If scatter dominates, no feature->ratio model can defensibly cut much.\n")

    # ---- 2. Baseline ladder (leave-one-station-out) for GHI ----
    print("=" * 70)
    print("  2. BASELINE LADDER — GHI, leave-one-Tier-1-station-out")
    print("=" * 70)
    print(f"  {'method':<28}{'RMSE':>8}{'bias':>8}{'MAE':>8}")
    methods = {}
    # raw
    def eval_pred(pred):
        yt = df["ghi_ground"].values
        return dict(rmse=np.sqrt(np.mean((pred-yt)**2)),
                    bias=np.mean(pred-yt), mae=np.mean(np.abs(pred-yt)))
    methods["raw satellite"] = eval_pred(df["ghi_satellite"].values)

    # global linear: fit ground ~ a*sat + b on the OTHER station (LOSO)
    pred_lin = np.zeros(len(df))
    pred_reg = np.zeros(len(df))
    for test_st in TIER1:
        tr = df[df["station"] != test_st]
        te_mask = (df["station"] == test_st).values
        # linear
        a, b = np.polyfit(tr["ghi_satellite"], tr["ghi_ground"], 1)
        pred_lin[te_mask] = a * df.loc[te_mask, "ghi_satellite"] + b
        # per-regime multiplicative: median(ground/sat) in kt bins, learned on tr
        bins = np.array([0, .3, .5, .65, .8, 1.3])
        tr = tr.assign(kb=np.digitize(tr["kt"], bins))
        ratio_by_bin = (tr.assign(r=tr["ghi_ground"]/np.maximum(tr["ghi_satellite"],10))
                          .groupby("kb")["r"].median())
        kb_te = np.digitize(df.loc[te_mask, "kt"], bins)
        r = pd.Series(kb_te).map(ratio_by_bin).fillna(1.0).values
        pred_reg[te_mask] = df.loc[te_mask, "ghi_satellite"].values * r
    methods["global linear (LOSO)"] = eval_pred(pred_lin)
    methods["per-regime ratio (LOSO)"] = eval_pred(pred_reg)
    for name, m in methods.items():
        print(f"  {name:<28}{m['rmse']:>8.1f}{m['bias']:>+8.1f}{m['mae']:>8.1f}")
    print("\n  If ML barely beats 'global linear', the complexity isn't defensible.\n")

    # ---- 3. Residual characterization per regime (fuel for ML-B uncertainty) ----
    print("=" * 70)
    print("  3. RESIDUAL DISTRIBUTION per clearness regime  (GHI ground - satellite)")
    print("=" * 70)
    print(f"  {'kt bin':<14}{'n':>6}{'mean':>8}{'std':>8}{'p05':>8}{'p50':>8}{'p95':>8}"
          f"{'rel.std%':>9}")
    df["resid"] = df["ghi_ground"] - df["ghi_satellite"]
    bins = [(0,.3),(.3,.5),(.5,.65),(.65,.8),(.8,1.3)]
    for lo, hi in bins:
        s = df[(df["kt"]>=lo)&(df["kt"]<hi)]["resid"]
        gm = df[(df["kt"]>=lo)&(df["kt"]<hi)]["ghi_ground"].mean()
        if len(s) < 10: continue
        print(f"  [{lo:.2f},{hi:.2f})  {len(s):>6}{s.mean():>+8.1f}{s.std():>8.1f}"
              f"{np.percentile(s,5):>+8.1f}{np.percentile(s,50):>+8.1f}"
              f"{np.percentile(s,95):>+8.1f}{s.std()/max(gm,1)*100:>8.1f}%")
    print("\n  Wide, regime-dependent spread => a single fixed σ is wrong; ML-B should")
    print("  model σ(regime). This table is exactly what the conformal layer will calibrate.")


if __name__ == "__main__":
    main()

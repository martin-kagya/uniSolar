"""
train_separation.py — ML separation model + POA benchmark.

NASA POWER GHI is accurate but its DNI/DHI split is broken (POA bias ~-40 W/m²).
This learns the operational map: satellite-derived predictors -> TRUE diffuse fraction
k = DHI/GHI (target from ground). Reconstruct DNI/DHI from the accurate satellite GHI
enforcing closure (GHI = DHI + DNI·cosθ), transpose to plane-of-array (POA), and
benchmark against the standard physical separation models (Erbs, DIRINT, DISC).

Only the 2 Tier-1 stations (navrongo, sunyani) measure DHI -> leave-one-station-out.
Small (n=2) but genuinely out-of-station. Reported with that caveat.

Usage: python scripts/train_separation.py
"""
import os, sys
import numpy as np
import pandas as pd
import pvlib
import joblib
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.exp_foundation import TIER1, CLEAN

FEATURES = ["kt", "kc", "zenith", "elevation", "airmass", "hour",
            "kt_lag1", "kt_std3", "rh", "temp"]
# k decreases as clearness rises => monotonic-decreasing constraint on kt & kc (physical)
MONO = [-1, -1, 0, 0, 0, 0, 0, 0, 0, 0]


def build(df):
    """Add geometry, clear-sky, and satellite-derived separation predictors."""
    out = []
    for st, g in df.groupby("station"):
        g = g.sort_values("timestamp").copy()
        lat, lon = g["latitude"].iloc[0], g["longitude"].iloc[0]
        loc = pvlib.location.Location(latitude=lat, longitude=lon)
        t = pd.DatetimeIndex(g["timestamp"])
        sp = loc.get_solarposition(t)
        cs = loc.get_clearsky(t, model="ineichen")
        z = sp["apparent_zenith"].values
        cosz = np.cos(np.radians(np.clip(z, 0, 89)))
        i0 = pvlib.irradiance.get_extra_radiation(t).values
        g["zenith"] = z
        g["azimuth"] = sp["azimuth"].values
        g["elevation"] = sp["apparent_elevation"].values
        g["airmass"] = pvlib.atmosphere.get_relative_airmass(np.clip(z, 0.01, 89)).clip(0, 40)
        g["dni_extra"] = i0
        g["cosz"] = cosz
        g["clear_sky_ghi"] = cs["ghi"].values
        # satellite-derived clearness predictors (what we have at inference)
        g["kt"] = np.clip(g["ghi_satellite"] / np.maximum(i0 * cosz, 1.0), 0, 1.3)
        g["kc"] = np.clip(g["ghi_satellite"] / np.maximum(cs["ghi"].values, 1.0), 0, 1.3)
        g["hour"] = t.hour + t.minute / 60.0
        g["kt_lag1"] = g["kt"].shift(1).fillna(g["kt"])
        g["kt_std3"] = g["kt"].rolling(3, min_periods=1).std().fillna(0.0)
        g["rh"] = pd.to_numeric(g.get("relative_humidity", 60), errors="coerce").fillna(60.0)
        g["temp"] = pd.to_numeric(g.get("temp_air", 28), errors="coerce").fillna(28.0)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def poa(df, ghi, dni, dhi):
    r = pvlib.irradiance.get_total_irradiance(
        surface_tilt=np.abs(df["latitude"].values), surface_azimuth=180.0,
        solar_zenith=df["zenith"].values, solar_azimuth=df["azimuth"].values,
        dni=np.asarray(dni), ghi=np.asarray(ghi), dhi=np.asarray(dhi),
        dni_extra=df["dni_extra"].values, airmass=df["airmass"].values, model="haydavies")
    return np.asarray(r["poa_global"])


def close_dhi(ghi, dni, cosz):
    """DHI from closure given GHI and DNI."""
    return np.maximum(ghi - dni * cosz, 0.0)


def metr(yt, yp, m):
    e = (np.asarray(yp) - np.asarray(yt))[m]
    return np.sqrt(np.mean(e**2)), np.mean(e)


def main():
    df = pd.read_parquet(CLEAN)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["station"].isin(TIER1)].copy()
    df = build(df)
    # valid daytime rows with full ground components
    df = df[(df["ghi_satellite"] > 0) & (df["ghi_ground"] > 10) & (df["zenith"] < 85) &
            (df["dhi_ground"] > 0) & (df["dni_ground"] >= 0)].copy().reset_index(drop=True)
    df["k_true"] = np.clip(df["dhi_ground"] / np.maximum(df["ghi_ground"], 1.0), 0, 1)
    t = pd.DatetimeIndex(df["timestamp"])
    cosz = df["cosz"].values
    ghi_s = df["ghi_satellite"].values

    # ---- Build every method's DNI/DHI, then POA (LOSO for the ML model) ----
    methods = {}

    # raw satellite components
    methods["raw satellite"] = (df["dni_satellite"].values, df["dhi_satellite"].values)

    # Erbs (physical, GHI->fraction)
    erbs = pvlib.irradiance.erbs(ghi_s, df["zenith"].values, t)
    methods["Erbs"] = (erbs["dni"].values, erbs["dhi"].values)

    # DIRINT (GHI->DNI), close DHI
    dni_di = np.nan_to_num(pvlib.irradiance.dirint(ghi_s, df["zenith"].values, t), nan=0.0)
    methods["DIRINT"] = (dni_di, close_dhi(ghi_s, dni_di, cosz))

    # DISC (GHI->DNI), close DHI
    disc = pvlib.irradiance.disc(ghi_s, df["zenith"].values, t)
    dni_ds = np.nan_to_num(disc["dni"].values, nan=0.0)
    methods["DISC"] = (dni_ds, close_dhi(ghi_s, dni_ds, cosz))

    # ML separation, leave-one-station-out
    k_ml = np.zeros(len(df))
    for test_st in TIER1:
        tr = df[df["station"] != test_st]
        te = (df["station"] == test_st).values
        model = HistGradientBoostingRegressor(
            max_iter=400, learning_rate=0.05, max_depth=4, l2_regularization=1.0,
            min_samples_leaf=60, monotonic_cst=MONO, random_state=0)
        model.fit(tr[FEATURES], tr["k_true"])
        k_ml[te] = np.clip(model.predict(df.loc[te, FEATURES]), 0.0, 1.0)
    dhi_ml = k_ml * ghi_s
    dni_ml = close_dhi(ghi_s, 0, cosz) * 0  # placeholder
    dni_ml = np.where(cosz > 0.01, (ghi_s - dhi_ml) / np.maximum(cosz, 0.01), 0.0)
    dni_ml = np.clip(dni_ml, 0, df["dni_extra"].values)
    methods["ML separation (LOSO)"] = (dni_ml, dhi_ml)

    # ---- Evaluate ----
    poa_ref = poa(df, df["ghi_ground"], df["dni_ground"], df["dhi_ground"])
    m = np.isfinite(poa_ref) & (poa_ref > 10)
    mean_poa = poa_ref[m].mean()
    dni_t, dhi_t = df["dni_ground"].values, df["dhi_ground"].values
    md = m & (dni_t > 10); mh = m & (dhi_t > 5)

    print("=" * 78)
    print(f"  ML SEPARATION — POA BENCHMARK (Tier-1, LOSO)   n={m.sum():,}  mean POA={mean_poa:.0f} W/m²")
    print("=" * 78)
    print(f"  {'method':<24}{'POA RMSE':>9}{'POA bias':>9}{'  ':>3}"
          f"{'DNI RMSE':>9}{'DNI bias':>9}{'  ':>3}{'DHI RMSE':>9}{'DHI bias':>9}")
    base = None
    for name, (dni, dhi) in methods.items():
        p = poa(df, df["ghi_satellite"], dni, dhi)
        pr, pb = metr(poa_ref, p, m)
        if base is None: base = pr
        dr, db = metr(dni_t, dni, md)
        hr, hb = metr(dhi_t, dhi, mh)
        tag = "" if name == "raw satellite" else f"  ({(1-pr/base)*100:+.1f}% POA)"
        print(f"  {name:<24}{pr:>9.1f}{pb:>+9.1f}{'':>3}{dr:>9.1f}{db:>+9.1f}{'':>3}"
              f"{hr:>9.1f}{hb:>+9.1f}{tag}")

    # ---- Single-axis tracker POA (DNI-dominated; where the split matters) ----
    tr = pvlib.tracking.singleaxis(
        apparent_zenith=df["zenith"].values, apparent_azimuth=df["azimuth"].values,
        axis_tilt=0, axis_azimuth=0, max_angle=60, backtrack=True, gcr=0.35)
    st_tilt = np.nan_to_num(np.asarray(tr["surface_tilt"]), nan=0.0)
    st_az = np.nan_to_num(np.asarray(tr["surface_azimuth"]), nan=180.0)

    def poa_track(ghi, dni, dhi):
        r = pvlib.irradiance.get_total_irradiance(
            surface_tilt=st_tilt, surface_azimuth=st_az,
            solar_zenith=df["zenith"].values, solar_azimuth=df["azimuth"].values,
            dni=np.asarray(dni), ghi=np.asarray(ghi), dhi=np.asarray(dhi),
            dni_extra=df["dni_extra"].values, airmass=df["airmass"].values, model="haydavies")
        return np.asarray(r["poa_global"])

    poa_ref_tr = poa_track(df["ghi_ground"], df["dni_ground"], df["dhi_ground"])
    mt = np.isfinite(poa_ref_tr) & (poa_ref_tr > 10)
    print("\n" + "=" * 78)
    print(f"  SINGLE-AXIS TRACKER POA (DNI-dominated)   n={mt.sum():,}  mean={poa_ref_tr[mt].mean():.0f} W/m²")
    print("=" * 78)
    print(f"  {'method':<24}{'POA RMSE':>9}{'POA bias':>9}{'  ':>3}{'vs raw':>9}")
    base_t = None
    for name, (dni, dhi) in methods.items():
        p = poa_track(df["ghi_satellite"], dni, dhi)
        pr, pb = metr(poa_ref_tr, p, mt)
        if base_t is None: base_t = pr
        tag = "" if name == "raw satellite" else f"{(1-pr/base_t)*100:+.1f}%"
        print(f"  {name:<24}{pr:>9.1f}{pb:>+9.1f}{'':>3}{tag:>9}")

    # ---- Train final model on BOTH stations, save for pipeline ----
    final = HistGradientBoostingRegressor(
        max_iter=400, learning_rate=0.05, max_depth=4, l2_regularization=1.0,
        min_samples_leaf=60, monotonic_cst=MONO, random_state=0)
    final.fit(df[FEATURES], df["k_true"])
    out_path = os.path.join(ROOT, "core", "models", "separation_ml.pkl")
    joblib.dump({"model": final, "features": FEATURES}, out_path)
    print(f"\n  [saved] final separation model -> {out_path}")

    # ---- figure: fixed-tilt (tie) vs tracker (ML wins) ----
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = list(methods.keys())
    rmses_fx = [metr(poa_ref, poa(df, df["ghi_satellite"], *methods[n]), m)[0] for n in names]
    rmses_tr = [metr(poa_ref_tr, poa_track(df["ghi_satellite"], *methods[n]), mt)[0] for n in names]
    col = ["#C0392B", "#95A5A6", "#95A5A6", "#95A5A6", "#28B463"]
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.8))
    for a, vals, title, raw in [(ax[0], rmses_fx, "Fixed tilt (near-equator): all decomps tie", rmses_fx[0]),
                                (ax[1], rmses_tr, "Single-axis tracker: only ML beats raw", rmses_tr[0])]:
        a.bar(names, vals, color=col)
        a.axhline(raw, color="#C0392B", ls="--", lw=1, label="raw satellite")
        a.set_ylabel("POA RMSE (W/m²)"); a.set_title(title, fontsize=10)
        a.tick_params(axis="x", rotation=25); a.legend(fontsize=8)
        for i, v in enumerate(vals): a.text(i, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    fig.tight_layout()
    fp = os.path.join(ROOT, "reports", "figures", "ml_separation_poa.png")
    fig.savefig(fp, dpi=130)
    print(f"  [saved] figure -> {fp}")


if __name__ == "__main__":
    main()

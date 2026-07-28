"""
exp_components.py — Is there a defensible, BANKABLE win in the irradiance components?

NASA POWER GHI is accurate but its DNI/DHI split is broken (closure off by ~46 W/m²,
diffuse fraction 0.58 vs ground 0.67). A fixed-tilt PV plant converts PLANE-OF-ARRAY
(POA) irradiance, transposed from GHI+DNI+DHI — so a bad split corrupts bankable energy
even when GHI is right.

Test: keep the accurate satellite GHI, re-derive a physically-consistent DNI/DHI split
via separation models (Erbs, DIRINT), transpose to POA, and compare against POA built
from the raw (inconsistent) satellite components. Reference = POA from ground components.

Tilt = latitude, south-facing. Validated on Tier-1 references.
"""
import os, sys
import numpy as np
import pandas as pd
import pvlib

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from scripts.exp_foundation import TIER1, CLEAN


def geom(df):
    out = []
    for st, g in df.groupby("station"):
        g = g.sort_values("timestamp").copy()
        lat, lon = g["latitude"].iloc[0], g["longitude"].iloc[0]
        loc = pvlib.location.Location(latitude=lat, longitude=lon)
        t = pd.DatetimeIndex(g["timestamp"])
        sp = loc.get_solarposition(t)
        g["zenith"] = sp["apparent_zenith"].values
        g["azimuth"] = sp["azimuth"].values
        g["dni_extra"] = pvlib.irradiance.get_extra_radiation(t).values
        g["airmass"] = pvlib.atmosphere.get_relative_airmass(sp["apparent_zenith"].clip(lower=0.01).values)
        g["tilt"] = abs(lat)
        g["lat"] = lat
        out.append(g)
    return pd.concat(out, ignore_index=True)


def poa(df, ghi, dni, dhi):
    r = pvlib.irradiance.get_total_irradiance(
        surface_tilt=df["tilt"].values, surface_azimuth=180.0,
        solar_zenith=df["zenith"].values, solar_azimuth=df["azimuth"].values,
        dni=np.asarray(dni), ghi=np.asarray(ghi), dhi=np.asarray(dhi),
        dni_extra=df["dni_extra"].values, airmass=df["airmass"].values,
        model="haydavies")
    return np.asarray(r["poa_global"])


def stats(yt, yp, m):
    e = (yp - yt)[m]
    return f"RMSE={np.sqrt(np.mean(e**2)):6.1f}  bias={np.mean(e):+6.1f}"


def main():
    df = pd.read_parquet(CLEAN)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df[df["station"].isin(TIER1)].copy()
    df = geom(df)
    df = df[(df["ghi_ground"] > 10) & (df["ghi_satellite"] > 0) & (df["zenith"] < 88)].copy().reset_index(drop=True)
    cz = np.cos(np.radians(df["zenith"].clip(0, 89)))
    t = pd.DatetimeIndex(df["timestamp"])

    # Reference POA from GROUND components
    poa_ref = poa(df, df["ghi_ground"], df["dni_ground"], df["dhi_ground"])

    # Raw satellite POA (inconsistent components)
    poa_raw = poa(df, df["ghi_satellite"], df["dni_satellite"], df["dhi_satellite"])

    # --- Reconstruct consistent split from accurate satellite GHI ---
    # Erbs: GHI -> diffuse fraction -> DNI/DHI (physical, no training)
    erbs = pvlib.irradiance.erbs(df["ghi_satellite"].values, df["zenith"].values, t)
    poa_erbs = poa(df, df["ghi_satellite"], erbs["dni"].values, erbs["dhi"].values)

    # DIRINT: GHI -> DNI (uses stability + zenith), DHI closed from GHI
    dni_dirint = pvlib.irradiance.dirint(df["ghi_satellite"].values, df["zenith"].values, t)
    dni_dirint = np.nan_to_num(dni_dirint, nan=0.0)
    dhi_dirint = np.maximum(df["ghi_satellite"].values - dni_dirint * cz.values, 0.0)
    poa_dirint = poa(df, df["ghi_satellite"], dni_dirint, dhi_dirint)

    m = np.isfinite(poa_ref) & (poa_ref > 10)
    mean_poa = poa_ref[m].mean()
    print("=" * 66)
    print(f"  BANKABLE POA IRRADIANCE (fixed tilt=|lat|, south)  n={m.sum():,}  mean={mean_poa:.0f} W/m²")
    print("  Reference = POA from GROUND components")
    print("=" * 66)
    print(f"  {'POA source':<34}{'metrics':<28}{'ΔRMSE':>8}")
    base = np.sqrt(np.mean((poa_raw[m]-poa_ref[m])**2))
    for name, p in [("raw satellite components", poa_raw),
                    ("GHI + Erbs split", poa_erbs),
                    ("GHI + DIRINT split", poa_dirint)]:
        rmse = np.sqrt(np.mean((p[m]-poa_ref[m])**2))
        d = (1 - rmse/base) * 100 if name != "raw satellite components" else 0.0
        print(f"  {name:<34}{stats(poa_ref, p, m):<28}{d:>+7.1f}%")

    # ---- bankable money figure: POA bias + RMSE ----
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    srcs = ["raw satellite\ncomponents", "GHI + Erbs\nsplit", "GHI + DIRINT\nsplit"]
    poas = [poa_raw, poa_erbs, poa_dirint]
    biases = [np.mean((p-poa_ref)[m]) for p in poas]
    rmses = [np.sqrt(np.mean(((p-poa_ref)[m])**2)) for p in poas]
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))
    c = ["#C0392B", "#28B463", "#2E86C1"]
    ax[0].bar(srcs, biases, color=c); ax[0].axhline(0, color="k", lw=.8)
    ax[0].set_ylabel("POA bias (W/m²)"); ax[0].set_title("Bankable POA bias: raw split loses ~9%")
    for i, b in enumerate(biases): ax[0].text(i, b, f"{b:+.0f}", ha="center", va="bottom" if b>0 else "top")
    ax[1].bar(srcs, rmses, color=c)
    ax[1].set_ylabel("POA RMSE (W/m²)"); ax[1].set_title("POA RMSE vs ground reference")
    for i, r in enumerate(rmses): ax[1].text(i, r, f"{r:.0f}", ha="center", va="bottom")
    fig.tight_layout()
    fp = os.path.join(ROOT, "reports", "figures", "poa_decomposition_fix.png")
    os.makedirs(os.path.dirname(fp), exist_ok=True); fig.savefig(fp, dpi=130)
    print(f"\n  [saved bankable POA figure] {fp}")

    print("\n" + "=" * 66)
    print("  Component-level check (satellite vs ground)")
    print("=" * 66)
    for label, dni, dhi in [("raw satellite", df["dni_satellite"].values, df["dhi_satellite"].values),
                            ("Erbs split", erbs["dni"].values, erbs["dhi"].values),
                            ("DIRINT split", dni_dirint, dhi_dirint)]:
        md = np.isfinite(dni) & (df["dni_ground"].values > 10)
        mh = np.isfinite(dhi) & (df["dhi_ground"].values > 10)
        print(f"  {label:<16} DNI[{stats(df['dni_ground'].values, dni, md)}]   "
              f"DHI[{stats(df['dhi_ground'].values, dhi, mh)}]")
    print("\n  If a GHI-preserving reconstruction beats raw components on POA, the bankable")
    print("  win is the DECOMPOSITION — and an ML separation model (Engerer/Yang family,")
    print("  trained on these features) is the defensible upgrade over Erbs/DIRINT.")


if __name__ == "__main__":
    main()

"""
Layer 6 (ML-B): Uncertainty quantification — the bankable P50/P90/P99.

The physics layer is deterministic: one energy number. Lenders underwrite on the
EXCEEDANCE probability (P90 = value exceeded 90% of years), which the physics cannot
provide. This layer supplies the calibrated risk envelope, in two tiers:

  1. Hourly, regime-conditional CONFORMAL intervals on irradiance — distribution-free,
     empirically calibrated (see scripts/train_uncertainty.py: reliability on the
     diagonal, P90 coverage ~90%). This is the honesty proof.

  2. Annual ENERGY P50/P90/P99 — the number in the report. Hourly random scatter
     averages down over a year, so annual uncertainty is dominated by the SYSTEMATIC
     model uncertainty (does not average down) combined in quadrature with INTERANNUAL
     variability (year-to-year weather). Standard solar-finance aggregation.

Calibration artifact: core/models/uncertainty_calib.json (built by train_uncertainty.py).
"""
import os
import json
import numpy as np
import pandas as pd

# Normal exceedance z-scores: P(X >= P50 + z*sigma) = level
Z = {"p50": 0.0, "p75": -0.6745, "p90": -1.2816, "p95": -1.6449, "p99": -2.3263}

# West-Africa savanna interannual GHI variability prior (coefficient of variation).
# Used only when a site-specific multi-year record is not supplied.
DEFAULT_IAV_COV = 0.035


class UncertaintyLayer:
    def __init__(self, calib_path="core/models/uncertainty_calib.json"):
        self.calib_path = calib_path
        self.calib = None
        self.sigma_model_cov = 0.02   # annual systematic model uncertainty (fraction)
        self.kt_bins = [0, .3, .5, .65, .8, 1.3]
        self.elev_bins = [0, 15, 30, 50, 90]
        self.taus = [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]
        self._resid_q = None
        if os.path.exists(calib_path):
            try:
                with open(calib_path) as f:
                    self.calib = json.load(f)
                self.sigma_model_cov = float(self.calib.get("sigma_model_cov", self.sigma_model_cov))
                self.kt_bins = self.calib.get("kt_bins", self.kt_bins)
                self.elev_bins = self.calib.get("elev_bins", self.elev_bins)
                self.taus = self.calib.get("taus", self.taus)
                self._resid_q = self.calib.get("residual_quantiles", None)
            except Exception:
                self.calib = None

    # ---- interannual variability ----
    def interannual_cov(self, annual_ghi_by_year=None):
        """CoV of annual GHI from a multi-year record; regional prior if unavailable.
        annual_ghi_by_year: 1-D array/list of yearly GHI totals (>=5 years recommended)."""
        if annual_ghi_by_year is not None:
            a = np.asarray(annual_ghi_by_year, dtype=float)
            a = a[np.isfinite(a) & (a > 0)]
            if len(a) >= 3:
                return float(np.std(a, ddof=1) / np.mean(a))
        return DEFAULT_IAV_COV

    # ---- annual energy P50/P90/P99 (the bankable number) ----
    def energy_percentiles(self, p50_energy_kwh, annual_ghi_by_year=None,
                           model_cov=None, iav_cov=None):
        """Return P50/P75/P90/P95/P99 annual energy + a transparent breakdown."""
        m = self.sigma_model_cov if model_cov is None else float(model_cov)
        v = self.interannual_cov(annual_ghi_by_year) if iav_cov is None else float(iav_cov)
        total_cov = float(np.sqrt(m ** 2 + v ** 2))
        out = {k: float(p50_energy_kwh * (1.0 + z * total_cov)) for k, z in Z.items()}
        out["breakdown"] = {
            "model_cov": m, "interannual_cov": v, "total_cov": total_cov,
            "p90_over_p50": out["p90"] / out["p50"] if out["p50"] else None,
        }
        return out

    # ---- hourly conformal intervals (QC / plotting / calibration proof) ----
    def _regime_key(self, kt, elev):
        return int(np.digitize(kt, self.kt_bins) * 10 + np.digitize(elev, self.elev_bins))

    def hourly_intervals(self, ghi_point, kt, elevation, taus=None):
        """Regime-conditional conformal interval on irradiance:
        interval bound = point + residual_quantile(regime). Returns {tau: array}."""
        if self._resid_q is None:
            return None
        taus = taus or self.taus
        ghi_point = np.asarray(ghi_point, float)
        kt = np.asarray(kt, float); elevation = np.asarray(elevation, float)
        glob = self._resid_q.get("global", {})
        out = {}
        for t in taus:
            ts = f"{t:.2f}"
            q = np.array([
                self._resid_q.get(str(self._regime_key(kt[i], elevation[i])), {}).get(ts,
                    glob.get(ts, 0.0))
                for i in range(len(ghi_point))])
            out[t] = np.maximum(ghi_point + q, 0.0)
        return out

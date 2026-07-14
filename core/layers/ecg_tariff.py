"""
ECG Tariff Engine — Electricity Company of Ghana
Tariff Reckoner effective 1st May 2025

This module provides:
- Lookup tables for RESIDENTIAL and NON-RESIDENTIAL customers
- Interpolation to get the monthly bill for any consumption (kWh)
- Effective rate calculation (GH₵/kWh)
- Reverse lookup: estimate kWh from a monthly bill amount
- Annual savings calculation for financial modelling
"""

import bisect

# ─────────────────────────────────────────────────────────────────────────────
# RESIDENTIAL Lookup Table
# Format: {kWh: total_monthly_bill_GHS}
# Source: ECG Electricity Tariff Reckoner, Effective 1st May 2025
# ─────────────────────────────────────────────────────────────────────────────
RESIDENTIAL_TABLE = {
    0: 2.13,
    1: 3.98,
    2: 5.83,
    3: 7.68,
    4: 9.51,
    5: 11.36,
    10: 20.60,
    20: 39.06,
    25: 48.30,
    30: 57.53,   # Last lifeline block
    31: 67.98,
    35: 75.36,
    40: 84.60,
    45: 93.82,
    50: 103.07,
    51: 104.90,
    55: 112.29,
    60: 121.53,
    65: 130.77,
    70: 139.99,
    75: 149.23,
    80: 158.46,
    100: 195.40,
    110: 213.86,
    120: 232.32,
    130: 250.79,
    140: 269.26,
    150: 287.73,
    151: 289.57,
    160: 306.19,
    170: 324.66,
    180: 343.13,
    190: 361.58,
    200: 380.05,
    210: 398.53,
    220: 416.99,
    230: 435.46,
    240: 453.92,
    250: 472.39,
    260: 490.86,
    270: 509.33,
    280: 527.79,
    290: 546.25,
    300: 564.72,
    301: 567.16,
    310: 589.13,
    320: 613.52,
    330: 637.93,
    340: 662.33,
    350: 686.73,
    550: 1174.75,
    600: 1296.75,
    601: 1299.18,
    650: 1418.76,
    700: 1540.76,
    750: 1662.77,
    800: 1784.77,
    850: 1906.78,
    900: 2028.78,
    950: 2150.78,
    1000: 2272.79,
    1050: 2394.80,
    1100: 2516.79,
    1200: 2760.80,
    1300: 3004.82,
    1400: 3248.83,
    1500: 3492.84,
    2000: 4712.88,
    2500: 5932.93,
    3000: 7152.97,
    3500: 8373.02,
    4000: 9593.07,
    4500: 10813.12,
    5000: 12033.17,
    10000: 24233.64,
}

# ─────────────────────────────────────────────────────────────────────────────
# NON-RESIDENTIAL Lookup Table
# Format: {kWh: total_monthly_bill_GHS}  (includes NHIL/GETFund + 15% VAT)
# Source: ECG Electricity Tariff Reckoner, Effective 1st May 2025
# ─────────────────────────────────────────────────────────────────────────────
NON_RESIDENTIAL_TABLE = {
    0: 14.92,
    1: 16.90,
    2: 18.89,
    3: 20.87,
    4: 22.86,
    5: 24.84,
    10: 34.77,
    20: 54.62,
    25: 64.54,
    30: 74.46,
    31: 76.44,
    35: 84.39,
    40: 94.32,
    45: 104.24,
    50: 114.17,
    51: 116.14,
    55: 124.08,
    60: 134.01,
    65: 143.93,
    70: 153.85,
    75: 163.77,
    80: 173.70,
    100: 213.40,
    110: 233.25,
    120: 253.11,
    130: 272.95,
    140: 292.81,
    150: 312.65,
    151: 314.63,
    160: 332.49,
    170: 352.34,
    180: 372.19,
    190: 392.04,
    200: 411.89,
    210: 431.74,
    220: 451.59,
    230: 471.44,
    240: 491.29,
    250: 511.14,
    260: 530.99,
    270: 550.82,
    280: 570.68,
    290: 590.52,
    300: 610.38,
    301: 612.84,
    310: 635.04,
    320: 659.72,
    330: 684.38,
    340: 709.05,
    350: 733.71,
    550: 1227.04,
    600: 1350.37,
    601: 1352.83,
    650: 1473.70,
    700: 1597.02,
    750: 1720.37,
    800: 1843.69,
    850: 1967.02,
    900: 2090.36,
    950: 2213.69,
    1000: 2337.01,
    1050: 2460.36,
    1100: 2583.68,
    1200: 2830.34,
    1300: 3077.00,
    1400: 3323.67,
    1500: 3570.33,
    2000: 4803.64,
    2500: 6036.95,
    3000: 7270.27,
    3500: 8503.58,
    4000: 9736.89,
    4500: 10970.20,
    5000: 12203.52,
    10000: 24536.64,
}


class ECGTariff:
    """
    ECG May 2025 Tariff Engine.
    Supports RESIDENTIAL and NON-RESIDENTIAL customer types.
    Uses linear interpolation between reckoner table breakpoints.
    """

    CUSTOMER_TYPES = ("residential", "non_residential")

    def __init__(self):
        self._tables = {
            "residential": RESIDENTIAL_TABLE,
            "non_residential": NON_RESIDENTIAL_TABLE,
        }
        # Pre-sort keys for bisect lookups
        self._keys = {
            k: sorted(v.keys()) for k, v in self._tables.items()
        }

    def _validate(self, customer_type: str):
        ct = customer_type.lower().replace("-", "_").replace(" ", "_")
        if ct not in self.CUSTOMER_TYPES:
            raise ValueError(
                f"Unknown customer_type '{customer_type}'. "
                f"Must be one of: {self.CUSTOMER_TYPES}"
            )
        return ct

    def get_monthly_bill(self, kwh: float, customer_type: str = "residential") -> float:
        """
        Return the total monthly bill (GH₵) for a given consumption in kWh.
        Uses linear interpolation between reckoner table breakpoints.
        """
        ct = self._validate(customer_type)
        table = self._tables[ct]
        keys = self._keys[ct]

        kwh = max(0.0, kwh)

        # If exact value exists in table
        if kwh in table:
            return table[kwh]

        # Clamp to table bounds
        if kwh <= keys[0]:
            return table[keys[0]]
        if kwh >= keys[-1]:
            # Extrapolate linearly beyond last point using last two points
            x0, x1 = keys[-2], keys[-1]
            y0, y1 = table[x0], table[x1]
            rate = (y1 - y0) / (x1 - x0)
            return y1 + rate * (kwh - x1)

        # Linear interpolation between surrounding table points
        idx = bisect.bisect_right(keys, kwh)
        x0, x1 = keys[idx - 1], keys[idx]
        y0, y1 = table[x0], table[x1]
        t = (kwh - x0) / (x1 - x0)
        return y0 + t * (y1 - y0)

    def get_effective_rate(self, kwh: float, customer_type: str = "residential") -> float:
        """
        Return the blended effective tariff rate (GH₵/kWh) for a given monthly consumption.
        This is the 'total bill / kWh' — i.e., what each kWh costs you on average including
        all levies, charges, and taxes.
        """
        if kwh <= 0:
            return 0.0
        bill = self.get_monthly_bill(kwh, customer_type)
        return bill / kwh

    def get_kwh_from_bill(self, monthly_bill_ghs: float, customer_type: str = "residential") -> float:
        """
        Reverse lookup: given a monthly bill in GH₵, estimate the corresponding
        monthly consumption in kWh. Uses linear interpolation on the sorted bill values.
        """
        ct = self._validate(customer_type)
        table = self._tables[ct]
        keys = self._keys[ct]

        # Build sorted (bill, kwh) pairs
        bill_kwh = sorted((table[k], k) for k in keys)
        bills = [b for b, _ in bill_kwh]
        kwhs = [k for _, k in bill_kwh]

        if monthly_bill_ghs <= bills[0]:
            return kwhs[0]
        if monthly_bill_ghs >= bills[-1]:
            # Extrapolate
            rate = (kwhs[-1] - kwhs[-2]) / (bills[-1] - bills[-2])
            return kwhs[-1] + rate * (monthly_bill_ghs - bills[-1])

        idx = bisect.bisect_right(bills, monthly_bill_ghs)
        b0, b1 = bills[idx - 1], bills[idx]
        k0, k1 = kwhs[idx - 1], kwhs[idx]
        t = (monthly_bill_ghs - b0) / (b1 - b0)
        return k0 + t * (k1 - k0)

    def get_annual_savings(self, annual_kwh: float, customer_type: str = "residential",
                           tariff_escalation_rate: float = 0.03) -> list:
        """
        Compute annual grid bill savings over a 25-year lifetime with tariff escalation.
        Returns a list of 25 annual savings values (GH₵).

        Uses monthly average consumption to look up the correct tariff tier.
        Savings = what the customer would have paid the grid, avoided by solar.
        """
        monthly_kwh = annual_kwh / 12.0
        base_monthly_bill = self.get_monthly_bill(monthly_kwh, customer_type)
        base_annual_bill = base_monthly_bill * 12.0

        savings = []
        for year in range(1, 26):
            escalated = base_annual_bill * ((1 + tariff_escalation_rate) ** (year - 1))
            savings.append(escalated)
        return savings

    def get_tariff_summary(self) -> dict:
        """
        Returns a summary of effective rates at common consumption levels,
        useful for displaying in the frontend.
        """
        breakpoints = [50, 100, 200, 300, 500, 1000]
        return {
            "source": "ECG Electricity Tariff Reckoner, Effective 1st May 2025",
            "residential": [
                {
                    "kwh": k,
                    "monthly_bill": round(self.get_monthly_bill(k, "residential"), 2),
                    "effective_rate": round(self.get_effective_rate(k, "residential"), 4),
                }
                for k in breakpoints
            ],
            "non_residential": [
                {
                    "kwh": k,
                    "monthly_bill": round(self.get_monthly_bill(k, "non_residential"), 2),
                    "effective_rate": round(self.get_effective_rate(k, "non_residential"), 4),
                }
                for k in breakpoints
            ],
        }

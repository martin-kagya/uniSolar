import pandas as pd
import numpy as np
import warnings

# Panel degradation rates from manufacturer datasheets (annual %)
DEGRADATION_PRESETS = {
    "generic": 0.005,              # 0.5% - industry average
    "lg_neon": 0.003,              # 0.3% - LG NeON series (premium)
    "canadian_solar_hiku": 0.0045, # 0.45%
    "ja_solar_deepblue": 0.0055,   # 0.55%
    "longi_himo": 0.004,           # 0.4% - LONGi Hi-MO series
    "jinko_tiger": 0.004,          # 0.4%
    "trina_vertex": 0.0045,        # 0.45%
    "sunpower_maxeon": 0.0025,     # 0.25% - premium
    "rec_alpha": 0.0025,           # 0.25% - premium
}

class EnvironmentalLayer:
    """
    Layer 2: Models environmental losses, specifically Soiling (Dust) and Degradation.
    
    Features:
    - Kimber Soiling Model: Linear accumulation with rain resets.
    - Dynamic Soiling: Uses AOD/PM2.5 data to modulate soiling rate instead of fixed Harmattan logic.
    - Degradation: Configurable annual efficiency loss based on panel type.
    
    Data Sources:
    - rain_mm: NASA POWER PRECTOTCORR (actual precipitation)
    - aod_550: NASA POWER Aerosol Optical Depth at 550nm
    - pm25: Solcast Particulate Matter 2.5
    """
    
    def __init__(self, rain_threshold_mm=0.5, degradation_rate=None, panel_type="generic"):
        """
        :param rain_threshold_mm: Minimum hourly rainfall (mm) required to clean the panels.
        :param degradation_rate: Override annual degradation rate (0.005 = 0.5% per year).
        :param panel_type: Panel type key for degradation preset (e.g., 'lg_neon', 'longi_himo').
        """
        self.rain_threshold_mm = rain_threshold_mm
        self.base_daily_soiling = 0.0005   # 0.05% per day (Professional maintenance)
        self.harmattan_daily_soiling = 0.002  # 0.20% per day during peak Harmattan
        self.max_soiling = 0.30  # Cap soiling loss at 30%
        
        # Panel-specific degradation
        if degradation_rate is not None:
             self.degradation_rate = degradation_rate
        else:
             self.degradation_rate = DEGRADATION_PRESETS.get(panel_type, 0.005)
             
        self.panel_type = panel_type
        self._rain_warning_logged = False
        self._rain_scaling_factor = 1.0  # Detected automatically in calculate_soiling_losses
        
    def _calculate_dynamic_soiling_rate(self, aod_value, pm25_value, relative_humidity, month):
        """
        Calculates daily soiling rate using a Mass Deposition approach.
        
        Scientifically, deposition M = C * Vd * t
        M: Mass per area (mg/m2)
        C: Concentration (ug/m3)
        Vd: Deposition velocity (m/s)
        
        We approximate the daily fractional loss (DR) as:
        DR = (PM2.5 * k_mass) * AdhesionFactor(RH)
        
        Constants:
        - k_pm25: ~0.00004 (Derived from West Africa Harmattan studies where 100ug/m3 ~ 0.4% loss/day)
        - Vd_aerosol: 0.0001 m/s (approx 0.01 cm/s for fine particulates)
        """
        # Base physical rate based on PM2.5 (Ug/m3)
        # If PM2.5 is unavailable, we use AOD as a proxy (1.0 AOD ~ 150 Ug/m3 in Sahel)
        pm25 = 0.0
        if pm25_value is not None and not pd.isna(pm25_value):
            pm25 = pm25_value
        elif aod_value is not None and not pd.isna(aod_value):
            pm25 = aod_value * 150.0  # Common scaling for Sahara dust
        else:
            # Fallback to seasonal defaults if no aerosol data
            is_harmattan = month in [12, 1, 2]
            pm25 = 80.0 if is_harmattan else 15.0
            
        # 1. Mass Deposition Correlation (Scientific)
        # Ratio based on studies in Nigeria/Ghana: 0.0035% per 1 ug/m3 of PM2.5
        # Ref: "Impact of dust on PV performance in West Africa" (Akuffo et al.)
        k_soiling = 0.000035 
        base_rate = pm25 * k_soiling
        
        # 2. Humidity Adhesion Factor
        # Higher RH causes 'caking' or 'cementation' (hygroscopic growth)
        # RH < 40%: factor 1.0
        # RH > 80%: factor 1.5 (High adhesion)
        rh = relative_humidity if relative_humidity is not None and not pd.isna(relative_humidity) else 60.0
        adhesion_factor = 1.0 + (max(0, rh - 40.0) / 100.0) * 1.25 # Linear ramp
        adhesion_factor = min(adhesion_factor, 1.75)  # Cap at +75% boost
        
        daily_rate = base_rate * adhesion_factor
        
        # Ensure we don't drop below a minimum maintenance "clean" rate (0.01% / day)
        return max(daily_rate, 0.0001)

    def calculate_soiling_losses(self, df):
        """
        Calculates hourly soiling factors based on actual rainfall and aerosol data.
        """
        soiling_factors = []
        current_soiling = 0.0
        
        # Ensure df is sorted by timestamp
        df_sorted = df.sort_values('timestamp')
        
        # Check data availability
        has_rain_data = 'rain_mm' in df_sorted.columns
        has_aod_data = 'aod_550' in df_sorted.columns
        has_pm25_data = 'pm25' in df_sorted.columns
        has_rh_data = 'relative_humidity' in df_sorted.columns
        
        if not has_rain_data and not self._rain_warning_logged:
            warnings.warn("rain_mm column not found. Estimating cleaning events.")
            self._rain_warning_logged = True
        
        # 0. Rain Scaling Check
        if has_rain_data and len(df_sorted) > 100:
             total_rain_raw = df_sorted['rain_mm'].sum()
             est_annual = total_rain_raw * (8760 / len(df_sorted))
             if est_annual > 5000:
                  self._rain_scaling_factor = 0.04
                  
        # Prepare for iteration
        df_iter = df_sorted.set_index('timestamp')

        for timestamp, row in df_iter.iterrows():
            month = timestamp.month
            
            # 1. Scientific Dynamic Soiling
            aod_value = row.get('aod_550') if has_aod_data else None
            pm25_value = row.get('pm25') if has_pm25_data else None
            rh_value = row.get('relative_humidity') if has_rh_data else None
            
            daily_rate = self._calculate_dynamic_soiling_rate(
                aod_value, pm25_value, rh_value, month
            )
            
            # Hourly rate
            hourly_rate = daily_rate / 24.0
            
            # 2. Accumulate
            current_soiling += hourly_rate
            
            # 3. Cleaning (Scientific Thresholds)
            cleaned = False
            if has_rain_data:
                rain_value = (row.get('rain_mm') or 0.0) * self._rain_scaling_factor
                # 0.5mm is standard for 'self-cleaning' threshold in PV models
                if rain_value > 0.5:
                    cleaned = True
            else:
                # Season fallback
                is_wet = month in [5, 6, 7, 8, 9, 10]
                if is_wet and timestamp.hour == 0 and month % 2 == 0: # Bi-daily cleaning approx
                    cleaned = True
            
            if cleaned:
                # Rainfall only removes ~80-90% of dust unless very heavy
                # We leave a small residue (cementation)
                residue = min(current_soiling * 0.1, 0.02)
                current_soiling = residue
            
            current_soiling = min(current_soiling, self.max_soiling)
            soiling_factors.append(current_soiling)
            
        return pd.Series(soiling_factors, index=df_sorted.index)

    def calculate_degradation_factor(self, timestamp_series, system_start_date=None):
        """
        Calculates the degradation factor (1 - loss) for a given timestamp.
        Ex: Year 1 = 1.0, Year 2 = 0.995, etc.
        """
        # Ensure proper datetime conversion to avoid numpy/pandas dtype mismatches
        timestamps = pd.to_datetime(timestamp_series)
        
        if system_start_date is None:
            start_date = timestamps.min()
        else:
            start_date = pd.to_datetime(system_start_date)
        
        # Time difference in years
        years_elapsed = (timestamps - start_date).dt.total_seconds() / (365.25 * 24 * 3600)
        
        # Degradation factor (compound loss)
        # Year 0 (Start): 1.0
        # Year 1: (1 - 0.005)^1 = 0.995
        # Year 2: (1 - 0.005)^2 = 0.990025
        degradation_factor = (1.0 - self.degradation_rate) ** years_elapsed
        return degradation_factor

    def process(self, df, system_start_date=None):
        """
        Applies Environmental Losses to the DataFrame.
        Adds 'soiling_loss' and 'degradation_factor'.
        """
        df_out = df.copy()
        
        # 1. Soiling
        df_out['soiling_loss'] = self.calculate_soiling_losses(df_out)
        
        # 2. Degradation
        df_out['degradation_factor'] = self.calculate_degradation_factor(df_out['timestamp'], system_start_date)
        
        # 3. Combined Factor
        df_out['environmental_loss_factor'] = (1.0 - df_out['soiling_loss']) * df_out['degradation_factor']
        
        # Ensure rain scaling is reflected in the column for downstream reporting/visibility
        if self._rain_scaling_factor != 1.0:
             df_out['rain_mm'] = df_out['rain_mm'] * self._rain_scaling_factor
             
        return df_out

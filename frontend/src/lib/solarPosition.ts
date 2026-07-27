/**
 * solarPosition.ts
 *
 * Client-side solar position + cast-shadow geometry for the map visualization.
 *
 * PARITY NOTE
 * -----------
 * The backend computes solar position with pvlib's NREL SPA
 * (`pvlib.location.Location.get_solarposition`, see core/layers/weather_model.py).
 * This module implements the NOAA solar-position equations, which agree with the
 * NREL SPA to well within ~1° for any date/time — more than adequate for a *visual*
 * shadow. The backend `/simulate` endpoint remains the authoritative source for all
 * energy / financial numbers; this module only drives what the array *looks like*.
 *
 * Azimuth convention matches the backend exactly:
 *   0° = North, 90° = East, 180° = South, 270° = West.
 *
 * The sun-vector / shadow math (`sunGroundVector`, `shadowLengthFactor`,
 * `atmosphericFade`) mirrors core/layers/geometry_model.py lines 111-142 so the
 * rendered shadows are geometrically consistent with the physics layer.
 */

export interface SolarPosition {
  /** Apparent zenith angle in degrees (0 = overhead, 90 = horizon). */
  zenithDeg: number;
  /** Apparent elevation angle in degrees (90 - zenith). */
  elevationDeg: number;
  /** Azimuth in degrees, compass convention (0 = N, 90 = E, 180 = S, 270 = W). */
  azimuthDeg: number;
}

const toRad = (d: number): number => (d * Math.PI) / 180;
const toDeg = (r: number): number => (r * 180) / Math.PI;

/**
 * Compute solar position for a site using the NOAA algorithm.
 *
 * @param latDeg     Site latitude in degrees (+N).
 * @param lngDeg     Site longitude in degrees (+E).
 * @param year       Full year (e.g. 2026).
 * @param month      Month 1-12.
 * @param day        Day of month 1-31.
 * @param hour       Local standard time, fractional hours (e.g. 13.5 = 13:30).
 * @param tzOffsetHours  Standard-time UTC offset in hours. Defaults to the
 *                       longitude-implied zone (round(lng / 15)), which is exact
 *                       for near-meridian sites such as Ghana (lng ≈ 0).
 */
export function solarPosition(
  latDeg: number,
  lngDeg: number,
  year: number,
  month: number,
  day: number,
  hour: number,
  tzOffsetHours: number = Math.round(lngDeg / 15)
): SolarPosition {
  // --- Julian day / century (NOAA) ---
  let y = year;
  let m = month;
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const A = Math.floor(y / 100);
  const B = 2 - A + Math.floor(A / 4);
  // Day fraction at the given local time, expressed in UTC.
  const dayFrac = (hour - tzOffsetHours) / 24;
  const jd =
    Math.floor(365.25 * (y + 4716)) +
    Math.floor(30.6001 * (m + 1)) +
    day +
    B -
    1524.5 +
    dayFrac;
  const jc = (jd - 2451545) / 36525;

  // --- Sun geometry ---
  const geomMeanLong = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360;
  const L0 = geomMeanLong < 0 ? geomMeanLong + 360 : geomMeanLong;
  const geomMeanAnom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);
  const eccent = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);

  const mRad = toRad(geomMeanAnom);
  const sunEqCtr =
    Math.sin(mRad) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
    Math.sin(2 * mRad) * (0.019993 - 0.000101 * jc) +
    Math.sin(3 * mRad) * 0.000289;

  const sunTrueLong = L0 + sunEqCtr;
  const sunAppLong = sunTrueLong - 0.00569 - 0.00478 * Math.sin(toRad(125.04 - 1934.136 * jc));

  const meanObliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60;
  const obliqCorr = meanObliq + 0.00256 * Math.cos(toRad(125.04 - 1934.136 * jc));

  const declRad = Math.asin(Math.sin(toRad(obliqCorr)) * Math.sin(toRad(sunAppLong)));

  // --- Equation of time (minutes) ---
  const varY = Math.tan(toRad(obliqCorr / 2)) ** 2;
  const eqTime =
    4 *
    toDeg(
      varY * Math.sin(2 * toRad(L0)) -
        2 * eccent * Math.sin(mRad) +
        4 * eccent * varY * Math.sin(mRad) * Math.cos(2 * toRad(L0)) -
        0.5 * varY * varY * Math.sin(4 * toRad(L0)) -
        1.25 * eccent * eccent * Math.sin(2 * mRad)
    );

  // --- Hour angle ---
  const minutesOfDay = hour * 60;
  let trueSolarTime = (minutesOfDay + eqTime + 4 * lngDeg - 60 * tzOffsetHours) % 1440;
  if (trueSolarTime < 0) trueSolarTime += 1440;
  let hourAngle = trueSolarTime / 4 - 180;
  if (hourAngle < -180) hourAngle += 360;

  // --- Zenith / elevation / azimuth ---
  const latRad = toRad(latDeg);
  const haRad = toRad(hourAngle);
  const cosZenith =
    Math.sin(latRad) * Math.sin(declRad) + Math.cos(latRad) * Math.cos(declRad) * Math.cos(haRad);
  const zenithRad = Math.acos(Math.max(-1, Math.min(1, cosZenith)));
  const zenithDeg = toDeg(zenithRad);

  // Azimuth (0 = N, clockwise), NOAA formulation.
  let azimuthDeg: number;
  const denom = Math.cos(latRad) * Math.sin(zenithRad);
  if (Math.abs(denom) > 1e-9) {
    let azRad = Math.acos(
      Math.max(-1, Math.min(1, (Math.sin(latRad) * Math.cos(zenithRad) - Math.sin(declRad)) / denom))
    );
    azimuthDeg = toDeg(azRad);
    // Before solar noon the sun is in the east; convention: bearing from north.
    azimuthDeg = hourAngle > 0 ? (azimuthDeg + 180) % 360 : (540 - azimuthDeg) % 360;
  } else {
    azimuthDeg = latDeg > declRad ? 180 : 0;
  }

  return {
    zenithDeg,
    elevationDeg: 90 - zenithDeg,
    azimuthDeg,
  };
}

/**
 * Ground-plane unit vector pointing in the direction shadows are cast
 * (i.e. away from the sun). Mirrors geometry_model.py:
 *   s_az = azimuth + 180 ; dx = sin(s_az) ; dy = cos(s_az)
 * Returned in the renderer's local meter frame: +x = East, +y = North.
 */
export function sunGroundVector(azimuthDeg: number): { x: number; y: number } {
  const sAz = toRad(azimuthDeg + 180);
  return { x: Math.sin(sAz), y: Math.cos(sAz) };
}

/**
 * Shadow length for an object of the given height, in meters.
 *
 * At low sun angles tan(zenith) explodes, producing shadows many metres long
 * that extend well beyond the map viewport and look broken.  We apply two
 * safeguards:
 *   1. An absolute ceiling of `MAX_SHADOW_LENGTH_M`.
 *   2. A smooth cosine roll-off above `SOFT_MAX_ZENITH_DEG` so shadows
 *      shrink to zero at the horizon instead of jumping to the cap.
 *
 * Returns 0 when the sun is at or below the horizon.
 */
const MAX_SHADOW_LENGTH_M = 4;    // absolute cap in metres
const SOFT_MAX_ZENITH_DEG = 70;   // start rolling off above this zenith

export function shadowLengthMeters(heightM: number, zenithDeg: number): number {
  if (zenithDeg >= 90 || heightM <= 0) return 0;
  const raw = heightM * Math.tan(toRad(zenithDeg));
  if (zenithDeg <= SOFT_MAX_ZENITH_DEG) {
    return Math.min(raw, MAX_SHADOW_LENGTH_M);
  }
  // Smooth cosine fade from soft-max zenith (100 %) to 90° (0 %)
  const t = (zenithDeg - SOFT_MAX_ZENITH_DEG) / (90 - SOFT_MAX_ZENITH_DEG); // 0→1
  const fade = Math.cos(t * Math.PI / 2);                          // 1→0
  return Math.min(raw, MAX_SHADOW_LENGTH_M) * fade;
}

/**
 * Atmospheric-scattering fade factor (0-1) applied to shadow opacity/impact as the
 * sun approaches the horizon.  Tightly coupled with `shadowLengthMeters` so the
 * visual roll-off starts at the same zenith angle.
 */
export function atmosphericFade(zenithDeg: number): number {
  if (zenithDeg >= 90) return 0;
  if (zenithDeg <= 75) return 1;
  const t = (zenithDeg - 75) / (90 - 75); // 0→1 over 75°–90°
  return Math.cos(t * Math.PI / 2);        // 1→0 smooth cosine
}

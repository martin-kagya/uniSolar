import { describe, it, expect } from 'vitest';
import {
  solarPosition,
  sunGroundVector,
  shadowLengthMeters,
  atmosphericFade,
} from '../lib/solarPosition';

// Ghana site used across the app.
const LAT = 8.2615;
const LNG = -2.2455;

describe('solarPosition (NOAA)', () => {
  it('puts the sun high near solar noon in June', () => {
    const s = solarPosition(LAT, LNG, 2026, 6, 21, 12);
    expect(s.zenithDeg).toBeGreaterThanOrEqual(0);
    expect(s.zenithDeg).toBeLessThanOrEqual(90);
    expect(s.elevationDeg).toBeGreaterThan(60); // very high sun at this latitude/date
    expect(s.azimuthDeg).toBeGreaterThanOrEqual(0);
    expect(s.azimuthDeg).toBeLessThan(360);
  });

  it('places the morning sun in the east and afternoon sun in the west', () => {
    const morning = solarPosition(LAT, LNG, 2026, 3, 21, 8);
    const afternoon = solarPosition(LAT, LNG, 2026, 3, 21, 16);
    // Convention: 0=N, 90=E, 180=S, 270=W
    expect(morning.azimuthDeg).toBeGreaterThan(45);
    expect(morning.azimuthDeg).toBeLessThan(135);
    expect(afternoon.azimuthDeg).toBeGreaterThan(225);
    expect(afternoon.azimuthDeg).toBeLessThan(315);
  });

  it('has the sun below the horizon at night', () => {
    const night = solarPosition(LAT, LNG, 2026, 6, 21, 0);
    expect(night.elevationDeg).toBeLessThan(0);
  });
});

describe('sunGroundVector (shadow direction = away from sun)', () => {
  it('sun in the east casts shadows to the west (-x)', () => {
    const v = sunGroundVector(90);
    expect(v.x).toBeCloseTo(-1, 6);
    expect(v.y).toBeCloseTo(0, 6);
  });

  it('sun in the south casts shadows to the north (+y)', () => {
    const v = sunGroundVector(180);
    expect(v.x).toBeCloseTo(0, 6);
    expect(v.y).toBeCloseTo(1, 6);
  });
});

describe('shadowLengthMeters', () => {
  it('is zero for an overhead sun and grows as it lowers', () => {
    expect(shadowLengthMeters(1, 0)).toBeCloseTo(0, 6);
    expect(shadowLengthMeters(1, 45)).toBeCloseTo(1, 6);
    expect(shadowLengthMeters(2, 45)).toBeCloseTo(2, 6);
  });

  it('is capped at 4 m absolute, then rolls off smoothly toward the horizon', () => {
    // At zenith 70° (soft-max), tan(70°)=2.75×h, still under 4 m cap for h=1
    expect(shadowLengthMeters(2, 70)).toBeCloseTo(4, 0);
    // At zenith 85° (late afternoon), cosine fade shrinks shadow substantially
    const val85 = shadowLengthMeters(1, 85);
    expect(val85).toBeGreaterThan(0);
    expect(val85).toBeLessThan(2);
    expect(shadowLengthMeters(1, 90)).toBe(0);
  });
});

describe('atmosphericFade', () => {
  it('is full below 75°, then tapers via cosine to zero at 90°', () => {
    expect(atmosphericFade(70)).toBe(1);
    expect(atmosphericFade(75)).toBe(1);
    // cos(7/15 * PI/2) ≈ 0.743
    expect(atmosphericFade(82)).toBeCloseTo(0.74, 1);
    // cos(10/15 * PI/2) = cos(PI/3) = 0.5
    expect(atmosphericFade(85)).toBeCloseTo(0.5, 6);
    expect(atmosphericFade(89)).toBeCloseTo(0.10, 1);
    expect(atmosphericFade(90)).toBe(0);
  });
});

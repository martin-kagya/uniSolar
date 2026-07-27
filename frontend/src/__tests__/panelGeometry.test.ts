import { describe, it, expect } from 'vitest';
import {
  rowPitch,
  projectedLength,
  panelHeight,
  shadowLength,
  orientationVectors,
} from '../lib/panelGeometry';

/**
 * Parity tests: verify that the frontend geometry formulas match
 * core/layers/geometry_model.py's compute_row_pitch() exactly.
 *
 * Backend formula (Python):
 *   import math
 *   def compute_row_pitch(collector_width, tilt_deg, gcr):
 *       projected = collector_width * math.cos(math.radians(tilt_deg))
 *       return projected / gcr
 */

const COLLECTOR_WIDTH = 1.0; // matches backend constant

describe('rowPitch parity with geometry_model.py', () => {
  it('matches backend at 0° tilt, GCR 0.4', () => {
    // Backend: pitch = 1.0 * cos(0) / 0.4 = 2.5
    expect(rowPitch(COLLECTOR_WIDTH, 0, 0.4)).toBeCloseTo(2.5, 10);
  });

  it('matches backend at 10° tilt, GCR 0.4', () => {
    const expected = COLLECTOR_WIDTH * Math.cos((10 * Math.PI) / 180) / 0.4;
    expect(rowPitch(COLLECTOR_WIDTH, 10, 0.4)).toBeCloseTo(expected, 10);
  });

  it('matches backend at 15° tilt, GCR 0.4', () => {
    const expected = COLLECTOR_WIDTH * Math.cos((15 * Math.PI) / 180) / 0.4;
    expect(rowPitch(COLLECTOR_WIDTH, 15, 0.4)).toBeCloseTo(expected, 10);
  });

  it('matches backend at 45° tilt, GCR 0.3', () => {
    const expected = COLLECTOR_WIDTH * Math.cos((45 * Math.PI) / 180) / 0.3;
    expect(rowPitch(COLLECTOR_WIDTH, 45, 0.3)).toBeCloseTo(expected, 10);
  });

  it('matches backend at 60° tilt, GCR 0.6', () => {
    const expected = COLLECTOR_WIDTH * Math.cos((60 * Math.PI) / 180) / 0.6;
    expect(rowPitch(COLLECTOR_WIDTH, 60, 0.6)).toBeCloseTo(expected, 10);
  });

  it('matches backend at 90° tilt, GCR 0.5', () => {
    // cos(90°) = 0, so pitch = 0 / 0.5 = 0
    expect(rowPitch(COLLECTOR_WIDTH, 90, 0.5)).toBeCloseTo(0, 10);
  });

  it('throws on invalid GCR', () => {
    expect(() => rowPitch(COLLECTOR_WIDTH, 15, 0)).toThrow(RangeError);
    expect(() => rowPitch(COLLECTOR_WIDTH, 15, -0.1)).toThrow(RangeError);
    expect(() => rowPitch(COLLECTOR_WIDTH, 15, 1.1)).toThrow(RangeError);
  });
});

describe('projectedLength', () => {
  it('equals module length at 0° tilt', () => {
    expect(projectedLength(2.278, 0)).toBeCloseTo(2.278, 10);
  });

  it('reduces with increasing tilt', () => {
    const p0 = projectedLength(2.278, 0);
    const p30 = projectedLength(2.278, 30);
    const p60 = projectedLength(2.278, 60);
    expect(p30).toBeLessThan(p0);
    expect(p60).toBeLessThan(p30);
  });
});

describe('panelHeight', () => {
  it('is zero at 0° tilt', () => {
    expect(panelHeight(2.278, 0)).toBeCloseTo(0, 10);
  });

  it('equals module length at 90° tilt', () => {
    expect(panelHeight(2.278, 90)).toBeCloseTo(2.278, 10);
  });
});

describe('shadowLength', () => {
  it('is zero at 0° tilt (panel on ground)', () => {
    expect(shadowLength(2.278, 0, 35)).toBeCloseTo(0, 10);
  });

  it('increases with tilt', () => {
    const s15 = shadowLength(2.278, 15, 35);
    const s30 = shadowLength(2.278, 30, 35);
    expect(s30).toBeGreaterThan(s15);
  });
});

describe('orientationVectors', () => {
  it('0° (North) points along -y', () => {
    const { facing, rowAxis } = orientationVectors(0);
    expect(facing.x).toBeCloseTo(0, 10);
    expect(facing.y).toBeCloseTo(-1, 10);
    expect(rowAxis.x).toBeCloseTo(1, 10);
    expect(rowAxis.y).toBeCloseTo(0, 10);
  });

  it('90° (East) points along +x', () => {
    const { facing, rowAxis } = orientationVectors(90);
    expect(facing.x).toBeCloseTo(1, 10);
    expect(facing.y).toBeCloseTo(0, 10);
  });

  it('180° (South) points along +y', () => {
    const { facing } = orientationVectors(180);
    expect(facing.x).toBeCloseTo(0, 10);
    expect(facing.y).toBeCloseTo(1, 10);
  });
});

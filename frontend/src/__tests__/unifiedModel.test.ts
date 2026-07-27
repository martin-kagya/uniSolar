import { describe, it, expect } from 'vitest';
import {
  fillPolygonWithPanels,
  computeSiteAnchor,
  panelCenterLatLng,
  latLngToMetersOffset,
  redistributeRow,
  rebuildPanelFootprint,
  DEFAULT_MODULE,
  type LatLng,
} from '../lib/panelGeometry';

// ~45 m square around a Ghana rooftop, big enough for several rows/columns.
const D = 0.0002; // ≈ 22 m in latitude
const SQUARE: LatLng[] = [
  { lat: 8.2612, lng: -2.2458 },
  { lat: 8.2612, lng: -2.2458 + D },
  { lat: 8.2612 + D, lng: -2.2458 + D },
  { lat: 8.2612 + D, lng: -2.2458 },
];

function fill() {
  const anchor = computeSiteAnchor([SQUARE]);
  const panels = fillPolygonWithPanels(SQUARE, anchor, DEFAULT_MODULE, 15, 180, 0.4, 'portrait', 0.02, 40, 6, 'area0');
  return { anchor, panels };
}

describe('unified panel model', () => {
  it('produces panels with stable ids across an identical re-fill', () => {
    const a = fill();
    const b = fill();
    expect(a.panels.length).toBeGreaterThan(0);
    expect(b.panels.length).toBe(a.panels.length);
    expect(b.panels.map(p => p.id)).toEqual(a.panels.map(p => p.id));
    expect(b.panels.map(p => p.rowId)).toEqual(a.panels.map(p => p.rowId));
  });

  it('assigns unique panel ids and groups by rowId', () => {
    const { panels } = fill();
    const ids = new Set(panels.map(p => p.id));
    expect(ids.size).toBe(panels.length);
    const rows = new Set(panels.map(p => p.rowId));
    expect(rows.size).toBeGreaterThan(0);
  });

  it('round-trips center meters <-> lat/lng through the shared anchor', () => {
    const { anchor, panels } = fill();
    for (const p of panels.slice(0, 5)) {
      const ll = panelCenterLatLng(p, anchor);
      const back = latLngToMetersOffset(anchor, ll);
      expect(back.x).toBeCloseTo(p.centerMeters.x, 4);
      expect(back.y).toBeCloseTo(p.centerMeters.y, 4);
    }
  });

  it('redistributeRow keeps panel count and enforces spacing', () => {
    const { panels } = fill();
    const rowId = panels[0].rowId;
    const row = panels.filter(p => p.rowId === rowId);
    if (row.length < 2) return; // need a multi-panel row
    const gap = 0.1;
    const out = redistributeRow(row, gap);
    expect(out.length).toBe(row.length);
    // Consecutive centers are spaced width+gap apart along the row axis.
    const expected = row[0].widthM + gap;
    for (let i = 1; i < out.length; i++) {
      const dx = out[i].centerMeters.x - out[i - 1].centerMeters.x;
      const dy = out[i].centerMeters.y - out[i - 1].centerMeters.y;
      expect(Math.hypot(dx, dy)).toBeCloseTo(expected, 3);
    }
  });

  it('rebuildPanelFootprint keeps the footprint centered on centerMeters', () => {
    const { panels } = fill();
    const p = panels[0];
    const r = rebuildPanelFootprint(p, 30, p.widthM, p.heightM);
    const cx = r.polygonMeters.reduce((s, v) => s + v.x, 0) / 4;
    const cy = r.polygonMeters.reduce((s, v) => s + v.y, 0) / 4;
    expect(cx).toBeCloseTo(p.centerMeters.x, 6);
    expect(cy).toBeCloseTo(p.centerMeters.y, 6);
    expect(r.gridRotationDeg).toBe(30);
  });
});

/**
 * setbacks.ts
 *
 * Setback and boundary line utilities for code compliance visualization.
 * Computes fire code setbacks, NEC clearances, and property line offsets.
 */

import type { LatLng, Vec2 } from './panelGeometry';
import { latLngToMetersOffset, metersOffsetToLatLng } from './panelGeometry';

// ---------- Types ----------

export interface SetbackLine {
  /** Setback type identifier. */
  type: 'fire' | 'nec' | 'property' | 'custom';
  /** Setback distance in meters. */
  distanceM: number;
  /** Description of the setback. */
  description: string;
  /** Offset polygon vertices in lat/lng. */
  polygonLatLng: LatLng[];
  /** Color for rendering [r, g, b, a]. */
  color: [number, number, number, number];
}

export interface PropertyBoundary {
  /** Original polygon vertices in lat/lng. */
  vertices: LatLng[];
  /** Total area in square meters. */
  areaM2: number;
  /** Perimeter in meters. */
  perimeterM: number;
  /** Bounding box dimensions. */
  dimensions: {
    widthM: number;
    depthM: number;
  };
}

// ---------- Constants ----------

/** Fire code setback from property line (typically 1.8m for residential). */
const FIRE_SETBACK_M = 1.8;

/** NEC clearance from power lines (typically 3m minimum). */
const NEC_CLEARANCE_M = 3.0;

// ---------- Setback Computation ----------

/**
 * Compute an inset polygon by a given distance (setback from boundary).
 * Uses the simple offset algorithm: move each edge inward by the setback
 * distance, then find intersection points of adjacent offset edges.
 *
 * @param polygon - Original polygon vertices in lat/lng
 * @param setbackM - Setback distance in meters
 * @param anchor - Site anchor point for meter conversion
 * @returns Inset polygon vertices in lat/lng
 */
function computeInsetPolygon(
  polygon: LatLng[],
  setbackM: number,
  anchor: LatLng
): LatLng[] {
  if (polygon.length < 3) return polygon;

  // Convert to meters
  const meterVerts = polygon.map((p) => latLngToMetersOffset(anchor, p));

  // Compute normals for each edge (pointing inward)
  const normals: Vec2[] = [];
  for (let i = 0; i < meterVerts.length; i++) {
    const a = meterVerts[i];
    const b = meterVerts[(i + 1) % meterVerts.length];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const len = Math.sqrt(dx * dx + dy * dy);
    // Inward normal (left of edge direction)
    normals.push({ x: -dy / len, y: dx / len });
  }

  // Offset each edge inward
  const offsetEdges: { a: Vec2; b: Vec2; normal: Vec2 }[] = [];
  for (let i = 0; i < meterVerts.length; i++) {
    const a = meterVerts[i];
    const b = meterVerts[(i + 1) % meterVerts.length];
    const n = normals[i];
    offsetEdges.push({
      a: { x: a.x + n.x * setbackM, y: a.y + n.y * setbackM },
      b: { x: b.x + n.x * setbackM, y: b.y + n.y * setbackM },
      normal: n,
    });
  }

  // Find intersection of consecutive offset edges
  const result: Vec2[] = [];
  for (let i = 0; i < offsetEdges.length; i++) {
    const e1 = offsetEdges[i];
    const e2 = offsetEdges[(i + 1) % offsetEdges.length];
    
    // Line-line intersection
    const d1x = e1.b.x - e1.a.x;
    const d1y = e1.b.y - e1.a.y;
    const d2x = e2.b.x - e2.a.x;
    const d2y = e2.b.y - e2.a.y;
    
    const denom = d1x * d2y - d1y * d2x;
    if (Math.abs(denom) < 1e-10) {
      // Parallel edges, use midpoint
      result.push({
        x: (e1.b.x + e2.a.x) / 2,
        y: (e1.b.y + e2.a.y) / 2,
      });
      continue;
    }

    const t = ((e2.a.x - e1.a.x) * d2y - (e2.a.y - e1.a.y) * d2x) / denom;
    result.push({
      x: e1.a.x + t * d1x,
      y: e1.a.y + t * d1y,
    });
  }

  // Convert back to lat/lng
  return result.map((v) => metersOffsetToLatLng(anchor, v));
}

/**
 * Generate all setback lines for a property boundary.
 *
 * @param polygon - Property boundary vertices in lat/lng
 * @param anchor - Site anchor point
 * @param options - Optional overrides for setback distances
 * @returns Array of setback lines
 */
export function generateSetbackLines(
  polygon: LatLng[],
  anchor: LatLng,
  options: {
    fireSetbackM?: boolean;
    necClearanceM?: boolean;
    customSetbackM?: number;
  } = {}
): SetbackLine[] {
  const setbacks: SetbackLine[] = [];

  // Fire code setback
  if (options.fireSetbackM !== false) {
    const firePolygon = computeInsetPolygon(polygon, FIRE_SETBACK_M, anchor);
    setbacks.push({
      type: 'fire',
      distanceM: FIRE_SETBACK_M,
      description: `Fire Setback (${FIRE_SETBACK_M}m)`,
      polygonLatLng: firePolygon,
      color: [255, 100, 100, 200],
    });
  }

  // NEC clearance
  if (options.necClearanceM !== false) {
    const necPolygon = computeInsetPolygon(polygon, NEC_CLEARANCE_M, anchor);
    setbacks.push({
      type: 'nec',
      distanceM: NEC_CLEARANCE_M,
      description: `NEC Clearance (${NEC_CLEARANCE_M}m)`,
      polygonLatLng: necPolygon,
      color: [100, 100, 255, 200],
    });
  }

  // Custom setback
  if (options.customSetbackM && options.customSetbackM > 0) {
    const customPolygon = computeInsetPolygon(polygon, options.customSetbackM, anchor);
    setbacks.push({
      type: 'custom',
      distanceM: options.customSetbackM,
      description: `Custom Setback (${options.customSetbackM}m)`,
      polygonLatLng: customPolygon,
      color: [255, 200, 100, 200],
    });
  }

  return setbacks;
}

// ---------- Property Boundary Analysis ----------

/**
 * Compute property boundary statistics.
 *
 * @param polygon - Property boundary vertices in lat/lng
 * @param anchor - Site anchor point
 * @returns Property boundary information
 */
export function analyzePropertyBoundary(
  polygon: LatLng[],
  anchor: LatLng
): PropertyBoundary {
  // Convert to meters
  const meterVerts = polygon.map((p) => latLngToMetersOffset(anchor, p));

  // Compute area using shoelace formula
  let area = 0;
  for (let i = 0; i < meterVerts.length; i++) {
    const j = (i + 1) % meterVerts.length;
    area += meterVerts[i].x * meterVerts[j].y;
    area -= meterVerts[j].x * meterVerts[i].y;
  }
  area = Math.abs(area) / 2;

  // Compute perimeter
  let perimeter = 0;
  for (let i = 0; i < meterVerts.length; i++) {
    const j = (i + 1) % meterVerts.length;
    const dx = meterVerts[j].x - meterVerts[i].x;
    const dy = meterVerts[j].y - meterVerts[i].y;
    perimeter += Math.sqrt(dx * dx + dy * dy);
  }

  // Compute bounding box
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const v of meterVerts) {
    minX = Math.min(minX, v.x);
    maxX = Math.max(maxX, v.x);
    minY = Math.min(minY, v.y);
    maxY = Math.max(maxY, v.y);
  }

  return {
    vertices: polygon,
    areaM2: area,
    perimeterM: perimeter,
    dimensions: {
      widthM: maxX - minX,
      depthM: maxY - minY,
    },
  };
}

// ---------- Rendering Utilities ----------

/**
 * Convert a setback line to deck.gl PathLayer-compatible data.
 */
export function setbackToPathData(
  setback: SetbackLine
): { path: [number, number, number][]; color: [number, number, number, number] }[] {
  const vertices = setback.polygonLatLng;
  if (vertices.length < 2) return [];

  // Create path segments (close the polygon)
  const path: [number, number, number][] = vertices.map((v) => [
    v.lng,
    v.lat,
    0.15,
  ]);
  // Close the polygon
  path.push([vertices[0].lng, vertices[0].lat, 0.15]);

  return [{ path, color: setback.color }];
}

/**
 * Convert a setback line to deck.gl TextLayer-compatible label data.
 */
export function setbackToLabelData(
  setback: SetbackLine,
  anchor: LatLng
): { position: [number, number, number]; text: string; color: [number, number, number, number] }[] {
  const vertices = setback.polygonLatLng;
  if (vertices.length < 2) return [];

  // Place label at the midpoint of the first edge
  const midLat = (vertices[0].lat + vertices[1].lat) / 2;
  const midLng = (vertices[0].lng + vertices[1].lng) / 2;

  return [{
    position: [midLng, midLat, 0.2],
    text: setback.description,
    color: setback.color,
  }];
}

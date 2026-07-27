/**
 * panelGeometry.ts
 *
 * Single source of truth for panel/array geometry math shared between:
 *  - the deck.gl PolygonLayer renderer (frontend)
 *  - a parity test that checks these values match core/layers/geometry_model.py (backend)
 *
 * All internal math is done in local meters on a flat ground plane, then the final
 * step projects each polygon's corners to lat/lng around a given anchor point.
 */

// ---------- Types ----------

export interface ModuleSpec {
  /** Module length along the tilt axis, in meters (e.g. 2.278 for a 420W portrait panel). */
  length: number;
  /** Module width along the row axis, in meters (e.g. 1.134). */
  width: number;
  /** Rated power in watts, used only for capacity readouts. */
  wattage: number;
}

export interface LatLng {
  lat: number;
  lng: number;
}

export interface PanelFootprint {
  /** Stable, deterministic identity that survives a re-fill of the same polygon/config. */
  id: string;
  /** Stable id of the physical row this panel belongs to (unique per row across blocks). */
  rowId: string;
  /** Stable id of the block (road-separated band) this panel belongs to. */
  blockId: string;
  /** Row index (0-based, within its block). */
  row: number;
  /** Panel index within the row (0-based). */
  index: number;
  /** Four ground-footprint corners in local meters, relative to the shared site anchor. */
  polygonMeters: [Vec2, Vec2, Vec2, Vec2];
  /** Footprint center in local meters, relative to the shared site anchor. */
  centerMeters: Vec2;
  /**
   * Shadow quad in local meters (initial estimate from a default sun elevation).
   * The renderer recomputes this each frame from the live sun vector, so it does not
   * need to be kept in sync during edits.
   */
  shadowMeters: [Vec2, Vec2, Vec2, Vec2];
  /** Footprint width along the row axis, in meters. */
  widthM: number;
  /** Footprint depth along the facing axis (tilt-projected module length), in meters. */
  heightM: number;
  /** True (un-projected) module length along the tilt axis, in meters — used for 3D. */
  moduleLengthM: number;
  /** True module width, in meters — used for 3D. */
  moduleWidthM: number;
  /** Panel orientation. */
  orientation: 'portrait' | 'landscape';
  /** System tilt in degrees (for 3D extrusion). */
  tiltDeg: number;
  /** System azimuth in degrees (compass convention). */
  azimuthDeg: number;
  /** Grid alignment angle in degrees (rotation of the footprint rectangle). */
  gridRotationDeg: number;
}

export interface Vec2 {
  x: number;
  y: number;
}

// ---------- Defaults ----------

export const DEFAULT_MODULE: ModuleSpec = {
  length: 2.278,
  width: 1.134,
  wattage: 420,
};

const DEFAULT_GAP = 0.02;
const DEFAULT_LIGHT_ELEVATION_DEG = 35;
const EARTH_RADIUS_M = 6378137;

// ---------- Core formulas (must stay in lockstep with geometry_model.py) ----------

const toRad = (deg: number): number => (deg * Math.PI) / 180;

/**
 * Ground footprint depth of a tilted module, projected onto a flat plane.
 */
export function projectedLength(moduleLength: number, tiltDeg: number): number {
  return moduleLength * Math.cos(toRad(tiltDeg));
}

/** Height of the panel's raised (upper) edge above the ground. */
export function panelHeight(moduleLength: number, tiltDeg: number): number {
  return moduleLength * Math.sin(toRad(tiltDeg));
}

/**
 * Row pitch (center-to-center spacing between rows), derived from GCR and tilt.
 *
 *   pitch = projectedLength / GCR
 *
 * Mirrors geometry_model.py's compute_row_pitch().
 */
export function rowPitch(moduleLength: number, tiltDeg: number, gcr: number): number {
  if (gcr <= 0 || gcr > 1) {
    throw new RangeError(`gcr must be in (0, 1], got ${gcr}`);
  }
  return projectedLength(moduleLength, tiltDeg) / gcr;
}

/**
 * Shadow length cast forward from a panel's raised top edge.
 */
export function shadowLength(
  moduleLength: number,
  tiltDeg: number,
  lightElevationDeg: number = DEFAULT_LIGHT_ELEVATION_DEG
): number {
  const height = panelHeight(moduleLength, tiltDeg);
  const elevRad = toRad(lightElevationDeg);
  if (elevRad <= 0) return Infinity;
  return height / Math.tan(elevRad);
}

// ---------- Orientation basis ----------

/**
 * Screen/ground-plane unit vectors for a given azimuth, compass convention.
 * - facing: the direction panels face and the direction rows recede along.
 * - rowAxis: perpendicular to facing; the direction panels are laid out side by side.
 */
export function orientationVectors(azimuthDeg: number): { facing: Vec2; rowAxis: Vec2 } {
  const az = toRad(azimuthDeg);
  const facing: Vec2 = { x: Math.sin(az), y: -Math.cos(az) };
  const rowAxis: Vec2 = { x: Math.cos(az), y: Math.sin(az) };
  return { facing, rowAxis };
}

// ---------- Map projection (meters <-> lat/lng) ----------

export function metersOffsetToLatLng(anchor: LatLng, offset: Vec2): LatLng {
  const dLat = (offset.y / EARTH_RADIUS_M) * (180 / Math.PI);
  const dLng =
    (offset.x / (EARTH_RADIUS_M * Math.cos((anchor.lat * Math.PI) / 180))) * (180 / Math.PI);
  return { lat: anchor.lat + dLat, lng: anchor.lng + dLng };
}

/** Inverse of metersOffsetToLatLng: project a lat/lng into the local meter frame. */
export function latLngToMetersOffset(anchor: LatLng, point: LatLng): Vec2 {
  const y = ((point.lat - anchor.lat) * Math.PI) / 180 * EARTH_RADIUS_M;
  const x =
    ((point.lng - anchor.lng) * Math.PI) / 180 *
    EARTH_RADIUS_M *
    Math.cos((anchor.lat * Math.PI) / 180);
  return { x, y };
}

/** Convenience: project a panel's footprint center back to lat/lng. */
export function panelCenterLatLng(panel: PanelFootprint, anchor: LatLng): LatLng {
  return metersOffsetToLatLng(anchor, panel.centerMeters);
}

/** Compute the shared site anchor (centroid) for one or more boundary polygons. */
export function computeSiteAnchor(polygons: LatLng[][]): LatLng {
  const flat = polygons.flat();
  if (flat.length === 0) return { lat: 0, lng: 0 };
  return {
    lat: flat.reduce((s, p) => s + p.lat, 0) / flat.length,
    lng: flat.reduce((s, p) => s + p.lng, 0) / flat.length,
  };
}

// ---------- Polygon filling ----------

/** Ray-casting point-in-polygon test. */
function pointInPolygon(point: Vec2, polygon: Vec2[]): boolean {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i].x, yi = polygon[i].y;
    const xj = polygon[j].x, yj = polygon[j].y;
    if ((yi > point.y) !== (yj > point.y) &&
        point.x < ((xj - xi) * (point.y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Check if all 4 panel corners are inside the polygon. */
function panelFitsInPolygon(corners: Vec2[], polygon: Vec2[]): boolean {
  return corners.every(c => pointInPolygon(c, polygon));
}

/**
 * Compute the longest edge angle of a lat/lng polygon (used to align the panel grid).
 * Returns angle in radians.
 */
function getBaselineAngle(polygonMeters: Vec2[]): number {
  let bestAngle = 0;
  let bestScore = -1;

  for (let i = 0; i < polygonMeters.length; i++) {
    const a = polygonMeters[i];
    const b = polygonMeters[(i + 1) % polygonMeters.length];
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const distSq = dx * dx + dy * dy;
    const angle = Math.atan2(dy, dx);
    const horizontalBias = Math.abs(Math.cos(angle));
    const score = distSq * (1 + horizontalBias * 0.5);
    if (score > bestScore) {
      bestScore = score;
      bestAngle = angle;
    }
  }
  return bestAngle;
}

/** Rotate a Vec2 around an origin by the given angle (radians). */
function rotatePoint(point: Vec2, origin: Vec2, angle: number): Vec2 {
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const dx = point.x - origin.x;
  const dy = point.y - origin.y;
  return {
    x: origin.x + dx * cos - dy * sin,
    y: origin.y + dx * sin + dy * cos,
  };
}

/**
 * Fill a boundary polygon with tilted panel footprints, all expressed in the local
 * meter frame of a shared site `anchor`. Because every polygon in a site shares the
 * same anchor, panels from multiple polygons project consistently and can be rendered
 * and edited as one dataset.
 *
 * Emits the full unified {@link PanelFootprint} model: stable ids, block/row identity,
 * footprint corners, center, and metadata needed for 2.5D/3D rendering.
 *
 * @param polygonLatLng - Boundary vertices in lat/lng [{lat, lng}, ...]
 * @param anchor - Shared site anchor; all meter coordinates are relative to it
 * @param moduleSpec - Physical module dimensions
 * @param tiltDeg - System tilt
 * @param azimuthDeg - System azimuth (compass convention)
 * @param gcr - Ground coverage ratio
 * @param orientation - 'portrait' or 'landscape'
 * @param interPanelGap - Gap between panels within a row (meters)
 * @param blockSizeM - Size of sub-array blocks (meters)
 * @param roadWidthM - Width of access roads between blocks (meters)
 * @param idPrefix - Namespaces panel ids so multiple polygons don't collide
 */
export function fillPolygonWithPanels(
  polygonLatLng: LatLng[],
  anchor: LatLng,
  moduleSpec: ModuleSpec,
  tiltDeg: number,
  azimuthDeg: number,
  gcr: number,
  orientation: 'portrait' | 'landscape' = 'portrait',
  interPanelGap: number = DEFAULT_GAP,
  blockSizeM: number = 40,
  roadWidthM: number = 6,
  idPrefix: string = 'a0'
): PanelFootprint[] {
  if (polygonLatLng.length < 3) return [];

  // Determine panel dimensions based on orientation
  let w: number, h: number;
  if (orientation === 'landscape') {
    w = Math.max(moduleSpec.width, moduleSpec.length);
    h = Math.min(moduleSpec.width, moduleSpec.length);
  } else {
    w = moduleSpec.width;
    h = moduleSpec.length;
  }

  // Project polygon into the shared anchor's meter frame (round-trips with
  // metersOffsetToLatLng used by the renderer).
  const polygonMeters: Vec2[] = polygonLatLng.map(p => latLngToMetersOffset(anchor, p));

  const baselineAngle = getBaselineAngle(polygonMeters);
  const gridRotationDeg = (baselineAngle * 180) / Math.PI;

  // Rotate polygon to an axis-aligned coordinate system for scanning
  const rotOrigin = polygonMeters[0];
  const rotatedPoly = polygonMeters.map(p => rotatePoint(p, rotOrigin, -baselineAngle));

  // Bounding box in rotated space
  let minY = Infinity, maxY = -Infinity, minX = Infinity, maxX = -Infinity;
  for (const p of rotatedPoly) {
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
  }

  // Row pitch and footprint depth from GCR / tilt
  const pitch = rowPitch(h, tiltDeg, gcr);
  const projLen = projectedLength(h, tiltDeg);
  const shadowLen = shadowLength(h, tiltDeg, DEFAULT_LIGHT_ELEVATION_DEG);
  const { facing } = orientationVectors(azimuthDeg);

  const panels: PanelFootprint[] = [];

  // Three-level hierarchy: blocks (road-separated bands) -> rows -> modules
  const blockStep = blockSizeM + roadWidthM;
  const rowStep = pitch;
  const colStep = w + interPanelGap;

  let blockIndex = 0;
  for (let blockStart = 0; blockStart < maxY - minY; blockStart += blockStep) {
    const blockId = `${idPrefix}_b${blockIndex}`;
    let rowInBlock = 0;
    for (let rowOffset = 0; rowOffset < blockSizeM; rowOffset += rowStep) {
      const rotatedY = minY + blockStart + rowOffset;
      if (rotatedY + projLen > maxY) break;
      const rowId = `${blockId}_r${rowInBlock}`;

      let colIndex = 0;
      for (let colStart = minX; colStart < maxX; colStart += colStep) {
        const rc0: Vec2 = { x: colStart, y: rotatedY };
        const rc1: Vec2 = { x: colStart + w, y: rotatedY };
        const rc2: Vec2 = { x: colStart + w, y: rotatedY + projLen };
        const rc3: Vec2 = { x: colStart, y: rotatedY + projLen };

        const thisCol = colIndex++;

        // Bounds check against the rotated bounding box
        if (rc0.x < minX || rc1.x > maxX || rc3.y > maxY) continue;

        // Rotate corners back into the anchor meter frame
        const mc0 = rotatePoint(rc0, rotOrigin, baselineAngle);
        const mc1 = rotatePoint(rc1, rotOrigin, baselineAngle);
        const mc2 = rotatePoint(rc2, rotOrigin, baselineAngle);
        const mc3 = rotatePoint(rc3, rotOrigin, baselineAngle);

        if (!panelFitsInPolygon([mc0, mc1, mc2, mc3], polygonMeters)) continue;

        // Initial shadow estimate (renderer recomputes from the live sun vector)
        const ms3: Vec2 = { x: mc3.x + facing.x * shadowLen, y: mc3.y + facing.y * shadowLen };
        const ms2: Vec2 = { x: mc2.x + facing.x * shadowLen, y: mc2.y + facing.y * shadowLen };

        const centerMeters: Vec2 = {
          x: (mc0.x + mc1.x + mc2.x + mc3.x) / 4,
          y: (mc0.y + mc1.y + mc2.y + mc3.y) / 4,
        };

        panels.push({
          id: `${rowId}_c${thisCol}`,
          rowId,
          blockId,
          row: rowInBlock,
          index: thisCol,
          polygonMeters: [mc0, mc1, mc2, mc3],
          centerMeters,
          shadowMeters: [mc3, mc2, ms2, ms3],
          widthM: w,
          heightM: projLen,
          moduleLengthM: h,
          moduleWidthM: w,
          orientation,
          tiltDeg,
          azimuthDeg,
          gridRotationDeg,
        });
      }
      rowInBlock++;
    }
    blockIndex++;
  }

  return panels;
}

/**
 * Generic shadow polygon for any rectangular footprint.
 *
 * Given a 4-corner polygon and a height above ground, projects the silhouette
 * onto the ground plane. The shadow shape is a trapezoid: the 2 front vertices
 * (closest to sun) stay fixed, the 2 back vertices are displaced by
 * `sunVec * height * tan(zenith)`. This single function feeds both the visual
 * deck.gl layer and the simulation's row-shading geometry.
 *
 * A soft length cap prevents shadows from exploding at extreme low-sun angles
 * where the atmospheric fade already renders them nearly invisible.
 *
 * @param corners  Four ground-footprint corners in [SW, SE, NE, NW] order.
 * @param sunVec   Unit-like ground vector pointing toward the sun's azimuth.
 * @param height   Object height above ground (meters).
 * @param zenithDeg  Solar zenith angle in degrees (0 = overhead, 90 = horizon).
 * @returns 4-corner shadow polygon in meters, or null when no shadow.
 */
export function computeShadowPolygon(
  corners: [Vec2, Vec2, Vec2, Vec2],
  sunVec: Vec2,
  height: number,
  zenithDeg: number
): [Vec2, Vec2, Vec2, Vec2] | null {
  if (zenithDeg >= 90 || height <= 0) return null;

  // Raw shadow length: height × tan(zenith). At low sun this explodes (88° ≈ 28×),
  // so we apply a soft cap: shadow ≤ 4× height, with cosine roll-off above 75°
  // so shadows shrink smoothly toward zero at the horizon.
  const raw = height * Math.tan((zenithDeg * Math.PI) / 180);
  const CAP_FACTOR = 4;
  const SOFT_ZENITH = 75;

  let disp: number;
  if (zenithDeg <= SOFT_ZENITH) {
    disp = Math.min(raw, height * CAP_FACTOR);
  } else {
    // Smooth cosine fade: at 75° → full capped length; at 90° → 0
    const t = (zenithDeg - SOFT_ZENITH) / (90 - SOFT_ZENITH);
    disp = Math.min(raw, height * CAP_FACTOR) * Math.cos((t * Math.PI) / 2);
  }
  if (disp < 0.01) return null;

  // Sort corners by dot product with sunVec to find front vs back edge.
  // Front = closest to sun (smallest dot), back = farthest (largest dot).
  const scored = corners.map((c, i) => ({
    v: c,
    dot: c.x * sunVec.x + c.y * sunVec.y,
    i,
  }));
  scored.sort((a, b) => a.dot - b.dot);

  const front0 = scored[0].v;
  const front1 = scored[1].v;
  const back0 = scored[2].v;
  const back1 = scored[3].v;

  return [
    front0,
    front1,
    { x: back1.x + sunVec.x * disp, y: back1.y + sunVec.y * disp },
    { x: back0.x + sunVec.x * disp, y: back0.y + sunVec.y * disp },
  ];
}

/**
 * Shadow polygon for a tilted panel (convenience wrapper around computeShadowPolygon).
 *
 * The panel's raised back edge sits at height `panelHeight(moduleLength, tilt)`.
 * `dispM` should be `panelHeight * tan(zenith)` (see `shadowLengthMeters` in
 * solarPosition.ts).
 */
export function panelGroundShadow(
  panel: PanelFootprint,
  sunVec: Vec2,
  dispM: number
): [Vec2, Vec2, Vec2, Vec2] | null {
  if (dispM <= 0) return null;
  const [c0, c1, c2, c3] = panel.polygonMeters; // SW, SE, NE(back-right), NW(back-left)
  return [
    c0,
    c1,
    { x: c2.x + sunVec.x * dispM, y: c2.y + sunVec.y * dispM },
    { x: c3.x + sunVec.x * dispM, y: c3.y + sunVec.y * dispM },
  ];
}

/**
 * Soft shadow layers — multiple concentric shadow polygons at decreasing opacity,
 * producing a gradient falloff from dark (near base) to transparent (at tip).
 * Each returned item is a polygon + alpha pair for rendering as a separate
 * deck.gl PolygonLayer.
 */
export function softShadowLayers(
  corners: [Vec2, Vec2, Vec2, Vec2],
  sunVec: Vec2,
  height: number,
  zenithDeg: number,
  baseAlpha: number,
  layers = 4
): Array<{ polygon: [Vec2, Vec2, Vec2, Vec2]; alpha: number }> {
  const full = computeShadowPolygon(corners, sunVec, height, zenithDeg);
  if (!full) return [];

  const cx = (corners[0].x + corners[1].x + corners[2].x + corners[3].x) / 4;
  const cy = (corners[0].y + corners[1].y + corners[2].y + corners[3].y) / 4;

  const result: Array<{ polygon: [Vec2, Vec2, Vec2, Vec2]; alpha: number }> = [];
  for (let i = 0; i < layers; i++) {
    const t = (i + 1) / layers; // 0→1 from base to tip
    const poly: [Vec2, Vec2, Vec2, Vec2] = full.map((v) => ({
      x: cx + (v.x - cx) * t,
      y: cy + (v.y - cy) * t,
    })) as [Vec2, Vec2, Vec2, Vec2];
    result.push({ polygon: poly, alpha: baseAlpha * (1 - t * 0.7) });
  }
  return result;
}

// ---------- Panel transforms (meters space) ----------

/**
 * Rebuild a panel's footprint rectangle centered on its current `centerMeters`,
 * rotated to `rotationDeg`, sized `widthM` × `heightM`. Operates entirely in the
 * anchor meter frame, so there is no latitude scaling to get wrong.
 */
export function rebuildPanelFootprint(
  panel: PanelFootprint,
  rotationDeg: number,
  widthM: number,
  heightM: number
): PanelFootprint {
  const a = (rotationDeg * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  const hw = widthM / 2;
  const hh = heightM / 2;
  const c = panel.centerMeters;

  // Corner order matches fillPolygonWithPanels: SW, SE, NE, NW (before rotation)
  const local = [
    { x: -hw, y: -hh },
    { x: hw, y: -hh },
    { x: hw, y: hh },
    { x: -hw, y: hh },
  ];
  const corners = local.map((p) => ({
    x: c.x + p.x * cos - p.y * sin,
    y: c.y + p.x * sin + p.y * cos,
  })) as [Vec2, Vec2, Vec2, Vec2];

  return {
    ...panel,
    polygonMeters: corners,
    widthM,
    heightM,
    gridRotationDeg: rotationDeg,
  };
}

/**
 * Space the panels of a single row evenly along the row axis at `gapM` spacing,
 * preventing overlaps after an orientation flip. All in the anchor meter frame.
 */
export function redistributeRow(rowPanels: PanelFootprint[], gapM: number): PanelFootprint[] {
  if (rowPanels.length < 2) return rowPanels;

  const sorted = [...rowPanels].sort((a, b) => a.centerMeters.x - b.centerMeters.x || a.centerMeters.y - b.centerMeters.y);
  const first = sorted[0];
  // Row axis unit vector from the grid rotation.
  const a = (first.gridRotationDeg * Math.PI) / 180;
  const ux = Math.cos(a);
  const uy = Math.sin(a);

  return sorted.map((p, i) => {
    if (i === 0) return p;
    const step = i * (p.widthM + gapM);
    const nextCenter: Vec2 = {
      x: first.centerMeters.x + ux * step,
      y: first.centerMeters.y + uy * step,
    };
    return rebuildPanelFootprint({ ...p, centerMeters: nextCenter }, p.gridRotationDeg, p.widthM, p.heightM);
  });
}

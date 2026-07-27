/**
 * electrical.ts
 *
 * Electrical layout utilities for the solar array visualization.
 * Handles string assignment, inverter placement, and wiring visualization.
 */

import type { PanelFootprint, Vec2, LatLng } from './panelGeometry';
import { metersOffsetToLatLng } from './panelGeometry';

// ---------- Types ----------

export interface StringAssignment {
  /** String index (0-based). */
  index: number;
  /** Panel IDs in this string, in electrical order. */
  panelIds: string[];
  /** Inverter index this string connects to. */
  inverterIndex: number;
}

export interface InverterLocation {
  /** Inverter index. */
  index: number;
  /** Inverter capacity in kW. */
  capacityKw: number;
  /** Inverter model name. */
  model: string;
  /** Position in local meters relative to site anchor. */
  positionMeters: Vec2;
  /** Position as lat/lng. */
  positionLatLng: LatLng;
  /** Number of strings connected to this inverter. */
  stringCount: number;
}

export interface WiringPath {
  /** Panel center position (lat/lng). */
  panelPosition: LatLng;
  /** Inverter position (lat/lng). */
  inverterPosition: LatLng;
  /** String index for color coding. */
  stringIndex: number;
}

// ---------- Constants ----------

/** Typical panels per string for common module voltages. */
const PANELS_PER_STRING_DEFAULT = 18;

/** String color palette (distinct hues for up to 12 strings). */
const STRING_COLORS: [number, number, number, number][] = [
  [255, 100, 100, 200],   // red
  [100, 255, 100, 200],   // green
  [100, 100, 255, 200],   // blue
  [255, 255, 100, 200],   // yellow
  [255, 100, 255, 200],   // magenta
  [100, 255, 255, 200],   // cyan
  [255, 180, 100, 200],   // orange
  [180, 100, 255, 200],   // purple
  [100, 255, 180, 200],   // teal
  [255, 100, 180, 200],   // pink
  [180, 255, 100, 200],   // lime
  [100, 180, 255, 200],   // sky
];

// ---------- String Assignment ----------

/**
 * Assign panels to electrical strings, grouping by row and connecting
 * adjacent panels in series. Strings are assigned to inverters round-robin.
 *
 * @param panels - All panel footprints in the array
 * @param panelsPerString - Number of panels per string (default: 18)
 * @param inverterCount - Number of inverters (default: 1)
 * @returns Array of string assignments
 */
export function assignStrings(
  panels: PanelFootprint[],
  panelsPerString: number = PANELS_PER_STRING_DEFAULT,
  inverterCount: number = 1
): StringAssignment[] {
  if (panels.length === 0) return [];

  // Group panels by row
  const rowGroups = new Map<string, PanelFootprint[]>();
  panels.forEach((p) => {
    if (!rowGroups.has(p.rowId)) rowGroups.set(p.rowId, []);
    rowGroups.get(p.rowId)!.push(p);
  });

  // Sort panels within each row by their position along the row axis
  const sortedRows = Array.from(rowGroups.values()).map((rowPanels) => {
    const azimuth = rowPanels[0].azimuthDeg;
    const rowRad = (azimuth * Math.PI) / 180;
    const rowX = Math.cos(rowRad);
    const rowY = Math.sin(rowRad);
    
    return [...rowPanels].sort((a, b) => {
      const projA = a.centerMeters.x * rowX + a.centerMeters.y * rowY;
      const projB = b.centerMeters.x * rowX + b.centerMeters.y * rowY;
      return projA - projB;
    });
  });

  // Flatten rows into a single array (row-major order)
  const allPanels = sortedRows.flat();

  // Assign panels to strings
  const strings: StringAssignment[] = [];
  let stringIndex = 0;

  for (let i = 0; i < allPanels.length; i += panelsPerString) {
    const stringPanels = allPanels.slice(i, i + panelsPerString);
    strings.push({
      index: stringIndex,
      panelIds: stringPanels.map((p) => p.id),
      inverterIndex: stringIndex % inverterCount,
    });
    stringIndex++;
  }

  return strings;
}

// ---------- Inverter Placement ----------

/**
 * Place inverters at optimal locations based on string endpoints.
 * Each inverter is placed near the center of its connected strings.
 *
 * @param panels - All panel footprints
 * @param strings - String assignments
 * @param anchor - Site anchor point for lat/lng conversion
 * @param inverterKw - Inverter capacity in kW (default: 50)
 * @param inverterModel - Inverter model name
 * @returns Array of inverter locations
 */
export function placeInverters(
  panels: PanelFootprint[],
  strings: StringAssignment[],
  anchor: LatLng,
  inverterKw: number = 50,
  inverterModel: string = 'SMA Sunny Tripower'
): InverterLocation[] {
  if (strings.length === 0) return [];

  // Group panels by ID for quick lookup
  const panelMap = new Map<string, PanelFootprint>();
  panels.forEach((p) => panelMap.set(p.id, p));

  // Group strings by inverter
  const inverterGroups = new Map<number, StringAssignment[]>();
  strings.forEach((s) => {
    if (!inverterGroups.has(s.inverterIndex)) inverterGroups.set(s.inverterIndex, []);
    inverterGroups.get(s.inverterIndex)!.push(s);
  });

  const inverters: InverterLocation[] = [];

  inverterGroups.forEach((invStrings, invIndex) => {
    // Collect all panel centers for this inverter
    const allCenters: Vec2[] = [];
    invStrings.forEach((s) => {
      s.panelIds.forEach((pid) => {
        const panel = panelMap.get(pid);
        if (panel) allCenters.push(panel.centerMeters);
      });
    });

    if (allCenters.length === 0) return;

    // Compute centroid of all connected panels
    const centerX = allCenters.reduce((s, c) => s + c.x, 0) / allCenters.length;
    const centerY = allCenters.reduce((s, c) => s + c.y, 0) / allCenters.length;

    // Offset slightly to the side (perpendicular to row axis) to avoid overlapping panels
    const firstPanel = panelMap.get(invStrings[0].panelIds[0]);
    const az = firstPanel?.azimuthDeg ?? 180;
    const rowRad = (az * Math.PI) / 180;
    const perpX = -Math.sin(rowRad);
    const perpY = Math.cos(rowRad);
    const offsetM = 3; // 3m offset from panel edge

    const positionMeters: Vec2 = {
      x: centerX + perpX * offsetM,
      y: centerY + perpY * offsetM,
    };

    const positionLatLng = metersOffsetToLatLng(anchor, positionMeters);

    inverters.push({
      index: invIndex,
      capacityKw: inverterKw,
      model: inverterModel,
      positionMeters,
      positionLatLng,
      stringCount: invStrings.length,
    });
  });

  return inverters;
}

// ---------- Wiring Paths ----------

/**
 * Generate wiring paths from the last panel in each string to its inverter.
 *
 * @param panels - All panel footprints
 * @param strings - String assignments
 * @param inverters - Inverter locations
 * @param anchor - Site anchor point
 * @returns Array of wiring paths
 */
export function generateWiringPaths(
  panels: PanelFootprint[],
  strings: StringAssignment[],
  inverters: InverterLocation[],
  anchor: LatLng
): WiringPath[] {
  if (strings.length === 0 || inverters.length === 0) return [];

  // Group panels by ID
  const panelMap = new Map<string, PanelFootprint>();
  panels.forEach((p) => panelMap.set(p.id, p));

  // Group inverters by index
  const inverterMap = new Map<number, InverterLocation>();
  inverters.forEach((inv) => inverterMap.set(inv.index, inv));

  const paths: WiringPath[] = [];

  strings.forEach((s) => {
    const lastPanelId = s.panelIds[s.panelIds.length - 1];
    const lastPanel = panelMap.get(lastPanelId);
    const inverter = inverterMap.get(s.inverterIndex);

    if (lastPanel && inverter) {
      const panelPosition = metersOffsetToLatLng(anchor, lastPanel.centerMeters);
      paths.push({
        panelPosition,
        inverterPosition: inverter.positionLatLng,
        stringIndex: s.index,
      });
    }
  });

  return paths;
}

// ---------- Color Utilities ----------

/**
 * Get the color for a string index.
 */
export function getStringColor(stringIndex: number): [number, number, number, number] {
  return STRING_COLORS[stringIndex % STRING_COLORS.length];
}

/**
 * Get a contrasting text color for a string (white or black).
 */
export function getStringTextColor(stringIndex: number): [number, number, number, number] {
  const [r, g, b] = STRING_COLORS[stringIndex % STRING_COLORS.length];
  // Simple luminance check
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.5 ? [0, 0, 0, 255] : [255, 255, 255, 255];
}

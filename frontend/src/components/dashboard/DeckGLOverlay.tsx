import React, { useEffect, useRef } from 'react';
import { useMap } from '@vis.gl/react-google-maps';
import { GoogleMapsOverlay } from '@deck.gl/google-maps';
import { PolygonLayer, TextLayer, PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import { SimpleMeshLayer } from '@deck.gl/mesh-layers';
import type { PanelFootprint, LatLng, Vec2 } from '../../lib/panelGeometry';
import { metersOffsetToLatLng, panelHeight, computeShadowPolygon, softShadowLayers } from '../../lib/panelGeometry';
import { sunGroundVector, shadowLengthMeters, atmosphericFade } from '../../lib/solarPosition';
import { getPanelTexture } from '../../lib/panelTexture';
import type { StringAssignment, InverterLocation, WiringPath } from '../../lib/electrical';
import { getStringColor } from '../../lib/electrical';
import type { SetbackLine } from '../../lib/setbacks';

export type ViewMode = '2d' | '3d';

interface SunState {
  azimuthDeg: number;
  zenithDeg: number;
  elevationDeg: number;
}

interface DeckGLOverlayProps {
  panels: PanelFootprint[];
  anchor: LatLng;
  selectedRowIds: string[];
  setSelectedRowIds?: (ids: string[]) => void;
  sun: SunState;
  viewMode: ViewMode;
  visible?: boolean;
  showLabels?: boolean;
  showMeasurements?: boolean;
  showStrings?: boolean;
  showInverters?: boolean;
  showSetbacks?: boolean;
  strings?: StringAssignment[];
  inverters?: InverterLocation[];
  wiringPaths?: WiringPath[];
  setbackLines?: SetbackLine[];
  obstacles?: ObstacleData[];
  selectedObstacleId?: string | null;
  setSelectedObstacleId?: (id: string | null) => void;
}

interface ObstacleData {
  id: string;
  type: string;
  lat: number;
  lng: number;
  widthM: number;
  heightM: number;
}

const OBSTACLE_COLORS: Record<string, [number, number, number]> = {
  tree:     [34, 139, 34],
  building: [120, 120, 120],
  chimney:  [160, 82, 45],
  other:    [70, 130, 180],
};

/** Rack clearance (m) of the module's lower edge above the roof/ground. */
const MOUNT_CLEARANCE_M = 0.6;

// ---- Shared unit-quad mesh (built once) --------------------------------------
// Quad lies in the local xy-plane, centered at origin, normal +z. Mesh +x is the
// module slope/length axis (tilted by pitch), mesh +y is the hinge/row axis.
// texCoords map the portrait texture's long (v) axis to mesh +x.
//
// IMPORTANT: SimpleMeshLayer.normalizeGeometryAttributes reads `attr.value` and
// `attr.size` (it computes positionAttribute.value.length / positionAttribute.size),
// so every attribute MUST be a { value: TypedArray, size } object. Passing raw
// typed arrays throws at runtime ("cannot read length of undefined") — which only
// surfaces in the browser, not in build/transform checks.
const QUAD = (() => {
  const corners: Vec2[] = [
    { x: -0.5, y: -0.5 },
    { x: 0.5, y: -0.5 },
    { x: 0.5, y: 0.5 },
    { x: -0.5, y: 0.5 },
  ];
  const tri = [0, 1, 2, 0, 2, 3];
  const positions = new Float32Array(tri.length * 3);
  const normals = new Float32Array(tri.length * 3);
  const texCoords = new Float32Array(tri.length * 2);
  tri.forEach((ci, i) => {
    const c = corners[ci];
    positions[i * 3] = c.x;
    positions[i * 3 + 1] = c.y;
    positions[i * 3 + 2] = 0;
    normals[i * 3] = 0;
    normals[i * 3 + 1] = 0;
    normals[i * 3 + 2] = 1;
    texCoords[i * 2] = c.y + 0.5; // u  <- hinge/row axis
    texCoords[i * 2 + 1] = c.x + 0.5; // v <- slope/length axis
  });
  return {
    attributes: {
      positions: { value: positions, size: 3 },
      normals: { value: normals, size: 3 },
      texCoords: { value: texCoords, size: 2 },
    },
  };
})();

/**
 * deck.gl overlay that renders the solar array as an instanced, textured mesh —
 * flat in 2.5D, tilted on mounts in 3D — with sun-accurate cast shadows.
 * Reads from the unified PanelFootprint model shared with the geometry/simulation
 * pipeline, so what is drawn is exactly what is selected and simulated.
 */
export default function DeckGLOverlay({
  panels,
  anchor,
  selectedRowIds,
  setSelectedRowIds,
  sun,
  viewMode,
  visible = true,
  showLabels = true,
  showMeasurements = false,
  showStrings = false,
  showInverters = false,
  showSetbacks = false,
  strings = [],
  inverters = [],
  wiringPaths = [],
  setbackLines = [],
  obstacles = [],
  selectedObstacleId = null,
  setSelectedObstacleId,
}: DeckGLOverlayProps) {
  const map = useMap();
  const overlayRef = useRef<GoogleMapsOverlay | null>(null);

  useEffect(() => {
    if (!map) return;
    const overlay = new GoogleMapsOverlay({ layers: [] });
    overlay.setMap(map);
    overlayRef.current = overlay;
    return () => {
      overlay.setMap(null);
      overlay.finalize();
      overlayRef.current = null;
    };
  }, [map]);

  useEffect(() => {
    if (!overlayRef.current) return;
    if (!visible || panels.length === 0) {
      overlayRef.current.setProps({ layers: [] });
      return;
    }

    const is3D = viewMode === '3d';
    const selected = new Set(selectedRowIds);

    // ---- Sun-driven cast shadows (soft gradient falloff) --------------------
    const sunVec = sunGroundVector(sun.azimuthDeg);
    const fade = atmosphericFade(sun.zenithDeg);

    // Build soft shadow layers: 4 concentric polygons per panel, decreasing opacity
    const softShadowData: Array<{ polygon: [number, number][]; alpha: number }> = [];
    if (fade > 0.05) {
      for (const p of panels) {
        const hEdge = MOUNT_CLEARANCE_M + panelHeight(p.moduleLengthM, p.tiltDeg);
        const disp = shadowLengthMeters(hEdge, sun.zenithDeg);
        const layers = softShadowLayers(p.polygonMeters, sunVec, hEdge, sun.zenithDeg, 110 * fade);
        for (const l of layers) {
          softShadowData.push({
            polygon: l.polygon.map((v) => {
              const ll = metersOffsetToLatLng(anchor, v);
              return [ll.lng, ll.lat] as [number, number];
            }),
            alpha: l.alpha,
          });
        }
      }
    }

    const shadowLayers = fade > 0.05
      ? [new PolygonLayer({
          id: 'panel-shadows',
          data: softShadowData,
          getPolygon: (d) => d.polygon,
          getFillColor: (d) => [10, 14, 24, Math.round(d.alpha)],
          stroked: false,
          pickable: false,
          parameters: { depthTest: false },
        })]
      : [];

    // ---- Instanced, textured panel meshes (split by selection) -------------
    const getPosition = (p: PanelFootprint): [number, number, number] => {
      const ll = metersOffsetToLatLng(anchor, p.centerMeters);
      const z = is3D ? MOUNT_CLEARANCE_M + panelHeight(p.moduleLengthM, p.tiltDeg) / 2 : 0.1;
      return [ll.lng, ll.lat, z];
    };
    const getOrientation = (p: PanelFootprint): [number, number, number] => [
      is3D ? p.tiltDeg : 0, // pitch
      p.gridRotationDeg + 90, // yaw (align mesh +x with the slope/facing axis)
      0,
    ];
    const getScale = (p: PanelFootprint): [number, number, number] =>
      is3D
        ? [p.moduleLengthM, p.widthM, 1] // real module, tilted
        : [p.heightM, p.widthM, 1]; // footprint (ground projection), flat

    const makeMeshLayer = (id: string, data: PanelFootprint[], sel: boolean) =>
      new SimpleMeshLayer<PanelFootprint>({
        id,
        data,
        mesh: QUAD,
        texture: getPanelTexture(sel),
        getPosition,
        getOrientation,
        getScale,
        sizeScale: 1,
        // deck default material + default lights (standard Phong, not the darker
        // 'pbr' path). The texture supplies the detail; light adds dimensionality
        // in 3D without washing the panels out.
        material: true,
        pickable: true,
        parameters: { depthTest: is3D },
        updateTriggers: {
          getPosition: [viewMode, anchor.lat, anchor.lng],
          getOrientation: [viewMode],
          getScale: [viewMode],
        },
      });

    const unselected = panels.filter((p) => !selected.has(p.rowId));
    const selPanels = panels.filter((p) => selected.has(p.rowId));

    const layers: any[] = [...shadowLayers, makeMeshLayer('panels', unselected, false)];
    if (selPanels.length) layers.push(makeMeshLayer('panels-selected', selPanels, true));

    // ---- Mount piers (3D only) ---------------------------------------------
    if (is3D) {
      const pierHalf = 0.06; // meters
      const pierData = panels.map((p) => {
        const c = p.centerMeters;
        const square: Vec2[] = [
          { x: c.x - pierHalf, y: c.y - pierHalf },
          { x: c.x + pierHalf, y: c.y - pierHalf },
          { x: c.x + pierHalf, y: c.y + pierHalf },
          { x: c.x - pierHalf, y: c.y + pierHalf },
        ];
        return {
          polygon: square.map((v) => {
            const ll = metersOffsetToLatLng(anchor, v);
            return [ll.lng, ll.lat] as [number, number];
          }),
          elevation: MOUNT_CLEARANCE_M,
        };
      });
      layers.push(
        new PolygonLayer({
          id: 'mount-piers',
          data: pierData,
          getPolygon: (d) => d.polygon,
          getElevation: (d) => d.elevation,
          extruded: true,
          getFillColor: [90, 96, 104, 220],
          stroked: false,
          pickable: false,
        })
      );
    }

    // ---- Row/Block Labels (2D only, offset with leader lines) ---------------
    if (!is3D && showLabels && panels.length > 0) {
      // Group panels by rowId to compute row centers and extents
      const rowGroups = new Map<string, PanelFootprint[]>();
      panels.forEach((p) => {
        if (!rowGroups.has(p.rowId)) rowGroups.set(p.rowId, []);
        rowGroups.get(p.rowId)!.push(p);
      });

      // Row label offset: push label 3m north (negative y) of row center so it
      // doesn't sit on top of the panels. A thin leader line connects back.
      const LABEL_OFFSET_M = 3;

      const rowData: Array<{
        position: [number, number, number];
        anchor: [number, number];
        text: string;
        rowId: string;
        blockIdx: string;
      }> = [];

      const leaderData: Array<{
        sourcePosition: [number, number];
        targetPosition: [number, number];
      }> = [];

      for (const [rowId, rowPanels] of rowGroups) {
        const centerX = rowPanels.reduce((s, p) => s + p.centerMeters.x, 0) / rowPanels.length;
        const centerY = rowPanels.reduce((s, p) => s + p.centerMeters.y, 0) / rowPanels.length;
        const ll = metersOffsetToLatLng(anchor, { x: centerX, y: centerY });
        const labelLL = metersOffsetToLatLng(anchor, { x: centerX, y: centerY - LABEL_OFFSET_M });

        const parts = rowId.split('_');
        const blockIdx = parts.find(p => p.startsWith('b'))?.slice(1) ?? '?';
        const rowIdx = parts.find(p => p.startsWith('r'))?.slice(1) ?? '?';

        rowData.push({
          position: [labelLL.lng, labelLL.lat, 0.3] as [number, number, number],
          anchor: [ll.lng, ll.lat] as [number, number],
          text: `R${rowIdx}`,
          rowId,
          blockIdx,
        });

        leaderData.push({
          sourcePosition: [labelLL.lng, labelLL.lat] as [number, number],
          targetPosition: [ll.lng, ll.lat] as [number, number],
        });
      }

      // Leader lines from label to row center
      layers.push(
        new PathLayer({
          id: 'label-leaders',
          data: leaderData,
          getSourcePosition: (d) => d.sourcePosition,
          getTargetPosition: (d) => d.targetPosition,
          getColor: [255, 255, 255, 100],
          getWidth: 1,
          pickable: false,
          parameters: { depthTest: false },
        })
      );

      layers.push(
        new TextLayer({
          id: 'row-labels',
          data: rowData,
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: 11,
          getColor: [255, 255, 255, 230],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'center',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );

      // Block labels (larger, at block centroids)
      const blockGroups = new Map<string, PanelFootprint[]>();
      panels.forEach((p) => {
        if (!blockGroups.has(p.blockId)) blockGroups.set(p.blockId, []);
        blockGroups.get(p.blockId)!.push(p);
      });

      const blockData = Array.from(blockGroups.entries()).map(([blockId, blockPanels]) => {
        const centerX = blockPanels.reduce((s, p) => s + p.centerMeters.x, 0) / blockPanels.length;
        const centerY = blockPanels.reduce((s, p) => s + p.centerMeters.y, 0) / blockPanels.length;
        const ll = metersOffsetToLatLng(anchor, { x: centerX, y: centerY });
        
        const blockIdx = blockId.split('_').find(p => p.startsWith('b'))?.slice(1) ?? '?';
        
        return {
          position: [ll.lng, ll.lat, 0.4] as [number, number, number],
          text: `Block ${blockIdx}`,
        };
      });

      layers.push(
        new TextLayer({
          id: 'block-labels',
          data: blockData,
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: 12,
          getColor: [245, 158, 11, 255],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'center',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );
    }

    // ---- Distance Measurements (2D only) -----------------------------------
    if (!is3D && showMeasurements && panels.length > 1) {
      // Group panels by row to compute inter-row pitch
      const rowGroups = new Map<string, PanelFootprint[]>();
      panels.forEach((p) => {
        if (!rowGroups.has(p.rowId)) rowGroups.set(p.rowId, []);
        rowGroups.get(p.rowId)!.push(p);
      });

      const rows = Array.from(rowGroups.values());
      if (rows.length >= 2) {
        // Sort rows by their position along the facing axis
        const rowCenters = rows.map((rowPanels) => {
          const centerX = rowPanels.reduce((s, p) => s + p.centerMeters.x, 0) / rowPanels.length;
          const centerY = rowPanels.reduce((s, p) => s + p.centerMeters.y, 0) / rowPanels.length;
          return { x: centerX, y: centerY, panels: rowPanels };
        });

        // Use the first row's azimuth to define the facing axis
        const firstAz = rows[0][0].azimuthDeg;
        const facingRad = (firstAz * Math.PI) / 180;
        const facingX = Math.sin(facingRad);
        const facingY = -Math.cos(facingRad);

        // Project row centers onto the facing axis
        const projected = rowCenters.map((rc) => ({
          ...rc,
          proj: rc.x * facingX + rc.y * facingY,
        }));
        projected.sort((a, b) => a.proj - b.proj);

        // Compute inter-row pitch (distance between consecutive row centers)
        const measurementData: {
          path: [number, number, number][];
          text: string;
          position: [number, number, number];
        }[] = [];

        for (let i = 0; i < projected.length - 1; i++) {
          const r1 = projected[i];
          const r2 = projected[i + 1];
          const distM = Math.sqrt(
            (r2.x - r1.x) ** 2 + (r2.y - r1.y) ** 2
          );

          // Midpoint for the label
          const midX = (r1.x + r2.x) / 2;
          const midY = (r1.y + r2.y) / 2;
          const midLL = metersOffsetToLatLng(anchor, { x: midX, y: midY });

          // Start and end points for the line
          const startLL = metersOffsetToLatLng(anchor, { x: r1.x, y: r1.y });
          const endLL = metersOffsetToLatLng(anchor, { x: r2.x, y: r2.y });

          measurementData.push({
            path: [
              [startLL.lng, startLL.lat, 0.2],
              [endLL.lng, endLL.lat, 0.2],
            ],
            text: `${distM.toFixed(2)}m`,
            position: [midLL.lng, midLL.lat, 0.3],
          });
        }

        // Add measurement lines
        layers.push(
          new PathLayer({
            id: 'measurement-lines',
            data: measurementData,
            getPath: (d) => d.path,
            getColor: [245, 158, 11, 180],
            getWidth: 2,
            widthMinPixels: 1,
            pickable: false,
            parameters: { depthTest: false },
          })
        );

        // Add measurement labels
        layers.push(
          new TextLayer({
            id: 'measurement-labels',
            data: measurementData,
            getPosition: (d) => d.position,
            getText: (d) => d.text,
            getSize: 10,
            getColor: [245, 158, 11, 255],
            getTextAnchor: 'middle',
            getAlignmentBaseline: 'bottom',
            fontFamily: 'monospace',
            fontWeight: 'bold',
            billboard: false,
            parameters: { depthTest: false },
          })
        );
      }
    }

    // ---- String Visualization (2D only) ------------------------------------
    if (!is3D && showStrings && strings.length > 0 && panels.length > 0) {
      // Create a map from panel ID to string index
      const panelStringMap = new Map<string, number>();
      strings.forEach((s) => {
        s.panelIds.forEach((pid) => panelStringMap.set(pid, s.index));
      });

      // Color panels by string
      const stringPanelData = panels
        .filter((p) => panelStringMap.has(p.id))
        .map((p) => {
          const stringIdx = panelStringMap.get(p.id)!;
          return {
            polygon: p.polygonMeters.map((v) => {
              const llv = metersOffsetToLatLng(anchor, v);
              return [llv.lng, llv.lat] as [number, number];
            }),
            color: getStringColor(stringIdx),
          };
        });

      layers.push(
        new PolygonLayer({
          id: 'string-panels',
          data: stringPanelData,
          getPolygon: (d) => d.polygon,
          getFillColor: (d) => d.color,
          stroked: false,
          pickable: false,
          parameters: { depthTest: false },
        })
      );

      // String labels
      const stringLabelData = strings.map((s) => {
        const rowPanels = panels.filter((p) => s.panelIds.includes(p.id));
        const centerX = rowPanels.reduce((sum, p) => sum + p.centerMeters.x, 0) / rowPanels.length;
        const centerY = rowPanels.reduce((sum, p) => sum + p.centerMeters.y, 0) / rowPanels.length;
        const ll = metersOffsetToLatLng(anchor, { x: centerX, y: centerY });
        return {
          position: [ll.lng, ll.lat, 0.5] as [number, number, number],
          text: `S${s.index + 1}`,
          color: getStringColor(s.index),
        };
      });

      layers.push(
        new TextLayer({
          id: 'string-labels',
          data: stringLabelData,
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: 9,
          getColor: (d) => d.color,
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'center',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );
    }

    // ---- Inverter Markers (2D only) ----------------------------------------
    if (!is3D && showInverters && inverters.length > 0) {
      const inverterData = inverters.map((inv) => ({
        position: [inv.positionLatLng.lng, inv.positionLatLng.lat, 0.3] as [number, number, number],
        name: inv.model,
        capacity: `${inv.capacityKw}kW`,
        strings: `${inv.stringCount} strings`,
      }));

      // Inverter circles
      layers.push(
        new ScatterplotLayer({
          id: 'inverter-markers',
          data: inverterData,
          getPosition: (d) => d.position,
          getRadius: 4,
          getFillColor: [245, 158, 11, 255],
          getLineColor: [255, 255, 255, 255],
          getLineWidth: 2,
          radiusUnits: 'pixels',
          pickable: false,
          parameters: { depthTest: false },
        })
      );

      // Inverter labels
      layers.push(
        new TextLayer({
          id: 'inverter-labels',
          data: inverterData,
          getPosition: (d) => [d.position[0], d.position[1], 0.4],
          getText: (d) => `${d.capacity}`,
          getSize: 10,
          getColor: [255, 255, 255, 255],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'bottom',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );
    }

    // ---- Wiring Paths (2D only) --------------------------------------------
    if (!is3D && showInverters && wiringPaths.length > 0) {
      const wiringData = wiringPaths.map((wp) => ({
        path: [
          [wp.panelPosition.lng, wp.panelPosition.lat, 0.15],
          [wp.inverterPosition.lng, wp.inverterPosition.lat, 0.15],
        ] as [number, number, number][],
        color: getStringColor(wp.stringIndex),
      }));

      layers.push(
        new PathLayer({
          id: 'wiring-paths',
          data: wiringData,
          getPath: (d) => d.path,
          getColor: (d) => d.color,
          getWidth: 1,
          widthMinPixels: 1,
          pickable: false,
          parameters: { depthTest: false },
        })
      );
    }

    // ---- Setback/Boundary Lines (2D only) ----------------------------------
    if (!is3D && showSetbacks && setbackLines.length > 0) {
      // Setback polygon lines
      const setbackPathData = setbackLines.flatMap((setback) => {
        const vertices = setback.polygonLatLng;
        if (vertices.length < 2) return [];
        
        const path: [number, number, number][] = vertices.map((v) => [
          v.lng,
          v.lat,
          0.12,
        ]);
        // Close the polygon
        path.push([vertices[0].lng, vertices[0].lat, 0.12]);
        
        return [{ path, color: setback.color, type: setback.type }];
      });

      layers.push(
        new PathLayer({
          id: 'setback-lines',
          data: setbackPathData,
          getPath: (d) => d.path,
          getColor: (d) => d.color,
          getWidth: 2,
          widthMinPixels: 1,
          pickable: false,
          parameters: { depthTest: false },
        })
      );

      // Setback labels
      const setbackLabelData = setbackLines.map((setback) => {
        const vertices = setback.polygonLatLng;
        const midLat = (vertices[0].lat + vertices[1].lat) / 2;
        const midLng = (vertices[0].lng + vertices[1].lng) / 2;
        return {
          position: [midLng, midLat, 0.15] as [number, number, number],
          text: setback.description,
          color: setback.color,
        };
      });

      layers.push(
        new TextLayer({
          id: 'setback-labels',
          data: setbackLabelData,
          getPosition: (d) => d.position,
          getText: (d) => d.text,
          getSize: 9,
          getColor: (d) => d.color,
          getTextAnchor: 'start',
          getAlignmentBaseline: 'bottom',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );
    }

    // ---- Obstacle footprints + shadows + labels ----------------------------
    if (obstacles.length > 0) {
      const halfW = (o: ObstacleData) => o.widthM / 2;
      const halfH = (o: ObstacleData) => o.widthM / 2; // square footprint

      // Helper: footprint corners in meter frame
      const footprintMeters = (o: ObstacleData): Vec2[] => {
        const mPerLat = 111320.0;
        const mPerLon = 111320.0 * Math.cos((anchor.lat * Math.PI) / 180);
        const cx = (o.lng - anchor.lng) * mPerLon;
        const cy = (o.lat - anchor.lat) * mPerLat;
        const hw = halfW(o);
        const hh = halfH(o);
        return [
          { x: cx - hw, y: cy - hh },
          { x: cx + hw, y: cy - hh },
          { x: cx + hw, y: cy + hh },
          { x: cx - hw, y: cy + hh },
        ];
      };

      const toLatLng = (v: Vec2) => {
        const ll = metersOffsetToLatLng(anchor, v);
        return [ll.lng, ll.lat] as [number, number];
      };

      // Compute obstacle shadow polygons — unified with panel shadow geometry
      const obstacleShadowLayers: any[] = [];
      if (fade > 0.05) {
        for (const o of obstacles) {
          const corners = footprintMeters(o) as [Vec2, Vec2, Vec2, Vec2];
          const soft = softShadowLayers(corners, sunVec, o.heightM, sun.zenithDeg, 90 * fade);
          for (const l of soft) {
            obstacleShadowLayers.push({
              polygon: l.polygon.map((v) => {
                const ll = metersOffsetToLatLng(anchor, v);
                return [ll.lng, ll.lat] as [number, number];
              }),
              alpha: l.alpha,
            });
          }
        }
      }

      if (obstacleShadowLayers.length > 0) {
        layers.push(
          new PolygonLayer({
            id: 'obstacle-shadows',
            data: obstacleShadowLayers,
            getPolygon: (d: any) => d.polygon,
            getFillColor: (d: any) => [10, 14, 24, Math.round(d.alpha)],
            stroked: false,
            pickable: false,
            parameters: { depthTest: false },
          })
        );
      }

      // Obstacle footprint polygons
      const obstacleFootprintData = obstacles.map((o) => {
        const footprint = footprintMeters(o).map(toLatLng);
        const color = OBSTACLE_COLORS[o.type] || OBSTACLE_COLORS.other;
        const isSelected = o.id === selectedObstacleId;
        return { polygon: footprint, color, isSelected, type: o.type, heightM: o.heightM };
      });

      layers.push(
        new PolygonLayer({
          id: 'obstacles',
          data: obstacleFootprintData,
          getPolygon: (d: any) => d.polygon,
          getFillColor: (d: any) => [...d.color, d.isSelected ? 100 : 60],
          getLineColor: (d: any) => d.isSelected ? [255, 255, 0] : d.color,
          getLineWidth: (d: any) => d.isSelected ? 3 : 1.5,
          stroked: true,
          pickable: true,
          parameters: { depthTest: false },
        })
      );

      // Obstacle labels
      const obstacleLabelData = obstacles.map((o) => {
        const ll = { lat: o.lat, lng: o.lng };
        const label = o.type.charAt(0).toUpperCase() + o.type.slice(1);
        return {
          position: [ll.lng, ll.lat, 0.2] as [number, number, number],
          text: `${label} ${o.heightM.toFixed(0)}m`,
        };
      });

      layers.push(
        new TextLayer({
          id: 'obstacle-labels',
          data: obstacleLabelData,
          getPosition: (d: any) => d.position,
          getText: (d: any) => d.text,
          getSize: 10,
          getColor: [255, 255, 255, 220],
          getTextAnchor: 'middle',
          getAlignmentBaseline: 'bottom',
          fontFamily: 'monospace',
          fontWeight: 'bold',
          billboard: false,
          parameters: { depthTest: false },
        })
      );
    }

    overlayRef.current.setProps({
      layers,
      onClick: (info: any) => {
        // Check if an obstacle was clicked
        if (info?.object?.type && info?.object?.polygon && setSelectedObstacleId) {
          const clickedObstacle = obstacles.find(o => {
            const ll = { lat: o.lat, lng: o.lng };
            return Math.abs(ll.lat - info.object.polygon[0][1]) < 0.0001;
          });
          if (clickedObstacle) {
            setSelectedObstacleId(clickedObstacle.id);
            return;
          }
        }
        if (!setSelectedRowIds) return;
        if (info?.object?.rowId) {
          const rowId = info.object.rowId as string;
          setSelectedRowIds(selectedRowIds.includes(rowId) ? [] : [rowId]);
        } else {
          setSelectedRowIds([]);
        }
      },
    });
  }, [panels, anchor, selectedRowIds, setSelectedRowIds, sun, viewMode, visible, showLabels, showMeasurements, showStrings, showInverters, showSetbacks, strings, inverters, wiringPaths, setbackLines, obstacles, selectedObstacleId, setSelectedObstacleId]);

  return null;
}

// Realistic Solar Panel 3D Model Generator
// Creates detailed solar panel meshes with proper dimensions and materials

// Creates detailed solar panel meshes with proper dimensions and materials

// import * as THREE from 'https://cdn.skypack.dev/three@0.132.2'; // REMOVED
const THREE = window.THREE;


/**
 * Creates a realistic solar panel mesh group
 * Standard dimensions: 1.65m × 1.0m × 0.04m (typical residential solar panel)
 * @param {number} scale - Mercator coordinate scale factor
 * @returns {THREE.Group} Panel mesh group
 */
export function createRealisticPanel(scale) {
    const group = new THREE.Group();

    // Standard Residential Panel Dimensions (approx 60 cell)
    const LENGTH = 1.65;
    const WIDTH = 1.0;
    const THICKNESS = 0.04;
    const FRAME_WIDTH = 0.03;

    // --- 1. ALUMINUM FRAME ---
    // Silver anodized aluminum (Standard Material)
    const frameMat = new THREE.MeshStandardMaterial({
        color: 0xcccccc,
        roughness: 0.5,
        metalness: 0.8
    });

    // Create 4 pieces for the frame
    const frameGeoH = new THREE.BoxGeometry(LENGTH * scale, FRAME_WIDTH * scale, THICKNESS * scale);
    const frameGeoV = new THREE.BoxGeometry(FRAME_WIDTH * scale, (WIDTH - 2 * FRAME_WIDTH) * scale, THICKNESS * scale);

    // Top Frame
    const topFrame = new THREE.Mesh(frameGeoH, frameMat);
    topFrame.position.set(0, (WIDTH / 2 - FRAME_WIDTH / 2) * scale, 0);
    group.add(topFrame);

    // Bottom Frame
    const bottomFrame = new THREE.Mesh(frameGeoH, frameMat);
    bottomFrame.position.set(0, -(WIDTH / 2 - FRAME_WIDTH / 2) * scale, 0);
    group.add(bottomFrame);

    // Left Frame
    const leftFrame = new THREE.Mesh(frameGeoV, frameMat);
    leftFrame.position.set(-(LENGTH / 2 - FRAME_WIDTH / 2) * scale, 0, 0);
    group.add(leftFrame);

    // Right Frame
    const rightFrame = new THREE.Mesh(frameGeoV, frameMat);
    rightFrame.position.set((LENGTH / 2 - FRAME_WIDTH / 2) * scale, 0, 0);
    group.add(rightFrame);


    // --- 2. SOLAR CELLS & GLASS SURACE ---
    // The active area sits inside the frame
    const cellAreaLength = LENGTH - 2 * FRAME_WIDTH;
    const cellAreaWidth = WIDTH - 2 * FRAME_WIDTH;

    // Geometry for the panel face
    // Slightly thinner than frame, sat slightly below frame top
    const panelGeo = new THREE.BoxGeometry(
        cellAreaLength * scale,
        cellAreaWidth * scale,
        (THICKNESS * 0.5) * scale
    );

    // Generate High-Res Texture
    const texture = createSolarCellTexture();

    // Glass/Cell Material
    // Use Standard material for interaction with lights (shininess/reflection)
    const glassMat = new THREE.MeshStandardMaterial({
        map: texture,
        color: 0xffffff,
        roughness: 0.2,
        metalness: 0.1,
        side: THREE.DoubleSide
    });

    const panelMesh = new THREE.Mesh(panelGeo, glassMat);
    panelMesh.renderOrder = 999; // Force draw last
    // Position it slightly below the frame top (z is up/thickness here?? No y is up in ThreeJS geometry usually, but we rotate z later)
    // In BoxGeometry created here: Y is Width, X is Length, Z is Thickness.
    // Frame is at Z=0 (center). Frame height is THICKNESS. Top of frame is Z = THICKNESS/2.
    // Panel thickness is THICKNESS*0.5. WE want top of panel to be slightly below top of frame.
    // Top of panel = Z_pos + THICKNESS*0.25.
    // We want Z_pos + THICKNESS*0.25 = THICKNESS/2 - 0.005 (recessed 5mm).
    // Z_pos = THICKNESS/2 - 0.005 - THICKNESS/4.

    // Simplified: Just center it, it looks fine.
    panelMesh.position.z = -0.005 * scale; // Recess slightly
    group.add(panelMesh);


    // --- 3. BACKSHEET (White/Black) ---
    // Visible from bottom (if flipped) - Optional optimization: skip if not rotating
    const backGeo = new THREE.BoxGeometry(LENGTH * scale, WIDTH * scale, 0.001 * scale);
    const backMat = new THREE.MeshBasicMaterial({ color: 0xffffff }); // White backsheet
    const backMesh = new THREE.Mesh(backGeo, backMat);
    backMesh.position.z = -THICKNESS / 2 * scale; // Bottom
    group.add(backMesh);

    return group;
}

/**
 * Creates a high-fidelity procedural texture showing solar cells, busbars, and fingers.
 * @returns {THREE.CanvasTexture}
 */
function createSolarCellTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 1024; // High res
    canvas.height = 1024;
    const ctx = canvas.getContext('2d');

    // 1. Background (Backsheet gaps - White or Black)
    // Monocrystalline usually has white diamonds, Polycrystalline is solid blue.
    // Let's do Monocrystalline aesthetics (Black/Dark Blue with white diamond gaps)
    ctx.fillStyle = '#ffffff'; // White backsheet
    ctx.fillRect(0, 0, 1024, 1024);

    // 2. Cells (6 rows x 10 cols)
    const ROWS = 6;
    const COLS = 10;
    const GAP = 4; // pixels
    const CELL_W = (1024 - (COLS + 1) * GAP) / COLS;
    const CELL_H = (1024 - (ROWS + 1) * GAP) / ROWS;

    // Draw Cells
    for (let r = 0; r < ROWS; r++) {
        for (let c = 0; c < COLS; c++) {
            const x = GAP + c * (CELL_W + GAP);
            const y = GAP + r * (CELL_H + GAP);

            // Cell Color: Deep Blue/Black Gradient
            const grad = ctx.createLinearGradient(x, y, x + CELL_W, y + CELL_H);
            grad.addColorStop(0, '#0f172a'); // Slate 900
            grad.addColorStop(0.5, '#1e3a8a'); // Blue 900
            grad.addColorStop(1, '#0f172a');

            ctx.fillStyle = grad;

            // Monocrystalline "Cut Corners" (pseudo-diamond shape)
            // Just drawing rectangles for now, corners are subtle.
            ctx.fillRect(x, y, CELL_W, CELL_H);

            // 3. Busbars (Silver lines)
            // Top to bottom of cell
            const BUSBARS = 5; // Modern panels have 5+
            ctx.fillStyle = '#d1d5db'; // Silver (Gray 300)
            const busbarWidth = 2; // Thin
            const spacing = CELL_W / (BUSBARS + 1);

            for (let b = 1; b <= BUSBARS; b++) {
                ctx.fillRect(x + b * spacing - busbarWidth / 2, y, busbarWidth, CELL_H);
            }
        }
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.anisotropy = 4; // Sharper at angles
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;

    return texture;
}

/**
 * Creates a simple box panel (fallback/performance mode)
 * @param {number} scale - Mercator coordinate scale factor
 * @param {number} color - Panel color
 * @returns {THREE.Mesh}
 */
export function createSimplePanel(scale, color = 0x00ffff) {
    // DEBUG: Increased thickness and bright color
    const geometry = new THREE.BoxGeometry(1.65 * scale, 1.0 * scale, 0.2 * scale); // Thicker for visibility
    const material = new THREE.MeshBasicMaterial({
        color: 0x00ffff, // Cyan
        side: THREE.DoubleSide
    });
    return new THREE.Mesh(geometry, material);
}

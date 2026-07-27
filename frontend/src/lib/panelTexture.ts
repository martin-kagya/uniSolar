/**
 * panelTexture.ts
 *
 * Procedurally draws a photorealistic monocrystalline PV module texture onto an
 * offscreen <canvas>, cached and reused across every panel instance in the deck.gl
 * SimpleMeshLayer. One sharp texture, thousands of instances — cheap and crisp at
 * any zoom.
 *
 * The texture is drawn "portrait" (cells taller than wide-ish grid); the mesh layer
 * scales/orients it to each panel's real footprint.
 */

let cachedGlass: HTMLCanvasElement | null = null;
let cachedSelected: HTMLCanvasElement | null = null;

interface PanelStyle {
  /** Deep silicon color at the top of the anti-reflective gradient. */
  glassTop: string;
  /** Near-black silicon color at the bottom of the gradient. */
  glassBottom: string;
  /** Cell gap / grid line color. */
  gap: string;
  /** Busbar (fine conductor) color. */
  busbar: string;
  /** Aluminium frame color. */
  frame: string;
  /** Specular sheen color (drawn semi-transparent). */
  sheen: string;
}

const DEFAULT_STYLE: PanelStyle = {
  glassTop: '#1b3a63',
  glassBottom: '#0a1526',
  gap: '#060b16',
  busbar: 'rgba(150,180,220,0.25)',
  frame: '#c8ccd4',
  sheen: 'rgba(255,255,255,0.10)',
};

const SELECTED_STYLE: PanelStyle = {
  glassTop: '#7a4f12',
  glassBottom: '#2a1a05',
  gap: '#1a1206',
  busbar: 'rgba(255,214,140,0.30)',
  frame: '#fbbf24',
  sheen: 'rgba(255,240,200,0.16)',
};

const COLS = 6; // cells across
const ROWS = 12; // cells down (portrait 60-cell layout)

function drawPanel(style: PanelStyle): HTMLCanvasElement {
  const W = 256;
  const H = 512;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d')!;

  // Aluminium frame fills the whole texture; glass inset sits on top.
  ctx.fillStyle = style.frame;
  ctx.fillRect(0, 0, W, H);

  const bezel = 8;
  const gx = bezel;
  const gy = bezel;
  const gw = W - bezel * 2;
  const gh = H - bezel * 2;

  // Anti-reflective glass gradient with sky-tint effect
  const grad = ctx.createLinearGradient(0, gy, 0, gy + gh);
  grad.addColorStop(0, style.glassTop);
  grad.addColorStop(0.6, style.glassBottom);
  grad.addColorStop(1, style.glassBottom);
  ctx.fillStyle = grad;
  ctx.fillRect(gx, gy, gw, gh);

  // Sky-reflective band across upper third (lighter, bluer tint)
  const skyGrad = ctx.createLinearGradient(0, gy, 0, gy + gh * 0.35);
  skyGrad.addColorStop(0, 'rgba(140,180,220,0.12)');
  skyGrad.addColorStop(1, 'rgba(140,180,220,0)');
  ctx.fillStyle = skyGrad;
  ctx.fillRect(gx, gy, gw, gh * 0.35);

  // Cell grid
  const cellW = gw / COLS;
  const cellH = gh / ROWS;
  const inset = Math.max(1, cellW * 0.09); // gap between cells (visible cell separation)
  const chamfer = cellW * 0.16; // monocrystalline chamfered corners

  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = gx + c * cellW + inset;
      const y = gy + r * cellH + inset;
      const w = cellW - inset * 2;
      const h = cellH - inset * 2;

      // Cell body (chamfered rectangle) with its own subtle vertical sheen
      const cellGrad = ctx.createLinearGradient(x, y, x, y + h);
      cellGrad.addColorStop(0, style.glassTop);
      cellGrad.addColorStop(1, style.glassBottom);
      ctx.fillStyle = cellGrad;
      ctx.beginPath();
      ctx.moveTo(x + chamfer, y);
      ctx.lineTo(x + w - chamfer, y);
      ctx.lineTo(x + w, y + chamfer);
      ctx.lineTo(x + w, y + h - chamfer);
      ctx.lineTo(x + w - chamfer, y + h);
      ctx.lineTo(x + chamfer, y + h);
      ctx.lineTo(x, y + h - chamfer);
      ctx.lineTo(x, y + chamfer);
      ctx.closePath();
      ctx.fill();

      // Busbars: two fine vertical conductors per cell
      ctx.strokeStyle = style.busbar;
      ctx.lineWidth = 1;
      for (const bx of [x + w * 0.34, x + w * 0.66]) {
        ctx.beginPath();
        ctx.moveTo(bx, y);
        ctx.lineTo(bx, y + h);
        ctx.stroke();
      }
    }
  }

  // Cell grid gap lines (drawn over to darken seams)
  ctx.strokeStyle = style.gap;
  ctx.lineWidth = Math.max(1.5, inset * 1.1);
  for (let c = 1; c < COLS; c++) {
    const x = gx + c * cellW;
    ctx.beginPath();
    ctx.moveTo(x, gy);
    ctx.lineTo(x, gy + gh);
    ctx.stroke();
  }
  for (let r = 1; r < ROWS; r++) {
    const y = gy + r * cellH;
    ctx.beginPath();
    ctx.moveTo(gx, y);
    ctx.lineTo(gx + gw, y);
    ctx.stroke();
  }

  // Diagonal specular sheen highlight across the glass (stronger glass reflection)
  const sheen = ctx.createLinearGradient(gx, gy, gx + gw * 0.7, gy + gh * 0.5);
  sheen.addColorStop(0, 'rgba(255,255,255,0)');
  sheen.addColorStop(0.25, 'rgba(255,255,255,0)');
  sheen.addColorStop(0.35, style.sheen);
  sheen.addColorStop(0.45, 'rgba(255,255,255,0.04)');
  sheen.addColorStop(0.55, style.sheen);
  sheen.addColorStop(0.65, 'rgba(255,255,255,0)');
  sheen.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = sheen;
  ctx.fillRect(gx, gy, gw, gh);

  // Bottom edge darkening (subtle vignette)
  const vignette = ctx.createLinearGradient(0, gy + gh * 0.7, 0, gy + gh);
  vignette.addColorStop(0, 'rgba(0,0,0,0)');
  vignette.addColorStop(1, 'rgba(0,0,0,0.10)');
  ctx.fillStyle = vignette;
  ctx.fillRect(gx, gy + gh * 0.7, gw, gh * 0.3);

  return canvas;
}

/**
 * Returns the shared module texture canvas. `selected` yields the amber-tinted
 * variant used to highlight the active row(s).
 */
export function getPanelTexture(selected = false): HTMLCanvasElement {
  if (selected) {
    if (!cachedSelected) cachedSelected = drawPanel(SELECTED_STYLE);
    return cachedSelected;
  }
  if (!cachedGlass) cachedGlass = drawPanel(DEFAULT_STYLE);
  return cachedGlass;
}

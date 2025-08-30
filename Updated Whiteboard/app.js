/**
 * Handwriting Board - Portable JS Webapp
 * License: MIT
 * Features:
 * - Pointer events (mouse, touch, pen) with pressure support
 * - Pen and eraser tools
 * - Adjustable color and size
 * - Undo/redo stack
 * - Clear board
 * - Save as PNG / SVG
 * - High-DPI crisp rendering with devicePixelRatio scaling
 * - Responsive canvas that preserves drawing on resize
 */

/* Elements */
const canvas = document.getElementById('board');
const container = document.getElementById('board-container');
const colorInput = document.getElementById('color');
const sizeInput = document.getElementById('size');
const sizeVal = document.getElementById('sizeVal');
const undoBtn = document.getElementById('undo');
const redoBtn = document.getElementById('redo');
const clearBtn = document.getElementById('clear');
const savePngBtn = document.getElementById('savePng');
const saveSvgBtn = document.getElementById('saveSvg');
const toolPen = document.getElementById('tool-pen');
const toolEraser = document.getElementById('tool-eraser');
const bgColorInput = document.getElementById('bgColor');
const ossLink = document.getElementById('ossLink');

ossLink.href = 'https://opensource.org/license/mit';
ossLink.textContent = 'Open Source (MIT)';

/* Canvas 2D Context */
const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true, willReadFrequently: false });

/* State */
let dpr = Math.max(1, window.devicePixelRatio || 1);
let isDrawing = false;
let lastPoint = null;
let currentStroke = null;
let needsFullRedraw = true;
let bgColor = bgColorInput ? bgColorInput.value : '#1d2230';
canvas.style.backgroundColor = bgColor;
canvas.style.backgroundColor = bgColor;

/* History stacks */
const history = [];      // Array<Stroke>
const redoStack = [];    // Array<Stroke>

/* Stroke structure:
{
  tool: 'pen' | 'eraser',
  color: string,
  size: number,
  points: Array<{x:number,y:number,p:number}> // x/y in CSS pixels, p = pressure (0..1)
}
*/

/* Utilities */
function setCanvasSize() {
  const rect = container.getBoundingClientRect();
  const cssW = Math.max(1, Math.floor(rect.width));
  const cssH = Math.max(1, Math.floor(rect.height));
  dpr = Math.max(1, window.devicePixelRatio || 1);

  // Preserve content by redrawing from history after resize
  canvas.width = Math.floor(cssW * dpr);
  canvas.height = Math.floor(cssH * dpr);
  canvas.style.width = cssW + 'px';
  canvas.style.height = cssH + 'px';

  ctx.setTransform(1, 0, 0, 1, 0, 0); // reset
  ctx.scale(dpr, dpr);
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  fullRedraw();
}

function getPos(evt) {
  const rect = canvas.getBoundingClientRect();
  let x, y, p = 0.5;

  if (evt instanceof PointerEvent) {
    x = evt.clientX - rect.left;
    y = evt.clientY - rect.top;
    p = evt.pressure && evt.pressure > 0 ? evt.pressure : (evt.pointerType === 'mouse' ? 0.5 : 0.5);
  } else if (evt.touches && evt.touches[0]) {
    x = evt.touches[0].clientX - rect.left;
    y = evt.touches[0].clientY - rect.top;
    p = 0.5;
  } else {
    x = 0; y = 0; p = 0.5;
  }

  return { x, y, p };
}

function lerp(a, b, t) { return a + (b - a) * t; }

/* Smoothing: simple moving average with window=2 using lastPoint */
function smoothedPoint(prev, curr) {
  if (!prev) return curr;
  return {
    x: lerp(prev.x, curr.x, 0.5),
    y: lerp(prev.y, curr.y, 0.5),
    p: lerp(prev.p, curr.p, 0.5),
  };
}

/* Draw a stroke incrementally or full */
function drawStroke(stroke, incremental = false) {
  if (!stroke || stroke.points.length < 1) return;

  const isEraser = stroke.tool === 'eraser';
  ctx.save();
  ctx.globalCompositeOperation = isEraser ? 'destination-out' : 'source-over';
  ctx.strokeStyle = isEraser ? 'rgba(0,0,0,1)' : stroke.color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  // Variable width by pressure
  const pressureWidth = (pt) => Math.max(0.5, stroke.size * (0.3 + 0.7 * (pt.p || 0.5)));

  if (incremental) {
    const n = stroke.points.length;
    if (n < 2) { ctx.restore(); return; }
    const a = stroke.points[n - 2];
    const b = stroke.points[n - 1];

    const sa = smoothedPoint(null, a);
    const sb = smoothedPoint(a, b);

    ctx.beginPath();
    ctx.moveTo(sa.x, sa.y);
    ctx.lineWidth = pressureWidth(sb);
    // Quadratic curve between points for smoother line
    const cx = (sa.x + sb.x) / 2;
    const cy = (sa.y + sb.y) / 2;
    ctx.quadraticCurveTo(sa.x, sa.y, cx, cy);
    ctx.quadraticCurveTo(cx, cy, sb.x, sb.y);
    ctx.stroke();
    ctx.restore();
    return;
  }

  // Full redraw for the stroke
  let prev = null;
  for (let i = 0; i < stroke.points.length; i++) {
    const curr = stroke.points[i];
    const sCurr = smoothedPoint(prev, curr);
    if (prev) {
      ctx.beginPath();
      ctx.moveTo(prev.x, prev.y);
      ctx.lineWidth = pressureWidth(sCurr);
      const cx = (prev.x + sCurr.x) / 2;
      const cy = (prev.y + sCurr.y) / 2;
      ctx.quadraticCurveTo(prev.x, prev.y, cx, cy);
      ctx.quadraticCurveTo(cx, cy, sCurr.x, sCurr.y);
      ctx.stroke();
    }
    prev = sCurr;
  }

  ctx.restore();
}

function fullRedraw() {
  // Clear
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.restore();

  // Re-apply scale
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  // Redraw all strokes
  for (const stroke of history) {
    drawStroke(stroke, false);
  }
  needsFullRedraw = false;
  updateButtonsState();
}

function startStroke(evt) {
  evt.preventDefault();
  canvas.setPointerCapture(evt.pointerId);
  isDrawing = true;
  redoStack.length = 0; // invalidate redo on new action

  const { x, y, p } = getPos(evt);
  lastPoint = { x, y, p };
  currentStroke = {
    tool: toolEraser.checked ? 'eraser' : 'pen',
    color: colorInput.value,
    size: Number(sizeInput.value),
    points: [lastPoint],
  };
  drawStroke(currentStroke, true);
}

function extendStroke(evt) {
  if (!isDrawing || !currentStroke) return;
  const { x, y, p } = getPos(evt);

  // Previous point in the current stroke
  const prev = currentStroke.points[currentStroke.points.length - 1];

  // If no previous point (edge case), start with this one
  if (!prev) {
    const first = { x, y, p };
    currentStroke.points.push(first);
    drawStroke(currentStroke, true);
    lastPoint = first;
    return;
  }

  const dx = x - prev.x;
  const dy = y - prev.y;
  const dist = Math.hypot(dx, dy);

  // Densify points based on brush size to keep lines continuous even with low event rates
  const spacing = Math.max(0.5, currentStroke.size * 0.35);
  const steps = Math.floor(dist / spacing);

  if (steps > 0) {
    for (let i = 1; i <= steps; i++) {
      const t = i / (steps + 1);
      const ipt = { x: prev.x + dx * t, y: prev.y + dy * t, p: lerp(prev.p, p, t) };
      currentStroke.points.push(ipt);
      // Draw each interpolated segment to avoid gaps
      drawStroke(currentStroke, true);
    }
  }

  const pt = { x, y, p };
  currentStroke.points.push(pt);
  drawStroke(currentStroke, true);
  lastPoint = pt;
}

function endStroke(evt) {
  if (!isDrawing) return;
  isDrawing = false;
  try {
    canvas.releasePointerCapture(evt.pointerId);
  } catch {}
  if (currentStroke && currentStroke.points.length > 0) {
    history.push(currentStroke);
  }
  currentStroke = null;
  lastPoint = null;
  updateButtonsState();
}

/* UI wiring */
sizeVal.textContent = `${sizeInput.value} px`;
sizeInput.addEventListener('input', () => {
  sizeVal.textContent = `${sizeInput.value} px`;
});

// Background color control
if (bgColorInput) {
  bgColorInput.addEventListener('input', () => {
    bgColor = bgColorInput.value;
    canvas.style.backgroundColor = bgColor;
    fullRedraw();
  });
}

undoBtn.addEventListener('click', () => {
  if (history.length === 0) return;
  const s = history.pop();
  redoStack.push(s);
  fullRedraw();
});

redoBtn.addEventListener('click', () => {
  if (redoStack.length === 0) return;
  const s = redoStack.pop();
  history.push(s);
  fullRedraw();
});

clearBtn.addEventListener('click', () => {
  if (history.length === 0) return;
  history.length = 0;
  redoStack.length = 0;
  fullRedraw();
});

savePngBtn.addEventListener('click', () => {
  // Export at current CSS size with DPR baked in
  const link = document.createElement('a');
  link.download = `handwriting-${Date.now()}.png`;
  link.href = canvas.toDataURL('image/png');
  link.click();
});

saveSvgBtn.addEventListener('click', () => {
  const svg = strokesToSVG(history, canvas.clientWidth, canvas.clientHeight, bgColor);
  const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.download = `handwriting-${Date.now()}.svg`;
  link.href = url;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

/* Keyboard shortcuts */
window.addEventListener('keydown', (e) => {
  // Undo: Ctrl+Z, Redo: Ctrl+Y or Ctrl+Shift+Z
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === 'z') {
    e.preventDefault();
    if (e.shiftKey) {
      redoBtn.click();
    } else {
      undoBtn.click();
    }
  } else if (ctrl && e.key.toLowerCase() === 'y') {
    e.preventDefault();
    redoBtn.click();
  }
});

/* Pointer events */
canvas.addEventListener('pointerdown', startStroke);
canvas.addEventListener('pointermove', extendStroke);
// High-frequency updates for supported devices (e.g., pens)
canvas.addEventListener('pointerrawupdate', extendStroke);
canvas.addEventListener('pointerup', endStroke);
canvas.addEventListener('pointercancel', endStroke);
canvas.addEventListener('pointerleave', endStroke);

/* Resize handling */
window.addEventListener('resize', () => {
  setCanvasSize();
});

/* Initial setup */
setCanvasSize();
updateButtonsState();

/* Controls state */
function updateButtonsState() {
  undoBtn.disabled = history.length === 0;
  redoBtn.disabled = redoStack.length === 0;
  clearBtn.disabled = history.length === 0;
}

/* SVG Export */
function strokesToSVG(strokes, width, height) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  const pathForStroke = (stroke) => {
    if (!stroke.points.length) return '';
    const pts = stroke.points;
    const d = [];
    let prev = null;

    for (let i = 0; i < pts.length; i++) {
      const curr = pts[i];
      const sCurr = smoothedPoint(prev, curr);
      if (i === 0) {
        d.push(`M ${sCurr.x.toFixed(2)} ${sCurr.y.toFixed(2)}`);
      } else {
        const cx = ((prev.x + sCurr.x) / 2).toFixed(2);
        const cy = ((prev.y + sCurr.y) / 2).toFixed(2);
        d.push(`Q ${prev.x.toFixed(2)} ${prev.y.toFixed(2)} ${cx} ${cy}`);
        d.push(`Q ${cx} ${cy} ${sCurr.x.toFixed(2)} ${sCurr.y.toFixed(2)}`);
      }
      prev = sCurr;
    }

    // approximate pressure width by average
    const avgP = pts.reduce((a, p) => a + (p.p || 0.5), 0) / pts.length || 0.5;
    const widthPx = Math.max(0.5, stroke.size * (0.3 + 0.7 * avgP));

    if (stroke.tool === 'eraser') {
      // Eraser via mask: represent as white stroke with 'destination-out'-like effect is not directly in plain SVG.
      // Instead, we emulate by using 'mix-blend-mode: destination-out' which is not standard in all renderers.
      // For portability, export eraser as transparent stroke on a mask group. Simplify: skip eraser strokes in SVG.
      // Alternatively draw eraser as white path with stroke-opacity to visually indicate. We'll skip for true transparency.
      return ''; // skipping eraser strokes ensures they don't add ink in exported SVG
    }

    return `<path d="${esc(d.join(' '))}" fill="none" stroke="${esc(stroke.color)}" stroke-width="${widthPx.toFixed(2)}" stroke-linecap="round" stroke-linejoin="round" />`;
  };

  const paths = strokes.map(pathForStroke).filter(Boolean).join('\n  ');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs></defs>
  ${bg ? `<rect width="100%" height="100%" fill="${esc(bg)}"/>` : ''}
  ${paths}
</svg>`;
}
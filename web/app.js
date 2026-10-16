const $ = (id) => document.getElementById(id),
  canvas = $("canvas"),
  overlay = $("overlay"),
  ctx = canvas.getContext("2d"),
  oc = overlay.getContext("2d");
const MAX_PIXELS = 48000000,
  MAX_BYTES = 48 * 1024 * 1024,
  BLENDS = [
    "source-over",
    "multiply",
    "screen",
    "overlay",
    "darken",
    "lighten",
  ];
let width = 1200,
  height = 800,
  layers = [],
  active = 0,
  tool = "brush",
  zoom = 1,
  pan = { x: 0, y: 0 },
  gesture = null,
  selection = null,
  undo = [],
  redo = [],
  busy = false,
  dirty = false,
  autosaveTimer = null,
  db = null,
  space = false,
  revision = 0;
const status = (message) => ($("status").textContent = message);
const makeCanvas = (w = width, h = height) => {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
};
function layer(name = "layer", c = makeCanvas()) {
  return { name, opacity: 1, blend: "source-over", visible: true, canvas: c };
}
function current() {
  return layers[active];
}
function render() {
  ctx.clearRect(0, 0, width, height);
  for (const l of layers) {
    if (!l.visible) continue;
    ctx.globalAlpha = l.opacity;
    ctx.globalCompositeOperation = l.blend;
    ctx.drawImage(l.canvas, 0, 0);
  }
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = "source-over";
  renderOverlay();
}
function renderOverlay() {
  oc.clearRect(0, 0, width, height);
  if ($("grid").checked) {
    oc.save();
    oc.strokeStyle = "#77777755";
    oc.lineWidth = 1 / zoom;
    const step = zoom >= 4 ? 1 : 32;
    oc.beginPath();
    for (let x = 0; x <= width; x += step) {
      oc.moveTo(x, 0);
      oc.lineTo(x, height);
    }
    for (let y = 0; y <= height; y += step) {
      oc.moveTo(0, y);
      oc.lineTo(width, y);
    }
    oc.stroke();
    oc.restore();
  }
  if ($("mirror").checked) {
    oc.save();
    oc.strokeStyle = "#c39a93bb";
    oc.lineWidth = 1 / zoom;
    oc.setLineDash([4 / zoom, 4 / zoom]);
    oc.beginPath();
    oc.moveTo(width / 2, 0);
    oc.lineTo(width / 2, height);
    oc.stroke();
    oc.restore();
  }
  if (selection) {
    oc.save();
    oc.lineWidth = 1 / zoom;
    oc.strokeStyle = "#181b1e";
    oc.setLineDash([5 / zoom, 5 / zoom]);
    oc.strokeRect(selection.x, selection.y, selection.w, selection.h);
    oc.lineDashOffset = 5 / zoom;
    oc.strokeStyle = "#fff";
    oc.strokeRect(selection.x, selection.y, selection.w, selection.h);
    oc.restore();
  }
}
function transform() {
  $("canvas-wrap").style.transform =
    `translate(${pan.x}px,${pan.y}px) scale(${zoom})`;
  $("zoom").textContent = `${Math.round(zoom * 100)}%`;
  renderOverlay();
}
function fit() {
  const r = $("viewport").getBoundingClientRect();
  zoom = Math.min((r.width - 40) / width, (r.height - 40) / height, 1);
  pan = { x: (r.width - width * zoom) / 2, y: (r.height - height * zoom) / 2 };
  transform();
}
function setZoom(z, anchor) {
  const r = $("viewport").getBoundingClientRect(),
    p = anchor || { x: r.width / 2, y: r.height / 2 },
    nz = Math.max(0.05, Math.min(16, z));
  pan = {
    x: p.x - ((p.x - pan.x) * nz) / zoom,
    y: p.y - ((p.y - pan.y) * nz) / zoom,
  };
  zoom = nz;
  transform();
}
function resize() {
  canvas.width = overlay.width = width;
  canvas.height = overlay.height = height;
  $("dimensions").textContent = `${width} × ${height}`;
  render();
  fit();
}
function refreshLayers() {
  const list = $("layers");
  list.replaceChildren();
  [...layers.keys()].reverse().forEach((i) => {
    const l = layers[i],
      row = document.createElement("div");
    row.className = `layer${i === active ? " selected" : ""}`;
    const vis = document.createElement("button");
    vis.className = "visibility";
    vis.textContent = l.visible ? "●" : "○";
    vis.setAttribute("aria-label", `${l.visible ? "Hide" : "Show"} ${l.name}`);
    vis.setAttribute("aria-pressed", String(l.visible));
    vis.onclick = () => {
      checkpoint();
      l.visible = !l.visible;
      changed();
    };
    const name = document.createElement("button");
    name.className = "layer-name";
    name.textContent = l.name;
    name.setAttribute("aria-pressed", String(i === active));
    name.onclick = () => {
      active = i;
      refreshLayers();
    };
    name.ondblclick = async () => {
      const value = await ask("name this layer", [
        {
          id: "layer-name-input",
          label: "name",
          value: l.name,
          maxLength: 100,
        },
      ]);
      if (value) {
        checkpoint();
        l.name = value["layer-name-input"].trim() || "layer";
        changed();
      }
    };
    row.append(vis, name);
    list.append(row);
  });
  $("layer-opacity").value = current().opacity * 100;
  $("blend").value = current().blend;
  $("undo").disabled = !undo.length;
  $("redo").disabled = !redo.length;
  $("layer-up").disabled = active === layers.length - 1;
  $("layer-down").disabled = active === 0;
  $("layer-delete").disabled = layers.length === 1;
}
function snapshot() {
  return {
    width,
    height,
    name: $("name").value,
    active,
    layers: layers.map((l) => ({ ...l, canvas: clone(l.canvas) })),
  };
}
function clone(c) {
  const out = makeCanvas(c.width, c.height);
  out.getContext("2d").drawImage(c, 0, 0);
  return out;
}
function checkpoint() {
  undo.push(snapshot());
  const max = Math.max(
    1,
    Math.min(30, Math.floor(128000000 / (width * height * layers.length * 4))),
  );
  while (undo.length > max) undo.shift();
  redo = [];
}
function restore(s) {
  width = s.width;
  height = s.height;
  layers = s.layers;
  active = s.active;
  $("name").value = s.name;
  selection = null;
  resize();
  changed();
}
function history(direction) {
  if (busy || gesture) return;
  const from = direction === "undo" ? undo : redo,
    to = direction === "undo" ? redo : undo;
  if (!from.length) return;
  to.push(snapshot());
  restore(from.pop());
  status(direction === "undo" ? "undid last change" : "redid change");
}
function changed() {
  revision++;
  dirty = true;
  render();
  refreshLayers();
  $("save-status").textContent = "saving recovery…";
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(saveRecovery, 1200);
  window.dispatchEvent(
    new CustomEvent("flapart:change", { detail: { revision } }),
  );
}
function allowLayer() {
  if (
    layers.length >= 32 ||
    width * height * (layers.length + 1) > MAX_PIXELS
  ) {
    status("layer limit reached for this canvas size");
    return false;
  }
  return true;
}
function point(e) {
  const r = $("viewport").getBoundingClientRect();
  return {
    x: (e.clientX - r.left - pan.x) / zoom,
    y: (e.clientY - r.top - pan.y) / zoom,
    p:
      e.pointerType === "pen" && $("pressure").checked
        ? Math.max(0.05, e.pressure)
        : 1,
  };
}
function clip(c) {
  if (selection) {
    c.beginPath();
    c.rect(selection.x, selection.y, selection.w, selection.h);
    c.clip();
  }
}
function brushSegment(a, b) {
  const c = gesture.stroke.getContext("2d"),
    size = +$("size").value,
    flow = +$("flow").value / 100,
    kind = $("brush").value,
    hardness =
      kind === "soft"
        ? Math.min(0.98, +$("hardness").value / 100)
        : +$("hardness").value / 100;
  c.save();
  clip(c);
  c.globalCompositeOperation = "source-over";
  c.fillStyle = $("color").value;
  const dist = Math.hypot(b.x - a.x, b.y - a.y),
    spacing = Math.max(0.35, size * (+$("spacing").value / 100));
  function stamp(x, y, pressure) {
    const r = Math.max(0.25, (size * pressure) / 2);
    c.globalAlpha = flow;
    if (kind === "spray") {
      c.fillStyle = $("color").value;
      const count = Math.max(5, Math.round(r * 2));
      for (let j = 0; j < count; j++) {
        const angle = Math.random() * Math.PI * 2,
          radius = Math.sqrt(Math.random()) * r;
        c.fillRect(
          x + Math.cos(angle) * radius,
          y + Math.sin(angle) * radius,
          Math.max(0.7, r / 16),
          Math.max(0.7, r / 16),
        );
      }
      return;
    }
    if (hardness < 1 && kind !== "square") {
      const g = c.createRadialGradient(
        x,
        y,
        Math.max(0, r * hardness),
        x,
        y,
        r,
      );
      g.addColorStop(0, $("color").value);
      g.addColorStop(1, `${$("color").value}00`);
      c.fillStyle = g;
    } else c.fillStyle = $("color").value;
    c.beginPath();
    if (kind === "square") c.rect(x - r, y - r, r * 2, r * 2);
    else c.arc(x, y, r, 0, Math.PI * 2);
    c.fill();
  }
  function both(x, y, p) {
    stamp(x, y, p);
    if ($("mirror").checked && Math.abs(x - width / 2) > 0.5)
      stamp(width - x, y, p);
  }
  if (dist === 0) both(a.x, a.y, a.p);
  else {
    let step = spacing - (gesture.distance || 0);
    for (; step <= dist; step += spacing) {
      const t = step / dist;
      both(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.p + (b.p - a.p) * t);
    }
    gesture.distance = ((gesture.distance || 0) + dist) % spacing;
  }
  c.restore();
  const dest = current().canvas.getContext("2d");
  dest.clearRect(0, 0, width, height);
  dest.drawImage(gesture.original, 0, 0);
  dest.save();
  dest.globalAlpha = +$("opacity").value / 100;
  dest.globalCompositeOperation =
    tool === "eraser" ? "destination-out" : "source-over";
  dest.drawImage(gesture.stroke, 0, 0);
  dest.restore();
}
function rect(a, b) {
  return {
    x: Math.max(0, Math.min(a.x, b.x)),
    y: Math.max(0, Math.min(a.y, b.y)),
    w: Math.min(width, Math.max(a.x, b.x)) - Math.max(0, Math.min(a.x, b.x)),
    h: Math.min(height, Math.max(a.y, b.y)) - Math.max(0, Math.min(a.y, b.y)),
  };
}
function shape(c, a, b) {
  c.save();
  clip(c);
  if (tool === "gradient") {
    const distance = Math.max(0.01, Math.hypot(b.x - a.x, b.y - a.y)),
      g =
        $("gradient-kind").value === "radial"
          ? c.createRadialGradient(a.x, a.y, 0, a.x, a.y, distance)
          : c.createLinearGradient(
              a.x,
              a.y,
              b.x === a.x && b.y === a.y ? b.x + 0.01 : b.x,
              b.y,
            );
    g.addColorStop(0, $("color").value);
    g.addColorStop(1, $("color-secondary").value);
    c.globalAlpha = +$("opacity").value / 100;
    c.fillStyle = g;
    c.fillRect(0, 0, width, height);
    c.restore();
    return;
  }
  c.strokeStyle = c.fillStyle = $("color").value;
  c.lineWidth = +$("size").value;
  c.globalAlpha = +$("opacity").value / 100;
  c.lineCap = "round";
  c.beginPath();
  if (tool === "line") {
    c.moveTo(a.x, a.y);
    c.lineTo(b.x, b.y);
  } else if (tool === "rectangle") c.rect(a.x, a.y, b.x - a.x, b.y - a.y);
  else
    c.ellipse(
      (a.x + b.x) / 2,
      (a.y + b.y) / 2,
      Math.abs(b.x - a.x) / 2,
      Math.abs(b.y - a.y) / 2,
      0,
      0,
      Math.PI * 2,
    );
  if ($("shape-fill").checked && tool !== "line") c.fill();
  else c.stroke();
  c.restore();
}
function fill(p) {
  const x = Math.floor(p.x),
    y = Math.floor(p.y);
  if (x < 0 || y < 0 || x >= width || y >= height) return;
  const c = current().canvas.getContext("2d"),
    im = c.getImageData(0, 0, width, height),
    data = im.data,
    start = (y * width + x) * 4,
    target = [...data.slice(start, start + 4)],
    hex = $("color").value,
    paint = [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16),
      Math.round(+$("opacity").value * 2.55),
    ],
    tol = +$("tolerance").value * 2.55,
    seen = new Uint8Array(width * height),
    stack = [y * width + x];
  const matches = (px, py) => {
    if (
      px < 0 ||
      py < 0 ||
      px >= width ||
      py >= height ||
      seen[py * width + px]
    )
      return false;
    if (
      selection &&
      (px < selection.x ||
        py < selection.y ||
        px >= selection.x + selection.w ||
        py >= selection.y + selection.h)
    )
      return false;
    const o = (py * width + px) * 4;
    return target.every((v, j) => Math.abs(v - data[o + j]) <= tol);
  };
  while (stack.length) {
    const n = stack.pop(),
      py = Math.floor(n / width);
    let px = n % width;
    if (!matches(px, py)) continue;
    while (matches(px - 1, py)) px--;
    let above = false,
      below = false;
    while (matches(px, py)) {
      const o = (py * width + px) * 4;
      seen[py * width + px] = 1;
      const pa = paint[3] / 255,
        oldAlpha = data[o + 3] / 255,
        outAlpha = pa + oldAlpha * (1 - pa);
      for (let k = 0; k < 3; k++)
        data[o + k] = outAlpha
          ? (paint[k] * pa + data[o + k] * oldAlpha * (1 - pa)) / outAlpha
          : 0;
      data[o + 3] = outAlpha * 255;
      const a = matches(px, py - 1),
        b = matches(px, py + 1);
      if (a && !above) stack.push((py - 1) * width + px);
      if (b && !below) stack.push((py + 1) * width + px);
      above = a;
      below = b;
      px++;
    }
  }
  c.putImageData(im, 0, 0);
}
function setTool(name) {
  if (gesture || busy) return;
  tool = name;
  document.querySelectorAll("[data-tool]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tool === tool);
    b.setAttribute("aria-pressed", String(b.dataset.tool === tool));
  });
  $("viewport").style.cursor = tool === "pan" ? "grab" : "crosshair";
  status(`${tool} selected`);
}
for (const [name, key] of [
  ["brush", "B"],
  ["eraser", "E"],
  ["fill", "F"],
  ["picker", "I"],
  ["line", "L"],
  ["rectangle", "R"],
  ["ellipse", "O"],
  ["gradient", "G"],
  ["text", "T"],
  ["select", "S"],
  ["move", "V"],
  ["pan", "H"],
]) {
  const b = document.createElement("button");
  b.textContent = name;
  b.dataset.tool = name;
  b.title = `${name} (${key})`;
  b.onclick = () => setTool(name);
  $("tools").append(b);
}
for (const color of [
  "#181b1e",
  "#efe9dc",
  "#c39a93",
  "#d7c8ab",
  "#a6a496",
  "#84968c",
  "#748c9b",
  "#99849b",
  "#bf8a60",
  "#d4b85c",
  "#7b8386",
  "#ffffff",
]) {
  const b = document.createElement("button");
  b.style.backgroundColor = color;
  b.title = color;
  b.setAttribute("aria-label", `Use color ${color}`);
  b.onclick = () => {
    $("color").value = color;
  };
  $("swatches").append(b);
}
$("viewport").addEventListener("pointerdown", (e) => {
  if (busy || gesture || e.button > 1) return;
  e.preventDefault();
  $("viewport").focus();
  $("viewport").setPointerCapture(e.pointerId);
  const p = point(e);
  if (space || tool === "pan" || e.button === 1) {
    gesture = {
      mode: "pan",
      id: e.pointerId,
      client: { x: e.clientX, y: e.clientY },
      pan: { ...pan },
    };
    return;
  }
  if (p.x < 0 || p.y < 0 || p.x >= width || p.y >= height) return;
  if (tool === "picker") {
    const d = ctx.getImageData(Math.floor(p.x), Math.floor(p.y), 1, 1).data;
    $("color").value =
      "#" +
      [...d.slice(0, 3)].map((v) => v.toString(16).padStart(2, "0")).join("");
    status("color picked from visible painting");
    return;
  }
  if (!current().visible) {
    status("show this layer before drawing");
    return;
  }
  if (tool === "select") {
    gesture = {
      mode: "select",
      start: p,
      id: e.pointerId,
      previousSelection: selection,
    };
    selection = null;
    return;
  }
  const previousUndo = undo.slice(),
    previousRedo = redo.slice(),
    previousDirty = dirty;
  checkpoint();
  if (tool === "fill") {
    fill(p);
    changed();
    return;
  }
  if (tool === "text") {
    const text = $("text").value || "hello, flaptown";
    const c = current().canvas.getContext("2d");
    c.save();
    clip(c);
    c.font = `${Math.max(8, Math.min(500, +$("text-size").value || 48))}px "Syne Mono"`;
    c.fillStyle = $("color").value;
    c.globalAlpha = +$("opacity").value / 100;
    c.fillText(text, p.x, p.y);
    c.restore();
    changed();
    return;
  }
  gesture = {
    mode: tool,
    start: p,
    last: p,
    id: e.pointerId,
    previousUndo,
    previousRedo,
    previousDirty,
  };
  if (tool === "brush" || tool === "eraser") {
    gesture.original = clone(current().canvas);
    gesture.stroke = makeCanvas();
    gesture.distance = 0;
    brushSegment(p, p);
    render();
  }
  if (tool === "move") {
    gesture.original = clone(current().canvas);
    gesture.selection = selection ? { ...selection } : null;
    gesture.piece = makeCanvas();
    const gc = gesture.piece.getContext("2d");
    if (selection) {
      gc.drawImage(
        current().canvas,
        selection.x,
        selection.y,
        selection.w,
        selection.h,
        selection.x,
        selection.y,
        selection.w,
        selection.h,
      );
    } else gc.drawImage(current().canvas, 0, 0);
  }
});
$("viewport").addEventListener("pointermove", (e) => {
  if (!gesture || gesture.id !== e.pointerId) return;
  const p = point(e);
  if (gesture.mode === "pan") {
    pan = {
      x: gesture.pan.x + e.clientX - gesture.client.x,
      y: gesture.pan.y + e.clientY - gesture.client.y,
    };
    transform();
    return;
  }
  if (gesture.mode === "brush" || gesture.mode === "eraser") {
    const events = e.getCoalescedEvents?.() || [e];
    for (const event of events) {
      const q = point(event);
      brushSegment(gesture.last, q);
      gesture.last = q;
    }
    render();
  } else if (gesture.mode === "select") {
    selection = rect(gesture.start, p);
    renderOverlay();
  } else if (gesture.mode === "move") {
    const c = current().canvas.getContext("2d"),
      s = gesture.selection,
      dx = Math.round(p.x - gesture.start.x),
      dy = Math.round(p.y - gesture.start.y);
    c.clearRect(0, 0, width, height);
    c.drawImage(gesture.original, 0, 0);
    if (s) c.clearRect(s.x, s.y, s.w, s.h);
    else c.clearRect(0, 0, width, height);
    c.drawImage(gesture.piece, dx, dy);
    if (s) selection = { ...s, x: s.x + dx, y: s.y + dy };
    render();
  } else {
    renderOverlay();
    shape(oc, gesture.start, p);
  }
});
function finish(e, cancel = false) {
  if (!gesture || gesture.id !== e.pointerId) return;
  const g = gesture;
  gesture = null;
  if (g.mode === "pan") return;
  if (g.mode === "select") {
    if (cancel) selection = g.previousSelection;
    if (selection && (selection.w < 1 || selection.h < 1)) selection = null;
    renderOverlay();
    return;
  }
  if (cancel) {
    const original = undo.at(-1);
    undo = g.previousUndo;
    redo = g.previousRedo;
    if (original) restore(original);
    dirty = g.previousDirty;
    status("interrupted stroke restored; previous history kept");
    return;
  }
  if (["line", "rectangle", "ellipse", "gradient"].includes(g.mode))
    shape(current().canvas.getContext("2d"), g.start, point(e));
  changed();
}
$("viewport").addEventListener("pointerup", (e) => finish(e));
$("viewport").addEventListener("pointercancel", (e) => finish(e, true));
$("viewport").addEventListener("lostpointercapture", (e) => finish(e, true));
$("viewport").addEventListener(
  "wheel",
  (e) => {
    e.preventDefault();
    const r = $("viewport").getBoundingClientRect();
    if (e.ctrlKey || e.metaKey)
      setZoom(zoom * Math.exp(-e.deltaY * 0.002), {
        x: e.clientX - r.left,
        y: e.clientY - r.top,
      });
    else {
      pan.x -= e.deltaX;
      pan.y -= e.deltaY;
      transform();
    }
  },
  { passive: false },
);
$("undo").onclick = () => history("undo");
$("redo").onclick = () => history("redo");
$("fit").onclick = fit;
$("actual").onclick = () => setZoom(1);
$("zoom-in").onclick = () => setZoom(zoom * 1.25);
$("zoom-out").onclick = () => setZoom(zoom / 1.25);
$("size").oninput = () => ($("size-value").textContent = $("size").value);
$("opacity").oninput = () =>
  ($("opacity-value").textContent = `${$("opacity").value}%`);
$("name").onchange = changed;
$("layer-add").onclick = () => {
  if (!allowLayer()) return;
  checkpoint();
  layers.splice(active + 1, 0, layer(`layer ${layers.length + 1}`));
  active++;
  changed();
};
$("layer-duplicate").onclick = () => {
  if (!allowLayer()) return;
  checkpoint();
  const l = current();
  layers.splice(active + 1, 0, {
    ...l,
    name: `${l.name} copy`,
    canvas: clone(l.canvas),
  });
  active++;
  changed();
};
$("layer-delete").onclick = () => {
  if (layers.length === 1) {
    status("keep at least one layer; use clear to empty it");
    return;
  }
  checkpoint();
  layers.splice(active, 1);
  active = Math.min(active, layers.length - 1);
  changed();
};
$("layer-clear").onclick = () => {
  checkpoint();
  current().canvas.getContext("2d").clearRect(0, 0, width, height);
  changed();
};
for (const [id, delta] of [
  ["layer-up", 1],
  ["layer-down", -1],
])
  $(id).onclick = () => {
    const next = active + delta;
    if (next < 0 || next >= layers.length) return;
    checkpoint();
    [layers[active], layers[next]] = [layers[next], layers[active]];
    active = next;
    changed();
  };
$("layer-opacity").onchange = () => {
  checkpoint();
  current().opacity = +$("layer-opacity").value / 100;
  changed();
};
$("blend").onchange = () => {
  checkpoint();
  current().blend = $("blend").value;
  changed();
};
$("select-all").onclick = () => {
  selection = { x: 0, y: 0, w: width, h: height };
  renderOverlay();
};
$("deselect").onclick = () => {
  selection = null;
  renderOverlay();
};
$("delete-selection").onclick = () => {
  if (!selection) return;
  checkpoint();
  current()
    .canvas.getContext("2d")
    .clearRect(selection.x, selection.y, selection.w, selection.h);
  changed();
};
for (const [id, h] of [
  ["flip-h", true],
  ["flip-v", false],
])
  $(id).onclick = () => {
    checkpoint();
    const c = current().canvas.getContext("2d"),
      copy = clone(current().canvas);
    c.clearRect(0, 0, width, height);
    c.save();
    c.translate(h ? width : 0, h ? 0 : height);
    c.scale(h ? -1 : 1, h ? 1 : -1);
    c.drawImage(copy, 0, 0);
    c.restore();
    changed();
  };
$("grid").onchange = renderOverlay;
for (const id of ["hardness", "flow", "spacing"])
  $(id).oninput = () => ($(id + "-value").textContent = $(id).value + "%");
$("mirror").onchange = renderOverlay;
$("preset").onchange = () => {
  const presets = {
    ink: { brush: "round", size: 16, hardness: 100, flow: 100, spacing: 12 },
    pencil: { brush: "round", size: 3, hardness: 70, flow: 35, spacing: 8 },
    soft: { brush: "soft", size: 70, hardness: 0, flow: 18, spacing: 8 },
    spray: { brush: "spray", size: 60, hardness: 0, flow: 35, spacing: 15 },
    block: { brush: "square", size: 32, hardness: 100, flow: 100, spacing: 15 },
  };
  const p = presets[$("preset").value];
  for (const [key, value] of Object.entries(p)) {
    $(key).value = value;
    $(key).oninput?.();
  }
  setTool("brush");
};
$("rotate-layer").onclick = () => {
  checkpoint();
  const c = current().canvas.getContext("2d"),
    copy = clone(current().canvas);
  c.clearRect(0, 0, width, height);
  c.save();
  c.translate(width / 2, height / 2);
  c.rotate(Math.PI / 2);
  c.drawImage(copy, -width / 2, -height / 2);
  c.restore();
  changed();
  status(
    "layer rotated 90°; edges outside the canvas are clipped (undo to restore)",
  );
};
async function resizeDocument(scale) {
  const v = await ask(
    scale ? "resize your image" : "resize your canvas",
    [
      {
        id: "resize-width",
        label: "width in pixels",
        type: "number",
        value: width,
        min: 1,
        max: 4096,
      },
      {
        id: "resize-height",
        label: "height in pixels",
        type: "number",
        value: height,
        min: 1,
        max: 4096,
      },
      ...(scale
        ? [
            {
              id: "resample",
              label: "resampling",
              value: "smooth",
              options: [
                ["smooth", "smooth artwork"],
                ["pixel", "crisp pixel art"],
              ],
            },
          ]
        : []),
    ],
    scale
      ? "Every layer scales to these dimensions. Keep the same width-to-height ratio to preserve proportions. Undo restores the original."
      : "The artwork stays its original size and is centered in the new canvas. Smaller canvases crop the edges; undo restores them. New space is transparent.",
  );
  if (!v) return;
  const w = +v["resize-width"],
    h = +v["resize-height"];
  if (
    !Number.isInteger(w) ||
    !Number.isInteger(h) ||
    w < 1 ||
    h < 1 ||
    w > 4096 ||
    h > 4096 ||
    w * h * layers.length > MAX_PIXELS
  ) {
    status("dimensions exceed canvas or total layer-pixel limits");
    return;
  }
  checkpoint();
  layers = layers.map((l) => {
    const c = makeCanvas(w, h),
      g = c.getContext("2d");
    g.imageSmoothingEnabled = v.resample !== "pixel";
    g.imageSmoothingQuality = "high";
    if (scale) g.drawImage(l.canvas, 0, 0, w, h);
    else
      g.drawImage(
        l.canvas,
        Math.floor((w - width) / 2),
        Math.floor((h - height) / 2),
      );
    return { ...l, canvas: c };
  });
  width = w;
  height = h;
  selection = null;
  resize();
  changed();
  status(
    scale
      ? "image resized; all layers preserved"
      : "canvas resized; all layers preserved",
  );
}
$("resize-image").onclick = () => resizeDocument(true);
$("resize-canvas").onclick = () => resizeDocument(false);
$("crop").onclick = () => {
  if (!selection) {
    status("select a rectangle first, then crop");
    return;
  }
  const x = Math.max(0, Math.floor(selection.x)),
    y = Math.max(0, Math.floor(selection.y)),
    w = Math.min(width, Math.ceil(selection.x + selection.w)) - x,
    h = Math.min(height, Math.ceil(selection.y + selection.h)) - y;
  if (w < 1 || h < 1) {
    status("selection must overlap the canvas");
    return;
  }
  checkpoint();
  layers = layers.map((l) => {
    const c = makeCanvas(w, h);
    c.getContext("2d").drawImage(l.canvas, x, y, w, h, 0, 0, w, h);
    return { ...l, canvas: c };
  });
  width = w;
  height = h;
  selection = null;
  resize();
  changed();
  status("cropped all layers to the selection; undo restores the full canvas");
};
$("filters").onclick = async () => {
  const v = await ask(
    "adjust the active layer",
    [
      {
        id: "filter-kind",
        label: "adjustment",
        value: "brightness",
        options: [
          ["brightness", "brightness"],
          ["contrast", "contrast"],
          ["grayscale", "grayscale"],
          ["invert", "invert"],
          ["saturation", "saturation"],
        ],
      },
      {
        id: "filter-amount",
        label: "amount (−100 to 100; grayscale/invert always full)",
        type: "number",
        min: -100,
        max: 100,
        value: 20,
      },
    ],
    "Applies to the active layer, inside your selection if one exists. Undo restores the original pixels.",
  );
  if (!v) return;
  const amount = +v["filter-amount"];
  if (!Number.isFinite(amount) || amount < -100 || amount > 100) {
    status("choose an amount from −100 to 100");
    return;
  }
  const s = selection || { x: 0, y: 0, w: width, h: height },
    x = Math.max(0, Math.floor(s.x)),
    y = Math.max(0, Math.floor(s.y)),
    w = Math.min(width, Math.ceil(s.x + s.w)) - x,
    h = Math.min(height, Math.ceil(s.y + s.h)) - y;
  if (w < 1 || h < 1) return;
  checkpoint();
  const c = current().canvas.getContext("2d"),
    im = c.getImageData(x, y, w, h),
    d = im.data,
    factor = (259 * (amount * 2.55 + 255)) / (255 * (259 - amount * 2.55));
  for (let i = 0; i < d.length; i += 4) {
    const gray = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
    for (let j = 0; j < 3; j++) {
      if (v["filter-kind"] === "brightness") d[i + j] += amount * 2.55;
      else if (v["filter-kind"] === "contrast")
        d[i + j] = factor * (d[i + j] - 128) + 128;
      else if (v["filter-kind"] === "grayscale") d[i + j] = gray;
      else if (v["filter-kind"] === "invert") d[i + j] = 255 - d[i + j];
      else if (v["filter-kind"] === "saturation")
        d[i + j] = gray + (d[i + j] - gray) * (1 + amount / 100);
    }
  }
  c.putImageData(im, x, y);
  changed();
  status(v["filter-kind"] + " applied to active layer");
};
function ask(title, fields, description) {
  return new Promise((resolve) => {
    if ($("dialog").open) {
      resolve(null);
      return;
    }
    $("dialog-title").textContent = title;
    $("dialog-body").replaceChildren();
    if (description) {
      const p = document.createElement("p");
      p.textContent = description;
      $("dialog-body").append(p);
    }
    for (const f of fields) {
      const label = document.createElement("label");
      label.textContent = f.label;
      let input;
      if (f.options) {
        input = document.createElement("select");
        for (const [value, text] of f.options) {
          const o = document.createElement("option");
          o.value = value;
          o.textContent = text;
          input.append(o);
        }
      } else {
        input = document.createElement("input");
        input.type = f.type || "text";
        if (f.min) input.min = f.min;
        if (f.max) input.max = f.max;
        if (f.maxLength) input.maxLength = f.maxLength;
      }
      input.id = f.id;
      input.value = f.value ?? "";
      label.append(input);
      $("dialog-body").append(label);
    }
    $("dialog").returnValue = "cancel";
    $("dialog").showModal();
    $("dialog").addEventListener(
      "close",
      () =>
        resolve(
          $("dialog").returnValue === "ok"
            ? Object.fromEntries(fields.map((f) => [f.id, $(f.id).value]))
            : null,
        ),
      { once: true },
    );
  });
}
async function newProject() {
  const v = await ask(
    "a fresh canvas",
    [
      {
        id: "new-width",
        label: "width in pixels",
        type: "number",
        value: 1200,
        min: 1,
        max: 4096,
      },
      {
        id: "new-height",
        label: "height in pixels",
        type: "number",
        value: 800,
        min: 1,
        max: 4096,
      },
      {
        id: "background",
        label: "background",
        value: "white",
        options: [
          ["white", "white"],
          ["transparent", "transparent"],
          ["dark", "slate"],
        ],
      },
    ],
    "Download your current project first if you want to keep it. Local recovery will be replaced.",
  );
  if (!v) return;
  const w = +v["new-width"],
    h = +v["new-height"];
  if (
    !Number.isInteger(w) ||
    !Number.isInteger(h) ||
    w < 1 ||
    h < 1 ||
    w > 4096 ||
    h > 4096
  ) {
    status("choose whole dimensions from 1 to 4096");
    return;
  }
  checkpoint();
  width = w;
  height = h;
  layers = [layer("background")];
  if (v.background !== "transparent") {
    const c = layers[0].canvas.getContext("2d");
    c.fillStyle = v.background === "white" ? "#ffffff" : "#1f2327";
    c.fillRect(0, 0, width, height);
  }
  layers.push(layer("drawing"));
  active = 1;
  selection = null;
  $("name").value = "untitled";
  resize();
  changed();
}
async function exportProject() {
  return {
    format: "flapart",
    version: 1,
    name: $("name").value || "untitled",
    width,
    height,
    layers: layers.map((l) => ({
      name: l.name,
      opacity: l.opacity,
      blend: l.blend,
      visible: l.visible,
      data: l.canvas.toDataURL("image/png"),
    })),
  };
}
function pngSize(data) {
  if (
    typeof data !== "string" ||
    !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(data) ||
    data.length > MAX_BYTES
  )
    throw Error("invalid PNG layer");
  const bytes = atob(data.slice(22));
  if (
    bytes.length < 45 ||
    [137, 80, 78, 71, 13, 10, 26, 10].some((v, i) => bytes.charCodeAt(i) !== v)
  )
    throw Error("invalid PNG signature");
  const n = (o) =>
    bytes.charCodeAt(o) * 16777216 +
    (bytes.charCodeAt(o + 1) << 16) +
    (bytes.charCodeAt(o + 2) << 8) +
    bytes.charCodeAt(o + 3);
  if (n(8) !== 13 || bytes.slice(12, 16) !== "IHDR")
    throw Error("invalid PNG header");
  let pos = 8,
    end = false,
    idat = false;
  while (pos + 12 <= bytes.length) {
    const size = n(pos),
      kind = bytes.slice(pos + 4, pos + 8);
    if (size > bytes.length - pos - 12) throw Error("incomplete PNG layer");
    if (kind === "IDAT") idat = true;
    pos += size + 12;
    if (kind === "IEND") {
      if (size !== 0 || pos !== bytes.length) throw Error("invalid PNG ending");
      end = true;
      break;
    }
  }
  if (!end || !idat) throw Error("incomplete PNG layer");
  return [n(16), n(20)];
}
async function decode(data) {
  const img = new Image();
  img.src = data;
  await img.decode();
  return img;
}
async function loadProject(p, { record = true } = {}) {
  if (busy || gesture) throw Error("finish the current operation first");
  if (
    !p ||
    p.format !== "flapart" ||
    p.version !== 1 ||
    !Number.isInteger(p.width) ||
    !Number.isInteger(p.height) ||
    p.width < 1 ||
    p.height < 1 ||
    p.width > 4096 ||
    p.height > 4096 ||
    !Array.isArray(p.layers) ||
    !p.layers.length ||
    p.layers.length > 32 ||
    p.width * p.height * p.layers.length > MAX_PIXELS
  )
    throw Error("unsupported project or canvas limits exceeded");
  if (
    typeof p.name !== "string" ||
    p.name.length > 100 ||
    JSON.stringify(p).length > MAX_BYTES
  )
    throw Error("project is too large or has an invalid name");
  for (const l of p.layers) {
    if (
      !l ||
      typeof l.name !== "string" ||
      l.name.length > 100 ||
      typeof l.visible !== "boolean" ||
      typeof l.opacity !== "number" ||
      !Number.isFinite(l.opacity) ||
      l.opacity < 0 ||
      l.opacity > 1 ||
      !BLENDS.includes(l.blend)
    )
      throw Error("invalid layer settings");
    const [w, h] = pngSize(l.data);
    if (w !== p.width || h !== p.height)
      throw Error("layer dimensions do not match project");
  }
  busy = true;
  document.querySelector("main").inert = true;
  try {
    const decoded = [];
    for (const l of p.layers) {
      const img = await decode(l.data);
      const c = makeCanvas(p.width, p.height);
      c.getContext("2d").drawImage(img, 0, 0);
      decoded.push({ ...l, canvas: c });
      delete decoded.at(-1).data;
    }
    if (record) checkpoint();
    width = p.width;
    height = p.height;
    layers = decoded;
    active = layers.length - 1;
    selection = null;
    $("name").value = p.name;
    resize();
    changed();
    status("project opened with all layers");
  } finally {
    busy = false;
    document.querySelector("main").inert = false;
  }
}
function download(blob, name) {
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
function filename() {
  return ($("name").value || "untitled")
    .replace(/[^\p{L}\p{N} _.-]/gu, "_")
    .slice(0, 100);
}
async function saveProject() {
  const p = await exportProject();
  download(
    new Blob([JSON.stringify(p)], { type: "application/json" }),
    `${filename()}.flapart`,
  );
  dirty = false;
  status("project downloaded; layers are included");
}
async function exportImage() {
  const v = await ask("take your creation with you", [
    {
      id: "export-format",
      label: "format",
      value: "png",
      options: [
        ["png", "PNG · lossless + transparency"],
        ["jpeg", "JPEG · smaller, white background"],
        ["webp", "WebP · compact + transparency"],
      ],
    },
    {
      id: "export-quality",
      label: "JPEG / WebP quality (1–100)",
      type: "number",
      min: 1,
      max: 100,
      value: 92,
    },
  ]);
  if (!v) return;
  const type = v["export-format"],
    c = makeCanvas();
  const out = c.getContext("2d");
  if (type === "jpeg") {
    out.fillStyle = "#fff";
    out.fillRect(0, 0, width, height);
  }
  out.drawImage(canvas, 0, 0);
  c.toBlob(
    (b) => {
      if (!b) {
        status("export failed; try PNG");
        return;
      }
      download(b, `${filename()}.${type === "jpeg" ? "jpg" : type}`);
      status("image exported");
    },
    `image/${type}`,
    Math.max(0.01, Math.min(1, +v["export-quality"] / 100 || 0.92)),
  );
}
$("new").onclick = newProject;
$("save").onclick = saveProject;
$("export").onclick = exportImage;
$("open").onclick = async () => {
  if (dirty) {
    const yes = await ask(
      "open another project?",
      [],
      "Your current artwork will be replaced. Download a project first to keep a durable copy. You can also undo immediately after opening to return to this canvas.",
    );
    if (!yes) return;
  }
  $("project-file").click();
};
let imageImportMode = "layer";
function chooseImage({ mode = "layer" } = {}) {
  if (!["layer", "new"].includes(mode)) throw Error("unsupported image import mode");
  if (busy || gesture) { status("finish the current operation first"); return false; }
  imageImportMode = mode;
  $("image-file").click();
  return true;
}
$("import").onclick = () => chooseImage();
$("project-file").onchange = async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  try {
    if (f.size > MAX_BYTES) throw Error("project exceeds 48 MB");
    await loadProject(JSON.parse(await f.text()));
  } catch (err) {
    status(`could not open project: ${err.message}`);
  }
};
async function imageDimensions(file) {
  const b = new Uint8Array(await file.slice(0, 262144).arrayBuffer()),
    v = new DataView(b.buffer);
  if (b.length < 16) throw Error("image file is incomplete");
  const str = (o, n) => String.fromCharCode(...b.slice(o, o + n));
  if (b[0] === 137 && str(1, 3) === "PNG" && b.length >= 24)
    return [v.getUint32(16), v.getUint32(20)];
  if (str(0, 3) === "GIF") return [v.getUint16(6, true), v.getUint16(8, true)];
  if (str(0, 4) === "RIFF" && str(8, 4) === "WEBP") {
    const t = str(12, 4),
      u24 = (o) => b[o] + b[o + 1] * 256 + b[o + 2] * 65536;
    if (t === "VP8X" && b.length >= 30) return [u24(24) + 1, u24(27) + 1];
    if (t === "VP8 " && b.length >= 30)
      return [v.getUint16(26, true) & 16383, v.getUint16(28, true) & 16383];
    if (t === "VP8L" && b.length >= 25) {
      const n = v.getUint32(21, true);
      return [(n & 16383) + 1, ((n >>> 14) & 16383) + 1];
    }
  }
  if (b[0] === 255 && b[1] === 216) {
    let o = 2;
    while (o + 9 < b.length) {
      if (b[o] !== 255) break;
      const marker = b[o + 1];
      if (marker === 255) {
        o++;
        continue;
      }
      if (
        [
          192, 193, 194, 195, 197, 198, 199, 201, 202, 203, 205, 206, 207,
        ].includes(marker)
      )
        return [v.getUint16(o + 7), v.getUint16(o + 5)];
      const len = v.getUint16(o + 2);
      if (len < 2) break;
      o += 2 + len;
    }
  }
  throw Error(
    "image dimensions could not be read safely; export it as PNG first",
  );
}
function imageImportResult(state, type = "", mode = "layer") {
  window.dispatchEvent(new CustomEvent("flapart:image-import", { detail: { state, type, mode } }));
}
$("image-file").addEventListener("cancel", () => {
  const mode = imageImportMode;
  imageImportMode = "layer";
  imageImportResult("cancel", "", mode);
});
$("image-file").onchange = async (e) => {
  const f = e.target.files[0], mode = imageImportMode;
  imageImportMode = "layer";
  e.target.value = "";
  if (!f) { imageImportResult("cancel", "", mode); return; }
  if (busy || gesture || (mode === "layer" && !allowLayer())) { imageImportResult("error", f.type, mode); return; }
  if (
    f.size > 32 * 1024 * 1024 ||
    !["image/png", "image/jpeg", "image/webp", "image/gif"].includes(f.type)
  ) {
    status("choose a PNG, JPEG, WebP or GIF under 32 MB");
    imageImportResult("error", f.type, mode);
    return;
  }
  busy = true;
  document.querySelector("main").inert = true;
  let bitmap, imported = false;
  try {
    const [iw, ih] = await imageDimensions(f);
    if (mode === "new" && (iw > 4096 || ih > 4096 || iw * ih > MAX_PIXELS))
      throw Error("PNG is too large to open at its original size here. Resize it in Flapart Studio and export a smaller PNG (up to 4096 pixels per side)");
    if (!iw || !ih || iw > 16384 || ih > 16384 || iw * ih > 64000000)
      throw Error(
        "source image exceeds 64 million pixels or 16384 pixels per side",
      );
    const ratio = mode === "new" ? 1 : Math.min(width / iw, height / ih, 1),
      w = Math.max(1, Math.round(iw * ratio)),
      h = Math.max(1, Math.round(ih * ratio));
    bitmap = await createImageBitmap(f, {
      resizeWidth: w,
      resizeHeight: h,
      resizeQuality: "high",
    });
    // Decode and draw fully before touching the current drawing or its history.
    const c = makeCanvas(mode === "new" ? w : width, mode === "new" ? h : height);
    c.getContext("2d").drawImage(bitmap, mode === "new" ? 0 : (width - w) / 2, mode === "new" ? 0 : (height - h) / 2, w, h);
    checkpoint();
    if (mode === "new") {
      width = w;
      height = h;
      layers = [layer(f.name.slice(0, 100), c)];
      active = 0;
      selection = null;
      $("name").value = f.name.replace(/\.[^.]+$/, "").slice(0, 100) || "untitled";
      resize();
    } else {
      layers.push(layer(f.name.slice(0, 100), c));
      active = layers.length - 1;
    }
    changed();
    status(mode === "new" ? "PNG opened as its own drawing; undo restores your previous canvas" : "image added as a layer; use move to position it");
    imported = true;
  } catch (err) {
    status(`image could not be opened: ${err.message}`);
  } finally {
    bitmap?.close();
    busy = false;
    document.querySelector("main").inert = false;
    imageImportResult(imported ? "success" : "error", f.type, mode);
  }
};
async function initRecovery() {
  try {
    db = await new Promise((resolve, reject) => {
      const req = indexedDB.open("flapart", 1);
      req.onupgradeneeded = () => req.result.createObjectStore("recovery");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    const old = await new Promise((resolve, reject) => {
      const r = db
        .transaction("recovery")
        .objectStore("recovery")
        .get("latest");
      r.onsuccess = () => resolve(r.result);
      r.onerror = () => reject(r.error);
    });
    if (old) {
      const yes = await ask(
        "pick up where you left off?",
        [],
        `A local recovery copy of “${old.name}” is available. Continue to restore it, or cancel to start fresh.`,
      );
      if (yes) await loadProject(old, { record: false });
    }
    $("save-status").textContent = "local recovery ready";
  } catch {
    $("save-status").textContent =
      "local recovery unavailable · download a project";
  }
}
async function saveRecovery() {
  if (!db) return;
  const thisRevision = revision;
  try {
    const p = await exportProject();
    await new Promise((resolve, reject) => {
      const tx = db.transaction("recovery", "readwrite");
      tx.objectStore("recovery").put(p, "latest");
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
    if (thisRevision === revision)
      $("save-status").textContent = "saved in this browser";
  } catch {
    $("save-status").textContent = "recovery full · download your project";
  }
}
$("help").onclick = () =>
  ask(
    "your little painting room",
    [],
    `Brush B · Eraser E · Fill F · Pick color I · Line L · Rectangle R · Ellipse O · Gradient G · Text T · Select S · Move V · Pan H. Space + drag pans. Ctrl/Cmd + wheel zooms. Ctrl/Cmd Z undoes; Shift Z redoes. [ and ] change brush size. Escape clears a selection. Text comes from tool settings. Double-click a layer name to rename it. Select an area, then use move to move only that area. PNG preserves transparency; JPEG uses white. Projects retain layers and can be opened here again. Local recovery is one copy in this browser, not a backup. Flapart is an original painting app; it does not read Krita .kra files.`,
  );
document.addEventListener("keydown", (e) => {
  if (busy || gesture) {
    if (
      (e.ctrlKey || e.metaKey) &&
      ["s", "z", "y", "a"].includes(e.key.toLowerCase())
    )
      e.preventDefault();
    return;
  }
  if (
    document.querySelector("dialog[open]") ||
    ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
  )
    return;
  const key = e.key.toLowerCase(),
    mod = e.ctrlKey || e.metaKey;
  if (mod && key === "z") {
    e.preventDefault();
    history(e.shiftKey ? "redo" : "undo");
    return;
  }
  if (mod && key === "y") {
    e.preventDefault();
    history("redo");
    return;
  }
  if (mod && key === "s") {
    e.preventDefault();
    saveProject();
    return;
  }
  if (mod && key === "a") {
    e.preventDefault();
    $("select-all").click();
    return;
  }
  if (mod) return;
  if (e.code === "Space") {
    e.preventDefault();
    space = true;
    return;
  }
  if (key === "escape") {
    $("deselect").click();
    return;
  }
  if (key === "delete" || key === "backspace") {
    e.preventDefault();
    $("delete-selection").click();
    return;
  }
  if (key === "[" || key === "]") {
    $("size").value = Math.max(
      1,
      Math.min(250, +$("size").value + (key === "]" ? 2 : -2)),
    );
    $("size").oninput();
    return;
  }
  const map = {
    b: "brush",
    e: "eraser",
    f: "fill",
    i: "picker",
    l: "line",
    r: "rectangle",
    o: "ellipse",
    g: "gradient",
    t: "text",
    s: "select",
    v: "move",
    h: "pan",
  };
  if (map[key]) setTool(map[key]);
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space") space = false;
});
window.addEventListener("blur", () => {
  space = false;
});
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
window.flapart = {
  chooseImage,
  exportProject,
  loadProject,
  exportPreview: async () => canvas.toDataURL("image/png"),
  getName: () => $("name").value,
  setStatus: status,
  ask,
  getRevision: () => revision,
  limits: {
    maxDimension: 4096,
    maxLayers: 32,
    maxPixels: MAX_PIXELS,
    maxBytes: MAX_BYTES,
  },
};
for (const id of ["account-save", "account-post"])
  $(id).onclick = () =>
    window.dispatchEvent(
      new CustomEvent(
        id === "account-save"
          ? "flapart:save-profile"
          : "flapart:post-townhall",
      ),
    );
layers = [layer("background"), layer("drawing")];
layers[0].canvas.getContext("2d").fillStyle = "#ffffff";
layers[0].canvas.getContext("2d").fillRect(0, 0, width, height);
active = 1;
resize();
refreshLayers();
setTool("brush");
await document.fonts.ready;
window.dispatchEvent(new CustomEvent("flapart:ready"));
await initRecovery();
new ResizeObserver(() => {
  if (!gesture) fit();
}).observe($("viewport"));

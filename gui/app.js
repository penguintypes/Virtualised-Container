const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character],
  );
const encode = encodeURIComponent;
let activeView = sessionStorage.getItem("activeView") || "home";
let refreshTimer = null;
let inspectedVolume = null;

let desktopBridgeChecks = 0;

function detectDesktopBridge() {
  if (window.pywebview?.api) {
    document.documentElement.classList.add("pywebview-desktop");
    return;
  }

  if (desktopBridgeChecks < 20) {
    desktopBridgeChecks += 1;
    window.setTimeout(detectDesktopBridge, 50);
  }
}

document.addEventListener("pywebviewready", detectDesktopBridge);
detectDesktopBridge();

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-window-action]");
  if (!button || !window.pywebview?.api) return;

  const action = button.dataset.windowAction;
  if (action === "minimize") {
    await window.pywebview.api.minimize();
  } else if (action === "maximize") {
    const maximized = await window.pywebview.api.toggle_maximize();
    button.setAttribute("aria-label", maximized ? "Restore" : "Maximize");
  } else if (action === "close") {
    await window.pywebview.api.close();
  }
});

document.addEventListener("dblclick", async (event) => {
  if (
    event.target.closest(".pywebview-drag-region") &&
    !event.target.closest("[data-window-action]") &&
    window.pywebview?.api
  ) {
    await window.pywebview.api.toggle_maximize();
  }
});

document
  .querySelector(".desktop-window-controls")
  ?.addEventListener("mousedown", (event) => {
    event.stopPropagation();
  });

let resizeState = null;
let pendingBounds = null;
let resizeRequestRunning = false;

async function applyPendingResize() {
  if (resizeRequestRunning || !pendingBounds || !window.pywebview?.api) return;

  resizeRequestRunning = true;
  const bounds = pendingBounds;
  pendingBounds = null;

  try {
    await window.pywebview.api.resize_window(
      bounds.x,
      bounds.y,
      bounds.width,
      bounds.height,
    );
  } finally {
    resizeRequestRunning = false;
    if (pendingBounds) window.requestAnimationFrame(applyPendingResize);
  }
}

document.querySelectorAll("[data-resize]").forEach((handle) => {
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !window.pywebview?.api) return;

    event.preventDefault();
    event.stopPropagation();
    handle.setPointerCapture(event.pointerId);

    resizeState = {
      direction: handle.dataset.resize,
      pointerId: event.pointerId,
      startX: event.screenX,
      startY: event.screenY,
      x: window.screenX,
      y: window.screenY,
      width: window.outerWidth,
      height: window.outerHeight,
    };
  });
});

document.addEventListener("pointermove", (event) => {
  if (!resizeState || event.pointerId !== resizeState.pointerId) return;

  const deltaX = event.screenX - resizeState.startX;
  const deltaY = event.screenY - resizeState.startY;
  const direction = resizeState.direction;
  let x = resizeState.x;
  let y = resizeState.y;
  let width = resizeState.width;
  let height = resizeState.height;

  if (direction.includes("right")) width = Math.max(900, width + deltaX);
  if (direction.includes("bottom")) height = Math.max(600, height + deltaY);

  if (direction.includes("left")) {
    width = Math.max(900, resizeState.width - deltaX);
    x = resizeState.x + resizeState.width - width;
  }

  if (direction.includes("top")) {
    height = Math.max(600, resizeState.height - deltaY);
    y = resizeState.y + resizeState.height - height;
  }

  pendingBounds = { x, y, width, height };
  window.requestAnimationFrame(applyPendingResize);
});

document.addEventListener("pointerup", (event) => {
  if (resizeState?.pointerId === event.pointerId) resizeState = null;
});

document.addEventListener("pointercancel", () => {
  resizeState = null;
});


let pendingRequests = 0;
const refreshAfterAction = new Set([
  "compose-start",
  "compose-stop",
  "compose-restart",
  "compose-remove",
  "start",
  "stop",
  "delete",
  "delete-image",
  "delete-inspected-volume",
  "delete-volume",
]);

async function withBusyCursor(operation) {
  pendingRequests += 1;
  document.documentElement.classList.add("is-loading");
  try {
    return await operation();
  } finally {
    pendingRequests -= 1;
    if (pendingRequests === 0) {
      document.documentElement.classList.remove("is-loading");
    }
  }
}

async function api(path, options) {
  return withBusyCursor(async () => {
    const response = await fetch(path, options);
    let data = null;
    try {
      data = await response.json();
    } catch (_) {}
    if (!response.ok)
      throw new Error(data?.detail || data?.error || response.statusText);
    return data;
  });
}

function bytes(value) {
  if (value == null) return "—";
  const units = ["B", "KiB", "MiB", "GiB", "TiB"];
  let number = Number(value);
  let index = 0;
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024;
    index += 1;
  }
  return `${number.toFixed(index ? 1 : 0)} ${units[index]}`;
}

const CPU_PERIOD = 100000;

function cpuLimit(cores) {
  const value = Number(cores);
  if (!Number.isFinite(value) || value < 0.1) {
    throw new Error("CPU cores must be 0.1 or greater");
  }
  return {
    cpu_quota: Math.round(value * CPU_PERIOD),
    cpu_period: CPU_PERIOD,
  };
}

function cpuCores(cpuMax) {
  const [quota, period] = String(cpuMax || "").trim().split(/\s+/);
  if (quota === "max" || !Number(quota) || !Number(period)) return "1";
  return String(Number((Number(quota) / Number(period)).toFixed(2)));
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast${error ? " error" : ""}`;
  element.textContent = message;
  document.body.append(element);
  setTimeout(() => element.remove(), 4000);
}

function renderLoadingSpinner(message) {
  return `<span class="loading-status" role="status"><span class="loader animate" aria-hidden="true"></span><span>${esc(message)}</span></span>`;
}

function setButtonLoading(button, message = "Loading…") {
  const originalContent = button.innerHTML;
  const wasDisabled = button.disabled;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.innerHTML = renderLoadingSpinner(message);
  return () => {
    button.innerHTML = originalContent;
    button.disabled = wasDisabled;
    button.removeAttribute("aria-busy");
  };
}

let detailsRequest = 0;
async function showDetails(name) {
  const request = ++detailsRequest;
  const dialog = $("#details");
  $("#detail-title").textContent = name;
  $("#detail-content").innerHTML = renderLoadingSpinner(
    "Loading container details…",
  );
  $("#detail-content").setAttribute("aria-busy", "true");
  if (!dialog.open) dialog.showModal();
  try {
    await loadDetails(name, request);
  } catch (error) {
    if (request === detailsRequest) {
      $("#detail-content").textContent =
        `Could not load details: ${error.message}`;
    }
  } finally {
    if (request === detailsRequest)
      $("#detail-content").removeAttribute("aria-busy");
  }
}

function status(value) {
  return `<span class="status ${esc(value)}"><i></i>${esc(value)}</span>`;
}

function portLinks(container) {
  if (!container.ports?.length) return "—";
  return container.ports
    .map((mapping) => {
      const [hp, cp] = typeof mapping === "string" ? mapping.split(":") : [mapping.host_port, mapping.container_port];
      const label = `${hp}:${cp}`;
      return `<a target="_blank" rel="noopener" href="http://127.0.0.1:${hp}">${esc(label)} ↗</a>`;
    })
    .join(", ");
}

async function getContainers() {
  return asList(await api("/containers"), "containers");
}

function ratio(value, limit) {
  if (!limit || value == null) return 0;
  return Math.min(100, Math.round((Number(value) / Number(limit)) * 100));
}

function renderResourceProgressBar(label, value, limit, formatter = String) {
  const percent = ratio(value, limit);
  const level = percent >= 90 ? "hot" : percent >= 70 ? "warm" : "";
  const detail =
    value == null
      ? "—"
      : limit
        ? `${formatter(value)} / ${formatter(limit)}`
        : `${formatter(value)} · no limit`;
  return `<div class="resource-progress-bar"><div class="space-between-row"><span>${esc(label)}</span><small>${esc(detail)}</small></div>
    <div role="progressbar" aria-label="${esc(label)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percent}" class="progress-bar ${level === "hot" ? "error" : level === "warm" ? "paused" : ""}"><div class="progress-bar-fill" style="width:${percent}%"></div></div></div>`;
}

function containerCard(container, metrics = null) {
  const name = esc(container.name);
  const running = container.status === "running";
  return `<article class="card container-card">
    <div class="space-between-row"><div><h3>${name}</h3><div class="container-metadata">${status(container.status)} <span class="image-badge">${esc(container.image || "—")}</span></div></div>
      <button data-action="details" data-name="${name}">Details</button></div>
    <dl class="container-configuration">
      ${container.network_address ? `<dt>Address</dt><dd>${esc(container.network_address)}</dd>` : ""}
      <dt>Ports</dt><dd>${portLinks(container)}</dd>
      <dt>Command</dt><dd><code>${esc((container.command || []).join(" ") || "—")}</code></dd>
    </dl>
    <div class="container-progress-bars">${
      running && metrics
        ? renderResourceProgressBar(
            "Memory",
            metrics.memory_used_bytes,
            metrics.memory_limit_bytes,
            bytes,
          ) +
          renderResourceProgressBar(
            "Processes",
            metrics.process_count,
            metrics.process_limit,
          )
        : renderResourceProgressBar("Memory", null, null, bytes) +
          renderResourceProgressBar("Processes", null, null)
    }</div>
    <div class="button-row">
      <button data-action="${running ? "stop" : "start"}" data-name="${name}">${running ? "Stop" : "Start"}</button>
      <button class="danger" data-action="delete" data-name="${name}">Delete</button>
    </div>
  </article>`;
}

async function renderHome() {
  const [containers, images, disk, volumesRaw] = await Promise.all([
    getContainers(),
    api("/images"),
    api("/system/disk").catch(() => null),
    api("/volumes").catch(() => []),
  ]);
  const runningContainers = containers.filter(
    (item) => item.status === "running",
  );
  const metrics = Object.fromEntries(
    runningContainers.map((container) => [container.name, container.metrics]),
  );
  const activeMetrics = Object.values(metrics).filter(Boolean);
  const memoryUsed = activeMetrics.reduce(
    (sum, item) => sum + (item.memory_used_bytes || 0),
    0,
  );
  const processes = activeMetrics.reduce(
    (sum, item) => sum + (item.process_count || 0),
    0,
  );
  const cpu = activeMetrics.reduce(
    (sum, item) => sum + (item.cpu_percent || 0),
    0,
  );
  const running = runningContainers.length;
  $("#title").textContent = "Home";
  $("#actions").innerHTML = `
	  <button class="default" data-action="run">+ Run container</button>
	  <button data-action="compose">Compose</button>
	`;
  $("#content").innerHTML = `<div class="container-summary">
      <article class="card"><span>Running</span><strong>${running}</strong></article>
      <article class="card"><span>Stopped</span><strong>${containers.length - running}</strong></article>
      <article class="card"><span>Images</span><strong>${asList(images, "images").length}</strong><small>${asList(volumesRaw, "volumes").length} volumes</small></article>
      <article class="card"><span>Disk Utilization</span><strong>${disk ? bytes(disk.used_bytes) : "—"}</strong><small>${disk ? `Images ${bytes(disk.image_bytes)} · Volumes ${bytes(disk.volume_bytes)} · Containers ${bytes(disk.container_bytes)}` : "Disk usage unavailable"}</small></article>
    </div>
    <div class="section-title"><h2>Containers</h2><button data-action="refresh">Refresh</button></div>
    <div class="container-grid">${containers.length ? containers.map((container) => containerCard(container, metrics[container.name])).join("") : '<div class="empty-state">No containers yet.</div>'}</div>`;
}

async function renderContainers() {
  const containers = await getContainers();
  const metrics = Object.fromEntries(
    containers.map((container) => [container.name, container.metrics]),
  );
  $("#title").textContent = "Containers";
  $("#actions").innerHTML = `
    <button class="default" data-action="run">+ Run container</button>
    <button data-action="compose">Compose</button>
  `;
  $("#content").innerHTML =
    `<div class="container-grid">${containers.length ? containers.map((container) => containerCard(container, metrics[container.name])).join("") : '<div class="empty-state">No containers yet.</div>'}</div>`;
}

function asList(r, key) {
  return Array.isArray(r) ? r : (r && r[key]) || [];
}

async function renderImages() {
  const images = asList(await api("/images"), "images");
  $("#title").textContent = "Images";
  $("#actions").innerHTML =
    '<button class="default" data-action="pull">Pull image</button>';
  $("#content").innerHTML = images.length
    ? `<div class="card image-table-container"><table>
    <thead><tr><th>Name</th><th>Size</th><th>Created</th><th></th></tr></thead>
    <tbody>${images
      .map(
        (
          image,
        ) => `<tr><td data-label="Name"><b class="image-name">${esc(image.name)}</b></td><td data-label="Size">${image.size ? (image.size / 1048576).toFixed(1) + " MB" : "—"}</td><td data-label="Created">${image.created ? esc(new Date(image.created).toLocaleDateString()) : "—"}</td>
      <td><button class="danger" data-action="delete-image" data-name="${esc(image.name)}">Delete</button></td></tr>`,
      )
      .join("")}</tbody>
    </table></div>`
    : '<div class="empty-state">No images yet.</div>';
}

async function renderVolumes() {
  const volumes = asList(await api("/volumes"), "volumes");
  $("#title").textContent = "Volumes";
  $("#actions").innerHTML =
    '<button class="default" data-action="create-volume">+ Create volume</button>';
  $("#content").innerHTML = volumes.length
    ? `<div class="card image-table-container"><table>
    <thead><tr><th>Name</th><th>Mount source</th><th></th></tr></thead>
    <tbody>${volumes
      .map(
        (volume) => `<tr><td data-label="Name"><b>${esc(volume.name)}</b></td>
      <td data-label="Mount source"><code>${esc(volume.mount_source)}</code></td><td>
      <button data-action="inspect-volume" data-name="${esc(volume.name)}">Inspect</button>
      <button class="danger" data-action="delete-volume" data-name="${esc(volume.name)}">Delete</button>
      </td></tr>`,
      )
      .join("")}</tbody>
    </table></div>`
    : '<div class="empty-state">No volumes yet.</div>';
}

function composeProjectCard(project) {
  const services = project.services
    .map(
      (service) => `
        <li>
          <span>${esc(service.name)}</span>
          <small>${esc(service.container)}</small>
          ${status(service.status)}
        </li>`,
    )
    .join("");
  return `<article class="card compose-project-card">
    <div class="compose-project-heading">
      <div>
        <h2>${esc(project.name)}</h2>
        <p>${project.service_count} service(s) · ${project.running} running</p>
      </div>
      ${status(project.status)}
    </div>
    <ul class="compose-service-list">${services}</ul>
    <div class="compose-project-actions">
      <button data-action="compose-edit" data-name="${esc(project.name)}">Edit YAML</button>
      <button data-action="compose-start" data-name="${esc(project.name)}">Start</button>
      <button data-action="compose-stop" data-name="${esc(project.name)}">Stop</button>
      <button data-action="compose-restart" data-name="${esc(project.name)}">Restart</button>
      <button
        class="danger"
        data-action="compose-remove"
        data-name="${esc(project.name)}"
      >
        Remove
      </button>
    </div>
  </article>`;
}

async function renderComposeProjects() {
  const data = await api("/compose");
  const projects = data.projects || [];
  $("#title").textContent = "Compose";
  $("#actions").innerHTML =
    '<button class="default" data-action="compose-new">+ New project</button>';
  $("#content").innerHTML = projects.length
    ? `<div class="compose-project-grid">${projects.map(composeProjectCard).join("")}</div>`
    : '<div class="empty-state">No saved Compose projects yet.</div>';
  return projects;
}

async function followComposeProject(name, expectedStatus) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    if (activeView !== "compose") return;

    try {
      const projects = await renderComposeProjects();
      const project = projects.find((item) => item.name === name);
      if (!project || project.status === expectedStatus) return;
    } catch (error) {
      console.error("Compose status refresh failed:", error);
      return;
    }
  }
}

let volumeDetailsRequest = 0;

async function inspectVolume(name) {
  const request = ++volumeDetailsRequest;
  inspectedVolume = null;
  const dialog = $("#volume-details");
  const content = $("#volume-detail-content");
  $("#volume-detail-title").textContent = name;
  content.innerHTML = renderLoadingSpinner("Loading volume details…");
  content.setAttribute("aria-busy", "true");
  if (!dialog.open) dialog.showModal();
  try {
    await loadVolumeDetails(name, request);
  } catch (error) {
    if (request === volumeDetailsRequest) {
      content.textContent = `Could not load volume details: ${error.message}`;
    }
  } finally {
    if (request === volumeDetailsRequest) content.removeAttribute("aria-busy");
  }
}

async function loadVolumeDetails(name, request) {
  const [volume, containers] = await Promise.all([
    api(`/volumes/${encode(name)}`),
    getContainers(),
  ]);
  const mounts = containers.flatMap((container) =>
    (container.volumes || [])
      .filter((mount) => mount.name === name)
      .map((mount) => ({
        container: container.name,
        status: container.status,
        target: mount.target,
      })),
  );
  if (request !== volumeDetailsRequest || !$("#volume-details").open) return;
  inspectedVolume = { ...volume, mounts };
  $("#volume-detail-title").textContent = volume.name;
  $("#volume-detail-content").innerHTML = `<div class="detail-grid">
    <div class="card"><h3>Volume</h3><dl>
      <dt>Name</dt><dd>${esc(volume.name)}</dd>
      <dt>Usage</dt><dd>${status(mounts.length ? "in-use" : "unused")}</dd>
      <dt>Attachments</dt><dd>${mounts.length}</dd>
    </dl></div>
    <div class="card"><h3>Storage location</h3>
      <p class="volume-path"><code>${esc(volume.mount_source)}</code></p>
      <button data-action="copy-volume-path">Copy path</button>
    </div>
  </div>
  <div class="card volume-attachments"><h3>Container attachments</h3>
    ${
      mounts.length
        ? `<table><thead><tr><th>Container</th><th>Status</th><th>Target</th></tr></thead>
      <tbody>${mounts.map((mount) => `<tr><td>${esc(mount.container)}</td><td>${status(mount.status)}</td><td><code>${esc(mount.target)}</code></td></tr>`).join("")}</tbody></table>`
        : '<p class="muted-text">This volume is not attached to a container.</p>'
    }
  </div>
  <div class="dialog-actions">
    <button class="danger" data-action="delete-inspected-volume" ${mounts.length ? 'disabled title="Detach the volume before removing it"' : ""}>${mounts.length ? "Volume in use" : "Remove volume"}</button>
  </div>`;
}

const WARN = 60, CRIT = 85; // percent: orange from WARN, red from CRIT
const liveHist = { cpuH: [], cpuC: [], ramH: [], ramC: [] };
const LIVE_TILES = [
  ["cpuH", "CPU · host", "#3a7bd5"],
  ["cpuC", "CPU · containers", "#3a7bd5"],
  ["ramH", "RAM · host", "#2e9e5b"],
  ["ramC", "RAM · containers", "#2e9e5b"],
];
let liveLast = null;

function liveHtml() {
  return `<div class="live-row">${LIVE_TILES.map(([k, title]) => `<div class="card"><div class="space-between-row"><b>${title}</b><span id="live-${k}-val">—</span></div><canvas id="live-${k}"></canvas></div>`).join("")}</div>`;
}

function levelColor(v, base) {
  return v >= CRIT ? "#e5484d" : v >= WARN ? "#f5a524" : base;
}

function drawSpark(id, data, base) {
  const c = document.getElementById(id);
  if (!c) return;
  const w = (c.width = c.clientWidth || 300);
  const h = (c.height = 84);
  const g = c.getContext("2d");
  const padL = 30, padR = 4, padT = 4, padB = 14;
  const pw = w - padL - padR, ph = h - padT - padB;
  const txt = getComputedStyle(document.body).color;
  const yOf = (v) => padT + ph - (Math.min(100, Math.max(0, v)) / 100) * ph;
  g.clearRect(0, 0, w, h);
  g.font = "10px Segoe UI, sans-serif";
  g.fillStyle = txt;
  g.strokeStyle = txt;
  g.lineWidth = 1;
  g.textAlign = "right";
  g.textBaseline = "middle";
  [0, 50, 100].forEach((v) => {
    g.globalAlpha = 0.22;
    g.beginPath();
    g.moveTo(padL, yOf(v) + 0.5);
    g.lineTo(w - padR, yOf(v) + 0.5);
    g.stroke();
    g.globalAlpha = 0.75;
    g.fillText(v + "%", padL - 4, yOf(v));
  });
  g.textBaseline = "top";
  g.textAlign = "left";
  g.fillText("60s", padL, h - padB + 3);
  g.textAlign = "right";
  g.fillText("now", w - padR, h - padB + 3);
  g.globalAlpha = 1;
  if (data.length < 2) return;
  const step = pw / 59;
  const pts = data.map((v, i) => [w - padR - (data.length - 1 - i) * step, yOf(v), v]);
  const last = pts[pts.length - 1];
  g.beginPath();
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
  g.lineTo(last[0], yOf(0));
  g.lineTo(pts[0][0], yOf(0));
  g.closePath();
  g.globalAlpha = 0.16;
  g.fillStyle = levelColor(last[2], base);
  g.fill();
  g.globalAlpha = 1;
  g.lineWidth = 2;
  for (let i = 1; i < pts.length; i++) {
    g.beginPath();
    g.moveTo(pts[i - 1][0], pts[i - 1][1]);
    g.lineTo(pts[i][0], pts[i][1]);
    g.strokeStyle = levelColor(pts[i][2], base);
    g.stroke();
  }
}

function drawLive() {
  LIVE_TILES.forEach(([k, , base]) => drawSpark("live-" + k, liveHist[k], base));
  if (!liveLast) return;
  const d = liveLast;
  const set = (k, text) => {
    const el = document.getElementById("live-" + k + "-val");
    if (el) el.textContent = text;
  };
  set("cpuH", d.host_cpu_percent + "%");
  set("cpuC", d.container_cpu_percent + "%");
  set("ramH", bytes(d.host_memory_used_bytes) + " / " + bytes(d.host_memory_total_bytes));
  set("ramC", bytes(d.container_memory_bytes));
}

async function liveTick() {
  if (document.hidden || activeView !== "home") return;
  try {
    const r = await fetch("/system/live");
    if (!r.ok) return;
    const d = await r.json();
    liveLast = d;
    const total = d.host_memory_total_bytes || 1;
    liveHist.cpuH.push(d.host_cpu_percent || 0);
    liveHist.cpuC.push(d.container_cpu_percent || 0);
    liveHist.ramH.push((d.host_memory_used_bytes / total) * 100);
    liveHist.ramC.push(((d.container_memory_bytes || 0) / total) * 100);
    Object.values(liveHist).forEach((a) => { if (a.length > 60) a.shift(); });
    drawLive();
  } catch (_) {}
}
setInterval(liveTick, 1000);

async function updateHealth() {
  try {
    const h = await api("/health");
    const caps = h.capabilities || {};
    $("#health").innerHTML =
      '<span class="dot on"></span>vContainer: online<br>' +
      [["namespaces", "namespaces"], ["cgroups_v2", "cgroups v2"], ["overlayfs", "overlayfs"], ["network_tools", "network"]]
        .map(([k, l]) => l + (caps[k] ? '<span class="ok" style="font-size: 10px; opacity: 0.5; margin-left: 6px;">✓</span>' : '<span class="bad" style="font-size: 10px; opacity: 0.5; margin-left: 6px;">✗</span>'))
        .join("<br>");
  } catch (_) {
    $("#health").innerHTML = '<span class="dot off"></span>vContainer: offline';
  }
}

async function render() {
  updateHealth();
  clearTimeout(refreshTimer);
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === activeView);
  });
  try {
    if (activeView === "images") await renderImages();
    else if (activeView === "volumes") await renderVolumes();
    else if (activeView === "compose") await renderComposeProjects();
    else if (activeView === "containers") await renderContainers();
    else {
      await renderHome();
      const statsRow = document.querySelector(".container-summary");
      if (statsRow) statsRow.insertAdjacentHTML("afterend", liveHtml());
      else $("#content").insertAdjacentHTML("beforeend", liveHtml());
      drawLive();
    }
    $("#banner").classList.add("is-hidden");
    if (activeView === "home" || activeView === "containers")
      $("#actions").insertAdjacentHTML("beforeend", '<button class="danger" data-action="killall">Kill all containers</button>');
  } catch (error) {
    console.error("Dashboard render failed:", error);
    $("#banner").textContent = `Dashboard error: ${error.message}`;
    $("#banner").classList.remove("is-hidden");
  }
  if (activeView === "home" || activeView === "containers") {
    refreshTimer = setTimeout(render, 5000);
  }
}

async function openRunDialog() {
  const [imageData, volumeData] = await Promise.all([
    api("/images"),
    api("/volumes"),
  ]);
  const images = asList(imageData, "images");
  const volumes = volumeData.volumes || [];
  $("#image").innerHTML = images
    .map(
      (image) =>
        `<option value="${esc(image.name)}">${esc(image.name)}</option>`,
    )
    .join("");
  $("#container-volume").innerHTML =
    '<option value="">No volume</option>' +
    volumes
      .map(
        (volume) =>
          `<option value="${esc(volume.name)}">${esc(volume.name)}</option>`,
      )
      .join("");
  $("#run").showModal();
}

function parseEnvironment(text) {
  const environment = {};
  if (!text.trim()) return environment;
  for (const assignment of text.split(/[\n,]+/)) {
    if (!assignment.trim()) continue;
    const separator = assignment.indexOf("=");
    if (separator < 1) throw new Error("Each environment variable must use KEY=value");
    const key = assignment.slice(0, separator).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      throw new Error(`Invalid environment variable name: ${key}`);
    }
    environment[key] = assignment.slice(
      separator + 1,
    ).trim();
  }
  return environment;
}

async function createContainer(event) {
  event.preventDefault();
  const command = $("#command").value.trim();
  const cpu = $("#cpus").value.trim();
  const port = $("#port").value.trim();
  const volume = $("#container-volume").value;
  const volumeTarget = $("#volume-target").value.trim();
  const payload = { memory: $("#memory").value,
    image: $("#image").value,
    name: $("#name").value,
    environment: parseEnvironment($("#environment").value),
  };
  if (Boolean(volume) !== Boolean(volumeTarget)) {
    throw new Error("Choose a volume and enter its container target path");
  }
  if (volume) {
    if (
      !volumeTarget.startsWith("/") ||
      volumeTarget.split("/").includes("..")
    ) {
      throw new Error(
        "Volume target must be an absolute container path without '..'",
      );
    }
    payload.volumes = [{ name: volume, target: volumeTarget }];
  }
  if (command) payload.command = ["/bin/sh", "-c", command];
  if ($("#memory").value) payload.memory_max = $("#memory").value;
  if ($("#pids").value) payload.pids_max = Number($("#pids").value);
  if (cpu) {
    Object.assign(payload, cpuLimit(cpu));
  }
  if (port) {
    const [hostPort, containerPort] = port.split(":").map(Number);
    if (!hostPort || !containerPort)
      throw new Error("Port must use HOST:CONTAINER");
    payload.ports = [{ host_port: hostPort, container_port: containerPort }];
  }
  await api("/containers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  $("#run").close();
  event.target.reset();
  toast(`Starting ${payload.name}`);
  setTimeout(render, 400);
}

async function loadDetails(name, request) {
  const id = encode(name);
  const [container, logs, processes] = await Promise.all([
    api(`/containers/${id}`),
    api(`/containers/${id}/logs`).catch(() => ({ output: "" })),
    api(`/containers/${id}/processes`).catch(() => ({ processes: [] })),
  ]);
  const metrics =
    container.status === "running"
      ? await api(`/containers/${id}/metrics`).catch(() => null)
      : null;
  if (request !== detailsRequest || !$("#details").open) return;
  $("#detail-title").textContent = name;
  $("#detail-content").innerHTML =
    `<div class="detail-grid"><div class="card"><h3>Configuration</h3><dl>
      <dt>Status</dt><dd>${status(container.status)}</dd><dt>Image</dt><dd>${esc(container.image || "—")}</dd>
      <dt>Created</dt><dd>${esc(container.created_at || container.created || "—")}</dd><dt>Started</dt><dd>${esc(container.started_at || "—")}</dd>
      <dt>Stopped</dt><dd>${esc(container.stopped_at || "—")}</dd><dt>Exit code</dt><dd>${esc(container.exit_code ?? "—")}</dd>
      <dt>Address</dt><dd>${esc(container.network_address || "—")}</dd><dt>Ports</dt><dd>${portLinks(container)}</dd>
    </dl></div><div class="card"><div class="space-between-row"><h3>Resources</h3>${container.status !== "running" ? `<button data-action="resources" data-name="${esc(name)}" data-memory="${esc(container.resource_limits?.memory_max || "250M")}" data-pids="${esc(container.resource_limits?.pids_max || "64")}" data-cpu="${esc(container.resource_limits?.cpu_max || "50000 100000")}">Edit resources</button>` : '<small class="muted-text">Stop to edit</small>'}</div><dl>
      <dt>Configured limit</dt><dd>${esc(container.resource_limits?.memory_max || "—")}</dd>
      <dt>Memory</dt><dd>${metrics ? `${bytes(metrics.memory_used_bytes)} / ${bytes(metrics.memory_limit_bytes)}` : "—"}</dd>
      <dt>CPU</dt><dd>${esc(metrics?.cpu_percent ?? "—")}%</dd><dt>Processes</dt><dd>${esc(metrics?.process_count ?? "—")}</dd>
      <dt>Network RX/TX</dt><dd>${metrics ? `${bytes(metrics.network_rx_bytes)} / ${bytes(metrics.network_tx_bytes)}` : "—"}</dd>
    </dl></div></div>
    <div class="card"><h3>Logs</h3><pre>${esc(logs.output || logs.logs || "No output")}</pre></div>
    <div class="card"><h3>Processes</h3><pre>${esc(JSON.stringify(processes.processes || [], null, 2))}</pre></div>`;
  const row = $("#detail-title").parentElement;
  let box = row.querySelector(".detail-actions");
  if (!box) {
    box = document.createElement("div");
    box.className = "detail-actions";
    row.appendChild(box);
  }
  const live = container.status === "running";
  box.innerHTML = `<button data-detail-action="${live ? "stop" : "start"}" data-name="${esc(name)}">${live ? "Stop" : "Start"}</button><button class="danger" data-detail-action="delete" data-name="${esc(name)}">Delete</button>`;
}

function openPullImageDialog() {
  $("#pull-image-error").classList.add("is-hidden");
  $("#pull-image").showModal();
}

async function pullImage(name, reference) {
  const result = await withBusyCursor(() =>
    api("/images/pull", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, reference }),
    }),
  );
  if (result?.status !== "complete") {
    throw new Error("Image pull did not complete");
  }
  toast(`Pulled ${name}`);
  if (activeView === "images") await render();
}

document.addEventListener("click", async (event) => {
  const view = event.target.closest("[data-view]");
  if (view) {
    if (view.disabled) return;
    const restoreButton = setButtonLoading(view);
    activeView = view.dataset.view;
    sessionStorage.setItem("activeView", activeView);
    try {
      await render();
    } finally {
      restoreButton();
    }
    return;
  }
  const close = event.target.closest("[data-close]");
  if (close) {
    $(`#${close.dataset.close}`).close();
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const action = button.dataset.action;
  const name = button.dataset.name;
  const confirmations = {
    "compose-remove": `Remove ${name} and all its containers? Named volumes will be preserved.`,
    killall: "Delete ALL containers?",
    delete: `Stop and delete ${name}?`,
    "delete-image": `Delete image ${name}?`,
    "delete-volume": `Remove volume ${name}? This only succeeds when it is unused and empty.`,
  };
  if (confirmations[action] && !confirm(confirmations[action])) return;
  const restoreButton = setButtonLoading(button, "Please wait…");
  try {
    if (action === "refresh") await render();
    else if (action === "run") await openRunDialog();
    else if (action === "compose") {
      window.vcontainerCompose.open();
      return;
    }
    else if (action === "compose-new") {
      window.vcontainerCompose.open();
      return;
    }
    else if (action === "compose-edit") {
      const project = await api(`/compose/${encode(name)}`);
      window.vcontainerCompose.edit(name, project.yaml);
      return;
    }
    else if (action === "compose-start") {
      await api(`/compose/${encode(name)}/start`, { method: "POST" });
      void followComposeProject(name, "running");
    }
    else if (action === "compose-stop")
      await api(`/compose/${encode(name)}/stop`, { method: "POST" });
    else if (action === "compose-restart") {
      await api(`/compose/${encode(name)}/restart`, { method: "POST" });
      void followComposeProject(name, "running");
    }
    else if (action === "compose-remove") {
      await api(`/compose/${encode(name)}/down`, {
        method: "POST",
      });

      toast(`Removed Compose project ${name}`);
    }
    else if (action === "killall") await killAllContainers();
    else if (action === "details") {
      await showDetails(name);
      return;
    }
    else if (action === "resources") {
      $("#resource-name").value = name;
      $("#resource-memory").value = button.dataset.memory || "512M";
      $("#resource-pids").value = button.dataset.pids || "64";
      $("#resource-cpu").value = cpuCores(button.dataset.cpu);
      $("#resources").showModal();
      return;
    } else if (action === "start")
      await api(`/containers/${encode(name)}/start`, { method: "POST" });
    else if (action === "stop")
      await api(`/containers/${encode(name)}/stop`, { method: "POST" });
    else if (action === "delete")
      await api(`/containers/${encode(name)}`, { method: "DELETE" });
    else if (action === "delete-image")
      await api(`/images/${encode(name)}`, { method: "DELETE" });
    else if (action === "pull") {
      openPullImageDialog();
      return;
    } else if (action === "create-volume") {
      $("#create-volume-error").classList.add("is-hidden");
      $("#create-volume").showModal();
      return;
    } else if (action === "inspect-volume") {
      await inspectVolume(name);
      return;
    } else if (
      action === "copy-volume-path" &&
      inspectedVolume
    ) {
      await navigator.clipboard.writeText(inspectedVolume.mount_source);
      toast("Volume path copied");
      return;
    } else if (
      action === "delete-inspected-volume" &&
      inspectedVolume &&
      confirm(`Remove volume ${inspectedVolume.name}?`)
    ) {
      const volumeName = inspectedVolume.name;
      await api(`/volumes/${encode(volumeName)}`, { method: "DELETE" });
      inspectedVolume = null;
      $("#volume-details").close();
      toast(`Removed volume ${volumeName}`);
    } else if (
      action === "delete-volume"
    ) {
      await api(`/volumes/${encode(name)}`, { method: "DELETE" });
      toast(`Removed volume ${name}`);
    }
    if (refreshAfterAction.has(action)) void render();
  } catch (error) {
    toast(error.message, true);
  } finally {
    restoreButton();
  }
});

window.addEventListener("compose-changed", () => {
  if (activeView === "compose") render();
});

const pullImageForm = $("#pull-image-form");
pullImageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = pullImageForm.querySelector("button[type='submit']");
  if (button.disabled) return;
  const name = $("#pull-image-name").value.trim();
  const reference = $("#pull-image-source").value.trim();
  const errorMessage = $("#pull-image-error");
  if (!name || !reference) {
    errorMessage.textContent = "Enter a name and an image.";
    errorMessage.classList.remove("is-hidden");
    return;
  }
  errorMessage.classList.add("is-hidden");
  const restoreButton = setButtonLoading(button, "Pulling image…");
  const closeButtons = document.querySelectorAll('[data-close="pull-image"]');
  closeButtons.forEach((control) => {
    control.disabled = true;
  });
  try {
    await pullImage(name, reference);
    $("#pull-image").close();
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.classList.remove("is-hidden");
  } finally {
    restoreButton();
    closeButtons.forEach((control) => {
      control.disabled = false;
    });
  }
});
$("#pull-image").addEventListener("cancel", (event) => {
  if (pullImageForm.querySelector("button[type='submit']").disabled)
    event.preventDefault();
});

$("#create-volume-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.target.querySelector("button[type='submit']");
  if (button.disabled) return;
  const name = $("#volume-name").value.trim();
  const errorMessage = $("#create-volume-error");
  errorMessage.classList.add("is-hidden");
  const restoreButton = setButtonLoading(button, "Creating…");
  try {
    await api("/volumes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    $("#create-volume").close();
    event.target.reset();
    toast(`Created volume ${name}`);
    await render();
  } catch (error) {
    errorMessage.textContent = error.message;
    errorMessage.classList.remove("is-hidden");
  } finally {
    restoreButton();
  }
});

$("#run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.target.querySelector("button:not([type='button'])");
  if (button.disabled) return;
  const restoreButton = setButtonLoading(button, "Starting…");
  try {
    await createContainer(event);
  } catch (error) {
    toast(error.message, true);
  } finally {
    restoreButton();
  }
});
$("#resource-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = $("#resource-name").value;
  let cpu;
  try {
    cpu = cpuLimit($("#resource-cpu").value);
  } catch (error) {
    return toast(error.message, true);
  }
  const button = event.target.querySelector("button:not([type='button'])");
  if (button.disabled) return;
  const restoreButton = setButtonLoading(button, "Saving…");
  try {
    await api(`/containers/${encode(name)}/resources`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        memory_max: $("#resource-memory").value.trim(),
        pids_max: Number($("#resource-pids").value),
        ...cpu,
      }),
    });
    $("#resources").close();
    $("#details").close();
    toast(`Resources updated for ${name}`);
    await render();
  } catch (error) {
    toast(error.message, true);
  } finally {
    restoreButton();
  }
});
(function boot() {
  api("/health")
    .then(() => { updateHealth(); render(); })
    .catch((error) => {
      $("#health").textContent = "backend unavailable";
      $("#banner").textContent = "Waiting for backend... " + error.message;
      $("#banner").classList.remove("is-hidden");
      setTimeout(boot, 2000);
    });
})();

function setTheme(theme) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  $("#theme").setAttribute("aria-pressed", String(dark));
  $("#theme").textContent = dark ? "Light mode" : "Dark mode";
  try {
    localStorage.setItem("vcontainer-theme", dark ? "dark" : "light");
  } catch (_) {}
}
$("#theme").addEventListener("click", () => {
  setTheme(
    document.documentElement.dataset.theme === "dark" ? "light" : "dark",
  );
});
let initialTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
  ? "dark"
  : "light";
try {
  initialTheme = localStorage.getItem("vcontainer-theme") || initialTheme;
} catch (_) {}
setTheme(initialTheme);


window.killAllContainers = async function () {
  const list = asList(await api("/containers"), "containers");
  for (const c of list)
    await api(`/containers/${encode(c.name)}`, { method: "DELETE" }).catch(() => {});
  toast("All containers deleted");
  render();
};

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-detail-action]");
  if (!b) return;
  const name = b.dataset.name;
  const act = b.dataset.detailAction;
  if (act === "delete" && !confirm("Delete " + name + "?")) return;
  b.disabled = true;
  try {
    const path = "/containers/" + encode(name);
    if (act === "stop") await api(path + "/stop", { method: "POST" });
    else if (act === "start") await api(path, { method: "POST" });
    else await api(path, { method: "DELETE" });
    if (act === "delete") $("#details").close();
    else await showDetails(name);
    render();
  } catch (err) {
    toast(err.message, true);
    b.disabled = false;
  }
});

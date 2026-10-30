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
let activeView = "home";
let refreshTimer = null;
let inspectedVolume = null;





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



let pendingRequests = 0;

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
  const [containers, images, disk] = await Promise.all([
    getContainers(),
    api("/images"),
    api("/system/disk").catch(() => null),
  ]);
  const runningContainers = containers.filter(
    (item) => item.status === "running",
  );
  const metrics = {};
  await Promise.all(
    runningContainers.map(async (container) => {
      metrics[container.name] = await api(
        `/containers/${encode(container.name)}/metrics`,
      ).catch(() => null);
    }),
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
  $("#actions").innerHTML =
    '<button class="default" data-action="run">+ Run container</button>';
  $("#content").innerHTML = `<div class="container-summary">
      <article class="card"><span>Running</span><strong>${running}</strong></article>
      <article class="card"><span>Stopped</span><strong>${containers.length - running}</strong></article>
      <article class="card"><span>Images</span><strong>${asList(images, "images").length}</strong></article>
      <article class="card"><span>Disk utillization</span><strong>${disk ? bytes(disk.used_bytes) : "—"}</strong><small>${disk ? `Writable layers, metadata and logs · ${disk.container_count} containers` : "Disk usage unavailable"}</small></article>
    </div>
    <div class="resource-statistics">
      <article class="card resource-statistic-card"><span>Combined CPU</span><strong>${cpu.toFixed(1)}%</strong><small>${running} running containers</small></article>
      <article class="card resource-statistic-card"><span>Container memory</span><strong>${bytes(memoryUsed)}</strong><small>Current cgroup usage</small></article>
      <article class="card resource-statistic-card"><span>Processes</span><strong>${processes}</strong><small>Across running containers</small></article>
    </div>
    <div class="section-title"><h2>Containers</h2><button data-action="refresh">Refresh</button></div>
    <div class="container-grid">${containers.length ? containers.map((container) => containerCard(container, metrics[container.name])).join("") : '<div class="empty-state">No containers yet.</div>'}</div>`;
}

async function renderContainers() {
  const containers = await getContainers();
  const metrics = {};
  await Promise.all(
    containers
      .filter((item) => item.status === "running")
      .map(async (container) => {
        metrics[container.name] = await api(
          `/containers/${encode(container.name)}/metrics`,
        ).catch(() => null);
      }),
  );
  $("#title").textContent = "Containers";
  $("#actions").innerHTML =
    '<button class="default" data-action="run">+ Run container</button>';
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
    <thead><tr><th>Name</th><th>Size</th><th></th></tr></thead>
    <tbody>${images
      .map(
        (
          image,
        ) => `<tr><td data-label="Name"><b class="image-name">${esc(image.name)}</b></td><td data-label="Size">${image.size ? (image.size / 1048576).toFixed(1) + " MB" : ""}</td>
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

const liveHist = { cpu: [], ram: [] };
let liveLast = null;

function liveHtml() {
  return `<div class="live-row"><div class="card"><div class="space-between-row"><b>CPU usage</b><span id="live-cpu-val">—</span></div><canvas id="live-cpu"></canvas></div><div class="card"><div class="space-between-row"><b>RAM usage</b><span id="live-ram-val">—</span></div><canvas id="live-ram"></canvas></div></div>`;
}

function drawSpark(id, data, max, color) {
  const c = document.getElementById(id);
  if (!c) return;
  const w = (c.width = c.clientWidth || 300);
  const h = (c.height = 70);
  const g = c.getContext("2d");
  g.clearRect(0, 0, w, h);
  g.strokeStyle = "rgba(127,127,127,0.35)";
  g.strokeRect(0.5, 0.5, w - 1, h - 1);
  if (data.length < 2) return;
  const step = w / 59;
  const pts = data.map((v, i) => [
    w - (data.length - 1 - i) * step,
    h - 4 - (Math.min(max, Math.max(0, v)) / max) * (h - 8),
  ]);
  g.beginPath();
  pts.forEach(([x, y], i) => (i ? g.lineTo(x, y) : g.moveTo(x, y)));
  g.strokeStyle = color;
  g.lineWidth = 2;
  g.stroke();
  g.lineTo(pts[pts.length - 1][0], h);
  g.lineTo(pts[0][0], h);
  g.closePath();
  g.globalAlpha = 0.18;
  g.fillStyle = color;
  g.fill();
  g.globalAlpha = 1;
}

function drawLive() {
  drawSpark("live-cpu", liveHist.cpu, Math.max(10, ...liveHist.cpu), "#3a7bd5");
  drawSpark("live-ram", liveHist.ram, 100, "#2e9e5b");
  if (!liveLast) return;
  const d = liveLast;
  const cv = $("#live-cpu-val");
  const rv = $("#live-ram-val");
  if (cv) cv.textContent = `host ${d.host_cpu_percent}% · containers ${d.container_cpu_percent}%`;
  if (rv) rv.textContent = `${bytes(d.host_memory_used_bytes)} / ${bytes(d.host_memory_total_bytes)} · containers ${bytes(d.container_memory_bytes)}`;
}

async function liveTick() {
  if (document.hidden || activeView !== "home") return;
  try {
    const r = await fetch("/system/live");
    if (!r.ok) return;
    const d = await r.json();
    liveLast = d;
    liveHist.cpu.push(d.host_cpu_percent);
    liveHist.ram.push((d.host_memory_used_bytes / (d.host_memory_total_bytes || 1)) * 100);
    if (liveHist.cpu.length > 60) liveHist.cpu.shift();
    if (liveHist.ram.length > 60) liveHist.ram.shift();
    drawLive();
  } catch (_) {}
}
setInterval(liveTick, 1000);

const QUICK = [["blog", "8081:8081"], ["runner", "8082:8082"]];
function quickStartHtml() {
  return `<div class="card"><b>Quick start</b> ${QUICK.map(([n, p]) => `<button data-action="quick" data-img="${n}" data-port="${p}">Run ${n}</button>`).join(" ")} <button id="launch-blogdrop" onclick="launchBlogDrop()">Launch BlogDrop</button></div>`;
}

async function updateHealth() {
  try {
    const h = await api("/health");
    const caps = h.capabilities || {};
    $("#health").innerHTML =
      '<span class="dot on"></span>vcontainer: online<br>' +
      [["namespaces", "namespaces"], ["cgroups_v2", "cgroups v2"], ["overlayfs", "overlayfs"], ["network_tools", "network"]]
        .map(([k, l]) => (caps[k] ? '<span class="ok">✓</span>' : '<span class="bad">✗</span>') + l)
        .join("<br>");
  } catch (_) {
    $("#health").innerHTML = '<span class="dot off"></span>vcontainer: offline';
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
    else if (activeView === "containers") await renderContainers();
    else {
      await renderHome();
      $("#content").insertAdjacentHTML("afterbegin", quickStartHtml());
      const statsRow = document.querySelector(".resource-statistics");
      if (statsRow) statsRow.insertAdjacentHTML("afterend", liveHtml());
      else $("#content").insertAdjacentHTML("beforeend", liveHtml());
      drawLive();
    }
    $("#banner").classList.add("is-hidden");
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
  for (const assignment of text.split(",")) {
    const separator = assignment.indexOf("=");
    if (separator < 1) throw new Error("Environment must use KEY=value");
    environment[assignment.slice(0, separator).trim()] = assignment.slice(
      separator + 1,
    );
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
    const [quota, period] = cpu.split("/").map(Number);
    if (!quota || !period) throw new Error("CPU must use QUOTA/PERIOD");
    payload.cpu_quota = quota;
    payload.cpu_period = period;
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
    <div class="card"><h3>Logs</h3><pre>${esc(logs.output || "No output")}</pre></div>
    <div class="card"><h3>Processes</h3><pre>${esc(JSON.stringify(processes.processes || [], null, 2))}</pre></div>`;
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
  const restoreButton = setButtonLoading(button, "Please wait…");
  const name = button.dataset.name;
  try {
    if (button.dataset.action === "refresh") await render();
    else if (button.dataset.action === "run") await openRunDialog();
    else if (button.dataset.action === "details") await showDetails(name);
    else if (button.dataset.action === "resources") {
      $("#resource-name").value = name;
      $("#resource-memory").value = button.dataset.memory || "512M";
      $("#resource-pids").value = button.dataset.pids || "64";
      $("#resource-cpu").value = (button.dataset.cpu || "50000 100000").replace(
        " ",
        "/",
      );
      $("#resources").showModal();
    } else if (button.dataset.action === "start")
      await api(`/containers/${encode(name)}/start`, { method: "POST" });
    else if (button.dataset.action === "stop")
      await api(`/containers/${encode(name)}/stop`, { method: "POST" });
    else if (
      button.dataset.action === "delete" &&
      confirm(`Stop and delete ${name}?`)
    )
      await api(`/containers/${encode(name)}`, { method: "DELETE" });
    else if (
      button.dataset.action === "delete-image" &&
      confirm(`Delete image ${name}?`)
    )
      await api(`/images/${encode(name)}`, { method: "DELETE" });
    else if (button.dataset.action === "quick") {
      const cp = button.dataset.port.split(":")[1];
      const existing = await (await fetch("/containers")).json();
      const used = new Set(
        (Array.isArray(existing) ? existing : existing.containers || []).flatMap((c) =>
          (c.ports || []).map((m) =>
            String(typeof m === "string" ? m.split(":")[0] : m.host_port),
          ),
        ),
      );
      let hp = 8081;
      while (used.has(String(hp))) hp++;
      const r = await fetch("/containers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: button.dataset.img,
          memory: "250M",
          name: button.dataset.img + "-" + Math.random().toString(36).slice(2, 6),
          ports: [{ host_port: hp, container_port: cp }],
        }),
      });
      if (!r.ok) throw new Error((await r.json()).error || "start failed");
      toast("Started " + button.dataset.img + " on port " + hp);
    } else if (button.dataset.action === "pull") {
      openPullImageDialog();
      return;
    } else if (button.dataset.action === "create-volume") {
      $("#create-volume-error").classList.add("is-hidden");
      $("#create-volume").showModal();
      return;
    } else if (button.dataset.action === "inspect-volume") {
      await inspectVolume(name);
      return;
    } else if (
      button.dataset.action === "copy-volume-path" &&
      inspectedVolume
    ) {
      await navigator.clipboard.writeText(inspectedVolume.mount_source);
      toast("Volume path copied");
      return;
    } else if (
      button.dataset.action === "delete-inspected-volume" &&
      inspectedVolume &&
      confirm(`Remove volume ${inspectedVolume.name}?`)
    ) {
      const volumeName = inspectedVolume.name;
      await api(`/volumes/${encode(volumeName)}`, { method: "DELETE" });
      inspectedVolume = null;
      $("#volume-details").close();
      toast(`Removed volume ${volumeName}`);
    } else if (
      button.dataset.action === "delete-volume" &&
      confirm(
        `Remove volume ${name}? This only succeeds when it is unused and empty.`,
      )
    ) {
      await api(`/volumes/${encode(name)}`, { method: "DELETE" });
      toast(`Removed volume ${name}`);
    }
    setTimeout(render, 300);
  } catch (error) {
    toast(error.message, true);
  } finally {
    restoreButton();
  }
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
  const [cpuQuota, cpuPeriod] = $("#resource-cpu")
    .value.trim()
    .split("/")
    .map(Number);
  if (!cpuQuota || !cpuPeriod) return toast("CPU must use QUOTA/PERIOD", true);
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
        cpu_quota: cpuQuota,
        cpu_period: cpuPeriod,
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
api("/health")
  .then((health) => {
    updateHealth();
    render();
  })
  .catch((error) => {
    $("#health").textContent = "● backend unavailable";
    $("#banner").textContent = error.message;
    $("#banner").classList.remove("is-hidden");
  });

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


window.launchBlogDrop = async function() {
  const btn = document.getElementById("launch-blogdrop");
  if(!btn) return;
  btn.disabled = true; btn.textContent = "Launching...";
  
  const doReq = async (p) => {
    const r = await fetch("/containers", { 
      method: "POST", 
      headers: {"Content-Type": "application/json"}, 
      body: JSON.stringify(p) 
    });
    if (!r.ok) throw new Error((await r.json()).error || "Failed");
  };

  try {
    await doReq({ name: "blogdrop-db", image: "mysql", command: ["docker-entrypoint.sh", "mysqld"], memory: "1G", pids: 256, ip: "10.88.0.30", env: ["MYSQL_ROOT_PASSWORD=change-root-password", "MYSQL_DATABASE=blogdrop_db", "MYSQL_USER=blogdrop", "MYSQL_PASSWORD=change-database-password"], volumes: ["blogdrop-db:/var/lib/mysql", "blogdrop-db-init:/docker-entrypoint-initdb.d"], network: "bridge" });
    await doReq({ name: "blogdrop-backend", image: "node", command: ["npm", "start"], memory: "500M", pids: 256, ip: "10.88.0.31", env: ["DB_HOST=10.88.0.30", "DB_USER=blogdrop", "DB_PASSWORD=change-database-password", "DB_NAME=blogdrop_db", "PORT=3000"], network: "bridge" });
    await doReq({ name: "blogdrop-frontend", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "250M", pids: 256, ip: "10.88.0.32", volumes: ["blogdrop-frontend:/usr/share/nginx/html"], network: "bridge" });
    await doReq({ name: "blogdrop-gateway", image: "nginx", command: ["nginx", "-g", "daemon off;"], memory: "250M", pids: 256, ip: "10.88.0.33", ports: [{ host_port: 8085, container_port: 80 }], volumes: ["blogdrop-gateway:/etc/nginx/conf.d"], network: "bridge" });
    alert("BlogDrop launched! Gateway available on port 8085.");
  } catch (err) {
    alert("Launch failed: " + err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Launch BlogDrop";
    if(typeof loadContainers === 'function') loadContainers();
  }
};

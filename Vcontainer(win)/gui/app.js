const $ = (selector) => document.querySelector(selector);
let containers = [];

async function api(path, options) {
  const response = await fetch(path, options);
  let data = null;
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data?.detail || data?.error || response.statusText);
  return data;
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function toast(message) {
  const element = document.createElement("div");
  element.className = "toast";
  element.textContent = message;
  document.body.append(element);
  setTimeout(() => element.remove(), 3500);
}

async function boot() {
  try {
    const health = await api("/health");
    $("#health").textContent = `● ${health.service}: ${health.status}`;
    $("#banner").classList.add("hidden");
    await show("containers");
  } catch (error) {
    $("#banner").textContent = `Backend unavailable: ${error.message}`;
    $("#banner").classList.remove("hidden");
  }
}

async function show(kind) {
  $("#title").textContent = kind[0].toUpperCase() + kind.slice(1);
  try {
    if (kind === "images") {
      const data = await api("/images");
      renderImages(data.images || []);
    } else {
      const data = await api("/containers");
      containers = data.containers || [];
      renderContainers();
    }
  } catch (error) { toast(error.message); }
}

function renderImages(images) {
  if (!images.length) { $("#content").innerHTML = '<div class="empty">No images yet.</div>'; return; }
  $("#content").innerHTML = `<table><tr><th>Name</th><th>Root filesystem</th><th></th></tr>${images.map((image) => `
    <tr><td>${escapeHtml(image.name)}</td><td><code>${escapeHtml(image.rootfs)}</code></td>
    <td><button onclick="deleteImage('${escapeHtml(image.name)}')">Delete</button></td></tr>`).join("")}</table>`;
}

function renderContainers() {
  if (!containers.length) { $("#content").innerHTML = '<div class="empty">No containers yet.</div>'; return; }
  $("#content").innerHTML = `<div class="grid">${containers.map((container) => {
    const name = escapeHtml(container.name);
    const command = (container.command || []).map(escapeHtml).join(" ");
    const ports = (container.ports || []).map((mapping) =>
      `${mapping.host_port}:${mapping.container_port}`
    ).join(", ") || "—";
    const open = container.ports?.length
      ? `<br><a target="_blank" href="http://127.0.0.1:${container.ports[0].host_port}">Open service</a>`
      : "";
    const action = container.status === "running" ? "stopContainer" : "startContainer";
    const label = container.status === "running" ? "Stop" : "Start";
    return `<article class="card"><h3>${name} <span class="badge">${escapeHtml(container.status)}</span></h3>
      <p>Image: <b>${escapeHtml(container.image || "—")}</b><br>Address: ${escapeHtml(container.network_address || "—")}<br>Ports: ${escapeHtml(ports)}${open}<br>Command: <code>${command || "—"}</code></p>
      <div id="s-${name}">Memory — · PIDs — · CPU —</div><p>
      <button onclick="${action}('${name}')">${label}</button> <button onclick="showLogs('${name}')">Logs</button>
      <button onclick="showProcesses('${name}')">Processes</button> <button onclick="deleteContainer('${name}')">Delete</button></p></article>`;
  }).join("")}</div>`;
  containers.filter((container) => container.status === "running").forEach(loadMetrics);
}

async function loadMetrics(container) {
  try {
    const metrics = await api(`/containers/${encodeURIComponent(container.name)}/metrics`);
    const element = document.getElementById(`s-${container.name}`);
    if (element) element.textContent = `Memory ${metrics.memory_used_bytes || 0} / ${metrics.memory_limit_bytes ?? "max"} · PIDs ${metrics.process_count || 0} / ${metrics.process_limit ?? "max"} · CPU ${metrics.cpu_percent ?? "—"}%`;
  } catch (_) {}
}

async function openRunDialog() {
  try {
    const data = await api("/images");
    $("#image").innerHTML = (data.images || []).map((image) => `<option value="${escapeHtml(image.name)}">${escapeHtml(image.name)}</option>`).join("");
    $("#run").showModal();
  } catch (error) { toast(error.message); }
}

async function runContainer(event) {
  event.preventDefault();
  try {
    const command = $("#command").value.trim();
    const cpu = $("#cpus").value.trim();
    const ip = $("#ip").value.trim();
    const port = $("#port").value.trim();
    const payload = {image: $("#image").value, name: $("#name").value,
      command: command ? ["/bin/sh", "-c", command] : undefined};
    if ($("#memory").value) payload.memory_max = $("#memory").value;
    if ($("#pids").value) payload.pids_max = Number($("#pids").value);
    if (cpu) {
      const [quota, period] = cpu.split("/").map(Number);
      if (!quota || !period) throw new Error("CPU must use QUOTA/PERIOD format");
      payload.cpu_quota = quota; payload.cpu_period = period;
    }
    if (ip) { payload.network = "bridge"; payload.ip = ip; }
    if (port) {
      const [hostPort, containerPort] = port.split(":").map(Number);
      if (!hostPort || !containerPort) {
        throw new Error("Port must use HOST_PORT:CONTAINER_PORT");
      }
      payload.ports = [{host_port: hostPort, container_port: containerPort}];
    }
    await api("/containers", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)});
    $("#run").close();
    setTimeout(() => show("containers"), 500);
  } catch (error) { toast(error.message); }
}

async function startContainer(name) {
  try { await api(`/containers/${encodeURIComponent(name)}/start`, {method: "POST"}); setTimeout(() => show("containers"), 500); }
  catch (error) { toast(error.message); }
}

async function stopContainer(name) {
  try { await api(`/containers/${encodeURIComponent(name)}/stop`, {method: "POST"}); await show("containers"); }
  catch (error) { toast(error.message); }
}

async function deleteContainer(name) {
  if (!confirm(`Delete ${name}?`)) return;
  try { await api(`/containers/${encodeURIComponent(name)}`, {method: "DELETE"}); await show("containers"); }
  catch (error) { toast(error.message); }
}

async function showLogs(name) {
  try {
    const data = await api(`/containers/${encodeURIComponent(name)}/logs`);
    $("#detail-title").textContent = `Logs: ${name}`; $("#detail-text").textContent = data.output || "No log output"; $("#details").showModal();
  } catch (error) { toast(error.message); }
}

async function showProcesses(name) {
  try {
    const data = await api(`/containers/${encodeURIComponent(name)}/processes`);
    $("#detail-title").textContent = `Processes: ${name}`; $("#detail-text").textContent = JSON.stringify(data.processes || [], null, 2); $("#details").showModal();
  } catch (error) { toast(error.message); }
}

async function deleteImage(name) {
  if (!confirm(`Delete ${name}?`)) return;
  try { await api(`/images/${encodeURIComponent(name)}`, {method: "DELETE"}); await show("images"); }
  catch (error) { toast(error.message); }
}

boot();

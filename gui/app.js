const $ = s => document.querySelector(s);
const enc = encodeURIComponent;
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const bytes = n => {
  if (n == null) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  while (n >= 1024 && i < 3) { n /= 1024; i++; }
  return n.toFixed(i ? 1 : 0) + ' ' + units[i];
};
async function api(path, options) {
  const r = await fetch(path, options);
  let data = null;
  try { data = await r.json(); } catch (e) {}
  if (!r.ok) throw Error(data?.error || r.statusText);
  return data;
}
function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast';
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => t.remove(), 3500);
}
async function busy(btn, label, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = label;
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = old; }
}
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('vc-theme', t); } catch (e) {}
}
try { setTheme(localStorage.getItem('vc-theme') || 'dark'); } catch (e) {}

let timers = [];
let hist = {mem: [], pid: []};
let reloadLogs = null;
const every = (ms, fn) => timers.push(setInterval(fn, ms));
const stopTimers = () => { timers.forEach(clearInterval); timers = []; };

const dot = s => `<span class="dot ${esc(s)}"></span>${esc(s)}`;
const portLinks = c => (c.ports || []).map(p => `<a target="_blank" rel="noopener" href="http://localhost:${esc(p.split(':')[0])}">${esc(p)}</a>`).join(', ') || '—';
const toggleBtn = c => c.status === 'running'
  ? `<button data-act="stop" data-id="${esc(c.id)}">Stop</button>`
  : `<button data-act="start" data-id="${esc(c.id)}">Start</button>`;

function containerTable(list) {
  if (!list.length) return '<div class="empty">No containers yet.</div>';
  const rows = list.map(c => `<tr>
    <td data-label="Status"><span class="pill ${esc(c.status)}">${esc(c.status)}</span></td>
    <td data-label="Name"><a class="rname" href="#/containers/${enc(c.id)}">${esc(c.name)}</a></td>
    <td data-label="Image"><span class="chip">${esc(c.image || '—')}</span></td>
    <td data-label="Ports" class="mono">${portLinks(c)}</td>
    <td data-label="Memory limit" class="mono ${c.memory ? '' : 'muted'}">${esc(c.memory || 'No limit')}</td>
    <td class="act">${toggleBtn(c)}<button class="danger" data-act="delete" data-id="${esc(c.id)}">Delete</button></td></tr>`).join('');
  return `<table><tr class="hd"><th>Status</th><th>Name</th><th>Image</th><th>Ports</th><th>Memory limit</th><th></th></tr>${rows}</table>`;
}

const meter = (label, used, limit, fmt) => {
  const pct = limit && used != null ? Math.min(100, used / limit * 100) : 0;
  return `<div class="meter"><div class="between"><span class="muted">${label}</span><span>${fmt(used)} / ${limit ? fmt(limit) : 'no limit'}</span></div>${limit ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ''}</div>`;
};

function openBtn(c) {
  const hp = ((c.ports || [])[0] || '').split(':')[0];
  return c.status === 'running' && hp ? ` <a class="btn primary sm" target="_blank" rel="noopener" href="http://localhost:${esc(hp)}">Open ↗</a>` : '';
}

function detailsList(c, s) {
  const mem = s ? (s.memory_limit_bytes ? bytes(s.memory_limit_bytes) : 'none') : (c.memory || 'none');
  const cpu = s ? (s.cpu_limit || 'none') : (c.cpus || 'none');
  const pids = s ? (s.pid_limit ?? 'none') : (c.pids || 'none');
  const rows = [['ID', esc(c.id)], ['Image', esc(c.image || '—')], ['Created', esc(c.created || '—')], ['PID', esc(c.pid ?? '—')],
    ['Ports', portLinks(c) + openBtn(c)], ['Command', `<code>${esc((c.command || []).join(' ') || '—')}</code>`],
    ['Memory limit', esc(mem)], ['CPU limit', esc(cpu)], ['PIDs limit', esc(pids)]];
  return `<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
}

function execBox(c) {
  if (c.status !== 'running') return '<p class="muted">Start the container to run commands.</p>';
  return `<form class="exec cx" data-id="${esc(c.id)}"><input placeholder="Run a command, e.g. ls -la /" required autocomplete="off"><button class="primary">Run</button></form><pre class="out hidden"></pre>`;
}

function miniBar(label, used, limit, fmt) {
  if (!limit) return `<div class="mini between"><span class="muted">${label}</span><span class="muted">${fmt(used)} · no limit</span></div>`;
  const pct = Math.min(100, Math.round((used || 0) / limit * 100));
  const level = pct >= 90 ? 'hot' : pct >= 70 ? 'warm' : '';
  return `<div class="mini"><div class="between"><span class="muted">${label}</span><span>${pct}%</span></div><div class="bar ${level}"><i style="width:${pct}%"></i></div></div>`;
}

function containerCard(c, s) {
  const id = esc(c.id);
  const running = c.status === 'running';
  const hostPort = ((c.ports || [])[0] || '').split(':')[0];
  const bars = !running ? '<p class="muted">Stopped</p>' : !s ? '<p class="muted">Stats unavailable</p>'
    : miniBar('Memory', s.memory_bytes, s.memory_limit_bytes, bytes) + miniBar('PIDs', s.pids, s.pid_limit, n => n ?? '—');
  return `<article class="card ccard">
    <div class="chead"><div><a class="cname" href="#/containers/${enc(c.id)}">${esc(c.name)}</a>
      <div class="meta"><span class="pill ${esc(c.status)}">${esc(c.status)}</span> <span class="chip">${esc(c.image || '—')}</span></div></div>
      ${running && hostPort ? `<a class="btn primary" target="_blank" rel="noopener" href="http://localhost:${esc(hostPort)}">Open :${esc(hostPort)} ↗</a>` : ''}</div>
    ${bars}
    <div class="cbtns"><button data-act="open" data-id="${id}">Details</button>${toggleBtn(c)}<button class="danger" data-act="delete" data-id="${id}">Delete</button></div></article>`;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const level = p => (p >= 90 ? 'hot' : p >= 70 ? 'warm' : '');
let cpuPrev = null;
let wasOffline = false;
const OFF = [['g-cpu', 'Host CPU'], ['g-mem', 'Host memory'], ['g-pid', 'Process IDs'], ['g-cmem', 'Container memory']];
const offlineGauges = () => OFF.map(([t, l]) => gauge(t + ' off', l, '—', 'Backend offline', null)).join('');

function cpuPct(a, b) {
  const sum = x => x.reduce((p, q) => p + q, 0);
  const total = sum(b) - sum(a);
  const idle = (b[3] + b[4]) - (a[3] + a[4]);
  return total > 0 ? Math.max(0, Math.min(100, Math.round(100 * (1 - idle / total)))) : null;
}

async function sample() {
  const s = await api('/system');
  const pct = cpuPrev ? cpuPct(cpuPrev, s.cpu_times) : null;
  cpuPrev = s.cpu_times;
  return [s, pct];
}

function gauge(tone, label, value, sub, pct) {
  return `<div class="card gauge ${tone}"><div class="between"><span class="muted">${label}</span><span class="gv">${value}</span></div>
    <div class="bar ${pct != null ? level(pct) : ''}">${pct != null ? `<i style="width:${pct}%"></i>` : ''}</div><div class="muted sub">${sub}</div></div>`;
}

async function drawGauges(ids) {
  const el = $('#gauges');
  try {
    const [[sys, cpu], stats] = await Promise.all([sample(),
      Promise.all(ids.map(id => api(`/containers/${enc(id)}/stats`).catch(() => null)))]);
    if (wasOffline) { wasOffline = false; return route(); }
    const ok = stats.filter(Boolean);
    const cmem = ok.reduce((a, s) => a + (s.memory_bytes || 0), 0);
    const pids = ok.reduce((a, s) => a + (s.pids || 0), 0);
    const pidCap = ok.length && ok.every(s => s.pid_limit) ? ok.reduce((a, s) => a + s.pid_limit, 0) : 0;
    const used = sys.mem_total - sys.mem_available;
    const memPct = Math.round(used / sys.mem_total * 100);
    const cPct = Math.min(100, Math.round(cmem / sys.mem_total * 100));
    if (el) el.innerHTML =
      gauge('g-cpu', 'Host CPU', cpu == null ? '…' : cpu + '%', `${sys.cpus} cores · load ${sys.load[0].toFixed(2)}`, cpu) +
      gauge('g-mem', 'Host memory', memPct + '%', `${bytes(used)} of ${bytes(sys.mem_total)} used`, memPct) +
      gauge('g-pid', 'Process IDs', pids, pidCap ? `of ${pidCap} allowed, ${ok.length} running` : `in ${ok.length} running container${ok.length === 1 ? '' : 's'}`,
        pidCap ? Math.round(pids / pidCap * 100) : null) +
      gauge('g-cmem', 'Container memory', bytes(cmem), `${cPct}% of host RAM`, cPct);
  } catch (e) {
    wasOffline = true;
    if (el) el.innerHTML = offlineGauges();
    document.querySelectorAll('.tile .big').forEach(t => { t.textContent = '—'; });
    const grid = document.querySelector('.cgrid');
    if (grid) grid.classList.add('stale');
  }
}

async function home() {
  $('#title').textContent = 'Home';
  wasOffline = false;
  let data = null;
  try { data = await Promise.all([api('/containers'), api('/images')]); } catch (e) {}
  const off = !data;
  const [cs, imgs] = data || [[], []];
  const running = cs.filter(c => c.status === 'running');
  const ids = running.map(c => c.id);
  const stats = {};
  await Promise.all(running.map(async c => { stats[c.id] = await api(`/containers/${enc(c.id)}/stats`).catch(() => null); }));
  const quick = off ? [] : [['blog', '8081:8081'], ['runner', '8082:8082']].filter(([n]) => imgs.some(i => i.name === n));
  const ordered = [...cs].sort((a, b) => (b.status === 'running') - (a.status === 'running'));
  const val = v => (off ? '—' : v);
  $('#view').innerHTML = `<div class="tiles">
    <div class="card tile t-ok"><div class="muted">Running</div><div class="big">${val(running.length)}</div></div>
    <div class="card tile t-bad"><div class="muted">Stopped</div><div class="big">${val(cs.length - running.length)}</div></div>
    <div class="card tile t-lav"><div class="muted">Images</div><div class="big">${val(imgs.length)}</div></div>
    <div class="card tile t-pink"><div class="muted">Image storage</div><div class="big">${val(bytes(imgs.reduce((a, i) => a + (i.size || 0), 0)))}</div></div></div>
    <div id="gauges" class="gauges"></div>
    ${quick.length ? `<div class="card"><b>Quick start</b> ${quick.map(([n, p]) => `<button data-act="quick" data-img="${n}" data-port="${p}">Run ${n}</button>`).join(' ')}</div>` : ''}
    <h3>Containers</h3>${off ? '<div class="empty">Backend offline. Start it with ./start.sh</div>'
      : cs.length ? `<div class="cgrid">${ordered.map(c => containerCard(c, stats[c.id])).join('')}</div>` : '<div class="empty">No containers yet.</div>'}`;
  cpuPrev = null;
  try { await sample(); await sleep(400); } catch (e) {}
  await drawGauges(ids);
  every(3000, () => drawGauges(ids));
}

async function containers() {
  $('#title').textContent = 'Containers';
  $('#actions').innerHTML = '<button class="primary" data-act="run">+ Run container</button>';
  const draw = async () => { $('#view').innerHTML = containerTable(await api('/containers')); };
  await draw();
  every(5000, () => draw().catch(() => {}));
}

const spark = v => {
  if (v.length < 2) return '<svg class="spark"></svg>';
  const max = Math.max(...v, 1);
  const pts = v.map((y, i) => `${(i * 200 / (v.length - 1)).toFixed(1)},${(38 - y / max * 34).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 200 40" preserveAspectRatio="none"><polyline points="${pts}"/></svg>`;
};
function statCard(label, used, limit, series, fmt) {
  const pct = limit && used != null ? Math.min(100, used / limit * 100) : 0;
  return `<div class="card"><div class="muted">${label}</div>
    <div class="big">${fmt(used)} <small>/ ${limit ? fmt(limit) : 'no limit'}</small></div>
    ${limit ? `<div class="bar"><i style="width:${pct}%"></i></div>` : ''}${spark(series)}</div>`;
}

async function detail(id) {
  const c = await api('/containers/' + enc(id));
  const running = c.status === 'running';
  const s = running ? await api(`/containers/${enc(id)}/stats`).catch(() => null) : null;
  $('#title').innerHTML = `<a class="back" href="#/containers">←</a>${esc(c.name)} <small class="muted">${dot(c.status)}</small>`;
  $('#actions').innerHTML = toggleBtn(c) + ` <button class="danger" data-act="delete" data-id="${esc(c.id)}" data-back="1">Delete</button>`;
  $('#view').innerHTML = `<div class="split"><div class="col">
      <div class="card"><div class="between"><h3>Logs <small id="lognote" class="muted"></small></h3><button data-act="logs">Refresh</button></div><pre id="log">Loading…</pre></div>
      <div class="card"><h3>Console</h3>${execBox(c)}</div>
    </div><div class="col">
      <div class="card"><h3>Details</h3>${detailsList(c, s)}</div>
      <div id="res" class="col"></div></div></div>`;
  const LOG_LINES = 10;
  const loadLogs = async () => {
    const el = $('#log');
    if (!el) return;
    const lines = ((await api(`/containers/${enc(id)}/logs`)).logs || '').split('\n').filter(Boolean);
    el.textContent = lines.length ? lines.slice(-LOG_LINES).join('\n') : '(no output)';
    const note = $('#lognote');
    if (note) note.textContent = lines.length > LOG_LINES ? `last ${LOG_LINES} of ${lines.length} lines` : '';
  };
  reloadLogs = loadLogs;
  await loadLogs();
  if (!running) return;
  hist = {mem: [], pid: []};
  const tick = async () => {
    const st = await api(`/containers/${enc(id)}/stats`);
    hist.mem.push(st.memory_bytes || 0); hist.pid.push(st.pids || 0);
    hist.mem = hist.mem.slice(-60); hist.pid = hist.pid.slice(-60);
    const el = $('#res');
    if (el) el.innerHTML = statCard('Memory', st.memory_bytes, st.memory_limit_bytes, hist.mem, bytes)
      + statCard('PIDs', st.pids, st.pid_limit, hist.pid, n => n ?? '—');
  };
  await tick();
  every(2000, () => tick().catch(() => {}));
  every(4000, () => loadLogs().catch(() => {}));
}

const ago = iso => {
  const t = Date.parse(iso);
  if (!t) return '';
  const d = (Date.now() - t) / 1000;
  if (d < 3600) return Math.max(1, Math.round(d / 60)) + 'm ago';
  if (d < 86400) return Math.round(d / 3600) + 'h ago';
  return Math.round(d / 86400) + 'd ago';
};

async function images() {
  $('#title').textContent = 'Images';
  $('#actions').innerHTML = '<button data-act="upload">Upload .tar</button><button class="primary" data-act="build">Build from VC File</button>';
  const [xs, cs] = await Promise.all([api('/images'), api('/containers').catch(() => [])]);
  const rows = xs.map(x => {
    const mine = cs.filter(c => c.image === x.name);
    const run = mine.filter(c => c.status === 'running').length;
    const use = run ? `<span class="pill use">${run} running</span>` : `<span class="pill">${mine.length ? mine.length + ' stopped' : 'unused'}</span>`;
    const when = String(x.created || '—').replace('T', ' ').slice(0, 16);
    const age = ago(x.created);
    return `<tr>
    <td data-label="Name"><span class="rname rimg">${esc(x.name)}</span></td>
    <td data-label="Size"><span class="chip size">${bytes(x.size)}</span></td>
    <td data-label="Created (UTC)" class="mono">${esc(when)}${age ? ` <span class="muted">· ${esc(age)}</span>` : ''}</td>
    <td data-label="Command"><span class="chip cmd">${esc((x.cmd || []).join(' '))}</span></td>
    <td data-label="In use">${use}</td>
    <td class="act"><a href="/images/${enc(x.name)}/download" download="${esc(x.name)}.tar"><button>Download</button></a>
    <button class="danger" data-act="delimg" data-id="${esc(x.name)}">Delete</button></td></tr>`;
  }).join('');
  $('#view').innerHTML = `<table><tr class="hd"><th>Name</th><th>Size</th><th>Created (UTC)</th><th>Command</th><th>In use</th><th></th></tr>${rows}</table>`;
}

async function route() {
  stopTimers();
  const [page, id, tab] = location.hash.replace(/^#\//, '').split('/');
  const name = page || 'home';
  document.querySelectorAll('[data-nav]').forEach(a => a.classList.toggle('on', a.dataset.nav === name));
  $('#actions').innerHTML = '';
  $('#view').innerHTML = '<div class="empty"><span class="spin"></span> Loading…</div>';
  try {
    if (name === 'containers' && id) await detail(decodeURIComponent(id), tab || 'overview');
    else if (name === 'containers') await containers();
    else if (name === 'images') await images();
    else await home();
  } catch (e) {
    $('#view').innerHTML = `<div class="empty">Failed to load: ${esc(e.message)}</div>`;
  }
}

document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]');
  if (!b) return;
  const {act, id, img, port, dlg, back} = b.dataset;
  try {
    if (act === 'theme') setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
    else if (act === 'close') $('#' + dlg).close();
    else if (act === 'reload') route();
    else if (act === 'logs') { if (reloadLogs) await reloadLogs(); }
    else if (act === 'open') location.hash = '#/containers/' + enc(id);
    else if (act === 'build') $('#build').showModal();
    else if (act === 'upload') $('#up').click();
    else if (act === 'run') {
      const xs = await api('/images');
      $('#image').innerHTML = xs.map(x => `<option>${esc(x.name)}</option>`).join('');
      $('#run').showModal();
    } else if (act === 'start') {
      await busy(b, 'Starting…', () => api('/containers/' + enc(id), {method: 'POST'})); route();
    } else if (act === 'stop') {
      await busy(b, 'Stopping…', () => api(`/containers/${enc(id)}/stop`, {method: 'POST'})); route();
    } else if (act === 'quick') {
      await busy(b, 'Starting…', async () => {
        const list = await api('/containers');
        const names = new Set(list.map(c => c.name));
        const used = new Set(list.flatMap(c => (c.ports || []).map(p => Number(p.split(':')[0]))));
        const [host, inner] = port.split(':').map(Number);
        let name = img, n = 1;
        while (names.has(name)) name = `${img}-${++n}`;
        let hp = host;
        if (used.has(hp)) { hp = host + 100; while (used.has(hp)) hp++; }
        await api('/containers', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image: img, name, port: `${hp}:${inner}`})});
        toast(`${name} started on :${hp}`);
      });
      route();
    } else if (act === 'delete' && confirm('Delete container ' + id + '?')) {
      await busy(b, 'Deleting…', () => api('/containers/' + enc(id), {method: 'DELETE'}));
      if (back) location.hash = '#/containers'; else route();
    } else if (act === 'delimg' && confirm('Delete image ' + id + '?')) {
      await api('/images/' + enc(id), {method: 'DELETE'}); route();
    }
  } catch (x) { toast(x.message); }
});

document.addEventListener('submit', async e => {
  e.preventDefault();
  try {
    if (e.target.id === 'runform') {
      await busy($('#rungo'), 'Running…', async () => {
        const command = $('#command').value.trim();
        await api('/containers', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
          image: $('#image').value, name: $('#name').value, command: command ? ['/bin/sh', '-c', command] : undefined,
          memory: $('#memory').value || undefined, cpus: $('#cpus').value || undefined,
          pids: $('#pids').value || undefined, port: $('#port').value || undefined})});
        $('#run').close(); location.hash = '#/containers'; route();
      });
    } else if (e.target.id === 'buildform') {
      await busy($('#bgo'), 'Building…', async () => {
        await api('/images/build', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
          file: $('#bfile').value.trim(), clean: $('#bclean').checked, update: $('#bupdate').checked})});
        $('#build').close(); toast('Image built'); location.hash = '#/images'; route();
      });
    }
  } catch (x) { toast(x.message); }
});

$('#up').addEventListener('change', async e => {
  const f = e.target.files[0];
  e.target.value = '';
  if (!f) return;
  const name = f.name.replace(/\.tar$/, '');
  if (!/^[A-Za-z0-9_.-]+$/.test(name)) return toast('Rename the file to letters, digits, . _ - only');
  try { await api(`/images/${enc(name)}/upload`, {method: 'POST', body: f}); toast('Uploaded ' + name); route(); }
  catch (x) { toast(x.message); }
});

window.addEventListener('hashchange', route);
document.addEventListener('submit', async e => {
  const form = e.target;
  if (!form.classList.contains('cx')) return;
  const input = form.querySelector('input');
  const out = form.nextElementSibling;
  await busy(form.querySelector('button'), 'Running…', async () => {
    try {
      const r = await api(`/containers/${enc(form.dataset.id)}/exec`, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({command: ['/bin/sh', '-c', input.value]})});
      out.classList.remove('hidden');
      out.textContent = `$ ${input.value}\n${r.stdout}${r.stderr}[exit ${r.code}]`;
    } catch (x) { toast(x.message); }
  });
});

async function health() {
  try {
    const h = await api('/health');
    const caps = h.capabilities || {};
    const items = [['Namespaces', caps.namespaces], ['cgroups v2', caps.cgroups_v2], ['OverlayFS', caps.overlayfs], ['Networking', caps.network_tools]];
    $('#health').innerHTML = `<div class="sys"><div class="between"><b>System</b><span class="ok">● Online</span></div>${items.map(([n, v]) =>
      `<div class="between"><span>${n}</span><span class="${v ? 'ok' : 'bad'}">${v ? '✓' : '✗'}</span></div>`).join('')}</div>`;
    $('#banner').classList.add('hidden');
  } catch (e) {
    $('#health').innerHTML = '<div class="sys"><div class="between"><b>System</b><span class="bad">● Offline</span></div></div>';
    $('#banner').textContent = 'Backend unavailable: ' + e.message;
    $('#banner').classList.remove('hidden');
  }
}
health();
route();
setInterval(health, 10000);

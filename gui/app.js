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

let timer = null;
let hist = {mem: [], pid: []};
const every = (ms, fn) => { clearInterval(timer); timer = setInterval(fn, ms); };

const dot = s => `<span class="dot ${esc(s)}"></span>${esc(s)}`;
const portLinks = c => (c.ports || []).map(p => `<a target="_blank" rel="noopener" href="http://localhost:${esc(p.split(':')[0])}">${esc(p)}</a>`).join(', ') || '—';
const toggleBtn = c => c.status === 'running'
  ? `<button data-act="stop" data-id="${esc(c.id)}">Stop</button>`
  : `<button data-act="start" data-id="${esc(c.id)}">Start</button>`;

function containerTable(list) {
  if (!list.length) return '<div class="empty">No containers yet.</div>';
  const rows = list.map(c => `<tr><td>${dot(c.status)}</td>
    <td><a href="#/containers/${enc(c.id)}">${esc(c.name)}</a></td><td>${esc(c.image || '—')}</td>
    <td>${portLinks(c)}</td><td>${esc(c.memory || '—')}</td>
    <td class="act">${toggleBtn(c)}<button class="danger" data-act="delete" data-id="${esc(c.id)}">Delete</button></td></tr>`).join('');
  return `<table><tr><th>Status</th><th>Name</th><th>Image</th><th>Ports</th><th>Mem limit</th><th></th></tr>${rows}</table>`;
}

async function home() {
  $('#title').textContent = 'Home';
  const [cs, imgs] = await Promise.all([api('/containers'), api('/images')]);
  const running = cs.filter(c => c.status === 'running');
  const stats = await Promise.all(running.map(c => api(`/containers/${enc(c.id)}/stats`).catch(() => ({}))));
  const mem = stats.reduce((a, s) => a + (s.memory_bytes || 0), 0);
  const quick = [['blog', '8081:8081'], ['runner', '8082:8082']].filter(([n]) => imgs.some(i => i.name === n));
  const recent = [...cs].sort((a, b) => String(b.created).localeCompare(String(a.created))).slice(0, 5);
  $('#view').innerHTML = `<div class="tiles">
    <div class="card"><div class="muted">Running</div><div class="big">${running.length}</div></div>
    <div class="card"><div class="muted">Stopped</div><div class="big">${cs.length - running.length}</div></div>
    <div class="card"><div class="muted">Images</div><div class="big">${imgs.length}</div></div>
    <div class="card"><div class="muted">Memory in use</div><div class="big">${bytes(mem)}</div></div></div>
    ${quick.length ? `<div class="card"><b>Quick start</b> ${quick.map(([n, p]) => `<button data-act="quick" data-img="${n}" data-port="${p}">Run ${n}</button>`).join(' ')}</div>` : ''}
    <h3>Recent containers</h3>${containerTable(recent)}`;
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

async function detail(id, tab) {
  const c = await api('/containers/' + enc(id));
  $('#title').innerHTML = `${esc(c.name)} <small class="muted">${dot(c.status)}</small>`;
  $('#actions').innerHTML = toggleBtn(c) + ` <button class="danger" data-act="delete" data-id="${esc(c.id)}" data-back="1">Delete</button>`;
  const tabs = ['overview', 'logs', 'stats', 'exec'].map(t =>
    `<a href="#/containers/${enc(id)}/${t}" class="${t === tab ? 'on' : ''}">${t[0].toUpperCase() + t.slice(1)}</a>`).join('');
  $('#view').innerHTML = `<div class="tabs">${tabs}</div><div id="pane"></div>`;
  const pane = $('#pane');
  const running = c.status === 'running';

  if (tab === 'logs') {
    pane.innerHTML = '<p><button data-act="reload">Refresh</button></p><pre id="log">Loading…</pre>';
    const load = async () => {
      const el = $('#log');
      if (!el) return;
      el.textContent = (await api(`/containers/${enc(id)}/logs`)).logs || '(no output)';
      el.scrollTop = el.scrollHeight;
    };
    await load();
    if (running) every(3000, () => load().catch(() => {}));
  } else if (tab === 'stats') {
    if (!running) { pane.innerHTML = '<div class="empty">Container is not running.</div>'; return; }
    hist = {mem: [], pid: []};
    const tick = async () => {
      const s = await api(`/containers/${enc(id)}/stats`);
      hist.mem.push(s.memory_bytes || 0); hist.pid.push(s.pids || 0);
      hist.mem = hist.mem.slice(-60); hist.pid = hist.pid.slice(-60);
      const el = $('#pane');
      if (el) el.innerHTML = `<div class="stats">
        ${statCard('Memory', s.memory_bytes, s.memory_limit_bytes, hist.mem, bytes)}
        ${statCard('PIDs', s.pids, s.pid_limit, hist.pid, n => n ?? '—')}
        <div class="card"><div class="muted">CPU limit</div><div class="big">${esc(s.cpu_limit || 'none')}</div>
        <div class="muted">quota / period (µs). Usage is not exposed by the API.</div></div></div>`;
    };
    await tick();
    every(2000, () => tick().catch(() => {}));
  } else if (tab === 'exec') {
    pane.innerHTML = running
      ? '<form class="exec" id="execform"><input id="cmd" placeholder="ls -la /" required autocomplete="off"><button class="primary" id="execgo">Run</button></form><pre id="out">Output appears here.</pre>'
      : '<div class="empty">Container is not running.</div>';
    const form = $('#execform');
    if (form) form.onsubmit = async e => {
      e.preventDefault();
      await busy($('#execgo'), 'Running…', async () => {
        try {
          const r = await api(`/containers/${enc(id)}/exec`, {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: ['/bin/sh', '-c', $('#cmd').value]})});
          $('#out').textContent = `$ ${$('#cmd').value}\n${r.stdout}${r.stderr}[exit ${r.code}]`;
        } catch (x) { toast(x.message); }
      });
    };
  } else {
    const rows = [['Status', dot(c.status)], ['ID', esc(c.id)], ['Image', esc(c.image || '—')], ['Created', esc(c.created || '—')],
      ['PID', esc(c.pid ?? '—')], ['Ports', portLinks(c)], ['Command', `<code>${esc((c.command || []).join(' ') || '—')}</code>`],
      ['Memory limit', esc(c.memory || 'none')], ['CPUs', esc(c.cpus || 'none')], ['PIDs limit', esc(c.pids || 'none')]];
    pane.innerHTML = `<div class="card"><dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></div>`;
  }
}

async function images() {
  $('#title').textContent = 'Images';
  $('#actions').innerHTML = '<button data-act="upload">Upload .tar</button> <button class="primary" data-act="build">Build from Vcfile</button>';
  const xs = await api('/images');
  $('#view').innerHTML = `<table><tr><th>Name</th><th>Size</th><th>Created</th><th>Command</th><th></th></tr>${xs.map(x => `<tr>
    <td>${esc(x.name)}</td><td>${bytes(x.size)}</td><td>${esc(x.created || '—')}</td><td><code>${esc((x.cmd || []).join(' '))}</code></td>
    <td class="act"><a href="/images/${enc(x.name)}/download" download="${esc(x.name)}.tar"><button>Download</button></a>
    <button class="danger" data-act="delimg" data-id="${esc(x.name)}">Delete</button></td></tr>`).join('')}</table>`;
}

async function route() {
  clearInterval(timer);
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
      await busy(b, 'Starting…', () => api('/containers', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({image: img, name: img, port})}));
      toast(img + ' started'); route();
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
(async function boot() {
  try {
    const h = await api('/health');
    $('#health').textContent = h.capabilities.cgroups_v2 ? '● limits available' : '● cgroups unavailable';
  } catch (e) {
    $('#banner').textContent = 'Backend unavailable: ' + e.message;
    $('#banner').classList.remove('hidden');
  }
  route();
})();

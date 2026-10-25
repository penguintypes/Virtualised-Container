const $=s=>document.querySelector(s); let cache=[];
async function api(path, options){const r=await fetch(path,options);let data=null;try{data=await r.json()}catch(e){}if(!r.ok)throw Error(data?.error||r.statusText);return data}
function toast(message){const x=document.createElement('div');x.className='toast';x.textContent=message;document.body.append(x);setTimeout(()=>x.remove(),3500)}
async function boot(){try{const h=await api('/health');$('#health').textContent=h.capabilities.cgroups_v2?'● limits available':'● cgroups unavailable';$('#banner').classList.add('hidden');show('containers')}catch(e){$('#banner').textContent='Backend unavailable: '+e.message;$('#banner').classList.remove('hidden')}}
async function show(kind){$('#title').textContent=kind[0].toUpperCase()+kind.slice(1);try{if(kind==='images'){const xs=await api('/images');$('#content').innerHTML='<table><tr><th>ID</th><th>Name</th><th>Created</th><th>Size</th><th></th></tr>'+xs.map(x=>`<tr><td>${x.id}</td><td>${x.name}</td><td>${x.created||'—'}</td><td>${x.size||0}</td><td><button onclick="deleteImage('${x.name}')">Delete</button></td></tr>`).join('')+'</table>'}else{cache=await api('/containers');render()}}catch(e){toast(e.message)}}
function render(){if(!cache.length){$('#content').innerHTML='<div class="empty">No containers yet.</div>';return}$('#content').innerHTML='<div class="grid">'+cache.map(c=>`<article class="card"><h3>${c.name} <span class="badge">${c.status}</span></h3><p>Image: <b>${c.image||'—'}</b><br>ID: <code>${c.id}</code><br>Ports: ${c.ports?.join(', ')||'—'}</p><div id="s-${c.id}">Memory — · PIDs —</div><p>${c.ports?.length?`<a target="_blank" href="http://localhost:${c.ports[0].split(':')[0]}">Open UI</a>`:''}</p><button onclick="${c.status==='running'?'stopC':'startC'}('${c.id}')">${c.status==='running'?'Stop':'Start'}</button> <button onclick="logsC('${c.id}')">Logs</button> <button onclick="deleteC('${c.id}')">Delete</button></article>`).join('')+'</div>';cache.filter(c=>c.status==='running').forEach(poll)}
async function poll(c){try{const s=await api('/containers/'+c.id+'/stats');const x=$('#s-'+c.id);if(x)x.textContent=`Memory ${s.memory_bytes||0} / ${s.memory_limit_bytes||'max'} · PIDs ${s.pids||0} / ${s.pid_limit||'max'}`}catch(e){}}
async function runModal(){const xs=await api('/images');$('#image').innerHTML=xs.map(x=>`<option>${x.name}</option>`).join('');run.showModal()}
async function runContainer(e){e.preventDefault();try{const command=$('#command').value.trim();const c=await api('/containers',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:$('#image').value,name:$('#name').value,command:command?['/bin/sh','-c',command]:undefined,memory:$('#memory').value||undefined,cpus:$('#cpus').value||undefined,pids:$('#pids').value||undefined,port:$('#port').value||undefined})});run.close();show('containers')}catch(x){toast(x.message)}}
async function startC(id){try{await api('/containers/'+id,{method:'POST'});show('containers')}catch(e){toast(e.message)}}
async function stopC(id){try{await api('/containers/'+id+'/stop',{method:'POST'});show('containers')}catch(e){toast(e.message)}}
async function deleteC(id){if(confirm('Delete this container?'))try{await api('/containers/'+id,{method:'DELETE'});show('containers')}catch(e){toast(e.message)}}
async function logsC(id){try{$('#logtext').textContent=(await api('/containers/'+id+'/logs')).logs;logs.showModal()}catch(e){toast(e.message)}}
async function deleteImage(name){if(confirm('Delete '+name+'?'))try{await api('/images/'+name,{method:'DELETE'});show('images')}catch(e){toast(e.message)}}
async function buildImage(){const file=prompt('Path to Vcfile inside this WSL project:','samples/blog/Vcfile');if(!file)return;try{await api('/images/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file, clean: confirm('Bypass cache (--clean)?'), update: confirm('Force base image update (--update)?')})});toast('Image built');show('images')}catch(e){toast(e.message)}}
boot();
async function quickRun(img, port) {
    try {
        await api('/containers', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({image: img, name: img, port: port})
        });
        toast(img + ' started');
        show('containers');
    } catch(e) { toast(e.message); }
}
async function quickRun(img, port) {
    try {
        await api('/containers', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({image: img, name: img, port: port})
        });
        toast(img + ' started');
        show('containers');
    } catch(e) { toast(e.message); }
}

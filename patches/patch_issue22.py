import re, os
api_path = "backend/api.py"
with open(api_path, "r") as f: 
    api = f.read()

boot_code = """
# --- Issue 22: Reconcile ghost containers on boot ---
try:
    import os, json
    if os.path.exists('var/engine.json'):
        with open('var/engine.json', 'r+') as f:
            db = json.load(f)
            changed = False
            for n, c in db.get('containers', {}).items():
                if c.get('status') == 'running' and not os.path.exists(f'/sys/fs/cgroup/vcontainer/{n}'):
                    c['status'] = 'stopped'
                    changed = True
            if changed:
                f.seek(0); f.truncate(); json.dump(db, f)
except Exception: pass
# ----------------------------------------------------
"""
if "Reconcile ghost containers" not in api:
    api = re.sub(r"(if __name__\s*==\s*['\"]__main__['\"]\:)", boot_code + r"\n\1", api)
    with open(api_path + ".bak", "w") as f: f.write(api)
    with open(api_path, "w") as f: f.write(api)
    print("Issue 22 Fixed: Boot reconciliation patched in backend/api.py")
else:
    print("Issue 22 already patched.")

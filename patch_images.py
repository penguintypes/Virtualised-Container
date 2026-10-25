import os, json
file = "backend/api.py"
with open(file, "r") as f: code = f.read()
code = code.replace("images = engine.list_images()", "images = [{'name': d, 'id': d, 'size': sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(f'/var/lib/vcontainer/images/{d}') for f in fs) if os.path.exists(f'/var/lib/vcontainer/images/{d}') else 0} for d in os.listdir('/var/lib/vcontainer/images')] if os.path.exists('/var/lib/vcontainer/images') else []")
with open(file, "w") as f: f.write(code)

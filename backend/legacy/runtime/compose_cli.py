import sys, json, urllib.request

def main():
    args = sys.argv[1:]
    if not args:
        sys.exit("Usage: vc compose <up|down|start|stop> <name> [--set KEY=VALUE]")
    action = args[0]
    if len(args) < 2:
        sys.exit("Error: missing stack name")
    name = args[1]
    
    try:
        urllib.request.urlopen("http://localhost:8080/health", timeout=2)
    except:
        sys.exit("Error: vcontainer server is down. Run ./start.sh first.")

    if action == "up":
        inputs = {}
        for i, arg in enumerate(args[2:]):
            if arg.startswith("--set="):
                k, v = arg[6:].split("=", 1)
                inputs[k] = v
            elif arg == "--set" and i+3 < len(args):
                k, v = args[i+3].split("=", 1)
                inputs[k] = v

        path = f"/var/lib/vcontainer/samples/{name}/vcompose.json"
        if not __import__("os").path.exists(path):
            path = f"./backend/samples/{name}/vcompose.json"
        with open(path) as f:
            template = json.load(f)
        
        for k, spec in template.get("inputs", {}).items():
            if k not in inputs and "generate" not in spec and "default" not in spec:
                inputs[k] = input(f"{spec.get('label', k)}: ")

        req = {"name": name, "template": template, "inputs": inputs}
        url = "http://localhost:8080/compose/up"
    else:
        req = {"name": name}
        url = f"http://localhost:8080/compose/{action}"

    req_data = json.dumps(req).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=req_data, method="POST")) as res:
            print(json.loads(res.read().decode())["message"])
    except urllib.error.HTTPError as e:
        sys.exit(f"Error: {e.read().decode()}")

if __name__ == "__main__":
    main()

import re
with open("backend/api.py", "r") as f: api = f.read()
if "memory is required" not in api:
    api = re.sub(r"(if parsed_path == ['\"]/containers['\"]:)", r"\1\n                if 'memory' not in body:\n                    return self.respond_with_json(400, {'error': 'memory is required'})", api)
    with open("backend/api.py", "w") as f: f.write(api)

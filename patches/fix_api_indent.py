with open('backend/api.py', 'r') as f:
    lines = f.readlines()

with open('backend/api.py', 'w') as f:
    for line in lines:
        if line.startswith("        if \"env\" in req_data"):
            # Also adding a dict check to prevent unhandled TypeErrors if array is passed
            f.write("            if isinstance(req_data, dict) and \"env\" in req_data and \"environment\" not in req_data:\n")
        elif line.startswith("            req_data[\"environment\"] = req_data[\"env\"]"):
            f.write("                req_data[\"environment\"] = req_data[\"env\"]\n")
        else:
            f.write(line)

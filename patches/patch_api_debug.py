with open('/home/ronnie/vcontainer/backend/api.py', 'r') as f:
    content = f.read()

if 'import traceback' not in content:
    content = content.replace('except Exception as e:\n            self.fail_out(e)',
                              'except Exception as e:\n            import traceback; traceback.print_exc()\n            self.fail_out(e)')

if 'req_data["environment"] = req_data["env"]' not in content:
    content = content.replace('req_data = json.loads(raw_data) if raw_data.strip() else {}',
                              'req_data = json.loads(raw_data) if raw_data.strip() else {}\n        if "env" in req_data and "environment" not in req_data:\n            req_data["environment"] = req_data["env"]')

with open('/home/ronnie/vcontainer/backend/api.py', 'w') as f:
    f.write(content)

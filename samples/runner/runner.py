import json, resource, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

class H(BaseHTTPRequestHandler):
 def send(self, value):
  raw=json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
 def do_GET(self):
  if self.path == '/': raw=Path('/opt/index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
  else: self.send({'error':'not found'})
 def do_POST(self):
  try:
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0)))); lang=data.get('language','python'); code=data.get('code',''); stdin=data.get('stdin','')
   commands={'python':['python3','-c',code],'node':['node','-e',code],'c':['sh','-c','cat >/tmp/main.c && gcc /tmp/main.c -o /tmp/main && /tmp/main']}
   def limit(): lang=='node' or resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024)); resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
   p=subprocess.run(commands.get(lang,commands['python']),input=(code if lang=='c' else stdin),text=True,capture_output=True,timeout=min(int(data.get('timeout',3)),10),preexec_fn=limit)
   self.send({'code':p.returncode,'stdout':p.stdout[:65536],'stderr':p.stderr[:65536]})
  except subprocess.TimeoutExpired: self.send({'code':124,'stdout':'','stderr':'timeout'})
  except Exception as e: self.send({'code':1,'stdout':'','stderr':str(e)})
 def log_message(self,*args): pass
HTTPServer(('0.0.0.0',8082),H).serve_forever()

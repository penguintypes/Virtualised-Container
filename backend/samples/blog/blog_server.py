import json, sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path('/var/lib/vcontainer/blog'); ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / 'comments.db'; sqlite3.connect(DB).execute('create table if not exists comments(post text, author text, body text)').connection.commit()
class H(BaseHTTPRequestHandler):
 def log_message(self, f, *a):
  if self.command != 'GET' or int(a[1]) >= 400: super().log_message(f, *a)
 def send(self, code, body, kind='text/html'):
  raw = body if isinstance(body, bytes) else body.encode(); self.send_response(code); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
 def do_GET(self):
  if self.path == '/': return self.send(200, Path('/opt/index.html').read_bytes())
  if self.path == '/B.png': return self.send(200, Path('/opt/B.png').read_bytes(), 'image/png')
  if self.path.startswith('/posts/'):
   name = Path(self.path[7:]).name + '.md'; file = ROOT / name
   return self.send(200, file.read_text() if file.exists() else '', 'text/plain')
  self.send(404, 'not found')
 def do_POST(self):
  try:
   data=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))))
   if self.path == '/posts': (ROOT / (Path(data['name']).name+'.md')).write_text(data['body']); return self.send(201, 'saved')
   if self.path == '/comments':
    with sqlite3.connect(DB) as db: db.execute('insert into comments values (?,?,?)',(data['post'],data['author'],data['body']))
    return self.send(201, 'saved')
  except Exception as error: return self.send(400, str(error))
  self.send(404, 'not found')

HTTPServer(('0.0.0.0',8081), H).serve_forever()

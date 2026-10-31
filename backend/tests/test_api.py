import json, unittest
from unittest.mock import patch
from http.client import HTTPConnection
from threading import Thread
from http.server import ThreadingHTTPServer
from backend.api import VcApiHandler

class Tests(unittest.TestCase):
 def test_health(self):
  with patch('backend.api.engine.capabilities', return_value={'namespaces':True}):
   server=ThreadingHTTPServer(('127.0.0.1',0),VcApiHandler); Thread(target=server.handle_request,daemon=True).start()
   c=HTTPConnection(*server.server_address); c.request('GET','/health'); r=c.getresponse(); data=json.loads(r.read()); server.server_close()
   self.assertTrue(data['ok'])
if __name__=='__main__': unittest.main()

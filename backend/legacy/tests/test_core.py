import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from backend import core, engine

class Tests(unittest.TestCase):
 def test_vcfile(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'Vcfile'; p.write_text('FROM alpine\nRUN apk add python3\nENV X=y\nCMD ["python3","/x"]\n')
   x=core.parse_vcfile(p); self.assertEqual(x['from'],'alpine'); self.assertEqual(x['run'][0],'apk add python3'); self.assertEqual(x['env']['X'],'y')
 def test_command(self):
  with patch('backend.engine._call', return_value='container x started') as call:
   with patch('backend.engine._load', return_value={}):
    engine.run('x','alpine',['/bin/sh'],pids='64')
   self.assertIn('--pids-max',call.call_args.args)
 def test_bad_copy(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'Vcfile'; p.write_text('COPY x relative\n')
   with self.assertRaises(ValueError): core.parse_vcfile(p)
if __name__=='__main__': unittest.main()

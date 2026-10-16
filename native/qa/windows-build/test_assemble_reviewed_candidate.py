import hashlib,importlib.util,json,tempfile,unittest,zipfile
from pathlib import Path
s=importlib.util.spec_from_file_location('assembly',Path(__file__).with_name('assemble-reviewed-candidate.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Assembly(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.archive=self.root/'original.zip';self.notices=self.root/'notices';self.notices.mkdir()
  with zipfile.ZipFile(self.archive,'w') as z:
   z.writestr('Flapart-Studio/bin/krita.exe',b'fixture executable');z.writestr('Flapart-Studio/bin/symsrv.yes',b'');z.writestr('Flapart-Studio/bin/dbghelp.dll',b'preserve diagnostic capability')
  rows=[]
  for name,raw in [('CREDITS.html',b'<html>credits</html>'),('credits.css',b'body{}')]:
   (self.notices/name).write_bytes(raw);rows.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
  self.manifest=self.notices/'notice-manifest.json';self.manifest.write_text(json.dumps({'files':rows}));self.pin=m.sha(self.archive);self.noticepin=m.sha(self.manifest)
 def run_assembly(self):return m.assemble(self.archive,self.pin,self.notices,self.noticepin,self.root/'output')
 def test_exact_change_set(self):
  result=self.run_assembly();self.assertEqual(m.sha(self.archive),self.pin);self.assertFalse(result['terms_accepted']);self.assertFalse(result['release_qualified'])
  with zipfile.ZipFile(self.root/'output/Flapart-Studio.zip') as z:
   self.assertNotIn('Flapart-Studio/bin/symsrv.yes',z.namelist());self.assertEqual(z.read('Flapart-Studio/bin/dbghelp.dll'),b'preserve diagnostic capability');self.assertEqual(z.read('Flapart-Studio/licenses/CREDITS.html'),b'<html>credits</html>')
  self.assertEqual(result['preserved_original_files'],2);self.assertEqual(result['added_notice_files'],2)
 def test_tampered_notice_refused_before_output(self):
  (self.notices/'credits.css').write_text('changed')
  with self.assertRaises(ValueError):self.run_assembly()
  self.assertFalse((self.root/'output').exists())
 def test_traversal_refused(self):
  with zipfile.ZipFile(self.archive,'a') as z:z.writestr('Flapart-Studio/../escape',b'no')
  self.pin=m.sha(self.archive)
  with self.assertRaises(ValueError):self.run_assembly()
  self.assertFalse((self.root/'output').exists())
 def test_windows_normalization_rejected(self):
  for name in ('Flapart-Studio/licenses/truncated.', 'Flapart-Studio/licenses/name ', 'Flapart-Studio/AUX.txt'):
   with self.subTest(name=name),self.assertRaises(ValueError):m.relative(name)
 def test_existing_output_preserved(self):
  out=self.root/'output';out.mkdir();(out/'sentinel').write_text('keep')
  with self.assertRaises(ValueError):self.run_assembly()
  self.assertEqual((out/'sentinel').read_text(),'keep')
if __name__=='__main__':unittest.main()

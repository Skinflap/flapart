"""Portable orchestration checks; synthetic commands never qualify native packages."""
import json
import ast
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import package_stage as stage

class PackageStage(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.out=self.base/'candidate';self.out.mkdir();self.root=self.out/'Flapart Studio.app';self.evidence=self.base/'evidence'
 def tearDown(self):self.temp.cleanup()
 def test_same_tree_explicit_tools_and_retention(self):
  for label in ('collector','completion','codesign','verify'):
   args=stage.stage_command(label,[sys.executable,'-c','pass'],self.root,self.evidence,tools=[sys.executable],retain=True,sdk=self.base/'sdk')
   self.assertIn('package='+str(self.root),args);self.assertIn(str(self.evidence/label),args)
   self.assertIn('sdk='+str(self.base/'sdk'),args);self.assertIn('--retain-native-bytes',args);self.assertIn('--tool',args)
   self.assertEqual(args[-4:],['--',sys.executable,'-c','pass'])
 def test_driver_verifier_names_and_bytecode_environment(self):
  source=Path(stage.__file__).with_name('package-candidate.py').read_text()
  tree=ast.parse(source)
  calls=[n.args[0].value for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='stage']
  self.assertEqual(calls,['collector','completion','codesign','verify'])
  self.assertIn("env['PYTHONDONTWRITEBYTECODE']='1'",source)
 def test_default_direct_command(self):
  self.assertEqual(stage.stage_command('x',['codesign','--verify'],self.root,None),['codesign','--verify'])
  with self.assertRaises(ValueError):stage.validate_evidence(self.out,None,True)
 def test_layout_refusals(self):
  for path in (self.out/'evidence',self.root/'evidence',self.base):
   with self.assertRaises(ValueError):stage.validate_evidence(self.out,path,False)
  self.evidence.mkdir()
  with self.assertRaises(ValueError):stage.validate_evidence(self.out,self.evidence,False)
 def test_actual_recorder_success_and_failure(self):
  stage.validate_evidence(self.out,self.evidence,False)
  stage.run_stage('stage01-create',[sys.executable,'-c',"from pathlib import Path;p=Path(__import__('sys').argv[1]);p.mkdir();(p/'fixture.txt').write_text('fixture')",str(self.root)],self.root,self.evidence)
  first=json.loads((self.evidence/'stage01-create/receipt.json').read_text())
  self.assertTrue(first['passed']);self.assertFalse(first['release_qualified'])
  self.assertFalse(first['before']['package']['exists']);self.assertTrue(first['after']['package']['exists'])
  with self.assertRaises(subprocess.CalledProcessError):stage.run_stage('stage02-fail',[sys.executable,'-c','raise SystemExit(7)'],self.root,self.evidence)
  failed=json.loads((self.evidence/'stage02-fail/receipt.json').read_text());self.assertFalse(failed['passed']);self.assertEqual(failed['returncode'],7)
 def test_collector_rename_and_plist_in_same_command(self):
  source=self.base/'source';prefix=self.base/'sdk';prefix.mkdir()
  def fake(cmd,check):
   self.assertIn(str(source/'packaging/macos/macos-deploy.py'),cmd)
   app=self.out/'krita.app';(app/'Contents/MacOS').mkdir(parents=True)
   (app/'Contents/MacOS/krita').write_bytes(b'not native')
   (app/'Contents/Info.plist').write_bytes(plistlib.dumps({'Existing':'kept'}))
  with patch.object(stage.subprocess,'run',side_effect=fake):stage.collect(source,prefix,self.out)
  info=plistlib.loads((self.root/'Contents/Info.plist').read_bytes())
  self.assertEqual(info['CFBundleIdentifier'],'com.flaptown.flapart-native');self.assertEqual(info['Existing'],'kept')
 def test_collector_sdk_mutation_refused(self):
  prefix=self.base/'sdk';prefix.mkdir();(prefix/'keep').write_text('original')
  def mutate(*args,**kwargs):(prefix/'keep').write_text('modified')
  with patch.object(stage.subprocess,'run',side_effect=mutate), self.assertRaisesRegex(ValueError,'changed SDK'):
   stage.collect(self.base/'source',prefix,self.out)
 def test_missing_tool_refused_before_command(self):
  with self.assertRaises(ValueError):stage.stage_command('x',['anything'],self.root,self.evidence,tools=['definitely-absent-flapart-tool'],env={'PATH':''})

if __name__=='__main__':unittest.main()

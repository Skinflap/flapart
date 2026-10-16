import contextlib,io,unittest
from unittest.mock import Mock,patch
from pathlib import Path
import coordinator_cli as cli
import protocol as p
import test_candidate_runner as fixtures

class CoordinatorCliTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.CandidateAdmissionTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  f=self.fixture;self.base=f.base;self.binding=f.request['binding'];self.bpath=self.base/'independent-binding.json';self.bpath.write_bytes(p.encode(self.binding))
  self.argv=['coordinate','--binding',str(self.bpath),'--artifact-id','40','--chain-sha256',f.chainsha,'--recovered-root',str(f.root),'--original-manifest',str(f.manifest),'--output',str(self.base/'exchange')]
  self.delegate=Mock();self.delegate.operator_id.return_value=self.binding['operator_id'];self.factory=Mock(return_value=self.delegate)
 def test_exact_coordinate_wiring_without_network(self):
  with patch.object(cli.full,'coordinate',return_value={'ready':True,'release_id':60}) as coordinate:
   value=cli.execute(cli.parser().parse_args(self.argv),self.factory)
  a=coordinate.call_args.args
  self.assertEqual(a[:7],(self.binding,40,self.fixture.root,self.fixture.manifest,self.fixture.chainsha,self.base/'exchange',a[6]));self.assertIsInstance(a[6],cli.CheckedAdapter)
  self.assertTrue(value['ready']);self.assertFalse(value['native_executed']);self.assertFalse(value['release_qualified']);self.delegate.create.assert_not_called()
 def test_invalid_local_pins_before_adapter_creation(self):
  for filename in ('candidate.zip','candidate-inventory.json','chain-manifest.json'):
   with self.subTest(filename=filename):
    path=self.fixture.root/filename;original=path.read_bytes();path.write_bytes(original+b'changed')
    try:
     with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(self.argv),self.factory)
    finally:path.write_bytes(original)
  self.factory.assert_not_called()
 def test_manifest_pin_before_adapter_creation(self):
  self.fixture.manifest.write_bytes(b'{}')
  with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(self.argv),self.factory)
  self.factory.assert_not_called()
 def test_invalid_binding_chain_and_artifact_before_adapter(self):
  for option,value in (('--artifact-id','0'),('--chain-sha256','bad')):
   args=self.argv.copy();args[args.index(option)+1]=value
   with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(args),self.factory)
  self.binding['attempt']=0;self.bpath.write_bytes(p.encode(self.binding))
  with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(self.argv),self.factory)
  self.factory.assert_not_called()
 def test_overlap_and_symlink_refused(self):
  for output in (self.fixture.root/'nested',self.fixture.root):
   args=self.argv.copy();args[-1]=str(output)
   with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(args),self.factory)
  link=self.base/'linked';link.symlink_to(self.fixture.root,target_is_directory=True);args=self.argv.copy();args[args.index('--recovered-root')+1]=str(link)
  with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(args),self.factory)
  self.factory.assert_not_called()
 def test_wrong_operator_no_coordinate(self):
  self.delegate.operator_id.return_value=999999
  with patch.object(cli.full,'coordinate') as coordinate:
   with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(self.argv),self.factory)
  coordinate.assert_not_called();self.delegate.create.assert_not_called()
 def test_identity_rechecked_before_each_mutation(self):
  wrapper=cli.CheckedAdapter(self.delegate,self.binding['operator_id'])
  for method,args in (('create',('repo',{})),('upload',('repo',60,'tag',Path('file'))),('delete',('repo',60))):
   getattr(wrapper,method)(*args);getattr(self.delegate,method).assert_called_once_with(*args)
   self.delegate.operator_id.return_value=999999
   with self.assertRaises(ValueError):getattr(wrapper,method)(*args)
   self.assertEqual(getattr(self.delegate,method).call_count,1);self.delegate.operator_id.return_value=self.binding['operator_id']
 def test_exact_receipt_cleanup_and_wrong_pin_no_adapter(self):
  receipt=self.base/'receipt.json';receipt.write_bytes(p.encode({'schema':1,'kind':'full-chain-coordinator','binding':self.binding,'artifact_id':40,'chain_manifest_sha256':self.fixture.chainsha,'cleanup_complete':False}))
  argv=['cleanup','--binding',str(self.bpath),'--artifact-id','40','--chain-sha256',self.fixture.chainsha,'--receipt',str(receipt)]
  with patch.object(cli.full,'cleanup',return_value={'ready':True,'cleanup_complete':True,'release_id':60}) as cleanup:
   result=cli.execute(cli.parser().parse_args(argv),self.factory)
  self.assertEqual(cleanup.call_args.args[:4],(self.binding,40,self.fixture.chainsha,receipt));self.assertTrue(result['cleanup_complete'])
  self.factory.reset_mock();argv[argv.index('--chain-sha256')+1]='f'*64
  with self.assertRaises(ValueError):cli.execute(cli.parser().parse_args(argv),self.factory)
  self.factory.assert_not_called()
 def test_cli_errors_redacted_no_private_key_argument(self):
  for args in (['--private-key','SECRET-PATH'],['coordinate','--artifact-id','SECRET-TOKEN']):
   stdout=io.StringIO();stderr=io.StringIO()
   with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):code=cli.main(args,self.factory)
   self.assertEqual(code,1);self.assertNotIn('SECRET',stderr.getvalue());self.assertEqual(stdout.getvalue(),'')
  self.factory.assert_not_called()
 def test_failure_diagnostics_redacted(self):
  with patch.object(cli.full,'coordinate',side_effect=ValueError('PRIVATE-DIAGNOSTIC')),contextlib.redirect_stderr(io.StringIO()) as errors:
   self.assertEqual(cli.main(self.argv,self.factory),1)
  self.assertNotIn('PRIVATE-DIAGNOSTIC',errors.getvalue())

if __name__=='__main__':unittest.main()

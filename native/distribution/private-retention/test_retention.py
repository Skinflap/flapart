import importlib.util
import json
import io
import tarfile
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('retain', Path(__file__).with_name('retain.py'))
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)

class Retention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); cls.base = Path(cls.tmp.name)
        cls.home = cls.base / 'keys'; cls.home.mkdir(mode=0o700)
        r.gpg(cls.home, '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key',
              'Disposable retention fixture', 'rsa2048', 'encr', '1d')
        listing = r.gpg(cls.home, '--with-colons', '--list-keys').stdout.decode()
        cls.fpr = next(x.split(':')[9] for x in listing.splitlines() if x.startswith('fpr:'))
        cls.pub = cls.base / 'public.asc'; cls.pub.write_bytes(r.gpg(cls.home, '--armor', '--export', cls.fpr).stdout)
    @classmethod
    def tearDownClass(cls):
        subprocess.run(['gpgconf', '--homedir', str(cls.home), '--kill', 'gpg-agent'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.tmp.cleanup()
    def setUp(self):
        self.case = tempfile.TemporaryDirectory(dir=self.base); self.root = Path(self.case.name)
        (self.root / 'candidate.zip').write_bytes(b'candidate fixture')
        (self.root / 'stage.json').write_text('{"qualification":false}')
        self.inventory = {'schema':1, 'candidate':'candidate.zip', 'files':[{'path':p, 'bytes':(self.root/p).stat().st_size,'sha256':r.digest(self.root/p)} for p in ('candidate.zip','stage.json')]}
        self.manifest = self.root / 'input.json'; self.manifest.write_text(json.dumps(self.inventory))
    def tearDown(self): self.case.cleanup()
    def encrypt(self):
        out = self.root / 'private.gpg'
        result = r.encrypt(self.root,self.manifest,self.pub,self.fpr,out)
        return out,result
    def test_roundtrip_private_files(self):
        encrypted, result = self.encrypt(); out = self.root/'recovered'
        receipt = r.decrypt(encrypted,result['encrypted_sha256'],self.home,self.fpr,out)
        self.assertFalse(receipt['release_qualified'])
        for name in ('candidate.zip','stage.json'): self.assertEqual((out/name).read_bytes(),(self.root/name).read_bytes())
        self.assertEqual(out.stat().st_mode & 0o777,0o700)
        self.assertEqual(encrypted.stat().st_mode & 0o777,0o600)
    def test_deep_payload_path_uses_short_private_key_home(self):
        parent = self.root / ('deep-' + 'x' * 110)
        parent.mkdir()
        encrypted = parent / 'private.gpg'
        with r.ephemeral_gpg_home() as home:
            self.assertLess(len(str(home / 'S.keyboxd').encode()), 90)
            self.assertEqual(home.stat().st_mode & 0o777, 0o700)
        self.assertFalse(home.exists())
        result = r.encrypt(self.root,self.manifest,self.pub,self.fpr,encrypted)
        recovered = parent / 'recovered'
        r.decrypt(encrypted,result['encrypted_sha256'],self.home,self.fpr,recovered)
        self.assertEqual((recovered/'candidate.zip').read_bytes(),b'candidate fixture')
    def test_wrong_fingerprint(self):
        with self.assertRaises(ValueError): r.encrypt(self.root,self.manifest,self.pub,'0'*40,self.root/'bad.gpg')
        self.assertFalse((self.root/'bad.gpg').exists())
    def test_mismatch_missing_and_symlink(self):
        for kind in ('changed','missing','symlink'):
            with self.subTest(kind=kind):
                path = self.root/'candidate.zip'
                if path.exists() or path.is_symlink(): path.unlink()
                if kind=='changed': path.write_bytes(b'changed')
                if kind=='symlink': path.symlink_to(self.root/'stage.json')
                with self.assertRaises(ValueError): self.encrypt()
                self.assertFalse((self.root/'private.gpg').exists())
    def test_corrupt_and_wrong_recipient_decrypt(self):
        encrypted,result=self.encrypt()
        with self.assertRaises(ValueError): r.decrypt(encrypted,'0'*64,self.home,self.fpr,self.root/'bad')
        with self.assertRaises(ValueError): r.decrypt(encrypted,result['encrypted_sha256'],self.home,'0'*40,self.root/'bad')
        raw=bytearray(encrypted.read_bytes());raw[len(raw)//2]^=1;encrypted.write_bytes(raw)
        with self.assertRaises(ValueError): r.decrypt(encrypted,r.digest(encrypted),self.home,self.fpr,self.root/'bad')
        self.assertFalse((self.root/'bad').exists())
    def test_inventory_refusal(self):
        for name in ('../escape','/absolute','a\\b','a/./b','inventory.json'):
            with self.subTest(name=name), self.assertRaises(ValueError): r.safe_name(name)
        dup=json.loads(json.dumps(self.inventory));dup['files'].append(dup['files'][0])
        with self.assertRaises(ValueError): r.validate_inventory(dup)
    def test_authenticated_unsafe_tar_refused(self):
        for kind in ('traversal', 'symlink', 'extra', 'duplicate', 'wronghash'):
            with self.subTest(kind=kind):
                payload=self.root/'malicious.tar'
                with tarfile.open(payload,'w') as tar:
                    def add(name,data):
                        member=tarfile.TarInfo(name);member.size=len(data);tar.addfile(member,io.BytesIO(data))
                    add('inventory.json',json.dumps(self.inventory).encode())
                    for row in self.inventory['files']:
                        add(row['path'],b'x'*row['bytes'] if kind=='wronghash' else (self.root/row['path']).read_bytes())
                    if kind=='traversal': add('../escape',b'bad')
                    if kind=='extra': add('unlisted',b'bad')
                    if kind=='duplicate': add('stage.json',b'bad')
                    if kind=='symlink':
                        member=tarfile.TarInfo('link');member.type=tarfile.SYMTYPE;member.linkname='../escape';tar.addfile(member)
                encrypted=self.root/'malicious.gpg'
                if encrypted.exists(): encrypted.unlink()
                r.gpg(self.home,'--trust-model','always','--recipient',self.fpr,'--output',str(encrypted),'--encrypt',str(payload))
                with self.assertRaises(ValueError): r.decrypt(encrypted,r.digest(encrypted),self.home,self.fpr,self.root/'bad')
                self.assertFalse((self.root/'bad').exists())
                self.assertFalse((self.root.parent/'escape').exists())

    def test_outputs_never_overwritten(self):
        encrypted,result=self.encrypt()
        with self.assertRaises(ValueError): self.encrypt()
        out=self.root/'existing';out.mkdir();(out/'keep').write_text('keep')
        with self.assertRaises(ValueError): r.decrypt(encrypted,result['encrypted_sha256'],self.home,self.fpr,out)
        self.assertEqual((out/'keep').read_text(),'keep')

if __name__=='__main__': unittest.main()

import sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,'/home/skinflap/Projects/Flaptown/accounts/issuer')
from session_issuer import create_session_fixture,COOKIE
from flapsoft_routes import register,install,files_checked
from flask import session
import secrets
O='https://identity.example'; W='https://flaptown.com'
class FlapsoftTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.app=create_session_fixture(Path(self.tmp.name)/'db',b'x'*32); self.s=self.app.fixture_store; install(self.s.db)
  self.s.db.execute("INSERT INTO principals VALUES('p',1),('q',1)")
  for principal in ('p','q'):
   self.s.db.execute('INSERT INTO lifecycle_state VALUES(?,?,?)',(principal,1,json.dumps({'active':True,'verified':True,'deleted':False})))
  def csrf(): session.setdefault('csrf',secrets.token_urlsafe(32)); return session['csrf']
  from flask import request
  register(self.app,self.app.fixture_request_store,lambda:request.cookies.get(COOKIE,''),csrf,O,lambda *a:True)
  self.c=self.app.test_client();self.a=self.app.test_client();self.q=self.app.test_client()
  self.c.set_cookie(COOKIE,self.s._session('p',1,method='google'),domain='identity.example');self.q.set_cookie(COOKIE,self.s._session('q',1,method='google'),domain='identity.example')
 def tearDown(self): self.s.close();self.tmp.cleanup()
 def get(self,p,c=None): return (c or self.c).get('/flapsoft'+p,base_url=O,headers={'Origin':W})
 def post(self,p,d,c=None):
  c=c or self.c; token=self.get('/session',c).json['csrf'];return c.post('/flapsoft'+p,base_url=O,headers={'Origin':W,'X-CSRF-Token':token},json=d)
 def create(self):
  r=self.post('/projects',{'name':'hello','description':'test','license':'MIT','files':{'README.md':'hello'}});self.assertEqual(r.status_code,201,r.data);return r.json
 def test_private_auth_revision_download(self):
  r=self.create();p='/projects/'+r['id'];self.assertEqual(self.get(p,self.a).status_code,404);self.assertEqual(self.get(p,self.q).status_code,404)
  self.assertEqual(self.post(p+'/save',{'revision':0,'files':{'a.py':'x'},'message':'x'}).status_code,409)
  self.assertEqual(self.post(p+'/save',{'revision':1,'files':{'a.py':'print(1)'},'message':'next'}).status_code,200)
  self.assertEqual(self.get(p).json['files'],{'a.py':'print(1)'});self.assertEqual(self.get(p+'?version=1').json['files'],{'README.md':'hello'})
  self.assertEqual(self.get(p+'/download').mimetype,'application/zip')
 def test_publish_fork_withdraw_disabled(self):
  r=self.create();p='/projects/'+r['id'];self.post(p+'/visibility',{'revision':1,'public':True});self.assertEqual(self.get(p,self.a).status_code,200)
  f=self.post(p+'/fork',{'revision':2},self.q);self.assertEqual(f.status_code,201);self.assertEqual(f.json['parent'],r['id']);self.assertFalse(f.json['public'])
  self.post(p+'/visibility',{'revision':2,'public':False});self.assertEqual(self.get(p+'/download',self.a).status_code,404)
  self.post(p+'/visibility',{'revision':3,'public':True});self.s.db.execute("UPDATE principals SET enabled=0 WHERE id='p'");self.assertEqual(self.get(p,self.a).status_code,404)
 def test_csrf_origin_ownership(self):
  r=self.create();p='/projects/'+r['id'];self.assertEqual(self.c.post('/flapsoft'+p+'/delete',base_url=O,json={'revision':1}).status_code,403)
  self.assertEqual(self.post(p+'/delete',{'revision':1},self.q).status_code,404)
  self.assertEqual(self.c.get('/flapsoft/session',base_url=O,headers={'Origin':'https://evil.example'}).status_code,403)
  self.assertEqual(self.post('/projects',{'name':'anon'},self.a).status_code,401)
 def test_paths_limits_xss_remains_text(self):
  for files in ({'../x':'oops'},{'/x':'oops'},{'.git/config':'oops'},{'a':'x\0'},{}):
   with self.assertRaises(ValueError): files_checked(files)
  r=self.create();p='/projects/'+r['id'];html='<script>alert(1)</script>';self.post(p+'/save',{'revision':1,'files':{'x.html':html},'message':'inert source'});self.assertEqual(self.get(p).json['files']['x.html'],html)
 def test_discussion_and_delete_cascade(self):
  r=self.create();p='/projects/'+r['id'];self.post(p+'/visibility',{'revision':1,'public':True});i=self.post(p+'/issues',{'title':'idea','body':'make it nice'},self.q);self.assertEqual(i.status_code,201);ip='/issues/'+i.json['id']
  self.assertEqual(self.post(ip+'/comment',{'body':'thanks'}).status_code,200);self.assertEqual(len(self.get(ip).json['comments']),1)
  self.assertEqual(self.post(ip+'/close',{'closed':True}).status_code,200);self.assertTrue(self.get(ip).json['closed'])
  self.post(p+'/delete',{'revision':2});self.assertEqual(self.get(ip).status_code,404);self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapsoft_versions').fetchone()[0],0)
 def test_archive_collisions_and_hostile_inputs(self):
  for files in ({'FLAPSOFT-PROVENANCE.json':'x'},{'a':'x','A':'x'},{'folder':'x','folder/a':'x'},{'CON.txt':'x'},{'x.':'x'},{'x':'\ud800'}):
   with self.assertRaises(ValueError): files_checked(files)
  self.assertEqual(self.post('/projects',{'name':'a','license':[]}).status_code,400)
  r=self.create();self.assertEqual(self.get('/projects/'+r['id']+'?version='+'9'*1000).status_code,400)
 def test_publication_conflict_moderation_and_export(self):
  r=self.create();p='/projects/'+r['id'];self.post(p+'/visibility',{'revision':1,'public':True});self.post(p+'/visibility',{'revision':2,'public':False})
  self.assertEqual(self.post(p+'/visibility',{'revision':1,'public':True}).status_code,409)
  self.post(p+'/visibility',{'revision':3,'public':True});self.s.db.execute("INSERT INTO account_admins VALUES('q')")
  self.assertEqual(self.post(p+'/report',{'reason':'review'},self.q).status_code,200)
  self.assertEqual(len(self.get('/moderation',self.q).json['reports']),1)
  self.assertEqual(self.post(p+'/moderate',{'action':'restrict','reason':'test'},self.q).status_code,200)
  self.assertEqual(self.get(p,self.a).status_code,404)
  self.assertEqual(self.post(p+'/save',{'revision':4,'files':{'a':'b'},'message':'x'}).status_code,403)
  self.assertEqual(self.post(p+'/visibility',{'revision':4,'public':False}).status_code,200)
  from flapsoft_routes import export
  self.assertEqual(len(export(self.s,'p')['projects']),1)
 def test_public_release_download_range_and_manifest_boundaries(self):
  import os,hashlib
  from unittest.mock import patch
  root=Path(self.tmp.name)/'releases';root.mkdir();artifact=root/'Flapart.zip';artifact.write_bytes(b'PK-test-artifact')
  manifest={'files':{'Flapart.zip':{'size':artifact.stat().st_size,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}}}
  (root/'manifest.json').write_text(json.dumps(manifest))
  with patch.dict(os.environ,{'FLAPTOWN_FLAPSOFT_RELEASES':str(root)}):
   response=self.get('/downloads/Flapart.zip',self.a);self.assertEqual(response.status_code,200);self.assertEqual(response.data,b'PK-test-artifact');self.assertIn('attachment',response.headers['Content-Disposition'])
   ranged=self.a.get('/flapsoft/downloads/Flapart.zip',base_url=O,headers={'Range':'bytes=0-1'});self.assertEqual(ranged.status_code,206);self.assertEqual(ranged.data,b'PK')
   self.assertEqual(self.get('/downloads/unknown.zip',self.a).status_code,404)
   for broken in ([],{'files':[]},{'files':{'Flapart.zip':{'size':2,'sha256':'x'}}}):
    (root/'manifest.json').write_text(json.dumps(broken));self.assertEqual(self.get('/downloads/Flapart.zip',self.a).status_code,404)
if __name__=='__main__':unittest.main()

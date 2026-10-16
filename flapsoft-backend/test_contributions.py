from test_flapsoft import FlapsoftTest,O,W
from flapsoft_routes import export,install,validate
import sqlite3,unittest,json

class ContributionsTest(FlapsoftTest):
 def setup_fork(self):
  original=self.create();pid=original['id'];self.post('/projects/'+pid+'/visibility',{'revision':1,'public':True})
  fork=self.post('/projects/'+pid+'/fork',{'revision':2},self.q).json['id']
  self.post('/projects/'+fork+'/save',{'revision':1,'files':{'README.md':'improved','new.html':'<script>throw 1</script>'},'message':'Improvement'},self.q)
  return pid,fork
 def suggest(self,fork):
  response=self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'Make it clearer','body':'Readable instructions'},self.q)
  self.assertEqual(response.status_code,201,response.data);return response.json['id']
 def test_accept_frozen_comparison_immutable_version(self):
  pid,fork=self.setup_fork();sid=self.suggest(fork);path='/suggestions/'+sid
  review=self.get(path).json;self.assertTrue(review['can_review']);self.assertEqual(review['base_revision'],2);self.assertEqual(len(review['changes']),2)
  self.assertEqual(self.get('/projects/'+fork).status_code,404)
  self.post('/projects/'+fork+'/save',{'revision':2,'files':{'other':'not proposed'},'message':'later'},self.q)
  self.assertEqual(self.post(path+'/accept',{'revision':2}).status_code,200)
  self.assertEqual(self.get('/projects/'+pid).json['files']['README.md'],'improved')
  self.assertEqual(self.get('/projects/'+pid+'?version=2').json['files'],{'README.md':'hello'})
  self.assertEqual(self.post(path+'/accept',{'revision':3}).status_code,409)
  self.assertEqual(self.post(path+'/withdraw',{},self.q).status_code,409)
 def test_conflict_decline_duplicate_and_no_diff(self):
  pid,fork=self.setup_fork();sid=self.suggest(fork)
  self.assertEqual(self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'duplicate'},self.q).status_code,409)
  self.post('/projects/'+pid+'/save',{'revision':2,'files':{'README.md':'owner changed'},'message':'own work'})
  self.assertTrue(self.get('/suggestions/'+sid).json['conflict'])
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':3}).status_code,409)
  self.assertEqual(self.post('/suggestions/'+sid+'/decline',{}).status_code,200)
  self.assertEqual(self.get('/projects/'+pid).json['files'],{'README.md':'owner changed'})
  self.assertEqual(self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'stale'},self.q).status_code,409)
  fresh=self.post('/projects/'+pid+'/fork',{'revision':3},self.q).json['id']
  self.assertEqual(self.post('/projects/'+fresh+'/suggest',{'revision':1,'title':'unchanged'},self.q).status_code,400)
 def test_auth_csrf_lifecycle_withdraw_and_export(self):
  pid,fork=self.setup_fork();sid=self.suggest(fork);path='/suggestions/'+sid
  self.assertEqual(self.get(path,self.a).status_code,404)
  self.assertEqual(self.post(path+'/accept',{'revision':2},self.q).status_code,403)
  self.assertEqual(self.c.post('/flapsoft'+path+'/accept',base_url=O,json={'revision':2},headers={'Origin':W}).status_code,403)
  self.assertEqual(len(export(self.s,'p')['received_suggestions']),1);self.assertEqual(len(export(self.s,'q')['received_suggestions']),0);self.assertEqual(len(export(self.s,'q')['suggestions']),1);self.assertEqual(len(export(self.s,'q')['fork_bases']),1)
  self.s.db.execute("UPDATE principals SET enabled=0 WHERE id='q'");self.assertEqual(self.get(path).status_code,404);self.assertEqual(self.post(path+'/accept',{'revision':2}).status_code,404)
  self.s.db.execute("UPDATE principals SET enabled=1 WHERE id='q'")
  self.post('/projects/'+pid+'/visibility',{'revision':2,'public':False});self.assertEqual(self.get(path,self.q).status_code,404)
  self.s.db.execute("INSERT INTO flapsoft_restrictions VALUES('q',1,'test')")
  self.assertEqual(self.post(path+'/withdraw',{},self.q).status_code,200);self.assertEqual(self.get(path).status_code,404)
 def test_delete_author_cascades_suggestion_accepted_recipient_retained(self):
  pid,fork=self.setup_fork();sid=self.suggest(fork);self.post('/suggestions/'+sid+'/accept',{'revision':2})
  token=self.q.get('/session',base_url=O).json['csrf']
  response=self.q.post('/account/delete',base_url=O,headers={'Origin':O,'X-CSRF-Token':token},json={'confirmation':'DELETE'});self.assertEqual(response.status_code,200,response.data)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapsoft_suggestions').fetchone()[0],0)
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapsoft_fork_bases').fetchone()[0],0)
  self.assertEqual(self.get('/projects/'+pid).json['files']['README.md'],'improved')
  self.assertEqual(self.get('/projects/'+pid).json['accepted_from']['fork'],fork)
  self.assertEqual(len(export(self.s,'p')['accepted_changes']),1)
 def test_quota_and_legacy_fork(self):
  from unittest.mock import patch
  pid,fork=self.setup_fork()
  with patch('flapsoft_routes.QUOTA',1):self.assertEqual(self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'large'},self.q).status_code,413)
  sid=self.suggest(fork)
  with patch('flapsoft_routes.QUOTA',1):self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':2}).status_code,413)
  self.assertEqual(self.get('/suggestions/'+sid).json['state'],'open')
  self.post('/suggestions/'+sid+'/withdraw',{},self.q)
  self.s.db.execute('DELETE FROM flapsoft_fork_bases WHERE fork=?',(fork,))
  self.assertEqual(self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'untrusted base'},self.q).status_code,409)
 def test_private_suggestions_do_not_leak_to_other_members(self):
  from session_issuer import COOKIE
  self.s.db.execute("INSERT INTO principals VALUES('third',1)");self.s.db.execute('INSERT INTO lifecycle_state VALUES(?,?,?)',('third',1,json.dumps({'active':True,'verified':True,'deleted':False})))
  other=self.app.test_client();other.set_cookie(COOKIE,self.s._session('third',1,method='google'),domain='identity.example')
  pid,fork=self.setup_fork();sid=self.suggest(fork)
  self.assertEqual(self.get('/suggestions/'+sid,other).status_code,404)
  self.assertEqual(self.get('/projects/'+pid+'/suggestions',other).json,{'suggestions':[]})
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':2},other).status_code,404)
  self.assertEqual(self.post('/projects/'+fork+'/suggest',{'revision':2,'title':'stolen'},other).status_code,404)
  self.s.db.execute('UPDATE lifecycle_state SET snapshot=? WHERE principal=?',(json.dumps({'active':True,'verified':False,'deleted':False}),'q'))
  self.assertEqual(self.get('/suggestions/'+sid).status_code,404)
  self.assertEqual(export(self.s,'p')['received_suggestions'],[])
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':2}).status_code,404)
  self.assertEqual(self.get('/projects/'+pid+'/suggestions').json,{'suggestions':[]})
 def test_restricted_upstream_and_revision_guards(self):
  pid,fork=self.setup_fork();sid=self.suggest(fork)
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':1}).status_code,409)
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':True}).status_code,409)
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':'2'}).status_code,409)
  self.s.db.execute("INSERT INTO flapsoft_restrictions VALUES('p',1,'test')")
  self.assertEqual(self.get('/suggestions/'+sid,self.q).status_code,404)
  self.assertEqual(self.post('/suggestions/'+sid+'/accept',{'revision':2}).status_code,403)
  self.assertEqual(self.post('/suggestions/'+sid+'/withdraw',{},self.q).status_code,200)
  self.assertEqual(self.get('/projects/'+pid).json['revision'],2)
 def test_additive_migration_preserves_existing_tables(self):
  self.create();before=[tuple(r) for r in self.s.db.execute('SELECT * FROM flapsoft_projects')]
  self.s.db.execute('DROP TABLE flapsoft_suggestions');self.s.db.execute('DROP TABLE flapsoft_fork_bases')
  with self.assertRaises(ValueError):validate(self.s.db)
  install(self.s.db);validate(self.s.db);self.assertEqual(before,[tuple(r) for r in self.s.db.execute('SELECT * FROM flapsoft_projects')])

def load_tests(loader,tests,pattern):
 return unittest.TestSuite(ContributionsTest(name) for name in ContributionsTest.__dict__ if name.startswith('test_'))

if __name__=='__main__':unittest.main()

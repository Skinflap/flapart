import base64,binascii,json,struct,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
from session_issuer import create_session_fixture,COOKIE
from account_lifecycle import publish,suspend
from flapart_store import install,png_clean,chunk,Repository,Quota
from public_catalog import PublicCatalog
ORIGIN='https://identity.example';WEB='https://flaptown.com'
def png(width=2,height=2,metadata=True):
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))
    if metadata:data+=chunk(b'tEXt',b'Secret\0private metadata')
    data+=chunk(b'IDAT',zlib.compress((b'\0'+b'\xff\x00\x00\xff'*width)*height))+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(data).decode()
class ArtTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'db'
        bootstrap=create_session_fixture(self.db,b'x'*32);self.s=bootstrap.fixture_store
        self.s.db.executescript("INSERT INTO principals VALUES('p',1),('q',1),('owner',1);INSERT INTO account_admins VALUES('owner');")
        for p in ('p','q','owner'):publish(self.s,p,verified=True)
        install(self.s.db)
        self.app=create_session_fixture(self.db,b'x'*32,flapart_enabled=True)
        self.clients={}
        for p in ('p','q','owner'):
            c=self.app.test_client();c.set_cookie(COOKIE,self.s._session(p,1,method='google'),domain='identity.example');self.clients[p]=c
        self.clients['anon']=self.app.test_client()
    def tearDown(self):self.app.fixture_store.close();self.s.close();self.tmp.cleanup()
    def get(self,path,p='p'):return self.clients[p].get(path,base_url=ORIGIN,headers={'Origin':WEB})
    def post(self,path,data,p='p'):
        token=self.get('/flapart/session',p).json['csrf']
        return self.clients[p].post(path,base_url=ORIGIN,headers={'Origin':WEB,'X-CSRF-Token':token},json=data)
    def create(self):
        r=self.post('/flapart/projects',{'title':'Artwork','project':{'layers':[{'name':'Private sketch'}]}});self.assertEqual(r.status_code,201,r.data);return r.json
    def pub(self,r,profile=True):
        response=self.post('/flapart/projects/'+r['id']+'/publish',dict(expectedRevision=r['revision'],png=png(),title='Public painting',description='Made here',profile=profile,public=True));self.assertEqual(response.status_code,200,response.data);return response.json
    def test_private_save_ownership_revision_export(self):
        r=self.create();path='/flapart/projects/'+r['id']
        self.assertEqual(self.get(path,'anon').status_code,401);self.assertEqual(self.get(path,'q').status_code,404)
        self.assertEqual(self.get('/flapart/projects','q').json['projects'],[])
        value={'title':'Changed','project':{'private':True},'expectedRevision':r['revision']}
        self.assertEqual(self.post(path,value).status_code,200);self.assertEqual(self.post(path,value).status_code,409)
        from account_profiles import export
        self.assertEqual(export(self.s,'p')['flapart'][0]['project'],{'private':True})
    def test_frozen_png_no_metadata_private_draft_does_not_change_publication(self):
        r=self.pub(self.create());url='/flapart/public/'+r['publication']['id']+'.png';a=self.get(url,'anon')
        self.assertEqual(a.status_code,200);self.assertNotIn(b'Secret',a.data);self.assertEqual(a.mimetype,'image/png');self.assertEqual(a.headers['Cache-Control'],'no-store')
        saved=self.post('/flapart/projects/'+r['id'],dict(title='Private edit',project={'secret':'private'},expectedRevision=r['revision'])).json
        self.assertEqual(self.get(url,'anon').data,a.data);self.assertNotIn('project',r)
        fresh=self.pub(saved);self.assertNotEqual(fresh['publication']['id'],r['publication']['id']);self.assertEqual(self.get(url,'anon').status_code,404)
    def test_catalog_profile_opt_in_and_retraction(self):
        r=self.pub(self.create(),False);self.assertEqual(PublicCatalog(self.s).records('p','image'),[])
        r=self.pub(r,True);records=PublicCatalog(self.s).records('p','image');self.assertEqual(len(records),1)
        self.assertNotIn('principal',records[0]);self.assertEqual(records[0]['ownerId'],'p')
        self.assertEqual(self.post('/flapart/projects/'+r['id']+'/unpublish',{'expectedRevision':r['revision']}).status_code,200)
        self.assertEqual(PublicCatalog(self.s).records('p','image'),[]);self.assertEqual(self.get('/flapart/public/'+r['publication']['id']+'.png','anon').status_code,404)
    def test_csrf_origin_and_preflight(self):
        c=self.clients['p'];self.assertEqual(c.post('/flapart/projects',base_url=ORIGIN,json={}).status_code,403)
        self.assertEqual(c.get('/flapart/session',base_url=ORIGIN,headers={'Origin':'https://evil.example'}).status_code,403)
        r=c.options('/flapart/projects',base_url=ORIGIN,headers={'Origin':WEB,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type,x-csrf-token'});self.assertEqual(r.status_code,204)
        self.assertEqual(r.headers['Access-Control-Allow-Origin'],WEB)
    def test_lifecycle_suspend_revoke_delete(self):
        r=self.pub(self.create());url='/flapart/public/'+r['publication']['id']+'.png'
        publish(self.s,'p',verified=False);self.assertEqual(self.get(url,'anon').status_code,404);self.assertEqual(self.get('/flapart/projects').status_code,403)
        publish(self.s,'p',verified=True);self.assertEqual(self.get(url,'anon').status_code,200)
        suspend(self.s,'p',True);self.assertEqual(self.get(url,'anon').status_code,404)
        suspend(self.s,'p',False);self.s.delete_principal('p');self.assertEqual(self.get(url,'anon').status_code,404)
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapart_projects').fetchone()[0],0);self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapart_publications').fetchone()[0],0)
    def test_townhall_attachment_alias_ban_moderation_delete(self):
        r=self.pub(self.create());path='/flapart/projects/'+r['id']+'/townhall';data=dict(expectedRevision=r['revision'],title='My art',body='Look at this',public=True)
        self.assertEqual(self.post(path,data).status_code,400)
        self.assertEqual(self.post('/forum/alias',{'alias':'Artist'}).status_code,200)
        response=self.post(path,data);self.assertEqual(response.status_code,201,response.data);item=response.json['id']
        public=self.get('/forum/posts/'+item,'anon').json['post'];self.assertEqual(public['artwork']['id'],r['publication']['id'])
        self.assertNotIn('principal',public)
        self.assertEqual(self.post('/forum/items/'+item+'/ban',{'enabled':True},'owner').status_code,200);self.assertEqual(self.post(path,data).status_code,403)
        self.assertEqual(self.post('/forum/items/'+item+'/delete',{'revision':1},'owner').status_code,200);self.assertIsNone(self.get('/forum/posts/'+item,'anon').json['post']['artwork'])
        self.post('/flapart/projects/'+r['id']+'/unpublish',{'expectedRevision':r['revision']});self.assertEqual(self.s.db.execute('SELECT count(*) FROM flapart_forum_art').fetchone()[0],0)
    def test_quota_and_failed_publish_preserve_prior(self):
        r=self.pub(self.create());before=self.get('/flapart/projects/'+r['id']).json
        with patch('flapart_store.ACCOUNT_QUOTA',1):self.assertEqual(self.post('/flapart/projects',dict(title='Too large',project={'x':'a'*1024})).status_code,413)
        bad=dict(expectedRevision=r['revision'],png='data:image/png;base64,broken',title='Bad',description='',profile=True,public=True)
        self.assertEqual(self.post('/flapart/projects/'+r['id']+'/publish',bad).status_code,400);self.assertEqual(self.get('/flapart/projects/'+r['id']).json,before)
    def test_png_validation(self):
        clean,w,h=png_clean(png());self.assertEqual((w,h),(2,2));self.assertNotIn(b'tEXt',clean)
        raw=base64.b64decode(png()[22:])
        variants=[raw+b'extra',raw[:-1],raw[:40]+bytes([raw[40]^1])+raw[41:],b'<svg/>']
        for data in variants:
            with self.assertRaises(ValueError):png_clean('data:image/png;base64,'+base64.b64encode(data).decode())
        bomb=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'*1000000))+chunk(b'IEND',b'')
        with self.assertRaises(ValueError):png_clean('data:image/png;base64,'+base64.b64encode(bomb).decode())
    def test_schema_idempotent_no_runtime_migration(self):
        install(self.s.db);self.assertEqual(self.get('/flapart/projects').status_code,200)
        self.s.db.execute('DROP TABLE flapart_forum_art')
        with self.assertRaises(ValueError):create_session_fixture(self.db,b'x'*32,flapart_enabled=True)
if __name__=='__main__':unittest.main()

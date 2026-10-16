"""Flapart same-site session API; private saves and explicit independent sharing."""
import hmac,secrets,time
from functools import wraps
from flask import abort,jsonify,request,session,Response
from flapart_store import Repository,Conflict,Quota,Missing,active,validate_schema,text,MAX_PROJECT,MAX_PNG,MAX_PROJECTS,MAX_DIMENSION

def register(app,store,bearer,csrf,origin,rate_limit):
    with app.app_context():validate_schema(store.db)
    repo=Repository(store);origins={origin,'https://flaptown.com'}
    def who(required=True):
        p=store.session(bearer())
        if not p:
            if required:abort(401)
            return None
        if not active(store.db,p):
            if required:abort(403)
            return None
        return p
    def mutate():
        p=who();expected=session.get('csrf','');supplied=request.headers.get('X-CSRF-Token','')
        if request.headers.get('Origin') not in origins or not expected or not supplied or not hmac.compare_digest(expected,supplied):abort(403)
        if not rate_limit('flapart-write:'+p,40,40):abort(429)
        if not request.is_json:abort(415)
        return p
    def body(keys):
        try:data=request.get_json(silent=True)
        except (ValueError,RecursionError):abort(400)
        if not isinstance(data,dict) or set(data)!=set(keys):abort(400)
        return data
    def run(fn,code=200):
        try:return jsonify(fn()),code
        except Missing:abort(404)
        except Conflict:return jsonify(error='stale_project_revision',message='This project changed elsewhere. Save a local copy before reloading.'),409
        except Quota:return jsonify(error='artwork_quota',message='Cloud storage limit reached. Your local artwork is preserved; export a project file.'),413
        except (ValueError,TypeError,KeyError,RecursionError):return jsonify(error='invalid_artwork'),400
    def atomic(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            with store.transaction():return fn(*args,**kwargs)
        return wrapped
    @app.before_request
    def flapart_boundary():
        if not request.path.startswith('/flapart/'):return
        request.max_content_length=MAX_PROJECT+MAX_PNG*4//3+65536
        supplied=request.headers.get('Origin')
        if supplied is not None and supplied not in origins:abort(403)
        if request.method=='OPTIONS':
            headers={v.strip().lower() for v in request.headers.get('Access-Control-Request-Headers','').split(',') if v.strip()}
            if supplied not in origins or request.headers.get('Access-Control-Request-Method') not in ('GET','POST') or not headers<={'content-type','x-csrf-token'}:abort(403)
            return '',204
    @app.after_request
    def flapart_headers(response):
        if request.path.startswith('/flapart/'):
            response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'});response.vary.add('Cookie');response.vary.add('Origin')
            if request.headers.get('Origin') in origins:response.headers.update({'Access-Control-Allow-Origin':request.headers['Origin'],'Access-Control-Allow-Credentials':'true','Access-Control-Allow-Methods':'GET, POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token'})
        return response
    @app.get('/flapart/session')
    def flapart_session():return jsonify(authenticated=bool(who(False)),csrf=csrf(),limits=dict(projectBytes=MAX_PROJECT,pngBytes=MAX_PNG,projects=MAX_PROJECTS,dimension=MAX_DIMENSION))
    @app.route('/flapart/projects',methods=['GET','POST'])
    @atomic
    def flapart_projects():
        if request.method=='POST':
            p=mutate();v=body(['title','project']);return run(lambda:repo.save(p,v['title'],v['project']),201)
        p=who()
        with store.transaction():return jsonify(projects=[repo.metadata(r) for r in store.db.execute('SELECT * FROM flapart_projects WHERE principal=? ORDER BY updated DESC',(p,))])
    @app.route('/flapart/projects/<ident>',methods=['GET','POST'])
    @atomic
    def flapart_project(ident):
        if request.method=='POST':
            p=mutate();v=body(['title','project','expectedRevision']);return run(lambda:repo.save(p,v['title'],v['project'],ident,v['expectedRevision']))
        p=who();return run(lambda:repo.metadata(repo.owned(p,ident),True))
    @app.post('/flapart/projects/<ident>/publish')
    @atomic
    def flapart_publish(ident):
        p=mutate();v=body(['expectedRevision','png','title','description','profile','public'])
        if not rate_limit('flapart-publish:'+p,8,8):abort(429)
        return run(lambda:repo.publish(p,ident,v))
    @app.post('/flapart/projects/<ident>/unpublish')
    @atomic
    def flapart_unpublish(ident):
        p=mutate();v=body(['expectedRevision']);return run(lambda:repo.remove(p,ident,v['expectedRevision']))
    @app.post('/flapart/projects/<ident>/delete')
    @atomic
    def flapart_delete(ident):
        p=mutate();v=body(['expectedRevision']);return run(lambda:repo.remove(p,ident,v['expectedRevision'],True))
    @app.get('/flapart/public/<ident>.png')
    def flapart_png(ident):
        try:pub=repo.public(ident)
        except Missing:abort(404)
        return Response(pub['png'],mimetype='image/png',headers={'Content-Disposition':'inline; filename="flapart-artwork.png"'})
    @app.post('/flapart/projects/<ident>/townhall')
    @atomic
    def flapart_townhall(ident):
        p=mutate();v=body(['expectedRevision','title','body','public'])
        def share():
            if v['public'] is not True:raise ValueError('Explicit post required')
            title=text(v['title'],160);content=text(v['body'],10000)
            with store.transaction():
                row=repo.owned(p,ident);repo.check(row,v['expectedRevision'])
                member=store.db.execute('SELECT * FROM forum_members WHERE principal=?',(p,)).fetchone()
                if not member:return dict(error='forum_alias_required',message='Choose your public name in Town Square first.'),400
                if member['banned']:abort(403)
                pub=store.db.execute('SELECT id FROM flapart_publications WHERE project_id=?',(ident,)).fetchone()
                if not pub:raise Conflict()
                if not rate_limit('forum-write:'+p,40,40) or not rate_limit('forum-global',600,100) or not rate_limit('forum-post:'+p,5,5):abort(429)
                item=secrets.token_hex(12);now=time.time()
                store.db.execute('INSERT INTO forum_items(id,principal,depth,alias,badge,title,body,flair,created,updated) VALUES(?,?,0,?,?,?,?,?,?,?)',(item,p,member['alias'],member['badge'],title,content,'Show & tell',now,now))
                store.db.execute('INSERT INTO flapart_forum_art VALUES(?,?)',(item,pub[0]))
                return dict(id=item,url='https://flaptown.com/forum/?post='+item,publication=pub[0])
        # Return a real 400 for missing public alias without conflating private saves.
        try:
            result=share()
            if isinstance(result,tuple):return jsonify(result[0]),result[1]
            return jsonify(result),201
        except Missing:abort(404)
        except Conflict:return jsonify(error='stale_or_publication_required'),409
        except (ValueError,TypeError):return jsonify(error='invalid_artwork_post'),400

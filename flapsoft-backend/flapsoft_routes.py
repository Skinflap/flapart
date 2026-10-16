"""Flapsoft: bounded source projects, immutable versions, forks and discussions.
User files are inert text. No user build commands, HTML previews or server execution.
"""
import hashlib, hmac, io, json, os, re, secrets, time, zipfile
from pathlib import Path
from functools import wraps
from flask import request, session, jsonify, abort, send_file

LIMIT=2*1024*1024
QUOTA=32*1024*1024
LICENSES={'MIT','Apache-2.0','GPL-3.0-only','BSD-3-Clause','CC0-1.0'}
SCHEMA='''
CREATE TABLE IF NOT EXISTS flapsoft_projects(id TEXT PRIMARY KEY,principal TEXT NOT NULL REFERENCES principals(id) ON DELETE CASCADE,name TEXT NOT NULL,description TEXT NOT NULL,license TEXT NOT NULL,public INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,updated REAL NOT NULL,parent TEXT);
CREATE TABLE IF NOT EXISTS flapsoft_versions(project TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,version INTEGER NOT NULL,files TEXT NOT NULL,message TEXT NOT NULL,digest TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(project,version));
CREATE TABLE IF NOT EXISTS flapsoft_issues(id TEXT PRIMARY KEY,project TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,principal TEXT REFERENCES principals(id) ON DELETE SET NULL,title TEXT NOT NULL,body TEXT NOT NULL,closed INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS flapsoft_reports(project TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,principal TEXT NOT NULL REFERENCES principals(id) ON DELETE CASCADE,reason TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(project,principal));
CREATE TABLE IF NOT EXISTS flapsoft_restrictions(principal TEXT PRIMARY KEY REFERENCES principals(id) ON DELETE CASCADE,restricted INTEGER NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS flapsoft_acceptances(project TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,version INTEGER NOT NULL,suggestion TEXT NOT NULL,fork TEXT NOT NULL,source_revision INTEGER NOT NULL,base_revision INTEGER NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(project,version));
CREATE TABLE IF NOT EXISTS flapsoft_fork_bases(fork TEXT PRIMARY KEY REFERENCES flapsoft_projects(id) ON DELETE CASCADE,upstream TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,base_revision INTEGER NOT NULL,base_digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS flapsoft_suggestions(id TEXT PRIMARY KEY,project TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,fork TEXT NOT NULL REFERENCES flapsoft_projects(id) ON DELETE CASCADE,principal TEXT NOT NULL REFERENCES principals(id) ON DELETE CASCADE,base_revision INTEGER NOT NULL,source_revision INTEGER NOT NULL,files TEXT NOT NULL,digest TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'open',accepted_revision INTEGER,created REAL NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS flapsoft_comments(id TEXT PRIMARY KEY,issue TEXT NOT NULL REFERENCES flapsoft_issues(id) ON DELETE CASCADE,principal TEXT REFERENCES principals(id) ON DELETE SET NULL,body TEXT NOT NULL,created REAL NOT NULL);
'''
def schema_statements():
    return [s.strip().replace('IF NOT EXISTS ','') for s in SCHEMA.split(';') if s.strip()]
def normalized(sql): return ''.join(sql.lower().split())
def install(db):
    if db.in_transaction: raise ValueError('Offline migration requires its own transaction')
    db.execute('PRAGMA foreign_keys=ON'); db.execute('BEGIN IMMEDIATE')
    try:
        for statement in schema_statements():
            name=statement.split('(')[0].split()[-1]
            old=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
            if old and normalized(old[0])!=normalized(statement): raise ValueError('Flapsoft schema conflict')
            if not old: db.execute(statement)
        if db.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Foreign key violation')
        db.commit()
    except BaseException: db.rollback(); raise
def validate(db):
    for statement in schema_statements():
        name=statement.split('(')[0].split()[-1]
        old=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
        if not old or normalized(old[0])!=normalized(statement): raise ValueError('Offline Flapsoft migration required')
def text(value,limit,empty=False):
    if not isinstance(value,str) or (not empty and not value.strip()) or len(value)>limit or any((ord(c)<32 and c not in '\n\t') or 0xD800<=ord(c)<=0xDFFF for c in value): raise ValueError('Check the text length and characters.')
    return value.strip()
def files_checked(files):
    if not isinstance(files,dict) or not 1<=len(files)<=100: raise ValueError('Use 1–100 text files per version.')
    result={}
    folded=set()
    for name,body in files.items():
        if not isinstance(name,str) or len(name)>180 or not re.fullmatch(r'[A-Za-z0-9_. -]+(?:/[A-Za-z0-9_. -]+)*',name) or any(part in ('.','..') or part.startswith('.') or part.endswith(' ') for part in name.split('/')): raise ValueError('Use ordinary relative filenames; hidden files and parent paths are not accepted.')
        parts=name.split('/')
        if any(part.rstrip(' .')!=part or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))} for part in parts) or name.casefold()=='flapsoft-provenance.json': raise ValueError('That filename is reserved for portability or provenance.')
        lower=name.casefold()
        if lower in folded or any(lower.startswith(old+'/') or old.startswith(lower+'/') for old in folded): raise ValueError('Filenames must be distinct across operating systems and folders.')
        folded.add(lower)
        if not isinstance(body,str) or '\x00' in body or any(0xD800<=ord(c)<=0xDFFF for c in body) or len(body.encode())>512*1024: raise ValueError('Each file must be text, at most 512 KiB.')
        result[name]=body
    encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    if len(encoded.encode())>LIMIT: raise ValueError('A version can contain at most 2 MiB of source.')
    return encoded

def register(app,store,bearer,csrf,origin,rate_limit):
    with app.app_context(): validate(store.db)
    origins={origin,'https://flaptown.com'}
    if origin=='http://127.0.0.1:8798': origins.add('http://127.0.0.1:8768')
    @app.before_request
    def flapsoft_boundary():
        if not request.path.startswith('/flapsoft/'): return
        request.max_content_length=LIMIT+65536
        supplied=request.headers.get('Origin')
        if supplied is not None and supplied not in origins: abort(403)
        if request.method=='OPTIONS':
            headers={x.strip().lower() for x in request.headers.get('Access-Control-Request-Headers','').split(',') if x.strip()}
            if supplied not in origins or request.headers.get('Access-Control-Request-Method') not in ('GET','POST') or not headers<={'content-type','x-csrf-token'}: abort(403)
            return '',204
    @app.after_request
    def flapsoft_headers(response):
        if request.path.startswith('/flapsoft/'):
            supplied=request.headers.get('Origin')
            if supplied in origins:
                response.headers.update({'Access-Control-Allow-Origin':supplied,'Access-Control-Allow-Credentials':'true','Access-Control-Allow-Methods':'GET, POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type, X-CSRF-Token'})
                response.vary.add('Origin')
            response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; sandbox"})
        return response
    def active(p):
        row=store.db.execute('SELECT enabled FROM principals WHERE id=?',(p,)).fetchone()
        state=store.db.execute('SELECT snapshot FROM lifecycle_state WHERE principal=?',(p,)).fetchone()
        state=json.loads(state[0]) if state else {}
        return bool(row and row[0] and state.get('active') and state.get('verified') and not state.get('deleted'))
    def atomic(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            with store.transaction(): return fn(*args,**kwargs)
        return wrapped
    def who():
        p=store.session(bearer())
        return p if p and active(p) else None
    def admin(p): return bool(p and store.db.execute('SELECT 1 FROM account_admins WHERE principal=?',(p,)).fetchone())
    def restricted(p): return bool(store.db.execute('SELECT 1 FROM flapsoft_restrictions WHERE principal=? AND restricted=1',(p,)).fetchone())
    def protect():
        expected=session.get('csrf',''); supplied=request.headers.get('X-CSRF-Token','')
        if request.headers.get('Origin') not in origins or not expected or not supplied or not hmac.compare_digest(expected,supplied): abort(403)
        p=who()
        if not p: abort(401)
        if restricted(p) and not request.path.endswith(('/delete','/visibility','/report','/withdraw')): abort(403,description='Project participation is restricted. You can still withdraw or delete your work.')
        if not rate_limit('flapsoft:'+p,30,30) or not rate_limit('flapsoft-global',300,100): abort(429)
        return p
    def data():
        try: d=request.get_json(silent=True)
        except (RecursionError,UnicodeError,ValueError): abort(400)
        if not isinstance(d,dict): abort(400)
        return d
    def project(pid,owner=False):
        p=who(); row=store.db.execute('SELECT s.* FROM flapsoft_projects s JOIN principals p ON p.id=s.principal AND p.enabled=1 WHERE s.id=?',(pid,)).fetchone()
        if not row or not active(row['principal']) or (row['principal']!=p and (owner or not row['public'] or restricted(row['principal']))): abort(404)
        return row
    def meta(row): return {**{k:row[k] for k in ('id','name','description','license','public','revision','created','updated','parent')},'owned':row['principal']==who(),'can_moderate':admin(who())}
    def quota(p,extra):
        count=store.db.execute('SELECT count(*) FROM flapsoft_projects WHERE principal=?',(p,)).fetchone()[0]
        used=store.db.execute('SELECT coalesce(sum(length(CAST(v.files AS BLOB))),0) FROM flapsoft_versions v JOIN flapsoft_projects p ON p.id=v.project WHERE p.principal=?',(p,)).fetchone()[0]
        used+=store.db.execute('SELECT coalesce(sum(length(CAST(body AS BLOB))),0) FROM flapsoft_issues WHERE principal=?',(p,)).fetchone()[0]
        used+=store.db.execute('SELECT coalesce(sum(length(CAST(body AS BLOB))),0) FROM flapsoft_comments WHERE principal=?',(p,)).fetchone()[0]
        total=store.db.execute('SELECT coalesce(sum(length(CAST(files AS BLOB))),0) FROM flapsoft_versions').fetchone()[0]
        total+=store.db.execute('SELECT coalesce(sum(length(CAST(body AS BLOB))),0) FROM flapsoft_issues').fetchone()[0]
        total+=store.db.execute('SELECT coalesce(sum(length(CAST(body AS BLOB))),0) FROM flapsoft_comments').fetchone()[0]
        used+=store.db.execute('SELECT coalesce(sum(length(CAST(files AS BLOB))+length(CAST(body AS BLOB))+length(CAST(title AS BLOB))),0) FROM flapsoft_suggestions WHERE principal=?',(p,)).fetchone()[0]
        total+=store.db.execute('SELECT coalesce(sum(length(CAST(files AS BLOB))+length(CAST(body AS BLOB))+length(CAST(title AS BLOB))),0) FROM flapsoft_suggestions').fetchone()[0]
        if total+extra>2*1024*1024*1024: abort(413,description='The community storage limit has been reached.')
        if used+extra>QUOTA: abort(413,description='Your 32 MiB source archive is full. Download and remove an old project.')
        return count
    def revision(row,d):
        if type(d.get('revision')) is not int or d['revision']!=row['revision']: abort(409,description='This project changed. Reopen it before saving.')
    def version_write(pid,v,encoded,message):
        store.db.execute('INSERT INTO flapsoft_versions VALUES(?,?,?,?,?,?)',(pid,v,encoded,message,hashlib.sha256(encoded.encode()).hexdigest(),time.time()))
    @app.get('/flapsoft/downloads/<filename>')
    def flapsoft_release_download(filename):
        # Release directory is owner-managed deployment material, never a member upload.
        root=os.environ.get('FLAPTOWN_FLAPSOFT_RELEASES')
        if not root or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,150}',filename): abort(404)
        root=Path(root)
        if not root.is_absolute() or root.is_symlink(): abort(404)
        try:
            manifest_path=root/'manifest.json'
            if manifest_path.is_symlink() or manifest_path.stat().st_size>65536: abort(404)
            manifest=json.loads(manifest_path.read_text())
            if not isinstance(manifest,dict) or not isinstance(manifest.get('files'),dict): abort(404)
            entry=manifest['files'].get(filename)
            path=root/filename
            if not isinstance(entry,dict) or path.is_symlink() or not path.is_file() or path.stat().st_size!=entry.get('size') or not re.fullmatch(r'[a-f0-9]{64}',entry.get('sha256','')): abort(404)
        except (OSError,ValueError,TypeError): abort(404)
        return send_file(path,as_attachment=True,download_name=filename,mimetype='application/octet-stream',conditional=True,etag=entry['sha256'])
    @app.get('/flapsoft/session')
    @atomic
    def flapsoft_session(): return jsonify(authenticated=bool(who()),moderator=admin(who()),csrf=csrf(),limits={'version_bytes':LIMIT,'account_bytes':QUOTA,'files':100})
    @app.get('/flapsoft/projects')
    @atomic
    def flapsoft_list():
        p=who(); mine=request.args.get('mine')=='1'
        if mine and not p: abort(401)
        q=request.args.get('q','')[:100]
        rows=store.db.execute('SELECT s.* FROM flapsoft_projects s JOIN principals p ON p.id=s.principal AND p.enabled=1 WHERE '+('s.principal=?' if mine else 's.public=1')+' AND (s.name LIKE ? OR s.description LIKE ?) ORDER BY s.updated DESC LIMIT 100', ((p,) if mine else ())+('%'+q+'%','%'+q+'%')).fetchall()
        return jsonify(projects=[meta(r) for r in rows if active(r['principal']) and (mine or not restricted(r['principal']))])
    @app.post('/flapsoft/projects')
    @atomic
    def flapsoft_create():
        with store.transaction():
            p=protect(); d=data()
            try:
                name=text(d.get('name'),80); description=text(d.get('description',''),1000,True); license=d.get('license')
                if not isinstance(license,str) or license not in LICENSES: raise ValueError('Choose an open-source license.')
                encoded=files_checked(d.get('files',{'README.md':'# '+name+'\n\n'+description+'\n'}))
            except ValueError as e: return jsonify(error=str(e)),400
            if quota(p,len(encoded.encode()))>=30: abort(413,description='Your account can hold 30 projects.')
            pid=secrets.token_urlsafe(16); now=time.time()
            store.db.execute('INSERT INTO flapsoft_projects VALUES(?,?,?,?,?,0,1,?,?,NULL)',(pid,p,name,description,license,now,now)); version_write(pid,1,encoded,'First version')
            return jsonify(meta(project(pid))),201
    @app.get('/flapsoft/projects/<pid>')
    @atomic
    def flapsoft_read(pid):
        r=project(pid); v=request.args.get('version',str(r['revision']))
        if not re.fullmatch(r'[0-9]{1,3}',v): abort(400)
        row=store.db.execute('SELECT * FROM flapsoft_versions WHERE project=? AND version=?',(pid,int(v))).fetchone()
        if not row: abort(404)
        base=store.db.execute('SELECT upstream,base_revision FROM flapsoft_fork_bases WHERE fork=?',(pid,)).fetchone()
        return jsonify(**meta(r),accepted_from=dict(acceptance) if (acceptance:=store.db.execute('SELECT suggestion,fork,source_revision,base_revision,digest FROM flapsoft_acceptances WHERE project=? AND version=?',(pid,int(v))).fetchone()) else None,suggestion_base=dict(base) if base and r['principal']==who() else None,files=json.loads(row['files']),version=row['version'],digest=row['digest'],message=row['message'])
    @app.get('/flapsoft/projects/<pid>/history')
    @atomic
    def flapsoft_history(pid):
        project(pid)
        return jsonify(versions=[dict(r) for r in store.db.execute('SELECT version,message,digest,created FROM flapsoft_versions WHERE project=? ORDER BY version DESC LIMIT 200',(pid,))])
    @app.post('/flapsoft/projects/<pid>/save')
    @atomic
    def flapsoft_save(pid):
        with store.transaction():
            p=protect(); r=project(pid,True); d=data(); revision(r,d)
            try: encoded=files_checked(d.get('files')); message=text(d.get('message'),240)
            except ValueError as e: return jsonify(error=str(e)),400
            quota(p,len(encoded.encode()))
            if r['revision']>=200: abort(413,description='This project has 200 versions. Start a new edition.')
            v=r['revision']+1; version_write(pid,v,encoded,message)
            store.db.execute('UPDATE flapsoft_projects SET revision=?,updated=? WHERE id=?',(v,time.time(),pid))
            return jsonify(meta(project(pid)))
    @app.post('/flapsoft/projects/<pid>/visibility')
    @atomic
    def flapsoft_visibility(pid):
        with store.transaction():
            protect(); r=project(pid,True); d=data(); revision(r,d)
            if type(d.get('public')) is not bool: abort(400)
            if bool(r['public'])==d['public']: return jsonify(meta(r))
            if d['public'] and restricted(r['principal']): abort(403)
            encoded=store.db.execute('SELECT files FROM flapsoft_versions WHERE project=? AND version=?',(pid,r['revision'])).fetchone()[0]
            if d['public']:
                quota(r['principal'],len(encoded.encode()))
                if r['revision']>=200: abort(413,description='This project has 200 versions. Start a new edition.')
            v=r['revision']+1
            version_write(pid,v,encoded,'Published project' if d['public'] else 'Made project private')
            store.db.execute('UPDATE flapsoft_projects SET public=?,revision=?,updated=? WHERE id=?',(int(d['public']),v,time.time(),pid))
            return jsonify(meta(project(pid)))
    @app.post('/flapsoft/projects/<pid>/delete')
    @atomic
    def flapsoft_delete(pid):
        with store.transaction():
            protect(); r=project(pid,True); revision(r,data()); store.db.execute('DELETE FROM flapsoft_projects WHERE id=?',(pid,))
            return jsonify(deleted=True)
    @app.post('/flapsoft/projects/<pid>/fork')
    @atomic
    def flapsoft_fork(pid):
        with store.transaction():
            p=protect(); r=project(pid); d=data(); revision(r,d)
            encoded=store.db.execute('SELECT files FROM flapsoft_versions WHERE project=? AND version=?',(pid,r['revision'])).fetchone()[0]
            if quota(p,len(encoded.encode()))>=30: abort(413)
            newid=secrets.token_urlsafe(16); now=time.time()
            store.db.execute('INSERT INTO flapsoft_projects VALUES(?,?,?,?,?,0,1,?,?,?)',(newid,p,(r['name']+' — my edition')[:80],r['description'],r['license'],now,now,pid)); version_write(newid,1,encoded,'Forked from '+pid+' version '+str(r['revision']))
            store.db.execute('INSERT INTO flapsoft_fork_bases VALUES(?,?,?,?)',(newid,pid,r['revision'],hashlib.sha256(encoded.encode()).hexdigest()))
            return jsonify(meta(project(newid))),201
    @app.get('/flapsoft/projects/<pid>/download')
    @atomic
    def flapsoft_download(pid):
        r=project(pid); row=store.db.execute('SELECT files FROM flapsoft_versions WHERE project=? AND version=?',(pid,r['revision'])).fetchone(); files=json.loads(row[0]); stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
            for name,body in files.items(): z.writestr(name,body)
            z.writestr('FLAPSOFT-PROVENANCE.json',json.dumps({'project':pid,'version':r['revision'],'license':r['license'],'parent':r['parent'],'accepted_changes':[dict(a) for a in store.db.execute('SELECT version,suggestion,fork,source_revision,base_revision,digest FROM flapsoft_acceptances WHERE project=? ORDER BY version',(pid,))]}))
        stream.seek(0)
        return send_file(stream,mimetype='application/zip',as_attachment=True,download_name='flapsoft-'+pid+'-v'+str(r['revision'])+'.zip')
    @app.get('/flapsoft/projects/<pid>/issues')
    @atomic
    def flapsoft_issues(pid):
        r=project(pid)
        return jsonify(issues=[{**{k:(('[account removed]' if k=='title' else '') if k in ('title','body') and (not x['principal'] or not active(x['principal'])) else x[k]) for k in ('id','title','body','closed','created')},'owned':x['principal']==who()} for x in store.db.execute('SELECT * FROM flapsoft_issues WHERE project=? ORDER BY created DESC LIMIT 100',(pid,))])
    @app.post('/flapsoft/projects/<pid>/issues')
    @atomic
    def flapsoft_issue(pid):
        with store.transaction():
            p=protect(); project(pid); d=data()
            try: title=text(d.get('title'),120); body=text(d.get('body'),8000)
            except ValueError as e: return jsonify(error=str(e)),400
            if store.db.execute('SELECT count(*) FROM flapsoft_issues WHERE project=?',(pid,)).fetchone()[0]>=300: abort(413)
            quota(p,len(body.encode())+len(title.encode()))
            iid=secrets.token_urlsafe(16); store.db.execute('INSERT INTO flapsoft_issues VALUES(?,?,?,?,?,0,?)',(iid,pid,p,title,body,time.time()))
            return jsonify(id=iid),201
    @app.get('/flapsoft/issues/<iid>')
    @atomic
    def flapsoft_issue_read(iid):
        r=store.db.execute('SELECT * FROM flapsoft_issues WHERE id=?',(iid,)).fetchone()
        if not r: abort(404)
        pr=project(r['project'])
        return jsonify(id=iid,title=r['title'] if r['principal'] and active(r['principal']) else '[account removed]',body=r['body'] if r['principal'] and active(r['principal']) else '',closed=bool(r['closed']),can_close=r['principal']==who() or pr['principal']==who(),comments=[{'body':c['body'] if c['principal'] and active(c['principal']) else '[account removed]','created':c['created']} for c in store.db.execute('SELECT * FROM flapsoft_comments WHERE issue=? ORDER BY created LIMIT 200',(iid,))])
    @app.post('/flapsoft/issues/<iid>/<action>')
    @atomic
    def flapsoft_issue_action(iid,action):
        with store.transaction():
            p=protect(); d=data(); r=store.db.execute('SELECT * FROM flapsoft_issues WHERE id=?',(iid,)).fetchone()
            if not r: abort(404)
            pr=project(r['project'])
            if action=='comment':
                try: body=text(d.get('body'),8000)
                except ValueError as e: return jsonify(error=str(e)),400
                if store.db.execute('SELECT count(*) FROM flapsoft_comments WHERE issue=?',(iid,)).fetchone()[0]>=200: abort(413)
                quota(p,len(body.encode()))
                store.db.execute('INSERT INTO flapsoft_comments VALUES(?,?,?,?,?)',(secrets.token_urlsafe(16),iid,p,body,time.time()))
            elif action=='close':
                if p not in (r['principal'],pr['principal']): abort(403)
                if type(d.get('closed')) is not bool: abort(400)
                store.db.execute('UPDATE flapsoft_issues SET closed=? WHERE id=?',(int(d['closed']),iid))
            else: abort(404)
            return jsonify(changed=True)

    def suggestion(sid):
        r=store.db.execute('SELECT * FROM flapsoft_suggestions WHERE id=?',(sid,)).fetchone()
        if not r: abort(404)
        upstream=store.db.execute('SELECT * FROM flapsoft_projects WHERE id=?',(r['project'],)).fetchone()
        p=who()
        if not upstream or p not in (r['principal'],upstream['principal']) or not active(r['principal']) or not active(upstream['principal']) or restricted(r['principal']) or restricted(upstream['principal']): abort(404)
        # Withdrawal of upstream publication revokes contributor access to review.
        if p!=upstream['principal'] and not upstream['public']: abort(404)
        return r,upstream
    def suggestion_meta(r,upstream):
        return {**{k:r[k] for k in ('id','project','fork','base_revision','source_revision','title','body','state','accepted_revision','created','updated')},'can_review':who()==upstream['principal'],'upstream_revision':upstream['revision'],'conflict':r['base_revision']!=upstream['revision']}
    @app.get('/flapsoft/projects/<pid>/suggestions')
    @atomic
    def flapsoft_suggestions(pid):
        p=who()
        if not p: abort(401)
        pr=project(pid)
        rows=store.db.execute('SELECT * FROM flapsoft_suggestions WHERE project=? OR fork=? ORDER BY created DESC LIMIT 300',(pid,pid)).fetchall()
        result=[]
        for r in rows:
            upstream=store.db.execute('SELECT * FROM flapsoft_projects WHERE id=?',(r['project'],)).fetchone()
            if upstream and p in (r['principal'],upstream['principal']) and active(r['principal']) and active(upstream['principal']) and not restricted(r['principal']) and not restricted(upstream['principal']) and (p==upstream['principal'] or upstream['public']):result.append(suggestion_meta(r,upstream))
        return jsonify(suggestions=result)
    @app.post('/flapsoft/projects/<pid>/suggest')
    @atomic
    def flapsoft_suggest(pid):
        p=protect(); fork=project(pid,True);d=data();revision(fork,d)
        base=store.db.execute('SELECT * FROM flapsoft_fork_bases WHERE fork=?',(pid,)).fetchone()
        if not base: abort(409,description='Start a fresh edition of the original project before suggesting changes.')
        upstream=project(base['upstream'])
        if upstream['principal']==p: abort(400,description='Save changes directly to your own project.')
        if base['base_revision']!=upstream['revision']: abort(409,description='The original project changed. Start a fresh edition and apply your improvements there.')
        original=store.db.execute('SELECT files,digest FROM flapsoft_versions WHERE project=? AND version=?',(upstream['id'],base['base_revision'])).fetchone()
        if not original or original['digest']!=base['base_digest']:abort(409)
        source=store.db.execute('SELECT files,digest FROM flapsoft_versions WHERE project=? AND version=?',(pid,fork['revision'])).fetchone()
        if source['digest']==original['digest']:abort(400,description='Save an improvement in your edition first.')
        try:title=text(d.get('title'),120);body=text(d.get('body',''),4000,True)
        except ValueError as e:return jsonify(error=str(e)),400
        if store.db.execute("SELECT 1 FROM flapsoft_suggestions WHERE fork=? AND state='open'",(pid,)).fetchone():abort(409,description='This edition already has an open suggestion.')
        if store.db.execute('SELECT count(*) FROM flapsoft_suggestions WHERE principal=?',(p,)).fetchone()[0]>=100 or store.db.execute('SELECT count(*) FROM flapsoft_suggestions WHERE project=?',(upstream['id'],)).fetchone()[0]>=300:abort(413)
        quota(p,len(source['files'].encode())+len(title.encode())+len(body.encode()))
        sid=secrets.token_urlsafe(16);now=time.time()
        store.db.execute("INSERT INTO flapsoft_suggestions VALUES(?,?,?,?,?,?,?,?,?,?,'open',NULL,?,?)",(sid,upstream['id'],pid,p,base['base_revision'],fork['revision'],source['files'],source['digest'],title,body,now,now))
        return jsonify(id=sid),201
    @app.get('/flapsoft/suggestions/<sid>')
    @atomic
    def flapsoft_suggestion_read(sid):
        r,upstream=suggestion(sid)
        base=store.db.execute('SELECT files FROM flapsoft_versions WHERE project=? AND version=?',(upstream['id'],r['base_revision'])).fetchone()
        if not base:abort(409)
        before=json.loads(base['files']);after=json.loads(r['files'])
        changes=[{'name':name,'kind':'added' if name not in before else 'removed' if name not in after else 'changed','before':before.get(name),'after':after.get(name)} for name in sorted(set(before)|set(after)) if before.get(name)!=after.get(name) or (name in before)!=(name in after)]
        return jsonify(**suggestion_meta(r,upstream),changes=changes,license=upstream['license'])
    @app.post('/flapsoft/suggestions/<sid>/<action>')
    @atomic
    def flapsoft_suggestion_action(sid,action):
        p=protect();d=data()
        if action=='withdraw':
            r=store.db.execute('SELECT * FROM flapsoft_suggestions WHERE id=? AND principal=?',(sid,p)).fetchone()
            if not r:abort(404)
            if r['state']=='accepted':abort(409,description='Accepted versions belong to the receiving project and cannot be withdrawn.')
            store.db.execute('DELETE FROM flapsoft_suggestions WHERE id=?',(sid,))
            return jsonify(state='withdrawn',accepted_revision=None)
        r,upstream=suggestion(sid)
        if action not in ('accept','decline'):abort(404)
        if p!=upstream['principal']:abort(403)
        if r['state']!='open':abort(409,description='This suggestion has already been resolved.')
        accepted=None
        if action=='accept':
            revision(upstream,d)
            if upstream['revision']!=r['base_revision']:abort(409,description='The original project changed. This suggestion cannot overwrite it; request a fresh edition.')
            if upstream['revision']>=200:abort(413)
            quota(p,len(r['files'].encode()))
            accepted=upstream['revision']+1
            version_write(upstream['id'],accepted,r['files'],'Accepted suggestion: '+r['title'])
            store.db.execute('INSERT INTO flapsoft_acceptances VALUES(?,?,?,?,?,?,?)',(upstream['id'],accepted,sid,r['fork'],r['source_revision'],r['base_revision'],r['digest']))
            store.db.execute('UPDATE flapsoft_projects SET revision=?,updated=? WHERE id=?',(accepted,time.time(),upstream['id']))
        state={'accept':'accepted','decline':'declined'}[action]
        store.db.execute('UPDATE flapsoft_suggestions SET state=?,accepted_revision=?,updated=? WHERE id=?',(state,accepted,time.time(),sid))
        return jsonify(state=state,accepted_revision=accepted)

    @app.post('/flapsoft/projects/<pid>/report')
    @atomic
    def flapsoft_report(pid):
        with store.transaction():
            p=protect(); project(pid); d=data()
            try: reason=text(d.get('reason'),1000)
            except ValueError as e: return jsonify(error=str(e)),400
            store.db.execute('INSERT INTO flapsoft_reports VALUES(?,?,?,?) ON CONFLICT(project,principal) DO UPDATE SET reason=excluded.reason,created=excluded.created',(pid,p,reason,time.time()))
            return jsonify(reported=True)
    @app.get('/flapsoft/moderation')
    @atomic
    def flapsoft_moderation():
        if not admin(who()): abort(403)
        return jsonify(reports=[dict(r) for r in store.db.execute('SELECT r.project,r.reason,r.created,p.name FROM flapsoft_reports r JOIN flapsoft_projects p ON p.id=r.project ORDER BY r.created DESC LIMIT 200')])
    @app.post('/flapsoft/projects/<pid>/moderate')
    @atomic
    def flapsoft_moderate(pid):
        with store.transaction():
            p=protect()
            if not admin(p): abort(403)
            d=data(); row=store.db.execute('SELECT principal FROM flapsoft_projects WHERE id=?',(pid,)).fetchone()
            if not row: abort(404)
            try: reason=text(d.get('reason'),1000)
            except ValueError as e: return jsonify(error=str(e)),400
            if d.get('action')=='hide':
                old=store.db.execute('SELECT revision FROM flapsoft_projects WHERE id=?',(pid,)).fetchone()[0]
                encoded=store.db.execute('SELECT files FROM flapsoft_versions WHERE project=? AND version=?',(pid,old)).fetchone()[0]
                version_write(pid,old+1,encoded,'Publication withdrawn by moderator')
                store.db.execute('UPDATE flapsoft_projects SET public=0,revision=? WHERE id=?',(old+1,pid))
            elif d.get('action') in ('restrict','restore'):
                store.db.execute('INSERT INTO flapsoft_restrictions VALUES(?,?,?) ON CONFLICT(principal) DO UPDATE SET restricted=excluded.restricted,reason=excluded.reason',(row[0],int(d['action']=='restrict'),reason))
            else: abort(400)
            store.db.execute('DELETE FROM flapsoft_reports WHERE project=?',(pid,))
            return jsonify(changed=True)

def export(store,principal):
    def visible_contributor(p):
        row=store.db.execute('SELECT p.enabled,l.snapshot FROM principals p JOIN lifecycle_state l ON l.principal=p.id WHERE p.id=?',(p,)).fetchone()
        state=json.loads(row['snapshot']) if row else {}
        return bool(row and row['enabled'] and state.get('active') and state.get('verified') and not state.get('deleted') and not store.db.execute('SELECT 1 FROM flapsoft_restrictions WHERE principal=? AND restricted=1',(p,)).fetchone())
    return {'received_suggestions':[dict(r) for r in store.db.execute('SELECT s.* FROM flapsoft_suggestions s JOIN flapsoft_projects p ON p.id=s.project WHERE p.principal=?',(principal,)) if visible_contributor(r['principal'])],
            'accepted_changes':[dict(r) for r in store.db.execute('SELECT a.* FROM flapsoft_acceptances a JOIN flapsoft_projects p ON p.id=a.project WHERE p.principal=?',(principal,))],
            'suggestions':[dict(r) for r in store.db.execute('SELECT * FROM flapsoft_suggestions WHERE principal=?',(principal,))],
            'fork_bases':[dict(r) for r in store.db.execute('SELECT b.* FROM flapsoft_fork_bases b JOIN flapsoft_projects p ON p.id=b.fork WHERE p.principal=?',(principal,))],
            'projects':[{**dict(p),'versions':[dict(v) for v in store.db.execute('SELECT version,files,message,digest,created FROM flapsoft_versions WHERE project=? ORDER BY version',(p['id'],))]} for p in store.db.execute('SELECT id,name,description,license,public,revision,created,updated,parent FROM flapsoft_projects WHERE principal=?',(principal,))],
            'ideas':[dict(r) for r in store.db.execute('SELECT id,project,title,body,closed,created FROM flapsoft_issues WHERE principal=?',(principal,))],
            'comments':[dict(r) for r in store.db.execute('SELECT id,issue,body,created FROM flapsoft_comments WHERE principal=?',(principal,))]}

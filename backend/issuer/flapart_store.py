"""Bounded private artwork storage and independently frozen public PNGs."""
import base64, binascii, hashlib, json, re, secrets, struct, time, zlib
MAX_PROJECT=16*1024*1024
MAX_PNG=12*1024*1024
MAX_DIMENSION=4096
MAX_PROJECTS=24
ACCOUNT_QUOTA=384*1024*1024
GLOBAL_QUOTA=4*1024*1024*1024
SCHEMA={
'flapart_projects':'''CREATE TABLE flapart_projects(id TEXT PRIMARY KEY,principal TEXT NOT NULL REFERENCES principals(id) ON DELETE CASCADE,title TEXT NOT NULL,project TEXT NOT NULL,revision INTEGER NOT NULL,created REAL NOT NULL,updated REAL NOT NULL)''',
'flapart_publications':'''CREATE TABLE flapart_publications(id TEXT PRIMARY KEY,project_id TEXT NOT NULL UNIQUE REFERENCES flapart_projects(id) ON DELETE CASCADE,principal TEXT NOT NULL REFERENCES principals(id) ON DELETE CASCADE,title TEXT NOT NULL,description TEXT NOT NULL,png BLOB NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,sha256 TEXT NOT NULL,profile INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL)''',
'flapart_forum_art':'''CREATE TABLE flapart_forum_art(item TEXT PRIMARY KEY REFERENCES forum_items(id) ON DELETE CASCADE,publication TEXT NOT NULL REFERENCES flapart_publications(id) ON DELETE CASCADE)'''}
class Conflict(Exception):pass
class Quota(Exception):pass
class Missing(Exception):pass

def normalize(sql):return ''.join(sql.lower().split())
def install(db):
    """Offline additive provisioning, never called by request registration."""
    if db.in_transaction:raise ValueError('Offline migration requires its own transaction')
    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
    try:
        for name,sql in SCHEMA.items():
            old=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
            if old and normalize(old[0])!=normalize(sql):raise ValueError('Flapart schema conflict')
            if not old:db.execute(sql)
        if db.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Foreign key violation')
        db.commit()
    except BaseException:db.rollback();raise

def validate_schema(db):
    for name,sql in SCHEMA.items():
        old=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()
        if not old or normalize(old[0])!=normalize(sql):raise ValueError('Offline Flapart schema required')

def active(db,p):
    row=db.execute('SELECT enabled FROM principals WHERE id=?',(p,)).fetchone()
    state=db.execute('SELECT snapshot FROM lifecycle_state WHERE principal=?',(p,)).fetchone()
    state=json.loads(state[0]) if state else {}
    return bool(row and row[0] and state.get('active') and state.get('verified') and not state.get('deleted'))

def text(value,limit,empty=False):
    if not isinstance(value,str) or len(value)>limit or (not empty and not value.strip()) or any((ord(c)<32 and c not in '\n\t') or 0xD800<=ord(c)<=0xDFFF for c in value):raise ValueError('Invalid text')
    return value.strip()

def encode(project):
    if not isinstance(project,dict):raise ValueError('Project object required')
    # This is private inert JSON. No HTML, SVG, URL or code is rendered server-side.
    try:value=json.dumps(project,ensure_ascii=False,allow_nan=False,separators=(',',':'))
    except (ValueError,TypeError,RecursionError):raise ValueError('Invalid project') from None
    try:size=len(value.encode())
    except UnicodeError:raise ValueError('Invalid project text') from None
    if size>MAX_PROJECT:raise Quota('Project too large')
    return value

def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
def png_clean(value):
    if not isinstance(value,str) or not value.startswith('data:image/png;base64,') or len(value)>MAX_PNG*4//3+128:raise ValueError('PNG required')
    try:raw=base64.b64decode(value[22:],validate=True)
    except (ValueError,binascii.Error):raise ValueError('Invalid PNG encoding') from None
    if len(raw)>MAX_PNG:raise Quota('PNG too large')
    if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('PNG signature')
    pos=8;ihdr=None;compressed=[];ended=False;idat_seen=False;idat_closed=False
    while pos<len(raw):
        if pos+12>len(raw):raise ValueError('Truncated PNG')
        size=struct.unpack('>I',raw[pos:pos+4])[0];kind=raw[pos+4:pos+8];end=pos+12+size
        if end>len(raw) or size>MAX_PNG:raise ValueError('PNG chunk length')
        data=raw[pos+8:pos+8+size];crc=struct.unpack('>I',raw[pos+8+size:end])[0]
        if binascii.crc32(kind+data)&0xffffffff!=crc:raise ValueError('PNG checksum')
        if ihdr is None and kind!=b'IHDR':raise ValueError('PNG header first')
        if kind==b'IHDR':
            if ihdr is not None or size!=13:raise ValueError('PNG header')
            width,height,depth,color,compression,filtration,interlace=struct.unpack('>IIBBBBB',data)
            if not 1<=width<=MAX_DIMENSION or not 1<=height<=MAX_DIMENSION or depth!=8 or color not in (2,6) or compression or filtration or interlace:raise ValueError('Export a noninterlaced RGB or RGBA canvas PNG up to4096 pixels')
            ihdr=data
        elif kind==b'IDAT':
            if idat_closed:raise ValueError('Noncontiguous PNG data')
            idat_seen=True;compressed.append(data)
        elif kind==b'IEND':
            if size or end!=len(raw) or not idat_seen:raise ValueError('PNG ending')
            ended=True;break
        else:
            if idat_seen:idat_closed=True
            if kind in (b'acTL',b'fcTL',b'fdAT') or not kind[0]&32:raise ValueError('Unsupported PNG')
            # Ancillary metadata never enters the sanitized public result.
        pos=end
    if not ended:raise ValueError('PNG missing ending')
    row=width*(4 if color==6 else 3)+1;expected=row*height
    decoder=zlib.decompressobj()
    try:pixels=decoder.decompress(b''.join(compressed),expected+1)
    except zlib.error:raise ValueError('PNG compression') from None
    if len(pixels)!=expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or any(pixels[y*row]>4 for y in range(height)):raise ValueError('PNG pixels')
    clean=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',ihdr)+chunk(b'IDAT',zlib.compress(pixels,6))+chunk(b'IEND',b'')
    if len(clean)>MAX_PNG:raise Quota('PNG too large')
    return clean,width,height

class Repository:
    def __init__(self,store):self.store=store
    @property
    def db(self):return self.store.db
    def owned(self,p,ident):
        if not active(self.db,p):raise Missing()
        row=self.db.execute('SELECT * FROM flapart_projects WHERE id=? AND principal=?',(ident,p)).fetchone()
        if not row:raise Missing()
        return row
    def check(self,row,expected):
        if type(expected) is not int or expected!=row['revision']:raise Conflict()
    def quota(self,p,extra):
        used=self.db.execute('SELECT coalesce(sum(length(CAST(project AS BLOB))),0) FROM flapart_projects WHERE principal=?',(p,)).fetchone()[0]+self.db.execute('SELECT coalesce(sum(length(png)),0) FROM flapart_publications WHERE principal=?',(p,)).fetchone()[0]
        total=self.db.execute('SELECT coalesce(sum(length(CAST(project AS BLOB))),0) FROM flapart_projects').fetchone()[0]+self.db.execute('SELECT coalesce(sum(length(png)),0) FROM flapart_publications').fetchone()[0]
        if used+extra>ACCOUNT_QUOTA or total+extra>GLOBAL_QUOTA:raise Quota()
    def metadata(self,row,project=False):
        pub=self.db.execute('SELECT id,title,description,width,height,profile,created FROM flapart_publications WHERE project_id=?',(row['id'],)).fetchone()
        out={k:row[k] for k in ('id','title','revision','created','updated')};out['publication']=dict(pub) if pub else None
        if pub:out['publication'].update(url='https://accounts.flaptown.com/flapart/public/'+pub['id']+'.png',profile=bool(pub['profile']))
        if project:out['project']=json.loads(row['project'])
        return out
    def save(self,p,title,project,ident=None,expected=None):
        title=text(title,160);encoded=encode(project)
        with self.store.transaction():
            if not active(self.db,p):raise Missing()
            now=time.time()
            if ident:
                old=self.owned(p,ident);self.check(old,expected);self.quota(p,len(encoded.encode())-len(old['project'].encode()))
                self.db.execute('UPDATE flapart_projects SET title=?,project=?,revision=revision+1,updated=? WHERE id=?',(title,encoded,now,ident))
            else:
                if self.db.execute('SELECT count(*) FROM flapart_projects WHERE principal=?',(p,)).fetchone()[0]>=MAX_PROJECTS:raise Quota()
                self.quota(p,len(encoded.encode()));ident=secrets.token_hex(16)
                self.db.execute('INSERT INTO flapart_projects VALUES(?,?,?,?,1,?,?)',(ident,p,title,encoded,now,now))
            return self.metadata(self.owned(p,ident),True)
    def publish(self,p,ident,data):
        if data['public'] is not True or type(data['profile']) is not bool:raise ValueError('Explicit publication required')
        title=text(data['title'],160);description=text(data['description'],1000,True)
        png,width,height=png_clean(data['png'])
        with self.store.transaction():
            row=self.owned(p,ident);self.check(row,data['expectedRevision'])
            old=self.db.execute('SELECT length(png) FROM flapart_publications WHERE project_id=?',(ident,)).fetchone()
            self.quota(p,len(png)-(old[0] if old else 0))
            # New unpredictable URL per frozen publication; old URL revoked, never changed in place.
            self.db.execute('DELETE FROM flapart_publications WHERE project_id=?',(ident,))
            pub=secrets.token_hex(16)
            self.db.execute('INSERT INTO flapart_publications VALUES(?,?,?,?,?,?,?,?,?,?,?)',(pub,ident,p,title,description,png,width,height,hashlib.sha256(png).hexdigest(),int(data['profile']),time.time()))
            self.db.execute('UPDATE flapart_projects SET revision=revision+1,updated=? WHERE id=?',(time.time(),ident))
            return self.metadata(self.owned(p,ident))
    def remove(self,p,ident,expected,delete=False):
        with self.store.transaction():
            row=self.owned(p,ident);self.check(row,expected)
            if delete:self.db.execute('DELETE FROM flapart_projects WHERE id=?',(ident,));return dict(deleted=True)
            self.db.execute('DELETE FROM flapart_publications WHERE project_id=?',(ident,));self.db.execute('UPDATE flapart_projects SET revision=revision+1,updated=? WHERE id=?',(time.time(),ident))
            return self.metadata(self.owned(p,ident))
    def public(self,ident):
        row=self.db.execute('SELECT * FROM flapart_publications WHERE id=?',(ident,)).fetchone()
        if not row or not active(self.db,row['principal']):raise Missing()
        return row

def catalog_records(store,p,origin):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='flapart_publications'").fetchone() or not active(store.db,p):return []
    return [dict(id='f'+r['id'],ownerId=p,visibility='public',title=r['title'],description=r['description'],url=origin+'/flapart/public/'+r['id']+'.png') for r in store.db.execute('SELECT id,title,description FROM flapart_publications WHERE principal=? AND profile=1 ORDER BY id LIMIT 24',(p,))]

def forum_art(store,item):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='flapart_forum_art'").fetchone():return None
    row=store.db.execute('SELECT a.publication FROM flapart_forum_art a JOIN forum_items f ON f.id=a.item WHERE a.item=? AND f.deleted=0',(item,)).fetchone()
    if not row:return None
    try:pub=Repository(store).public(row[0])
    except Missing:return None
    return dict(id=pub['id'],title=pub['title'],url='https://accounts.flaptown.com/flapart/public/'+pub['id']+'.png',width=pub['width'],height=pub['height'])

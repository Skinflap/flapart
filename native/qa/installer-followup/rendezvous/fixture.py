"""Deterministic harmless exchange bytes. No application or private material."""
import io,zipfile
import protocol as p

def payloads():
 out=io.BytesIO()
 with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_STORED) as z:
  entry=zipfile.ZipInfo('README.txt',date_time=(2026,1,1,0,0,0));entry.external_attr=0o100600<<16
  z.writestr(entry,b'Flapart harmless rendezvous fixture v1. No native application.\n')
 return {'candidate.zip':out.getvalue(),'candidate-inventory.json':p.encode({'schema':1,'fixture':'rendezvous-v1','native_executed':False}),'candidate-manifest.json':p.encode({'schema':1,'fixture':'rendezvous-v1','release_qualified':False})}

def pins():
 values=payloads()
 return {'candidate_sha256':p.digest(values['candidate.zip']),'candidate_bytes':len(values['candidate.zip']),'inventory_sha256':p.digest(values['candidate-inventory.json']),'manifest_sha256':p.digest(values['candidate-manifest.json'])}

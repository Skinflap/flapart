#!/usr/bin/env python3
"""Run inside packaged Python/PyQt. Local fixtures, no ignored TLS errors.
Usage: python https-validation-probe.py --openssl /path/to/openssl --output receipt.json
The openssl CLI generates disposable CA/server keys only in TemporaryDirectory.
"""
import argparse,datetime,http.server,json,pathlib,ssl,subprocess,tempfile,threading,urllib.request,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from tls_fixture import command as fixture_command
p=argparse.ArgumentParser();p.add_argument('--openssl',required=True);p.add_argument('--output',required=True);p.add_argument('--minimum',default='3.5.9');p.add_argument('--official-url',default='https://www.python.org/');a=p.parse_args()
from PyQt5.QtCore import QCoreApplication,QEventLoop,QTimer,QUrl
from PyQt5.QtNetwork import QNetworkAccessManager,QNetworkRequest,QSslConfiguration,QSslCertificate,QSslSocket,QSslError
app=QCoreApplication.instance() or QCoreApplication([])
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'flapart-tls-ok')
 def log_message(self,*args):pass
result={'python_openssl':ssl.OPENSSL_VERSION,'qt_openssl_runtime':QSslSocket.sslLibraryVersionString(),'qt_openssl_build':QSslSocket.sslLibraryBuildVersionString(),'cases':{}}
try:
 assert QSslSocket.supportsSsl(), 'Qt SSL unavailable'
 minimum=tuple(map(int,a.minimum.split('.')))
 for name in ['python_openssl','qt_openssl_runtime']:
  version=tuple(map(int,result[name].split()[1].split('.')));assert version>=minimum,(name,result[name])
 with tempfile.TemporaryDirectory(prefix='flapart-tls-test-') as tmp:
  root=pathlib.Path(tmp)
  def command(*args):fixture_command(a.openssl,root,*args)
  command('req','-x509','-newkey','rsa:2048','-nodes','-keyout','ca.key','-out','ca.pem','-days','2','-subj','/CN=Flapart disposable QA CA','-addext','basicConstraints=critical,CA:TRUE','-addext','keyUsage=critical,keyCertSign,cRLSign')
  command('req','-newkey','rsa:2048','-nodes','-keyout','server.key','-out','server.csr','-subj','/CN=localhost')
  (root/'extensions').write_text('subjectAltName=DNS:localhost\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
  command('x509','-req','-in','server.csr','-CA','ca.pem','-CAkey','ca.key','-CAcreateserial','-out','server.pem','-days','1','-extfile','extensions')
  (root/'index.txt').write_text('');(root/'serial').write_text('1000\n');(root/'newcerts').mkdir()
  (root/'ca.cnf').write_text('[ca]\ndefault_ca=qa\n[qa]\ndatabase=index.txt\nserial=serial\nnew_certs_dir=newcerts\ncertificate=ca.pem\nprivate_key=ca.key\ndefault_md=sha256\npolicy=qa_policy\n[qa_policy]\ncommonName=supplied\n')
  command('ca','-batch','-config','ca.cnf','-in','server.csr','-out','expired.pem','-startdate','20200101000000Z','-enddate','20200102000000Z','-extfile','extensions')
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(root/'server.pem',root/'server.key');server.socket=ctx.wrap_socket(server.socket,server_side=True)
  threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   for name,host,trust,expected in [('valid','localhost',True,True),('unknown_ca','localhost',False,False),('hostname_mismatch','127.0.0.1',True,False),('expired','localhost',True,False)]:
    if name=='expired':ctx.load_cert_chain(root/'expired.pem',root/'server.key')
    url=f'https://{host}:{server.server_port}/';case={}
    pyctx=ssl.create_default_context(cafile=str(root/'ca.pem')) if trust else ssl.create_default_context();pyctx.minimum_version=ssl.TLSVersion.TLSv1_2
    try:
     with urllib.request.urlopen(url,context=pyctx,timeout=8) as response:case['python_ok']=response.read()==b'flapart-tls-ok'
    except urllib.error.URLError as e:
     assert isinstance(e.reason,ssl.SSLCertVerificationError),str(e);case.update(python_ok=False,python_certificate_rejected=True,python_verify_code=e.reason.verify_code)
    manager=QNetworkAccessManager();request=QNetworkRequest(QUrl(url));config=QSslConfiguration.defaultConfiguration();config.setPeerVerifyMode(QSslSocket.VerifyPeer)
    if trust:config.setCaCertificates(QSslCertificate.fromPath(str(root/'ca.pem')))
    request.setSslConfiguration(config);reply=manager.get(request);loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);reply.finished.connect(loop.quit);errors=[];error_codes=[];reply.sslErrors.connect(lambda es:(errors.extend(e.errorString() for e in es),error_codes.extend(int(e.error()) for e in es)));timer.start(10000);loop.exec_();timer.stop()
    case.update(qt_ok=reply.isFinished() and int(reply.error())==0 and bytes(reply.readAll())==b'flapart-tls-ok',qt_ssl_errors=errors,qt_ssl_error_codes=error_codes,qt_error=int(reply.error()),qt_finished=reply.isFinished());reply.abort();reply.deleteLater()
    assert case['python_ok']==expected and case['qt_ok']==expected,(name,case)
    if not expected:assert case['qt_ssl_errors'],(name,case)
    if name=='expired':assert case.get('python_verify_code')==10 and int(QSslError.CertificateExpired) in error_codes,(name,case)
    result['cases'][name]=case
  finally:server.shutdown();server.server_close()
 assert a.official_url.startswith('https://'), 'HTTPS required'
 with urllib.request.urlopen(a.official_url,context=ssl.create_default_context(),timeout=15) as response:
  result['official_python']={'status':response.status,'verified':True};response.read(256)
 manager=QNetworkAccessManager();request=QNetworkRequest(QUrl(a.official_url));reply=manager.get(request);loop=QEventLoop();timer=QTimer();timer.setSingleShot(True);timer.timeout.connect(loop.quit);reply.finished.connect(loop.quit);errors=[];reply.sslErrors.connect(lambda es:errors.extend(e.errorString() for e in es));timer.start(15000);loop.exec_();timer.stop()
 result['official_qt']={'finished':reply.isFinished(),'error':int(reply.error()),'ssl_errors':errors,'status':reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)}
 assert reply.isFinished() and int(reply.error())==0 and not errors,result['official_qt']
 reply.deleteLater()
 result['passed']=True
except Exception as e:
 result['passed']=False;result['error']=repr(e)
finally:pathlib.Path(a.output).write_text(json.dumps(result,indent=2)+'\n')
raise SystemExit(0 if result['passed'] else 1)

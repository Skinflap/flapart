"""Browser validation, resource bounds and strict CSP checks. Local server required."""
import sys,json,struct,base64,zlib
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8937'
CSP="default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob: https://accounts.flaptown.com; connect-src 'self' https://accounts.flaptown.com; base-uri 'none'; object-src 'none'; form-action 'self'"
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1200,'height':900},accept_downloads=True)
 page.route('https://accounts.flaptown.com/**',lambda route:route.fulfill(status=200,content_type='application/json',body='{"authenticated":false}'))
 def csp(route):
  response=route.fetch();route.fulfill(response=response,headers={**response.headers,'Content-Security-Policy':CSP})
 page.route(base+'/',csp)
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.add_init_script('window.violations=[];document.addEventListener("securitypolicyviolation",e=>window.violations.push({directive:e.effectiveDirective,blocked:e.blockedURI}));')
 page.goto(base);page.wait_for_function('!!window.flapart');page.wait_for_timeout(300)
 project=page.evaluate('window.flapart.exportProject()')
 invalid=[]
 for change in [dict(version=2),dict(width=4097),dict(width=1.1),dict(height=0),dict(layers=[]),dict(name='x'*101),dict(layers=project['layers']*17)]:invalid.append({**project,**change})
 for change in [dict(opacity=-1),dict(opacity=2),dict(visible='yes'),dict(blend='copy'),dict(name='x'*101),dict(data='data:image/svg+xml,<svg onload=alert(1)>'),dict(data=project['layers'][0]['data'][:-10])]:invalid.append({**project,'layers':[{**project['layers'][0],**change}]})
 for bad in invalid:
  result=page.evaluate('async p=>{try{await window.flapart.loadProject(p);return false}catch{return true}}',bad)
  assert result,'Accepted invalid project'
 assert page.evaluate('window.flapart.exportProject()')==project,'Invalid input changed canvas'
 # Check all-pixel fill and undo on an empty layer.
 page.click('[data-tool="fill"]');box=page.locator('#canvas').bounding_box();page.mouse.click(box['x']+10,box['y']+10)
 assert page.evaluate('Array.from(document.getElementById("canvas").getContext("2d").getImageData(1100,700,1,1).data)')==[195,154,147,255]
 page.click('#undo')
 # Selection contains fill.
 page.click('[data-tool="select"]');page.mouse.move(box['x']+20,box['y']+20);page.mouse.down();page.mouse.move(box['x']+80,box['y']+80);page.mouse.up();page.click('[data-tool="fill"]');page.mouse.click(box['x']+40,box['y']+40)
 assert page.evaluate('Array.from(document.getElementById("canvas").getContext("2d").getImageData(1100,700,1,1).data)')==[255,255,255,255]
 page.click('#undo');page.click('#deselect',force=True)
 # Tiny valid import, then impossible dimensions rejected before decoding.
 png=base64.b64decode(project['layers'][0]['data'].split(',')[1])
 page.locator('#image-file').set_input_files({'name':'drawing.png','mimeType':'image/png','buffer':png})
 page.wait_for_timeout(300);assert page.locator('#status').inner_text().startswith('image added'),page.locator('#status').inner_text()
 assert len(page.evaluate('window.flapart.exportProject()')['layers'])==3
 bomb=bytearray(png);bomb[16:20]=struct.pack('>I',100000)
 page.locator('#image-file').set_input_files({'name':'oversize.png','mimeType':'image/png','buffer':bytes(bomb)})
 page.wait_for_timeout(100);assert 'exceeds 64 million' in page.locator('#status').inner_text()
 assert len(page.evaluate('window.flapart.exportProject()')['layers'])==3
 # All export formats produce the expected file magic.
 for fmt,magic in [('jpeg',b'\xff\xd8'),('webp',b'RIFF')]:
  page.click('#export');page.select_option('#export-format',fmt)
  with page.expect_download() as dl:page.click('#dialog-ok')
  assert open(dl.value.path(),'rb').read(4).startswith(magic)
 page.click('#account-save');page.wait_for_selector('.account-dialog[open]');page.wait_for_timeout(200);assert 'Sign in' in page.locator('.account-notice').inner_text()
 assert not page.evaluate('window.violations'),page.evaluate('window.violations')
 assert not errors,errors
 browser.close();print(json.dumps({'passed':True,'checks':['strict CSP','14 malformed project variants','failed imports preserve work','full canvas fill','selection bounds','PNG import','oversized image rejected before decode','JPEG magic','WebP magic','signed-out account flow']}))

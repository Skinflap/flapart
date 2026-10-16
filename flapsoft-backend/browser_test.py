import sys,json,mimetypes
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0,str(Path(__file__).parent))
from test_flapsoft import FlapsoftTest
from playwright.sync_api import sync_playwright
root=Path('/home/skinflap/Projects/Flapart');site=Path('/home/skinflap/Projects/Flaptown/site');test=FlapsoftTest();test.setUp(); errors=[]
try:
 with sync_playwright() as p:
  browser=p.chromium.launch(headless=True,executable_path='/home/skinflap/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome')
  page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:print('console',m.type,m.text) if m.type=='error' else None);page.on('dialog',lambda d:d.accept('A useful response'))
  def route(r):
   u=urlsplit(r.request.url)
   if u.hostname=='accounts.flaptown.com':
    headers={k:v for k,v in r.request.headers.items() if k.lower() in ('content-type','x-csrf-token')};headers['Origin']='https://flaptown.com'
    response=test.c.open(u.path+('?' +u.query if u.query else ''),method=r.request.method,base_url='https://identity.example',headers=headers,data=r.request.post_data)
    r.fulfill(status=response.status_code,body=response.data,headers={k:v for k,v in response.headers if k.lower()!='set-cookie'});return
   if u.hostname=='flaptown.com':
    path=u.path
    f=(root/'flapsoft'/path.removeprefix('/flapsoft/')) if path.startswith('/flapsoft/') else site/path.lstrip('/')
    if path.endswith('/'):f=f/'index.html'
    if f.is_file():r.fulfill(status=200,body=f.read_bytes(),content_type=mimetypes.guess_type(str(f))[0] or 'application/octet-stream',headers={'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self' https://accounts.flaptown.com; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"})
    else:r.fulfill(status=404,body='Not found')
    return
   r.abort()
  page.route('**/*',route);page.goto('https://flaptown.com/flapsoft/');page.get_by_text('Account connected. New projects and editions start private.',exact=True).wait_for(timeout=10000)
  page.click('#new-project');page.fill('#new-form [name=name]','Browser qualification project');page.fill('#new-form [name=description]','Disposable synthetic workflow');page.click('#new-form button[type=submit]');page.wait_for_function("() => document.querySelector('#project-name').textContent === 'Browser qualification project'")
  page.fill('#source','# hello\n\nA real browser edit.');page.fill('#message','Improve the introduction');page.click('#save-version');page.wait_for_function("() => document.querySelector('#project-meta').textContent.includes('version 2 of 2')")
  page.click('#visibility');page.wait_for_function("() => document.querySelector('#project-meta').textContent.startsWith('public')")
  page.click('#new-issue');page.fill('#issue-form [name=title]','Add an example');page.fill('#issue-form [name=body]','Show the first step.');page.click('#issue-form button[type=submit]');page.wait_for_function("() => document.querySelector('#issue-title').textContent === 'Add an example'")
  page.fill('#comment','An example is coming.');page.click('#reply');page.wait_for_function("() => document.querySelector('#comments').textContent.includes('An example is coming.')")
  page.click('#close-issue');page.wait_for_function("() => document.querySelector('#close-issue').textContent === 'reopen idea'")
  with page.expect_download() as download:page.click('#download-source')
  d=download.value;assert d.suggested_filename.endswith('.zip')
  page.screenshot(path=str(root/'evidence/flapsoft-desktop.png'),full_page=True)
  page.click('#fork');page.wait_for_function("() => document.querySelector('#project-name').textContent.includes('my edition')")
  assert page.locator('#project-meta').text_content().startswith('private')
  page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
  page.screenshot(path=str(root/'evidence/flapsoft-mobile.png'),full_page=True)
  assert not errors,errors
  (root/'evidence/flapsoft-browser.json').write_text(json.dumps({'passed':True,'checks':['private create','source edit/version','publication','idea/reply/resolve','source ZIP download','private fork','390px no overflow','strict CSP','no page errors'],'errors':errors},indent=2)+'\n');browser.close()
finally:test.tearDown()
print('Flapsoft browser journey PASS')

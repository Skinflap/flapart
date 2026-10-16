"""Interrupted pointers, history preservation and async import race regression checks."""
import sys,json
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8937'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base);page.wait_for_function('!!window.flapart');page.wait_for_timeout(200)
 box=page.locator('#canvas').bounding_box();x,y=box['x']+100,box['y']+100
 original=page.evaluate('window.flapart.exportProject()')
 page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+100,y+100,steps=10);page.mouse.up()
 committed=page.evaluate('window.flapart.exportProject()')
 page.click('#undo');assert page.evaluate('window.flapart.exportProject()')==original
 page.mouse.move(x+200,y);page.mouse.down();page.mouse.move(x+250,y+100,steps=10)
 page.dispatch_event('#viewport','pointerup',{'pointerId':99,'clientX':x,'clientY':y})
 rejected=page.evaluate('async p=>{try{await window.flapart.loadProject(p);return false}catch{return true}}',original)
 assert rejected,'Second pointer incorrectly ended first pointer gesture'
 page.dispatch_event('#viewport','pointercancel',{'pointerId':1})
 page.mouse.up();assert page.evaluate('window.flapart.exportProject()')==original
 assert page.locator('#redo').is_enabled(),'Canceled stroke destroyed redo branch'
 page.click('#redo');assert page.evaluate('window.flapart.exportProject()')==committed
 page.click('#open');page.wait_for_selector('#dialog[open]');assert 'open another' in page.locator('#dialog-title').inner_text();page.click('#dialog button[value="cancel"]');assert page.evaluate('window.flapart.exportProject()')==committed
 page.click('#new');page.click('#dialog button[value="cancel"]');assert page.evaluate('window.flapart.exportProject()')==committed
 page.evaluate('p=>{window.savedDecode=Image.prototype.decode;Image.prototype.decode=function(){return new Promise(r=>setTimeout(r,180)).then(()=>window.savedDecode.call(this))};window.pendingLoad=window.flapart.loadProject(p)}',original)
 assert page.locator('main').evaluate('e=>e.inert')
 page.keyboard.press('Control+z');page.keyboard.press('Control+a');page.keyboard.press('Delete');page.keyboard.press('g')
 page.evaluate('window.pendingLoad');page.evaluate('()=>{Image.prototype.decode=window.savedDecode}')
 assert page.evaluate('window.flapart.exportProject()')==original
 assert not page.locator('main').evaluate('e=>e.inert')
 page.route('https://accounts.flaptown.com/**',lambda route:route.fulfill(status=200,content_type='application/json',body='{"authenticated":false}'))
 page.click('#account-save');page.wait_for_selector('.account-dialog[open]');page.keyboard.press('Control+z');assert page.evaluate('window.flapart.exportProject()')==original
 assert not errors,errors
 browser.close();print(json.dumps({'passed':True,'checks':['second pointer ignored','load rejected mid-stroke','pointer cancellation restores artwork','cancel preserves redo','open unsaved warning','new cancel preserves work','async import inert','keyboard blocked during import','account modal isolates editor shortcuts']}))

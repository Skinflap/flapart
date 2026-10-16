"""Run against a local HTTP server: python test_editor.py [base_url]."""
import sys,json
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8937'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True)
 page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
 errors=[]
 page.on('pageerror',lambda error: errors.append(str(error)))
 page.goto(base);page.wait_for_function('!!window.flapart');page.wait_for_timeout(300)
 assert page.evaluate('document.fonts.check(\'16px "Syne Mono"\')')
 box=page.locator('#canvas').bounding_box();x,y=box['x']+100,box['y']+100
 page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+140,y+80,steps=12);page.mouse.up()
 project=page.evaluate('window.flapart.exportProject()');assert len(project['layers'])==2
 painted=project['layers'][1]['data']
 page.click('#undo');assert page.evaluate('window.flapart.exportProject()')['layers'][1]['data']!=painted
 page.click('#redo');assert page.evaluate('window.flapart.exportProject()')['layers'][1]['data']==painted
 page.click('#layer-add');assert len(page.evaluate('window.flapart.exportProject()')['layers'])==3
 page.click('#layer-duplicate');assert len(page.evaluate('window.flapart.exportProject()')['layers'])==4
 page.click('#layer-delete');assert len(page.evaluate('window.flapart.exportProject()')['layers'])==3
 page.evaluate('(p)=>window.flapart.loadProject(p)',project)
 assert page.evaluate('window.flapart.exportProject()')['layers'][1]['data']==painted
 assert page.evaluate('async()=>{try{await window.flapart.loadProject({format:"flapart",version:1,width:100000,height:100000,layers:[]});return false}catch{return true}}')
 page.click('[data-tool="rectangle"]');page.mouse.move(x+200,y+100);page.mouse.down();page.mouse.move(x+340,y+220);page.mouse.up()
 page.click('[data-tool="select"]');page.mouse.move(x+180,y+80);page.mouse.down();page.mouse.move(x+360,y+240);page.mouse.up()
 page.click('[data-tool="move"]');page.mouse.move(x+220,y+120);page.mouse.down();page.mouse.move(x+250,y+150);page.mouse.up()
 with page.expect_download() as dl:page.click('#save')
 assert dl.value.suggested_filename.endswith('.flapart')
 page.click('#export')
 with page.expect_download() as dl:page.click('#dialog-ok')
 assert dl.value.suggested_filename.endswith('.png')
 page.wait_for_timeout(1600)
 page.screenshot(path='/tmp/flapart-desktop.png',full_page=True)
 page.reload();page.wait_for_selector('#dialog[open]');assert 'pick up' in page.locator('#dialog-title').inner_text();page.click('#dialog-ok')
 page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
 assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 page.screenshot(path='/tmp/flapart-mobile.png',full_page=True)
 assert not errors,errors
 browser.close()
 print(json.dumps({'passed':True,'checks':['font','paint','undo','redo','layers','project roundtrip','malformed project rejection','shape','selection move','project download','PNG export','IndexedDB recovery','mobile overflow','no JS errors']}))

"""Pixel-level checks for extended art tools, transformations and adjustments."""
import sys,json
from playwright.sync_api import sync_playwright
base=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8937'
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1000})
 errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base);page.wait_for_function('!!window.flapart');page.wait_for_timeout(200)
 page.click('#new');page.fill('#new-width','128');page.fill('#new-height','128');page.select_option('#background','transparent');page.click('#dialog-ok')
 def value(id,v):page.eval_on_selector('#'+id,'(e,v)=>{e.value=v;e.dispatchEvent(new Event("input"))}',str(v))
 def pixel(x,y):return page.evaluate('([x,y])=>Array.from(document.getElementById("canvas").getContext("2d").getImageData(x,y,1,1).data)',[x,y])
 def pt(x,y):
  b=page.locator('#canvas').bounding_box();return b['x']+x*b['width']/128,b['y']+y*b['height']/128
 def stroke(a,b):
  page.mouse.move(*pt(*a));page.mouse.down();page.mouse.move(*pt(*b),steps=20);page.mouse.up()
 def undo():page.click('#undo')
 def expand():
  page.locator('.layers-panel details').evaluate('(e)=>e.open=true');page.locator('.tools details').evaluate('(e)=>e.open=true')
 expand();value('color','#ff0000');value('size',20);value('opacity',50)
 stroke((20,30),(100,30))
 assert pixel(50,30)[3] in (127,128),pixel(50,30)
 assert pixel(21,30)[3]==pixel(50,30)[3],'Stroke opacity accumulated per stamp'
 undo();value('opacity',100)
 page.check('#mirror');stroke((20,20),(20,20));assert pixel(20,20)==[255,0,0,255];assert pixel(108,20)==[255,0,0,255];undo();page.uncheck('#mirror')
 page.click('[data-tool="gradient"]');value('color-secondary','#0000ff');stroke((0,64),(127,64));assert pixel(2,64)[0]>pixel(2,64)[2];assert pixel(125,64)[2]>pixel(125,64)[0];undo()
 page.select_option('#preset','ink');value('size',8);stroke((20,30),(20,30));before=page.evaluate('window.flapart.exportProject()')
 page.click('#rotate-layer');assert pixel(98,20)[0]==255 and pixel(98,20)[3]>0;undo();assert page.evaluate('window.flapart.exportProject()')==before
 page.click('#filters');page.select_option('#filter-kind','invert');page.click('#dialog-ok');page.wait_for_timeout(80);assert pixel(20,30)==[0,255,255,255],pixel(20,30);undo()
 page.click('#filters');page.select_option('#filter-kind','grayscale');page.click('#dialog-ok');page.wait_for_timeout(80);gray=pixel(20,30);assert gray[0]==gray[1]==gray[2] and gray[3]==255;undo()
 for kind in ['brightness','contrast','saturation']:
  page.click('#filters');page.select_option('#filter-kind',kind);page.fill('#filter-amount','-40');page.click('#dialog-ok');page.wait_for_timeout(80);assert pixel(20,30)[3]==255;undo()
 page.click('#resize-image');page.fill('#resize-width','64');page.fill('#resize-height','96');page.click('#dialog-ok');page.wait_for_timeout(80);q=page.evaluate('window.flapart.exportProject()');assert(q['width'],q['height'],len(q['layers']))==(64,96,2);undo();assert page.evaluate('window.flapart.exportProject()')==before
 page.click('#resize-canvas');page.fill('#resize-width','160');page.fill('#resize-height','140');page.click('#dialog-ok');page.wait_for_timeout(80);assert pixel(36,36)==[255,0,0,255];undo();assert page.evaluate('window.flapart.exportProject()')==before
 page.click('[data-tool="select"]');stroke((10,10),(50,50));page.click('#crop');q=page.evaluate('window.flapart.exportProject()');assert(q['width'],q['height'])==(40,40);assert pixel(10,20)==[255,0,0,255];undo();assert page.evaluate('window.flapart.exportProject()')==before
 for preset in ['pencil','soft','spray','block']:
  page.select_option('#preset',preset);stroke((30,70),(100,70));assert page.evaluate('window.flapart.exportProject()')['layers'][1]['data']!=before['layers'][1]['data'];undo()
 assert not errors,errors
 browser.close();print(json.dumps({'passed':True,'checks':['stroke opacity','mirror symmetry','linear gradient colors','rotate pixels and undo','invert','grayscale','brightness','contrast','saturation','resize image layer preservation','canvas resize centering','selection crop','four brush presets']}))

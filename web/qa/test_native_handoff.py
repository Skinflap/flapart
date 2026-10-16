"""Local real-browser native PNG handoff; mocked account reads, never public writes."""
import functools
import http.server
import json
import os
from pathlib import Path
import struct
import threading
import zlib
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_): pass
    def end_headers(self):
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob:; connect-src 'self' https://accounts.flaptown.com; object-src 'none'; base-uri 'self'")
        super().end_headers()

def png(width=32, height=24, transparent=False):
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    pixels = (b'\0' + b'\xbf\x8b\x6f\xff' + (b'\0\0\0\0' if transparent else b'\xbf\x8b\x6f\xff') * (width - 1)) * height
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')

def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT / 'web')))
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    engine = os.environ.get('FLAPART_QA_BROWSER', 'chromium')
    assert engine in ('chromium', 'firefox', 'webkit')
    evidence = ROOT / ('evidence/native-handoff-local' + ('' if engine == 'chromium' else '-' + engine)); evidence.mkdir(parents=True, exist_ok=True)
    errors, calls, checks = [], [], []
    auth = {'authenticated': True}
    try:
        with sync_playwright() as p:
            chrome = Path.home() / '.cache/ms-playwright/chromium-1234/chrome-linux64/chrome'
            browser = getattr(p, engine).launch(headless=True, **({'executable_path': str(chrome)} if engine == 'chromium' and chrome.exists() else {}))
            def new(query='', width=1440):
                context = browser.new_context(viewport={'width': width, 'height': 1000 if width > 500 else 844})
                context.route('https://accounts.flaptown.com/**', account)
                page = context.new_page(); page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(base + '/' + query); page.wait_for_function('() => !!window.flapart'); page.wait_for_timeout(100)
                return context, page
            def account(route):
                request = route.request; calls.append((request.method, request.url))
                if request.method != 'GET':
                    route.abort(); raise AssertionError('Unexpected account mutation')
                data = {'authenticated': auth['authenticated'], 'csrf': 'local-fixture', 'limits': {'projectBytes': 16777216, 'projects': 24}} if request.url.endswith('/session') else {'projects': []}
                route.fulfill(status=200, content_type='application/json', body=json.dumps(data))
            def choose(page, content, kind='image/png', mode='new'):
                if mode == 'new': page.locator('#native-handoff-choose').click()
                with page.expect_file_chooser() as picker:
                    page.locator('#dialog-ok' if mode == 'new' else '#native-handoff-layer').click()
                picker.value.set_files({'name': 'local-art.png', 'mimeType': kind, 'buffer': content})
            for destination in ('profile', 'townhall'):
                calls.clear(); context, page = new('?from=native&destination=' + destination)
                assert page.locator('.native-handoff').count() == 1
                assert not calls and not page.locator('.account-dialog').is_visible()
                before = page.evaluate('async()=>await window.flapart.exportProject()')
                choose(page, png())
                page.wait_for_selector('.account-dialog[open]')
                expected = 'publish image to profile library' if destination == 'profile' else 'publish to townhall'
                page.get_by_role('button', name=expected, exact=True).wait_for()
                opened = page.evaluate('async()=>await window.flapart.exportProject()')
                assert (opened['width'], opened['height'], len(opened['layers'])) == (32, 24, 1)
                assert len(calls) == 1 and calls[0][1].endswith('/flapart/session')
                assert page.locator('.account-dialog').get_by_label('public title').count() == 1
                assert page.evaluate('document.fonts.check(\'16px "Syne Mono"\')')
                page.screenshot(path=str(evidence / (destination + '-review.png')), full_page=True)
                page.locator('.account-dialog').get_by_role('button', name='close', exact=True).click()
                page.locator('#undo').click()
                assert page.evaluate('async()=>await window.flapart.exportProject()') == before
                assert len(calls) == 1
                context.close(); checks.append(destination + ' actual PNG to review, GET only')
            calls.clear(); context, page = new('?from=native&destination=profile', 390)
            before = page.evaluate('window.flapart.getRevision()')
            choose(page, b'not a PNG')
            page.wait_for_function("() => document.querySelector('.handoff-status').textContent.includes('could not be added')")
            assert not calls and page.evaluate('window.flapart.getRevision()') == before
            choose(page, png(), 'image/jpeg')
            assert 'canvas has not changed' in page.locator('.handoff-status').inner_text()
            assert not calls and page.evaluate('window.flapart.getRevision()') == before
            page.locator('#native-handoff-choose').click()
            with page.expect_file_chooser() as picker: page.locator('#dialog-ok').click()
            picker.value.set_files([])
            page.wait_for_function("() => document.querySelector('.handoff-status').textContent.includes('No file chosen')")
            assert not calls and not page.locator('.account-dialog').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.screenshot(path=str(evidence / 'mobile-guidance.png'), full_page=True)
            page.set_viewport_size({'width': 320, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            page.get_by_role('button', name='keep drawing', exact=True).click()
            assert page.locator('.native-handoff').count() == 0
            context.close(); checks.append('corrupt PNG, other MIME, cancellation, mobile overflow and dismiss')
            calls.clear(); auth['authenticated'] = False
            context, page = new('?from=native&destination=profile')
            choose(page, png()); page.get_by_role('button', name='refresh sign-in').wait_for()
            auth['authenticated'] = True
            page.get_by_role('button', name='refresh sign-in').click()
            page.get_by_role('button', name='publish image to profile library', exact=True).wait_for()
            assert len(calls) == 2 and all(method == 'GET' for method, _ in calls)
            context.close(); checks.append('sign-in refresh preserves profile review destination without mutation')
            for query in ('', '?from=native&destination=invalid', '?from=other&destination=profile', '?from=native&from=native&destination=profile', '?from=native&destination=profile&destination=townhall'):
                calls.clear(); context, page = new(query)
                assert not page.locator('.native-handoff').count() and not calls
                context.close()
            calls.clear(); context, page = new()
            page.locator('#account-save').click()
            page.get_by_role('button', name='save a new private copy', exact=True).wait_for()
            assert [url.rsplit('/', 1)[-1] for _, url in calls] == ['session', 'projects']
            context.close()
            context, page = new('?from=native&destination=townhall')
            calls.clear()
            with page.expect_file_chooser() as picker: page.locator('#import').click()
            picker.value.set_files({'name': 'ordinary.png', 'mimeType': 'image/png', 'buffer': png()})
            page.wait_for_function('async()=>(await window.flapart.exportProject()).layers.length===3')
            assert not calls and not page.locator('.account-dialog').is_visible()
            context.close(); checks.append('invalid params ignored and ordinary import does not advance handoff')
            calls.clear(); context, page = new('?from=native&destination=profile')
            # Actual local recovery containing opaque private art, then a new transparent PNG.
            page.evaluate("""async() => {const p=await window.flapart.exportProject(); const c=document.createElement('canvas'); c.width=91;c.height=67; const x=c.getContext('2d');x.fillStyle='#00ff00';x.fillRect(0,0,91,67);p.width=91;p.height=67;p.name='private recovered drawing';p.layers=[{name:'private green',opacity:1,blend:'source-over',visible:true,data:c.toDataURL()}];await window.flapart.loadProject(p);} """)
            page.wait_for_timeout(1700)
            page.on('dialog', lambda dialog: dialog.accept())
            page.reload(); page.locator('#dialog-ok').click()
            page.wait_for_function("() => document.querySelector('#name').value==='private recovered drawing' && !document.querySelector('main').inert")
            old = page.evaluate('async()=>await window.flapart.exportProject()')
            def recovered():
                return page.evaluate("""() => new Promise((resolve,reject)=>{const r=indexedDB.open('flapart',1);r.onsuccess=()=>{const db=r.result,q=db.transaction('recovery').objectStore('recovery').get('latest');q.onsuccess=()=>{resolve(q.result);db.close();};q.onerror=reject;};r.onerror=reject;})""")
            page.wait_for_timeout(1500); stored = recovered()
            with page.expect_download() as saved:
                page.get_by_role('button',name='save current project first',exact=True).click()
            assert json.loads(Path(saved.value.path()).read_text()) == old
            page.locator('#native-handoff-choose').click()
            page.screenshot(path=str(evidence / 'replace-confirmation.png'), full_page=True)
            page.locator('#dialog button[value="cancel"]').click()
            assert page.evaluate('async()=>await window.flapart.exportProject()') == old
            page.locator('#native-handoff-choose').click()
            with page.expect_file_chooser() as picker: page.locator('#dialog-ok').click()
            picker.value.set_files([])
            page.wait_for_function("() => document.querySelector('.handoff-status').textContent.includes('No file chosen')")
            assert page.evaluate('async()=>await window.flapart.exportProject()') == old and recovered() == stored
            choose(page, b'corrupt PNG')
            page.wait_for_function("() => document.querySelector('.handoff-status').textContent.includes('could not be added')")
            assert page.evaluate('async()=>await window.flapart.exportProject()') == old and recovered() == stored
            choose(page, png(4097,1))
            page.wait_for_function("() => document.querySelector('#status').textContent.includes('Resize it in Flapart Studio')")
            assert page.evaluate('async()=>await window.flapart.exportProject()') == old and recovered() == stored and not calls
            choose(page, png(32,24,True))
            page.wait_for_selector('.account-dialog[open]')
            assert page.evaluate("() => Array.from(document.querySelector('#canvas').getContext('2d').getImageData(5,5,1,1).data)") == [0,0,0,0]
            opened = page.evaluate('async()=>await window.flapart.exportProject()')
            assert (opened['width'],opened['height'],len(opened['layers'])) == (32,24,1)
            page.locator('.account-dialog').get_by_role('button',name='close',exact=True).click()
            page.locator('#undo').click()
            assert page.evaluate('async()=>await window.flapart.exportProject()') == old
            page.wait_for_timeout(1500); assert recovered() == old
            calls.clear(); choose(page, png(), mode='layer'); page.wait_for_selector('.account-dialog[open]')
            combined=page.evaluate('async()=>await window.flapart.exportProject()')
            assert (combined['width'],combined['height'],len(combined['layers'])) == (91,67,2)
            assert combined['layers'][0] == old['layers'][0]
            assert page.evaluate("() => Array.from(document.querySelector('#canvas').getContext('2d').getImageData(0,0,1,1).data)") == [0,255,0,255]
            context.close(); checks.append('recovered private art: explicit replacement, exact transparent PNG, undo restores recovery; cancel/corrupt/oversize unchanged; combined canvas opt-in')
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown(); server.server_close()
    result = {'passed': True, 'checks': checks, 'errors': errors, 'public_mutations': 0, 'live_publication': False}
    (evidence / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))

if __name__ == '__main__': main()

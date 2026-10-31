"""Real Chromium DOM and native-bridge contract tests (requires Playwright + Chromium)."""
import unittest
import re
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

UI_DATA = Path(__file__).resolve().parents[1] / 'ext' / 'ui-build' / 'data'
APP = UI_DATA / 'app'
FALLBACK = UI_DATA.parent / 'loadscreen-fallback'


@unittest.skipIf(sync_playwright is None, 'Playwright not installed')
class BrowserUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        chromium = Path('/usr/bin/chromium')
        options = {'headless': True, 'args': ['--no-sandbox']}
        if chromium.is_file():
            options['executable_path'] = str(chromium)
        cls.browser = cls.pw.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1360, 'height': 860})
        self.addCleanup(self.page.close)
        # set_content is used because this execution environment blocks navigation
        # to file:// and localhost; the production page retains its strict CSP.
        html = (APP / 'index.html').read_text(encoding='utf-8')
        html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>', '', html)
        self.page.set_content(html)
        self.page.add_style_tag(content=(APP / 'styles.css').read_text(encoding='utf-8'))

    def load(self, native=True):
        if native:
            self.page.evaluate("window.__calls=[]; window.invokeNative=(action,arg)=>window.__calls.push([action,arg])")
        self.page.add_script_tag(content=(APP / 'connection.js').read_text(encoding='utf-8'))
        self.page.add_script_tag(content=(APP / 'admission.js').read_text(encoding='utf-8'))
        self.page.add_script_tag(content=(APP / 'app.js').read_text(encoding='utf-8'))

    def test_first_party_root_native_lifecycle_and_authenticated_dispatch(self):
        """Exercise the shipped root.js against actual Chromium iframe windows."""
        html = (APP / 'index.html').read_text(encoding='utf-8')
        html = html.replace('<script src="app.js" defer></script>', '')
        html = html.replace('<link rel="stylesheet" href="styles.css">', '')
        html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>', '', html)
        self.page.set_content('<!doctype html><html><body></body></html>')
        # Browser fixture: replace blocked external navigation with srcdoc.
        # This does not alter production root.js or its native event handlers.
        self.page.evaluate('''(markup) => {
          window.__push = null; window.__frame = null; window.__poll = null;
          window.registerPushFunction = fn => window.__push = fn;
          window.registerFrameFunction = fn => window.__frame = fn;
          window.registerPollFunction = fn => window.__poll = fn;
          Object.defineProperty(HTMLIFrameElement.prototype, 'src', {
            configurable: true,
            get() { return 'about:blank'; },
            set(value) { this.srcdoc = markup; }
          });
        }''', html)
        self.page.add_script_tag(content=(UI_DATA / 'root.js').read_text(encoding='utf-8'))
        self.assertTrue(self.page.evaluate('Boolean(window.__push && window.__frame && window.__poll)'))
        self.page.evaluate('''() => {
          window.__frame('createFrame', 'blocked', 'javascript:alert(1)');
          window.__frame('createFrame', '__proto__', 'data:text/html,evil');
          window.__frame('createFrame', 'mpMenu', 'https://nui-game-internal/ui/app/index.html');
        }''')
        self.assertEqual(self.page.locator('iframe').count(), 1)
        self.assertFalse(self.page.evaluate("Object.hasOwn(window.citFrames, 'blocked')"))
        child = self.page.frame(name='mpMenu')
        self.assertIsNotNone(child)
        child.wait_for_selector('#server-list', state='attached', timeout=4000)
        child.add_style_tag(content=(APP / 'styles.css').read_text(encoding='utf-8'))
        child.evaluate('''() => {
          window.__calls = [];
          window.invokeNative = (action, argument) => window.__calls.push([action, argument]);
        }''')
        child.add_script_tag(content=(APP / 'connection.js').read_text(encoding='utf-8'))
        child.add_script_tag(content=(APP / 'admission.js').read_text(encoding='utf-8'))
        child.add_script_tag(content=(APP / 'app.js').read_text(encoding='utf-8'))
        self.page.evaluate('''() => window.__push('frameCall', 'mpMenu', JSON.stringify({
          type: 'serverQueried', addr: 'root.example:30120', name: 'First-party root'
        }))''')
        child.wait_for_selector('.server-name:has-text("First-party root")', timeout=4000)
        self.page.evaluate('''() => {
          window.__push('rootCall', JSON.stringify({type:'focusFrame',frameName:'mpMenu'}));
          window.__poll('mpMenu');
          window.__push('frameCall','mpMenu','{broken-json');
          window.__push('rootCall','{broken-json');
        }''')
        self.assertIn('z-index: 99999', self.page.locator('iframe').get_attribute('style'))
        self.page.evaluate('''() => window.__push('rootCall', JSON.stringify({type:'blurFrame',frameName:'mpMenu'}))''')
        self.page.evaluate('''() => window.__frame('destroyFrame','mpMenu')''')
        self.assertEqual(self.page.locator('iframe').count(), 0)
        self.assertFalse(self.page.evaluate("Object.hasOwn(window.citFrames, 'mpMenu')"))
        # Recreating a frame with the same name must not retain a stale iframe.
        self.page.evaluate('''() => {
          window.__frame('createFrame','mpMenu','https://nui-game-internal/ui/app/index.html');
          window.__frame('createFrame','mpMenu','https://nui-game-internal/ui/app/index.html');
        }''')
        self.assertEqual(self.page.locator('iframe').count(), 1)
        self.page.evaluate('''() => {
          window.__push('rootCall', JSON.stringify({type:'setHandover',data:{name:'OpenV'}}));
          window.__push('rootCall', JSON.stringify({type:'setServerAddress',data:'play.example:30120'}));
          window.__frame('createFrame','loadingScreen','https://nui-game-internal/ui/loadscreen/index.html');
        }''')
        self.page.wait_for_timeout(100)  # srcdoc frame registration is asynchronous
        self.page.frame(name='loadingScreen').wait_for_load_state('domcontentloaded')
        self.page.wait_for_function("() => window.citFrames.loadingScreen?.contentWindow?.nuiHandoverData?.serverAddress === 'play.example:30120'")
        self.assertEqual(self.page.locator('iframe').count(), 2)

    def test_root_uses_exact_nui_origin_instead_of_wildcard(self):
        """Cfx registers nui: as a standard scheme; native messages must not use '*'."""
        self.page.set_content('<!doctype html><html><body></body></html>')
        self.page.evaluate('''() => {
          window.registerPushFunction = fn => window.__push = fn;
          window.registerFrameFunction = fn => window.__frame = fn;
          window.registerPollFunction = fn => window.__poll = fn;
          Object.defineProperty(HTMLIFrameElement.prototype, 'src', {
            configurable: true,
            get() { return this.dataset.expectedUrl || 'about:blank'; },
            set(value) {
              this.dataset.expectedUrl = value;
              this.srcdoc = '<html><body>Resource</body></html>';
            }
          });
        }''')
        self.page.add_script_tag(content=(UI_DATA / 'root.js').read_text(encoding='utf-8'))
        self.page.evaluate("window.__frame('createFrame','resource','nui://my-resource/ui/index.html')")
        self.page.wait_for_timeout(100)
        self.page.evaluate('''() => {
          window.__targets = [];
          window.citFrames.resource.contentWindow.postMessage = (data, target) => window.__targets.push(target);
          window.__push('frameCall', 'resource', JSON.stringify({type:'event'}));
        }''')
        self.assertEqual(self.page.evaluate('window.__targets'), ['nui://my-resource'])

    def test_root_buffers_startup_native_events_until_child_load(self):
        """Native may push frameCall/poll immediately after createFrame, before child JS exists."""
        self.page.set_content('<!doctype html><html><body></body></html>')
        child_markup = "<html><body><script>window.received=[];window.addEventListener('message',e=>window.received.push(e.data));</script></body></html>"
        self.page.evaluate('''(markup) => {
          window.registerPushFunction = fn => window.__push = fn;
          window.registerFrameFunction = fn => window.__frame = fn;
          window.registerPollFunction = fn => window.__poll = fn;
          Object.defineProperty(HTMLIFrameElement.prototype, 'src', {
            configurable: true,
            get() { return 'about:blank'; },
            set(value) { this.srcdoc = markup; }
          });
        }''', child_markup)
        self.page.add_script_tag(content=(UI_DATA / 'root.js').read_text(encoding='utf-8'))
        self.page.evaluate('''() => {
          window.__frame('createFrame', 'mpMenu', 'https://nui-game-internal/ui/app/index.html');
          window.__push('frameCall', 'mpMenu', JSON.stringify({type:'serverQueried',addr:'early.example:30120'}));
          window.__poll('mpMenu');
          window.__push('rootCall', JSON.stringify({type:'focusFrame',frameName:'mpMenu'}));
        }''')
        self.page.wait_for_timeout(100)  # Chromium registers srcdoc frames asynchronously
        child = self.page.frame(name='mpMenu')
        child.wait_for_load_state('load')
        self.page.wait_for_timeout(100)
        self.assertEqual(child.evaluate('window.received'), [
            {'type': 'serverQueried', 'addr': 'early.example:30120'}, {'type': 'poll'}
        ])
        self.assertIn('z-index: 99999', self.page.locator('iframe').get_attribute('style'))

    def test_root_discards_replaced_frame_startup_events_and_bounds_queue(self):
        self.page.set_content('<!doctype html><html><body></body></html>')
        child_markup = "<html><body><script>window.received=[];window.addEventListener('message',e=>window.received.push(e.data));</script></body></html>"
        self.page.evaluate('''(markup) => {
          window.registerPushFunction = fn => window.__push = fn;
          window.registerFrameFunction = fn => window.__frame = fn;
          window.registerPollFunction = fn => window.__poll = fn;
          Object.defineProperty(HTMLIFrameElement.prototype, 'src', {
            configurable: true,
            get() { return 'about:blank'; },
            set(value) { this.srcdoc = markup; }
          });
        }''', child_markup)
        self.page.add_script_tag(content=(UI_DATA / 'root.js').read_text(encoding='utf-8'))
        self.page.evaluate('''() => {
          window.__frame('createFrame','mpMenu','https://nui-game-internal/ui/app/index.html');
          window.__push('frameCall','mpMenu',JSON.stringify({type:'old'}));
          window.__frame('createFrame','mpMenu','https://nui-game-internal/ui/app/index.html');
          for (let i = 0; i < 100; i++) {
            window.__push('frameCall','mpMenu',JSON.stringify({type:'number',seq:i}));
          }
        }''')
        self.page.wait_for_timeout(100)  # Chromium registers srcdoc frames asynchronously
        child = self.page.frame(name='mpMenu')
        child.wait_for_load_state('load')
        self.page.wait_for_timeout(100)
        received = child.evaluate('window.received')
        self.assertNotIn({'type': 'old'}, received)
        self.assertTrue(received)
        self.assertLessEqual(len(received), 65)
        self.assertEqual(received[-2], {'type': 'number', 'seq': 99})
        self.assertEqual(received[-1], {'type': 'openvStartupOverflow'})
        self.assertEqual(self.page.locator('iframe').count(), 1)

    def test_source_only_loadscreen_progress_and_untrusted_messages(self):
        html = (FALLBACK / 'index.html').read_text(encoding='utf-8')
        html = html.replace('<script src="code.js" defer></script>', '')
        html = html.replace('<link rel="stylesheet" href="styles.css">', '')
        html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>', '', html)
        self.page.set_content(html)
        self.page.add_style_tag(content=(FALLBACK / 'styles.css').read_text(encoding='utf-8'))
        self.page.add_script_tag(content=(FALLBACK / 'code.js').read_text(encoding='utf-8'))
        self.page.evaluate('''() => window.postMessage({eventName:'loadProgress',loadFraction:0.37}, '*')''')
        self.page.wait_for_function("document.querySelector('#percent').textContent === '37%'")
        self.page.evaluate('''() => window.postMessage({eventName:'loadProgress',loadFraction:0.1}, '*')''')
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.locator('#percent').inner_text(), '37%')
        self.page.evaluate('''() => window.postMessage({eventName:'loadProgress',loadFraction:1.5}, '*')''')
        self.page.wait_for_timeout(50)
        self.assertEqual(self.page.locator('#percent').inner_text(), '37%')
        self.page.evaluate('''() => window.dispatchEvent(new MessageEvent('message', {
          source: null, origin: 'https://untrusted.invalid',
          data: {eventName: 'loadProgress', loadFraction: 1}
        }))''')
        self.assertEqual(self.page.locator('#percent').inner_text(), '37%')
        self.page.evaluate('''() => window.postMessage({eventName:'onLogLine',message:'<img src=x onerror=alert(1)>'}, '*')''')
        self.page.wait_for_function("document.querySelector('#status').textContent.includes('<img')")
        self.assertEqual(self.page.locator('#status img').count(), 0)
        self.page.evaluate('''() => window.postMessage({eventName:'shutdownLoadingScreen'}, '*')''')
        self.page.wait_for_function("document.querySelector('#percent').textContent === '100%'")
        self.assertEqual(self.page.locator('#status').inner_text(), 'Ready')

    def test_preview_has_coherent_navigation_and_no_fake_connect(self):
        self.load(native=False)
        self.assertEqual(self.page.title(), 'OpenV — Multiplayer')
        self.page.locator('#server-address').fill('play.example.com:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        self.assertIn('not available', self.page.locator('#toast').inner_text())
        self.page.locator('.nav-link[data-view=settings]').click()
        self.assertTrue(self.page.locator('[data-page=settings]').is_visible())
        self.assertTrue(self.page.locator('[data-page=home]').is_hidden())

    def test_native_bootstrap_and_connect_payload(self):
        self.load()
        calls = self.page.evaluate('window.__calls')
        self.assertEqual([call[0] for call in calls if call[0] is not None][:2], ['getMinModeInfo', 'getFavorites'])
        self.page.locator('#server-address').fill('PLAY.EXAMPLE.COM:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        calls = self.page.evaluate('window.__calls')
        connect = [c for c in calls if c[0] == 'connectTo']
        self.assertEqual(len(connect), 1)
        import json
        self.assertEqual(json.loads(connect[0][1])[0], 'play.example.com:30120')
        self.assertEqual(len(json.loads(connect[0][1])[1]), 32)
        self.assertIn('play.example.com:30120', self.page.locator('#recent-list').inner_text())

    def test_real_native_stages_and_pending_probe_never_claim_gameplay(self):
        import json
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        nonce = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        for stage, expected in [
            ('downloading', 'downloading server resources'),
            ('download_complete', 'resource transfer completed'),
            ('connected', 'network transport connected'),
            ('active', 'gameplay admission'),
        ]:
            self.page.evaluate("(a) => window.postMessage({type:'openvNativeStage',nonce:a[0],stage:a[1]},'*')", [nonce, stage])
            self.page.wait_for_function("(text) => document.querySelector('#connection-state').textContent.includes(text)", arg=expected)
            self.assertIn(expected, self.page.locator('#connection-state').inner_text())
            self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(n) => window.postMessage({type:'openvNativeStage',nonce:n,stage:'__proto__'},'*')", nonce)
        self.assertIn('gameplay admission', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(n) => window.postMessage({type:'openvTransportConnected',nonce:n},'*')", nonce)
        self.assertIn('gameplay admission', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(n) => window.postMessage({type:'openvConnectClosed',nonce:n},'*')", nonce)
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())

    def test_native_connection_pending_gate_failure_and_retry(self):
        self.load()
        self.page.locator('#server-address').fill('play.example.com:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.assertIn('Waiting for server response', self.page.locator('#connection-state').inner_text())
        import json
        nonce = json.loads(next(c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'))[1]
        self.page.evaluate("(nonce) => window.postMessage({type:'connecting',nonce},'*')", nonce)
        self.page.wait_for_function("document.querySelector('#connection-state').textContent.includes('not yet verified')")
        self.page.evaluate("(nonce) => window.postMessage({type:'connectFailed',nonce,message:'Rejected by server'},'*')", nonce)
        self.page.wait_for_function("document.querySelector('#connection-state').textContent.includes('Waiting for Cfx')")
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        # A failed native connection can remain non-IDLE. Neither a stale
        # ACTIVE callback nor a pending probe may reopen the connection gate.
        self.page.evaluate("(nonce) => window.postMessage({type:'openvNativeStage',nonce,stage:'active'},'*')", nonce)
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectionProbe',nonce,state:'pending'},'*')", nonce)
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.assertIn('Waiting for Cfx', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectionProbe',nonce,state:'absent'},'*')", nonce)
        self.page.wait_for_function("!document.querySelector('#connect-form button[type=submit]').disabled")
        self.assertIn('native network connection ended', self.page.locator('#connection-state').inner_text())
        self.page.locator('#connect-form button[type=submit]').click()
        self.assertEqual(len([call for call in self.page.evaluate('window.__calls') if call[0] == 'connectTo']), 2)

    def test_native_nonce_rejects_stale_and_untagged_events(self):
        import json
        self.load()
        self.page.locator('#server-address').fill('play.example.com:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        old = json.loads(next(c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'))[1]
        self.page.evaluate("window.postMessage({type:'connectFailed',message:'Legacy untagged'},'*')")
        self.page.evaluate("window.postMessage({type:'connectFailed',nonce:'0'.repeat(32),message:'Wrong request'},'*')")
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectAccepted',nonce},'*')", old)
        self.assertIn('accepted the request', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvTransportConnected',nonce},'*')", old)
        self.assertIn('not yet verified', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectClosed',nonce},'*')", old)
        self.page.wait_for_function("!document.querySelector('#connect-form button[type=submit]').disabled")
        self.page.locator('#connect-form button[type=submit]').click()
        new = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        self.assertNotEqual(new, old)
        self.page.evaluate("(nonce) => window.postMessage({type:'connectFailed',nonce,message:'Stale'},'*')", old)
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectRejected',nonce,reason:'busy'},'*')", new)
        # postMessage queues a browser task; do not race its dispatch with a
        # synchronous Playwright disabled-state read.
        self.page.wait_for_function("!document.querySelector('#connect-form button[type=submit]').disabled")

    def test_native_disconnect_requires_confirmation_and_matching_ack(self):
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        import json
        token = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        self.assertTrue(self.page.locator('#connection-cancel').is_visible())
        self.page.locator('#connection-cancel').click()
        self.page.locator('#connection-disconnect-dialog button[value=cancel]').click()
        self.assertFalse(any(c[0] == 'openvCancelConnect' for c in self.page.evaluate('window.__calls')))
        self.page.locator('#connection-cancel').click()
        self.page.locator('#connection-disconnect-dialog button[value=disconnect]').click()
        self.page.wait_for_function("() => window.__calls.some(call => call[0] === 'openvCancelConnect')")
        self.assertIn(['openvCancelConnect', token], self.page.evaluate('window.__calls'))
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectClosed',nonce},'*')", '0' * 32)
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectClosed',nonce},'*')", token)
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.assertTrue(self.page.locator('#connection-cancel').is_hidden())

    def test_openv_join_code_card_submission_and_replay_fencing(self):
        import json
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        nonce = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        card = json.dumps({
            'type': 'AdaptiveCard', 'version': '1.0',
            'body': [
                {'type': 'TextBlock', 'text': 'Connect to OpenV'},
                {'type': 'TextBlock', 'text': 'Enter a one-time code.'},
                {'type': 'Input.Text', 'id': 'join_code', 'maxLength': 43},
            ],
            'actions': [{'type': 'Action.Submit', 'title': 'Join server'}],
        })
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", ['0' * 32, card])
        self.assertFalse(self.page.locator('#admission-dialog').evaluate('(d) => d.open'))
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [nonce, card])
        self.assertTrue(self.page.locator('#admission-dialog').evaluate('(d) => d.open'))
        self.page.locator('#admission-code').fill('invalid')
        self.page.locator('#admission-form button[type=submit]').click()
        self.assertIn('43-character', self.page.locator('#admission-error').inner_text())
        self.assertFalse(any(c[0] == 'openvSubmitJoinCode' for c in self.page.evaluate('window.__calls')))
        code = 'A' * 42 + '_'
        self.page.locator('#admission-code').fill(code)
        self.page.locator('#admission-form button[type=submit]').click()
        self.page.wait_for_function("!document.querySelector('#admission-dialog').open")
        calls = [c for c in self.page.evaluate('window.__calls') if c[0] == 'openvSubmitJoinCode']
        self.assertEqual(len(calls), 1)
        self.assertEqual(json.loads(calls[0][1]), [nonce, code])
        self.assertEqual(self.page.locator('#admission-code').input_value(), '')
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(n) => window.postMessage({type:'openvConnectClosed',nonce:n},'*')", nonce)
        self.page.wait_for_function("() => !document.querySelector('#connect-form button[type=submit]').disabled")
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [nonce, card])
        self.assertFalse(self.page.locator('#admission-dialog').evaluate('(d) => d.open'))

    def test_expired_admission_clears_secret_and_cancels_native(self):
        import json
        self.page.clock.install()
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        nonce = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        card = json.dumps({
            'type': 'AdaptiveCard', 'version': '1.0',
            'body': [
                {'type': 'TextBlock', 'text': 'Connect to OpenV'},
                {'type': 'TextBlock', 'text': 'Enter a one-time code.'},
                {'type': 'Input.Text', 'id': 'join_code', 'maxLength': 43},
            ],
            'actions': [{'type': 'Action.Submit'}],
        })
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [nonce, card])
        self.page.locator('#admission-code').fill('S' * 43)
        self.page.clock.fast_forward(60000)
        self.assertFalse(self.page.locator('#admission-dialog').evaluate('(d) => d.open'))
        self.assertEqual(self.page.locator('#admission-code').input_value(), '')
        self.assertIn(['openvCancelConnect', nonce], self.page.evaluate('window.__calls'))
        self.assertFalse(any(c[0] == 'openvSubmitJoinCode' for c in self.page.evaluate('window.__calls')))
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(n) => window.postMessage({type:'openvConnectClosed',nonce:n},'*')", nonce)
        self.page.wait_for_function("() => !document.querySelector('#connect-form button[type=submit]').disabled")
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())

    def test_native_rejected_admission_cancels_matching_connection(self):
        import json
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        nonce = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        self.page.evaluate("(n) => window.postMessage({type:'openvAdmissionRejected',nonce:n},'*')", '0' * 32)
        self.assertFalse(any(c[0] == 'openvCancelConnect' for c in self.page.evaluate('window.__calls')))
        self.page.evaluate("(n) => window.postMessage({type:'openvAdmissionRejected',nonce:n},'*')", nonce)
        self.page.wait_for_function("() => window.__calls.some(c => c[0] === 'openvCancelConnect')")
        self.assertIn(['openvCancelConnect', nonce], self.page.evaluate('window.__calls'))
        self.assertIn('rejected', self.page.locator('#toast').inner_text())

    def test_openv_unsupported_card_cancels_and_dialog_abort_wipes_code(self):
        import json
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        nonce = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        hostile = json.dumps({
            'type': 'AdaptiveCard', 'version': '1.0',
            'body': [{'type': 'Input.Text', 'id': 'password'}],
            'actions': [{'type': 'Action.OpenUrl', 'url': 'https://evil.invalid'}],
        })
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [nonce, hostile])
        self.assertFalse(self.page.locator('#admission-dialog').evaluate('(d) => d.open'))
        self.assertIn(['openvCancelConnect', nonce], self.page.evaluate('window.__calls'))
        self.page.evaluate("(n) => window.postMessage({type:'openvConnectClosed',nonce:n},'*')", nonce)
        self.page.locator('#connect-form button[type=submit]').click()
        newer = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        card = json.dumps({
            'type': 'AdaptiveCard', 'version': '1.0',
            'body': [
                {'type': 'TextBlock', 'text': 'Connect to OpenV'},
                {'type': 'TextBlock', 'text': 'Enter a one-time code.'},
                {'type': 'Input.Text', 'id': 'join_code', 'maxLength': 43},
            ],
            'actions': [{'type': 'Action.Submit'}],
        })
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [newer, card])
        self.page.locator('#admission-code').fill('B' * 43)
        self.page.locator('#admission-abort').click()
        self.page.wait_for_function("!document.querySelector('#admission-dialog').open")
        self.assertEqual(self.page.locator('#admission-code').input_value(), '')
        self.assertIn(['openvCancelConnect', newer], self.page.evaluate('window.__calls'))
        self.assertFalse(any(c[0] == 'openvSubmitJoinCode' for c in self.page.evaluate('window.__calls')))
        self.page.evaluate("(n) => window.postMessage({type:'openvConnectClosed',nonce:n},'*')", newer)
        self.page.locator('#connect-form button[type=submit]').click()
        newest = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        self.page.evaluate("(args) => window.postMessage({type:'connectCard',nonce:args[0],data:{card:args[1]}},'*')", [newest, card])
        self.page.locator('#admission-code').fill('C' * 43)
        self.page.locator('#admission-code').press('Escape')
        self.assertEqual(self.page.locator('#admission-code').input_value(), '')
        self.assertIn(['openvCancelConnect', newest], self.page.evaluate('window.__calls'))

    def test_native_probe_does_not_grant_gameplay(self):
        self.load()
        self.page.locator('#server-address').fill('play.example:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        import json
        token = json.loads([c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'][-1])[1]
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectionProbe',nonce,state:'active'},'*')", token)
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvTransportConnected',nonce},'*')", token)
        self.assertIn('not yet verified', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("(nonce) => window.postMessage({type:'openvConnectionProbe',nonce,state:'absent'},'*')", token)
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())

    def test_query_favorites_and_native_messages(self):
        self.load()
        self.page.locator('.nav-link[data-view=servers]').click()
        self.page.locator('#query-address').fill('127.0.0.1:30120')
        self.page.locator('#query-form button[type=submit]').click()
        self.assertIn(['queryServer', '127.0.0.1:30120'], self.page.evaluate('window.__calls'))
        self.page.evaluate("window.postMessage({type:'serverQueried',addr:'127.0.0.1:30120',name:'<img src=x onerror=alert(1)>',clients:2,maxclients:16},'*')")
        self.page.wait_for_timeout(100)
        self.assertEqual(self.page.locator('#server-list img').count(), 0)
        self.assertIn('<img', self.page.locator('#server-list .server-name').inner_text())
        self.page.locator('#server-list .star').click()
        self.assertIn('saveFavorites', [c[0] for c in self.page.evaluate('window.__calls')])
        self.page.locator('.nav-link[data-view=favorites]').click()
        self.assertIn('127.0.0.1:30120', self.page.locator('#favorites-list').inner_text())
        self.page.evaluate("window.postMessage({type:'backfillServerInfo',data:'sensitive'},'*')")
        self.page.wait_for_timeout(100)
        self.assertIn(['backfillDone', ''], self.page.evaluate('window.__calls'))

    def test_startup_queue_overflow_requests_authoritative_native_refresh(self):
        self.load()
        self.page.evaluate("window.postMessage({type:'openvStartupOverflow'},'*')")
        self.page.wait_for_timeout(100)
        calls = [c[0] for c in self.page.evaluate('window.__calls')]
        self.assertEqual(calls.count('getFavorites'), 2)  # initial + recovery
        self.assertEqual(calls.count('refreshServers'), 1)
        self.assertIn('refreshing discovery', self.page.locator('#toast').inner_text())

    def test_native_external_connect_and_progress(self):
        self.load()
        self.page.evaluate("window.postMessage({type:'connectTo',hostnameStr:'example.org:30120'},'*')")
        self.page.wait_for_timeout(100)
        self.assertTrue(any(c[0] == 'connectTo' for c in self.page.evaluate('window.__calls')))
        import json
        nonce = json.loads(next(c[1] for c in self.page.evaluate('window.__calls') if c[0] == 'connectTo'))[1]
        self.page.evaluate("(nonce) => window.postMessage({type:'connectStatus',data:{nonce,message:'Loading verified resources'}},'*')", nonce)
        self.page.wait_for_timeout(100)
        self.assertIn('Loading verified resources', self.page.locator('#toast').inner_text())
        self.page.evaluate("(nonce) => window.postMessage({type:'connectFailed',nonce,message:'Server unavailable'},'*')", nonce)
        self.page.wait_for_timeout(100)
        self.assertIn('Server unavailable', self.page.locator('#toast').inner_text())

    def test_exit_confirmation_and_preferences(self):
        self.load()
        self.page.locator('#quit').click()
        self.assertTrue(self.page.locator('#confirm-dialog').evaluate('(dialog)=>dialog.open'))
        self.page.locator('#confirm-dialog button[value=cancel]').click()
        self.assertNotIn('quit', [c[0] for c in self.page.evaluate('window.__calls')])
        self.page.locator('.nav-link[data-view=settings]').click()
        self.page.locator('#confirm-exit').uncheck(force=True)
        self.page.locator('#quit').click()
        self.assertIn('quit', [c[0] for c in self.page.evaluate('window.__calls')])

    def test_connect_fails_closed_without_secure_nonce(self):
        self.load()
        self.page.evaluate("Object.defineProperty(window, 'crypto', {value:{}, configurable:true})")
        self.page.locator('#server-address').fill('play.example.com:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        self.assertNotIn('connectTo', [c[0] for c in self.page.evaluate('window.__calls')])
        self.assertIn('Secure connection initialization', self.page.locator('#toast').inner_text())
        self.assertNotIn('play.example.com', self.page.locator('#recent-list').inner_text())

    def test_real_root_frame_dispatch_and_origin_isolation(self):
        """Exercise Cfx root frameCall -> child postMessage, not a self-message mock."""
        ui_url = 'https://nui-game-internal/ui/app/index.html'
        fixture = '''<!doctype html><html><body><script>
          window.citFrames = {};
          window.__rootFrame = (message, name, url) => {
            if (message === 'createFrame') {
              const frame = document.createElement('iframe');
              frame.name = name; frame.srcdoc = url;
              document.body.append(frame); window.citFrames[name] = frame;
            }
          };
          window.__rootPush = (type, frameName, dataString) => {
            if (type === 'frameCall')
              window.citFrames[frameName].contentWindow.postMessage(JSON.parse(dataString), '*');
          };
        </script></body></html>'''
        # This environment blocks external navigation even when intercepted.
        # srcdoc keeps a real parent/child Window relationship without network.
        html = (APP / 'index.html').read_text(encoding='utf-8')
        html = html.replace('<script src="app.js" defer></script>', '')
        html = html.replace('<link rel="stylesheet" href="styles.css">', '')
        html = re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]+>', '', html)
        self.page.set_content(fixture)
        self.page.evaluate('''() => {
            window.__calls = [];
            window.invokeNative = (action, argument) => window.__calls.push([action, argument]);
        }''')
        self.page.evaluate('(markup) => window.__rootFrame("createFrame", "mpMenu", markup)', html)
        self.page.wait_for_timeout(300)
        child = self.page.frame(name='mpMenu')
        self.assertIsNotNone(child)
        child.wait_for_selector('#server-list', timeout=8000, state='attached')
        child.evaluate('''() => { window.__calls = []; window.invokeNative = (action, argument) => window.__calls.push([action, argument]); }''')
        child.add_style_tag(content=(APP / 'styles.css').read_text(encoding='utf-8'))
        child.add_script_tag(content=(APP / 'connection.js').read_text(encoding='utf-8'))
        child.add_script_tag(content=(APP / 'admission.js').read_text(encoding='utf-8'))
        child.add_script_tag(content=(APP / 'app.js').read_text(encoding='utf-8'))
        self.page.evaluate('''() => window.__rootPush('frameCall', 'mpMenu', JSON.stringify({
            type: 'serverQueried', addr: '127.0.0.1:30120', name: 'Trusted frame server', clients: 2, maxclients: 16
        }))''')
        child.wait_for_selector('.server-name:has-text("Trusted frame server")', timeout=4000)
        self.assertIn('127.0.0.1:30120', child.locator('#server-list').inner_text())
        # Production Cfx uses nui://game/ui/root.html as parent, while the
        # child menu is https://nui-game-internal/ui/app/index.html. A
        # same-origin-only check silently discards every native frameCall.
        child.evaluate('''() => window.dispatchEvent(new MessageEvent('message', {
            source: window.parent, origin: 'nui://game',
            data: {type:'serverQueried',addr:'root.example:30120',name:'Cfx native root'}
        }))''')
        self.assertIn('Cfx native root', child.locator('#server-list').inner_text())
        # The production HTTPS menu must reject opaque origins, while this
        # about:srcdoc browser fixture can accept its own opaque parent.
        self.assertFalse(child.evaluate("window.OpenVUI.isTrustedNativeOrigin('null', 'https://nui-game-internal', 'https:')"))
        self.assertTrue(child.evaluate("window.OpenVUI.isTrustedNativeOrigin('nui://game', 'https://nui-game-internal', 'https:')"))
        self.assertFalse(child.evaluate("window.OpenVUI.isTrustedNativeOrigin('https://attacker.invalid', 'https://nui-game-internal', 'https:')"))
        # Native messages must not be forgeable by a self-post inside the UI frame.
        child.evaluate('''() => window.postMessage({type:'serverQueried', addr:'evil.example:30120',name:'Self spoof'}, '*')''')
        self.assertNotIn('Self spoof', child.locator('#server-list').inner_text())
        self.page.evaluate('''() => {
            const sibling = document.createElement('iframe');
            sibling.name = 'untrustedSibling';
            sibling.srcdoc = '<html><body></body></html>';
            document.body.append(sibling);
        }''')
        self.page.wait_for_timeout(100)
        sibling = self.page.frame(name='untrustedSibling')
        self.assertIsNotNone(sibling)
        sibling.evaluate('''() => window.parent.citFrames.mpMenu.contentWindow.postMessage({
            type:'serverQueried',addr:'sibling.example:30120',name:'Sibling spoof'
        }, '*')''')
        self.assertNotIn('Sibling spoof', child.locator('#server-list').inner_text())
        child.evaluate('''() => window.dispatchEvent(new MessageEvent('message', {
            source: window.parent, origin: 'https://untrusted.example',
            data: {type:'serverQueried',addr:'foreign.example:30120',name:'Foreign origin'}
        }))''')
        self.assertNotIn('Foreign origin', child.locator('#server-list').inner_text())
        self.page.evaluate('''() => window.__rootPush('frameCall', 'mpMenu', JSON.stringify({
            type:'serverQueried',addr:'127.0.0.1:30120',name:'OpenV Gateway',
            clients:'1',maxclients:32,
            infoBlob:{version:4,vars:{openv_discovery_only:'true'}}
        }))''')
        self.assertIn('Discovery only', child.locator('#server-list').inner_text())
        self.assertTrue(child.locator('#server-list article:has-text("OpenV Gateway") button.primary').is_disabled())
        self.page.evaluate('''() => window.__rootPush('frameCall', 'mpMenu', JSON.stringify({type:'backfillServerInfo',data:'private-ticket'}))''')
        self.assertIn(['backfillDone', ''], child.evaluate('window.__calls'))

    def test_discovery_only_gateway_not_offered_as_playable(self):
        self.load()
        self.page.evaluate("""window.postMessage({
            type: 'serverQueried', addr: '127.0.0.1:30120', name: 'OpenV Gateway',
            clients: '2', maxclients: 32,
            infoBlob: {version:4, vars:{openv_discovery_only:'true',openv_protocol:'openv-gateway-v1'}}
        }, '*')""")
        self.page.wait_for_timeout(100)
        self.assertIn('2/32 admitted sessions', self.page.locator('#server-list').inner_text())
        self.assertIn('Discovery only', self.page.locator('#server-list').inner_text())
        self.assertTrue(self.page.locator('#server-list button.primary').is_disabled())
        self.assertEqual(self.page.locator('#server-list button.primary').inner_text(), 'Not playable yet')
        # A subsequent Cfx query with a missing infoBlob must not silently
        # promote an already known discovery-only endpoint to playable.
        self.page.evaluate("""window.postMessage({type:'serverAdd',addr:'127.0.0.1:30120',name:'Gateway refresh',clients:'2',maxclients:32},'*')""")
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator('#server-list button.primary').is_disabled())
        self.page.locator('.nav-link[data-view=home]').click()
        self.page.locator('#server-address').fill('127.0.0.1:30120')
        self.page.locator('#connect-form button[type=submit]').click()
        self.assertIn('discovery only', self.page.locator('#toast').inner_text())
        self.assertNotIn('connectTo', [c[0] for c in self.page.evaluate('window.__calls')])
        # A normal server still retains its previous connection behavior.
        self.page.evaluate("""window.postMessage({
            type:'serverQueried',addr:'play.example.org:30120',name:'Playable server',
            clients:'1',maxclients:8,infoBlob:{version:4,vars:{}}
        }, '*')""")
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator('#server-list button.primary').last.is_enabled())

    def test_endpoint_security_validation(self):
        self.load()
        cases = {
            'SERVER.LOCAL': 'server.local:30120',
            '192.168.1.2:30121': '192.168.1.2:30121',
            '[::1]:30120': '[::1]:30120',
            'host:0': None,
            'host:65536': None,
            'host;quit': None,
            'https://host': None,
            'host/path': None,
            '999.999.999.999': None,
            '[:::]': None,
            'host\\command': None,
            'a..b': None,
            '': None,
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(self.page.evaluate('(value)=>window.OpenVUI.parseEndpoint(value)', source), expected)

    def test_native_connection_recovers_after_cef_reload(self):
        self.load()
        self.assertIn(['openvConnectionSnapshot', ''], self.page.evaluate('window.__calls'))
        nonce = 'a' * 32
        self.page.evaluate("""(nonce) => window.postMessage({
            type: 'openvConnectionSnapshot', nonce,
            address: 'play.example.org:30120', stage: 'connected'
        }, '*')""", nonce)
        self.page.wait_for_timeout(100)
        self.assertTrue(self.page.locator('#connect-form button[type=submit]').is_disabled())
        self.assertFalse(self.page.locator('#connection-cancel').is_hidden())
        self.assertIn(['openvConnectionProbe', nonce], self.page.evaluate('window.__calls'))
        self.page.evaluate("""(nonce) => window.postMessage({
            type: 'openvConnectionProbe', nonce, state: 'active'
        }, '*')""", nonce)
        self.page.wait_for_timeout(100)
        self.assertIn('network session is active', self.page.locator('#connection-state').inner_text())
        self.page.evaluate("""(nonce) => window.postMessage({
            type: 'openvConnectClosed', nonce, reason: 'native_idle'
        }, '*')""", nonce)
        self.page.wait_for_timeout(100)
        self.assertFalse(self.page.locator('#connect-form button[type=submit]').is_disabled())


if __name__ == '__main__':
    unittest.main()

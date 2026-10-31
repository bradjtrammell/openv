import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const sandbox = { window: {}, Object, TypeError, JSON, Array };
vm.runInNewContext(readFileSync(new URL('../ext/ui-build/data/app/admission.js', import.meta.url), 'utf8'), sandbox);
const { create } = sandbox.window.OpenVAdmission;
const first = '1'.repeat(32), second = '2'.repeat(32), code = 'a'.repeat(43);
const card = JSON.stringify({ type: 'AdaptiveCard', version: '1.0',
  body: [{ type: 'TextBlock', text: 'Connect to OpenV' },
    { type: 'TextBlock', text: 'Enter the one-time code.' },
    { type: 'Input.Text', id: 'join_code', maxLength: 43 }],
  actions: [{ type: 'Action.Submit' }] });
function fixture() {
  let now = 1000, seq = 0, shows = 0, hides = 0;
  const timers = new Map(), expired = [], sent = [];
  let dispatch = () => true;
  const coordinator = create({
    show() { shows++; }, hide() { hides++; },
    dispatch(n, c) { sent.push([n, c]); return dispatch(n, c); },
    schedule(fn, ms) { const id = ++seq; timers.set(id, { fn, ms }); return id; },
    cancel(id) { timers.delete(id); }, now() { return now; },
    onExpire(n) { expired.push(n); },
  });
  return { c: coordinator, timers, expired, sent,
    advance(ms) { now += ms; },
    rewind(ms) { now -= ms; },
    clock() { return now; },
    dispatch(fn) { dispatch = fn; },
    fire() { assert.equal(timers.size, 1); const timer = [...timers.values()][0]; timer.fn(); },
    get shows() { return shows; }, get hides() { return hides; },
  };
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card, 60000), true);
  const stale = [...f.timers.values()][0].fn;
  f.advance(10000);
  assert.equal(f.c.present(first, card, 60000), true, 'identical native card is idempotent');
  assert.equal(f.shows, 1, 'duplicate card must not reset the input');
  assert.equal(f.timers.size, 1);
  assert.equal(f.c.present(first, card.replace('one-time', 'different'), 10000), false);
  assert.equal(f.c.present(second, card, 10000), false);
  assert.equal(f.c.present(first, card, 5000), true, 'native may tighten remaining deadline');
  assert.equal([...f.timers.values()][0].ms, 5000);
  stale();
  assert.equal(f.c.owns(first), true, 'stale timer must not cancel a recovered card');
  f.advance(4999);
  assert.equal(f.c.submit(code).ok, true);
  assert.equal(f.shows, 1);
  assert.equal(f.hides, 1);
  assert.equal(f.sent.length, 1);
  assert.equal(f.expired.length, 0);
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card, 60000), true);
  f.advance(1000);
  f.fire(); // early CEF timer callback must rearm rather than expire.
  assert.equal(f.c.active(), true);
  assert.equal([...f.timers.values()][0].ms, 59000);
  assert.equal(f.expired.length, 0);
  f.advance(59000);
  f.fire();
  assert.equal(f.c.active(), false);
  assert.deepEqual(f.expired, [first]);
  assert.equal(f.timers.size, 0);
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card, 60000), true);
  f.advance(60000);
  assert.equal(f.c.present(first, card, 60000), false, 'expired duplicate cannot extend lease');
  assert.deepEqual(f.expired, [first]);
  assert.equal(f.c.active(), false);
  assert.equal(f.sent.length, 0);
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card), true);
  f.dispatch(() => {
    f.c.dismiss();
    assert.equal(f.c.present(second, card), true);
    return true;
  });
  assert.equal(f.c.submit(code).ok, true);
  assert.equal(f.c.owns(second), true, 'reentrant native callback must not dismiss replacement');
  assert.equal(f.hides, 1);
  assert.equal(f.shows, 2);
  assert.equal(f.timers.size, 1);
  assert.equal(f.c.submit(code).ok, true);
  assert.equal(f.sent.length, 2);
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card), true);
  f.dispatch(() => { f.c.dismiss(); f.c.present(second, card); return false; });
  assert.equal(f.c.submit(code).reason, 'stale');
  assert.equal(f.c.owns(second), true);
}
{
  const f = fixture();
  assert.equal(f.c.present(first, card), true);
  f.rewind(1);
  f.fire();
  assert.deepEqual(f.expired, [first], 'backward clock must fail closed');
  assert.equal(f.c.active(), false);
}
console.log('PASS: duplicate native card replay, deadline tightening, early timer recovery, stale timer fencing, reentrant dispatch and clock rollback');

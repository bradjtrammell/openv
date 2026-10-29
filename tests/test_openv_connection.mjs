import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../ext/ui-build/data/app/connection.js', import.meta.url), 'utf8');
const sandbox = { window: {}, Uint8Array, Array, Object, TypeError, Error };
vm.runInNewContext(source, sandbox, { filename: 'connection.js' });
const { create, WAIT_MS } = sandbox.window.OpenVConnectionCoordinator;
assert.equal(WAIT_MS, 90000);

function fixture(crypto = { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } }) {
  const timers = new Map();
  const changes = [];
  let next = 0;
  const coordinator = create({ crypto,
    schedule(fn, ms) { assert.equal(ms, WAIT_MS); const id = ++next; timers.set(id, fn); return id; },
    cancel(id) { timers.delete(id); },
    onChange(state) { changes.push({ ...state }); },
  });
  return { coordinator, timers, changes };
}
{
  const { coordinator: c, timers, changes } = fixture();
  const calls = [];
  assert.equal(c.start('play.example:30120', (address, nonce) => {
    calls.push([address, nonce]); return true;
  }).ok, true);
  assert.deepEqual(calls, [['play.example:30120', 'ab'.repeat(16)]]);
  assert.equal(c.active(), true);
  assert.equal(c.start('other.example:30120', () => { throw Error('duplicate dispatched'); }).reason, 'busy');
  c.progress();
  assert.equal(changes.at(-1).phase, 'connecting');
  const stale = timers.values().next().value;
  assert.equal(c.failed(), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(changes.at(-1).phase, 'failed');
  assert.equal(c.start('other.example:30120', () => true).ok, true);
  stale(); // stale timer from prior native attempt must not unlock the replacement
  assert.equal(c.active(), true);
  timers.values().next().value();
  assert.equal(c.active(), false);
  assert.equal(changes.at(-1).phase, 'timeout');
  assert.equal(c.failed(), false);
}
{
  const { coordinator: c, timers, changes } = fixture();
  assert.equal(c.start('a:1', () => false).reason, 'dispatch');
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(changes.at(-1).phase, 'dispatch_failed');
  assert.equal(c.start('a:1', () => { throw Error('native'); }).reason, 'dispatch');
  assert.equal(c.start('a:1', () => true).ok, true);
  assert.equal(c.dispose(), true);
  assert.equal(c.active(), false);
}
{
  const { coordinator: c } = fixture(null);
  let called = false;
  assert.equal(c.start('a:1', () => { called = true; return true; }).reason, 'crypto');
  assert.equal(called, false);
}
{
  const c = create({ crypto: { getRandomValues: b => b },
    schedule() { throw Error('no timers'); }, cancel() {}, onChange() {} });
  assert.equal(c.start('a:1', () => true).reason, 'timer');
  assert.equal(c.active(), false);
}
{
  const c = create({ crypto: { getRandomValues: b => new Uint8Array(b.length) },
    schedule() { return 1; }, cancel() {}, onChange() {} });
  assert.equal(c.start('a:1', () => true).reason, 'crypto');
}
console.log('PASS: native connection coordination, nonce, duplicate fencing, timeout, stale callbacks and failure recovery');

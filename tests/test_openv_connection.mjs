import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../ext/ui-build/data/app/connection.js', import.meta.url), 'utf8');
const sandbox = { window: {}, Uint8Array, Array, Object, TypeError, Error };
vm.runInNewContext(source, sandbox, { filename: 'connection.js' });
const { create, WAIT_MS, PROBE_MS } = sandbox.window.OpenVConnectionCoordinator;
assert.equal(PROBE_MS, 5000);
assert.equal(WAIT_MS, 90000);

function fixture(crypto = { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } }) {
  const timers = new Map();
  const changes = [];
  const probes = [];
  let next = 0;
  const coordinator = create({ crypto,
    schedule(fn, ms) { assert.ok(ms === WAIT_MS || ms === PROBE_MS); const id = ++next; timers.set(id, () => { timers.delete(id); fn(); }); return id; },
    cancel(id) { timers.delete(id); },
    onChange(state) { changes.push({ ...state }); },
    probe(nonce) { probes.push(nonce); return true; },
  });
  return { coordinator, timers, changes, probes };
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
  assert.equal(c.accepted('ab'.repeat(16)), true);
  assert.equal(c.progress('ab'.repeat(16)), true);
  assert.equal(changes.at(-1).phase, 'connecting');
  assert.equal(c.progress(undefined), false);
  assert.equal(c.failed(undefined), false);
  const stale = timers.values().next().value;
  assert.equal(c.failed('ab'.repeat(16)), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(changes.at(-1).phase, 'failed');
  assert.equal(c.start('other.example:30120', () => true).ok, true);
  stale(); // stale timer from prior native attempt must not unlock the replacement
  assert.equal(c.active(), true);
  timers.values().next().value();
  assert.equal(c.active(), true);
  assert.equal(changes.at(-1).phase, 'checking');
  assert.equal(c.probed('ab'.repeat(16), 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(c.failed('ab'.repeat(16)), false);
}
{
  let counter = 0;
  const { coordinator: c, timers, changes } = fixture({ getRandomValues(bytes) { bytes.fill(++counter); return bytes; } });
  assert.equal(c.start('a:1', () => true).ok, true);
  const old = '01'.repeat(16);
  const staleTimer = timers.values().next().value;
  assert.equal(c.rejected('ff'.repeat(16)), false);
  assert.equal(c.rejected(old), true);
  assert.equal(changes.at(-1).phase, 'rejected');
  assert.equal(c.start('b:2', () => true).ok, true);
  assert.equal(c.failed(old), false);
  assert.equal(c.closed(old), false);
  assert.equal(c.accepted(old), false);
  assert.equal(c.progress(old), false);
  staleTimer();
  assert.equal(c.active(), true);
  assert.equal(c.accepted('02'.repeat(16)), true);
  assert.equal(c.transport('02'.repeat(16)), true);
  assert.equal(changes.at(-1).phase, 'transport');
  assert.equal(c.progress('02'.repeat(16)), true);
  assert.equal(changes.at(-1).phase, 'transport');
  assert.equal(c.closed('02'.repeat(16)), true);
  assert.equal(changes.at(-1).phase, 'closed');
  assert.equal(c.start('c:3', () => true).ok, true);
  assert.equal(timers.size, 1); // a new request owns its own watchdog
  assert.equal(c.active(), true);
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'checking');
  assert.equal(c.probed('03'.repeat(16), 'absent'), true);
  assert.equal(c.active(), false);
}
{
  const { coordinator: c, changes } = fixture();
  assert.equal(c.start('a:1', (_, nonce) => {
    assert.equal(c.rejected(nonce), true);
    return true;
  }).reason, 'native');
  assert.equal(c.active(), false);
  assert.equal(changes.at(-1).phase, 'rejected');
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
    schedule() { throw Error('no timers'); }, cancel() {}, onChange() {}, probe() { return true; } });
  assert.equal(c.start('a:1', () => true).reason, 'timer');
  assert.equal(c.active(), false);
}
{
  const c = create({ crypto: { getRandomValues: b => new Uint8Array(b.length) },
    schedule() { return 1; }, cancel() {}, onChange() {}, probe() { return true; } });
  assert.equal(c.start('a:1', () => true).reason, 'crypto');
}
{
  const { coordinator: c, timers, changes, probes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('game.example:30120', () => true).ok, true);
  timers.values().next().value();
  assert.deepEqual(probes, [token]);
  assert.equal(changes.at(-1).phase, 'checking');
  assert.equal(c.probed(token, 'invalid'), false);
  assert.equal(c.probed('ff'.repeat(16), 'absent'), false);
  assert.equal(c.probed(token, 'active'), true);
  assert.equal(changes.at(-1).phase, 'native_active');
  assert.equal(timers.size, 0);
  assert.equal(c.requestCancel(() => false), false);
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.requestCancel(nonce => nonce === token), true);
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  assert.equal(c.requestCancel(() => true), false);
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.active(), true);
  assert.equal(c.closed('ff'.repeat(16)), false);
  assert.equal(c.closed(token), true);
  assert.equal(c.active(), false);
}
{
  const { coordinator: c, timers, changes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('game.example:30120', () => true).ok, true);
  timers.values().next().value();
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.active(), true);
  assert.equal(c.probed(token, 'other'), true);
  assert.equal(c.active(), false);
}
{
  let counter = 0;
  const { coordinator: c, changes, timers, probes } = fixture({
    getRandomValues(bytes) { bytes.fill(++counter); return bytes; },
  });
  const first = '01'.repeat(16), second = '02'.repeat(16);
  assert.equal(c.start('first.example:30120', () => true).ok, true);
  for (const stage of ['initializing', 'handshake', 'downloading', 'download_complete',
                       'fetching', 'connecting', 'connected', 'active']) {
    assert.equal(c.nativeStage(first, stage), true);
    assert.equal(changes.at(-1).phase, 'native_' + stage);
    assert.equal(c.active(), true);
  }
  assert.equal(timers.size, 0, 'native active has no pending connection timeout');
  assert.equal(c.progress(first), true);
  assert.equal(changes.at(-1).phase, 'native_active', 'legacy progress cannot downgrade active');
  assert.equal(c.transport(first), true);
  assert.equal(changes.at(-1).phase, 'native_active', 'late transport event cannot downgrade active');
  assert.equal(c.nativeStage(first, 'downloading'), false, 'late native stage cannot downgrade active');
  assert.equal(c.probed(first, 'pending'), false, 'stale pending probe cannot downgrade active');
  assert.equal(changes.at(-1).phase, 'native_active');
  assert.equal(c.nativeStage(first, '__proto__'), false);
  assert.equal(c.nativeStage(first, 'idle'), false);
  assert.equal(c.nativeStage(second, 'downloading'), false);
  assert.equal(c.closed(first), true);
  assert.equal(c.start('second.example:30120', () => true).ok, true);
  assert.equal(c.nativeStage(first, 'active'), false, 'old native state cannot affect replacement');
  assert.equal(c.nativeStage(second, 'downloading'), true);
  assert.equal(changes.at(-1).phase, 'native_downloading');
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'checking');
  assert.deepEqual(probes, [second]);
  assert.equal(c.probed(second, 'pending'), true);
  assert.equal(changes.at(-1).phase, 'native_pending');
  assert.equal(timers.size, 1, 'pending native connection must be probed again');
  timers.values().next().value();
  assert.equal(probes.length, 2);
  assert.equal(c.probed(second, 'active'), true);
  assert.equal(changes.at(-1).phase, 'native_active');
  assert.equal(timers.size, 0);
  assert.equal(c.requestCancel(() => true), true);
  assert.equal(c.nativeStage(second, 'active'), false, 'cancellation cannot be undone by native stage');
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  assert.equal(c.closed(second), true);
}
{
  const { coordinator: c, timers, changes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('play.example:30120', () => true).ok, true);
  const staleRequested = timers.values().next().value;
  assert.equal(c.accepted(token), true);
  staleRequested(); // canceled callback from this same request must not restart probe
  assert.equal(changes.at(-1).phase, 'accepted');
  assert.equal(c.nativeStage(token, 'connected'), true);
  assert.equal(c.nativeStage(token, 'downloading'), false);
  assert.equal(changes.at(-1).phase, 'native_connected');
  const staleConnected = timers.values().next().value;
  assert.equal(c.requestCancel(() => true), true);
  staleConnected(); // a queued pre-cancel timeout cannot undo cancellation
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  assert.equal(c.active(), true);
  assert.equal(c.closed(token), true);
  assert.equal(c.active(), false);
}

{
  // A timed-out native disconnect remains irrevocable until verified closure.
  let counter = 0;
  const { coordinator: c, timers, changes } = fixture({
    getRandomValues(bytes) { bytes.fill(++counter); return bytes; },
  });
  const old = '01'.repeat(16), next = '02'.repeat(16);
  let cancellations = 0;
  assert.equal(c.start('first.example:30120', () => true).ok, true);
  assert.equal(c.nativeStage(old, 'connected'), true);
  assert.equal(c.requestCancel(() => { cancellations++; return true; }), true);
  for (const stage of ['initializing', 'connected', 'active'])
    assert.equal(c.nativeStage(old, stage), false);
  assert.equal(c.accepted(old), false);
  assert.equal(c.progress(old), false);
  assert.equal(c.transport(old), false);
  assert.equal(c.failed(old), false);
  assert.equal(c.rejected(old), false);
  assert.equal(c.probed(old, 'active'), true);
  assert.equal(c.probed(old, 'pending'), true);
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.nativeStage(old, 'active'), false);
  assert.equal(c.progress(old), false);
  assert.equal(c.failed(old), false);
  assert.equal(c.rejected(old), false);
  assert.equal(c.probed(old, 'active'), true);
  assert.equal(c.probed(old, 'pending'), true);
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.start('second.example:30120', () => true).reason, 'busy');
  assert.equal(c.requestCancel(() => { cancellations++; return true; }), true);
  assert.equal(cancellations, 2, 'unconfirmed cancellation may be retried');
  assert.equal(c.probed(old, 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(c.start('second.example:30120', () => true).ok, true);
  assert.equal(c.closed(old), false, 'stale closure cannot release new nonce');
  assert.equal(c.owns(next), true);
}
{
  // Failed retry must not clear an earlier successful cancellation intent.
  const { coordinator: c, timers, changes } = fixture();
  const nonce = 'ab'.repeat(16);
  assert.equal(c.start('game.example:30120', () => true).ok, true);
  assert.equal(c.requestCancel(() => true), true);
  timers.values().next().value();
  assert.equal(c.requestCancel(() => false), false);
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.nativeStage(nonce, 'active'), false);
  assert.equal(c.failed(nonce), false);
  assert.equal(c.probed(nonce, 'other'), true);
  assert.equal(c.active(), false);
}

console.log('PASS: native connection coordination, nonce, duplicate fencing, phase-fenced timers, native stage order and failure recovery');

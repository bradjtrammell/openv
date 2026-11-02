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
  assert.equal(c.active(), true, 'failure callback does not prove native IDLE');
  assert.equal(changes.at(-1).phase, 'native_closing');
  assert.equal(c.probed('ab'.repeat(16), 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(changes.at(-1).phase, 'closed');
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
  assert.equal(c.active(), true, 'ambiguous dispatch cannot unlock native transport');
  assert.equal(timers.size, 1, 'uncertain dispatch must retry native probes');
  assert.equal(changes.at(-1).phase, 'dispatch_unconfirmed');
  assert.equal(c.start('a:1', () => true).reason, 'busy');
  assert.equal(c.probed('ab'.repeat(16), 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(c.start('a:1', () => { throw Error('native'); }).reason, 'dispatch');
  assert.equal(c.active(), true, 'throwing bridge may have dispatched');
  assert.equal(c.probed('ab'.repeat(16), 'other'), true);
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


{
  // A disconnect with no native terminal event must keep probing, not stop
  // forever after one timeout. A later IDLE observation releases the gate.
  const { coordinator: c, timers, changes, probes } = fixture();
  const nonce = 'ab'.repeat(16);
  assert.equal(c.start('game.example:30120', () => true).ok, true);
  assert.equal(c.requestCancel(() => true), true);
  for (let i = 0; i < 4; i++) {
    timers.values().next().value();
    assert.equal(changes.at(-1).phase, 'unconfirmed');
    assert.equal(probes.length, i + 1);
    assert.equal(probes.at(-1), nonce);
    assert.equal(c.probed(nonce, 'pending'), true);
    assert.equal(timers.size, 1, 'cancel polling must remain armed');
    assert.equal(c.nativeStage(nonce, 'active'), false);
  }
  assert.equal(c.probed(nonce, 'absent'), true);
  assert.equal(timers.size, 0);
  assert.equal(c.active(), false);
}

{
  // A native error precedes IDLE: duplicate/stale events cannot revive it.
  const { coordinator: c, timers, changes, probes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('play.example:30120', () => true).ok, true);
  const stale = timers.values().next().value;
  assert.equal(c.nativeStage(token, 'connecting'), true);
  assert.equal(c.terminating(token), true);
  assert.equal(changes.at(-1).phase, 'native_closing');
  assert.equal(c.failed(token), true, 'duplicate failure is idempotent');
  stale();
  assert.equal(changes.at(-1).phase, 'native_closing');
  assert.equal(c.start('second.example:30120', () => true).reason, 'busy');
  assert.equal(c.nativeStage(token, 'active'), false);
  assert.equal(c.progress(token), false);
  assert.equal(c.transport(token), false);
  assert.equal(c.probed(token, 'active'), true);
  assert.equal(c.probed(token, 'pending'), true);
  assert.equal(changes.at(-1).phase, 'native_closing');
  timers.values().next().value();
  assert.equal(probes.at(-1), token);
  assert.equal(c.active(), true);
  assert.equal(c.requestCancel(() => true), true, 'operator can retry disconnect');
  assert.equal(c.nativeStage(token, 'active'), false);
  assert.equal(c.probed(token, 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
  assert.equal(c.start('second.example:30120', () => true).ok, true);
  assert.equal(c.terminating('ff'.repeat(16)), false);
}
{
  // A failed watchdog cannot authorize a replacement request.
  let count = 0;
  const states = [];
  const c = create({
    crypto: { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } },
    schedule() { if (++count === 1) return 1; throw Error('timer failure'); },
    cancel() {}, onChange(s) { states.push(s); }, probe() { return true; },
  });
  const token = 'ab'.repeat(16);
  assert.equal(c.start('a:1', () => true).ok, true);
  assert.equal(c.terminating(token), true);
  assert.equal(c.active(), true);
  assert.equal(states.at(-1).phase, 'unconfirmed');
  assert.equal(c.nativeStage(token, 'active'), false);
  assert.equal(c.closed(token), true);
  assert.equal(c.active(), false);
}
{
  const { coordinator: c, timers, changes, probes } = fixture();
  const token = 'ab'.repeat(16);
  for (const invalid of ['', 'AB'.repeat(16), 'x'.repeat(32)])
    assert.equal(c.restore(invalid, 'play.example:30120', 'active'), false);
  assert.equal(c.restore(token, 'play.example:30120', '__proto__'), false);
  assert.equal(c.restore(token, 'play.example:30120', 'active'), true);
  assert.equal(c.active(), true);
  assert.equal(changes.at(-1).phase, 'checking');
  assert.deepEqual(probes, [token]);
  assert.equal(c.start('other.example:30120', () => true).reason, 'busy');
  assert.equal(c.restore(token, 'other.example:30120', 'active'), false);
  assert.equal(c.probed(token, 'active'), true);
  assert.equal(changes.at(-1).phase, 'native_active');
  assert.equal(c.requestCancel(nonce => nonce === token), true);
  assert.equal(c.closed(token), true);
  assert.equal(c.active(), false);
  assert.equal(timers.size, 0);
}
{
  let counter = 0;
  const { coordinator: c, timers } = fixture({
    getRandomValues(bytes) { bytes.fill(++counter); return bytes; },
  });
  const old = 'ab'.repeat(16);
  assert.equal(c.restore(old, 'play.example:30120', 'pending'), true);
  const stale = timers.values().next().value;
  assert.equal(c.closed(old), true);
  assert.equal(c.start('next.example:30120', () => true).ok, true);
  stale();
  assert.equal(c.active(), true, 'stale restored watchdog unlocked a new connection');
  assert.equal(c.owns('01'.repeat(16)), true);
  assert.equal(c.probed(old, 'absent'), false);
}
{
  // A late server card must never reopen admission after a native cancel.
  // A CEF reload during asynchronous teardown must recover the cancellation
  // fence rather than treating the old native nonce as a fresh connection.
  const { coordinator: c, changes, timers, probes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('play.example:30120', () => true).ok, true);
  assert.equal(c.canAcceptAdmission(token), true);
  assert.equal(c.nativeStage(token, 'active'), true);
  assert.equal(c.canAcceptAdmission(token), false, 'active session cannot accept a late card');
  assert.equal(c.requestCancel(() => true), true);
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.probed(token, 'pending'), true);
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.closed(token), true);
  assert.equal(c.restore(token, 'play.example:30120', 'connected', true), true);
  assert.equal(changes.at(-1).phase, 'native_closing');
  assert.equal(c.canAcceptAdmission(token), false);
  assert.deepEqual(probes.at(-1), token);
  assert.equal(c.probed(token, 'active'), true);
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.start('another.example:30120', () => true).reason, 'busy');
  timers.values().next().value();
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.probed(token, 'absent'), true);
  assert.equal(c.active(), false);
  assert.equal(c.restore(token, 'play.example:30120', 'pending', 'true'), false);
  assert.equal(c.restore(token, 'play.example:30120', 'pending', false), true);
  assert.equal(c.canAcceptAdmission(token), true);
  assert.equal(c.terminating(token), true);
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.probed(token, 'absent'), true);
}
{
  // A synchronous native response is authoritative even if the bridge
  // subsequently returns false or throws. Do not replace ACTIVE with an
  // unconfirmed UI state or destroy a newly armed pending probe.
  for (const state of ['active', 'pending']) {
    for (const mode of ['false', 'throw']) {
      const timers = new Map(), changes = [];
      let sequence = 0, c;
      const token = 'ab'.repeat(16);
      c = create({
        crypto: { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } },
        schedule(fn) { const id = ++sequence; timers.set(id, () => { timers.delete(id); fn(); }); return id; },
        cancel(id) { timers.delete(id); },
        onChange(s) { changes.push(s); },
        probe(nonce) {
          assert.equal(nonce, token);
          assert.equal(c.probed(nonce, state), true);
          if (mode === 'throw') throw Error('bridge returned after callback');
          return false;
        },
      });
      assert.equal(c.start('play.example:30120', () => true).ok, true);
      const watchdog = timers.values().next().value;
      watchdog();
      assert.equal(changes.at(-1).phase, state === 'active' ? 'native_active' : 'native_pending',
        'synchronous native response was overwritten by bridge failure');
      assert.equal(c.active(), true);
      assert.equal(timers.size, state === 'active' ? 0 : 1);
      assert.equal(c.closed(token), true);
      assert.equal(timers.size, 0);
    }
  }
}
{
  // Cancellation must fence reentrant native progress and admission BEFORE
  // calling the bridge. A failed dispatch is not native closure, and an
  // explicit retry remains possible without accepting another card.
  const { coordinator: c, timers, changes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('play.example:30120', () => true).ok, true);
  assert.equal(c.requestCancel(nonce => {
    assert.equal(nonce, token);
    assert.equal(c.canAcceptAdmission(nonce), false);
    assert.equal(c.nativeStage(nonce, 'active'), false);
    assert.equal(c.accepted(nonce), false);
    assert.equal(c.transport(nonce), false);
    return false;
  }), false);
  assert.equal(changes.at(-1).phase, 'unconfirmed');
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.active(), true);
  assert.equal(timers.size, 1, 'failed native cancel must retain a closure probe');
  assert.equal(c.requestCancel(nonce => {
    assert.equal(c.canAcceptAdmission(nonce), false);
    return true;
  }), true);
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  assert.equal(c.probed(token, 'active'), true);
  assert.equal(changes.at(-1).phase, 'cancel_requested');
  assert.equal(c.closed(token), true);
  assert.equal(timers.size, 0);
}
{
  // A synchronous native terminal callback must not be downgraded by the
  // returning cancellation dispatch.
  const { coordinator: c, changes } = fixture();
  const token = 'ab'.repeat(16);
  assert.equal(c.start('play.example:30120', () => true).ok, true);
  assert.equal(c.requestCancel(nonce => {
    assert.equal(c.terminating(nonce), true);
    return true;
  }), true);
  assert.equal(changes.at(-1).phase, 'native_closing');
  assert.equal(c.canAcceptAdmission(token), false);
  assert.equal(c.probed(token, 'absent'), true);
  assert.equal(c.active(), false);
}

{
  // Native acceptance can be delivered *inside* dispatch before the bridge
  // returns false or throws. It must retain the native watchdog and gate.
  for (const phase of ['accepted', 'transport', 'native_pending', 'native_active']) {
    for (const mode of ['false', 'throw']) {
      const { coordinator: c, changes, timers } = fixture();
      const token = 'ab'.repeat(16);
      const result = c.start('play.example:30120', (_, nonce) => {
        assert.equal(nonce, token);
        if (phase === 'accepted') assert.equal(c.accepted(nonce), true);
        else if (phase === 'transport') assert.equal(c.transport(nonce), true);
        else assert.equal(c.probed(nonce, phase === 'native_pending' ? 'pending' : 'active'), true);
        if (mode === 'throw') throw Error('bridge threw after native callback');
        return false;
      });
      assert.equal(result.ok, true, 'native callback wins over bridge ' + mode);
      assert.equal(c.active(), true);
      assert.equal(changes.at(-1).phase, phase);
      assert.equal(timers.size, ['transport', 'native_active'].includes(phase) ? 0 : 1);
      assert.equal(c.canAcceptAdmission(token), phase !== 'native_active');
      assert.equal(c.closed(token), true);
      assert.equal(timers.size, 0);
    }
  }
}
{
  // An ambiguous dispatch without native callbacks keeps checking, including
  // when a probe throws, until the native side proves the transport is gone.
  let tokenCounter = 0, timerCounter = 0;
  const timers = new Map(), changes = [], probes = [];
  let c;
  c = create({
    crypto: { getRandomValues(bytes) { bytes.fill(++tokenCounter); return bytes; } },
    schedule(fn, ms) {
      assert.equal(ms === PROBE_MS || ms === WAIT_MS, true);
      const id = ++timerCounter;
      timers.set(id, () => { timers.delete(id); fn(); });
      return id;
    },
    cancel(id) { timers.delete(id); },
    onChange(s) { changes.push(s); },
    probe(nonce) { probes.push(nonce); throw Error('native bridge temporarily unavailable'); },
  });
  const old = '01'.repeat(16);
  assert.equal(c.start('first.example:30120', () => false).reason, 'dispatch');
  assert.deepEqual(probes, [old]);
  assert.equal(c.start('next.example:30120', () => true).reason, 'busy');
  const stale = timers.values().next().value;
  stale();
  assert.deepEqual(probes, [old, old]);
  assert.equal(changes.at(-1).phase, 'dispatch_unconfirmed');
  assert.equal(c.probed(old, 'active'), true);
  assert.equal(changes.at(-1).phase, 'native_active');
  assert.equal(timers.size, 0);
  assert.equal(c.requestCancel(() => true), true);
  assert.equal(c.probed(old, 'absent'), true);
  assert.equal(c.start('next.example:30120', () => true).ok, true);
  stale();
  assert.equal(c.active(), true, 'stale failed-dispatch probe cannot release new nonce');
  assert.equal(c.owns('02'.repeat(16)), true);
}
{
  // Synchronous native rejection/closure must not resurrect a finished
  // request even if dispatch later reports success or failure.
  for (const mode of ['false', 'true', 'throw']) {
    for (const terminal of ['rejected', 'closed']) {
      const { coordinator: c, changes } = fixture();
      const token = 'ab'.repeat(16);
      const result = c.start('play.example:30120', (_, nonce) => {
        assert.equal(c[terminal](nonce), true);
        if (mode === 'throw') throw Error('late bridge error');
        return mode === 'true';
      });
      assert.equal(result.ok, false);
      assert.equal(result.reason, 'native');
      assert.equal(changes.at(-1).phase, terminal);
      assert.equal(c.active(), false);
      assert.equal(c.start('next.example:30120', () => true).ok, true);
      assert.equal(c.closed(token), true);
    }
  }
}
{
  // If a false dispatch triggers a synchronous native probe, that response
  // is authoritative: ACTIVE/PENDING retain the gate, ABSENT releases it.
  for (const state of ['active', 'pending', 'absent']) {
    const timers = new Map(), changes = [];
    let next = 0, c;
    const token = 'ab'.repeat(16);
    c = create({
      crypto: { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } },
      schedule(fn) { const id = ++next; timers.set(id, () => { timers.delete(id); fn(); }); return id; },
      cancel(id) { timers.delete(id); },
      onChange(s) { changes.push(s); },
      probe(nonce) { assert.equal(c.probed(nonce, state), true); return false; },
    });
    const result = c.start('play.example:30120', () => false);
    assert.equal(result.ok, state !== 'absent');
    assert.equal(c.active(), state !== 'absent');
    assert.equal(changes.at(-1).phase, state === 'absent' ? 'closed' : 'native_' + state);
    assert.equal(timers.size, state === 'pending' ? 1 : 0);
  }
}

{
  // Even a UI state observer can be reentrant. A native callback delivered
  // while the uncertain-dispatch state is being published must keep its own
  // watchdog; the dispatch probe must not cancel it or overwrite its phase.
  for (const event of ['accepted', 'terminating']) {
    const timers = new Map(), changes = [];
    let next = 0, c;
    const token = 'ab'.repeat(16);
    c = create({
      crypto: { getRandomValues(bytes) { bytes.fill(0xab); return bytes; } },
      schedule(fn, ms) {
        const id = ++next;
        timers.set(id, { ms, fn: () => { timers.delete(id); fn(); } });
        return id;
      },
      cancel(id) { timers.delete(id); },
      onChange(s) {
        changes.push(s);
        if (s.phase === 'dispatch_unconfirmed')
          assert.equal(c[event](token), true);
      },
      probe() { throw Error('probe should not replace the native watchdog'); },
    });
    const result = c.start('play.example:30120', () => false);
    assert.equal(result.ok, event === 'accepted');
    assert.equal(c.active(), true);
    assert.equal(changes.at(-1).phase, event === 'accepted' ? 'accepted' : 'native_closing');
    assert.equal(timers.size, 1);
    assert.equal([...timers.values()][0].ms, event === 'accepted' ? WAIT_MS : PROBE_MS);
    assert.equal(c.closed(token), true);
    assert.equal(timers.size, 0);
  }
}
console.log('PASS: native connection coordination, CEF reload recovery, nonce, duplicate fencing, phase-fenced timers, native stage order and asynchronous teardown recovery');

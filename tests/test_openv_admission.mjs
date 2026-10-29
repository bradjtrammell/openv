import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../ext/ui-build/data/app/admission.js', import.meta.url), 'utf8');
const sandbox = { window: {}, Object, TypeError, JSON, Array };
vm.runInNewContext(source, sandbox, { filename: 'admission.js' });
const { create, supported, MAX_CARD_BYTES, SUBMISSION_MS } = sandbox.window.OpenVAdmission;
const schema = {
  type: 'AdaptiveCard', version: '1.0',
  body: [
    { type: 'TextBlock', text: 'Connect to OpenV', size: 'Large', weight: 'Bolder' },
    { type: 'TextBlock', text: 'Enter the one-time game connection code.', wrap: true },
    { type: 'Input.Text', id: 'join_code', placeholder: 'OpenV one-time join code', maxLength: 43 },
  ],
  actions: [{ type: 'Action.Submit', title: 'Join server' }],
};
const card = JSON.stringify(schema), nonce = 'a'.repeat(32), other = 'b'.repeat(32);
const code = 'A'.repeat(42) + '_';
assert.equal(MAX_CARD_BYTES, 4096);
assert.equal(SUBMISSION_MS, 60000);
assert.equal(supported(card), true);
assert.equal(supported('not json'), false);
assert.equal(supported(card.repeat(50)), false);
for (const invalid of [
  { ...schema, actions: [{ type: 'Action.OpenUrl', url: 'https://evil.invalid' }] },
  { ...schema, body: [...schema.body, { type: 'Input.Text', id: 'password' }] },
  { ...schema, body: [{ type: 'TextBlock', text: 'Different server' }, ...schema.body.slice(1)] },
  { ...schema, body: schema.body.map(x => x.id === 'join_code' ? { ...x, id: 'token' } : x) },
]) assert.equal(supported(JSON.stringify(invalid)), false);
const calls = [];
let visible = false, shouldDispatch = true, time = 1000, timerId = 0;
const timers = new Map(), expired = [];
const a = create({
  show() { visible = true; },
  hide() { visible = false; },
  dispatch(n, c) { calls.push([n, c]); return shouldDispatch; },
  schedule(fn, ms) { assert.equal(ms, SUBMISSION_MS); const id = ++timerId; timers.set(id, fn); return id; },
  cancel(id) { timers.delete(id); },
  now() { return time; },
  onExpire(nonce) { expired.push(nonce); },
});
assert.equal(a.present('wrong', card), false);
assert.equal(a.present(nonce, 'bad'), false);
assert.equal(a.present(nonce, card), true);
assert.equal(a.present(other, card), false);
assert.equal(a.owns(nonce), true);
assert.equal(a.owns(other), false);
assert.equal(visible, true);
assert.equal(a.submit('invalid').reason, 'invalid');
assert.equal(calls.length, 0);
shouldDispatch = false;
assert.equal(a.submit(code).reason, 'dispatch');
assert.equal(a.active(), true);
shouldDispatch = true;
time += 59999;
assert.equal(a.submit(' ' + code + ' ').ok, true);
assert.equal(visible, false);
assert.equal(a.active(), false);
assert.equal(a.submit(code).reason, 'inactive');
assert.equal(a.present(other, card), true);
const stale = timers.get(timerId);
assert.equal(a.dismiss(), true);
stale();
assert.equal(expired.length, 0);
assert.equal(a.active(), false);
assert.equal(a.dismiss(), false);
assert.equal(calls.length, 2);
assert.equal(timers.size, 0);
assert.equal(a.present(nonce, card), true);
const staleAfterReplacement = timers.get(timerId);
assert.equal(a.dismiss(), true);
assert.equal(a.present(other, card), true);
staleAfterReplacement();
assert.equal(a.owns(other), true);
time += SUBMISSION_MS;
assert.equal(a.submit(code).reason, 'expired');
assert.equal(a.active(), false);
assert.equal(expired.at(-1), other);
assert.equal(a.present(nonce, card), true);
const timeout = timers.get(timerId);
timeout();
assert.equal(a.active(), false);
assert.equal(expired.at(-1), nonce);
assert.equal(timers.size, 0);
assert.equal(a.present(other, card), true);
time -= 1;
assert.equal(a.submit(code).reason, 'clock');
assert.equal(expired.at(-1), other);
assert.throws(() => create({show() {}}), TypeError);
assert.deepEqual(calls[1], [nonce, code]);
console.log('PASS: strict FXServer card schema, nonce fencing, 60-second expiry, stale timers, cancel and secret cleanup');

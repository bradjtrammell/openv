/* OpenV first-party native connection request coordinator.
 * UI-only state: it never authenticates, grants gameplay or declares success.
 * Native connectTo remains the sole owner of entitlement and session setup.
 */
(() => {
  'use strict';
  const WAIT_MS = 90000;

  function create({ crypto, schedule, cancel, onChange }) {
    if (typeof schedule !== 'function' || typeof cancel !== 'function' ||
        typeof onChange !== 'function') throw new TypeError('Invalid connection coordinator');
    let pending = null;
    let sequence = 0;

    function publish(phase, address = '') {
      onChange(Object.freeze({ phase, address, pending: pending !== null }));
    }
    function release(phase) {
      if (!pending) return false;
      const old = pending;
      pending = null;
      try { cancel(old.timer); } catch (_) { /* timer already fired or destroyed */ }
      publish(phase, old.address);
      return true;
    }
    function nonce() {
      if (!crypto || typeof crypto.getRandomValues !== 'function') return null;
      try {
        const bytes = new Uint8Array(16);
        const filled = crypto.getRandomValues(bytes);
        if (filled !== bytes) return null;
        return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
      } catch (_) { return null; }
    }
    function start(address, dispatch) {
      if (pending) return { ok: false, reason: 'busy' };
      if (typeof address !== 'string' || !address || typeof dispatch !== 'function') {
        return { ok: false, reason: 'invalid' };
      }
      const token = nonce();
      if (!token) return { ok: false, reason: 'crypto' };
      const id = ++sequence;
      pending = { id, address, token, phase: 'requested', timer: null };
      try {
        const timer = schedule(() => {
          if (pending && pending.id === id) release('timeout');
        }, WAIT_MS);
        if (timer === false || timer == null) throw new Error('timer unavailable');
        pending.timer = timer;
      } catch (_) {
        pending = null;
        return { ok: false, reason: 'timer' };
      }
      let dispatched = false;
      try { dispatched = dispatch(address, token) === true; } catch (_) { /* native bridge failure */ }
      if (!dispatched) {
        release('dispatch_failed');
        return { ok: false, reason: 'dispatch' };
      }
      // Native callbacks can execute synchronously during invokeNative.
      if (!pending || pending.id !== id) return { ok: false, reason: 'native' };
      if (pending.phase === 'requested') publish('requested', address);
      return { ok: true };
    }
    function matching(token) {
      return pending !== null && typeof token === 'string' && token === pending.token;
    }
    function accepted(token) {
      if (!matching(token)) return false;
      if (pending.phase === 'requested') {
        pending.phase = 'accepted';
        publish('accepted', pending.address);
      }
      return true;
    }
    function progress(token) {
      if (!matching(token)) return false;
      if (pending.phase !== 'transport') {
        pending.phase = 'connecting';
        publish('connecting', pending.address);
      }
      return true;
    }
    function transport(token) {
      if (!matching(token)) return false;
      pending.phase = 'transport';
      publish('transport', pending.address);
      return true;
    }
    return Object.freeze({
      start,
      active: () => pending !== null,
      accepted,
      progress,
      transport,
      failed: token => matching(token) && release('failed'),
      rejected: token => matching(token) && release('rejected'),
      closed: token => matching(token) && release('closed'),
      // A native UI frame may be destroyed while a request is pending.
      dispose: () => release('disposed'),
    });
  }

  window.OpenVConnectionCoordinator = Object.freeze({ create, WAIT_MS });
})();

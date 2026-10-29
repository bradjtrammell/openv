/* OpenV native transport state is authoritative. UI timeouts cannot unlock a live connection. */
(() => {
  'use strict';
  const WAIT_MS = 90000;
  const PROBE_MS = 5000;
  const NATIVE_STAGES = Object.freeze({
    initializing: 'native_initializing',
    handshake: 'native_handshake',
    downloading: 'native_downloading',
    download_complete: 'native_download_complete',
    fetching: 'native_fetching',
    connecting: 'native_connecting',
    connected: 'native_connected',
    active: 'native_active',
  });
  function create({ crypto, schedule, cancel, onChange, probe }) {
    if (![schedule, cancel, onChange, probe].every(fn => typeof fn === 'function'))
      throw new TypeError('Invalid connection coordinator');
    let pending = null;
    let sequence = 0;
    function publish(phase, address = '') {
      onChange(Object.freeze({ phase, address, pending: pending !== null }));
    }
    function clear(request) {
      if (request.timer !== null) {
        try { cancel(request.timer); } catch (_) { /* disposed */ }
        request.timer = null;
      }
    }
    function release(phase) {
      if (!pending) return false;
      const old = pending;
      pending = null;
      clear(old);
      publish(phase, old.address);
      return true;
    }
    function arm(request, ms, callback) {
      clear(request);
      try {
        const timer = schedule(() => {
          if (pending !== request) return;
          request.timer = null;
          callback();
        }, ms);
        if (timer === false || timer == null) throw Error('timer unavailable');
        request.timer = timer;
        return true;
      } catch (_) { return false; }
    }
    function unconfirmed(request) {
      if (pending !== request) return;
      request.phase = 'unconfirmed';
      publish('unconfirmed', request.address);
    }
    function checkNative(request) {
      if (pending !== request || request.phase === 'transport' || request.phase === 'native_active') return;
      request.phase = 'checking';
      publish('checking', request.address);
      if (!arm(request, PROBE_MS, () => unconfirmed(request))) {
        unconfirmed(request);
        return;
      }
      try { if (probe(request.token) !== true) { clear(request); unconfirmed(request); } }
      catch (_) { clear(request); unconfirmed(request); }
    }
    function nonce() {
      if (!crypto || typeof crypto.getRandomValues !== 'function') return null;
      try {
        const bytes = new Uint8Array(16);
        if (crypto.getRandomValues(bytes) !== bytes) return null;
        return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
      } catch (_) { return null; }
    }
    function start(address, dispatch) {
      if (pending) return { ok: false, reason: 'busy' };
      if (typeof address !== 'string' || !address || typeof dispatch !== 'function')
        return { ok: false, reason: 'invalid' };
      const token = nonce();
      if (!token) return { ok: false, reason: 'crypto' };
      const request = { id: ++sequence, address, token, phase: 'requested', timer: null };
      pending = request;
      if (!arm(request, WAIT_MS, () => checkNative(request))) {
        pending = null;
        return { ok: false, reason: 'timer' };
      }
      let sent = false;
      try { sent = dispatch(address, token) === true; } catch (_) { /* bridge failed */ }
      if (!sent) { release('dispatch_failed'); return { ok: false, reason: 'dispatch' }; }
      if (pending !== request) return { ok: false, reason: 'native' };
      if (request.phase === 'requested') publish('requested', address);
      return { ok: true };
    }
    function matching(token) {
      return pending !== null && typeof token === 'string' && pending.token === token;
    }
    function progress(phase, token) {
      if (!matching(token)) return false;
      if (pending.phase === 'transport' || pending.phase === 'cancel_requested' ||
          pending.phase.startsWith('native_')) return true;
      pending.phase = phase;
      publish(phase, pending.address);
      const request = pending;
      if (!arm(request, WAIT_MS, () => checkNative(request))) unconfirmed(request);
      return true;
    }
    function transport(token) {
      if (!matching(token)) return false;
      if (pending.phase === 'cancel_requested' || pending.phase.startsWith('native_')) return true;
      clear(pending);
      pending.phase = 'transport';
      publish('transport', pending.address);
      return true;
    }
    function nativeStage(token, stage) {
      if (!matching(token) || !Object.prototype.hasOwnProperty.call(NATIVE_STAGES, stage) ||
          pending.phase === 'cancel_requested') return false;
      const request = pending;
      const phase = NATIVE_STAGES[stage];
      if (request.phase === 'native_active' && phase !== 'native_active') return false;
      request.phase = phase;
      publish(phase, request.address);
      if (phase === 'native_active') clear(request);
      else if (!arm(request, WAIT_MS, () => checkNative(request))) unconfirmed(request);
      return true;
    }
    function probed(token, state) {
      if (!matching(token) || !['active', 'pending', 'absent', 'other'].includes(state)) return false;
      if (state === 'absent' || state === 'other') return release('closed');
      if (state === 'active') {
        clear(pending);
        if (pending.phase !== 'cancel_requested') {
          pending.phase = 'native_active';
          publish('native_active', pending.address);
        }
        return true;
      }
      if (pending.phase === 'cancel_requested') return true;
      if (pending.phase === 'native_active') return false;
      const request = pending;
      request.phase = 'native_pending';
      publish('native_pending', request.address);
      if (!arm(request, PROBE_MS, () => checkNative(request))) unconfirmed(request);
      return true;
    }
    function requestCancel(dispatch) {
      if (!pending || typeof dispatch !== 'function' || pending.phase === 'cancel_requested') return false;
      const request = pending;
      let sent = false;
      try { sent = dispatch(request.token) === true; } catch (_) { /* bridge failed */ }
      if (pending !== request) return sent;
      if (!sent) { unconfirmed(request); return false; }
      request.phase = 'cancel_requested';
      publish('cancel_requested', request.address);
      if (!arm(request, PROBE_MS, () => unconfirmed(request))) unconfirmed(request);
      return true;
    }
    return Object.freeze({
      start, active: () => pending !== null,
      owns: token => matching(token),
      accepted: token => progress('accepted', token),
      progress: token => progress('connecting', token),
      transport, nativeStage, probed, requestCancel,
      failed: token => matching(token) && release('failed'),
      rejected: token => matching(token) && release('rejected'),
      closed: token => matching(token) && release('closed'),
      dispose: () => release('disposed'),
    });
  }
  window.OpenVConnectionCoordinator = Object.freeze({ create, WAIT_MS, PROBE_MS });
})();

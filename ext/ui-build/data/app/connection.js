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
  const NATIVE_ORDER = Object.freeze({
    initializing: 1, handshake: 2, downloading: 3, download_complete: 4,
    fetching: 5, connecting: 6, connected: 7, active: 8,
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
      // Invalidate even a callback already queued before clearTimeout.
      request.timerEpoch += 1;
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
      const epoch = request.timerEpoch;
      try {
        const timer = schedule(() => {
          if (pending !== request || request.timerEpoch !== epoch) return;
          request.timer = null;
          request.timerEpoch += 1; // A timer callback is single-use.
          callback();
        }, ms);
        if (timer === false || timer == null) throw Error('timer unavailable');
        if (request.timerEpoch !== epoch) {
          try { cancel(timer); } catch (_) { /* callback already ran */ }
          return false;
        }
        request.timer = timer;
        return true;
      } catch (_) { return false; }
    }
    function checkCancellation(request) {
      if (pending !== request || !request.cancellationRequested) return;
      // Continue probing after the first timeout; a native disconnect can be
      // asynchronous, and a single lost probe must not strand the UI forever.
      request.phase = 'unconfirmed';
      publish('unconfirmed', request.address);
      if (!arm(request, PROBE_MS, () => checkCancellation(request))) return;
      try { probe(request.token); } catch (_) { /* retry on the next probe */ }
    }
    function unconfirmed(request) {
      if (pending !== request) return;
      request.phase = 'unconfirmed';
      publish('unconfirmed', request.address);
    }
    function checkNative(request) {
      if (pending !== request || request.phase === 'transport' || request.phase === 'native_active' || request.phase === 'cancel_requested') return;
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
      const request = { id: ++sequence, address, token, phase: 'requested', timer: null, timerEpoch: 0, cancellationRequested: false, terminal: false };
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
      if (pending.cancellationRequested) return false;
      if (pending.phase === 'transport' || pending.phase.startsWith('native_')) return true;
      pending.phase = phase;
      publish(phase, pending.address);
      const request = pending;
      if (!arm(request, WAIT_MS, () => checkNative(request))) unconfirmed(request);
      return true;
    }
    function transport(token) {
      if (!matching(token)) return false;
      if (pending.cancellationRequested) return false;
      if (pending.phase.startsWith('native_')) return true;
      clear(pending);
      pending.phase = 'transport';
      publish('transport', pending.address);
      return true;
    }
    function nativeStage(token, stage) {
      if (!matching(token) || !Object.prototype.hasOwnProperty.call(NATIVE_STAGES, stage) ||
          pending.cancellationRequested) return false;
      const request = pending;
      const phase = NATIVE_STAGES[stage];
      if (request.phase === 'native_active' && phase !== 'native_active') return false;
      const previous = request.phase.startsWith('native_') ?
        request.phase.slice('native_'.length) : '';
      if (Object.prototype.hasOwnProperty.call(NATIVE_ORDER, previous) &&
          NATIVE_ORDER[stage] < NATIVE_ORDER[previous]) return false;
      request.phase = phase;
      publish(phase, request.address);
      if (phase === 'native_active') clear(request);
      else if (!arm(request, WAIT_MS, () => checkNative(request))) unconfirmed(request);
      return true;
    }
    function probed(token, state) {
      if (!matching(token) || !['active', 'pending', 'absent', 'other'].includes(state)) return false;
      if (state === 'absent' || state === 'other') return release('closed');
      // A live or pending probe cannot undo a sent disconnect; wait for native closure.
      if (pending.cancellationRequested) return true;
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
    function terminating(token) {
      if (!matching(token)) return false;
      const request = pending;
      if (request.terminal) return true;
      request.terminal = true;
      request.cancellationRequested = true;
      request.phase = 'native_closing';
      publish('native_closing', request.address);
      if (!arm(request, PROBE_MS, () => checkCancellation(request))) unconfirmed(request);
      return true;
    }
    function requestCancel(dispatch) {
      if (!pending || typeof dispatch !== 'function' || pending.phase === 'cancel_requested') return false;
      const request = pending;
      let sent = false;
      try { sent = dispatch(request.token) === true; } catch (_) { /* bridge failed */ }
      if (pending !== request) return sent;
      if (!sent) { unconfirmed(request); return false; }
      request.cancellationRequested = true;
      request.phase = 'cancel_requested';
      publish('cancel_requested', request.address);
      if (!arm(request, PROBE_MS, () => checkCancellation(request))) unconfirmed(request);
      return true;
    }
    return Object.freeze({
      start, active: () => pending !== null,
      owns: token => matching(token),
      accepted: token => progress('accepted', token),
      progress: token => progress('connecting', token),
      transport, nativeStage, probed, requestCancel, terminating,
      failed: token => terminating(token),
      rejected: token => matching(token) && !pending.cancellationRequested && release('rejected'),
      closed: token => matching(token) && release('closed'),
      dispose: () => release('disposed'),
    });
  }
  window.OpenVConnectionCoordinator = Object.freeze({ create, WAIT_MS, PROBE_MS });
})();

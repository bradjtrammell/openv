/* OpenV one-time FXServer admission. Never render untrusted Adaptive Card markup. */
(() => {
  'use strict';
  const MAX_CARD_BYTES = 4096;
  const SUBMISSION_MS = 60000;
  const CODE_PATTERN = /^[A-Za-z0-9_-]{43}$/;
  const NONCE_PATTERN = /^[0-9a-f]{32}$/;
  function supported(card) {
    if (typeof card !== 'string' || !card.length || card.length > MAX_CARD_BYTES) return false;
    try {
      const c = JSON.parse(card);
      if (!c || Array.isArray(c) || c.type !== 'AdaptiveCard' ||
          c.version !== '1.0' || !Array.isArray(c.body) || c.body.length !== 3 ||
          !Array.isArray(c.actions) || c.actions.length !== 1) return false;
      const [title, explanation, input] = c.body;
      const [action] = c.actions;
      return title && title.type === 'TextBlock' && title.text === 'Connect to OpenV' &&
        explanation && explanation.type === 'TextBlock' &&
        typeof explanation.text === 'string' && explanation.text.length <= 500 &&
        input && input.type === 'Input.Text' && input.id === 'join_code' &&
        input.maxLength === 43 && input.isMultiline !== true &&
        action && action.type === 'Action.Submit';
    } catch (_) { return false; }
  }
  function create({ show, hide, dispatch, schedule, cancel, now, onExpire }) {
    if (![show, hide, dispatch, schedule, cancel, now, onExpire].every(fn => typeof fn === 'function'))
      throw new TypeError('Invalid OpenV admission coordinator');
    let pending = null;
    function clock() {
      try {
        const value = now();
        return Number.isFinite(value) && value >= 0 ? value : NaN;
      } catch (_) { return NaN; }
    }
    function clear(request) {
      // A canceled timer can already be queued by CEF; fence its callback.
      request.epoch += 1;
      if (request.timer !== null) {
        try { cancel(request.timer); } catch (_) { /* disposed */ }
        request.timer = null;
      }
    }
    function dismiss() {
      if (!pending) return false;
      const previous = pending;
      pending = null;
      clear(previous);
      hide();
      return true;
    }
    function expire(request) {
      if (pending !== request) return false;
      dismiss();
      try { onExpire(request.nonce); } catch (_) { /* native closure unconfirmed */ }
      return true;
    }
    function arm(request, delay) {
      clear(request);
      const epoch = request.epoch;
      try {
        const timer = schedule(() => {
          if (pending !== request || request.epoch !== epoch) return;
          const current = clock();
          // Timer delivery is not an authority clock. A premature callback
          // must not shorten the original native admission deadline.
          if (!Number.isFinite(current) || current < request.started ||
              current >= request.expiresAt) {
            expire(request);
          } else if (!arm(request, Math.ceil(request.expiresAt - current))) {
            expire(request); // No reliable watchdog: fail closed.
          }
        }, delay);
        if (timer === false || timer == null) throw new Error('timer unavailable');
        if (pending !== request || request.epoch !== epoch) {
          try { cancel(timer); } catch (_) { /* already delivered */ }
          return false;
        }
        request.timer = timer;
        return true;
      } catch (_) { return false; }
    }
    function present(nonce, card, remainingMs = SUBMISSION_MS) {
      if (typeof nonce !== 'string' || !NONCE_PATTERN.test(nonce) ||
          !supported(card) || !Number.isInteger(remainingMs) ||
          remainingMs < 1 || remainingMs > SUBMISSION_MS) return false;
      const started = clock();
      if (!Number.isFinite(started) ||
          !Number.isFinite(started + remainingMs)) return false;
      if (pending) {
        // Cfx may replay the same card during CEF recovery. Accept the
        // identical card without redisplaying it or extending its deadline.
        // A shorter native remaining lifetime tightens the local deadline.
        if (pending.nonce !== nonce || pending.card !== card) return false;
        if (started < pending.started || started >= pending.expiresAt) {
          expire(pending);
          return false;
        }
        const deadline = Math.min(pending.expiresAt, started + remainingMs);
        if (deadline < pending.expiresAt) {
          pending.expiresAt = deadline;
          if (!arm(pending, Math.ceil(deadline - started))) {
            expire(pending);
            return false;
          }
        }
        return true;
      }
      const request = { nonce, card, started, expiresAt: started + remainingMs,
        timer: null, epoch: 0 };
      pending = request;
      if (!arm(request, remainingMs)) {
        expire(request);
        return false;
      }
      try { show(); } catch (_) { expire(request); return false; }
      return true;
    }
    function submit(code) {
      if (!pending) return { ok: false, reason: 'inactive' };
      const request = pending;
      const current = clock();
      if (!Number.isFinite(current) || current < request.started) {
        expire(request);
        return { ok: false, reason: 'clock' };
      }
      if (current >= request.expiresAt) {
        expire(request);
        return { ok: false, reason: 'expired' };
      }
      const normalized = typeof code === 'string' ? code.trim() : '';
      if (!CODE_PATTERN.test(normalized)) return { ok: false, reason: 'invalid' };
      let sent = false;
      try { sent = dispatch(request.nonce, normalized) === true; }
      catch (_) { /* native unavailable */ }
      // Native dispatch can synchronously reject, expire, or replace a card.
      // Never dismiss the replacement or report a stale request as current.
      if (pending !== request) return { ok: sent, reason: sent ? undefined : 'stale' };
      if (!sent) return { ok: false, reason: 'dispatch' };
      dismiss();
      return { ok: true };
    }
    return Object.freeze({
      present, submit, dismiss, active: () => pending !== null,
      owns: nonce => pending !== null && pending.nonce === nonce,
    });
  }
  window.OpenVAdmission = Object.freeze({ create, supported, MAX_CARD_BYTES, SUBMISSION_MS });
})();

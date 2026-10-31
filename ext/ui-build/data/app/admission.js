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
    function dismiss() {
      if (!pending) return false;
      const previous = pending;
      pending = null;
      if (previous.timer !== null) {
        try { cancel(previous.timer); } catch (_) { /* disposed */ }
      }
      hide();
      return true;
    }
    function expire(request) {
      if (pending !== request) return false;
      dismiss();
      try { onExpire(request.nonce); } catch (_) { /* native closure unconfirmed */ }
      return true;
    }
    function present(nonce, card, remainingMs = SUBMISSION_MS) {
      if (pending || typeof nonce !== 'string' || !NONCE_PATTERN.test(nonce) ||
          !supported(card) || !Number.isInteger(remainingMs) ||
          remainingMs < 1 || remainingMs > SUBMISSION_MS) return false;
      let started;
      try { started = now(); } catch (_) { return false; }
      if (!Number.isFinite(started) || started < 0 ||
          !Number.isFinite(started + remainingMs)) return false;
      const request = { nonce, started, expiresAt: started + remainingMs, timer: null };
      pending = request;
      try {
        const timer = schedule(() => expire(request), remainingMs);
        if (timer === false || timer == null) throw new Error('timer unavailable');
        request.timer = timer;
        show();
      } catch (_) { dismiss(); return false; }
      return true;
    }
    function submit(code) {
      if (!pending) return { ok: false, reason: 'inactive' };
      let current;
      try { current = now(); } catch (_) { current = NaN; }
      if (!Number.isFinite(current) || current < pending.started) {
        expire(pending);
        return { ok: false, reason: 'clock' };
      }
      if (current >= pending.expiresAt) {
        expire(pending);
        return { ok: false, reason: 'expired' };
      }
      const normalized = typeof code === 'string' ? code.trim() : '';
      if (!CODE_PATTERN.test(normalized)) return { ok: false, reason: 'invalid' };
      let sent = false;
      try { sent = dispatch(pending.nonce, normalized) === true; } catch (_) { /* native unavailable */ }
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

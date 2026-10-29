/* OpenV one-time FXServer admission. Never render untrusted Adaptive Card markup. */
(() => {
  'use strict';
  const MAX_CARD_BYTES = 4096;
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
  function create({ show, hide, dispatch }) {
    if (![show, hide, dispatch].every(fn => typeof fn === 'function'))
      throw new TypeError('Invalid OpenV admission coordinator');
    let pending = null;
    function dismiss() {
      if (!pending) return false;
      pending = null;
      hide();
      return true;
    }
    function present(nonce, card) {
      if (pending || typeof nonce !== 'string' || !NONCE_PATTERN.test(nonce) ||
          !supported(card)) return false;
      pending = nonce;
      try { show(); } catch (_) { pending = null; return false; }
      return true;
    }
    function submit(code) {
      if (!pending) return { ok: false, reason: 'inactive' };
      const normalized = typeof code === 'string' ? code.trim() : '';
      if (!CODE_PATTERN.test(normalized)) return { ok: false, reason: 'invalid' };
      let sent = false;
      try { sent = dispatch(pending, normalized) === true; } catch (_) { /* native unavailable */ }
      if (!sent) return { ok: false, reason: 'dispatch' };
      dismiss();
      return { ok: true };
    }
    return Object.freeze({
      present, submit, dismiss, active: () => pending !== null,
      owns: nonce => pending !== null && pending === nonce,
    });
  }
  window.OpenVAdmission = Object.freeze({ create, supported, MAX_CARD_BYTES });
})();

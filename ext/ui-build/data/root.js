/* OpenV's independently authored NUI root frame manager.
 * Native host contracts: registerPushFunction, registerFrameFunction,
 * registerPollFunction. This file does not emulate or bypass a game client.
 */
(() => {
  'use strict';

  const frames = Object.create(null);
  const escapeListeners = Object.create(null);
  // Cfx may dispatch native frameCall/poll synchronously after createFrame,
  // before navigation and the child's message listener have finished loading.
  // Keep a bounded, per-iframe startup queue; never replay it into a replacement.
  const deliveryState = new WeakMap();
  const MAX_PENDING_EVENTS = 64;
  const MAX_PENDING_BYTES = 512 * 1024;
  const zStack = [];
  const focusStack = [];
  let handover = {};
  let serverAddress = '';
  window.citFrames = frames;

  function validName(value) {
    return typeof value === 'string' && value.length > 0 && value.length <= 128 &&
      /^[a-zA-Z0-9_.:-]+$/.test(value);
  }

  function allowedFrameUrl(value) {
    if (typeof value !== 'string' || value.length > 2048 || !value) return false;
    try {
      const parsed = new URL(value);
      if (parsed.username || parsed.password) return false;
      if (parsed.protocol === 'nui:' || parsed.protocol === 'https:') return Boolean(parsed.hostname);
      return parsed.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname);
    } catch (_) {
      return false;
    }
  }

  function parseNativeJson(raw) {
    if (typeof raw !== 'string' || raw.length > 1024 * 1024) return null;
    try {
      const value = JSON.parse(raw);
      return value !== null && typeof value === 'object' && !Array.isArray(value) ? value : null;
    } catch (_) {
      return null;
    }
  }

  function targetOrigin(frame) {
    try {
      const parsed = new URL(frame.src);
      // URL.origin serializes custom schemes as 'null' in stock Chromium, but
      // OpenV's actual CEF registers nui: as a STANDARD, secure scheme. Use
      // its explicit origin instead of broadcasting native data with '*'.
      if (parsed.protocol === 'nui:') return `nui://${parsed.host}`;
      return parsed.origin !== 'null' ? parsed.origin : '*'; // srcdoc-only browser fixtures
    } catch (_) {
      return '*';
    }
  }

  function postToFrame(frame, payload) {
    try {
      frame.contentWindow?.postMessage(payload, targetOrigin(frame));
    } catch (_) {
      // A frame may be destroyed or navigating while a native event arrives.
    }
  }

  function send(frameName, payload, encodedSize) {
    if (!validName(frameName) || !Object.hasOwn(frames, frameName)) return;
    const frame = frames[frameName];
    const state = deliveryState.get(frame);
    if (!state) return;
    if (state.ready) {
      postToFrame(frame, payload);
      return;
    }
    // Count UTF-16 units conservatively. A native frameCall is already capped
    // at 1 MiB; never keep an unbounded set of pending native payloads.
    const size = encodedSize ?? JSON.stringify(payload).length;
    if (size > MAX_PENDING_BYTES) {
      state.overflow = true;
      return;
    }
    while (state.queue.length &&
           (state.queue.length >= MAX_PENDING_EVENTS || state.bytes + size > MAX_PENDING_BYTES)) {
      state.bytes -= state.queue.shift().size;
      state.overflow = true;
    }
    state.queue.push({ payload, size });
    state.bytes += size;
  }

  function finishFrameLoad(name, frame) {
    if (frames[name] !== frame) return;
    const state = deliveryState.get(frame);
    if (!state || state.ready) return;
    state.ready = true;
    frame.style.visibility = 'visible';
    for (const event of state.queue) postToFrame(frame, event.payload);
    state.queue.length = 0;
    state.bytes = 0;
    if (state.overflow) {
      // A child can re-query the native server/favorites snapshot. Never
      // pretend an incomplete sequence of startup events is authoritative.
      postToFrame(frame, { type: 'openvStartupOverflow' });
    }
    if (name === 'loadingScreen') deliverHandover();
    if (focusStack[0] === name) {
      // Navigation replaces the child's Window; rebind the blur handler to
      // the loaded document instead of retaining the initial about:blank one.
      detachEscape(name);
      focusFrame(name);
    }
  }

  function deliverHandover() {
    if (!Object.hasOwn(frames, 'loadingScreen')) return;
    const frame = frames.loadingScreen;
    if (!deliveryState.get(frame)?.ready) return;
    const data = { ...handover, serverAddress };
    try { safeWindow(frame).nuiHandoverData = data; } catch (_) {}
    send('loadingScreen', { eventName: 'openvHandover', data });
  }

  function restack() {
    zStack.forEach((name, index) => {
      if (Object.hasOwn(frames, name)) frames[name].style.zIndex = String(index);
    });
    if (focusStack.length && Object.hasOwn(frames, focusStack[0])) {
      frames[focusStack[0]].style.zIndex = '99999';
    }
  }

  function removeName(stack, name) {
    const index = stack.indexOf(name);
    if (index !== -1) stack.splice(index, 1);
  }

  function safeWindow(frame) {
    try { return frame.contentWindow; } catch (_) { return null; }
  }

  function detachEscape(name) {
    const frame = frames[name];
    const callback = escapeListeners[name];
    if (frame && callback) {
      try { safeWindow(frame)?.removeEventListener('blur', callback); } catch (_) {}
    }
    delete escapeListeners[name];
  }

  function focusFrame(name) {
    if (!validName(name) || !Object.hasOwn(frames, name)) return;
    const previous = focusStack[0];
    if (previous && previous !== name) detachEscape(previous);
    removeName(zStack, name);
    zStack.push(name);
    removeName(focusStack, name);
    focusStack.unshift(name);
    restack();
    const frame = frames[name];
    const child = safeWindow(frame);
    if (!child) return;
    if (!escapeListeners[name]) {
      const callback = () => {
        window.setTimeout(() => {
          if (Object.hasOwn(frames, name) && focusStack[0] === name &&
              document.activeElement === document.body) {
            try { safeWindow(frames[name])?.focus(); } catch (_) {}
          }
        }, 32);
      };
      escapeListeners[name] = callback;
      try { child.addEventListener('blur', callback); } catch (_) {}
    }
    try { child.focus(); } catch (_) {}
  }

  function blurFrame(name) {
    if (!validName(name) || !Object.hasOwn(frames, name)) return;
    const wasTop = focusStack[0] === name;
    detachEscape(name);
    removeName(focusStack, name);
    try { safeWindow(frames[name])?.blur(); } catch (_) {}
    restack();
    if (wasTop && focusStack.length) focusFrame(focusStack[0]);
  }

  function destroyFrame(name) {
    if (!validName(name) || !Object.hasOwn(frames, name)) return;
    const wasTop = focusStack[0] === name;
    detachEscape(name);
    removeName(zStack, name);
    removeName(focusStack, name);
    const frame = frames[name];
    delete frames[name];
    frame.remove();
    restack();
    if (wasTop && focusStack.length) focusFrame(focusStack[0]);
  }

  function createFrame(name, url) {
    if (!validName(name) || !allowedFrameUrl(url)) return;
    // Replacing a native frame must not leave a stale focus or event listener.
    if (Object.hasOwn(frames, name)) destroyFrame(name);
    const frame = document.createElement('iframe');
    frame.className = 'openv-frame';
    frame.name = name;
    frame.tabIndex = -1;
    frame.style.visibility = 'hidden';
    frame.setAttribute('allow', 'microphone *; camera *');
    // Set the navigation before attachment: appending a blank iframe first can
    // fire an about:blank load and flush native events before child JS exists.
    frame.src = url;
    frame.addEventListener('load', () => finishFrameLoad(name, frame));
    deliveryState.set(frame, { ready: false, queue: [], bytes: 0, overflow: false });
    frames[name] = frame;
    zStack.push(name);
    document.body.appendChild(frame);
    try {
      const child = safeWindow(frame);
      if (child) {
        child.GetParentResourceName = () => name;
      }
    } catch (_) {
      // Cross-origin NUI pages cannot receive JS properties directly.
    }
    restack();
  }

  function nativePush(type, ...args) {
    if (type === 'frameCall') {
      const [name, raw] = args;
      const payload = parseNativeJson(raw);
      if (payload) send(name, payload, raw.length);
    } else if (type === 'rootCall') {
      const payload = parseNativeJson(args[0]);
      if (!payload) return;
      const name = payload.frameName;
      switch (payload.type) {
        case 'focusFrame': focusFrame(name); break;
        case 'blurFrame': blurFrame(name); break;
        case 'setHandover':
          if (payload.data && typeof payload.data === 'object' && !Array.isArray(payload.data)) {
            handover = { ...payload.data };
            deliverHandover();
          }
          break;
        case 'setServerAddress':
          if (typeof payload.data === 'string' && payload.data.length <= 2048) {
            serverAddress = payload.data;
            deliverHandover();
          }
          break;
        case 'setZIndex':
          if (validName(name) && Object.hasOwn(frames, name) &&
              Number.isSafeInteger(payload.zIndex) && payload.zIndex >= -1000 && payload.zIndex <= 100000) {
            frames[name].style.zIndex = String(payload.zIndex);
          }
          break;
        default: break;
      }
    }
  }

  window.focusFrame = focusFrame;
  window.blurFrame = blurFrame;
  if (typeof window.registerPushFunction === 'function') window.registerPushFunction(nativePush);
  if (typeof window.registerFrameFunction === 'function') {
    window.registerFrameFunction((message, name, url) => {
      if (message === 'createFrame') createFrame(name, url);
      else if (message === 'destroyFrame') destroyFrame(name);
    });
  }
  if (typeof window.registerPollFunction === 'function') {
    window.registerPollFunction((name) => send(name, { type: 'poll' }));
  }
})();

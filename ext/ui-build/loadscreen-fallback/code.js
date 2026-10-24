/* First-party offline loadscreen for source-only builds without upstream webpack assets. */
(() => {
  'use strict';
  const status = document.getElementById('status');
  const fill = document.getElementById('progress-fill');
  const bar = document.querySelector('[role="progressbar"]');
  const percent = document.getElementById('percent');
  let current = 0;
  const setProgress = (value, fraction = false) => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0 ||
        (fraction && value > 1) || (!fraction && value > 100)) return;
    current = Math.max(current, Math.round(value * (fraction ? 100 : 1)));
    fill.style.width = `${current}%`;
    bar.setAttribute('aria-valuenow', String(current));
    percent.textContent = `${current}%`;
  };
  const setStatus = (value) => {
    if (typeof value === 'string' && value.length && value.length <= 512) status.textContent = value;
  };
  window.addEventListener('message', (event) => {
    if (event.source !== window.parent && event.source !== window) return;
    if (event.source === window.parent && event.origin !== 'nui://game' && event.origin !== location.origin) return;
    const data = event.data;
    if (!data || typeof data !== 'object' || Array.isArray(data)) return;
    switch (data.eventName || data.type) {
      case 'loadProgress':
        if (data.loadFraction !== undefined) setProgress(data.loadFraction, true);
        else setProgress(data.progress);
        break;
      case 'startInitFunction': setStatus(`Initializing ${String(data.type || data.name || 'game resources').slice(0, 100)}…`); break;
      case 'startDataFileEntries': setStatus('Loading game data…'); break;
      case 'performMapLoadFunction': setStatus('Preparing the world…'); break;
      case 'onLogLine': if (typeof data.message === 'string') setStatus(data.message); break;
      case 'openvHandover':
        if (data.data && typeof data.data.serverAddress === 'string' &&
            data.data.serverAddress.length > 0 && data.data.serverAddress.length <= 255) {
          setStatus(`Connecting to ${data.data.serverAddress}…`);
        }
        break;
      case 'shutdownLoadingScreen': setProgress(100); setStatus('Ready'); break;
      default: break;
    }
  });
})();

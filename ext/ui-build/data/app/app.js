/* OpenV first-party client UI. No remote scripts, network fetches, or entitlement shortcuts. */
(() => {
  'use strict';

  const nativeAvailable = typeof window.invokeNative === 'function';
  const STORAGE_RECENT = 'openv.recent.v1';
  const STORAGE_CONFIRM_EXIT = 'openv.confirmExit.v1';
  const MAX_RECENT = 8;
  const MAX_FAVORITES = 100;
  const MAX_SERVERS = 250;
  const nativeServers = new Map();
  let favorites = [];
  let recents = [];
  let confirmExit = true;
  let toastTimer;
  const connection = window.OpenVConnectionCoordinator.create({
    crypto: window.crypto,
    schedule: (callback, ms) => window.setTimeout(callback, ms),
    cancel: timer => window.clearTimeout(timer),
    onChange: updateConnectionState,
  });

  function updateConnectionState({ phase, address, pending }) {
    const status = document.getElementById('connection-state');
    if (!status) return;
    const messages = {
      idle: 'No active connection request.',
      requested: `Native connection requested for ${address}. Waiting for server response.`,
      connecting: `Connecting to ${address}. Game ownership and multiplayer are not yet verified.`,
      failed: 'The native client reported a connection failure. You may retry.',
      timeout: 'No final native response received. The previous request may still be running.',
      dispatch_failed: 'The native client could not accept the connection request.',
      disposed: 'Connection UI was closed.',
    };
    status.textContent = messages[phase] || messages.idle;
    const submit = document.querySelector('#connect-form button[type="submit"]');
    if (submit) submit.disabled = pending;
    // Rebuild native server cards so all join actions share the same pending gate.
    renderAll();
  }

  function parseEndpoint(value) {
    if (typeof value !== 'string' || value.length > 255) return null;
    const raw = value.trim();
    if (!raw || /[\s\x00-\x1f\x7f\\/?#@'"<>;]/.test(raw)) return null;
    let host;
    let port = 30120;
    const ipv6 = raw.match(/^\[([0-9a-fA-F:.]+)\](?::([0-9]{1,5}))?$/);
    if (ipv6) {
      if (!ipv6[1].includes(':')) return null;
      try { new URL('http://[' + ipv6[1] + ']/'); } catch { return null; }
      host = '[' + ipv6[1].toLowerCase() + ']';
      if (ipv6[2]) port = Number(ipv6[2]);
    } else {
      const match = raw.match(/^([a-zA-Z0-9_.-]+)(?::([0-9]{1,5}))?$/);
      if (!match) return null;
      host = match[1].toLowerCase();
      if (host.length > 253 || host.startsWith('.') || host.endsWith('.') || host.includes('..')) return null;
      if (host.split('.').some(part => !part || part.length > 63 || part.startsWith('-') || part.endsWith('-'))) return null;
      if (/^[0-9.]+$/.test(host) && (host.split('.').length !== 4 || host.split('.').some(part => Number(part) > 255))) return null;
      if (match[2]) port = Number(match[2]);
    }
    if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
    return `${host}:${port}`;
  }

  function readStored(key, fallback) {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : JSON.parse(value);
    } catch { return fallback; }
  }

  function writeStored(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private CEF storage may be disabled */ }
  }

  function normalizeAddresses(input, max) {
    if (!Array.isArray(input)) return [];
    const result = [];
    const seen = new Set();
    for (const item of input.slice(0, max * 3)) {
      const raw = typeof item === 'string' ? item : item && typeof item.address === 'string' ? item.address : '';
      const address = parseEndpoint(raw);
      if (!address || seen.has(address)) continue;
      seen.add(address);
      result.push(address);
      if (result.length >= max) break;
    }
    return result;
  }

  function invoke(action, argument = '') {
    if (!nativeAvailable) {
      toast('OpenV native client is not available in this browser preview.');
      return false;
    }
    try { window.invokeNative(action, argument); return true; }
    catch { toast('The game client could not complete that request.'); return false; }
  }

  function toast(message) {
    const element = document.getElementById('toast');
    element.textContent = String(message).slice(0, 350);
    element.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { element.hidden = true; }, 6000);
  }

  function switchView(view) {
    if (!['home', 'servers', 'favorites', 'settings'].includes(view)) return;
    for (const element of document.querySelectorAll('[data-page]')) element.hidden = element.dataset.page !== view;
    for (const element of document.querySelectorAll('.nav-link')) {
      const active = element.dataset.view === view;
      element.classList.toggle('active', active);
      if (active) element.setAttribute('aria-current', 'page');
      else element.removeAttribute('aria-current');
    }
    document.getElementById('breadcrumb').textContent = view[0].toUpperCase() + view.slice(1);
    if (view === 'favorites') renderFavorites();
    if (view === 'servers') renderServers();
  }

  function addRecent(address) {
    recents = [address, ...recents.filter(x => x !== address)].slice(0, MAX_RECENT);
    writeStored(STORAGE_RECENT, recents);
    renderRecents();
  }

  function connect(address) {
    const parsed = parseEndpoint(address);
    if (!parsed) { toast('Enter a valid server hostname or IP address and port.'); return false; }
    if (nativeServers.get(parsed)?.discoveryOnly) {
      toast('This OpenV gateway supports discovery only. GTA V gameplay is not available on this endpoint.');
      return false;
    }
    if (!nativeAvailable) {
      toast('OpenV native client is not available in this browser preview.');
      return false;
    }
    const result = connection.start(parsed, (endpoint, nonce) =>
      invoke('connectTo', JSON.stringify([endpoint, nonce])));
    if (!result.ok) {
      const errors = {
        busy: 'A native connection request is already pending. Wait for its result.',
        crypto: 'Secure connection initialization is unavailable. Restart OpenV and try again.',
        timer: 'The client cannot monitor this connection request. Restart OpenV.',
        dispatch: 'The native client could not accept the connection request.',
      };
      toast(errors[result.reason] || 'Unable to request this connection.');
      return false;
    }
    addRecent(parsed);
    toast(`Connection requested for ${parsed}. Waiting for the game client.`);
    return true;
  }

  function setFavorite(address, add) {
    const parsed = parseEndpoint(address);
    if (!parsed) return;
    if (add) favorites = [parsed, ...favorites.filter(x => x !== parsed)].slice(0, MAX_FAVORITES);
    else favorites = favorites.filter(x => x !== parsed);
    if (nativeAvailable) invoke('saveFavorites', JSON.stringify(favorites));
    else writeStored('openv.previewFavorites.v1', favorites);
    renderAll();
  }

  function makeCard(address, info) {
    const card = document.createElement('article');
    card.className = 'server-card';
    const top = document.createElement('div'); top.className = 'server-card-top';
    const name = document.createElement('div'); name.className = 'server-name';
    name.textContent = info && typeof info.name === 'string' && info.name.trim() ? info.name.slice(0, 140) : 'OpenV server';
    top.append(name);
    const endpoint = document.createElement('div'); endpoint.className = 'server-address'; endpoint.textContent = address;
    const meta = document.createElement('div'); meta.className = 'server-meta';
    const count = info && Number.isInteger(info.clients) && Number.isInteger(info.maxclients) && info.clients >= 0 && info.maxclients >= 0 ? `${info.clients}/${info.maxclients} players` : 'Direct connection';
    meta.textContent = info?.discoveryOnly ? `${count.replace(' players', ' admitted sessions')} · Discovery only — gameplay unavailable` : count;
    const actions = document.createElement('div'); actions.className = 'server-actions';
    const join = document.createElement('button'); join.className = 'primary'; join.type = 'button'; join.textContent = 'Connect →';
    if (info?.discoveryOnly) {
      join.disabled = true;
      join.textContent = 'Not playable yet';
      join.title = 'The OpenV gateway is not connected to a GTA V gameplay transport';
    } else {
      join.disabled = connection.active();
      join.addEventListener('click', () => connect(address));
    }
    const favorite = document.createElement('button'); favorite.className = 'star'; favorite.type = 'button';
    const selected = favorites.includes(address);
    favorite.textContent = selected ? '★' : '☆';
    favorite.setAttribute('aria-pressed', String(selected));
    favorite.setAttribute('aria-label', selected ? `Remove ${address} from favorites` : `Save ${address} to favorites`);
    favorite.addEventListener('click', () => setFavorite(address, !selected));
    actions.append(join, favorite);
    card.append(top, endpoint, meta, actions);
    return card;
  }

  function renderList(id, addresses, emptyMessage) {
    const target = document.getElementById(id);
    target.replaceChildren();
    if (!addresses.length) {
      const empty = document.createElement('div'); empty.className = 'empty'; empty.textContent = emptyMessage;
      target.append(empty); return;
    }
    const fragment = document.createDocumentFragment();
    for (const address of addresses) fragment.append(makeCard(address, nativeServers.get(address)));
    target.append(fragment);
  }

  function renderRecents() { renderList('recent-list', recents.slice(0, 4), 'No recent servers yet. Enter a server address above to get started.'); }
  function renderFavorites() { renderList('favorites-list', favorites, 'No favorites yet. Save a server using the star on its card.'); }
  function renderServers() { renderList('server-list', [...nativeServers.keys()], 'No servers discovered yet. Query a known server address above.'); }
  function renderAll() { renderRecents(); renderFavorites(); renderServers(); }

  function isTrustedNativeOrigin(origin, ownOrigin, protocol) {
    // about:srcdoc is only used by the isolated Chromium test/preview fixture.
    // Never treat an opaque origin as trusted in the real HTTPS NUI runtime.
    return origin === 'nui://game' ||
      (origin === ownOrigin && (origin !== 'null' || protocol === 'about:'));
  }

  function onNativeMessage(event) {
    // Cfx root.html dispatches frameCall from nui://game/ui/root.html to
    // https://nui-game-internal/ui/app/index.html. These are DIFFERENT origins.
    // NUIApp.cpp registers `nui` as a standard, secure CEF scheme, so the
    // trusted root origin is serialized as `nui://game` (never `null`).
    // A browser preview can use the same-origin parent/self for testability.
    // Checking BOTH source identity and a narrow origin allowlist prevents
    // untrusted sibling frames or unrelated websites from forging native data.
    const source = window.parent === window ? window : window.parent;
    const trustedOrigin = isTrustedNativeOrigin(event.origin, window.location.origin, window.location.protocol);
    if (event.source !== source || !trustedOrigin ||
        !event.data || typeof event.data !== 'object' || Array.isArray(event.data)) return;
    const message = event.data;
    switch (message.type) {
      case 'openvStartupOverflow':
        // The native root bounds messages queued before this frame loads.
        // Recover state from native rather than trusting a partial startup
        // discovery/favorites sequence. The root sends this at most once per
        // navigation; normal live messages do not trigger these queries.
        if (nativeAvailable) {
          invoke('getFavorites');
          invoke('refreshServers');
          toast('Some early server updates were missed; refreshing discovery…');
        }
        break;
      case 'getFavorites':
        favorites = normalizeAddresses(message.list, MAX_FAVORITES);
        renderAll(); break;
      case 'serverAdd':
      case 'serverQueried': {
        const address = parseEndpoint(message.addr || message.queryCorrelation || '');
        if (!address) return;
        if (!nativeServers.has(address) && nativeServers.size >= MAX_SERVERS) nativeServers.delete(nativeServers.keys().next().value);
        const previouslyDiscoveryOnly = nativeServers.get(address)?.discoveryOnly === true;
        nativeServers.set(address, {
          name: typeof message.name === 'string' ? message.name : '',
          clients: Number(message.clients),
          maxclients: Number(message.maxclients),
          discoveryOnly: previouslyDiscoveryOnly || (message.infoBlob && typeof message.infoBlob === 'object' &&
            !Array.isArray(message.infoBlob) && message.infoBlob.vars &&
            message.infoBlob.vars.openv_discovery_only === 'true')
        });
        renderAll();
        if (message.type === 'serverQueried') { switchView('servers'); toast(`Server responded: ${address}`); }
        break;
      }
      case 'connectTo':
        if (typeof message.hostnameStr === 'string') connect(message.hostnameStr);
        break;
      case 'backfillServerInfo':
        // The inherited native connector waits for this callback to finish admission.
        // Do not display or persist server-provided entitlement material.
        invoke('backfillDone');
        break;
      case 'connectCard':
        invoke('cancelDefer');
        toast('This server requested an unsupported interactive connection card; connection canceled.');
        break;
      case 'setWarningMessage':
        if (typeof message.message === 'string') toast(message.message);
        break;
      case 'queryingFailed':
        toast('The server did not respond to the query. Check its address and availability.'); break;
      case 'connectStatus':
        connection.progress();
        if (message.data && typeof message.data.message === 'string') toast(message.data.message);
        break;
      case 'connectFailed':
        connection.failed();
        if (typeof message.message === 'string') toast(`Connection failed: ${message.message}`);
        break;
      case 'connecting':
        connection.progress();
        toast('Connecting to server…');
        break;
      case 'connectionStatus':
        connection.progress();
        if (typeof message.message === 'string') toast(message.message);
        break;
      default: break;
    }
  }

  function init() {
    recents = normalizeAddresses(readStored(STORAGE_RECENT, []), MAX_RECENT);
    favorites = nativeAvailable ? [] : normalizeAddresses(readStored('openv.previewFavorites.v1', []), MAX_FAVORITES);
    confirmExit = readStored(STORAGE_CONFIRM_EXIT, true) !== false;
    const toggle = document.getElementById('confirm-exit'); toggle.checked = confirmExit;
    toggle.addEventListener('change', () => { confirmExit = toggle.checked; writeStored(STORAGE_CONFIRM_EXIT, confirmExit); });
    document.getElementById('native-status').textContent = nativeAvailable ? 'Game client bridge available' : 'Browser preview · game bridge unavailable';
    if (nativeAvailable) document.getElementById('native-dot').classList.add('ready');
    document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));
    document.getElementById('browse').addEventListener('click', () => switchView('servers'));
    document.getElementById('connect-form').addEventListener('submit', event => { event.preventDefault(); connect(document.getElementById('server-address').value); });
    document.getElementById('query-form').addEventListener('submit', event => {
      event.preventDefault();
      const address = parseEndpoint(document.getElementById('query-address').value);
      if (!address) { toast('Enter a valid server address to query.'); return; }
      if (invoke('queryServer', address)) toast(`Querying ${address}…`);
    });
    document.getElementById('refresh').addEventListener('click', () => { if (invoke('refreshServers')) toast('Refreshing server discovery…'); });
    document.getElementById('add-favorite').addEventListener('click', () => { switchView('home'); document.getElementById('server-address').focus(); toast('Connect to a server, then select its star to save it.'); });
    document.getElementById('clear-recents').addEventListener('click', () => { recents = []; writeStored(STORAGE_RECENT, []); renderRecents(); toast('Recent server history cleared.'); });
    const dialog = document.getElementById('confirm-dialog');
    document.getElementById('quit').addEventListener('click', () => { if (confirmExit) dialog.showModal(); else invoke('quit'); });
    dialog.addEventListener('close', () => { if (dialog.returnValue === 'exit') invoke('quit'); });
    window.addEventListener('message', onNativeMessage);
    window.addEventListener('pagehide', () => connection.dispose(), { once: true });
    // Cfx queues native messages until its UI registers a listener. Flush them.
    if (typeof window.nuiInternalCallMessages === 'function') window.nuiInternalCallMessages();
    window.nuiInternalHandledMessages = true;
    renderAll();
    updateConnectionState({ phase: 'idle', address: '', pending: false });
    if (nativeAvailable) {
      invoke('getMinModeInfo'); // Required by the inherited Cfx NUI startup lifecycle.
      invoke('getFavorites');
    }
  }

  window.OpenVUI = Object.freeze({ parseEndpoint, normalizeAddresses, isTrustedNativeOrigin });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
  else init();
})();

const net = require('node:net');

function isLoopbackHost(host) {
  if (typeof host !== 'string') return false;
  const value = host.toLowerCase().replace(/^\[|\]$/g, '');
  if (value === 'localhost' || value === '::1') return true;
  return net.isIP(value) === 4 && value.startsWith('127.');
}

// Install before application modules create sockets. Chromium requests are
// blocked separately by installSessionBoundary. This is a defense in depth,
// not an OS firewall for child processes or native libraries.
function installNodeBoundary() {
  const original = net.Socket.prototype.connect;
  if (original.__localOnlyBoundary) return;
  function connect(...args) {
    const first = args[0];
    const options = Array.isArray(first) ? first[0] : first;
    if (typeof options === 'string' && !/^\d+$/.test(options)) return original.apply(this, args);
    const host = typeof options === 'object' && options !== null
      ? (options.path ? null : options.host || 'localhost')
      : (typeof args[1] === 'string' ? args[1] : 'localhost');
    if (host !== null && !isLoopbackHost(host)) {
      const error = new Error('Network access is disabled in local-only dictation');
      error.code = 'LOCAL_ONLY_NETWORK_BLOCKED';
      throw error;
    }
    return original.apply(this, args);
  }
  connect.__localOnlyBoundary = true;
  net.Socket.prototype.connect = connect;
}

function installSessionBoundary(session) {
  session.webRequest.onBeforeRequest((details, callback) => {
    try {
      const url = new URL(details.url);
      const networkProtocol = ['http:', 'https:', 'ws:', 'wss:', 'ftp:'].includes(url.protocol);
      callback({ cancel: networkProtocol && !isLoopbackHost(url.hostname) });
    } catch {
      callback({ cancel: true });
    }
  });
}
module.exports = { isLoopbackHost, installNodeBoundary, installSessionBoundary };

const test = require('node:test');
const assert = require('node:assert/strict');
const { isLoopbackHost } = require('../../src/helpers/localNetworkBoundary');
test('only permits explicit loopback addresses and localhost', () => {
  for (const host of ['localhost','127.0.0.1','127.12.3.4','::1','[::1]']) assert.equal(isLoopbackHost(host), true, host);
  for (const host of ['example.com','localhost.example.com','0.0.0.0','192.168.1.1','::ffff:8.8.8.8','']) assert.equal(isLoopbackHost(host), false, host);
});
test('Node socket boundary blocks remote connections and permits loopback connection attempts', () => {
  const net = require('node:net');
  const { installNodeBoundary } = require('../../src/helpers/localNetworkBoundary');
  installNodeBoundary();
  assert.throws(() => new net.Socket().connect({ host: 'example.com', port: 80 }), { code: 'LOCAL_ONLY_NETWORK_BLOCKED' });
  const socket = new net.Socket();
  socket.on('error', () => {});
  assert.doesNotThrow(() => socket.connect({ host: '127.0.0.1', port: 9 }));
  socket.destroy();
});
test('Chromium boundary blocks remote network requests and permits local and file URLs', () => {
  let listener;
  const { installSessionBoundary } = require('../../src/helpers/localNetworkBoundary');
  installSessionBoundary({ webRequest: { onBeforeRequest: fn => { listener = fn; } } });
  const check = url => { let result; listener({ url }, value => { result = value; }); return result.cancel; };
  assert.equal(check('https://example.com/model'), true);
  assert.equal(check('http://127.0.0.1:8080/v1/chat/completions'), false);
  assert.equal(check('file:///C:/app/index.html'), false);
});

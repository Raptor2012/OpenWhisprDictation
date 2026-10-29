const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '../..');
test('dictation build has independent identity and does not register an OAuth protocol', () => {
  const main = fs.readFileSync(path.join(root, 'main.js'), 'utf8');
  const config = JSON.parse(fs.readFileSync(path.join(root, 'electron-builder.json'), 'utf8'));
  assert.match(main, /OpenWhisprDictation/);
  assert.match(main, /const protocolRegistered = false/);
  assert.equal(config.appId, 'com.openwhispr.dictation');
  assert.equal(config.productName, 'OpenWhispr Dictation');
  assert.equal(config.protocols, undefined);
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
test('dictation never starts monitoring external field contents', () => {
  const source = fs.readFileSync(path.join(__dirname, '../../src/helpers/ipcHandlers.js'), 'utf8');
  assert.doesNotMatch(source, /\.startMonitoring\s*\(/);
  assert.doesNotMatch(source, /\.on\(\s*["']text-edited["']/);
});

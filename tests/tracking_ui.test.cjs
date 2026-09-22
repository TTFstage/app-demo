const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'main.js'), 'utf8');

function makeHarness(savedValues = new Map()) {
  const elements = new Map();
  const listeners = new Map();
  let nextTimer = 1;
  let nextWatch = 1;
  const domElement = (id) => {
    if (!elements.has(id)) elements.set(id, {
      hidden: true, disabled: false, textContent: '', style: {}, dataset: {},
      classList: {add() {}, remove() {}},
    });
    return elements.get(id);
  };
  const position = {coords: {latitude: 45.4642, longitude: 9.19, speed: 0, accuracy: 8}, timestamp: Date.now()};
  class HeadingEstimator {
    static async requestPermissions() { return true; }
    start() { this.isRunning = true; }
    stop() { this.isRunning = false; }
  }
  class SignalProcessor { setSamplingRate() {} process(row) { return row; } }
  class FallDetector { process(row) { return row; } }
  const context = vm.createContext({
    console, Date, URL, Math,
    localStorage: {
      getItem: (key) => savedValues.get(key) ?? null,
      setItem: (key, value) => savedValues.set(key, value),
      removeItem: (key) => savedValues.delete(key),
    },
    document: {
      body: {classList: {add() {}, remove() {}}},
      getElementById: domElement,
      querySelector: () => null,
      addEventListener: (event, callback) => listeners.set(`document:${event}`, callback),
    },
    navigator: {
      onLine: false,
      geolocation: {
        getCurrentPosition: (success) => success(position),
        watchPosition: () => nextWatch++,
        clearWatch() {},
      },
    },
    window: {
      RIDER_ID: 42,
      ROR_SETTINGS: {telemetryEnabled: true, fallDetectionEnabled: true, highAccuracyGps: true},
      ROR_RIDE_COPY: {ready: 'Ready', live: 'Live', paused: 'Paused', liveStatus: 'Recording', pausedStatus: 'Paused', recover: 'Recovered', queuedStatus: 'Queued', online: 'Online', offline: 'Offline'},
      crypto: {randomUUID: () => '6e174add-8964-45bd-9400-3ee4d970b6df'},
      location: {href: 'http://localhost/'},
      history: {replaceState() {}},
      addEventListener: (event, callback) => listeners.set(`window:${event}`, callback),
      removeEventListener() {},
    },
    HeadingEstimator, SignalProcessor, FallDetector,
    setInterval: () => nextTimer++, clearInterval() {},
    setTimeout: () => nextTimer++, clearTimeout() {},
  });
  vm.runInContext(source, context);
  return {context, elements, listeners, savedValues};
}

test('pause, reload and resume keep the same session without closing it', async () => {
  const initial = makeHarness();
  await initial.context.startTracking();
  const sessionId = vm.runInContext('sessionId', initial.context);
  assert.equal(vm.runInContext('isTracking', initial.context), true);
  initial.listeners.get('window:pagehide')();
  assert.equal(JSON.parse(initial.savedValues.get('ror.telemetry.sessionEnds.v1.user-42')).length, 0);

  const restored = makeHarness(initial.savedValues);
  restored.listeners.get('document:DOMContentLoaded')();
  assert.equal(vm.runInContext('sessionId', restored.context), sessionId);
  assert.equal(vm.runInContext('isPaused', restored.context), true);
  await restored.context.resumeTracking();
  assert.equal(vm.runInContext('sessionId', restored.context), sessionId);
  assert.equal(vm.runInContext('isPaused', restored.context), false);
});

test('finishing offline queues the session end before leaving the page', async () => {
  const harness = makeHarness();
  await harness.context.startTracking();
  await harness.context.stopTracking();
  assert.equal(vm.runInContext('isTracking', harness.context), false);
  assert.equal(harness.savedValues.has('ror.telemetry.active.v1.user-42'), false);
  assert.equal(JSON.parse(harness.savedValues.get('ror.telemetry.sessionEnds.v1.user-42')).length, 1);
});

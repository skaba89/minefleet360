import test from "node:test";
import assert from "node:assert/strict";
import { createExpoLocationAdapter } from "../src/expoLocationAdapter.mjs";

function harness(overrides = {}) {
  const events = [];
  let running = false;
  const location = {
    Accuracy: { Balanced: 3 },
    getForegroundPermissionsAsync: async () => ({ status: "granted" }),
    getBackgroundPermissionsAsync: async () => ({ status: "granted" }),
    hasServicesEnabledAsync: async () => true,
    hasStartedLocationUpdatesAsync: async () => running,
    startLocationUpdatesAsync: async (_name, options) => {
      events.push("start");
      assert.equal(options.foregroundService.notificationTitle, "MineFleet360 — suivi GPS actif");
      running = true;
    },
    stopLocationUpdatesAsync: async () => { events.push("stop"); running = false; },
    ...overrides.location,
  };
  const taskManager = {
    isTaskDefined: () => true,
    isAvailableAsync: async () => true,
    ...overrides.taskManager,
  };
  const adapter = createExpoLocationAdapter({
    location,
    taskManager,
    taskName: "MineFleet360BackgroundGPS",
    purgeQueuedPoints: async () => { events.push("purge"); },
  });
  return { adapter, events };
}

test("starts native background tracking only after permission checks", async () => {
  const { adapter, events } = harness();
  await adapter.startNative();
  await adapter.startNative();
  await adapter.stopNative();
  await adapter.stopNative();
  await adapter.purgeQueuedPoints();
  assert.deepEqual(events, ["start", "stop", "purge"]);
});

for (const [name, overrides] of [
  ["undefined task", { taskManager: { isTaskDefined: () => false } }],
  ["missing task manager", { taskManager: { isAvailableAsync: async () => false } }],
  ["foreground denied", { location: { getForegroundPermissionsAsync: async () => ({ status: "denied" }) } }],
  ["background denied", { location: { getBackgroundPermissionsAsync: async () => ({ status: "denied" }) } }],
  ["location services off", { location: { hasServicesEnabledAsync: async () => false } }],
]) {
  test(`refuses start if ${name}`, async () => {
    const { adapter, events } = harness(overrides);
    await assert.rejects(adapter.startNative());
    assert.deepEqual(events, []);
  });
}

test("requires a real purge adapter and a fixed task identity", () => {
  assert.throws(() => createExpoLocationAdapter({
    location: {}, taskManager: {}, taskName: "../invalid", purgeQueuedPoints: async () => undefined,
  }), TypeError);
  assert.throws(() => createExpoLocationAdapter({
    location: {}, taskManager: {}, taskName: "MyGPS",
  }), TypeError);
});

test("does not automatically request background permission from the OS", async () => {
  const { adapter } = harness({
    location: {
      getBackgroundPermissionsAsync: async () => ({ status: "denied" }),
      requestBackgroundPermissionsAsync: async () => { throw new Error("must not request"); },
    },
  });
  await assert.rejects(adapter.startNative());
});

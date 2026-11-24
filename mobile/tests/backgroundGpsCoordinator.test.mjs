import test from "node:test";
import assert from "node:assert/strict";
import { createBackgroundGpsCoordinator } from "../src/backgroundGpsCoordinator.mjs";

const context = () => ({
  consent: true,
  authenticated: true,
  authorizedVehicle: true,
  foregroundPermission: true,
  backgroundPermission: true,
  shareActive: true,
  revoked: false,
  shareExpiresAtMs: 2_000_000,
  nowMs: 1_000_000,
  networkAvailable: true,
});

function createHarness() {
  const events = [];
  const coordinator = createBackgroundGpsCoordinator({
    startNative: async () => { events.push("start"); },
    stopNative: async () => { events.push("stop"); },
    purgeQueuedPoints: async () => { events.push("purge"); },
  });
  return { events, coordinator };
}

test("start requires a valid lease and stays idempotent on repeated polls", async () => {
  const { events, coordinator } = createHarness();
  assert.equal((await coordinator.reconcile(context())).state, "running");
  assert.equal((await coordinator.reconcile(context())).state, "running");
  assert.deepEqual(events, ["start"]);
});

test("offline suspends collection and only a new authorized context resumes it", async () => {
  const { events, coordinator } = createHarness();
  await coordinator.reconcile(context());
  assert.equal((await coordinator.reconcile({ ...context(), networkAvailable: false })).state, "suspended");
  assert.deepEqual(events, ["start", "stop"]);
  await coordinator.reconcile(context());
  assert.deepEqual(events, ["start", "stop", "start"]);
});

test("revocation stops native tracking and purges pending GPS measurements", async () => {
  const { events, coordinator } = createHarness();
  await coordinator.reconcile(context());
  const result = await coordinator.reconcile({ ...context(), revoked: true });
  assert.equal(result.state, "stopped");
  assert.deepEqual(events, ["start", "stop", "purge"]);
});

test("foreground/background permission loss and expiry fail closed", async () => {
  for (const invalid of [
    { foregroundPermission: false },
    { backgroundPermission: false },
    { shareActive: false },
    { nowMs: 2_000_000 },
  ]) {
    const { events, coordinator } = createHarness();
    await coordinator.reconcile(context());
    assert.equal((await coordinator.reconcile({ ...context(), ...invalid })).state, "stopped");
    assert.deepEqual(events, ["start", "stop", "purge"]);
  }
});

test("explicit stop always purges, even when the adapter was already stopped", async () => {
  const { events, coordinator } = createHarness();
  await coordinator.stop();
  assert.equal(coordinator.status(), "stopped");
  assert.deepEqual(events, ["stop", "purge"]);
});

test("concurrent start and stop are serialized, never leave a tracking task running", async () => {
  const { events, coordinator } = createHarness();
  const start = coordinator.reconcile(context());
  const stop = coordinator.stop();
  await Promise.all([start, stop]);
  assert.deepEqual(events, ["start", "stop", "purge"]);
  assert.equal(coordinator.status(), "stopped");
});

test("missing native adapter methods are rejected", () => {
  assert.throws(() => createBackgroundGpsCoordinator({}), TypeError);
});

test("native startup failure never reports successful running state", async () => {
  const coordinator = createBackgroundGpsCoordinator({
    startNative: async () => { throw new Error("native permission revoked"); },
    stopNative: async () => undefined,
    purgeQueuedPoints: async () => undefined,
  });
  await assert.rejects(coordinator.reconcile(context()), /native permission revoked/);
  assert.equal(coordinator.status(), "stopped");
});

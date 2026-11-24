import test from "node:test";
import assert from "node:assert/strict";
import { decideBackgroundGps } from "../src/backgroundGpsGate.mjs";

const valid = () => ({
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

test("allows a valid session only with explicit background permission", () => {
  assert.deepEqual(decideBackgroundGps(valid()), { action: "allow", purgeQueuedPoints: false });
});

for (const field of [
  "consent", "authenticated", "authorizedVehicle", "foregroundPermission",
  "backgroundPermission", "shareActive",
]) {
  test(`denies and purges when ${field} is absent`, () => {
    assert.deepEqual(decideBackgroundGps({ ...valid(), [field]: false }), {
      action: "stop", purgeQueuedPoints: true,
    });
  });
}

test("revocation stops collection and purges pending measurements", () => {
  assert.deepEqual(decideBackgroundGps({ ...valid(), revoked: true }), {
    action: "stop", purgeQueuedPoints: true,
  });
});

test("expired, invalid and missing deadlines fail closed", () => {
  for (const change of [
    { shareExpiresAtMs: 1_000_000 },
    { shareExpiresAtMs: 999_999 },
    { shareExpiresAtMs: Number.NaN },
    { shareExpiresAtMs: Number.POSITIVE_INFINITY },
    { shareExpiresAtMs: undefined },
    { nowMs: undefined },
    { nowMs: Number.NaN },
  ]) {
    assert.equal(decideBackgroundGps({ ...valid(), ...change }).action, "stop");
  }
});

test("network interruption suspends collection without pretending upload succeeded", () => {
  assert.deepEqual(decideBackgroundGps({ ...valid(), networkAvailable: false }), {
    action: "suspend", purgeQueuedPoints: false,
  });
});

test("security revocation wins over loss of network", () => {
  assert.deepEqual(decideBackgroundGps({ ...valid(), revoked: true, networkAvailable: false }), {
    action: "stop", purgeQueuedPoints: true,
  });
});

test("restored network does not override missing background permission", () => {
  assert.equal(decideBackgroundGps({ ...valid(), backgroundPermission: false, networkAvailable: true }).action, "stop");
});

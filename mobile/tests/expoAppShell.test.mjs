import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appConfig = JSON.parse(readFileSync(new URL("../expo-app/app.json", import.meta.url), "utf8"));
const manifest = JSON.parse(readFileSync(new URL("../expo-app/package.json", import.meta.url), "utf8"));
const source = readFileSync(new URL("../expo-app/App.js", import.meta.url), "utf8");

test("native prototype stays disabled by default on iOS and Android", () => {
  const config = appConfig.expo;
  const plugin = config.plugins.find((entry) => Array.isArray(entry) && entry[0] === "expo-location");
  assert.ok(plugin);
  assert.equal(config.extra.gpsBackgroundTrackingEnabled, false);
  assert.equal(plugin[1].isIosBackgroundLocationEnabled, false);
  assert.equal(plugin[1].isAndroidBackgroundLocationEnabled, false);
  assert.equal(plugin[1].isAndroidForegroundServiceEnabled, false);
});

test("native prototype is a separately packaged app, never a web dependency", () => {
  assert.equal(manifest.name, "minefleet360-driver");
  assert.match(manifest.dependencies.expo, /^~58\./);
  assert.ok(manifest.dependencies["expo-location"]);
});

test("foreground sensor check cannot silently enable background tracking or upload", () => {
  assert.match(source, /requestForegroundPermissionsAsync/);
  assert.match(source, /getCurrentPositionAsync/);
  assert.doesNotMatch(source, /startLocationUpdatesAsync|watchPositionAsync/);
  assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|AsyncStorage/);
});

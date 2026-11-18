import { describe, expect, it } from "vitest";

import type { OutboxEntry } from "./offline-outbox";
import { pendingEventsOf, projectMission } from "./offlineMissionEvents";

function entry(missionId: string, event: string, status: OutboxEntry["status"] = "pending"): OutboxEntry {
  return {
    operationId: `${missionId}-${event}`,
    tenantId: "espace-a",
    userId: "u1",
    siteId: "s1",
    endpoint: "/missions/{mission_id}/events",
    payload: { mission_id: missionId, event_type: event },
    createdAt: "2026-11-18T06:00:00Z",
    status,
    attempts: 0,
  };
}

describe("projection de l'état d'une mission avec les étapes en attente", () => {
  it("enchaîne départ, chargement et déchargement, et compte la rotation", () => {
    expect(projectMission("ASSIGNED", 0, ["DEPARTED", "ARRIVED_LOADING", "LOADED", "ARRIVED_UNLOADING", "UNLOADED"])).toEqual({
      status: "EN_ROUTE_EMPTY",
      rotationsCompleted: 1,
    });
  });

  it("une clôture en déchargement compte la rotation en cours", () => {
    expect(projectMission("UNLOADING", 2, ["COMPLETED"])).toEqual({ status: "COMPLETED", rotationsCompleted: 3 });
  });

  it("s'arrête à la première étape incohérente (le serveur tranchera)", () => {
    expect(projectMission("ASSIGNED", 0, ["LOADED", "DEPARTED"])).toEqual({ status: "ASSIGNED", rotationsCompleted: 0 });
    expect(projectMission("SUSPENDED", 0, ["DEPARTED"])).toEqual({ status: "SUSPENDED", rotationsCompleted: 0 });
  });
});

it("ne retient que les étapes non envoyées de cette mission", () => {
  const entries = [
    entry("m1", "DEPARTED", "synchronized"),
    entry("m1", "ARRIVED_LOADING"),
    entry("m2", "DEPARTED"),
    entry("m1", "LOADED", "syncing"),
    entry("m1", "ARRIVED_UNLOADING", "rejected"),
    { ...entry("m1", "X"), endpoint: "/hse/incidents" },
  ];
  expect(pendingEventsOf(entries, "m1").map((e) => e.payload.event_type)).toEqual(["ARRIVED_LOADING", "LOADED"]);
});

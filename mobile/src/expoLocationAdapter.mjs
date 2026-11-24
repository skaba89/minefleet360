/**
 * Optional Expo adapter for the backgroundGpsCoordinator.
 * Native modules are injected for Node tests; nothing runs on import.
 * The future application MUST define its TaskManager task at module scope and
 * provide a durable authenticated, encrypted sink before enabling acquisition.
 */
export function createExpoLocationAdapter({
  location, taskManager, taskName, purgeQueuedPoints,
}) {
  if (!location || !taskManager || typeof purgeQueuedPoints !== "function"
    || typeof taskName !== "string" || !/^[A-Za-z][A-Za-z0-9_.-]{2,100}$/.test(taskName)) {
    throw new TypeError("Explicit Expo location, task registration and queue purge are required");
  }

  return {
    async startNative() {
      if (!taskManager.isTaskDefined(taskName)) {
        throw new Error("Background GPS task must be defined at application module scope");
      }
      if (!(await taskManager.isAvailableAsync())) {
        throw new Error("Native background task manager is unavailable");
      }
      const foreground = await location.getForegroundPermissionsAsync();
      const background = await location.getBackgroundPermissionsAsync();
      if (foreground?.status !== "granted" || background?.status !== "granted") {
        throw new Error("User must explicitly grant foreground and background location permissions");
      }
      if (!(await location.hasServicesEnabledAsync())) {
        throw new Error("Device location services are disabled");
      }
      if (await location.hasStartedLocationUpdatesAsync(taskName)) return;
      await location.startLocationUpdatesAsync(taskName, {
        accuracy: location.Accuracy?.Balanced,
        distanceInterval: 20,
        timeInterval: 10_000,
        foregroundService: {
          notificationTitle: "MineFleet360 — suivi GPS actif",
          notificationBody: "Localisation partagée pour le véhicule autorisé",
        },
        showsBackgroundLocationIndicator: true,
        pausesUpdatesAutomatically: false,
      });
    },

    async stopNative() {
      if (await location.hasStartedLocationUpdatesAsync(taskName)) {
        await location.stopLocationUpdatesAsync(taskName);
      }
    },

    async purgeQueuedPoints() {
      await purgeQueuedPoints();
    },
  };
}

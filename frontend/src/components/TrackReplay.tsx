import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";

import { createMap, reducedMotion } from "../lib/maplibre";
import { compass, frameAt, segments, times, type ReplayFrame, type ReplayGap, type ReplayPoint } from "../lib/replay";
import { formatDateTime } from "../lib/time";

export interface ReplayTrack {
  points: ReplayPoint[];
  gaps: ReplayGap[];
  stops: { start: string; end: string; minutes: number; latitude: number; longitude: number }[];
}

const SPEEDS = [10, 60, 300, 1800];
const KIND_LABEL: Record<ReplayFrame["kind"], string> = {
  measured: "Position mesurée",
  interpolated: "Entre deux mesures : position estimée pour l'animation, non mesurée",
  gap: "Signal interrompu : dernière position mesurée affichée",
};

function lines(coords: [number, number][][]) {
  return { type: "Feature" as const, properties: {}, geometry: { type: "MultiLineString" as const, coordinates: coords } };
}

/** Relecture d'un trajet mesuré sur la carte : lecture, pause, vitesse, curseur ; arrêts et trous visibles. */
export function TrackReplay({ track, timezone }: { track: ReplayTrack; timezone: string }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<{ marker: Marker; element: HTMLDivElement } | null>(null);
  const [ready, setReady] = useState(false);
  const [failure, setFailure] = useState(false);
  const stamps = useMemo(() => times(track.points), [track.points]);
  const startAt = stamps[0] ?? 0;
  const endAt = stamps[stamps.length - 1] ?? 0;
  const [at, setAt] = useState(startAt);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(60);
  const frame = frameAt(track.points, stamps, track.gaps, at, playing && !reducedMotion());
  const parts = useMemo(() => segments(track.points, stamps, track.gaps), [track.points, stamps, track.gaps]);

  useEffect(() => {
    setAt(startAt);
    setPlaying(false);
  }, [startAt]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!container.current) return;
      try {
        const { map } = await createMap(container.current);
        if (cancelled) {
          map.remove();
          return;
        }
        map.on("load", () => {
          map.addSource("trace", { type: "geojson", data: lines([]) });
          map.addSource("parcouru", { type: "geojson", data: lines([]) });
          map.addSource("arrets", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
          map.addLayer({ id: "trace", type: "line", source: "trace", paint: { "line-color": "#8a99ab", "line-width": 3 } });
          map.addLayer({ id: "parcouru", type: "line", source: "parcouru", paint: { "line-color": "#0667df", "line-width": 4 } });
          map.addLayer({ id: "arrets", type: "circle", source: "arrets", paint: { "circle-radius": 6, "circle-color": "#e5a126", "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
          const element = document.createElement("div");
          element.className = "replay-marker";
          element.setAttribute("aria-hidden", "true");
          markerRef.current = { marker: new maplibregl.Marker({ element }).setLngLat([0, 0]).addTo(map), element };
          if (!cancelled) setReady(true);
        });
        mapRef.current = map;
      } catch {
        if (!cancelled) setFailure(true);
      }
    })();
    return () => {
      cancelled = true;
      markerRef.current?.marker.remove();
      markerRef.current = null;
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  // Tracé complet, arrêts et cadrage : une fois par trajet.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("trace") as GeoJSONSource | undefined)?.setData(lines(parts));
    (map.getSource("arrets") as GeoJSONSource | undefined)?.setData({
      type: "FeatureCollection",
      features: track.stops.map((s) => ({ type: "Feature", properties: { minutes: s.minutes }, geometry: { type: "Point", coordinates: [s.longitude, s.latitude] } })),
    });
    if (track.points.length > 0) {
      const bounds = new maplibregl.LngLatBounds();
      for (const p of track.points) bounds.extend([p.longitude, p.latitude]);
      map.fitBounds(bounds, { padding: 50, maxZoom: 15, duration: 0 });
    }
  }, [parts, track.stops, track.points, ready]);

  // Position du marqueur et portion parcourue à l'instant de lecture.
  useEffect(() => {
    const map = mapRef.current;
    const entry = markerRef.current;
    if (!map || !ready || !entry || !frame) return;
    entry.marker.setLngLat([frame.longitude, frame.latitude]);
    entry.element.className = `replay-marker replay-marker--${frame.kind}`;
    const played = segments(track.points.slice(0, frame.index + 1), stamps.slice(0, frame.index + 1), track.gaps);
    if (frame.kind === "interpolated") {
      const tail = played[played.length - 1];
      if (tail) tail.push([frame.longitude, frame.latitude]);
      else played.push([[track.points[frame.index]!.longitude, track.points[frame.index]!.latitude], [frame.longitude, frame.latitude]]);
    }
    (map.getSource("parcouru") as GeoJSONSource | undefined)?.setData(lines(played));
  }, [frame, ready, track.points, stamps, track.gaps]);

  // Horloge de lecture : temps du trajet = temps réel × vitesse choisie.
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let handle = requestAnimationFrame(function step(now) {
      const dt = now - last;
      last = now;
      setAt((current) => Math.min(endAt, current + dt * speed));
      handle = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(handle);
  }, [playing, speed, endAt]);

  useEffect(() => {
    if (playing && at >= endAt) setPlaying(false);
  }, [playing, at, endAt]);

  if (track.points.length < 2) return <p className="muted">Moins de deux positions mesurées : rien à relire sur cette période.</p>;
  const span = Math.max(1, endAt - startAt);
  const heading = frame?.headingDeg;

  return (
    <section className="card track-replay" aria-label="Relecture du trajet">
      {failure ? (
        <p role="status">Carte indisponible sur cet appareil (WebGL) : utilisez les listes d'arrêts et d'interruptions ci-dessous.</p>
      ) : (
        <div ref={container} className="track-replay-canvas" data-testid="track-replay-map" />
      )}
      <div className="track-replay-controls">
        <button
          type="button"
          className="primary"
          onClick={() => {
            if (at >= endAt) setAt(startAt);
            setPlaying(!playing);
          }}
        >
          {playing ? "Pause" : at >= endAt ? "Rejouer" : "Lecture"}
        </button>
        <label>
          Vitesse
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>×{s}</option>
            ))}
          </select>
        </label>
        <label className="track-replay-slider">
          Instant
          <input
            type="range"
            min={0}
            max={1000}
            value={Math.round(((at - startAt) / span) * 1000)}
            onChange={(e) => {
              setPlaying(false);
              setAt(startAt + (Number(e.target.value) / 1000) * span);
            }}
            aria-valuetext={formatDateTime(new Date(at).toISOString(), timezone)}
          />
        </label>
      </div>
      {frame && (
        <p className="track-replay-status">
          <strong>{formatDateTime(new Date(at).toISOString(), timezone)}</strong> ·{" "}
          <span role="status">{KIND_LABEL[frame.kind]}</span> · dernière mesure {formatDateTime(frame.recordedAt, timezone)}
          {frame.speedKmh != null ? ` · ${frame.speedKmh.toFixed(1)} km/h` : " · vitesse inconnue"}
          {heading != null ? ` · cap ${Math.round(heading)}° (${compass(heading)})` : ""}
        </p>
      )}
      <p className="muted small">
        Trait gris : trajet mesuré (coupé aux interruptions du signal) · trait bleu : déjà parcouru · points orange : arrêts.
      </p>
    </section>
  );
}

import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./residents-map.css";
import { districts, type DistrictId } from "./data";
import { baseline, type Projection } from "./engine";
import { population, residentState, type Resident } from "./population";
import {
  districtKato,
  geographicDistricts,
  geoCenters,
  toLatLng,
} from "./geography";
import type { Poll } from "./residents";
import {
  buildResidentsLod,
  residentCellColor,
  residentCellRadius,
  snapResidentPixel,
  RESIDENT_SMALL_SPRITE,
  RESIDENT_FULL_SPRITE,
  RESIDENT_SMALL_HALO,
  RESIDENT_FULL_HALO,
} from "./residentsLod";
export interface Marker {
  id: string;
  districtId: DistrictId | null;
  label: string;
}
interface Props {
  /** Decisions already placed on the map; city-wide ones sit near the centre. */
  markers?: Marker[];
  /** District to draw attention to before the first decision. */
  spotlight?: DistrictId | null;
  selected: DistrictId | null;
  onSelect: (id: DistrictId) => void;
  result: Projection | null;
  after: boolean;
  poll: Poll | null;
  panelOpen: boolean;
  minutes: number;
  onResident: (p: Resident) => void;
  residentId: number | null;
  stayInside: boolean;
}
export default function CityMap(props: Props) {
  const host = useRef<HTMLDivElement>(null),
    mapRef = useRef<L.Map | null>(null),
    overlayRef = useRef<HTMLCanvasElement | null>(null),
    snapshot = useRef(props);
  snapshot.current = props;
  const [mapError, setMapError] = useState(false),
    [ready, setReady] = useState(false);
  useEffect(() => {
    const map = L.map(host.current!, {
      zoomControl: false,
      attributionControl: true,
      minZoom: 10,
      maxZoom: 18,
      zoomSnap: 0.5,
      preferCanvas: true,
    }).setView([51.153, 71.427], 12);
    mapRef.current = map;
    // Dev-only handle lets browser regressions exercise Leaflet's real zoom events.
    const testHost = host.current! as HTMLDivElement & { simMap?: L.Map };
    if (import.meta.env.DEV) testHost.simMap = map;
    L.control.zoom({ position: "bottomright" }).addTo(map);
    // OSM tiles, desaturated in CSS (.game .leaflet-tile-pane) so districts, residents and decisions read first.
    const tiles = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
      },
    ).addTo(map);
    tiles.on("tileerror", () => setMapError(true));
    tiles.on("tileload", () => setMapError(false));
    const boundaries = L.geoJSON(geographicDistricts, {
      style: () => ({
        color: "#477363",
        weight: 1.5,
        fillColor: "#d4e6c7",
        fillOpacity: 0.12,
      }),
      onEachFeature(feature, layer) {
        const id = Object.entries(districtKato).find(
          ([, kato]) => kato === feature.properties.kato,
        )?.[0] as DistrictId | undefined;
        if (id) layer.on("click", () => snapshot.current.onSelect(id));
        else
          layer.bindPopup(
            "Сарайшык · реальный район. В исходной модели пока нет отдельных показателей.",
          );
      },
    }).addTo(map);
    map.attributionControl.addAttribution(
      'Границы: <a href="https://map.gov.kz" target="_blank" rel="noreferrer">map.gov.kz</a> · снимок 23.09.2026',
    );
    const markers = districts.map((d) =>
      L.marker(geoCenters[d.id], {
        keyboard:false,
        icon: L.divIcon({
          className: "real-district-marker",
          html: `<button aria-label="Район ${d.name}" class="district-label"><span>${d.name}</span><small></small></button>`,
          iconSize: [120, 38],
          iconAnchor: [60, 19],
        }),
      })
        .addTo(map)
        .on("click", () => snapshot.current.onSelect(d.id)),
    );
    const decisionMarkers = new Map<string, L.Marker>();
    const cityCenter: L.LatLngExpression = [51.128, 71.43];
    const overlay = document.createElement("canvas");
    overlay.className = "resident-overlay";
    overlay.style.pointerEvents = "none";
    const residentPane=map.createPane("residents");residentPane.style.zIndex="3";residentPane.style.pointerEvents="none";residentPane.appendChild(overlay);
    overlayRef.current = overlay;
    const ctx = overlay.getContext("2d")!,
      sprites = new Image();
    sprites.src = "/residents.png";
    const draw = () => {
      // Never latch visibility to zoomstart: interrupted flyTo/zoom animations
      // need not finish in the same order as they started.
      overlay.style.opacity = "1";
      const s = snapshot.current,
        size = map.getSize(),
        ratio = Math.min(devicePixelRatio, 2),
        width = Math.round(size.x * ratio),
        height = Math.round(size.y * ratio);
      if (overlay.width !== width || overlay.height !== height) {
        overlay.width = width;
        overlay.height = height;
        overlay.style.width = size.x + "px";
        overlay.style.height = size.y + "px";
      }
      L.DomUtil.setPosition(overlay,map.containerPointToLayerPoint([0,0]));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, size.x, size.y);
      ctx.imageSmoothingEnabled = false;
      function* screenResidents() {
        for (const p of population) {
          const state = residentState(p, s.minutes, s.stayInside),
            point = map.latLngToContainerPoint(toLatLng(state.point));
          if (
            point.x < -12 ||
            point.y < -12 ||
            point.x > size.x + 12 ||
            point.y > size.y + 12
          )
            continue;
          const cohort = s.poll?.cohorts?.find(
              (c) => c.districtId === p.districtId && c.profileId === p.profileId,
            ),
            row = s.poll?.districts[p.districtIndex];
          yield {
            id: p.id,
            x: point.x,
            y: point.y,
            vote: cohort
              ? p.cohortIndex < cohort.yes
              : row
                ? p.index < row.yes
                : null,
            alpha: s.selected && s.selected !== p.districtId ? 0.2 : 0.95,
            highlighted: s.residentId === p.id,
            p,
            state,
          };
        }
      }
      const lod = buildResidentsLod(map.getZoom(), screenResidents());
      overlay.dataset.detail = lod.detail;
      const snap = (value: number) => snapResidentPixel(value, ratio);
      const drawResident = (point: NonNullable<typeof lod.highlighted>) => {
        const { p, state } = point;
        const full = lod.detail === "full" || point.highlighted;
        const px = snap(full ? RESIDENT_FULL_SPRITE : RESIDENT_SMALL_SPRITE);
        const halo = full ? RESIDENT_FULL_HALO : RESIDENT_SMALL_HALO;
        ctx.globalAlpha = point.highlighted ? 1 : point.alpha;
        if (point.vote !== null || point.highlighted) {
          ctx.fillStyle =
            point.highlighted ? "#fff59d" : point.vote ? "#5fae3f" : "#d8584a";
          ctx.beginPath();
          ctx.arc(snap(point.x), snap(point.y), snap(halo), 0, Math.PI * 2);
          ctx.fill();
        } else if (s.spotlight === p.districtId && !s.selected) {
          ctx.fillStyle = "#e58a7a";
          ctx.beginPath();
          ctx.arc(snap(point.x), snap(point.y), snap(halo), 0, Math.PI * 2);
          ctx.fill();
        } else {
          ctx.fillStyle = "#d9e6cf";
          ctx.beginPath();
          ctx.arc(snap(point.x), snap(point.y), snap(halo), 0, Math.PI * 2);
          ctx.fill();
        }
        const next = residentState(p, s.minutes + 0.2, s.stayInside).point,
          dx = next[0] - state.point[0],
          dy = next[1] - state.point[1],
          direction =
            Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 2 : 1) : dy < 0 ? 3 : 0,
          frame = state.moving ? Math.floor(s.minutes * 4 + p.id) % 3 : 1;
        if (sprites.complete && sprites.naturalWidth)
          ctx.drawImage(
            sprites,
            (p.sprite % 5) * 48 + frame * 16,
            Math.floor(p.sprite / 5) * 64 + direction * 16,
            16,
            16,
            snap(point.x - px / 2),
            snap(point.y - px),
            px,
            px,
          );
        else {
          ctx.fillStyle = "#356749";
          ctx.fillRect(snap(point.x), snap(point.y), snap(2), snap(3));
        }
      };
      for (const cell of lod.cells.values()) {
        if (lod.detail === "sparse") {
          drawResident(cell.resident);
          continue;
        }
        ctx.globalAlpha = cell.alphaSum / cell.count;
        ctx.fillStyle = residentCellColor(cell.yes, cell.votes);
        ctx.beginPath();
        ctx.arc(
          snap(cell.x), snap(cell.y), snap(residentCellRadius(cell.count)),
          0, Math.PI * 2,
        );
        ctx.fill();
      }
      for (const point of lod.residents) drawResident(point);
      if (lod.highlighted) drawResident(lod.highlighted);
      ctx.globalAlpha = 1;
    };
    const update = () => {
      draw();
      const s = snapshot.current;
      boundaries.setStyle((feature) => {
        const id = Object.entries(districtKato).find(
          ([, k]) => k === feature?.properties.kato,
        )?.[0];
        const index = districts.findIndex((d) => d.id === id);
        const spot = s.spotlight === id && !s.selected;
        const delta =
          index >= 0 && s.after && s.result
            ? s.result.districts[index].score - baseline.districts[index].score
            : 0;
        return {
          weight: s.selected === id ? 3 : spot ? 3 : 1.2,
          color: s.selected === id ? "#1f5a3c" : spot ? "#c9503b" : "#5a7562",
          fillColor: delta > 0.05 ? "#7fb35a" : spot ? "#e07a68" : "#c9d9bf",
          fillOpacity:
            s.selected === id
              ? 0.14
              : delta > 0.05
                ? Math.min(0.42, 0.08 + delta * 0.08)
                : spot
                  ? 0.16
                  : 0.06,
          dashArray: index < 0 ? "5 5" : "",
        };
      });
      // Decisions on the map: one chip list per district, city-wide ones near the centre.
      const groups = new Map<string, string[]>();
      for (const m of s.markers ?? []) {
        const key = m.districtId ?? "city";
        groups.set(key, [...(groups.get(key) ?? []), m.label]);
      }
      for (const [key, marker] of decisionMarkers)
        if (!groups.has(key)) {
          marker.remove();
          decisionMarkers.delete(key);
        }
      for (const [key, labels] of groups) {
        const html = `<ul class="map-markers${key === "city" ? " city" : ""}">${labels
          .map((l) => `<li>${l}</li>`)
          .join("")}</ul>`;
        const existing = decisionMarkers.get(key);
        if (existing) {
          const el = existing.getElement();
          if (el && el.innerHTML !== html) el.innerHTML = html;
          continue;
        }
        const at =
          key === "city" ? cityCenter : geoCenters[key as DistrictId];
        const created = L.marker(at, {
          keyboard: false,
          interactive: false,
          icon: L.divIcon({ className: "decision-marker", html, iconSize: [160, 20], iconAnchor: [80, -14] }),
        }).addTo(map);
        decisionMarkers.set(key, created);
      }
      markers.forEach((marker, i) => {
        const el = marker.getElement();
        const button = el?.querySelector("button"),
          small = el?.querySelector("small");
        button?.setAttribute(
          "aria-pressed",
          String(s.selected === districts[i].id),
        );
        button?.classList.toggle("selected", s.selected === districts[i].id);
        button?.classList.toggle(
          "spotlight",
          s.spotlight === districts[i].id && !s.selected,
        );
        if (small)
          small.textContent = (
            s.after && s.result ? s.result.districts[i] : baseline.districts[i]
          ).score.toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      });
    };
    let settledFrame = 0;
    const redrawSettled = () => {
      draw();
      cancelAnimationFrame(settledFrame);
      settledFrame = requestAnimationFrame(draw);
    };
    map.on("move zoom resize", draw);
    map.on("zoomend moveend", redrawSettled);
    sprites.onload = draw;
    const timer = window.setInterval(update, 100);
    update();
    setReady(true);
    const click = (event: MouseEvent) => {
      if (
        (event.target as HTMLElement).closest(
          ".leaflet-marker-icon,.leaflet-control,.leaflet-popup",
        )
      )
        return;
      const rect = host.current!.getBoundingClientRect();
      const clickPoint = L.point(
        event.clientX - rect.left,
        event.clientY - rect.top,
      );
      let nearest: Resident | undefined,
        distance = 8;
      for (const p of population) {
        const pixel = map.latLngToContainerPoint(
          toLatLng(
            residentState(
              p,
              snapshot.current.minutes,
              snapshot.current.stayInside,
            ).point,
          ),
        );
        const d = pixel.distanceTo(clickPoint);
        if (d < distance) {
          nearest = p;
          distance = d;
        }
      }
      if (nearest) {
        event.stopPropagation();
        snapshot.current.onResident(nearest);
      }
    };
    host.current!.addEventListener("click", click, true);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(host.current!);
    return () => {
      clearInterval(timer);
      resize.disconnect();
      sprites.onload = null;
      cancelAnimationFrame(settledFrame);
      map.off("zoomend moveend", redrawSettled);
      map.off("move zoom resize", draw);
      delete testHost.simMap;
      host.current?.removeEventListener("click", click, true);
      overlay.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const reduced = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    map.flyTo(
      props.selected ? geoCenters[props.selected] : [51.153, 71.427],
      props.selected ? 13 : 12,
      { animate: !reduced, duration: 0.6 },
    );
  }, [props.selected, ready]);
  return (
    <div className="city-map real-city-map">
      <div
        ref={host}
        className="leaflet-host"
        aria-label="Карта Астаны: OpenStreetMap и реальные границы районов"
      />
      {mapError && (
        <div className="map-error glass" role="status">
          Картографические тайлы временно недоступны. Границы районов сохранены.
        </div>
      )}
    </div>
  );
}

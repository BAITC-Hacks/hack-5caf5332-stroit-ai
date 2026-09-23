import raw from "./astana-districts.json" with { type: "json" };
import type { DistrictId } from "./data";
import type { FeatureCollection, MultiPolygon } from "geojson";
export const geographicDistricts = raw as FeatureCollection<
  MultiPolygon,
  { kato: string; name_ru: string }
>;
export const districtKato: Record<DistrictId, string> = {
  esil: "711210000",
  almaty: "711110000",
  saryarka: "711310000",
  baikonur: "711410000",
  nura: "711510000",
};
export const geoCenters: Record<DistrictId, [number, number]> = {
  esil: [51.112, 71.43],
  almaty: [51.169, 71.505],
  saryarka: [51.185, 71.385],
  baikonur: [51.213, 71.457],
  nura: [51.126, 71.367],
};
export function toWorld(lng: number, lat: number): [number, number] {
  return [(lng - 71.2) * 2000, (51.3 - lat) * 3200];
}
export function toLatLng(point: [number, number]): [number, number] {
  return [51.3 - point[1] / 3200, 71.2 + point[0] / 2000];
}
export function mainPolygon(id: DistrictId): [number, number][] {
  const rings = geographicDistricts.features
    .filter((f) => f.properties.kato === districtKato[id])
    .flatMap((f) => f.geometry.coordinates.map((p) => p[0]));
  const area = (r: number[][]) =>
    Math.abs(
      r.reduce((n, p, i) => {
        const q = r[(i + 1) % r.length];
        return n + p[0] * q[1] - q[0] * p[1];
      }, 0),
    );
  const ring = rings.sort((a, b) => area(b) - area(a))[0];
  return ring.map((p) => toWorld(p[0], p[1]));
}

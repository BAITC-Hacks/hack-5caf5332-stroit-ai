export const RESIDENT_DETAIL_ZOOM = 12.5;
export const RESIDENT_FULL_ZOOM = 14;
export const RESIDENT_CLUSTER_CELL = 12;
export const RESIDENT_SPRITE_CELL = 8;
export const RESIDENT_CLUSTER_MAX_RADIUS = 3.5;
export const RESIDENT_SMALL_SPRITE = 8;
export const RESIDENT_FULL_SPRITE = 12;
export const RESIDENT_SMALL_HALO = 2;
export const RESIDENT_FULL_HALO = 6;

export interface ResidentScreenPoint {
  id: number;
  x: number;
  y: number;
  vote: boolean | null;
  alpha: number;
  highlighted: boolean;
}

export interface ResidentCell<T> {
  x: number;
  y: number;
  count: number;
  yes: number;
  votes: number;
  alphaSum: number;
  resident: T;
}

export function residentDetail(zoom: number) {
  return zoom < RESIDENT_DETAIL_ZOOM
    ? "cluster"
    : zoom < RESIDENT_FULL_ZOOM
      ? "sparse"
      : "full";
}

// Accept a stream so projection and binning need only one population pass.
export function buildResidentsLod<T extends ResidentScreenPoint>(
  zoom: number,
  points: Iterable<T>,
) {
  const detail = residentDetail(zoom);
  const cellSize = detail === "cluster" ? RESIDENT_CLUSTER_CELL : RESIDENT_SPRITE_CELL;
  const cells = new Map<string, ResidentCell<T>>();
  const residents: T[] = [];
  let highlighted: T | undefined;
  for (const point of points) {
    if (point.highlighted) {
      highlighted = point;
      continue;
    }
    if (detail === "full") {
      residents.push(point);
      continue;
    }
    const column = Math.floor(point.x / cellSize);
    const row = Math.floor(point.y / cellSize);
    const key = `${column}:${row}`;
    const cell = cells.get(key);
    if (cell) {
      cell.count++;
      cell.yes += point.vote === true ? 1 : 0;
      cell.votes += point.vote === null ? 0 : 1;
      cell.alphaSum += point.alpha;
      if (point.id < cell.resident.id) cell.resident = point;
    } else {
      cells.set(key, {
        x: (column + 0.5) * cellSize,
        y: (row + 0.5) * cellSize,
        count: 1,
        yes: point.vote === true ? 1 : 0,
        votes: point.vote === null ? 0 : 1,
        alphaSum: point.alpha,
        resident: point,
      });
    }
  }
  return { detail, cells, residents, highlighted };
}

export function residentCellRadius(count: number) {
  return Math.min(RESIDENT_CLUSTER_MAX_RADIUS, 1.5 + Math.sqrt(count) * 0.5);
}

export function residentCellColor(yes: number, votes: number) {
  if (!votes) return "#3d5c4a";
  const share = yes / votes;
  // Interpolate from the existing red to green poll colors.
  return `rgb(${Math.round(216 - 121 * share)}, ${Math.round(88 + 86 * share)}, ${Math.round(74 - 11 * share)})`;
}

export function snapResidentPixel(value: number, ratio: number) {
  return Math.round(value * ratio) / ratio;
}

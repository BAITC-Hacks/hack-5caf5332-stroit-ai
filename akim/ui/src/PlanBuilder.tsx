// Shared number formatter used by the resident and AI panels.
export const fmt = (n: number, d = 2) =>
  n.toLocaleString("ru-RU", {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });

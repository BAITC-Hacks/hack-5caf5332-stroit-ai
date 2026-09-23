import { compareMobility } from "./mobility";
import type { Choice } from "./data";
self.onmessage = (event: MessageEvent<Choice[]>) => {
  try {
    self.postMessage({ result: compareMobility(event.data) });
  } catch {
    self.postMessage({ error: "Не удалось рассчитать мобильность." });
  }
};

import type { Choice } from "../src/data";
import type { CityData } from "../src/city-data";
import { ingestThreads } from "./threads";
import { askResidents } from "./polls";
import { PublicError, type Llm } from "./llm";
export async function askWithEvidence(
  llm: Llm,
  question: string,
  plan: Choice[],
  context: CityData,
  useThreads = false,
  signal?: AbortSignal,
) {
  const evidence = useThreads
    ? await ingestThreads(llm, question, plan, signal)
    : undefined;
  try {
    return {
      poll: await askResidents(llm, question, plan, context, signal, evidence),
      evidence,
    };
  } catch (e) {
    if (evidence && e instanceof PublicError && e.status === 400)
      return { poll: null, evidence, notice: e.message };
    throw e;
  }
}

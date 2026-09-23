import { z } from "zod";
export const districtSchema = z.enum([
  "esil",
  "almaty",
  "saryarka",
  "baikonur",
  "nura",
]);
export const choiceSchema = z
  .object({
    measureId: z.enum([
      "M1",
      "M2",
      "M3",
      "M4",
      "M5",
      "M6",
      "M7",
      "M8",
      "M9",
      "M10",
      "M11",
      "M12",
      "M13",
      "M14",
    ]),
    districtId: districtSchema.optional(),
  })
  .strict();
export const planSchema = z.array(choiceSchema).max(5);
export const askRequest = z
  .object({ question: z.string().trim().min(1).max(1000), plan: planSchema })
  .strict();
export const akimRequest = z
  .object({ mode: z.enum(["advisor", "autopilot"]), plan: planSchema })
  .strict();
export const wireChoice = z.object({
  measureId: z.enum([
    "M1",
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M7",
    "M8",
    "M9",
    "M10",
    "M11",
    "M12",
    "M13",
    "M14",
  ]),
  districtId: districtSchema.nullable(),
});
export const parsedQuestion = z.object({
  supported: z.boolean(),
  reason: z.string(),
  proposals: z.array(
    z.object({ label: z.string(), choices: z.array(wireChoice) }),
  ),
});
export const opinionsSchema = z.object({
  cohorts: z.array(
    z.object({
      districtId: districtSchema,
      profileId: z.number().int(),
      probability: z.number(),
      quote: z.string(),
    }),
  ),
});
export const narrativeSchema = z.object({
  title: z.string(),
  strengths: z.string(),
  risks: z.string(),
  why: z.string(),
});

import { z } from "zod";
import { directions } from "../src/data";
import { BUDGET_LIMIT } from "../src/money";
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
  .object({
    question: z.string().trim().min(1).max(1000),
    plan: planSchema,
    useThreads: z.boolean().optional(),
  })
  .strict();
export const goalConstraintsSchema = z.object({
  priorities: z.array(z.enum(directions)).max(directions.length),
  protectedDistricts: z.array(districtSchema).max(5),
  minSupportPercent: z.number().min(0).max(100),
  reserveUnits: z.number().min(0).max(BUDGET_LIMIT),
  mustInclude: z.array(choiceSchema.shape.measureId).max(5),
  mustExclude: z.array(choiceSchema.shape.measureId).max(14),
}).strict();
export type GoalConstraints = z.infer<typeof goalConstraintsSchema>;
export const constraintsInput = goalConstraintsSchema.partial().transform((value) => ({
  priorities: value.priorities ?? [],
  protectedDistricts: value.protectedDistricts ?? [],
  minSupportPercent: value.minSupportPercent ?? 0,
  reserveUnits: value.reserveUnits ?? 0,
  mustInclude: value.mustInclude ?? [],
  mustExclude: value.mustExclude ?? [],
}));
export const parsedGoalSchema = z.object({
  supported: z.boolean(),
  constraints: goalConstraintsSchema,
}).strict();
export const akimRequest = z
  .object({
    mode: z.enum(["advisor", "autopilot", "goal"]),
    plan: planSchema,
    goal: z.string().trim().min(1).max(300).optional(),
    constraints: constraintsInput.optional(),
  })
  .strict()
  .refine((value) => value.mode !== "goal" || !!value.goal || !!value.constraints, {
    message: "Укажите цель до 300 символов или структурированные ограничения.",
  });
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
export const threadsRequest = z.object({
  question: z.string().trim().min(3).max(1000),
  plan: planSchema,
});
export const explainRequest = z
  .object({
    plan: planSchema,
    priorities: z
      .array(z.enum(["Транспорт", "Экология", "Соцсфера", "Безопасность", "Сервисы"]))
      .max(2)
      .default([]),
  })
  .strict();
export const planBriefSchema = z.object({
  summary: z.string(),
  tradeoff: z.string(),
  nextStep: z.string(),
});

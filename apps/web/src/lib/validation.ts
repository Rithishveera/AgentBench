import { z } from "zod";

export const registerAgentSchema = z.object({
  name: z.string().trim().min(1, "Enter an agent name").max(200),
  url: z.string().url("Enter a valid HTTP or HTTPS URL").refine(
    (value) => {
      try {
        return ["http:", "https:"].includes(new URL(value).protocol);
      } catch {
        return false;
      }
    },
    "Use an HTTP or HTTPS URL",
  ),
  category: z.enum(["coding", "research", "support"]),
  framework_tag: z.string().trim().max(100).optional(),
  max_concurrency: z.number().int().min(1).max(100),
});

export const benchmarkRequestSchema = z.object({
  suite_id: z.string().min(1).max(100),
  agent_ids: z.array(z.string().uuid()).min(1).max(200),
  repetitions: z.number().int().min(1).max(1000),
  fault_flags: z.record(z.unknown()),
  paired: z.boolean(),
  seed: z.number().int().min(0).max(Number.MAX_SAFE_INTEGER).optional(),
});
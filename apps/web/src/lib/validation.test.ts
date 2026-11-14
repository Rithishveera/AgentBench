import { describe, expect, it } from "vitest";
import { benchmarkRequestSchema, registerAgentSchema } from "./validation";

describe("dashboard request validation", () => {
  it("accepts a bounded external agent registration", () => {
    expect(registerAgentSchema.safeParse({
      name: "PatchPilot",
      url: "https://agent.example.test",
      category: "coding",
      max_concurrency: 2,
    }).success).toBe(true);
  });

  it("rejects non-HTTP agent URLs and invalid categories", () => {
    expect(registerAgentSchema.safeParse({
      name: "Bad URL",
      url: "javascript:alert(1)",
      category: "unknown",
      max_concurrency: 0,
    }).success).toBe(false);
  });

  it("requires agents and bounds benchmark repetitions", () => {
    expect(benchmarkRequestSchema.safeParse({
      suite_id: "coding",
      agent_ids: [],
      repetitions: 0,
      fault_flags: {},
      paired: true,
    }).success).toBe(false);
  });
});
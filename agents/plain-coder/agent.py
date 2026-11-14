"""Minimal coding agent that emits a unified diff."""

from __future__ import annotations

import os

from agentbench_sdk import RunContext, RunResult
from agentbench_sdk.integrations.plain import serve

MOCK_PATCH = """diff --git a/src/scores.py b/src/scores.py
index 1111111..2222222 100644
--- a/src/scores.py
+++ b/src/scores.py
@@ -1,2 +1,4 @@
 def clamp(value: int, lower: int = 0, upper: int = 100) -> int:
-    return value
+    if lower > upper:
+        raise ValueError("lower must not exceed upper")
+    return max(lower, min(upper, value))
"""


async def handler(ctx: RunContext) -> RunResult:
    if os.getenv("MOCK") == "1":
        if ctx.task.id != "fix-failing-test":
            raise ValueError("MOCK mode only supports fix-failing-test")
        return RunResult(patch=MOCK_PATCH)
    if ctx.llm is None:
        raise ValueError("an LLM configuration is required outside MOCK mode")

    files = "\n\n".join(f"--- {file.path}\n{file.content}" for file in ctx.task.files)
    async with ctx.tool("generate_patch"):
        response = await ctx.openai_client().chat.completions.create(
            model=ctx.llm.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return only a unified diff. Do not include markdown fences."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{ctx.task.prompt}\n\nVisible files:\n{files}",
                },
            ],
        )
    patch = response.choices[0].message.content
    if not patch:
        raise ValueError("model returned an empty patch")
    patch = patch.strip()
    if patch.startswith("```diff"):
        patch = patch[len("```diff") :].strip()
    if patch.endswith("```"):
        patch = patch[:-3].strip()
    return RunResult(patch=patch)


if __name__ == "__main__":
    serve(handler)

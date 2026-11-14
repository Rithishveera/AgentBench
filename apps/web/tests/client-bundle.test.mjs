import assert from "node:assert/strict";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../.next/static");

async function filesIn(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map((entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? filesIn(target) : [target];
  }));
  return files.flat();
}

test("the server API key is absent from built client assets", async () => {
  const apiKey = process.env.API_KEY;
  assert.ok(apiKey, "Set API_KEY while running the client bundle security test");
  const assets = await filesIn(root);
  assert.ok(assets.length > 0, "Build the web app before scanning its client assets");
  for (const asset of assets) {
    const contents = await readFile(asset);
    assert.equal(contents.includes(Buffer.from(apiKey)), false, `${asset} contains API_KEY`);
  }
});
import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const schema = JSON.parse(await readFile(new URL("../../api/openapi.json", import.meta.url), "utf8"));
const output = astToString(await openapiTS(schema));
await writeFile(new URL("../src/lib/api-schema.d.ts", import.meta.url), output);
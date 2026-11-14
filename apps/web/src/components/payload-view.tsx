import { createElement } from "react";

export function PayloadView({ value }: Readonly<{ value: unknown }>) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return createElement("pre", { className: "payload-pre" }, text ?? "");
}
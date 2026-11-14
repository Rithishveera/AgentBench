import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { PayloadView } from "./payload-view";

describe("payload rendering", () => {
  it("renders markup-looking agent text as inert escaped content", () => {
    const markup = renderToStaticMarkup(
      createElement(PayloadView, {
        value: { response: "<script>alert(1)</script><b>hello</b>" },
      }),
    );
    expect(markup).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(markup).not.toContain("<script>");
  });
});
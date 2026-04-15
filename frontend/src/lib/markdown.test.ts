import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";

import {
  markdownRehypePlugins,
  markdownRemarkPlugins,
  markdownUrlTransform
} from "./markdown.ts";

test("markdown pipeline renders LaTeX expressions with KaTeX", () => {
  const content = String.raw`Inline $r_d$.

$$R_d = \frac{1}{\gamma_{Rd}}$$`;

  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: markdownRemarkPlugins,
        rehypePlugins: markdownRehypePlugins
      },
      content
    )
  );

  assert.match(html, /katex/);
  assert.doesNotMatch(html, /\$r_d\$/);
  assert.match(html, /annotation encoding="application\/x-tex">r_d<\/annotation>/);
});

test("markdown pipeline preserves internal citation protocols", () => {
  const content = "[EN 1990:2002 · 3.1(2)](reference://m1-ref-1)";

  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        urlTransform: markdownUrlTransform
      },
      content
    )
  );

  assert.match(html, /href="reference:\/\/m1-ref-1"/);
});

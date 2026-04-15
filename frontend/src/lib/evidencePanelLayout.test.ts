import assert from "node:assert/strict";
import test from "node:test";

import { getEvidencePanelClassName } from "./evidencePanelLayout.ts";

test("getEvidencePanelClassName uses responsive clamp width", () => {
  const className = getEvidencePanelClassName();

  // 语义断言：使用 clamp 响应式宽度（非固定宽度）
  assert.match(className, /w-\[clamp\(/);
  // 大屏（>= xl/1280px）时可见
  assert.match(className, /xl:flex/);
  // 小屏默认隐藏
  assert.match(className, /\bhidden\b/);
});

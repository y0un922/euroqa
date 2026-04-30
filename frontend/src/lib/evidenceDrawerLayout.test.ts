import assert from "node:assert/strict";
import test from "node:test";

import {
  clampDrawerHeight,
  getDefaultDrawerHeight,
  getDrawerBounds,
  resizeDrawerHeight
} from "./evidenceDrawerLayout.ts";

test("getDrawerBounds returns stable min and max values", () => {
  assert.deepEqual(getDrawerBounds(900), {
    minHeight: 180,
    maxHeight: 648
  });
});

test("getDefaultDrawerHeight stays within bounds", () => {
  assert.equal(getDefaultDrawerHeight(900), 306);
  assert.equal(getDefaultDrawerHeight(320), 180);
});

test("clampDrawerHeight enforces lower and upper bounds", () => {
  assert.equal(clampDrawerHeight(120, 900), 180);
  assert.equal(clampDrawerHeight(900, 900), 648);
});

test("resizeDrawerHeight grows upward and shrinks downward within bounds", () => {
  assert.equal(resizeDrawerHeight(280, -60, 900), 340);
  assert.equal(resizeDrawerHeight(280, 80, 900), 200);
  assert.equal(resizeDrawerHeight(280, 400, 900), 180);
});

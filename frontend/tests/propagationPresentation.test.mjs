import assert from "node:assert/strict";
import test from "node:test";

import { buildPropagationNotice } from "../src/views/events/propagationPresentation.ts";

test("insufficient propagation evidence is explained without claiming a path", () => {
  const notice = buildPropagationNotice({
    coverage_status: "insufficient",
    limitations: ["现有报道之间缺少足够的显式或推断传播证据"],
    summary: { edge_count: 0 }
  });

  assert.match(notice, /传播证据不足/);
  assert.match(notice, /不代表已验证传播路径/);
  assert.match(notice, /缺少足够的显式或推断传播证据/);
});

test("sufficient propagation data does not add a warning", () => {
  assert.equal(
    buildPropagationNotice({ coverage_status: "sufficient", limitations: [] }),
    ""
  );
});

import assert from "node:assert/strict";
import test from "node:test";

import { buildLifecycleNote } from "../src/views/events/lifecyclePresentation.ts";

test("lifecycle note exposes confidence and low-volume evidence", () => {
  assert.equal(
    buildLifecycleNote({
      lifecycle_confidence: 0.68,
      lifecycle_evidence: { low_volume: true }
    }),
    "置信度 68% · 样本量有限"
  );
});

test("lifecycle note stays empty when no evidence is available", () => {
  assert.equal(buildLifecycleNote({}), "");
});

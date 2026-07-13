import assert from "node:assert/strict";
import test from "node:test";

import {
  formatTaskStatus,
  getTaskStatusTag,
  taskKeyword
} from "../src/components/taskPresentation.ts";

test("successful tasks use a localized completed state", () => {
  assert.equal(formatTaskStatus("success"), "已完成");
  assert.equal(getTaskStatusTag("success"), "success");
});

test("task history exposes the analysis keyword from the API payload", () => {
  assert.equal(
    taskKeyword({ payload: { keyword: "《功夫女足》电影" } }),
    "《功夫女足》电影"
  );
  assert.equal(taskKeyword({ payload: {} }), "-");
});

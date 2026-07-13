import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("event card passes numeric progress props to Element Plus", async () => {
  const source = await readFile(
    new URL("../src/components/EventCard.vue", import.meta.url),
    "utf8"
  );

  assert.match(source, /:stroke-width="6"/);
  assert.doesNotMatch(source, /(?<!:)stroke-width="6"/);
});

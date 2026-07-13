import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { buildRiskRadarMetrics } from "../src/views/events/riskRadar.ts";

test("risk radar metrics are derived from real event fields", () => {
  const metrics = buildRiskRadarMetrics({
    sentiment_negative: 0.25,
    first_publish_time: "2026-07-12T00:00:00Z",
    last_activity_time: "2026-07-13T00:00:00Z",
    platform: { platforms: [{}, {}, {}, {}] },
    report: {
      risk_data: {
        score: 42,
        suspicious_count: 2,
        total_count: 10
      }
    },
    articles: {
      total: 10,
      articles: Array.from({ length: 10 }, () => ({
        likes_count: 60,
        comments_count: 30,
        reposts_count: 9
      }))
    }
  });

  assert.deepEqual(
    metrics.map(metric => metric.name),
    ["传播活跃度", "负面占比", "可疑风险", "可疑报道率", "平台覆盖", "互动强度"]
  );
  assert.deepEqual(metrics.map(metric => metric.value), [50, 25, 42, 20, 50, 50]);
});

test("risk radar returns finite zeroes when evidence is absent", () => {
  const metrics = buildRiskRadarMetrics({});

  assert.equal(metrics.length, 6);
  assert.ok(metrics.every(metric => metric.value === 0));
  assert.ok(metrics.every(metric => Number.isFinite(metric.value)));
});

test("event detail renders the tested radar metrics without fixed placeholders", async () => {
  const source = await readFile(
    new URL("../src/views/events/detail.vue", import.meta.url),
    "utf8"
  );

  assert.match(source, /buildRiskRadarMetrics\(eventData\.value\)/);
  assert.doesNotMatch(source, /fakeRisk\s*=\s*45/);
  assert.doesNotMatch(source, /heatVal\s*\*\s*0\.7/);
});

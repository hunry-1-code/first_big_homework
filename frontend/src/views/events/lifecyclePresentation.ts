export function buildLifecycleNote(data: any): string {
  const confidence = Number(data?.lifecycle_confidence);
  const hasConfidence = Number.isFinite(confidence);
  const lowVolume = data?.lifecycle_evidence?.low_volume === true;
  if (!hasConfidence && !lowVolume) return "";

  const parts: string[] = [];
  if (hasConfidence) {
    parts.push(`置信度 ${Math.round(Math.min(1, Math.max(0, confidence)) * 100)}%`);
  }
  if (lowVolume) parts.push("样本量有限");
  return parts.join(" · ");
}

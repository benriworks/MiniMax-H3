// A short, exact crop of an actual demo can have fewer pixels than a whole
// official-page excerpt. Keep that exception tied to its reviewed evidence.
export function validateCaptureForRender(capture, metadata, staged, preparationSources, proofs) {
  if (metadata.codec_name !== 'png') throw Error('Source capture must be PNG');
  if (capture.origin !== 'demonstration') {
    if (metadata.width < 300 || metadata.height < 100) throw Error('Source capture resolution too low');
    return {origin: capture.origin ?? 'legacy', width: metadata.width, height: metadata.height};
  }
  const proof = proofs.find(item => item.origin === 'demonstration'
    && item.artifact?.sha256 === staged.sha256 && item.artifact?.bytes === staged.bytes
    && item.title === capture.title && item.product === capture.product && item.phase === capture.phase);
  if (!proof || proof.review_status !== 'capture_review_passed'
    || proof.fictional_materials_only !== true || proof.personal_information_excluded !== true
    || proof.pixel_exact_crop_verified !== true || proof.content_modified !== false) {
    throw Error('Small demonstration crop needs reviewed, unmodified pixel evidence');
  }
  for (const source of [proof.artifact, proof.context]) {
    if (!preparationSources.some(item => item.path === source.path && item.sha256 === source.sha256 && item.bytes === source.bytes)) {
      throw Error('Demonstration crop or context is not frozen in preparation');
    }
  }
  const region = proof.clip, context = proof.context_clip;
  if (!region || !context || metadata.width !== region.width || metadata.height !== region.height
    || region.width <= 0 || region.height <= 0 || region.x < context.x || region.y < context.y
    || region.x + region.width > context.x + context.width || region.y + region.height > context.y + context.height) {
    throw Error('Demonstration crop geometry differs from the recorded original');
  }
  const scale = Math.min(828 / region.width, 550 / region.height);
  // This bounds pathological tiny crops. It is not a substitute for inspecting
  // the actual scene; a high scale is explicitly recorded for that review.
  if (scale > 12) throw Error('Demonstration crop is too small; capture the native UI at a larger size');
  return {origin: 'demonstration', width: region.width, height: region.height,
    displayScale: scale, displayWidth: region.width * scale, displayHeight: region.height * scale,
    requiresSceneLegibilityReview: true, highUpscale: scale > 4};
}

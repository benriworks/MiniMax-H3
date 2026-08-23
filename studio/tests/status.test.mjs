import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeStatus } from '../.test-dist/status.js';

test('compound production gates retain pass and blocker semantics', () => {
  assert.equal(normalizeStatus('master_visual_safe_area_pass'), 'succeeded');
  assert.equal(normalizeStatus('review_pass'), 'succeeded');
  assert.equal(normalizeStatus('not_pass'), 'failed');
  assert.equal(normalizeStatus('not_passed'), 'failed');
  assert.equal(normalizeStatus('did_not_pass'), 'failed');
  assert.equal(normalizeStatus('cut03_needs_improvement'), 'blocked');
  assert.equal(normalizeStatus('blocked_pending_rights_review'), 'blocked');
  assert.equal(normalizeStatus('interrupted'), 'cancelled');
  assert.equal(normalizeStatus('process_interrupted'), 'cancelled');
});

await import('./narration.test.mjs');

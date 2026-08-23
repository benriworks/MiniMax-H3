import type { StudioStatus } from './types';

export const normalizeStatus = (value: unknown): StudioStatus => {
  const status = (typeof value === 'string' || typeof value === 'number' ? String(value) : 'unknown')
    .toLowerCase()
    .replaceAll('-', '_')
    .replaceAll(' ', '_');
  if (status.includes('blocked') || status.includes('awaiting') || status.includes('needs_review') || status.includes('pending_rights')) return 'blocked';
  if (status.includes('needs_') || status.includes('not_clear') || status.includes('unverified')) return 'blocked';
  if (status.includes('fail') || status.includes('error')) return 'failed';
  if (status.includes('reject') || status.includes('declin')) return 'rejected';
  if (status.includes('cancel') || status.includes('interrupt') || status === 'aborted' || status === 'stopped') return 'cancelled';
  if (status.includes('running') || status.includes('processing') || status.includes('in_progress')) return 'running';
  if (status.includes('approved')) return 'approved';
  if (/(^|_)(?:not|no)_pass(?:ed)?($|_)/.test(status) || status.includes('did_not_pass')) return 'failed';
  if (/(^|_)pass(?:ed)?($|_)/.test(status)) return 'succeeded';
  if (status.includes('complete') || status.includes('success') || status.includes('master_pass') || status.includes('reviewed')) return 'succeeded';
  if (status.includes('pending')) return 'pending';
  if (['queued', 'created', 'new', 'waiting', 'not_started'].includes(status)) return 'pending';
  if (['processing', 'in_progress', 'active', 'working'].includes(status)) return 'running';
  if (['complete', 'completed', 'success', 'pass', 'passed', 'done'].includes(status)) return 'succeeded';
  if (['error', 'errored'].includes(status)) return 'failed';
  if (['needs_review', 'needs_approval', 'on_hold'].includes(status)) return 'blocked';
  if (['approve', 'accepted'].includes(status)) return 'approved';
  if (['reject', 'declined'].includes(status)) return 'rejected';
  if (['canceled'].includes(status)) return 'cancelled';
  if (status === 'ready') return 'pending';
  const allowed: StudioStatus[] = ['pending', 'running', 'succeeded', 'failed', 'blocked', 'approved', 'rejected', 'cancelled', 'unknown'];
  return allowed.includes(status as StudioStatus) ? (status as StudioStatus) : 'unknown';
};

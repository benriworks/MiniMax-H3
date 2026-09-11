export type StillSource = { kind: 'web'; url: string; viewport: 'desktop' | 'mobile'; area: 'viewport' | 'fullpage' | 'element'; selector: string } | { kind: 'artifact'; artifact_id: string } | { kind: 'claude'; selection_token?: string } | { kind: 'terminal'; selection_token?: string };
export interface StillImage {
  id: string; job_id: string; title: string; memo: string; revision: number; parent_id: string | null;
  source: StillSource; created_at: string; status: string; ready: boolean; image_url?: string;
  media: { width: number; height: number; bytes: number; sha256: string } | null;
  history?: { revision: number; title: string; memo: string; created_at: string }[];
  plan_capture?: PlanCaptureContext;
}
export interface PlanCaptureContext { plan_id: string; plan_revision: number; step_id: string }
export interface StillRequest { id: string; title: string; memo: string; parent_id: string | null; source: StillSource; confirm_capture: boolean }
export const stillId = (prefix: 'still' | 'edit') => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
export const STILL_PENDING_KEY = 'studio.still-library.pending.v1';

export class StillApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}
async function response(path: string, body?: unknown, signal?: AbortSignal) {
  const result = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } }), signal });
  if (!result.ok) {
    const value = await result.json().catch(() => ({}));
    throw new StillApiError(value?.error?.message || '静止画ライブラリに接続できませんでした。', result.status);
  }
  return result;
}
async function json<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> { return (await response(path, body, signal)).json(); }
export { json as stillJson, response as stillResponse };
export const stillApi = {
  list: (offset = 0, signal?: AbortSignal) => json<{ items: StillImage[]; total: number }>(`/api/stills?limit=60&offset=${offset}`, undefined, signal),
  sources: (signal?: AbortSignal) => json<{ items: { id: string; name: string }[] }>('/api/stills/sources', undefined, signal),
  get: (id: string, signal?: AbortSignal) => json<StillImage>(`/api/stills/${encodeURIComponent(id)}`, undefined, signal),
  submit: (body: StillRequest) => json<StillImage>('/api/stills', body),
  edit: (item: StillImage, title: string, memo: string, operationId: string) => json<StillImage>(`/api/stills/${item.id}/edit`, { operation_id: operationId, expected_revision: item.revision, title, memo }),
  export: async (item: StillImage) => (await response(`/api/stills/${item.id}/export`, { expected_revision: item.revision, confirm_privacy_review: true })).blob(),
};

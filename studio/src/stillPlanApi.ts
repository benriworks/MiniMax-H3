import { stillJson, stillResponse, type StillImage, type StillSource } from './stillLibraryApi';

export interface PlanStep { id: string; title: string; memo: string; source: StillSource; image: { id: string; revision: number } | null }
export interface StillPlan { id: string; revision: number; title: string; steps: PlanStep[]; history?: { revision: number; title: string; created_at: string }[] }
export interface PackPreview { snapshot: { plan_id: string; revision: number; title: string; steps: { id: string; order: number; title: string; memo: string; image: Pick<StillImage, 'id' | 'revision' | 'title' | 'memo' | 'media'> | null }[] }; review_digest: string; ready: boolean; blockers: string[]; total_bytes: number }
export const planId = (prefix: 'plan' | 'planedit' | 'step') => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
export const planSource = (source: StillSource): StillSource => source.kind === 'claude' || source.kind === 'terminal' ? { kind: source.kind } : { ...source };
export const planApi = {
  list: () => stillJson<{ items: Pick<StillPlan, 'id' | 'revision' | 'title'>[] }>('/api/still-plans'),
  get: (id: string) => stillJson<StillPlan>(`/api/still-plans/${id}`),
  save: (plan: StillPlan, operationId: string) => stillJson<StillPlan>(`/api/still-plans/${plan.id}`, { operation_id: operationId, expected_revision: plan.revision, title: plan.title, steps: plan.steps }),
  preview: (id: string) => stillJson<PackPreview>(`/api/still-plans/${id}/preview`),
  export: async (preview: PackPreview) => (await stillResponse(`/api/still-plans/${preview.snapshot.plan_id}/export`, { expected_revision: preview.snapshot.revision, review_digest: preview.review_digest, confirm_privacy_review: true })).blob(),
};

import { stillJson, stillResponse, type StillImage, type StillSource, type PlanCaptureContext } from './stillLibraryApi';

export interface PlanStep { id: string; title: string; memo: string; source: StillSource; image: { id: string; revision: number } | null }
export interface StillPlan { id: string; revision: number; title: string; steps: PlanStep[]; history?: { revision: number; title: string; created_at: string }[] }
export type ComparedImage = Pick<StillImage, 'id' | 'revision' | 'title' | 'memo' | 'media' | 'image_url'>;
export interface CaptureComparison { snapshot: { plan_id: string; plan_title: string; base_revision: number; current_revision: number; step_id: string; step_title: string; before: ComparedImage | null; after: ComparedImage | null }; review_digest: string; ready: boolean; adopted: boolean; blockers: string[] }
export interface AdoptionRequest { operation_id: string; expected_revision: number; review_digest: string; confirm_adoption: true }
export interface PackPreview { snapshot: { plan_id: string; revision: number; title: string; steps: { id: string; order: number; title: string; memo: string; image: Pick<StillImage, 'id' | 'revision' | 'title' | 'memo' | 'media'> | null }[] }; review_digest: string; ready: boolean; blockers: string[]; total_bytes: number }
export const planId = (prefix: 'plan' | 'planedit' | 'step') => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
export const planSource = (source: StillSource): StillSource => source.kind === 'claude' || source.kind === 'terminal' ? { kind: source.kind } : { ...source };
export const planApi = {
  list: () => stillJson<{ items: Pick<StillPlan, 'id' | 'revision' | 'title'>[] }>('/api/still-plans'),
  get: (id: string) => stillJson<StillPlan>(`/api/still-plans/${id}`),
  capture: (context: PlanCaptureContext, id: string, token: string | undefined, consent: boolean) => stillJson<StillImage>(`/api/still-plans/${context.plan_id}/steps/${context.step_id}/capture`, { id, expected_revision: context.plan_revision, selection_token: token ?? null, confirm_capture: consent }),
  compare: (context: PlanCaptureContext, id: string) => stillJson<CaptureComparison>(`/api/still-plans/${context.plan_id}/captures/${id}`),
  adopt: (context: PlanCaptureContext, id: string, request: AdoptionRequest) => stillJson<StillPlan>(`/api/still-plans/${context.plan_id}/captures/${id}/adopt`, request),
  save: (plan: StillPlan, operationId: string) => stillJson<StillPlan>(`/api/still-plans/${plan.id}`, { operation_id: operationId, expected_revision: plan.revision, title: plan.title, steps: plan.steps }),
  preview: (id: string) => stillJson<PackPreview>(`/api/still-plans/${id}/preview`),
  export: async (preview: PackPreview) => (await stillResponse(`/api/still-plans/${preview.snapshot.plan_id}/export`, { expected_revision: preview.snapshot.revision, review_digest: preview.review_digest, confirm_privacy_review: true })).blob(),
};

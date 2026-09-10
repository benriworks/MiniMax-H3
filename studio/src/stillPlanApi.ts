import { stillJson, type StillSource } from './stillLibraryApi';

export interface PlanStep { id: string; title: string; memo: string; source: StillSource; image: { id: string; revision: number } | null }
export interface StillPlan { id: string; revision: number; title: string; steps: PlanStep[]; history?: { revision: number; title: string; created_at: string }[] }
export const planId = (prefix: 'plan' | 'planedit' | 'step') => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
export const planSource = (source: StillSource): StillSource => source.kind === 'claude' || source.kind === 'terminal' ? { kind: source.kind } : { ...source };
export const planApi = {
  list: () => stillJson<{ items: Pick<StillPlan, 'id' | 'revision' | 'title'>[] }>('/api/still-plans'),
  get: (id: string) => stillJson<StillPlan>(`/api/still-plans/${id}`),
  save: (plan: StillPlan, operationId: string) => stillJson<StillPlan>(`/api/still-plans/${plan.id}`, { operation_id: operationId, expected_revision: plan.revision, title: plan.title, steps: plan.steps }),
};

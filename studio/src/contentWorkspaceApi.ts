import { studioRequest } from './api';

export interface ContentSource {
  source_id: string;
  title: string;
  url: string;
  kind: 'official' | 'first_hand' | 'secondary';
  checked_at: string;
  published_at?: string;
  event_at?: string;
  conditions?: string;
}
export interface Research {
  research_id: string;
  summary: string;
  checked_at: string;
  sources: ContentSource[];
  unknowns?: string[];
}
export interface ContentAsset {
  asset_id: string;
  kind: string;
  visibility: string;
  path: string;
  sha256: string;
  bytes: number;
  version: number;
  caption?: string;
  alt?: string;
  parent_asset_id?: string;
  source_url?: string;
}
export interface ContentClaim {
  claim_id: string;
  text: string;
  basis: 'official' | 'tested' | 'hypothesis';
  checked_at: string;
  source_ids: string[];
  asset_ids?: string[];
  needs_review?: boolean;
}
export interface ContentScene {
  scene_id: string;
  purpose: string;
  narration: string;
  visual: string;
  duration_seconds: number;
  claim_ids?: string[];
  asset_ids?: string[];
  character_ids?: string[];
  character_action?: string;
  needs_review: boolean;
  review_reasons: string[];
}
export interface ContentEpisode {
  episode_id: string;
  title: string;
  overview: string;
  intended_message: string;
  duration_seconds: number;
  demo_idea: string;
  article_role: string;
  capture_plan: {
    status: string;
    route?: string;
    result?: string;
    checked_at?: string;
    shots: { shot_id: string; purpose: string; asset_id?: string }[];
  };
  storyboard: ContentScene[];
}
export interface ContentProposal {
  proposal_id: string;
  count_reason: string;
  episodes: ContentEpisode[];
  based_on_research: string[];
}
export interface ContentCharacter {
  character_id: string;
  version: number;
  name: string;
  persona: string;
  role: string;
  clothing: string;
  voice: string;
  continuity: string;
  reference_asset_id: string;
  approval: { scope: string; accepted_at: string } | null;
}
export interface ContentProject {
  capture_inspections: {
    inspection_id: string;
    target_feature: string;
    status: string;
    result?: string;
    checked_at?: string;
  }[];
  content_project_id: string;
  title: string;
  revision: number;
  phase: string;
  archived: boolean;
  updated_at: string;
  request: { topic: string; audience: string; format: string };
  research: Research[];
  proposals: ContentProposal[];
  feedback: { feedback_id: string; proposal_id: string; text: string; interpretation: string }[];
  accepted_proposal: { proposal_id: string; feedback_id: string } | null;
  episodes: ContentEpisode[];
  retired_episodes: ContentEpisode[];
  claims: ContentClaim[];
  assets: ContentAsset[];
  characters: ContentCharacter[];
  article: {
    slug?: string;
    sections: { section_id: string; title: string; needs_review?: boolean }[];
  };
}
export interface ContentChecks {
  ready_for_production: boolean;
  blockers: string[];
  warnings: string[];
  technical_verified: false;
  human_reviewed: false;
  published: false;
}
export interface ContentResponse {
  project: ContentProject;
  checks: ContentChecks;
  history?: { revision: number; action: string; created_at: string }[];
}
export type ContentSummary = Pick<
  ContentProject,
  'content_project_id' | 'title' | 'revision' | 'phase' | 'archived' | 'updated_at'
>;
export const contentOperationId = () => `op_${crypto.randomUUID().replaceAll('-', '')}`;
export const contentEndpoint = (id: string) => `/api/content-projects/${encodeURIComponent(id)}`;
export const contentImageUrl = (id: string, asset: ContentAsset) =>
  `${contentEndpoint(id)}/assets/${encodeURIComponent(asset.asset_id)}?version=${asset.version}`;
export function contentDiff(previous: ContentProject, current: ContentProject): string[] {
  const fields: [keyof ContentProject, string][] = [
    ['research', '調査'],
    ['proposals', '企画案'],
    ['feedback', '返答'],
    ['accepted_proposal', '採用構成'],
    ['episodes', '撮影・絵コンテ'],
    ['claims', '主張・根拠'],
    ['assets', '素材'],
    ['characters', '人物'],
    ['article', '記事への接続'],
    ['archived', '保管状態'],
  ];
  return fields
    .filter(([key]) => JSON.stringify(previous[key]) !== JSON.stringify(current[key]))
    .map(([, label]) => label);
}
export const contentApi = {
  list: () => studioRequest<{ items: ContentSummary[] }>('/api/content-projects'),
  get: (id: string, revision?: number) =>
    studioRequest<ContentResponse>(
      `${contentEndpoint(id)}${revision === undefined ? '' : `?revision=${revision}`}`,
    ),
  create: (topic: string, operationId = contentOperationId()) =>
    studioRequest<ContentResponse>('/api/content-projects', {
      method: 'POST',
      body: JSON.stringify({
        content_project_id: `CONTENT_${crypto.randomUUID().replaceAll('-', '')}`,
        operation_id: operationId,
        title: topic,
        topic,
      }),
    }),
  apply: (
    project: ContentProject,
    action: string,
    data: unknown,
    operationId = contentOperationId(),
  ) =>
    studioRequest<ContentResponse>(`${contentEndpoint(project.content_project_id)}/${action}`, {
      method: 'POST',
      body: JSON.stringify({
        operation_id: operationId,
        expected_revision: project.revision,
        data,
      }),
    }),
};

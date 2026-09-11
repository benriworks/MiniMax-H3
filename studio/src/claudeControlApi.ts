import { stillJson } from './stillLibraryApi';

export type ControlOperation = 'launch' | 'tab' | 'input';
export interface ClaudeControlTarget {
  id: string; kind: 'tab' | 'input'; label: string; characters: number;
  position: { x: number; y: number; width: number; height: number };
  method: 'value' | 'legacy_value' | 'selection' | 'invoke';
}
export interface ControlDiagnostics {
  engine: 'uia3'; view: 'raw'; inspected_nodes: number; documents: number; hidden_nodes: number;
  unsupported_editors: number; supported_inputs: number; supported_tabs: number;
}
export interface ControlInspection { inspection_token: string; expires_in_seconds: number; available: boolean; reason: string | null; controls: ClaudeControlTarget[]; diagnostics: ControlDiagnostics }
export interface ControlReceipt { id: string; operation: ControlOperation; job_id: string; characters: number; created_at: string; status: string; outcome: 'processing' | 'verified' | 'review_required'; message_sent: false }
export interface ControlRequest { id: string; operation: ControlOperation; inspection_token: string | null; target_id: string | null; text: string | null; allow_replace: boolean; confirm_action: boolean }
export const CONTROL_PENDING_KEY = 'studio.claude-control.pending.v1';
export const controlApi = {
  list: (signal?: AbortSignal) => stillJson<{ available: boolean; items: ControlReceipt[] }>('/api/claude-control', undefined, signal),
  get: (id: string, signal?: AbortSignal) => stillJson<ControlReceipt>(`/api/claude-control/${encodeURIComponent(id)}`, undefined, signal),
  inspect: (selection_token: string) => stillJson<ControlInspection>('/api/claude-control/inspect', { selection_token, confirm_inspect: true }),
  submit: (body: ControlRequest) => stillJson<ControlReceipt>('/api/claude-control/actions', body),
};

import { useCallback, useMemo, useRef, useState, type FormEvent } from 'react';

import { api, REVIEW_ARTIFACT_PATTERN } from './api';
import type {
  Artifact,
  ProductionDetail,
  ReviewCategory,
  ReviewDecision,
  ReviewGate,
  ReviewGates,
  ReviewThread,
} from './types';


const CATEGORY_LABELS: Record<ReviewCategory, string> = {
  creative: '表現',
  rights: '権利',
  public_release: '公開可否',
};

const DECISION_LABELS: Record<ReviewDecision | ReviewGate['decision'], string> = {
  pending: '未判定',
  approved: '承認',
  changes_required: '要修正',
  not_applicable: '対象外',
};

const formatTimestamp = (value: string): string => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value || '—' : date.toLocaleString('ja-JP');
};

const formatTimecode = (milliseconds: number): string => {
  const totalSeconds = Math.max(0, milliseconds) / 1_000;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds - minutes * 60;
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(3).padStart(6, '0')}`;
};

const newIdempotencyKey = (): string => {
  const random = globalThis.crypto?.randomUUID?.().replaceAll('-', '');
  return `review-${random ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}`;
};

const cutIdForArtifact = (artifactId: string): string => (
  REVIEW_ARTIFACT_PATTERN.test(artifactId) ? `cut_${artifactId.slice(4)}` : ''
);

function ReviewGateCard({ category, gate }: { category: ReviewCategory; gate: ReviewGate }) {
  return (
    <article className={`review-gate review-decision-${gate.decision}`}>
      <span>{CATEGORY_LABELS[category]}</span>
      <strong>{DECISION_LABELS[gate.decision]}</strong>
      <small>open {gate.openCount} / resolved {gate.resolvedCount}</small>
    </article>
  );
}

interface ReviewCardProps {
  artifact?: Artifact;
  busyOperation?: string;
  review: ReviewThread;
  onDecision: (review: ReviewThread, decision: Exclude<ReviewDecision, 'pending'>) => void;
  onPlan: (review: ReviewThread) => void;
  onResolve: (review: ReviewThread) => void;
}

function ReviewCard({ artifact, busyOperation, review, onDecision, onPlan, onResolve }: ReviewCardProps) {
  const busy = busyOperation !== undefined;
  const latestPlan = review.revisionPlans.at(-1);
  return (
    <article className={`review-card review-status-${review.status}`}>
      <header>
        <div>
          <span className="section-kicker">{CATEGORY_LABELS[review.category]} · {formatTimecode(review.identity.timecodeMs)}</span>
          <h4>{artifact?.name ?? review.identity.artifactId}</h4>
        </div>
        <span className={`review-state review-state-${review.status}`}>{review.status === 'open' ? 'OPEN' : 'RESOLVED'}</span>
      </header>
      <p className="review-body">{review.body}</p>
      <dl className="review-identity-grid">
        <div><dt>cut</dt><dd>{review.identity.cutId}</dd></div>
        <div><dt>Run</dt><dd>{review.identity.runId}</dd></div>
        <div><dt>revision</dt><dd>{review.identity.revisionId}</dd></div>
        <div><dt>作成</dt><dd>{formatTimestamp(review.createdAt)} · {review.actor}</dd></div>
      </dl>
      <div className="review-decision-row">
        <span>判定 <strong>{DECISION_LABELS[review.decision]}</strong></span>
        <button className="button button-ghost" type="button" disabled={busy} onClick={() => onDecision(review, 'approved')}>承認</button>
        <button className="button button-danger" type="button" disabled={busy} onClick={() => onDecision(review, 'changes_required')}>要修正</button>
        <button className="button button-ghost" type="button" disabled={busy} onClick={() => onDecision(review, 'not_applicable')}>対象外</button>
      </div>
      <div className="button-row review-action-row">
        <button className="button button-secondary" type="button" disabled={busy || review.status !== 'open'} onClick={() => onPlan(review)}>このcutの修正planを作成</button>
        <button className="button button-primary" type="button" disabled={busy || review.status !== 'open'} onClick={() => onResolve(review)}>解決にする</button>
      </div>
      {latestPlan && (
        <div className="review-plan-notice" role="status">
          <strong>plan作成済み・render未実行</strong>
          <span>{latestPlan.id}</span>
          <small>対象は {latestPlan.exactCutIdentity.cutId} のみ。他cutはexact artifact再利用。M4 adapter: {latestPlan.execution.status}</small>
        </div>
      )}
      <details className="review-history">
        <summary>監査履歴 {review.actions.length}件</summary>
        <ol>
          {review.actions.map((action) => (
            <li key={action.id}>
              <span>{formatTimestamp(action.createdAt)}</span>
              <strong>{action.type}</strong>
              <small>{action.actor}{action.note ? ` · ${action.note}` : ''}</small>
            </li>
          ))}
        </ol>
      </details>
    </article>
  );
}

export function ReviewPanel({ detail, onReload }: { detail: ProductionDetail; onReload: () => Promise<void> }) {
  const eligibleArtifacts = useMemo(
    () => detail.artifacts.filter((artifact) => REVIEW_ARTIFACT_PATTERN.test(artifact.id)),
    [detail.artifacts],
  );
  const eligibleRuns = useMemo(
    () => detail.runs.filter((run) => run.revisionId),
    [detail.runs],
  );
  const artifactById = useMemo(
    () => new Map(eligibleArtifacts.map((artifact) => [artifact.id, artifact])),
    [eligibleArtifacts],
  );
  const [artifactId, setArtifactId] = useState(eligibleArtifacts[0]?.id ?? '');
  const [runId, setRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [timecodeSeconds, setTimecodeSeconds] = useState('0');
  const [category, setCategory] = useState<ReviewCategory>('creative');
  const [body, setBody] = useState('');
  const [actor, setActor] = useState('operator');
  const [submitting, setSubmitting] = useState(false);
  const [busyOperation, setBusyOperation] = useState<string>();
  const [message, setMessage] = useState<string>();
  const createKeyRef = useRef<string | undefined>(undefined);
  const actionKeysRef = useRef(new Map<string, string>());
  const selectedArtifact = artifactById.get(artifactId);
  const selectedRun = eligibleRuns.find((run) => run.id === runId);
  const cutId = cutIdForArtifact(selectedArtifact?.id ?? '');
  const timecodeMs = Math.round(Number(timecodeSeconds) * 1_000);
  const createErrors = [
    !selectedArtifact ? 'レビュー対象artifactを選択してください。' : '',
    !selectedRun?.revisionId ? 'revision付きRunを選択してください。' : '',
    !cutId ? 'exact cut identityを作成できません。' : '',
    !Number.isFinite(timecodeMs) || timecodeMs < 0 || timecodeMs > 86_400_000 ? '時刻は0〜86400秒で入力してください。' : '',
    !body.trim() || body !== body.trim() || body.length > 2_000 ? '指摘内容は前後空白なしの1〜2000文字で入力してください。' : '',
    !actor.trim() || actor !== actor.trim() || actor.length > 80 ? '担当者は前後空白なしの1〜80文字で入力してください。' : '',
  ].filter(Boolean);

  const resetCreateKey = useCallback(() => {
    createKeyRef.current = undefined;
  }, []);

  const submitReview = useCallback(async (event: FormEvent) => {
    event.preventDefault();
    if (submitting || createErrors.length > 0 || !selectedRun?.revisionId) return;
    const key = createKeyRef.current ?? newIdempotencyKey();
    createKeyRef.current = key;
    setSubmitting(true);
    setMessage(undefined);
    try {
      const result = await api.createReview(detail.id, {
        idempotencyKey: key,
        artifactId,
        revisionId: selectedRun.revisionId,
        runId: selectedRun.id,
        cutId,
        timecodeMs,
        category,
        body,
        actor,
      });
      createKeyRef.current = undefined;
      setBody('');
      setMessage(result.deduplicated ? '同じレビュー要求を復元しました。' : '時刻付きレビューを記録しました。');
      await onReload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'レビューを記録できませんでした。');
    } finally {
      setSubmitting(false);
    }
  }, [actor, artifactId, body, category, createErrors.length, cutId, detail.id, onReload, selectedRun, submitting, timecodeMs]);

  const runReviewAction = useCallback(async (
    review: ReviewThread,
    operation: string,
    execute: (key: string) => Promise<unknown>,
  ) => {
    const scope = `${review.id}:${operation}`;
    const key = actionKeysRef.current.get(scope) ?? newIdempotencyKey();
    actionKeysRef.current.set(scope, key);
    setBusyOperation(scope);
    setMessage(undefined);
    try {
      await execute(key);
      actionKeysRef.current.delete(scope);
      setMessage('レビューの監査履歴を更新しました。');
      await onReload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'レビュー操作を完了できませんでした。');
    } finally {
      setBusyOperation(undefined);
    }
  }, [onReload]);

  const resolveReview = useCallback((review: ReviewThread) => {
    void runReviewAction(review, 'resolve', (key) => api.resolveReview(detail.id, review.id, key, actor, 'Studio UIで解決'));
  }, [actor, detail.id, runReviewAction]);

  const setDecision = useCallback((review: ReviewThread, decision: Exclude<ReviewDecision, 'pending'>) => {
    void runReviewAction(review, `decision-${decision}`, (key) => api.setReviewDecision(detail.id, review.id, key, actor, decision, 'Studio UIで判定'));
  }, [actor, detail.id, runReviewAction]);

  const createPlan = useCallback((review: ReviewThread) => {
    void runReviewAction(review, 'revision-plan', (key) => api.createReviewRevisionPlan(detail.id, review.id, key, actor));
  }, [actor, detail.id, runReviewAction]);

  return (
    <div className="review-layout">
      <section className="panel review-create-panel">
        <div className="panel-header">
          <div><span className="section-kicker">TIME-CODED REVIEW</span><h3>レビュー指摘を追加</h3></div>
          <span className="count-chip">open {detail.reviews.filter((review) => review.status === 'open').length}</span>
        </div>
        <p className="panel-lead">artifact・revision・Run・cut・時刻を固定して記録します。ファイルパスやsecretは契約に含めません。</p>
        <form onSubmit={submitReview}>
          <div className="review-form-grid">
            <label className="field"><span>artifact</span><select value={artifactId} onChange={(event) => { setArtifactId(event.target.value); resetCreateKey(); }} disabled={submitting}>{eligibleArtifacts.map((artifact) => <option key={artifact.id} value={artifact.id}>{artifact.name}</option>)}</select></label>
            <label className="field"><span>Run / revision</span><select value={runId} onChange={(event) => { setRunId(event.target.value); resetCreateKey(); }} disabled={submitting}>{eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.id} · {run.revisionId}</option>)}</select></label>
            <label className="field"><span>時刻（秒）</span><input type="number" min="0" max="86400" step="0.001" value={timecodeSeconds} onChange={(event) => { setTimecodeSeconds(event.target.value); resetCreateKey(); }} disabled={submitting} /></label>
            <label className="field"><span>判定区分</span><select value={category} onChange={(event) => { setCategory(event.target.value as ReviewCategory); resetCreateKey(); }} disabled={submitting}><option value="creative">表現</option><option value="rights">権利</option><option value="public_release">公開可否</option></select></label>
            <label className="field"><span>担当者</span><input value={actor} maxLength={80} onChange={(event) => { setActor(event.target.value); resetCreateKey(); actionKeysRef.current.clear(); }} disabled={submitting || busyOperation !== undefined} /></label>
            <div className="review-cut-preview"><span>exact cut</span><code>{cutId || '—'}</code></div>
          </div>
          <label className="field"><span>指摘内容</span><textarea rows={4} maxLength={2_000} value={body} onChange={(event) => { setBody(event.target.value); resetCreateKey(); }} disabled={submitting} placeholder="例：後半2秒の動きを増やし、視線は正面を維持する" /></label>
          {createErrors.length > 0 && <ul className="validation-list">{createErrors.map((error) => <li key={error}>{error}</li>)}</ul>}
          <div className="button-row review-submit-row"><button className="button button-primary" type="submit" disabled={submitting || busyOperation !== undefined || createErrors.length > 0}>{submitting ? '記録中…' : 'レビューを記録'}</button></div>
        </form>
        {message && <p className="review-message" role="status" aria-live="polite">{message}</p>}
      </section>

      <section className="review-gates" aria-label="レビュー判定ゲート">
        {(Object.keys(CATEGORY_LABELS) as ReviewCategory[]).map((key) => <ReviewGateCard key={key} category={key} gate={(detail.reviewGates as ReviewGates)[key]} />)}
      </section>

      <section className="review-list" aria-label="レビュー指摘一覧">
        {detail.reviews.length === 0 ? <div className="panel"><p className="muted">レビュー指摘はまだありません。</p></div> : detail.reviews.map((review) => (
          <ReviewCard
            key={review.id}
            artifact={artifactById.get(review.identity.artifactId)}
            busyOperation={busyOperation}
            review={review}
            onDecision={setDecision}
            onPlan={createPlan}
            onResolve={resolveReview}
          />
        ))}
      </section>
    </div>
  );
}

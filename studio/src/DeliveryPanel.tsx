import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  api,
  buildDeliveryPackageRequest,
  deliveryPackageResult,
  resolveDeliveryPackageSource,
  DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH,
  DELIVERY_PACKAGE_TITLE_MAX_LENGTH,
} from './api';
import type { Job, ProductionDetail, ReviewCategory, ReviewDecision } from './types';

const ACTIVE_JOB_STATUSES = new Set(['pending', 'running']);
const TERMINAL_JOB_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);
const DELIVERY_POLL_INTERVAL_MS = 2_000;

const REVIEW_GATES: Array<{ category: ReviewCategory; label: string }> = [
  { category: 'creative', label: '表現' },
  { category: 'rights', label: '権利' },
  { category: 'public_release', label: '公開' },
];

const REVIEW_DECISION_LABEL: Record<ReviewDecision, string> = {
  pending: '未判断',
  approved: '承認済み',
  changes_required: '変更が必要',
  not_applicable: '対象外',
};

const jobTimestamp = (job: Job): string => job.updatedAt ?? job.startedAt ?? '';

const newestDeliveryJob = (jobs: readonly Job[]): Job | undefined => [...jobs]
  .filter((job) => job.type === 'delivery_package')
  .sort((left, right) => jobTimestamp(right).localeCompare(jobTimestamp(left)))[0];

export function DeliveryPanel({
  detail,
  jobs,
  onReload,
}: {
  detail: ProductionDetail;
  jobs: Job[];
  onReload: () => Promise<void>;
}) {
  const [title, setTitle] = useState(detail.title);
  const [description, setDescription] = useState(
    detail.description?.trim() || `${detail.title}の公開用動画です。`,
  );
  const [submitting, setSubmitting] = useState(false);
  const [trackedJob, setTrackedJob] = useState<Job>();
  const [message, setMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string }>();
  const resolution = useMemo(
    () => resolveDeliveryPackageSource(detail, jobs),
    [detail, jobs],
  );
  const latestKnownJob = useMemo(() => newestDeliveryJob(jobs), [jobs]);
  const observedTrackedJob = trackedJob
    ? jobs.find((job) => job.id === trackedJob.id) ?? trackedJob
    : undefined;
  const currentJob = observedTrackedJob ?? latestKnownJob;
  const completed = currentJob ? deliveryPackageResult(currentJob) : undefined;
  const jobActive = currentJob ? ACTIVE_JOB_STATUSES.has(currentJob.status) : false;
  const metadataInvalid = (
    !title.trim()
    || title.trim().length > DELIVERY_PACKAGE_TITLE_MAX_LENGTH
    || !description.trim()
    || description.trim().length > DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH
  );

  useEffect(() => {
    if (!trackedJob) return;
    const observed = jobs.find((job) => job.id === trackedJob.id);
    if (observed && observed !== trackedJob) setTrackedJob(observed);
  }, [jobs, trackedJob]);

  useEffect(() => {
    if (!currentJob || !ACTIVE_JOB_STATUSES.has(currentJob.status)) return undefined;
    let active = true;
    let timer: number | undefined;
    const jobId = currentJob.id;
    const poll = async () => {
      try {
        const next = await api.job(jobId);
        if (!active) return;
        setTrackedJob(next);
        if (TERMINAL_JOB_STATUSES.has(next.status)) {
          setMessage(next.status === 'succeeded'
            ? { type: 'success', text: '納品パッケージを作成しました。ZIPを確認できます。' }
            : { type: 'error', text: next.message || `納品Jobは${next.status}で終了しました。` });
          await onReload();
          return;
        }
      } catch (error) {
        if (!active) return;
        setMessage({
          type: 'error',
          text: `納品Jobの確認に失敗しました。Jobは継続している可能性があります：${error instanceof Error ? error.message : '不明なエラー'}`,
        });
      }
      if (active) timer = window.setTimeout(() => void poll(), DELIVERY_POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(() => void poll(), DELIVERY_POLL_INTERVAL_MS);
    return () => {
      active = false;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [currentJob?.id, currentJob?.status, onReload]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!resolution.ready || submitting || jobActive) return;
    setSubmitting(true);
    setMessage({ type: 'info', text: '納品元の系統を固定して、ローカルでZIPを作成します。' });
    try {
      const body = buildDeliveryPackageRequest(
        resolution.source,
        title,
        description,
      );
      const job = await api.createDeliveryPackage(detail.id, body);
      setTrackedJob(job);
      setMessage({ type: 'info', text: `納品Job ${job.id} を投入しました。完了まで自動確認します。` });
    } catch (error) {
      setMessage({
        type: 'error',
        text: error instanceof Error ? error.message : '納品パッケージを作成できませんでした。',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="delivery-layout">
      <section className="panel delivery-main-panel">
        <div className="panel-header">
          <div><span className="section-kicker">DELIVERY PACKAGE</span><h3>納品パッケージ</h3></div>
          <span className={`delivery-readiness ${resolution.ready ? 'is-ready' : 'is-blocked'}`}>
            {resolution.ready ? '作成可能' : '素材未解決'}
          </span>
        </div>
        <p className="panel-lead">字幕あり・なし動画、SRT、サムネイル3枚、QC・監査資料を検証済みZIPにまとめます。外部送信や課金は行いません。</p>

        {resolution.ready ? (
          <div className="delivery-source" aria-label="納品元">
            <div><span>Run</span><code>{resolution.source.runId}</code></div>
            <div><span>元Job</span><code>{resolution.source.sourceJobId}</code></div>
            <div><span>成果物</span><strong>6件をexact lineageで確認</strong></div>
          </div>
        ) : (
          <div className="inline-message is-error" role="alert">{resolution.reason}</div>
        )}

        <form className="delivery-form" onSubmit={(event) => void submit(event)}>
          <label className="field" htmlFor="delivery-title">
            <span>公開タイトル</span>
            <input id="delivery-title" value={title} maxLength={DELIVERY_PACKAGE_TITLE_MAX_LENGTH} onChange={(event) => setTitle(event.target.value)} disabled={submitting || jobActive} required />
            <small className="field-help">{title.trim().length} / {DELIVERY_PACKAGE_TITLE_MAX_LENGTH}文字</small>
          </label>
          <label className="field" htmlFor="delivery-description">
            <span>説明文</span>
            <textarea id="delivery-description" value={description} maxLength={DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH} rows={7} onChange={(event) => setDescription(event.target.value)} disabled={submitting || jobActive} required />
            <small className="field-help">{description.trim().length} / {DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH}文字。ZIP内のpublication.jsonへ保存します。</small>
          </label>
          <div className="button-row">
            <button className="button button-primary" type="submit" disabled={!resolution.ready || metadataInvalid || submitting || jobActive}>
              {submitting ? '投入中…' : jobActive ? '作成中…' : '納品ZIPを作成'}
            </button>
          </div>
        </form>

        {currentJob && (
          <div className="delivery-job" aria-live="polite">
            <span>Job</span><code>{currentJob.id}</code><strong>{currentJob.status}</strong>
          </div>
        )}
        {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</div>}
        {currentJob?.status === 'succeeded' && !completed && (
          <div className="inline-message is-error" role="alert">完了応答のidentityを検証できないため、ダウンロードを表示していません。</div>
        )}
        {completed && (
          <div className="delivery-result">
            <div>
              <span className="section-kicker">VERIFIED OUTPUT</span>
              <h4>納品ZIPが完成しました</h4>
              <p>{completed.filesIncluded}ファイル · サムネイル{completed.thumbnailCount}枚 · {completed.cacheHit ? '検証済みcacheを再利用' : '新規作成'}</p>
            </div>
            <a className="button button-primary" href={completed.artifact.url}>ZIPをダウンロード</a>
            <small>SHA256 sidecar: <code>{completed.sha256Sidecar}</code></small>
          </div>
        )}
      </section>

      <aside className="panel delivery-gates-panel">
        <div className="panel-header"><div><span className="section-kicker">REVIEW GATES</span><h3>レビュー判定</h3></div></div>
        <p className="panel-lead">判断状況を確認できます。未承認でも確認用Deliveryの作成自体は止めません。</p>
        <div className="delivery-gates">
          {REVIEW_GATES.map(({ category, label }) => {
            const gate = detail.reviewGates[category];
            return (
              <div className={`delivery-gate is-${gate.decision}`} key={category}>
                <span>{label}</span>
                <strong>{REVIEW_DECISION_LABEL[gate.decision]}</strong>
                <small>レビュー {gate.reviewCount}件 · 未解決 {gate.openCount}件</small>
              </div>
            );
          })}
        </div>
        <div className="delivery-safety-note">
          <strong>この画面では公開しません</strong>
          <p>YouTube等への外部公開は別の明示操作として追加されます。</p>
        </div>
      </aside>
    </div>
  );
}

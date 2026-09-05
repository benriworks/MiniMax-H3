import { Fragment, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  api,
  buildDeliveryPackageRequest,
  deliveryPackageResult,
  resolveDeliveryPackageSource,
  DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH,
  DELIVERY_PACKAGE_TITLE_MAX_LENGTH,
} from './api';
import type { Job, ProductionDetail, ReviewCategory, ReviewDecision } from './types';
import {
  buildManualPublicationText,
  compareZipMetadata,
  manualPublicationFileName,
  manualPublicationVideos,
  normalizeManualPublicationMetadata,
  zipMetadataSnapshot,
  MANUAL_PUBLICATION_TAGS_MAX_LENGTH,
  ZIP_METADATA_MESSAGES,
  type ZipMetadataSnapshot,
} from './manualPublication';
import './manualPublication.css';

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
    detail.description?.trim() || '',
  );
  const [tags, setTags] = useState('');
  const [zipSnapshots, setZipSnapshots] = useState<Record<string, ZipMetadataSnapshot>>({});
  const [textExport, setTextExport] = useState<{ text: string; fileName: string }>();
  const [copyFallback, setCopyFallback] = useState(false);
  const fallbackRef = useRef<HTMLTextAreaElement>(null);
  const productionRef = useRef(detail.id);
  productionRef.current = detail.id;
  const [submitting, setSubmitting] = useState(false);
  const [trackedJob, setTrackedJob] = useState<Job>();
  const [message, setMessage] = useState<{ type: 'info' | 'success' | 'error'; text: string }>();
  const resolution = useMemo(
    () => resolveDeliveryPackageSource(detail, jobs),
    [detail, jobs],
  );
  const latestKnownJob = useMemo(() => newestDeliveryJob(jobs.filter((job) => job.productionId === detail.id)), [jobs, detail.id]);
  const observedTrackedJob = trackedJob?.productionId === detail.id
    ? jobs.find((job) => job.id === trackedJob.id) ?? trackedJob
    : undefined;
  const currentJob = observedTrackedJob ?? latestKnownJob;
  const completedJob = currentJob && deliveryPackageResult(currentJob) ? currentJob
    : newestDeliveryJob(jobs.filter((job) => job.productionId === detail.id && Boolean(deliveryPackageResult(job))));
  const completed = completedJob ? deliveryPackageResult(completedJob) : undefined;
  const jobActive = currentJob ? ACTIVE_JOB_STATUSES.has(currentJob.status) : false;
  const metadataInvalid = (
    !title.trim()
    || title.trim().length > DELIVERY_PACKAGE_TITLE_MAX_LENGTH
    || !description.trim()
    || description.trim().length > DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH
  );
  const videos = useMemo(() => resolution.ready
    ? manualPublicationVideos(resolution.source, detail.artifacts) : [], [resolution, detail.artifacts]);
  const publication = useMemo(() => {
    try { return { metadata: normalizeManualPublicationMetadata(title, description, tags), error: undefined }; }
    catch (error) { return { metadata: undefined, error: error instanceof Error ? error.message : '投稿情報を確認してください。' }; }
  }, [title, description, tags]);
  const zipComparison = resolution.ready
    ? compareZipMetadata(zipMetadataSnapshot(detail.id, resolution.source, { title, description }), completed ? completedJob?.id : undefined, zipSnapshots)
    : completed ? 'unknown' : 'not_created';

  useEffect(() => {
    setTitle(detail.title);
    setDescription(detail.description?.trim() || '');
    setTags('');
    setSubmitting(false);
    setTrackedJob(undefined);
    setZipSnapshots({});
    setTextExport(undefined);
    setCopyFallback(false);
    setMessage(undefined);
  // A different production starts a new form; refreshes must preserve edits.
  }, [detail.id]);

  useEffect(() => {
    if (copyFallback && textExport) {
      fallbackRef.current?.focus();
      fallbackRef.current?.select();
    }
  }, [copyFallback, textExport]);

  useEffect(() => {
    if (!trackedJob) return;
    const observed = jobs.find((job) => job.id === trackedJob.id);
    if (observed && observed !== trackedJob) setTrackedJob(observed);
  }, [jobs, trackedJob]);

  // The global job refresh may observe completion before this panel's timer.
  // Derive terminal feedback from either path so stale "作成しています" never wins.
  useEffect(() => {
    if (!currentJob || !TERMINAL_JOB_STATUSES.has(currentJob.status)) return;
    setMessage(currentJob.status === 'succeeded'
      ? { type: 'success', text: '納品処理が完了しました。検証済みZIPの表示を確認してください。' }
      : { type: 'error', text: `納品ZIPの作成は${currentJob.status === 'cancelled' ? '停止' : '失敗'}しました。${currentJob.message || '処理記録を確認してから再試行してください。'}` });
  }, [currentJob?.id, currentJob?.status, currentJob?.message]);

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
    setMessage({ type: 'info', text: '選択した動画と投稿情報を納品ZIPにまとめます。' });
    try {
      const body = buildDeliveryPackageRequest(
        resolution.source,
        title,
        description,
      );
      const job = await api.createDeliveryPackage(detail.id, body);
      if (productionRef.current !== detail.id) return;
      setZipSnapshots((current) => ({ ...current, [job.id]: zipMetadataSnapshot(detail.id, resolution.source, body.metadata) }));
      setTrackedJob(job);
      setMessage({ type: 'info', text: '納品ZIPを作成しています。完了するとダウンロードできます。' });
    } catch (error) {
      if (productionRef.current !== detail.id) return;
      setMessage({
        type: 'error',
        text: error instanceof Error ? error.message : '納品パッケージを作成できませんでした。',
      });
    } finally {
      if (productionRef.current === detail.id) setSubmitting(false);
    }
  };

  const exportPublication = async (action: 'copy' | 'download') => {
    if (!resolution.ready || !publication.metadata || videos.length !== 2) return;
    try {
      const createdAt = new Date().toISOString();
      const text = buildManualPublicationText({ productionId: detail.id, source: resolution.source,
        metadata: publication.metadata, videos, createdAt, zipComparison });
      const fileName = manualPublicationFileName(publication.metadata.title, createdAt);
      setTextExport({ text, fileName });
      setCopyFallback(false);
      if (action === 'copy') {
        try {
          if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable');
          await navigator.clipboard.writeText(text);
          if (productionRef.current !== detail.id) return;
          setMessage({ type: 'success', text: '現在の投稿情報をコピーしました。' });
        } catch {
          if (productionRef.current !== detail.id) return;
          setCopyFallback(true);
          setMessage({ type: 'info', text: '自動コピーを利用できません。下のテキストを選択してコピーしてください。' });
        }
      } else {
        const url = URL.createObjectURL(new Blob(['\uFEFF', text], { type: 'text/plain;charset=utf-8' }));
        const link = document.createElement('a');
        try {
          link.href = url;
          link.download = fileName;
          document.body.appendChild(link);
          link.click();
        } finally {
          link.remove();
          // Keep the URL alive until the browser has accepted the download.
          window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
        }
        setMessage({ type: 'success', text: '現在の投稿情報をUTF-8テキストとして保存しました。' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '投稿情報を出力できませんでした。' });
    }
  };

  return (
    <div className="delivery-layout">
      <section className="panel delivery-main-panel">
        <div className="panel-header">
          <div><span className="section-kicker">MANUAL PUBLICATION</span><h3>動画と投稿情報を取り出す</h3></div>
          <span className={`delivery-readiness ${resolution.ready ? 'is-ready' : 'is-blocked'}`}>
            {resolution.ready ? '完成動画あり' : '動画の完成待ち'}
          </span>
        </div>
        <p className="panel-lead">動画を保存し、タイトル・説明文・タグをYouTube Studioへ手動で貼り付けられます。制作記録を含む納品ZIPも作成できます。</p>

        {resolution.ready ? (
          <div aria-label="投稿用動画">
            <div className="manual-publication-videos">
              {videos.map((video) => (
                <article className="manual-publication-video" key={video.id}>
                  <h4>{video.label}</h4>
                  <video controls preload="metadata" src={video.url} aria-label={`${video.label}の完成動画`} />
                  <a className="button button-secondary" href={video.url} download={video.fileName}>{video.label}動画を保存</a>
                </article>
              ))}
            </div>
            {videos.length !== 2 && <p className="inline-message is-error" role="alert">投稿用動画の情報を確認できません。制作を再読み込みしてください。</p>}
            <p className="field-help">「字幕なし」は読み上げ字幕を焼き込まない版です。編集で付けた大見出しは残ります。文字をすべて消すには編集内容の変更と再作成が必要です。</p>
            <details className="manual-publication-records">
              <summary>制作記録・ファイル情報</summary>
              <dl>
                <dt>制作ID</dt><dd><code>{detail.id}</code></dd>
                <dt>Run</dt><dd><code>{resolution.source.runId}</code></dd>
                <dt>元Job</dt><dd><code>{resolution.source.sourceJobId}</code></dd>
                {videos.map((video) => <Fragment key={video.id}><dt>{video.label}</dt><dd><code>{video.id}</code><br /><code>SHA-256: {video.sha256}</code><br />{(video.sizeBytes / 1024 / 1024).toFixed(1)} MB{video.durationSeconds ? ` · ${video.durationSeconds}秒` : ''}{video.width && video.height ? ` · ${video.width} × ${video.height}` : ''}</dd></Fragment>)}
              </dl>
            </details>
          </div>
        ) : (
          <div className="inline-message is-error" role="alert">{resolution.reason}</div>
        )}

        <form className="delivery-form" onSubmit={(event) => void submit(event)}>
          <label className="field" htmlFor="delivery-title">
            <span>タイトル</span>
            <input id="delivery-title" value={title} maxLength={DELIVERY_PACKAGE_TITLE_MAX_LENGTH} onChange={(event) => setTitle(event.target.value)} disabled={submitting || jobActive} required />
            <small className="field-help">{title.trim().length} / {DELIVERY_PACKAGE_TITLE_MAX_LENGTH}文字</small>
          </label>
          <label className="field" htmlFor="delivery-description">
            <span>説明文</span>
            <textarea id="delivery-description" value={description} maxLength={DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH} rows={7} onChange={(event) => setDescription(event.target.value)} disabled={submitting || jobActive} required />
            <small className="field-help">{description.trim().length} / {DELIVERY_PACKAGE_DESCRIPTION_MAX_LENGTH}文字。ZIP作成時にも保存します。</small>
          </label>
          <label className="field" htmlFor="delivery-tags">
            <span>タグ（任意）</span>
            <textarea id="delivery-tags" value={tags} maxLength={MANUAL_PUBLICATION_TAGS_MAX_LENGTH} rows={2} onChange={(event) => setTags(event.target.value)} />
            <small className="field-help">カンマまたは改行で区切って入力します。タグは投稿情報テキストだけに含まれます。</small>
          </label>
          <div className="manual-publication-actions">
            <div className="button-row">
              <button className="button button-primary" type="button" disabled={!resolution.ready || !publication.metadata || videos.length !== 2} onClick={() => void exportPublication('copy')}>投稿情報をコピー</button>
              <button className="button button-secondary" type="button" disabled={!resolution.ready || !publication.metadata || videos.length !== 2} onClick={() => void exportPublication('download')}>投稿情報を保存（.txt）</button>
            </div>
            <p className="field-help">入力した文章をそのままテキストにまとめます。入力は自動保存されません。別タブへ移動・再読み込みする前に .txt を保存してください。</p>
            {publication.error && <p className="field-help">{publication.error}</p>}
            <p className="manual-publication-note" role="status">{ZIP_METADATA_MESSAGES[zipComparison]}</p>
          </div>
          <div className="button-row">
            <button className="button button-secondary" type="submit" disabled={!resolution.ready || metadataInvalid || submitting || jobActive}>
              {submitting ? '投入中…' : jobActive ? '作成中…' : '納品ZIPを作成'}
            </button>
          </div>
        </form>

        {currentJob && <details className="manual-publication-records"><summary>納品処理の記録</summary><div className="delivery-job"><span>Job</span><code>{currentJob.id}</code><strong>{currentJob.status}</strong></div></details>}
        {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</div>}
        {textExport && (
          <details className="manual-publication-text" open={copyFallback}>
            <summary>直前に出力した投稿情報を見る</summary>
            <label className="field" htmlFor="manual-publication-text"><span>{textExport.fileName}</span><textarea ref={fallbackRef} id="manual-publication-text" readOnly value={textExport.text} onFocus={(event) => event.target.select()} aria-label="コピー可能な投稿情報" /></label>
            <small>この表示は直前の出力時点の内容です。入力を変更したら、もう一度コピーまたは保存してください。</small>
          </details>
        )}
        {currentJob?.status === 'succeeded' && !deliveryPackageResult(currentJob) && (
          <div className="inline-message is-error" role="alert">完成ZIPの情報を確認できません。制作を再読み込みしてください。</div>
        )}
        {completed && (
          <div className="delivery-result">
            <div>
              <span className="section-kicker">VERIFIED OUTPUT</span>
              <h4>直近の納品ZIP</h4>
              <p>{completed.filesIncluded}ファイル · サムネイル{completed.thumbnailCount}枚 · {completed.cacheHit ? '保存済みの納品を再利用' : '新規作成'}</p>
            </div>
            <a className="button button-primary" href={completed.artifact.url}>ZIPをダウンロード</a>
            <details className="manual-publication-records"><summary>ZIPの照合情報</summary><small>SHA-256照合用ファイル: <code>{completed.sha256Sidecar}</code></small></details>
          </div>
        )}
      </section>

      <aside className="panel delivery-gates-panel">
        <div className="panel-header"><div><span className="section-kicker">REVIEW GATES</span><h3>レビュー判定</h3></div></div>
        <p className="panel-lead">公開前の確認状況です。確認用の動画や納品ZIPは、未承認でも取り出せます。</p>
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
          <strong>YouTube Studioから手動で投稿</strong>
          <p>保存した動画をアップロードし、投稿情報を貼り付けて公開日時や公開範囲を設定してください。</p>
        </div>
      </aside>
    </div>
  );
}

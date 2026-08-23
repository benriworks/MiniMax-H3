import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import type {
  Approval,
  Artifact,
  CostEntry,
  HealthStatus,
  Job,
  ProductionDetail,
  ProductionRun,
  ProductionSummary,
  ProviderStatus,
  RerunChanges,
  RerunPlan,
  StudioEvent,
  StudioStatus,
} from './types';

type DetailTab = 'overview' | 'artifacts' | 'compare' | 'logs' | 'audit';

const STATUS_LABEL: Record<StudioStatus, string> = {
  pending: '待機',
  running: '実行中',
  succeeded: '完了',
  failed: '失敗',
  blocked: '確認待ち',
  approved: '承認済み',
  rejected: '却下',
  cancelled: '中止',
  unknown: '未判定',
};

const STAGE_LABELS: Record<string, string> = {
  planning: '企画・台本',
  script: '台本',
  narration: 'ナレーション',
  captions: '字幕・テロップ',
  capture: '画面収録',
  captures: '画面収録',
  screen_capture: '画面収録',
  keyframe: 'キーフレーム画像',
  keyframes: 'キーフレーム画像',
  generated_visuals: '生成映像',
  visuals: '生成映像',
  video: '生成映像',
  video_generation: '生成映像',
  composition: '編集・合成',
  compose: '編集・合成',
  assembly: '編集・合成',
  qc: '品質検査',
  release: '公開判定',
};

const formatDate = (value?: string): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const formatDuration = (seconds?: number): string => {
  if (seconds === undefined) return '—';
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
};

const formatBytes = (bytes?: number): string => {
  if (bytes === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
};

const formatMoney = (amount: number, currency = 'JPY'): string => {
  try {
    return new Intl.NumberFormat('ja-JP', { style: 'currency', currency }).format(amount);
  } catch {
    return `${amount.toLocaleString('ja-JP')} ${currency}`;
  }
};

const stageLabel = (value?: string): string => {
  if (!value) return '未分類';
  return STAGE_LABELS[value.toLowerCase()] ?? value;
};

const StatusBadge = ({ status, label }: { status: StudioStatus; label?: string }) => (
  <span className={`status-badge status-${status}`}>
    <span className="status-dot" aria-hidden="true" />
    {label ?? STATUS_LABEL[status]}
  </span>
);

const costApprovalLabel = (status: StudioStatus): string | undefined => {
  if (status === 'approved') return '費用承認済み';
  if (status === 'rejected') return '費用却下';
  return undefined;
};

const runCostApprovalLabel = (run: ProductionRun): string => {
  if ((run.estimatedCost ?? 0) <= 0) return '費用承認不要';
  return costApprovalLabel(run.status) ?? '費用承認待ち';
};

const EmptyState = ({ title, description }: { title: string; description?: string }) => (
  <div className="empty-state">
    <div className="empty-mark" aria-hidden="true">◇</div>
    <strong>{title}</strong>
    {description && <p>{description}</p>}
  </div>
);

const LoadingState = ({ label = '読み込み中' }: { label?: string }) => (
  <div className="loading-state" role="status">
    <span className="spinner" aria-hidden="true" />
    <span>{label}</span>
  </div>
);

const ErrorNotice = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div className="notice notice-error" role="alert">
    <div>
      <strong>読み込みに失敗しました</strong>
      <p>{message}</p>
    </div>
    {onRetry && <button className="button button-secondary" onClick={onRetry}>再試行</button>}
  </div>
);

function App() {
  const [health, setHealth] = useState<HealthStatus>({ healthy: false, message: '確認中' });
  const [productions, setProductions] = useState<ProductionSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [detail, setDetail] = useState<ProductionDetail>();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [detailError, setDetailError] = useState<string>();
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    const results = await Promise.allSettled([api.health(), api.productions(), api.jobs(), api.providers()]);
    const [healthResult, productionResult, jobsResult, providersResult] = results;
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
    if (productionResult.status === 'fulfilled') {
      setProductions(productionResult.value);
      setSelectedId((current) => current ?? productionResult.value[0]?.id);
    }
    if (jobsResult.status === 'fulfilled') setJobs(jobsResult.value);
    if (providersResult.status === 'fulfilled') setProviders(providersResult.value);
    const failures = results.filter((result) => result.status === 'rejected') as PromiseRejectedResult[];
    if (failures.length) {
      setError(failures.map((failure) => failure.reason instanceof Error ? failure.reason.message : String(failure.reason)).join(' / '));
    }
    setLoading(false);
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    setDetailLoading(true);
    setDetailError(undefined);
    try {
      setDetail(await api.production(id));
    } catch (loadError) {
      setDetail(undefined);
      setDetailError(loadError instanceof Error ? loadError.message : '制作情報を取得できませんでした');
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);
  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else setDetail(undefined);
  }, [selectedId, loadDetail]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void Promise.all([api.health(), api.jobs()]).then(([nextHealth, nextJobs]) => {
        setHealth(nextHealth);
        setJobs(nextJobs);
      }).catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const refreshIndex = async () => {
    setRefreshing(true);
    try {
      await api.refreshIndex();
      await loadDashboard();
      if (selectedId) await loadDetail(selectedId);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'インデックスを更新できませんでした');
    } finally {
      setRefreshing(false);
    }
  };

  const filteredProductions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return productions;
    return productions.filter((production) =>
      [production.title, production.description, ...production.tags].filter(Boolean).join(' ').toLowerCase().includes(normalized),
    );
  }, [productions, query]);

  const activeJobs = jobs.filter((job) => job.status === 'running' || job.status === 'pending');
  const configuredProviders = providers.filter((provider) => provider.configured).length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <div>
            <div className="eyebrow">LOCAL PRODUCTION CONTROL</div>
            <h1>MiniMax H3 Studio</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <div className={`connection-state ${health.degraded ? 'is-degraded' : health.healthy ? 'is-online' : 'is-offline'}`} title={health.message}>
            <span aria-hidden="true" />
            <span>{health.degraded ? '監査ログ 要確認' : health.healthy ? 'API 接続中' : 'API 未接続'}</span>
            {health.version && <small>v{health.version}</small>}
          </div>
          <button className="button button-secondary" onClick={() => void refreshIndex()} disabled={refreshing}>
            <span aria-hidden="true">↻</span>
            {refreshing ? '更新中…' : 'インデックス更新'}
          </button>
        </div>
      </header>

      {activeJobs.length > 0 && <JobsStrip jobs={activeJobs} productions={productions} />}

      <div className="studio-layout">
        <aside className="production-sidebar" aria-label="制作一覧">
          <div className="sidebar-header">
            <div>
              <span className="section-kicker">PRODUCTIONS</span>
              <h2>制作一覧</h2>
            </div>
            <span className="count-chip">{productions.length}</span>
          </div>
          <label className="search-box">
            <span className="sr-only">制作を検索</span>
            <span aria-hidden="true">⌕</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="タイトル・タグで検索" />
          </label>

          {loading && <LoadingState />}
          {!loading && error && productions.length === 0 && <ErrorNotice message={error} onRetry={() => void loadDashboard()} />}
          {!loading && filteredProductions.length === 0 && !error && (
            <EmptyState title="制作がありません" description="productions を追加し、インデックスを更新してください。" />
          )}
          <div className="production-list">
            {filteredProductions.map((production) => (
              <button
                key={production.id}
                className={`production-card ${selectedId === production.id ? 'is-selected' : ''}`}
                onClick={() => setSelectedId(production.id)}
                aria-current={selectedId === production.id ? 'page' : undefined}
              >
                <div className="production-thumb">
                  {production.thumbnailUrl
                    ? <img src={production.thumbnailUrl} alt="" />
                    : <span aria-hidden="true">{production.title.slice(0, 1)}</span>}
                </div>
                <div className="production-card-body">
                  <div className="production-card-top">
                    <strong>{production.title}</strong>
                    <StatusBadge status={production.status} />
                  </div>
                  <div className="production-meta">
                    <span>{formatDuration(production.durationSeconds)}</span>
                    <span>{formatDate(production.updatedAt)}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="provider-summary">
            <div className="provider-summary-title">
              <span>プロバイダー</span>
              <span>{configuredProviders}/{providers.length} 認証情報設定済み</span>
            </div>
            {providers.length === 0
              ? <p>設定情報がありません</p>
              : providers.map((provider) => (
                <div className="provider-row" key={provider.id} title={provider.message}>
                  <span className={`provider-indicator ${provider.healthy === true ? 'is-ready' : provider.configured ? 'is-configured' : ''}`} aria-hidden="true" />
                  <span>{provider.name}</span>
                  <small>{provider.configured ? (provider.healthy === true ? '接続確認済み' : provider.healthy === false ? '接続エラー' : '接続未確認') : '未設定'}</small>
                </div>
              ))}
          </div>
        </aside>

        <main className="workspace">
          {error && productions.length > 0 && <ErrorNotice message={error} onRetry={() => void loadDashboard()} />}
          {!selectedId && !loading && <EmptyState title="制作を選択してください" description="左の一覧から確認する制作を選択します。" />}
          {selectedId && detailLoading && <LoadingState label="制作記録を読み込み中" />}
          {selectedId && detailError && !detailLoading && <ErrorNotice message={detailError} onRetry={() => void loadDetail(selectedId)} />}
          {detail && !detailLoading && (
            <ProductionWorkspace
              detail={detail}
              jobs={jobs.filter((job) => job.productionId === detail.id)}
              onReload={() => loadDetail(detail.id)}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function JobsStrip({ jobs, productions }: { jobs: Job[]; productions: ProductionSummary[] }) {
  return (
    <section className="jobs-strip" aria-label="実行中のジョブ">
      <span className="jobs-strip-label"><span className="pulse" aria-hidden="true" />実行中</span>
      <div className="jobs-list">
        {jobs.slice(0, 4).map((job) => {
          const production = productions.find((item) => item.id === job.productionId);
          return (
            <div className="job-item" key={job.id}>
              <span>{production?.title ?? job.productionId ?? job.type}</span>
              <strong>{stageLabel(job.stage ?? job.type)}</strong>
              {job.progress !== undefined && (
                <div className="progress-track" aria-label={`${job.progress}%`}>
                  <span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
                </div>
              )}
              <small>{job.progress !== undefined ? `${Math.round(job.progress)}%` : STATUS_LABEL[job.status]}</small>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ProductionWorkspace({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const [tab, setTab] = useState<DetailTab>('overview');
  const latestRun = [...detail.runs].sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const completedArtifacts = detail.artifacts.length;
  const costSummary = [...detail.costs.reduce((totals, cost) => {
    totals.set(cost.currency, (totals.get(cost.currency) ?? 0) + cost.amount);
    return totals;
  }, new Map<string, number>()).entries()]
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(' / ') || '—';
  const activeJob = jobs.find((job) => job.status === 'running' || job.status === 'pending');

  const tabs: { id: DetailTab; label: string; count?: number }[] = [
    { id: 'overview', label: '概要' },
    { id: 'artifacts', label: '成果物', count: detail.artifacts.length },
    { id: 'compare', label: 'A/B比較' },
    { id: 'logs', label: 'ログ', count: detail.events.length },
    { id: 'audit', label: '監査・費用' },
  ];

  return (
    <>
      <section className="workspace-header">
        <div>
          <div className="breadcrumb"><span>制作</span><span>/</span><span>{detail.id}</span></div>
          <div className="title-row">
            <h2>{detail.title}</h2>
            <StatusBadge status={activeJob?.status ?? detail.status} />
          </div>
          {detail.description && <p className="production-description">{detail.description}</p>}
          <div className="tag-row">
            {detail.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
          </div>
          {(detail.technicalStatus || detail.creativeStatus || detail.publicReleaseStatus) && (
            <div className="gate-row" aria-label="判定ゲート">
              {detail.technicalStatus && <span><small>技術</small><StatusBadge status={detail.technicalStatus} /></span>}
              {detail.creativeStatus && <span><small>表現</small><StatusBadge status={detail.creativeStatus} /></span>}
              {detail.publicReleaseStatus && <span><small>公開</small><StatusBadge status={detail.publicReleaseStatus} /></span>}
            </div>
          )}
        </div>
        <div className="header-stats" aria-label="制作サマリー">
          <div><span>尺</span><strong>{formatDuration(detail.durationSeconds)}</strong></div>
          <div><span>Run</span><strong>{detail.runs.length}</strong></div>
          <div><span>成果物</span><strong>{completedArtifacts}</strong></div>
          <div><span>費用見積・記録</span><strong>{costSummary}</strong></div>
        </div>
      </section>

      <nav className="tabs" aria-label="制作情報">
        {tabs.map((item) => (
          <button key={item.id} className={tab === item.id ? 'is-active' : ''} onClick={() => setTab(item.id)}>
            {item.label}{item.count !== undefined && <span>{item.count}</span>}
          </button>
        ))}
      </nav>

      <div className="tab-content">
        {tab === 'overview' && <Overview detail={detail} latestRun={latestRun} onReload={onReload} />}
        {tab === 'artifacts' && <ArtifactsPanel artifacts={detail.artifacts} />}
        {tab === 'compare' && <ComparisonPanel artifacts={detail.artifacts} />}
        {tab === 'logs' && <LogPanel events={detail.events} />}
        {tab === 'audit' && <AuditPanel detail={detail} onReload={onReload} />}
      </div>
    </>
  );
}

function Overview({ detail, latestRun, onReload }: { detail: ProductionDetail; latestRun?: ProductionRun; onReload: () => Promise<void> }) {
  return (
    <div className="overview-grid">
      <div className="overview-main">
        <section className="panel">
          <div className="panel-header">
            <div><span className="section-kicker">PIPELINE PLAN</span><h3>要求工程（未実行）</h3></div>
            {latestRun && <span className="muted">{latestRun.label} · {formatDate(latestRun.createdAt)}</span>}
          </div>
          {!latestRun && <EmptyState title="Runがありません" description="再実行計画を作成すると、工程がここに表示されます。" />}
          {latestRun && latestRun.stages.length === 0 && (
            <div className="run-summary-line"><StatusBadge status={latestRun.status} /><span>工程の詳細記録はありません。</span></div>
          )}
          {latestRun && latestRun.stages.length > 0 && (
            <ol className="pipeline-list">
              {latestRun.stages.map((stage, index) => (
                <li key={stage.id} className={`pipeline-step step-${stage.status}`}>
                  <div className="step-rail"><span>{index + 1}</span></div>
                  <div className="step-body">
                    <div><strong>{stageLabel(stage.name)}</strong><StatusBadge status={stage.status} /></div>
                    {stage.message && <p>{stage.message}</p>}
                    <small>{formatDate(stage.startedAt)}{stage.finishedAt ? ` → ${formatDate(stage.finishedAt)}` : ''}</small>
                    {stage.progress !== undefined && <div className="progress-track"><span style={{ width: `${stage.progress}%` }} /></div>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">RUN PLANS</span><h3>Run計画履歴</h3></div></div>
          {detail.runs.length === 0 && <EmptyState title="Run計画履歴がありません" />}
          <div className="run-table-wrap">
            {detail.runs.length > 0 && (
              <table className="data-table">
                <thead><tr><th>Run</th><th>費用承認状態</th><th>作成日時</th><th>Revision</th></tr></thead>
                <tbody>{detail.runs.map((run) => (
                  <tr key={run.id}>
                    <td><strong>{run.label}</strong><small>{run.id}</small></td>
                    <td><StatusBadge status={run.status} label={runCostApprovalLabel(run)} /></td>
                    <td>{formatDate(run.createdAt)}</td>
                    <td>{run.revision ?? '—'}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>
      </div>
      <aside className="overview-side">
        <RerunPanel productionId={detail.id} onReload={onReload} />
        <section className="panel compact-panel">
          <div className="panel-header"><div><span className="section-kicker">LATEST ARTIFACTS</span><h3>最近の成果物</h3></div></div>
          {detail.artifacts.length === 0 && <p className="muted">成果物はまだありません。</p>}
          <div className="latest-artifacts">
            {detail.artifacts.slice(0, 5).map((artifact) => (
              <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer" className="latest-artifact">
                <span className={`artifact-kind kind-${artifact.kind}`} aria-hidden="true">{artifact.kind.slice(0, 1).toUpperCase()}</span>
                <span><strong>{artifact.name}</strong><small>{stageLabel(artifact.stage)} · {formatBytes(artifact.sizeBytes)}</small></span>
                <span aria-hidden="true">↗</span>
              </a>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

const RERUN_STAGES = [
  ['script', '台本'],
  ['narration', 'ナレーション'],
  ['captions', '字幕・テロップ'],
  ['screen_capture', '画面収録'],
  ['keyframe', 'キーフレーム画像'],
  ['video', '生成映像'],
  ['assembly', '編集・合成'],
  ['qc', '品質検査'],
] as const;

function RerunPanel({ productionId, onReload }: { productionId: string; onReload: () => Promise<void> }) {
  const [changes, setChanges] = useState<RerunChanges>({ stages: [], note: '', allowPaidApi: false });
  const [plan, setPlan] = useState<RerunPlan>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string }>();

  const toggleStage = (stage: string) => {
    setPlan(undefined);
    setChanges((current) => ({
      ...current,
      stages: current.stages.includes(stage) ? current.stages.filter((item) => item !== stage) : [...current.stages, stage],
    }));
  };

  const createPlan = async () => {
    if (changes.stages.length === 0) {
      setMessage({ type: 'error', text: '再実行する工程を1つ以上選択してください。' });
      return;
    }
    setBusy(true);
    setMessage(undefined);
    try {
      setPlan(await api.rerunPlan(productionId, changes));
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '計画を作成できませんでした' });
    } finally {
      setBusy(false);
    }
  };

  const startRun = async () => {
    if (!plan) return;
    if (plan.requiresCostEstimate && (!changes.allowPaidApi || !changes.maxCostJpy || changes.maxCostJpy <= 0)) {
      setMessage({ type: 'error', text: '課金工程を含むため、有料APIの計画を有効にして見積額を入力してください。' });
      return;
    }
    setBusy(true);
    setMessage(undefined);
    try {
      await api.createRun(productionId, plan, changes);
      setMessage({ type: 'success', text: '新しいRunを登録しました。' });
      await onReload();
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Run計画を保存できませんでした' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel rerun-panel">
      <div className="panel-header"><div><span className="section-kicker">PARTIAL RERUN</span><h3>再調整</h3></div></div>
      <p className="panel-lead">変更箇所から再実行範囲と再利用候補を計算し、監査可能なRun計画として保存します。MVPでは生成処理はまだ開始しません。</p>
      <fieldset className="stage-checks">
        <legend>変更する工程</legend>
        {RERUN_STAGES.map(([id, label]) => (
          <label key={id}>
            <input type="checkbox" checked={changes.stages.includes(id)} onChange={() => toggleStage(id)} />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <label className="field">
        <span>変更内容・理由</span>
        <textarea
          rows={3}
          value={changes.note}
          onChange={(event) => { setPlan(undefined); setChanges((current) => ({ ...current, note: event.target.value })); }}
          placeholder="例：CUT03後半の動きを増やす"
        />
      </label>
      <label className="toggle-field">
        <input
          type="checkbox"
          checked={changes.allowPaidApi}
          onChange={(event) => { setPlan(undefined); setChanges((current) => ({ ...current, allowPaidApi: event.target.checked })); }}
        />
          <span><strong>有料APIを使う計画</strong><small>Run作成後、監査タブで上限を承認します</small></span>
      </label>
      {changes.allowPaidApi && (
        <label className="field inline-field">
          <span>見積額</span>
          <div><input type="number" min="0" step="100" value={changes.maxCostJpy ?? ''} onChange={(event) => setChanges((current) => ({ ...current, maxCostJpy: event.target.value ? Number(event.target.value) : undefined }))} /><span>円</span></div>
        </label>
      )}
      {!plan && <button className="button button-primary full-button" onClick={() => void createPlan()} disabled={busy}>{busy ? '計算中…' : '再実行計画を確認'}</button>}
      {plan && (
        <div className="plan-result">
          <div className="plan-result-title"><strong>実行前の影響範囲</strong><span>{plan.id ?? 'draft'}</span></div>
          {plan.summary && <p>{plan.summary}</p>}
          <dl>
            <div><dt>再実行</dt><dd>{(plan.stages.length ? plan.stages : changes.stages).map(stageLabel).join('、')}</dd></div>
            <div><dt>再利用</dt><dd>{plan.reusedStages.length ? plan.reusedStages.map(stageLabel).join('、') : 'APIから情報なし'}</dd></div>
            <div><dt>課金工程</dt><dd>{plan.billableStages.length ? plan.billableStages.map(stageLabel).join('、') : 'なし'}</dd></div>
            <div><dt>見積費用</dt><dd>{plan.estimatedCost === undefined ? (plan.requiresCostEstimate ? (changes.maxCostJpy && changes.maxCostJpy > 0 ? formatMoney(changes.maxCostJpy, 'JPY') : '見積入力が必要') : '課金なし') : formatMoney(plan.estimatedCost, plan.currency)}</dd></div>
          </dl>
          <div className="button-row">
            <button className="button button-ghost" onClick={() => setPlan(undefined)} disabled={busy}>戻る</button>
            <button className="button button-primary" onClick={() => void startRun()} disabled={busy}>{busy ? '登録中…' : 'この内容でRunを作成'}</button>
          </div>
        </div>
      )}
      {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
    </section>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: Artifact[] }) {
  const [kind, setKind] = useState('all');
  const [selected, setSelected] = useState<Artifact>();
  const filtered = kind === 'all' ? artifacts : artifacts.filter((artifact) => artifact.kind === kind);
  const kinds = [...new Set(artifacts.map((artifact) => artifact.kind))];

  return (
    <section className="panel artifacts-panel">
      <div className="panel-header artifact-toolbar">
        <div><span className="section-kicker">ARTIFACT LIBRARY</span><h3>中間成果物・完成素材</h3></div>
        <div className="filter-chips" role="group" aria-label="成果物の種類">
          <button className={kind === 'all' ? 'is-active' : ''} onClick={() => setKind('all')}>すべて <span>{artifacts.length}</span></button>
          {kinds.map((item) => <button key={item} className={kind === item ? 'is-active' : ''} onClick={() => setKind(item)}>{item} <span>{artifacts.filter((artifact) => artifact.kind === item).length}</span></button>)}
        </div>
      </div>
      {filtered.length === 0 && <EmptyState title="表示できる成果物がありません" description="Run完了後、素材やログがここに並びます。" />}
      <div className="artifact-grid">
        {filtered.map((artifact) => (
          <article className="artifact-card" key={artifact.id}>
            <button className="artifact-preview-button" onClick={() => setSelected(artifact)} aria-label={`${artifact.name}をプレビュー`}>
              <ArtifactPreview artifact={artifact} compact />
            </button>
            <div className="artifact-info">
              <div><span className={`kind-label kind-${artifact.kind}`}>{artifact.kind}</span><span>{stageLabel(artifact.stage)}</span></div>
              <strong title={artifact.name}>{artifact.name}</strong>
              <small>{formatDate(artifact.createdAt)} · {formatBytes(artifact.sizeBytes)}</small>
              <div className="artifact-actions">
                <button onClick={() => setSelected(artifact)}>詳細</button>
                <a href={artifact.url} target="_blank" rel="noreferrer">開く ↗</a>
              </div>
            </div>
          </article>
        ))}
      </div>
      {selected && <ArtifactDialog artifact={selected} onClose={() => setSelected(undefined)} />}
    </section>
  );
}

function ArtifactDialog({ artifact, onClose }: { artifact: Artifact; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="artifact-dialog"
      aria-labelledby="artifact-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose(); }}
    >
      <div className="dialog-card">
        <header><div><span className={`kind-label kind-${artifact.kind}`}>{artifact.kind}</span><h3 id="artifact-dialog-title">{artifact.name}</h3></div><button className="icon-button" onClick={onClose} aria-label="閉じる" autoFocus>×</button></header>
        <div className="dialog-preview"><ArtifactPreview artifact={artifact} /></div>
        <dl className="artifact-details">
          <div><dt>工程</dt><dd>{stageLabel(artifact.stage)}</dd></div>
          <div><dt>作成日時</dt><dd>{formatDate(artifact.createdAt)}</dd></div>
          <div><dt>サイズ</dt><dd>{formatBytes(artifact.sizeBytes)}</dd></div>
          <div><dt>SHA-256</dt><dd className="mono">{artifact.sha256 ?? '—'}</dd></div>
          <div className="wide"><dt>保存先</dt><dd className="mono">{artifact.path ?? artifact.url ?? '—'}</dd></div>
        </dl>
        <footer><a className="button button-primary" href={artifact.url} target="_blank" rel="noreferrer">別画面で開く</a></footer>
      </div>
    </dialog>
  );
}

function ArtifactPreview({ artifact, compact = false }: { artifact: Artifact; compact?: boolean }) {
  if (!artifact.url) return <PreviewFallback artifact={artifact} />;
  if (artifact.kind === 'image') return <img className="media-preview" src={artifact.url} alt={artifact.name} loading="lazy" />;
  if (artifact.kind === 'video') return compact
    ? <video className="media-preview" src={`${artifact.url}#t=0.1`} muted preload="metadata" />
    : <video className="media-preview" src={artifact.url} controls preload="metadata" />;
  if (artifact.kind === 'audio') return compact
    ? <div className="audio-placeholder"><span aria-hidden="true">≋</span><small>AUDIO</small></div>
    : <div className="audio-full"><div className="audio-placeholder"><span aria-hidden="true">≋</span></div><audio src={artifact.url} controls preload="metadata" /></div>;
  if (artifact.kind === 'text') return compact ? <PreviewFallback artifact={artifact} /> : <TextPreview artifact={artifact} />;
  return <PreviewFallback artifact={artifact} />;
}

function TextPreview({ artifact }: { artifact: Artifact }) {
  const [content, setContent] = useState('読み込み中…');
  useEffect(() => {
    if (!artifact.url) return;
    const controller = new AbortController();
    fetch(artifact.url, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`${response.status}`);
      setContent((await response.text()).slice(0, 200_000));
    }).catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      setContent('テキストのプレビューを取得できませんでした。');
    });
    return () => controller.abort();
  }, [artifact.url]);
  return <pre className="text-preview">{content}</pre>;
}

function PreviewFallback({ artifact }: { artifact: Artifact }) {
  const marks: Record<string, string> = { text: 'TXT', document: 'DOC', archive: 'ZIP', other: 'FILE' };
  return <div className="preview-fallback"><span>{marks[artifact.kind] ?? artifact.kind.toUpperCase()}</span><small>{artifact.name}</small></div>;
}

function ComparisonPanel({ artifacts }: { artifacts: Artifact[] }) {
  const candidates = artifacts.filter((artifact) => ['video', 'audio', 'image'].includes(artifact.kind));
  const [leftId, setLeftId] = useState(candidates[0]?.id ?? '');
  const [rightId, setRightId] = useState(candidates[1]?.id ?? candidates[0]?.id ?? '');
  const left = candidates.find((artifact) => artifact.id === leftId);
  const right = candidates.find((artifact) => artifact.id === rightId);
  const leftMedia = useRef<HTMLMediaElement>(null);
  const rightMedia = useRef<HTMLMediaElement>(null);

  const mediaControl = (action: 'play' | 'pause' | 'sync') => {
    const a = leftMedia.current;
    const b = rightMedia.current;
    if (!a || !b) return;
    if (action === 'sync') b.currentTime = a.currentTime;
    if (action === 'pause') { a.pause(); b.pause(); }
    if (action === 'play') { void a.play(); void b.play(); }
  };

  if (candidates.length === 0) return <section className="panel"><EmptyState title="比較できる素材がありません" description="動画・音声・画像が2つ以上あるとA/B比較できます。" /></section>;
  const bothMedia = left && right && ['video', 'audio'].includes(left.kind) && left.kind === right.kind;

  return (
    <section className="panel comparison-panel">
      <div className="panel-header">
        <div><span className="section-kicker">VERSION REVIEW</span><h3>A/B比較</h3></div>
        {bothMedia && <div className="comparison-controls"><button onClick={() => mediaControl('play')}>両方再生</button><button onClick={() => mediaControl('pause')}>停止</button><button onClick={() => mediaControl('sync')}>BをAに同期</button></div>}
      </div>
      <p className="panel-lead">旧版と新版、生成候補やナレーションを並べて確認できます。</p>
      <div className="comparison-grid">
        <CompareSide label="A" artifact={left} candidates={candidates} value={leftId} onChange={setLeftId} mediaRef={leftMedia} />
        <CompareSide label="B" artifact={right} candidates={candidates} value={rightId} onChange={setRightId} mediaRef={rightMedia} />
      </div>
      {left && right && (
        <div className="comparison-metadata">
          <div><span>種類</span><strong>{left.kind}</strong><strong>{right.kind}</strong></div>
          <div><span>工程</span><strong>{stageLabel(left.stage)}</strong><strong>{stageLabel(right.stage)}</strong></div>
          <div><span>サイズ</span><strong>{formatBytes(left.sizeBytes)}</strong><strong>{formatBytes(right.sizeBytes)}</strong></div>
          <div><span>作成日時</span><strong>{formatDate(left.createdAt)}</strong><strong>{formatDate(right.createdAt)}</strong></div>
        </div>
      )}
    </section>
  );
}

function CompareSide({ label, artifact, candidates, value, onChange, mediaRef }: {
  label: string;
  artifact?: Artifact;
  candidates: Artifact[];
  value: string;
  onChange: (value: string) => void;
  mediaRef: React.RefObject<HTMLMediaElement | null>;
}) {
  return (
    <div className="compare-side">
      <div className="compare-select"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} aria-label={`比較素材 ${label}`}>
        {candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
      </select></div>
      <div className="compare-canvas">
        {!artifact && <PreviewFallback artifact={{ id: '', name: '未選択', kind: 'other', metadata: {}, raw: {} }} />}
        {artifact?.kind === 'video' && <video ref={mediaRef as React.RefObject<HTMLVideoElement>} src={artifact.url} controls preload="metadata" />}
        {artifact?.kind === 'audio' && <div className="audio-full"><div className="audio-placeholder"><span aria-hidden="true">≋</span></div><audio ref={mediaRef as React.RefObject<HTMLAudioElement>} src={artifact.url} controls preload="metadata" /></div>}
        {artifact?.kind === 'image' && <img src={artifact.url} alt={artifact.name} />}
      </div>
      {artifact && <div className="compare-name"><strong>{artifact.name}</strong><small>{artifact.sha256 ? `SHA ${artifact.sha256.slice(0, 12)}…` : artifact.path}</small></div>}
    </div>
  );
}

function LogPanel({ events }: { events: StudioEvent[] }) {
  const [level, setLevel] = useState('all');
  const [query, setQuery] = useState('');
  const filtered = events.filter((event) => {
    const levelMatches = level === 'all' || event.level === level;
    const textMatches = !query || `${event.message} ${event.stage ?? ''}`.toLowerCase().includes(query.toLowerCase());
    return levelMatches && textMatches;
  });
  return (
    <section className="panel log-panel">
      <div className="panel-header log-toolbar">
        <div><span className="section-kicker">EVENT STREAM</span><h3>Studioイベント</h3></div>
        <div className="log-filters">
          <select value={level} onChange={(event) => setLevel(event.target.value)} aria-label="ログレベル">
            <option value="all">すべてのレベル</option><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option><option value="debug">Debug</option>
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="メッセージを検索" aria-label="ログを検索" />
        </div>
      </div>
      {filtered.length === 0 && <EmptyState title="一致するログがありません" />}
      <div className="event-list">
        {filtered.map((event) => (
          <article className={`event-row event-${event.level}`} key={event.id}>
            <time>{formatDate(event.timestamp)}</time>
            <span className="event-level">{event.level}</span>
            <span className="event-stage">{stageLabel(event.stage)}</span>
            <div><p>{event.message}</p>{event.details !== undefined && <details><summary>詳細データ</summary><pre>{JSON.stringify(event.details, null, 2)}</pre></details>}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function AuditPanel({ detail, onReload }: { detail: ProductionDetail; onReload: () => Promise<void> }) {
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{ jobId?: string; error?: string }>();
  const groupedCosts = useMemo(() => {
    const result = new Map<string, number>();
    detail.costs.forEach((cost) => result.set(cost.currency, (result.get(cost.currency) ?? 0) + cost.amount));
    return [...result.entries()];
  }, [detail.costs]);
  const costApprovalRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => (run.estimatedCost ?? 0) > 0)
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );

  const exportAudit = async () => {
    setExporting(true);
    setExportResult(undefined);
    try {
      const result = await api.exportAudit(detail.id);
      const record = result !== null && typeof result === 'object' ? result as Record<string, unknown> : {};
      setExportResult({ jobId: String(record.id ?? record.job_id ?? '登録済み') });
    } catch (error) {
      setExportResult({ error: error instanceof Error ? error.message : '監査パッケージを作成できませんでした' });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="audit-grid">
      <div>
        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">COST LEDGER</span><h3>API費用</h3></div><div className="cost-total">{groupedCosts.map(([currency, amount]) => <strong key={currency}>{formatMoney(amount, currency)}</strong>)}</div></div>
          {detail.costs.length === 0 && <EmptyState title="費用記録がありません" />}
          {detail.costs.length > 0 && <table className="data-table cost-table"><thead><tr><th>日時</th><th>Provider</th><th>サービス</th><th>区分</th><th>金額</th></tr></thead><tbody>{detail.costs.map((cost) => <CostRow cost={cost} key={cost.id} />)}</tbody></table>}
        </section>
        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">COST APPROVAL TRAIL</span><h3>費用承認履歴</h3></div></div>
          {detail.approvals.length === 0 && <EmptyState title="費用承認記録がありません" />}
          <div className="approval-list">{detail.approvals.map((approval) => <ApprovalRow approval={approval} key={approval.id} />)}</div>
        </section>
      </div>
      <aside>
        <section className="panel compact-panel">
          <div className="panel-header"><div><span className="section-kicker">COST APPROVAL</span><h3>有料工程の費用上限</h3></div></div>
          <p className="panel-lead">正の見積を持つRun計画について、課金上限だけを承認または却下します。技術・表現・公開可否の判定とは別です。</p>
          {costApprovalRuns.length > 0
            ? <div className="approval-list">{costApprovalRuns.map((run) => <ApprovalControl key={run.id} run={run} onReload={onReload} />)}</div>
            : <p className="muted">費用承認が必要なRun計画はありません。</p>}
        </section>
        <section className="panel compact-panel audit-export">
          <div className="panel-header"><div><span className="section-kicker">AUDIT PACKAGE</span><h3>監査用書き出し</h3></div></div>
          <p>閲覧時点のStudio snapshot、イベント、格納entry hashと、台帳に存在する副生成物をまとめます。</p>
          <ul><li>audit/production-snapshot.json</li><li>audit/events.jsonl</li><li>audit/package-manifest.json</li><li>存在する台帳・ログ・QC sidecar</li></ul>
          <button className="button button-primary full-button" onClick={() => void exportAudit()} disabled={exporting}>{exporting ? '作成中…' : '監査パッケージを作成'}</button>
          {exportResult?.error && <div className="inline-message is-error">{exportResult.error}</div>}
          {exportResult?.jobId && <div className="inline-message is-success">書き出しジョブを登録しました：{exportResult.jobId}</div>}
        </section>
      </aside>
    </div>
  );
}

function CostRow({ cost }: { cost: CostEntry }) {
  return <tr><td>{formatDate(cost.createdAt)}</td><td><strong>{cost.provider}</strong></td><td>{cost.service ?? '—'}</td><td>{cost.estimated ? <span className="tag">見積</span> : '確定'}</td><td className="money-cell">{formatMoney(cost.amount, cost.currency)}</td></tr>;
}

function ApprovalRow({ approval }: { approval: Approval }) {
  return <article className="approval-row"><StatusBadge status={approval.status} label={costApprovalLabel(approval.status)} /><div><strong>{approval.target ?? 'Run費用上限'}</strong><p>{approval.note ?? 'コメントなし'}</p><small>{approval.approvedMax !== undefined ? `${formatMoney(approval.approvedMax, approval.currency ?? 'USD')} · ` : ''}{approval.reviewer ?? 'system'} · {formatDate(approval.createdAt)}</small></div></article>;
}

function ApprovalControl({ run, onReload }: { run: ProductionRun; onReload: () => Promise<void> }) {
  const [note, setNote] = useState('');
  const [maxCost, setMaxCost] = useState(run.estimatedCost ?? 0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  useEffect(() => setMaxCost(run.estimatedCost ?? 0), [run.id, run.estimatedCost]);
  const decide = async (approved: boolean) => {
    setBusy(true);
    setMessage(undefined);
    try {
      await api.approveRun(run.id, approved, note, maxCost, run.currency ?? 'USD');
      setMessage(approved ? '費用上限の承認を記録しました。' : '費用上限の却下を記録しました。');
      setNote('');
      await onReload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '判断を記録できませんでした');
    } finally {
      setBusy(false);
    }
  };
  return <div className="approval-control"><div className="target-run"><span>対象Run計画</span><strong>{run.label}</strong><StatusBadge status={run.status} label={runCostApprovalLabel(run)} /></div><label className="field"><span>費用判断コメント</span><textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="上限の承認・却下理由を記録" /></label><label className="field inline-field"><span>費用承認上限</span><div><input type="number" min="0" step="0.01" value={maxCost} onChange={(event) => setMaxCost(Number(event.target.value))} /><span>{run.currency ?? 'USD'}</span></div></label><div className="decision-buttons"><button className="button button-danger" onClick={() => void decide(false)} disabled={busy}>費用上限を却下</button><button className="button button-primary" onClick={() => void decide(true)} disabled={busy}>費用上限を承認</button></div>{message && <div className="inline-message">{message}</div>}</div>;
}

export default App;

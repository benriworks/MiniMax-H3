import { useEffect, useRef, useState } from 'react';
import { api, validateVideoImportFiles } from './api';
import type { Artifact, Job, ProductionDetail } from './types';
import { alignSharedScreenExplainerShots, artifactDuration, collectClaudeScreenExplainer, collectScreenExplainerAssets, createScreenExplainerSessionGuard, executeScreenExplainer, isScreenExplainerTheme, newScreenExplainerDraft, parseScreenExplainerDraft, persistScreenExplainerDraft, restoreScreenExplainerDraft, SCREEN_EXPLAINER_LABELS, SCREEN_EXPLAINER_STORAGE_KEY, SCREEN_EXPLAINER_THEME_OPTIONS, screenExplainerCaptureUrl, screenExplainerDraftFromRecipe, validateScreenExplainer, type ClaudeCaptureInspection, type ScreenExplainerDraft, type ScreenExplainerFocusRegion, type ScreenExplainerShot } from './screenExplainerWorkflow';
import './screenExplainer.css';
import { reviewScreenStructure } from './screenExplainerWorkflow';

interface ScreenExplainerPanelProps {
  open: boolean;
  onClose: () => void;
  onProductionReady: (productionId: string) => void;
  production?: ProductionDetail;
}
const steps = ['素材を集める', '台本を整える', '動画を作る'];
const safePersistedDraft = (draft: ScreenExplainerDraft): ScreenExplainerDraft => parseScreenExplainerDraft({ ...draft, shots: draft.shots.map((shot) => {
  let url = '';
  try { if (shot.url) url = screenExplainerCaptureUrl(shot.url); } catch { /* Incomplete URL input is held only in component memory. */ }
  return { ...shot, url };
}) });

export function ScreenExplainerPanel({ open, onClose, onProductionReady, production }: ScreenExplainerPanelProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const controller = useRef<AbortController | null>(null);
  const sessionGeneration = useRef(0);
  const running = useRef(false);
  const latestDraft = useRef<ScreenExplainerDraft | undefined>(undefined);
  const storageKey = `${SCREEN_EXPLAINER_STORAGE_KEY}:${production?.id ?? 'new'}`;
  const [draft, setDraft] = useState<ScreenExplainerDraft>();
  const [detail, setDetail] = useState<ProductionDetail | undefined>(production);
  const [files, setFiles] = useState<Map<number, File>>(() => new Map());
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [storageError, setStorageError] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [job, setJob] = useState<Job>();
  const [completedRender, setCompletedRender] = useState<Job>();
  const [loadedRecipeId, setLoadedRecipeId] = useState('');
  // Expiring window tokens and privacy consent must never enter persisted drafts.
  const [inspection, setInspection] = useState<ClaudeCaptureInspection>();
  const [selectedToken, setSelectedToken] = useState('');
  const [inspectionExpiresAt, setInspectionExpiresAt] = useState(0);
  const [inspectionBusy, setInspectionBusy] = useState(false);
  const [captureConfirmed, setCaptureConfirmed] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [cancelRequested, setCancelRequested] = useState('');
  const [previewRatios, setPreviewRatios] = useState<Record<string, number>>({});
  const clearCaptureConsent = () => { setInspection(undefined); setSelectedToken(''); setInspectionExpiresAt(0); setCaptureConfirmed(false); };

  const persistOnly = (value: ScreenExplainerDraft) => {
    const stored = safePersistedDraft(value);
    // Production identity is canonical even if this dialog was opened via the
    // "new" entry. App may select the created production after a reload.
    persistScreenExplainerDraft(window.localStorage, stored, storageKey);
  };
  const publishDraft = (value: ScreenExplainerDraft) => {
    latestDraft.current = value;
    setDraft(value);
  };
  const persist = (value: ScreenExplainerDraft) => { persistOnly(value); publishDraft(value); };

  useEffect(() => {
    const generation = ++sessionGeneration.current;
    clearCaptureConsent(); setInspectionBusy(false); setCancelling(false); setCancelRequested('');
    // A POST already on the wire may still return a recovery ID after close.
    // Keep mutation controls serialized until that operation retires; otherwise
    // a resumed same-production workflow could race its older checkpoint.
    setBusy(running.current);
    if (!open) {
      controller.current?.abort();
      if (dialog.current?.open) dialog.current.close();
      previousFocus.current?.focus();
      return;
    }
    previousFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    let restored: ScreenExplainerDraft | undefined;
    try {
      restored = restoreScreenExplainerDraft(window.localStorage, production?.id) ?? newScreenExplainerDraft(production);
      if (production && restored.productionId !== production.id) throw new Error('別の制作の保存情報です。');
      setStorageError('');
    } catch {
      setStorageError('保存情報が壊れているか、ブラウザ保存を利用できません。送信は停止しています。制作のログを確認してから、この端末の下書きを初期化してください。');
    }
    latestDraft.current = restored;
    setDraft(restored); setDetail(production); setFiles(new Map()); setStep(0); setError(''); setMessage(restored?.pending ? '前回の送信結果を照合するまで、同じ処理を自動再送しません。' : '目的・操作・結果の3場面で、素材取得から通常の制作経路につなぎます。'); setJob(undefined); setCompletedRender(undefined); setLoadedRecipeId('');
    if (dialog.current && !dialog.current.open) dialog.current.showModal();
    const abort = new AbortController();
    if (restored?.productionCreated) void api.production(restored.productionId, abort.signal).then((value) => {
      if (generation === sessionGeneration.current && !abort.signal.aborted) setDetail(value);
    }).catch((reason: unknown) => {
      if (generation === sessionGeneration.current && !abort.signal.aborted) setError(reason instanceof Error ? reason.message : '制作の読み込みに失敗しました。');
    });
    return () => { abort.abort(); controller.current?.abort(); };
    // The entry identity is stable while fetched production details change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, storageKey]);

  const edit = (patch: Partial<ScreenExplainerDraft>) => {
    const current = latestDraft.current;
    if (!current || running.current) return;
    const next = { ...current, ...patch };
    try { persist(next); setStorageError(''); } catch (reason) { setStorageError(reason instanceof Error ? reason.message : '下書きを保存できません。'); }
    setCompletedRender(undefined);
    setError('');
  };
  const editShot = (index: number, patch: Partial<ScreenExplainerShot>, sourceChanged = false) => {
    const current = latestDraft.current;
    if (!current) return;
    const shots = current.shots.map((shot, i) => i !== index ? shot : { ...shot, ...patch, ...(sourceChanged ? { artifactId: patch.artifactId ?? '', previewApproved: false, captureRunId: undefined, captureJobId: undefined, startMs: 0, focusRegion: undefined } : {}) });
    edit({ shots: current.sourceMode === 'claude_shared' ? alignSharedScreenExplainerShots(shots) : shots });
  };
  const close = () => { ++sessionGeneration.current; controller.current?.abort(); clearCaptureConsent(); onClose(); };
  const reset = () => {
    if (!window.confirm('ブラウザ内の下書きだけを初期化します。作成済みの素材・Run・Jobは削除も取消もしません。制作のログを確認済みですか？')) return;
    try {
      window.localStorage.removeItem(storageKey);
      if (latestDraft.current) {
        window.localStorage.removeItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:${latestDraft.current.productionId}`);
        const legacy = window.localStorage.getItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:new`);
        if (legacy && parseScreenExplainerDraft(JSON.parse(legacy)).productionId === latestDraft.current.productionId) window.localStorage.removeItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:new`);
      }
      const fresh = newScreenExplainerDraft(detail ?? production);
      persist(fresh); clearCaptureConsent(); setStorageError(''); setError(''); setFiles(new Map()); setJob(undefined); setCompletedRender(undefined); setStep(0);
    } catch { setStorageError('ブラウザ保存を利用できません。'); }
  };
  const perform = async (action: 'collect' | 'execute' | 'claude') => {
    const current = latestDraft.current;
    if (!current || running.current || storageError) return;
    if (action === 'claude' && (!captureConfirmed || !selectedToken || Date.now() >= inspectionExpiresAt)) {
      clearCaptureConsent(); setError('Claudeの選択が未確認か期限切れです。「Claudeを確認」からやり直してください。'); return;
    }
    const transientConsent = action === 'claude' ? { selectionToken: selectedToken, confirmCapture: true as const } : undefined;
    if (action === 'claude') clearCaptureConsent();
    running.current = true; setBusy(true); setError(''); setCompletedRender(undefined); setJob(undefined);
    const abort = new AbortController(); controller.current = abort;
    const generation = sessionGeneration.current;
    const isCurrent = () => generation === sessionGeneration.current && !abort.signal.aborted;
    const session = createScreenExplainerSessionGuard(isCurrent, persistOnly, publishDraft);
    const options = { onDraft: session.checkpoint, signal: abort.signal, onProgress: (text: string, value?: Job) => session.update(() => { setMessage(text); if (value) setJob(value); }) };
    try {
      if (action === 'collect' || action === 'claude') {
        const result = action === 'claude' ? await collectClaudeScreenExplainer(api, current, transientConsent, options) : await collectScreenExplainerAssets(api, current, files, options);
        session.update(() => {
          setDetail(result.production); setFiles(new Map());
          setMessage('3場面の素材を取得しました。各動画を再生して「確認済み」にすると、台本へ進めます。');
        });
      } else {
        const result = await executeScreenExplainer(api, current, options);
        const refreshed = await api.production(result.draft.productionId);
        session.update(() => {
          setJob(result.job); setCompletedRender(result.job); setDetail(refreshed);
          setMessage('標準Jobの動画作成・技術検査が完了しました。音声と映像の品質を確認し、制作画面から動画・投稿用テキストを取り出せます。');
        });
      }
    } catch (reason) {
      session.update(() => setError(reason instanceof Error ? reason.message : '処理に失敗しました。保存したIDから状態を確認してください。'));
    } finally {
      // Operation ownership, not dialog generation, releases the global
      // submission lock. An old completion cannot unlock a newer operation.
      if (controller.current === abort) { running.current = false; setBusy(false); }
    }
  };

  const inspectClaude = async () => {
    if (running.current || inspectionBusy) return;
    const generation = sessionGeneration.current;
    clearCaptureConsent(); setInspectionBusy(true); setError('');
    try {
      const result = await api.inspectClaudeCapture();
      if (generation !== sessionGeneration.current) return;
      setInspection(result); setInspectionExpiresAt(Date.now() + result.expiresInSeconds * 1000);
      if (result.targets.length === 1) setSelectedToken(result.targets[0].selectionToken);
    } catch {
      if (generation === sessionGeneration.current) setError('Claudeのウィンドウ確認に失敗しました。ウィンドウを開いた状態で確認してください。');
    } finally { if (generation === sessionGeneration.current) setInspectionBusy(false); }
  };
  const cancelCapture = async () => {
    const current = latestDraft.current;
    if (!current?.sharedCaptureJobId || cancelling || cancelRequested === current.sharedCaptureJobId) return;
    const generation = sessionGeneration.current;
    const jobId = current.sharedCaptureJobId;
    setCancelling(true); setCancelRequested(jobId);
    try {
      const known = await api.job(jobId);
      if (known.id !== jobId || known.productionId !== current.productionId || known.type !== 'claude_window_capture') throw new Error('収録Jobの対応を確認できません。');
      if (!['succeeded', 'failed', 'cancelled', 'blocked'].includes(known.status)) await api.cancelJob(jobId);
      if (generation === sessionGeneration.current) setMessage('収録停止を要求しました。Job IDを保持し、状態を再確認できます。');
    } catch {
      if (generation === sessionGeneration.current) setError('停止結果を確認できません。停止要求は自動再送しません。制作のJob状態を確認してください。');
    } finally { if (generation === sessionGeneration.current) setCancelling(false); }
  };
  const editFocus = (index: number, field: keyof ScreenExplainerFocusRegion, value: string) => {
    if (!value.trim()) return;
    const number = Number((Number(value) / 100).toFixed(4));
    const region = latestDraft.current?.shots[index].focusRegion;
    if (!region || !Number.isFinite(number)) return;
    const next = { ...region };
    if (field === 'x') next.x = Math.max(0, Math.min(number, 1 - region.width));
    if (field === 'y') next.y = Math.max(0, Math.min(number, 1 - region.height));
    if (field === 'width') next.width = Math.max(0.2, Math.min(number, 1 - region.x));
    if (field === 'height') next.height = Math.max(0.2, Math.min(number, 1 - region.y));
    for (const key of ['x', 'y', 'width', 'height'] as const) next[key] = Number(next[key].toFixed(4));
    editShot(index, { focusRegion: next, previewApproved: false });
  };

  const artifacts = detail?.artifacts.filter((artifact) => artifact.kind === 'video' && artifact.url) ?? [];
  const savedRecipes = detail?.announcementRecipes.filter((saved) => saved.recipe.templatePreset === 'screen_explainer_ja_v1') ?? [];
  const allAssets = Boolean(draft?.shots.every((shot) => shot.artifactId && artifacts.some((artifact) => artifact.id === shot.artifactId)));
  const allApproved = allAssets && Boolean(draft?.shots.every((shot) => shot.previewApproved));
  const validation = draft ? validateScreenExplainer(draft) : [];
  const locked = busy || inspectionBusy || cancelling || Boolean(storageError) || Boolean(draft?.pending);
  const sharedCapture = draft?.sourceMode === 'claude_shared';
  const sharedStarted = Boolean(draft?.sharedCaptureJobId || draft?.sharedCaptureArtifactId || draft?.pending);
  const canResumeShared = Boolean(draft?.sharedCaptureJobId || draft?.sharedCaptureArtifactId || draft?.pending);
  const totalSeconds = (draft?.shots.reduce((sum, shot) => sum + shot.durationMs, 0) ?? 15000) / 1000;
  const finalVideos = completedRender?.result?.artifacts.filter((artifact) => artifact.kind === 'video' && artifact.name === 'master-captioned.mp4') ?? [];

  const preview = (artifact: Artifact | undefined, index: number) => artifact?.url ? <div className="screen-explainer-preview-wrap" style={{ aspectRatio: previewRatios[artifact.id] ?? 16 / 9 }}><video
    className="screen-explainer-preview" key={`${artifact.id}:${draft?.shots[index].startMs}`} src={artifact.url} controls muted playsInline preload="metadata"
    aria-label={`${SCREEN_EXPLAINER_LABELS[index]}の素材プレビュー`}
    onLoadedMetadata={(event) => {
      const video = event.currentTarget;
      if (video.videoWidth && video.videoHeight) setPreviewRatios((ratios) => ({ ...ratios, [artifact.id]: video.videoWidth / video.videoHeight }));
      video.currentTime = (draft?.shots[index].startMs ?? 0) / 1000;
    }}
    onPlay={(event) => {
      const shot = draft?.shots[index]; if (!shot) return;
      if (event.currentTarget.currentTime < shot.startMs / 1000 || event.currentTarget.currentTime >= (shot.startMs + shot.durationMs) / 1000) event.currentTarget.currentTime = shot.startMs / 1000;
    }}
    onTimeUpdate={(event) => { const shot = draft?.shots[index]; if (shot && !event.currentTarget.paused && event.currentTarget.currentTime >= (shot.startMs + shot.durationMs) / 1000) event.currentTarget.pause(); }}
    onError={() => { editShot(index, { previewApproved: false }); setError(`${SCREEN_EXPLAINER_LABELS[index]}の素材を再生できません。別の素材を選択してください。`); }}
  />{draft?.shots[index].focusRegion ? <span className="screen-explainer-focus-overlay" aria-hidden="true" style={{ left: `${draft.shots[index].focusRegion!.x * 100}%`, top: `${draft.shots[index].focusRegion!.y * 100}%`, width: `${draft.shots[index].focusRegion!.width * 100}%`, height: `${draft.shots[index].focusRegion!.height * 100}%` }} /> : null}</div> : <div className="screen-explainer-preview screen-explainer-placeholder">ここに取得した画面を表示します</div>;

  return <dialog ref={dialog} className="screen-explainer-dialog" aria-labelledby="screen-explainer-heading" onCancel={(event) => { event.preventDefault(); close(); }}>
    <div className="screen-explainer-shell">
      <header className="screen-explainer-header"><div><span className="section-kicker">SCREEN EXPLAINER · 15–30 SEC</span><h2 id="screen-explainer-heading">画面で伝える、ひとつの操作</h2><p>編集前の素材集めをまとめて。画面全体または選んだ注目範囲を、目的 → 操作 → 結果で伝えます。</p></div><button type="button" onClick={close} aria-label="画面解説を閉じる">閉じる</button></header>
      <nav className="screen-explainer-steps" aria-label="画面解説の制作手順">{steps.map((label, index) => <button key={label} type="button" aria-current={step === index ? 'step' : undefined} disabled={busy || (index > 0 && !allApproved)} onClick={() => setStep(index)}><span>{index + 1}</span>{label}</button>)}</nav>
      <div className="notice notice-warning screen-explainer-scope"><div><strong>音声はWindows SAPIの試作版です。公開用音声は未受入です。</strong><p>Claude Desktopは明示的に選んだウィンドウだけを無音で収録します。アプリの自動操作・会話送信は行いません。ローカルURLは別の隔離ブラウザで収録します。台本だけが字幕になり、画面内の音は使用しません。</p></div></div>
      {storageError ? <div role="alert" className="notice notice-error"><div>{storageError}</div></div> : null}
      {error ? <div role="alert" className="notice notice-error"><div>{error}</div></div> : null}
      <p className="screen-explainer-progress" role="status" aria-live="polite">{message}{busy ? ' …' : ''}</p>
      {draft ? <>
        <div className="screen-explainer-identity"><span>制作 <code>{draft.productionId}</code></span><span>レシピ v{draft.recipeRevision}{draft.jobId ? ` · Job ${draft.jobId}` : ''}</span></div>
        <section className="screen-explainer-theme" data-theme={draft.screenTheme ?? 'neutral_v1'} aria-labelledby="screen-explainer-theme-heading">
          <div><h3 id="screen-explainer-theme-heading">紹介する製品・技術に合わせる</h3><p>構図と素材はそのままに、見出しの書体・配色・製品名を揃えます。</p></div>
          <label className="field"><span>デザインテーマ</span><select value={draft.screenTheme ?? 'neutral_v1'} disabled={locked} aria-describedby="screen-explainer-theme-note" onChange={(event) => {
            if (isScreenExplainerTheme(event.target.value)) edit({ screenTheme: event.target.value });
          }}>{['標準', '製品別', '技術テーマ別'].map((group) => <optgroup key={group} label={group}>{SCREEN_EXPLAINER_THEME_OPTIONS.filter((theme) => theme.group === group).map((theme) => <option key={theme.id} value={theme.id}>{theme.label}</option>)}</optgroup>)}</select></label>
          <p id="screen-explainer-theme-note">{SCREEN_EXPLAINER_THEME_OPTIONS.find((theme) => theme.id === (draft.screenTheme ?? 'neutral_v1'))?.description} テーマ選択だけでは再収録・音声生成を行いません。</p>
          {draft.screenTheme === 'claude_desktop_v1' || draft.screenTheme === 'claude_code_v1' || draft.screenTheme === 'claude_editorial_v1' ? <p className="screen-explainer-theme-disclosure"><strong>独立した非公式の紹介用です。</strong>公式ロゴは含みません。テーマは素材の内容を変更しません。Claude Codeの紹介にはCode画面を使用してください。通常のClaudeチャット画面をClaude Codeの実画面として扱わないでください。</p> : null}
        </section>
        {step > 0 ? <section className="screen-structure-review" aria-label="構成チェック">
          <h3>構成チェック — 書き出す前に</h3>
          <p>構成メモです。完成プレビューや画像の自動評価ではありません。素材は「素材を集める」で再生し、字幕と音声は完成版で確認します。</p>
          <ol className="screen-structure-beats">{draft.shots.map((shot, index) => <li key={shot.role}>
            <strong>{index + 1}. {['引きつける', '見せる', '持ち帰る'][index]}</strong>
            <span>{draft.shots.slice(0, index).reduce((sum, item) => sum + item.durationMs, 0) / 1000}秒〜 · {shot.durationMs / 1000}秒</span>
            <p>{shot.headline || '見出しを入れてください'}</p>
          </li>)}</ol>
          {reviewScreenStructure(draft).length ? <ul className="screen-structure-advice">{reviewScreenStructure(draft).map(issue => <li key={issue.key}>{issue.message}</li>)}</ul> : <p>設定上の重複・極端な切り抜きは見つかりません。映像内容の品質を保証する判定ではありません。</p>}
          <p>イラスト → 実画面 → 図解のように、場面ごとに見せるものを変えると切替が伝わります。この助言だけで保存・生成を止めたり、素材を変更したりはしません。</p>
        </section> : null}
        {step === 0 ? <>
          <label className="field"><span>制作タイトル</span><input value={draft.title} maxLength={120} disabled={locked} onChange={(event) => edit({ title: event.target.value })} /></label>
          {savedRecipes.length ? <div className="screen-explainer-load"><label className="field"><span>保存済みの画面解説を再調整</span><select value={loadedRecipeId} disabled={locked} onChange={(event) => setLoadedRecipeId(event.target.value)}><option value="">レシピを選択</option>{savedRecipes.map((saved) => <option key={saved.id} value={saved.id}>{saved.recipe.name} · v{saved.revision}</option>)}</select></label><button type="button" disabled={locked || !loadedRecipeId} onClick={() => {
            const saved = savedRecipes.find((item) => item.id === loadedRecipeId);
            if (!saved || !detail) return;
            try { persist(screenExplainerDraftFromRecipe(detail, saved)); clearCaptureConsent(); setFiles(new Map()); setJob(undefined); setCompletedRender(undefined); setMessage('保存した素材と台本を読み込みました。素材を再確認してから修正してください。'); } catch (reason) { setError(reason instanceof Error ? reason.message : '読み込みに失敗しました。'); }
          }}>読み込む</button></div> : null}
          <label className="field"><span>画面素材の取得方法</span><select disabled={locked} value={draft.sourceMode ?? 'individual'} onChange={(event) => {
            const sourceMode = event.target.value as 'individual' | 'claude_shared';
            clearCaptureConsent(); setFiles(new Map()); setJob(undefined);
            const shots = sourceMode === 'claude_shared' ? draft.shots.map((shot) => ({ ...shot, source: 'existing' as const, artifactId: '', previewApproved: false, focusRegion: undefined })) : draft.shots;
            edit({ sourceMode, shots: sourceMode === 'claude_shared' ? alignSharedScreenExplainerShots(shots) : shots });
          }}><option value="individual">場面ごとに素材を選ぶ</option><option value="claude_shared">Claude Desktopを1回収録</option></select></label>
          {sharedCapture ? <section className="screen-explainer-claude" aria-labelledby="screen-explainer-claude-heading">
            <h3 id="screen-explainer-claude-heading">Claude Desktopを1回だけ収録</h3>
            <p>合計{totalSeconds}秒の無音素材1本を、目的・操作・結果の順で連続して使います。事前にClaudeで見せたい画面を開いてください。収録中にこの画面からアプリを操作したり、プロンプトを送ったりすることはありません。</p>
            <p className="screen-explainer-window-warning"><strong>収録中はClaudeウィンドウを移動・サイズ変更・最小化しないでください。</strong>すぐ元へ戻しても、その収録は失敗として扱います。</p>
            {!sharedStarted ? <>
              <button type="button" disabled={locked} onClick={() => void inspectClaude()}>{inspectionBusy ? 'Claudeを確認中…' : 'Claudeを確認'}</button>
              {inspection ? inspection.available && inspection.targets.length ? <>
                <label className="field"><span>収録するClaudeウィンドウ</span><select disabled={locked} value={selectedToken} onChange={(event) => { setSelectedToken(event.target.value); setCaptureConfirmed(false); }}><option value="">ウィンドウを選択</option>{inspection.targets.map((target) => <option key={target.selectionToken} value={target.selectionToken}>{target.label} · {target.width}×{target.height}</option>)}</select><small>選択は約{inspection.expiresInSeconds}秒で失効します。閉じると選択と同意を破棄します。</small></label>
                <label className="screen-explainer-check"><input type="checkbox" disabled={locked || !selectedToken} checked={captureConfirmed} onChange={(event) => setCaptureConfirmed(event.target.checked)} />選択したウィンドウ内の会話・個人情報・秘密情報を確認し、この画面を無音で収録して制作素材として保存することに同意します。</label>
                <button className="primary" type="button" disabled={locked || !selectedToken || !captureConfirmed} onClick={() => void perform('claude')}>このウィンドウを{totalSeconds}秒収録する</button>
              </> : <p role="status">{inspection.reason || '収録できるClaudeウィンドウがありません。Claude Desktopを開いて、もう一度確認してください。'}</p> : null}
            </> : <p>前回の収録を再利用します。新しい収録要求は送りません。</p>}
            {draft.sharedCaptureRequestId ? <small className="screen-explainer-id">受付照合ID：{draft.sharedCaptureRequestId}</small> : null}
            {draft.sharedCaptureJobId ? <div className="screen-explainer-capture-status"><small className="screen-explainer-id">収録Job：{draft.sharedCaptureJobId}{job?.id === draft.sharedCaptureJobId ? ` · ${job.status}` : ''}</small>{!draft.sharedCaptureArtifactId ? <button type="button" disabled={cancelling || cancelRequested === draft.sharedCaptureJobId || (job?.id === draft.sharedCaptureJobId && ['succeeded', 'failed', 'cancelled', 'blocked'].includes(job.status))} onClick={() => void cancelCapture()}>{cancelling ? '停止を要求中…' : cancelRequested === draft.sharedCaptureJobId ? '停止要求済み' : '収録を停止する'}</button> : null}</div> : null}
            <small>閉じても収録は止まりません。停止する場合は「収録を停止する」を押してください。応答不明時はIDを保存し、照合だけを行います。</small>
          </section> : null}
          <div className="screen-explainer-scenes">{draft.shots.map((shot, index) => {
            const selected = artifacts.find((artifact) => artifact.id === shot.artifactId);
            return <section className="screen-explainer-card" key={shot.role}><h3><span>{index + 1}</span>{SCREEN_EXPLAINER_LABELS[index]}</h3>
              {!sharedCapture ? <label className="field"><span>素材の集め方</span><select disabled={locked} value={shot.source} onChange={(event) => editShot(index, { source: event.target.value as ScreenExplainerShot['source'] }, true)}><option value="existing">この制作の素材を使う</option><option value="file">動画ファイルを取り込む</option><option value="capture">ローカルURLを自動収録</option></select></label> : <p className="screen-explainer-trim">共通素材 {(shot.startMs / 1000).toFixed(1)}–{((shot.startMs + shot.durationMs) / 1000).toFixed(1)}秒</p>}
              {!sharedCapture && shot.source === 'existing' ? <label className="field"><span>動画素材</span><select disabled={locked} value={shot.artifactId} onChange={(event) => editShot(index, { artifactId: event.target.value }, true)}><option value="">素材を選択</option>{artifacts.map((artifact) => <option key={artifact.id} value={artifact.id}>{artifact.name}</option>)}</select></label> : null}
              {!sharedCapture && shot.source === 'file' ? <label className="field"><span>{shot.artifactId ? '取得済み（再取込しません）' : '動画ファイル'}</span><input type="file" accept="video/mp4,video/webm,video/quicktime,video/x-matroska,.mp4,.webm,.mov,.mkv" disabled={locked} onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                const result = validateVideoImportFiles([file]);
                if (result.errors.length) { setError(result.errors[0]); return; }
                setFiles((current) => new Map(current).set(index, file)); editShot(index, {}, true);
              }} /><small>{files.get(index)?.name ?? (shot.artifactId ? selected?.name ?? shot.artifactId : '未選択。ファイル本体はブラウザ保存されません。')}</small></label> : null}
              {!sharedCapture && shot.source === 'capture' ? <><label className="field"><span>収録するローカルURL</span><input type="url" disabled={locked || Boolean(shot.artifactId)} value={shot.url} placeholder="http://127.0.0.1:5173/" maxLength={2048} onChange={(event) => editShot(index, { url: event.target.value })} /><small>新しい隔離ブラウザで収録。ログインや外部URLは不可。</small></label><label className="screen-explainer-check"><input type="checkbox" disabled={locked || Boolean(shot.artifactId)} checked={shot.scroll} onChange={(event) => editShot(index, { scroll: event.target.checked })} />下へ1回スクロールする（クリックなし）</label>{shot.captureJobId ? <small className="screen-explainer-id">収録Job：{shot.captureJobId}</small> : null}</> : null}
              <label className="field"><span>場面の長さ</span><select disabled={locked} value={shot.durationMs} onChange={(event) => editShot(index, { durationMs: Number(event.target.value), previewApproved: false })}>{[5, 6, 7, 8, 9, 10].map((seconds) => <option key={seconds} value={seconds * 1000}>{seconds}秒</option>)}</select></label>
              {preview(selected, index)}
              {selected ? <small>{selected.name} · {artifactDuration(selected) !== undefined ? `${artifactDuration(selected)!.toFixed(2)}秒` : '長さ未確認'}{shot.startMs ? ` · 開始 ${(shot.startMs / 1000).toFixed(1)}秒` : ''}</small> : null}
              <details className="screen-explainer-focus"><summary>詳細：画面の注目範囲</summary><p>画面左上を0%、右下を100%として指定します（小数2桁まで）。範囲外は自動で調整します。完成動画では枠内が拡大表示されます。</p><label className="screen-explainer-check"><input type="checkbox" disabled={locked || !selected} checked={Boolean(shot.focusRegion)} onChange={(event) => editShot(index, { focusRegion: event.target.checked ? { x: 0.1, y: 0.1, width: 0.8, height: 0.8 } : undefined, previewApproved: false })} />注目範囲を指定する</label>{shot.focusRegion ? <div className="screen-explainer-focus-inputs">{([['x', '左位置'], ['y', '上位置'], ['width', '幅'], ['height', '高さ']] as const).map(([field, label]) => <label className="field" key={field}><span>{label}（%）</span><input type="number" step="0.01" min={field === 'width' || field === 'height' ? 20 : 0} max={100} disabled={locked} value={Number((shot.focusRegion![field] * 100).toFixed(2))} onChange={(event) => editFocus(index, field, event.target.value)} /></label>)}</div> : null}</details>
              <label className="screen-explainer-check"><input type="checkbox" disabled={locked || !selected} checked={shot.previewApproved} onChange={(event) => editShot(index, { previewApproved: event.target.checked })} />再生して内容・秘密情報・文字の見やすさを確認した</label>
              {shot.artifactId ? <small>{sharedCapture ? '1回の収録から、この区間を再利用します。' : '取得済み素材を再利用します。取り直す場合は素材の集め方を選び直してください。'}</small> : null}
            </section>;
          })}</div>
          <div className="screen-explainer-actions"><button className="primary" type="button" disabled={busy || inspectionBusy || Boolean(storageError) || (sharedCapture && !canResumeShared)} onClick={() => void perform('collect')}>{draft.pending ? '送信結果を再確認' : sharedCapture ? '同じ収録の状態を再確認' : allAssets ? '素材の状態を再確認' : '3場面の素材をまとめて取得'}</button><button type="button" disabled={busy || !allApproved} onClick={() => setStep(1)}>台本へ進む →</button></div>
        </> : null}
        {step === 1 ? <><div className="screen-explainer-scenes">{draft.shots.map((shot, index) => <section className="screen-explainer-card" key={shot.role}><h3>{index + 1}. {SCREEN_EXPLAINER_LABELS[index]} · {shot.durationMs / 1000}秒</h3>{preview(artifacts.find((artifact) => artifact.id === shot.artifactId), index)}<label className="field"><span>短い見出し（2行・全角10文字相当/行）</span><textarea rows={2} maxLength={80} disabled={locked} value={shot.headline} onChange={(event) => editShot(index, { headline: event.target.value })} /></label><label className="field"><span>読み上げ・字幕（全角19文字相当以内）</span><textarea rows={3} maxLength={300} disabled={locked} value={shot.narration} onChange={(event) => editShot(index, { narration: event.target.value })} /></label></section>)}</div>{validation.length ? <ul className="screen-explainer-errors">{validation.map((text) => <li key={text}>{text}</li>)}</ul> : <p>計{draft.shots.reduce((sum, shot) => sum + shot.durationMs, 0) / 1000}秒。場面間はハードカット、元画面は無音、見出しと字幕を別の領域に配置します。</p>}<div className="screen-explainer-actions"><button type="button" disabled={busy} onClick={() => setStep(0)}>← 素材に戻る</button><button className="primary" type="button" disabled={busy || validation.length > 0} onClick={() => setStep(2)}>生成内容を確認 →</button></div></> : null}
        {step === 2 ? <section className="screen-explainer-render"><h3>この内容で試作動画を作成</h3><dl><div><dt>完成尺</dt><dd>{draft.shots.reduce((sum, shot) => sum + shot.durationMs, 0) / 1000}秒・縦型9:16</dd></div><div><dt>テーマ</dt><dd>{SCREEN_EXPLAINER_THEME_OPTIONS.find((theme) => theme.id === (draft.screenTheme ?? 'neutral_v1'))?.label}{draft.screenTheme === undefined ? '（従来設定を保持）' : ''}</dd></div><div><dt>素材</dt><dd>{sharedCapture ? '同じ収録1本の連続3区間を再利用。' : '3場面の取得済み素材を再利用。'}再収録しません。</dd></div><div><dt>音声</dt><dd>Windows SAPI・ローカル・API課金なし。音質と発音は公開前に確認が必要です。</dd></div><div><dt>保存</dt><dd>同じレシピIDの新しい版を保存し、標準Jobで音声・字幕・合成・技術検査を実行します。</dd></div></dl>
          {draft.shots.map((shot, index) => <p key={shot.role}><strong>{SCREEN_EXPLAINER_LABELS[index]}</strong>：{shot.headline.replaceAll('\n', ' / ')}<br /><span>「{shot.narration}」</span></p>)}
          <div className="screen-explainer-actions"><button type="button" disabled={busy} onClick={() => setStep(1)}>← 台本に戻る</button><button className="primary" type="button" disabled={busy || Boolean(storageError) || validation.length > 0} onClick={() => void perform('execute')}>{draft.pending || draft.jobId ? '保存・Jobの状態を確認して続行' : 'レシピを保存して試作動画を作る'}</button></div>
          {job ? <p role="status">Job：<code>{job.id}</code> · {job.status}{typeof job.progress === 'number' ? ` · ${Math.round(job.progress * (job.progress <= 1 ? 100 : 1))}%` : ''}</p> : null}
          {finalVideos.length ? <div className="screen-explainer-results">{finalVideos.map((artifact) => <div key={artifact.id}><strong>{artifact.name}</strong>{artifact.url ? <video src={artifact.url} controls playsInline preload="metadata" aria-label={`完成動画 ${artifact.name}`} /> : null}</div>)}</div> : null}
          {completedRender ? <button className="primary" type="button" onClick={() => onProductionReady(draft.productionId)}>制作を開く：完成動画・投稿用テキスト・ログ</button> : null}
        </section> : null}
      </> : null}
      <footer className="screen-explainer-footer"><span>閉じても取得済み素材・レシピ版・Job IDを保持します。閉じる操作は監視だけを止め、収録・生成は取り消しません。</span><button type="button" disabled={busy || inspectionBusy || cancelling} onClick={reset}>この端末の下書きを初期化</button>{draft?.productionCreated ? <button type="button" disabled={busy} onClick={() => onProductionReady(draft.productionId)}>制作のログを開く</button> : null}</footer>
    </div>
  </dialog>;
}

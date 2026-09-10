import { useEffect, useRef, useState } from 'react';
import { StillApiError, type StillImage, type StillSource } from './stillLibraryApi';
import { planApi, planId, planSource, type StillPlan, type PlanStep } from './stillPlanApi';
import StillPackPreview from './StillPackPreview';

const RECEIPT = 'studio.still-plan.pending.v1';
const bodyKey = (plan: StillPlan) => JSON.stringify([plan.id, plan.revision, plan.title, plan.steps]);
const problem = (error: unknown) => error instanceof Error ? error.message : '撮影手順を処理できませんでした。';
const sourceLabel = (source: StillSource) => ({ web: 'ローカルWeb', claude: 'Claude', terminal: 'Windows Terminal', artifact: '登録済みPNG' }[source.kind]);

export default function StillPlanPanel({ source, selectedImage, locked, onPrepare, onDirty }: {
  source: StillSource; selectedImage?: StillImage; locked: boolean;
  onPrepare: (step: PlanStep) => void; onDirty: (dirty: boolean) => void;
}) {
  const [plans, setPlans] = useState<Pick<StillPlan, 'id' | 'title' | 'revision'>[]>([]);
  const [draft, setDraft] = useState<StillPlan>();
  const [savedKey, setSavedKey] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [uncertain, setUncertain] = useState('');
  const attempt = useRef<{ key: string; operationId: string } | undefined>(undefined);
  const alive = useRef(true);
  const dirty = !!draft && bodyKey(draft) !== savedKey;
  const disabled = locked || busy || !!uncertain;
  const accept = (plan: StillPlan) => { setDraft(plan); setSavedKey(bodyKey(plan)); setUncertain(''); attempt.current = undefined; };
  const refresh = async () => { const result = await planApi.list(); if (alive.current) setPlans(result.items); };
  useEffect(() => {
    alive.current = true;
    void refresh().catch((failure) => { if (alive.current) setError(problem(failure)); });
    try { const receipt = localStorage.getItem(RECEIPT); if (receipt && /^plan_[a-f0-9]{32}$/.test(receipt)) setUncertain(receipt); } catch { /* Saving checks storage before posting. */ }
    return () => { alive.current = false; };
  }, []);
  useEffect(() => { onDirty(dirty || !!uncertain); return () => onDirty(false); }, [dirty, uncertain, onDirty]);
  useEffect(() => {
    if (!dirty && !uncertain) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, uncertain]);
  const canReplace = () => !dirty || window.confirm('未保存の撮影手順を破棄しますか？');
  const load = async (id: string) => {
    if (!id || !canReplace()) return;
    setBusy(true); setError('');
    try { const result = await planApi.get(id); if (alive.current) { accept(result); localStorage.removeItem(RECEIPT); } }
    catch (failure) { if (alive.current) setError(problem(failure)); }
    finally { if (alive.current) setBusy(false); }
  };
  const create = () => {
    if (!canReplace()) return;
    setDraft({ id: planId('plan'), revision: 0, title: '新しい記事の撮影手順', steps: ['全体像', '操作・入力', '結果・確認'].map((title) => ({ id: planId('step'), title, memo: '', source: planSource(source), image: null })) });
    setSavedKey(''); setError(''); attempt.current = undefined;
  };
  const updateStep = (index: number, changes: Partial<PlanStep>) => setDraft((current) => current && ({ ...current, steps: current.steps.map((step, i) => i === index ? { ...step, ...changes } : step) }));
  const move = (index: number, delta: number) => setDraft((current) => {
    if (!current) return current;
    const steps = [...current.steps]; [steps[index], steps[index + delta]] = [steps[index + delta], steps[index]];
    return { ...current, steps };
  });
  const save = async () => {
    if (!draft || disabled) return;
    setBusy(true); setError('');
    const key = bodyKey(draft);
    if (attempt.current?.key !== key) attempt.current = { key, operationId: planId('planedit') };
    try {
      localStorage.setItem(RECEIPT, draft.id);
      const result = await planApi.save(draft, attempt.current.operationId);
      localStorage.removeItem(RECEIPT);
      if (alive.current) { accept(result); await refresh(); }
    } catch (failure) {
      if (failure instanceof StillApiError && failure.status < 500) localStorage.removeItem(RECEIPT);
      else { try { if (localStorage.getItem(RECEIPT)) setUncertain(draft.id); } catch { /* No POST when storage is unavailable. */ } }
      if (alive.current) setError(problem(failure));
    } finally { if (alive.current) setBusy(false); }
  };
  return <section className="still-plans" aria-label="撮影手順">
    <header><div><h3>撮影手順 — 素材を集める順番を決める</h3><p className="still-muted">手順を保存して再利用できます。自動操作・一括撮影はせず、各場面で対象と許可を確認します。</p></div></header>
    <p className="still-plan-selection">割り当てる選択画像：{selectedImage?.ready ? `${selectedImage.title}（メモ版${selectedImage.revision}）` : '未選択 — 下の保存画像から選んでください'}</p>
    {error && <p role="alert" className="still-error">{error}</p>}
    {uncertain && <p className="still-warning">保存結果が未確認です。自動で再送しません。<button type="button" disabled={busy} onClick={() => void load(uncertain)}>保存結果を確認</button><button type="button" disabled={busy} onClick={() => { if (window.confirm('一覧と保存結果を確認しましたか？遅れて保存される可能性があります。')) { localStorage.removeItem(RECEIPT); setUncertain(''); } }}>未確認状態を解除</button></p>}
    <fieldset disabled={disabled}>
      <div className="still-actions"><button type="button" onClick={create}>撮影手順を新規作成</button><button type="button" onClick={() => void refresh().catch((failure) => setError(problem(failure)))}>手順一覧を更新</button></div>
      <label>保存した撮影手順<select value={draft?.revision ? draft.id : ''} onChange={(event) => void load(event.target.value)}><option value="">手順を選択</option>{plans.map((plan) => <option key={plan.id} value={plan.id}>{plan.title} — 版{plan.revision}</option>)}</select></label>
      {draft && <>
        <label>手順の名前<input maxLength={120} value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} /></label>
        <p role="status">{dirty ? '手順に未保存の変更があります' : `手順を保存済み · 版${draft.revision}`} · {draft.steps.filter((step) => step.image).length}/{draft.steps.length}場面に画像を割り当て</p>
        <ol className="still-plan-steps">{draft.steps.map((step, index) => <li key={step.id}>
          <label>場面{index + 1}の見出し<input maxLength={120} value={step.title} onChange={(event) => updateStep(index, { title: event.target.value })} /></label>
          <label>場面{index + 1}の説明<textarea rows={2} maxLength={2000} value={step.memo} onChange={(event) => updateStep(index, { memo: event.target.value })} /></label>
          <p className="still-muted">撮影元: {sourceLabel(step.source)} · {step.image ? `画像 ${step.image.id.slice(-8)} / メモ版${step.image.revision}` : '画像未割り当て'}</p>
          <div className="still-actions">
            <button type="button" disabled={dirty} onClick={() => onPrepare(step)}>場面{index + 1}の撮影を準備</button>
            <button type="button" onClick={() => updateStep(index, { source: planSource(source) })}>現在の撮影条件を使う</button>
            <button type="button" disabled={!selectedImage?.ready} onClick={() => { if (selectedImage?.ready) updateStep(index, { image: { id: selectedImage.id, revision: selectedImage.revision } }); }}>選択画像を場面{index + 1}に割り当て</button>
            {step.image && <button type="button" onClick={() => updateStep(index, { image: null })}>画像の割り当てを外す</button>}
            <button type="button" aria-label={`場面${index + 1}を上へ`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
            <button type="button" aria-label={`場面${index + 1}を下へ`} disabled={index === draft.steps.length - 1} onClick={() => move(index, 1)}>↓</button>
            <button type="button" disabled={draft.steps.length === 1} onClick={() => { if (window.confirm('この場面を手順から外しますか？画像原本と保存済み履歴は残ります。')) setDraft({ ...draft, steps: draft.steps.filter((_, i) => i !== index) }); }}>場面を外す</button>
          </div>
        </li>)}</ol>
        <div className="still-actions">
          <button type="button" disabled={draft.steps.length >= 12} onClick={() => setDraft({ ...draft, steps: [...draft.steps, { id: planId('step'), title: '追加の場面', memo: '', source: planSource(source), image: null }] })}>場面を追加</button>
          <button type="button" className="button button-primary" disabled={!dirty || !draft.title.trim() || draft.steps.some((step) => !step.title.trim())} onClick={() => void save()}>撮影手順を保存</button>
          <button type="button" disabled={dirty || !draft.revision} onClick={() => { setDraft({ ...draft, id: planId('plan'), revision: 0, title: `${draft.title.slice(0, 110)}・複製`, steps: draft.steps.map((step) => ({ ...step, id: planId('step'), image: null })), history: [] }); setSavedKey(''); }}>画像を外して手順を複製</button>
          <button type="button" disabled={!draft.revision} onClick={() => void load(draft.id)}>保存済み手順を読み直す</button>
        </div>
        <details><summary>手順の保存履歴</summary>{draft.history?.map((entry) => <p key={entry.revision}>版{entry.revision} · {entry.title} · {entry.created_at}</p>)}</details>
        <StillPackPreview key={draft.id} plan={draft} disabled={disabled || dirty} />
      </>}
    </fieldset>
  </section>;
}

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { api } from './api';
import ClaudeStillSelector from './ClaudeStillSelector';
import StillPlanPanel from './StillPlanPanel';
import { stillApi, stillId, StillApiError, STILL_PENDING_KEY, type StillImage, type StillSource } from './stillLibraryApi';
import './stillLibrary.css';

const freshSource = (): StillSource => ({ kind: 'web', url: 'http://127.0.0.1:3000/', viewport: 'desktop', area: 'viewport', selector: '' });
const active = (item: StillImage) => ['queued', 'running'].includes(item.status);
const message = (error: unknown) => error instanceof Error ? error.message : '処理できませんでした。';
const statusLabel = (item: StillImage) => item.ready ? '保存済み' : ({ queued: '待機中', running: '撮影中', failed: '失敗', cancelled: '停止済み', interrupted: '中断' }[item.status] || item.status);

export default function StillLibraryPanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const alive = useRef(true);
  const loading = useRef(false);
  const sending = useRef(false);
  const editorDirty = useRef(false);
  const planDirty = useRef(false);
  const setPlanDirty = useCallback((value: boolean) => { planDirty.current = value; }, []);
  const [showPlans, setShowPlans] = useState(false);
  const requestController = useRef<AbortController | null>(null);
  const [items, setItems] = useState<StillImage[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [sources, setSources] = useState<{ id: string; name: string }[]>([]);
  const [selected, setSelected] = useState<StillImage>();
  const [editorEpoch, setEditorEpoch] = useState(0);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState<StillSource>(freshSource);
  const [selectorEpoch, setSelectorEpoch] = useState(0);
  const selectClaude = useCallback((token?: string) => { setSource({ kind: 'claude', ...(token ? { selection_token: token } : {}) }); setConsent(false); }, []);
  const selectTerminal = useCallback((token?: string) => { setSource({ kind: 'terminal', ...(token ? { selection_token: token } : {}) }); setConsent(false); }, []);
  const [title, setTitle] = useState('');
  const [memo, setMemo] = useState('');
  const [parent, setParent] = useState<StillImage>();
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pendingId, setPendingId] = useState(() => {
    try { const id = localStorage.getItem(STILL_PENDING_KEY); return id && /^still_[a-f0-9]{32}$/.test(id) ? id : ''; } catch { return ''; }
  });
  const [unresolved, setUnresolved] = useState(false);
  const pending = items.some(active) || !!pendingId;

  const refresh = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    const controller = new AbortController(); requestController.current = controller;
    try {
      const [list, registered] = await Promise.all([stillApi.list(offset, controller.signal), stillApi.sources(controller.signal)]);
      if (!alive.current) return;
      setItems(list.items); setTotal(list.total); setSources(registered.items);
      if (pendingId && !sending.current) {
        try {
          const receipt = await stillApi.get(pendingId, controller.signal);
          if (!alive.current) return;
          setUnresolved(false);
          if (!active(receipt)) {
            localStorage.removeItem(STILL_PENDING_KEY); setPendingId('');
            if (receipt.ready) { if (!editorDirty.current) setSelected(receipt); setNotice('静止画を保存しました。元の画像は上書きしていません。'); }
            else setError(receipt.source.kind === 'claude' ? 'Claude撮影は失敗または中断しました。ウィンドウの移動・最小化・選択期限を確認し、対象を選び直してください。' : '撮影は失敗または中断しました。URL・ページの読み込み・撮影範囲を確認して、新規撮影してください。');
          }
        } catch (failure) {
          if (failure instanceof StillApiError && failure.status === 404) setUnresolved(true);
          else throw failure;
        }
      }
    } catch (failure) {
      if (alive.current && !controller.signal.aborted) setError(message(failure));
    } finally { loading.current = false; }
  }, [offset, pendingId]);

  useEffect(() => { alive.current = true; dialog.current?.showModal(); return () => { alive.current = false; requestController.current?.abort(); }; }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!pending || unresolved) return;
    const timer = window.setInterval(() => { if (dialog.current?.open) void refresh(); }, 3000);
    return () => window.clearInterval(timer);
  }, [pending, unresolved, refresh]);

  const close = () => {
    if ((title || memo || editorDirty.current || planDirty.current) && !window.confirm('未保存の名前・メモ・撮影手順を破棄して閉じますか？保存済みの画像と処理中の撮影は残ります。')) return;
    onClose();
  };
  const capture = async (event: FormEvent) => {
    event.preventDefault(); if (busy || pending || (source.kind === 'claude' && !source.selection_token)) return;
    const id = stillId('still');
    sending.current = true;
    setBusy(true); setError(''); setNotice('');
    try {
      // Persist only an opaque receipt ID, before sending. No URL or page text.
      localStorage.setItem(STILL_PENDING_KEY, id); setPendingId(id);
      const item = await stillApi.submit({ id, title, memo, source, parent_id: parent?.id ?? null, confirm_capture: consent });
      if (!alive.current) return;
      setUnresolved(false);
      setItems((previous) => [item, ...previous.filter((entry) => entry.id !== id)]);
      setTitle(''); setMemo(''); setParent(undefined); setConsent(false); setOffset(0);
      setNotice('処理を開始しました。この画面を閉じても撮影は続きます。');
    } catch (failure) {
      if (failure instanceof StillApiError && failure.status < 500) { localStorage.removeItem(STILL_PENDING_KEY); setPendingId(''); }
      if (alive.current) setError(`${message(failure)}${failure instanceof StillApiError ? '' : ' 応答を確認中です。重複撮影は自動では行いません。'}`);
    } finally {
      sending.current = false;
      if (alive.current) {
        setBusy(false);
        if (source.kind === 'claude' || source.kind === 'terminal') { setSource({ kind: source.kind }); setSelectorEpoch((value) => value + 1); setConsent(false); }
      }
    }
  };

  const select = async (item: StillImage) => {
    if (editorDirty.current && !window.confirm('未保存の編集を破棄して、画像の情報を読み込み直しますか？')) return;
    setBusy(true); setError('');
    try { const detail = await stillApi.get(item.id); if (alive.current) { setSelected(detail); setEditorEpoch((value) => value + 1); } }
    catch (failure) { if (alive.current) setError(message(failure)); }
    finally { if (alive.current) setBusy(false); }
  };
  const retake = (item: StillImage) => {
    if ((title || memo) && !window.confirm('入力中の撮影条件を、この画像の条件に置き換えますか？')) return;
    setSource(item.source); setTitle(`${item.title.slice(0, 112)}・撮り直し`); setMemo(item.memo); setParent(item); setConsent(false);
    setSelectorEpoch((value) => value + 1);
    setNotice(item.source.kind === 'claude' || item.source.kind === 'terminal' ? '撮り直し元を設定しました。ウィンドウを再確認し、対象を選び直してください。' : '同じ条件を読み込みました。必要ならURLや範囲を変更して撮影してください。');
    dialog.current?.querySelector<HTMLInputElement>('#still-new-title')?.focus();
  };

  return <dialog ref={dialog} className="still-library" aria-labelledby="still-library-title" onCancel={(event) => { event.preventDefault(); close(); }}>
    <header className="still-header"><div><p className="still-eyebrow">ASSET LIBRARY / 静止画素材</p><h2 id="still-library-title">静止画ライブラリ</h2><p>動画を作らずに、記事・画面解説の素材を集める。</p></div><button type="button" className="button button-secondary" onClick={close}>閉じる</button></header>
    <div className="still-notices" aria-live="polite">{error && <p role="alert" className="still-error">{error}</p>}{notice && <p role="status">{notice}</p>}</div>
    <div className="still-plan-toggle"><button type="button" className="button button-secondary" aria-expanded={showPlans} onClick={() => { if (showPlans && planDirty.current && !window.confirm('未保存の撮影手順を破棄しますか？')) return; setShowPlans(!showPlans); }}>撮影手順を{showPlans ? '閉じる' : '開く'}</button></div>
    {showPlans && <StillPlanPanel source={source} selectedImage={selected} locked={busy || pending} onDirty={setPlanDirty} onPrepare={(step) => {
      if ((title || memo) && !window.confirm('撮影フォームをこの場面の条件に置き換えますか？')) return;
      setSource(step.source); setTitle(step.title); setMemo(step.memo); setParent(undefined); setConsent(false); setSelectorEpoch((value) => value + 1);
      setNotice(`「${step.title}」の撮影条件を読み込みました。対象を確認して撮影後、画像をこの場面に割り当ててください。`);
      dialog.current?.querySelector('.still-capture')?.scrollIntoView({ block: 'start' });
    }} />}
    {total > 0 && <button type="button" className="button button-secondary still-jump" onClick={() => dialog.current?.querySelector('.still-collection')?.scrollIntoView({ block: 'start' })}>保存画像へ ↓</button>}
    {unresolved && <div className="still-warning">撮影の受付記録がまだ見つかりません。自動で再送はしません。<button type="button" onClick={() => { setUnresolved(false); void refresh(); }}>受付を再確認</button><button type="button" onClick={() => { if (window.confirm('一覧に同じ撮影がないか確認しましたか？遅れて処理が完了する可能性があります。')) { localStorage.removeItem(STILL_PENDING_KEY); setPendingId(''); setUnresolved(false); } }}>確認を解除</button></div>}
    <div className="still-layout">
      <form onSubmit={(event) => void capture(event)} className="still-capture">
        <h3>01　素材を追加</h3><p className="still-muted">{source.kind === 'claude' || source.kind === 'terminal' ? '選択したウィンドウだけを取得します。対象の移動・サイズ変更などがあれば停止し、全画面撮影には切り替えません。' : 'ログイン済みブラウザは操作しません。外部通信や読み込みエラーのあるページは撮影失敗になります。'}</p>
        <fieldset disabled={busy || pending}>
          <label>撮影元<select value={source.kind} onChange={(event) => { setSource(event.target.value === 'web' ? freshSource() : event.target.value === 'claude' || event.target.value === 'terminal' ? { kind: event.target.value } : { kind: 'artifact', artifact_id: '' }); setConsent(false); }}><option value="web">ローカルWebを1枚撮影</option><option value="claude">Claudeウィンドウを1枚撮影</option><option value="terminal">Claude Code CLI用 — Windows Terminalを撮影</option><option value="artifact">登録済みPNGを取り込む</option></select></label>
          {source.kind === 'web' ? <>
            <label>ローカルURL<input type="url" required value={source.url} onChange={(event) => setSource({ ...source, url: event.target.value })} placeholder="http://127.0.0.1:3000/" /></label>
            <label>画面サイズ<select value={source.viewport} onChange={(event) => setSource({ ...source, viewport: event.target.value as 'desktop' | 'mobile' })}><option value="desktop">PC — 1440 × 900</option><option value="mobile">モバイル幅 — 390 × 844</option></select></label>
            <label>撮影範囲<select value={source.area} onChange={(event) => setSource({ ...source, area: event.target.value as 'viewport' | 'fullpage' | 'element', selector: '' })}><option value="viewport">表示領域</option><option value="fullpage">ページ全体</option><option value="element">指定要素（CSS）</option></select></label>
            {source.area === 'element' && <label>CSSセレクター<input required maxLength={200} placeholder="#main-content" value={source.selector} onChange={(event) => setSource({ ...source, selector: event.target.value })} /></label>}
          </> : source.kind === 'claude' || source.kind === 'terminal' ? <ClaudeStillSelector key={`${source.kind}:${selectorEpoch}`} kind={source.kind} value={source.selection_token} onSelect={source.kind === 'terminal' ? selectTerminal : selectClaude} /> : <label>登録済みPNG<select aria-label="登録済みPNG" required value={source.artifact_id} onChange={(event) => setSource({ ...source, artifact_id: event.target.value })}><option value="">選択してください</option>{sources.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}（{entry.id.slice(-8)}）</option>)}</select><small>インデックス登録済みの最新500件。Claude収録時のPNGも対象です。</small></label>}
          <label>画像名<input id="still-new-title" required maxLength={120} value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例：Claudeの回答画面" /></label>
          <label>メモ<textarea aria-label="メモ" maxLength={4000} rows={3} value={memo} onChange={(event) => setMemo(event.target.value)} placeholder="用途・見せたい部分・撮影条件など" /></label>
          {parent && <p className="still-parent">撮り直し元：{parent.title}<button type="button" onClick={() => setParent(undefined)}>関連を外す</button></p>}
          <label className="still-check"><input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} required />対象・機密情報を確認しました。撮影／コピーを許可します。</label>
          <button type="submit" className="button button-primary" disabled={!consent || !title.trim() || ((source.kind === 'claude' || source.kind === 'terminal') && !source.selection_token)}>{pending ? '処理中…' : source.kind === 'artifact' ? 'PNGをコピーして保存' : '1枚撮影して保存'}</button>
        </fieldset>
      </form>
      <section className="still-collection" aria-label="保存した静止画">
        <div className="still-toolbar"><h3>02　確認・取り出す <small>{total}枚</small></h3><button type="button" className="button button-secondary" onClick={() => void refresh()}>一覧を更新</button></div>
        <label>このページの画像名・メモで絞り込み<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
        {items.length === 0 && <div className="still-empty"><strong>まだ素材がありません</strong><p>左のフォームから最初の1枚を追加してください。<br />元画像を残したまま、撮り直しとメモを管理できます。</p></div>}
        <div className="still-grid">{items.filter((item) => `${item.title} ${item.memo}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map((item) => <article key={item.id} className={`still-card ${selected?.id === item.id ? 'is-selected' : ''}`}>
          <button type="button" className="still-card-select" disabled={busy || !item.ready} onClick={() => void select(item)} aria-label={`${item.title}を確認`}>
            {item.ready ? <img src={item.image_url} alt={item.title} loading="lazy" /> : <div className="still-placeholder">{statusLabel(item)}</div>}
            <strong>{item.title}</strong><span>{statusLabel(item)}{item.media ? ` · ${item.media.width} × ${item.media.height}` : ''}{item.parent_id ? ' · 撮り直し' : ''}</span>
          </button>
          {active(item) && <button type="button" disabled={busy} onClick={async () => { setBusy(true); try { await api.cancelJob(item.job_id); await refresh(); } catch (failure) { setError(message(failure)); } finally { setBusy(false); } }}>撮影を停止</button>}
        </article>)}</div>
        {total > 60 && <nav aria-label="静止画のページ"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 60))}>前へ</button><span>{offset + 1}–{Math.min(offset + 60, total)} / {total}</span><button disabled={offset + 60 >= total} onClick={() => setOffset(offset + 60)}>次へ</button></nav>}
        {selected?.ready && <StillEditor key={`${selected.id}:${selected.revision}:${editorEpoch}`} item={selected} locked={busy} onRetake={retake} onDirty={(dirty) => { editorDirty.current = dirty; }} onReload={() => void select(selected)} onSaved={(item) => { editorDirty.current = false; setSelected(item); void refresh(); }} />}
      </section>
    </div>
    <footer className="still-footer">PNG原本・SHA-256・編集履歴をローカル保存。Claude公式MSIX版／Windows Terminal安定版に対応。CLIの自動操作・Codexデスクトップ対応は未実装です。自動公開は行いません。</footer>
  </dialog>;
}

function StillEditor({ item, locked, onRetake, onSaved, onDirty, onReload }: { item: StillImage; locked: boolean; onRetake: (item: StillImage) => void; onSaved: (item: StillImage) => void; onDirty: (dirty: boolean) => void; onReload: () => void }) {
  const [title, setTitle] = useState(item.title), [memo, setMemo] = useState(item.memo);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [confirmed, setConfirmed] = useState(false);
  const attempt = useRef<{ title: string; memo: string; id: string } | null>(null);
  const dirty = title !== item.title || memo !== item.memo;
  useEffect(() => { onDirty(dirty); return () => onDirty(false); }, [dirty, onDirty]);
  useEffect(() => {
    if (!dirty) return;
    const prevent = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', prevent);
    return () => window.removeEventListener('beforeunload', prevent);
  }, [dirty]);
  const save = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    if (!attempt.current || attempt.current.title !== title || attempt.current.memo !== memo) attempt.current = { title, memo, id: stillId('edit') };
    try { onSaved(await stillApi.edit(item, title, memo, attempt.current.id)); }
    catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  const download = async () => {
    if (!confirmed || dirty) return;
    setBusy(true); setError('');
    try {
      const blob = await stillApi.export(item); const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `${item.id}-r${item.revision}.zip`; document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(false); }
  };
  return <section className="still-editor" aria-label="画像の詳細と編集">
    <h3>{item.title} <small>メモ版 {item.revision}</small></h3>
    <a href={item.image_url} target="_blank" rel="noreferrer">PNGを原寸で開く ↗</a>
    <p className="still-muted">{item.source.kind === 'web' ? `${item.source.url} · ${item.source.area}` : item.source.kind === 'claude' ? '選択したClaudeウィンドウから直接撮影 · 原寸PNG' : item.source.kind === 'terminal' ? 'Windows Terminalから直接撮影 · CLI内容は未検証 · 原寸PNG' : '登録済みPNGからコピー'}<br />{item.media?.width} × {item.media?.height} · {Math.round((item.media?.bytes ?? 0) / 1024)} KiB</p>
    {error && <div className="still-error" role="alert">{error}<button type="button" onClick={onReload}>保存済み情報を読み直す</button></div>}
    <form onSubmit={(event) => void save(event)}><fieldset disabled={busy || locked}>
      <label>保存画像の名前<input required maxLength={120} value={title} onChange={(event) => { setTitle(event.target.value); setConfirmed(false); }} /></label>
      <label>保存画像のメモ<textarea aria-label="保存画像のメモ" rows={3} maxLength={4000} value={memo} onChange={(event) => { setMemo(event.target.value); setConfirmed(false); }} /></label>
      <div className="still-actions"><button type="submit" className="button button-secondary" disabled={!dirty || !title.trim()}>名前・メモを保存</button><button type="button" className="button button-secondary" disabled={dirty} onClick={() => onRetake(item)}>この条件で撮り直す</button></div>
      {dirty && <p role="status">未保存の変更があります。保存後に書き出してください。</p>}
    </fieldset></form>
    <details><summary>変更履歴・検証情報</summary><code className="still-hash">SHA-256: {item.media?.sha256}</code><p>画像ID: {item.id}<br />撮り直し元: {item.parent_id || 'なし'}</p>{item.history?.map((entry) => <div key={entry.revision} className="still-history"><strong>版 {entry.revision}：{entry.title}</strong><time>{entry.created_at}</time><p>{entry.memo || 'メモなし'}</p></div>)}</details>
    <label className="still-check"><input type="checkbox" checked={confirmed} disabled={dirty || busy || locked} onChange={(event) => setConfirmed(event.target.checked)} />画像と現在のメモに機密情報がなく、書き出してよいことを確認しました。</label>
    <button type="button" className="button button-primary" disabled={!confirmed || dirty || busy || locked} onClick={() => void download()}>PNG＋MarkdownをZIPで保存</button>
  </section>;
}

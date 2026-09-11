import { useCallback, useEffect, useRef, useState } from 'react';
import ClaudeStillSelector from './ClaudeStillSelector';
import ClaudeControlDiagnostics from './ClaudeControlDiagnostics';
import { controlApi, CONTROL_PENDING_KEY, type ControlDiagnostics, type ControlInspection, type ControlOperation, type ControlReceipt } from './claudeControlApi';
import { StillApiError } from './stillLibraryApi';

const label = { launch: 'Claudeの起動要求', tab: 'タブ切替', input: '未送信の入力' };
const outcomeLabel = { processing: '処理中', verified: '操作結果を照合済み', review_required: '実画面で結果確認が必要' };
const pendingId = () => { try { const id = localStorage.getItem(CONTROL_PENDING_KEY); return id && /^control_[a-f0-9]{32}$/.test(id) ? id : ''; } catch { return ''; } };
const clearPending = (id: string) => { if (localStorage.getItem(CONTROL_PENDING_KEY) === id) localStorage.removeItem(CONTROL_PENDING_KEY); };

export default function ClaudeControlPanel({ locked, onActivity, onChanged, onDirty }: { locked: boolean; onActivity: (value: boolean) => void; onChanged: () => void; onDirty: (value: boolean) => void }) {
  const [expanded, setExpanded] = useState(() => !!pendingId());
  const [available, setAvailable] = useState(false), [history, setHistory] = useState<ControlReceipt[]>([]);
  const [selection, setSelection] = useState<string>(), [epoch, setEpoch] = useState(0);
  const [inspection, setInspection] = useState<ControlInspection>(), [target, setTarget] = useState('');
  const [diagnostics, setDiagnostics] = useState<ControlDiagnostics>();
  const [text, setText] = useState(''), [replace, setReplace] = useState(false);
  const [scanConsent, setScanConsent] = useState(false), [actionConsent, setActionConsent] = useState(false), [launchConsent, setLaunchConsent] = useState(false);
  const [busy, setBusy] = useState(false), [pending, setPending] = useState(pendingId);
  const [unresolved, setUnresolved] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const alive = useRef(true), loading = useRef(false), sending = useRef(false), timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reset = useCallback(() => { clearTimeout(timer.current); setSelection(undefined); setEpoch((n) => n + 1); setInspection(undefined); setTarget(''); setScanConsent(false); setActionConsent(false); setLaunchConsent(false); setReplace(false); }, []);
  const chooseWindow = useCallback((value?: string) => { setSelection(value); setScanConsent(false); }, []);
  const blocked = locked || busy || !!pending;
  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(timer.current); }; }, []);
  useEffect(() => { onActivity(busy || !!pending); return () => onActivity(false); }, [busy, pending, onActivity]);
  useEffect(() => { onDirty(!!text); return () => onDirty(false); }, [text, onDirty]);
  useEffect(() => {
    if (!text) return;
    const prevent = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', prevent); return () => window.removeEventListener('beforeunload', prevent);
  }, [text]);
  const refresh = useCallback(async () => {
    if (loading.current || sending.current) return;
    loading.current = true;
    try {
      const result = await controlApi.list();
      if (!alive.current) return;
      setAvailable(result.available); setHistory(result.items);
      if (pending) {
        try {
          const receipt = await controlApi.get(pending);
          if (!alive.current) return;
          setUnresolved(false);
          if (receipt.outcome !== 'processing') {
            clearPending(pending); setPending(''); reset(); onChanged();
            setNotice(`${label[receipt.operation]}：${outcomeLabel[receipt.outcome]}。Claudeを見て結果を確認し、撮影対象を選び直してください。送信は行っていません。`);
          }
        } catch (failure) {
          if (failure instanceof StillApiError && failure.status === 404) { if (alive.current) setUnresolved(true); }
          else throw failure;
        }
      }
    } catch { if (alive.current) setError('操作履歴を確認できません。接続回復後に受付を再確認してください。'); }
    finally { loading.current = false; }
  }, [pending, reset, onChanged]);
  useEffect(() => { if (expanded) void refresh(); }, [expanded, refresh]);
  useEffect(() => {
    if (!expanded || !pending || unresolved) return;
    const poll = window.setInterval(() => void refresh(), 3000); return () => window.clearInterval(poll);
  }, [expanded, pending, unresolved, refresh]);

  const inspect = async () => {
    if (blocked || !selection || !scanConsent) return;
    setBusy(true); setError(''); setNotice(''); setDiagnostics(undefined); const started = Date.now();
    try {
      const result = await controlApi.inspect(selection);
      if (!alive.current) return;
      reset(); setInspection(result); setDiagnostics(result.diagnostics);
      timer.current = setTimeout(() => { if (alive.current) { reset(); setNotice('操作対象の確認が期限切れです。入力文は未送信のまま残っています。対象を確認し直してください。'); } }, Math.max(0, result.expires_in_seconds * 1000 - (Date.now() - started)));
    } catch (failure) { if (alive.current) { reset(); setError(failure instanceof Error ? failure.message : '操作対象を確認できませんでした。'); } }
    finally { if (alive.current) { setBusy(false); onChanged(); } }
  };
  const act = async (operation: ControlOperation) => {
    if (blocked || (operation === 'launch' ? !launchConsent : !inspection || !target || !actionConsent)) return;
    const id = 'control_' + crypto.randomUUID().replaceAll('-', '');
    sending.current = true; setBusy(true); setError(''); setNotice('');
    try {
      // Store only a receipt ID. No draft text, selection tokens or target details.
      localStorage.setItem(CONTROL_PENDING_KEY, id); setPending(id);
      await controlApi.submit({ id, operation, inspection_token: operation === 'launch' ? null : inspection!.inspection_token, target_id: operation === 'launch' ? null : target,
        text: operation === 'input' ? text : null, allow_replace: operation === 'input' && replace, confirm_action: true });
      if (alive.current) { setUnresolved(false); setNotice('操作を受け付けました。送信・Enter操作はしません。'); }
    } catch (failure) {
      if (failure instanceof StillApiError && failure.status < 500) { clearPending(id); if (alive.current) setPending(''); }
      if (alive.current) setError(failure instanceof StillApiError ? failure.message : '応答が途切れました。受付IDで結果だけを確認します。操作は自動再送しません。');
    } finally { sending.current = false; if (alive.current) { setBusy(false); reset(); onChanged(); } }
  };
  const selected = inspection?.controls.find((item) => item.id === target);
  return <section className="claude-control" aria-label="Claudeの画面を準備">
    <button type="button" className="button button-secondary" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>Claudeの画面準備{expanded ? 'を閉じる' : 'を開く'}</button>
    {expanded && <div className="claude-control-body">
      <h3>撮影の前に：起動 → タブ・入力 → 画面を再確認</h3>
      <p className="still-muted">公式MSIX版専用・実験機能。操作用情報を確認できる画面だけが対象です。送信・Enter・コマンド実行・ログイン操作は含みません。操作中はClaudeに触れないでください。</p>
      {error && <p className="still-error" role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
      {diagnostics && <ClaudeControlDiagnostics value={diagnostics} />}
      {!available && <p className="still-warning">操作ヘルパーが未準備か、準備状態を確認中です。必要なら setup-studio.ps1 を実行してください。</p>}
      <fieldset disabled={blocked || !available}>
        <label className="still-check"><input type="checkbox" checked={launchConsent} onChange={(e) => setLaunchConsent(e.target.checked)} />今回、公式Claudeの起動を許可します。</label>
        <button type="button" className="button button-secondary" disabled={!launchConsent} onClick={() => void act('launch')}>Claudeを起動する</button>
        <p className="still-muted">インストール済みアプリの起動を要求します。起動後は表示・ログイン状態を手動で確認してください。</p>
        {!inspection && <ClaudeStillSelector key={epoch} value={selection} onSelect={chooseWindow} />}
        {!inspection && <><label className="still-check"><input type="checkbox" checked={scanConsent} onChange={(e) => setScanConsent(e.target.checked)} />選択したClaudeの操作対象確認を許可します。</label>
        <button type="button" className="button button-secondary" disabled={!selection || !scanConsent} onClick={() => void inspect()}>タブ・入力欄を確認</button></>}
        {inspection && <>
          <button type="button" className="button button-secondary" onClick={reset}>操作対象を選び直す</button>
          {inspection.available && <>
            <label>操作するタブ・入力欄<select value={target} onChange={(e) => { setTarget(e.target.value); setActionConsent(false); setReplace(false); }}><option value="">対象を選択してください</option>{inspection.controls.map((item) => <option key={item.id} value={item.id}>{item.label}{item.kind === 'input' ? `（既存 ${item.characters}字・左${Math.round(item.position.x)} 上${Math.round(item.position.y)}）` : ''}</option>)}</select></label>
            <p className="still-muted">有効期限60秒。位置はClaudeウィンドウ左上基準です。入力先を区別できない場合は実行しないでください。</p>
            {selected?.kind === 'input' && <p className="still-muted">入力方式：{selected.method === 'legacy_value' ? '互換入力（Legacy SetValue）' : '標準入力（ValuePattern）'}。失敗しても別方式での再入力はしません。</p>}
            {selected?.kind === 'input' && <label className="still-check"><input type="checkbox" checked={replace} onChange={(e) => { setReplace(e.target.checked); setActionConsent(false); }} />選択した入力欄の既存内容の置換を許可します。</label>}
            <label className="still-check"><input type="checkbox" checked={actionConsent} onChange={(e) => setActionConsent(e.target.checked)} />対象と内容を確認し、今回の1回の操作を許可します。</label>
            <button type="button" className="button button-primary" disabled={!selected || !actionConsent || (selected.kind === 'input' && (!text || (selected.characters > 0 && !replace)))} onClick={() => { if (selected) void act(selected.kind); }}>{selected?.kind === 'input' ? '未送信の文章を入力する' : '選択したタブへ切り替える'}</button>
          </>}
        </>}
      </fieldset>
      <label>Claudeに入力する文章（未送信）<textarea aria-label="Claudeに入力する文章（未送信）" rows={4} maxLength={4000} disabled={blocked} value={text} onChange={(e) => { setText(e.target.value); setActionConsent(false); }} placeholder="例：カフェの告知文を3案、各40文字以内で作成してください。" /></label>
      <p className="still-muted">文章はこの画面のメモリだけに保持します。ログ・ブラウザ保存領域には残しません。閉じる前に必要なら控えてください。</p>
      {pending && <div className="still-warning">{unresolved ? '受付記録が見つかりません。自動で再実行しません。' : '受付済み操作の結果を確認中です。'}<button type="button" onClick={() => { setUnresolved(false); void refresh(); }}>受付を再確認</button>{unresolved && <button type="button" onClick={() => { if (window.confirm('Claudeの実画面と操作履歴を確認しましたか？遅れて操作が反映される可能性があります。解除しても処理は停止しません。')) { localStorage.removeItem(CONTROL_PENDING_KEY); setPending(''); setUnresolved(false); reset(); onChanged(); } }}>実画面を確認して受付確認を解除</button>}</div>}
      <details><summary>操作履歴（最新50件・入力文なし）</summary><button type="button" onClick={() => void refresh()}>操作履歴を更新</button><ul>{history.map((item) => <li key={item.id}>{new Date(item.created_at).toLocaleString('ja-JP')} · {label[item.operation]} · {item.characters}字 · {outcomeLabel[item.outcome]}（{item.status}）</li>)}</ul></details>
    </div>}
  </section>;
}

import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { ClaudeCaptureInspection } from './types';

/** Window selection is ephemeral. Never save the token, title or HWND. */
export default function ClaudeStillSelector({ kind = 'claude', value, onSelect }: { kind?: 'claude' | 'terminal'; value?: string; onSelect: (value?: string) => void }) {
  const terminal = kind === 'terminal';
  const label = terminal ? 'Windows Terminal' : 'Claude';
  const [inspection, setInspection] = useState<ClaudeCaptureInspection>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const alive = useRef(true);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latestSelect = useRef(onSelect); latestSelect.current = onSelect;
  useEffect(() => { alive.current = true; return () => { alive.current = false; clearTimeout(timer.current); }; }, []);
  const inspect = async () => {
    clearTimeout(timer.current); onSelect(undefined); setInspection(undefined); setMessage(''); setBusy(true);
    const started = Date.now();
    try {
      const result = await (terminal ? api.inspectTerminalStill() : api.inspectClaudeCapture());
      if (!alive.current) return;
      setInspection(result);
      if (!result.available || !result.targets.length) {
        setMessage(`撮影可能な${label}ウィンドウがありません。${terminal ? 'Microsoft Store安定版' : '公式MSIX版'}を開き、最小化を解除して再確認してください。`);
        return;
      }
      const lifetime = result.expiresInSeconds * 1000 - (Date.now() - started);
      timer.current = setTimeout(() => {
        if (!alive.current) return;
        setInspection(undefined); latestSelect.current(undefined); setMessage('選択の有効期限が切れました。ウィンドウを再確認してください。');
      }, Math.max(0, lifetime));
    } catch {
      if (alive.current) setMessage(`対象を確認できませんでした。Studioへの接続と${label}の状態を確認してください。`);
    } finally { if (alive.current) setBusy(false); }
  };
  return <section className="claude-still-selector" aria-label={`${label}の撮影対象`}>
    <p className="still-muted">{label}に表示中の内容を原寸PNGで1枚撮影します。会話送信・スクロール・音声収録はしません。撮影が終わるまでウィンドウを動かさないでください。</p>
    {terminal && <p className="still-warning">Claude Code CLIを表示した状態で選択してください。CLIの実行状態は自動判定しません。コマンド実行・タブ切替は行いません。ウィンドウ全体（タブ名・分割ペインを含む）が写ります。候補を区別できない場合は、撮影対象だけを表示して再確認してください。</p>}
    <button type="button" className="button button-secondary" disabled={busy} onClick={() => void inspect()}>{busy ? '対象を確認中…' : `${label}ウィンドウを確認`}</button>
    <p className="still-muted">この確認だけでは撮影しません。対象名は匿名表示です。選択後、下の許可チェックを入れて撮影してください。</p>
    {message && <p role="status">{message}</p>}
    {inspection?.targets.map((item) => <label key={item.selectionToken} className="still-check">
      <input type="radio" name="claude-still-window" checked={value === item.selectionToken} onChange={() => onSelect(item.selectionToken)} />
      {item.label} — {item.width} × {item.height}（対象確認時のサイズ）
    </label>)}
    {inspection?.available && <p className="still-muted">選択は最大60秒・1回限り有効です。撮り直し時は再確認します。最終PNGのピクセル寸法はWindowsの表示倍率等で異なる場合があります。</p>}
  </section>;
}

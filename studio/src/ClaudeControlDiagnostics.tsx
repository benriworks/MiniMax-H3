import type { ControlDiagnostics } from './claudeControlApi';

/** Explicit projection: never serialize the inspection, draft, target IDs or tokens. */
function downloadReport(value: ControlDiagnostics) {
  const report = {
    report_version: 1, engine: value.engine, view: value.view,
    inspected_nodes: value.inspected_nodes, documents: value.documents, hidden_nodes: value.hidden_nodes,
    unsupported_editors: value.unsupported_editors, supported_inputs: value.supported_inputs, supported_tabs: value.supported_tabs,
    evidence: 'inspection_only_not_action_acceptance',
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'claude-control-diagnostics.json';
  anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ClaudeControlDiagnostics({ value }: { value: ControlDiagnostics }) {
  const inputs = value.supported_inputs > 0, tabs = value.supported_tabs > 0;
  return <section className="claude-control-diagnostics" aria-label="Claude操作の確認結果">
    <h4>直近の確認結果</h4>
    <p className="still-muted">操作の許可や実機試験の合格を示すものではありません。画面が変わったら再確認してください。</p>
    <dl className="claude-control-capabilities">
      <div><dt>タブ切替</dt><dd>{tabs ? `${value.supported_tabs}件の候補` : '候補なし'}</dd></div>
      <div><dt>未送信の入力</dt><dd>{inputs ? `${value.supported_inputs}件の候補` : '候補なし'}</dd></div>
    </dl>
    <p>{!inputs && !tabs ? '自動入力・切替は利用できません。操作対象を確認できていません。' : !inputs ? 'タブ候補のみ取得しました。入力欄は確認できていません。' : !tabs ? '入力欄候補のみ取得しました。タブ切替は手動で行ってください。' : '候補の位置と、いまClaudeで見えている画面が一致することを確認してください。'}</p>
    {value.unsupported_editors > 0 && <p>書き込み方法を確認できない欄が{value.unsupported_editors}件あります。読み取り専用や非対応の可能性があるため、自動入力の対象から外しています。</p>}
    {(!inputs || !tabs) && <ol>
      <li>Claudeの表示が落ち着くまで待ち、撮りたいタブを表示する。</li>
      <li>「操作対象を選び直す」から、ウィンドウと候補を確認し直す。</li>
      <li>表示と候補が一致しなければ操作せず、Claudeを手動で準備して撮影する。</li>
    </ol>}
    <details><summary>取得方式と診断（会話・入力文なし）</summary>
      <p>UIA3 / Raw · 調査 {value.inspected_nodes}要素 · 文書 {value.documents} · 非表示・無効などで除外 {value.hidden_nodes}要素</p>
      <p className="still-muted">除外数だけでは原因を断定できません。診断JSONに文章・画面名・パス・操作ID・トークンは含めません。自動送信や自動保存もしません。</p>
      <button type="button" className="button button-secondary" onClick={() => downloadReport(value)}>診断JSONを保存</button>
    </details>
  </section>;
}

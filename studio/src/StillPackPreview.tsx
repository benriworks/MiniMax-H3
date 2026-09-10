import { useEffect, useRef, useState } from 'react';
import { planApi, type StillPlan, type PackPreview } from './stillPlanApi';

export default function StillPackPreview({ plan, disabled }: { plan: StillPlan; disabled: boolean }) {
  const [preview, setPreview] = useState<PackPreview>();
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0);
  useEffect(() => { generation.current++; setPreview(undefined); setConfirmed(false); setError(''); return () => { generation.current++; }; }, [plan.id, plan.revision, disabled]);
  const review = async () => {
    const current = generation.current;
    setBusy(true); setError(''); setConfirmed(false); setPreview(undefined);
    try { const result = await planApi.preview(plan.id); if (current === generation.current) setPreview(result); }
    catch (failure) { if (current === generation.current) setError(failure instanceof Error ? failure.message : '確認できませんでした。'); }
    finally { setBusy(false); }
  };
  const download = async () => {
    if (!preview?.ready || !confirmed || disabled || busy) return;
    setBusy(true); setError('');
    try {
      const blob = await planApi.export(preview), url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = `${preview.snapshot.plan_id}-r${preview.snapshot.revision}.zip`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch (failure) { setError(failure instanceof Error ? failure.message : '書き出せませんでした。'); setConfirmed(false); setPreview(undefined); }
    finally { setBusy(false); }
  };
  return <section className="still-pack" aria-label="記事素材パック">
    <h4>記事素材パック — 場面順にまとめて持ち出す</h4>
    <p className="still-muted">PNGとARTICLE.md（見出し・説明・素材メモ）、検証用manifestをZIPにします。記事本文の自動執筆・投稿はしません。</p>
    <button type="button" disabled={disabled || busy || !plan.revision} onClick={() => void review()}>素材パックの内容を確認</button>
    {error && <p role="alert" className="still-error">{error}</p>}
    {preview && <>
      <p>確認対象：{preview.snapshot.title} · 手順版{preview.snapshot.revision} · {Math.ceil(preview.total_bytes / 1024)} KiB</p>
      {preview.blockers.map((blocker) => <p key={blocker} role="status" className="still-error">{blocker}</p>)}
      <ol className="still-pack-grid">{preview.snapshot.steps.map((step) => <li key={step.id}>
        <strong>{step.order}. {step.title}</strong>
        {step.image && <a href={`/api/stills/${step.image.id}/file`} target="_blank" rel="noreferrer"><img src={`/api/stills/${step.image.id}/file`} alt={`場面${step.order}の確認画像`} loading="lazy" />原寸で確認 ↗</a>}
        <p>{step.memo || '場面説明なし'}</p>
        {step.image && <><small>素材名：{step.image.title} / メモ版{step.image.revision}</small><p>{step.image.memo || '素材メモなし'}</p></>}
      </li>)}</ol>
      <label className="still-check"><input type="checkbox" disabled={!preview.ready || disabled || busy} checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />全場面の画像・見出し・説明・素材メモに公開できない情報がないことを確認しました。</label>
      <button type="button" className="button button-primary" disabled={!preview.ready || !confirmed || disabled || busy} onClick={() => void download()}>記事素材パックをZIPで保存</button>
    </>}
  </section>;
}

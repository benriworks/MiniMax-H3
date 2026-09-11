import { useEffect, useRef, useState } from 'react';
import { StillApiError, type StillImage } from './stillLibraryApi';
import { planApi, planId, type AdoptionRequest, type CaptureComparison, type StillPlan } from './stillPlanApi';

export default function StillCaptureReview({ item, locked, onBusy, onAdopted }: {
  item: StillImage; locked: boolean; onBusy: (busy: boolean) => void; onAdopted: (plan: StillPlan) => void;
}) {
  const [comparison, setComparison] = useState<CaptureComparison>();
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [uncertain, setUncertain] = useState(false);
  const [loaded, setLoaded] = useState<string[]>([]), [imageError, setImageError] = useState(false);
  const attempt = useRef<AdoptionRequest | undefined>(undefined);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { if (locked) setConfirmed(false); }, [locked]);
  const compare = async () => {
    if (!item.plan_capture || locked || busy) return;
    setBusy(true); onBusy(true); setError(''); setNotice(''); setConfirmed(false); setComparison(undefined); setLoaded([]); setImageError(false);
    try {
      const value = await planApi.compare(item.plan_capture, item.id);
      if (alive.current) {
        setComparison(value);
        if (value.adopted) {
          const plan = await planApi.get(item.plan_capture.plan_id);
          if (alive.current) { setUncertain(false); attempt.current = undefined; onAdopted(plan); }
        }
      }
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : '比較できませんでした。'); }
    finally { onBusy(false); if (alive.current) setBusy(false); }
  };
  const adopt = async () => {
    if (!item.plan_capture || !comparison?.ready || locked || busy || (!uncertain && !confirmed) || imageError || !allLoaded) return;
    const request = attempt.current ?? { operation_id: planId('planedit'), expected_revision: comparison.snapshot.base_revision, review_digest: comparison.review_digest, confirm_adoption: true as const };
    attempt.current = request;
    setBusy(true); onBusy(true); setError('');
    try {
      const plan = await planApi.adopt(item.plan_capture, item.id, request);
      if (alive.current) { onAdopted(plan); setComparison(undefined); setConfirmed(false); setUncertain(false); attempt.current = undefined; setNotice('場面に採用しました。手順の新しい版を保存し、元画像は残しています。'); }
    } catch (failure) {
      if (alive.current) {
        setError(failure instanceof Error ? failure.message : '採用結果を確認できませんでした。');
        if (failure instanceof StillApiError && failure.status < 500) { setComparison(undefined); setUncertain(false); attempt.current = undefined; }
        else setUncertain(true);
      }
    } finally { onBusy(false); if (alive.current) setBusy(false); }
  };
  const snapshot = comparison?.snapshot;
  const allLoaded = !!snapshot?.after && loaded.includes('after') && (!snapshot.before || loaded.includes('before'));
  return <section className="still-capture-review" aria-label="場面画像の比較と採用">
    <h3>03　比較して場面に採用</h3>
    <p className="still-muted">撮影だけでは手順を変更しません。比較後に、この場面だけを更新します。元画像・旧版は残ります。</p>
    {locked && !busy && <p className="still-warning">未保存の編集や処理を終えてから比較・採用してください。</p>}
    {error && <p role="alert" className="still-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {uncertain && <p className="still-warning">採用結果が未確認です。自動では再送しません。「比較・採用状況を確認」で読み直すか、同じ操作IDで再確認してください。</p>}
    <button type="button" className="button button-secondary" disabled={locked || busy} onClick={() => void compare()}>比較・採用状況を確認</button>
    {snapshot && <>
      <p><strong>{snapshot.plan_title} / {snapshot.step_title}</strong><br />撮影時の手順：版{snapshot.base_revision} · 現在：版{snapshot.current_revision}</p>
      {comparison.blockers.map((blocker) => <p key={blocker} className="still-warning">{blocker}</p>)}
      <div className="still-comparison-grid">{(['before', 'after'] as const).map((role) => {
        const image = snapshot[role];
        return <figure key={role}><figcaption>{role === 'before' ? '採用前の画像' : '今回撮影した画像'}</figcaption>
          {image ? <><a href={image.image_url} target="_blank" rel="noreferrer"><img src={image.image_url} alt={role === 'before' ? '採用前の画像' : '今回撮影した画像'} onLoad={() => setLoaded((values) => values.includes(role) ? values : [...values, role])} onError={() => { setImageError(true); setConfirmed(false); }} /></a>
            <strong>{image.title}</strong><p>{image.media?.width} × {image.media?.height} · メモ版{image.revision}</p><p className="still-comparison-memo">{image.memo || 'メモなし'}</p><small>クリックでPNGを原寸表示</small></> : <p>{role === 'before' ? '画像未割り当て — 初回の採用です' : '撮影画像が未完成です'}</p>}
        </figure>;
      })}</div>
      {snapshot.before?.media?.sha256 === snapshot.after?.media?.sha256 && snapshot.before && <p className="still-muted">両画像のSHA-256は同一です。画素データに変更はありません。</p>}
      {imageError && <p role="alert" className="still-error">比較画像を読み込めません。採用せず、画像と撮影結果を確認してください。</p>}
      <label className="still-check"><input type="checkbox" checked={confirmed} disabled={locked || busy || uncertain || !comparison.ready || !allLoaded || imageError} onChange={(event) => setConfirmed(event.target.checked)} />元画像と新画像を確認し、この場面への採用を許可します。</label>
      <button type="button" className="button button-primary" disabled={locked || busy || !comparison.ready || (!confirmed && !uncertain) || !allLoaded || imageError} onClick={() => void adopt()}>{uncertain ? '同じ採用操作を再確認' : 'この画像を場面に採用'}</button>
    </>}
  </section>;
}

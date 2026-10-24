import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import {
  contentApi,
  contentDiff,
  contentImageUrl,
  type ContentAsset,
  type ContentResponse,
  type ContentSummary,
} from './contentWorkspaceApi';
import './contentWorkspace.css';

const steps = ['調査・企画', '撮影計画', '主張と根拠', '共通素材', '人物・絵コンテ'];
const phaseLabel = (phase: string) =>
  ({
    researching: '調査中',
    awaiting_feedback: '企画を相談中',
    capture_planning: '撮影・構成の準備',
    storyboard_ready: '絵コンテ作成済み',
  })[phase] || phase;
const captureLabel = (state: string) =>
  ({
    uninspected: '未確認',
    available: '撮影可能・未撮影',
    blocked: '撮影困難',
    captured: '実画面保存済み',
  })[state] || state;
const message = (e: unknown) => (e instanceof Error ? e.message : '企画を開けませんでした。');

export default function ContentWorkspacePanel({ onClose }: { onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null),
    live = useRef(true),
    guard = useRef(false),
    sequence = useRef(0);
  const [items, setItems] = useState<ContentSummary[]>([]),
    [result, setResult] = useState<ContentResponse>();
  const [topic, setTopic] = useState(''),
    [feedback, setFeedback] = useState('');
  const [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [previous, setPrevious] = useState<ContentResponse>(),
    [notice, setNotice] = useState('');
  const project = result?.project;
  const pendingFeedback =
    result?.checks.blockers.includes('修正の相談を企画案へ反映する必要があります') ?? false;
  const reloadList = useCallback(async () => {
    const list = await contentApi.list();
    if (live.current) setItems(list.items);
  }, []);
  useEffect(() => {
    live.current = true;
    dialog.current?.showModal();
    void reloadList().catch((e) => {
      if (live.current) setError(message(e));
    });
    return () => {
      live.current = false;
      sequence.current += 1;
    };
  }, [reloadList]);
  useEffect(() => {
    if (!feedback.trim() && !busy) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [feedback, busy]);
  async function select(id: string) {
    const ticket = ++sequence.current;
    setError('');
    try {
      const value = await contentApi.get(id);
      if (live.current && ticket === sequence.current) {
        setResult(value);
        setPrevious(undefined);
        setFeedback('');
        setNotice('');
        void reloadList().catch((e) => {
          if (live.current) setError(message(e));
        });
      }
    } catch (e) {
      if (live.current && ticket === sequence.current) setError(message(e));
    }
  }
  async function perform(work: () => Promise<ContentResponse>) {
    if (guard.current) return false;
    guard.current = true;
    setBusy(true);
    setError('');
    sequence.current += 1;
    try {
      const value = await work();
      if (live.current) {
        setResult(value);
        setPrevious(undefined);
        setNotice('保存しました。');
        await reloadList();
      }
      return true;
    } catch (e) {
      if (live.current)
        setError(`${message(e)} 応答が不明な場合は、最新版を開いて保存結果を確認してください。`);
      return false;
    } finally {
      guard.current = false;
      if (live.current) setBusy(false);
    }
  }
  async function create(e: FormEvent) {
    e.preventDefault();
    if (await perform(() => contentApi.create(topic.trim()))) setTopic('');
  }
  async function saveFeedback(e: FormEvent) {
    e.preventDefault();
    if (!project?.proposals.length) return;
    const proposal = project.proposals.at(-1)!;
    const saved = await perform(() =>
      contentApi.apply(project, 'feedback', {
        feedback_id: `feedback_${crypto.randomUUID().replaceAll('-', '')}`,
        proposal_id: proposal.proposal_id,
        text: feedback,
        interpretation: 'チャットで意図を確認し、必要な構成変更へ反映する。',
      }),
    );
    if (saved) setFeedback('');
  }
  async function accept() {
    if (!project?.proposals.length) return;
    const current = project,
      proposal = current.proposals.at(-1)!,
      feedbackId = `feedback_${crypto.randomUUID().replaceAll('-', '')}`;
    await perform(async () => {
      const recorded = await contentApi.apply(current, 'feedback', {
        feedback_id: feedbackId,
        proposal_id: proposal.proposal_id,
        text: 'この企画案で制作を進めてください。',
        interpretation: '画面に表示した最新企画案の採用。',
        kind: 'acceptance',
      });
      return contentApi.apply(recorded.project, 'accept', {
        proposal_id: proposal.proposal_id,
        feedback_id: feedbackId,
        confirm_acceptance: true,
      });
    });
  }
  async function compare(revision: number) {
    if (!project || !revision) {
      setPrevious(undefined);
      return;
    }
    const ticket = ++sequence.current;
    try {
      const old = await contentApi.get(project.content_project_id, revision);
      if (live.current && ticket === sequence.current) setPrevious(old);
    } catch (e) {
      if (live.current) setError(message(e));
    }
  }
  function thumbnail(asset: ContentAsset) {
    return asset.visibility === 'public' && /\.(png|jpe?g|webp)$/i.test(asset.path) ? (
      <img
        loading="lazy"
        src={contentImageUrl(project!.content_project_id, asset)}
        alt={asset.alt || asset.asset_id}
      />
    ) : (
      <p className="cw-muted">
        {asset.visibility === 'private' ? '非公開原本・プレビュー対象外' : '動画・音声素材'}
      </p>
    );
  }
  return (
    <dialog
      className="content-workspace"
      ref={dialog}
      aria-labelledby="cw-title"
      onCancel={(e) => {
        if (busy || feedback.trim()) {
          e.preventDefault();
          setError(
            '保存中、または未送信のメモがあります。送信するか、メモを消してから閉じてください。',
          );
        } else onClose();
      }}
    >
      <header>
        <div>
          <p className="cw-eyebrow">VIDEO + BLOG</p>
          <h2 id="cw-title">動画と記事の企画</h2>
          <p>チャットで相談し、調べたこと・決めたこと・素材をひとつにつなぎます。</p>
        </div>
        <button
          className="button button-secondary"
          disabled={busy || !!feedback.trim()}
          onClick={onClose}
        >
          閉じる
        </button>
      </header>
      {error && (
        <p role="alert" className="cw-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="cw-notice">
          {notice}
        </p>
      )}
      <div className="cw-layout">
        <aside>
          <form onSubmit={create}>
            <label>
              調べたいテーマ
              <input
                aria-label="調べたいテーマ"
                maxLength={250}
                required
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="例：AIで会議メモを資料にする"
              />
            </label>
            <button className="button" disabled={busy || !topic.trim() || !!feedback.trim()}>
              企画を始める
            </button>
          </form>
          <p className="cw-muted">
            登録後、チャットで調査と本数・各回の概要を提案します。ここでフォームを埋める必要はありません。
          </p>
          <nav aria-label="企画一覧">
            {items.map((item) => (
              <button
                type="button"
                key={item.content_project_id}
                disabled={busy || !!feedback.trim()}
                aria-current={
                  project?.content_project_id === item.content_project_id ? 'page' : undefined
                }
                onClick={() => void select(item.content_project_id)}
              >
                <strong>{item.title}</strong>
                <small>
                  {item.archived ? '保管中' : phaseLabel(item.phase)} · v{item.revision}
                </small>
              </button>
            ))}
          </nav>
        </aside>
        <main>
          {!project || !result ? (
            <div className="cw-empty">企画を選ぶと、調査から絵コンテまで確認できます。</div>
          ) : (
            <>
              <div className="cw-title-row">
                <div>
                  <h3>{project.title}</h3>
                  <p>
                    {phaseLabel(project.phase)} · v{project.revision}
                    {project.archived ? ' · 保管中' : ''}
                  </p>
                </div>
                <button
                  className="button button-secondary"
                  disabled={busy || !!feedback.trim()}
                  onClick={() => void select(project.content_project_id)}
                >
                  最新版を開く
                </button>
              </div>
              <div className="cw-version">
                <label>
                  以前の版と比較
                  <select
                    value={previous?.project.revision || ''}
                    onChange={(e) => void compare(Number(e.target.value))}
                  >
                    <option value="">比較する版を選択</option>
                    {result.history
                      ?.filter((h) => h.revision < project.revision)
                      .map((h) => (
                        <option key={h.revision} value={h.revision}>
                          v{h.revision} · {h.action}
                        </option>
                      ))}
                  </select>
                </label>
                {previous && (
                  <p>
                    変更した項目：{contentDiff(previous.project, project).join('、') || '変更なし'}
                  </p>
                )}
              </div>
              <nav className="cw-steps" aria-label="制作工程">
                {steps.map((label, index) => (
                  <button
                    type="button"
                    key={label}
                    aria-current={step === index ? 'step' : undefined}
                    onClick={() => setStep(index)}
                  >
                    {index + 1}. {label}
                  </button>
                ))}
              </nav>
              <section className="cw-checks" aria-label="制作前の確認">
                <strong>
                  {result.checks.ready_for_production
                    ? '制作準備の記録がそろっています'
                    : '制作前に確認すること'}
                </strong>
                <ul>
                  {result.checks.blockers.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
                {result.checks.warnings.length > 0 && (
                  <details>
                    <summary>補足・素材の準備状況</summary>
                    <ul>
                      {result.checks.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </details>
                )}
                <small>技術検証・人の試聴・公開状況とは別の確認です。</small>
              </section>
              {step === 0 && (
                <section>
                  <p>
                    想定視聴者：{project.request.audience} ／ ショートを基本に内容に合う尺を提案
                  </p>
                  <h3>調査</h3>
                  {!project.research.length && (
                    <p className="cw-empty">
                      調査結果の登録待ちです。チャットでこのテーマを調べます。
                    </p>
                  )}
                  {project.research.map((r) => (
                    <article key={r.research_id} className="cw-card">
                      <p className="cw-prose">{r.summary}</p>
                      <small>確認：{r.checked_at}</small>
                      <ul>
                        {r.sources.map((s) => (
                          <li key={s.source_id}>
                            <a href={s.url} target="_blank" rel="noreferrer">
                              {s.title}
                            </a>{' '}
                            ·{' '}
                            {s.kind === 'official'
                              ? '公式'
                              : s.kind === 'first_hand'
                                ? '一次情報'
                                : '参考情報'}
                            <small>
                              確認 {s.checked_at}
                              {s.published_at ? ` ／ 発表 ${s.published_at}` : ''}
                              {s.event_at ? ` ／ 出来事 ${s.event_at}` : ''}
                            </small>
                            {s.conditions && <p>{s.conditions}</p>}
                          </li>
                        ))}
                      </ul>
                      {r.unknowns?.length ? <p>未確認：{r.unknowns.join('、')}</p> : null}
                    </article>
                  ))}
                  <h3>推奨する動画構成</h3>
                  {project.proposals.length ? (
                    <>
                      <p className="cw-count">
                        全{project.proposals.at(-1)!.episodes.length}本の提案
                      </p>
                      <p>{project.proposals.at(-1)!.count_reason}</p>
                      {project.proposals.at(-1)!.episodes.map((e, i) => (
                        <article className="cw-card" key={e.episode_id}>
                          <small>
                            第{i + 1}回 · 約{e.duration_seconds}秒
                          </small>
                          <h4>{e.title}</h4>
                          <p className="cw-message">伝えたいこと：{e.intended_message}</p>
                          <p>{e.overview}</p>
                          <dl>
                            <dt>見せる画面</dt>
                            <dd>{e.demo_idea}</dd>
                            <dt>ブログで詳しく</dt>
                            <dd>{e.article_role}</dd>
                          </dl>
                        </article>
                      ))}
                      <form onSubmit={saveFeedback}>
                        <label>
                          伝えたいこと・直したいところ
                          <textarea
                            rows={4}
                            value={feedback}
                            onChange={(e) => setFeedback(e.target.value)}
                            placeholder="例：第2回は共同編集の便利さを中心にしたい"
                          />
                        </label>
                        <button
                          className="button button-secondary"
                          disabled={busy || !feedback.trim() || project.archived}
                        >
                          相談メモを保存
                        </button>
                      </form>
                      <p className="cw-muted">
                        メモはチャットで意図を整理して反映します。保存だけで構成の採用にはなりません。
                      </p>
                      <button
                        className="button"
                        disabled={
                          busy ||
                          pendingFeedback ||
                          !!feedback.trim() ||
                          project.archived ||
                          project.accepted_proposal?.proposal_id ===
                            project.proposals.at(-1)!.proposal_id
                        }
                        onClick={() => void accept()}
                      >
                        この企画案で進める
                      </button>
                      <details>
                        <summary>これまでの相談</summary>
                        {project.feedback.map((f) => (
                          <article key={f.feedback_id}>
                            <p>{f.text}</p>
                            <small>反映方針：{f.interpretation}</small>
                          </article>
                        ))}
                      </details>
                    </>
                  ) : (
                    <p className="cw-empty">調査後、本数と各回の概要を提案します。</p>
                  )}
                </section>
              )}
              {step === 1 && (
                <section>
                  <h3>実画面の確認と撮影リスト</h3>
                  {(project.capture_inspections || []).map((inspection) => (
                    <article className="cw-card" key={inspection.inspection_id}>
                      <h4>企画前の確認：{inspection.target_feature}</h4>
                      <p>
                        {captureLabel(inspection.status)} · {inspection.checked_at}
                      </p>
                      <p>{inspection.result}</p>
                    </article>
                  ))}
                  {project.episodes.length === 0 && (
                    <p>企画採用後、各回に必要な画面を整理します。</p>
                  )}
                  {project.episodes.map((e) => (
                    <article className="cw-card" key={e.episode_id}>
                      <h4>{e.title}</h4>
                      <p className="cw-message">{captureLabel(e.capture_plan.status)}</p>
                      <p>{e.capture_plan.result}</p>
                      {e.capture_plan.route && (
                        <details>
                          <summary>試した経路</summary>
                          <p>{e.capture_plan.route}</p>
                        </details>
                      )}
                      <ul>
                        {e.capture_plan.shots.map((s) => (
                          <li key={s.shot_id}>
                            {s.purpose} · {s.asset_id ? `素材：${s.asset_id}` : '未撮影'}
                          </li>
                        ))}
                      </ul>
                    </article>
                  ))}
                </section>
              )}
              {step === 2 && (
                <section>
                  <h3>何を根拠に伝えるか</h3>
                  {!project.claims.length && (
                    <p className="cw-empty">各回で伝える内容と根拠を登録します。</p>
                  )}
                  {project.claims.map((c) => (
                    <article
                      className={`cw-card ${c.needs_review ? 'cw-stale' : ''}`}
                      key={c.claim_id}
                    >
                      <small>
                        {c.basis === 'official'
                          ? '公式情報'
                          : c.basis === 'tested'
                            ? '実機で確認'
                            : '推測・未検証'}{' '}
                        · {c.checked_at}
                      </small>
                      <p>{c.text}</p>
                      <p className="cw-muted">
                        出典：{c.source_ids.join('、') || 'なし'} ／ 実演：
                        {c.asset_ids?.join('、') || 'なし'}
                        {c.needs_review ? ' ／ 再確認が必要' : ''}
                      </p>
                    </article>
                  ))}
                </section>
              )}
              {step === 3 && (
                <section>
                  <h3>動画と記事で使う素材</h3>
                  <p>原本と派生素材を区別し、差し替えても過去版を残します。</p>
                  {project.assets.length === 0 && <p className="cw-empty">素材は準備中です。</p>}
                  <div className="cw-grid">
                    {project.assets.map((a) => (
                      <article className="cw-card" key={a.asset_id}>
                        {thumbnail(a)}
                        <h4>
                          {a.asset_id} · v{a.version}
                        </h4>
                        <p>{a.caption || a.kind}</p>
                        <small>
                          {a.visibility === 'public' ? '公開用' : '非公開'} ／{' '}
                          {(a.bytes / 1024).toFixed(1)} KB
                        </small>
                        {a.parent_asset_id && <p>派生元：{a.parent_asset_id}</p>}
                        <details>
                          <summary>保存情報</summary>
                          <p>{a.path}</p>
                          <small>{a.sha256}</small>
                        </details>
                      </article>
                    ))}
                  </div>
                </section>
              )}
              {step === 4 && (
                <section>
                  <h3>シリーズの人物</h3>
                  {project.characters.length === 0 && (
                    <p className="cw-muted">
                      人物設定は未登録です。人物を使う場合は、参照画像と役割をチャットで確認します。
                    </p>
                  )}
                  <div className="cw-grid">
                    {project.characters.map((c) => {
                      const asset = project.assets.find((a) => a.asset_id === c.reference_asset_id);
                      return (
                        <article className="cw-card" key={c.character_id}>
                          {asset && thumbnail(asset)}
                          <h4>
                            {c.name} · v{c.version}
                          </h4>
                          <p>{c.persona}</p>
                          <p>役割：{c.role}</p>
                          <p>
                            衣装：{c.clothing} ／ 口調：{c.voice}
                          </p>
                          <p>継続設定：{c.continuity}</p>
                          <strong>
                            {c.approval
                              ? `確認済み：${c.approval.scope}`
                              : 'ユーザー確認待ち・本番人物動画の生成前'}
                          </strong>
                        </article>
                      );
                    })}
                  </div>
                  <h3>絵コンテ</h3>
                  {project.episodes.map((e) => (
                    <article key={e.episode_id}>
                      <h4>{e.title}</h4>
                      <div className="cw-grid">
                        {e.storyboard.map((s, index) => (
                          <section
                            key={s.scene_id}
                            className={`cw-card ${s.needs_review ? 'cw-stale' : ''}`}
                          >
                            <small>
                              場面{index + 1} · {s.duration_seconds}秒
                            </small>
                            <h4>{s.purpose}</h4>
                            <p className="cw-message">{s.visual}</p>
                            <p>{s.narration}</p>
                            {s.character_action && <p>人物の動き：{s.character_action}</p>}
                            <small>
                              根拠：{s.claim_ids?.join('、') || '未割当'} ／ 素材：
                              {s.asset_ids?.join('、') || '準備中'}
                            </small>
                            {s.needs_review && <p>再確認：{s.review_reasons.join('、')}</p>}
                          </section>
                        ))}
                      </div>
                    </article>
                  ))}
                </section>
              )}
            </>
          )}
        </main>
      </div>
      <footer>
        制作の窓口はチャットです。共有はGoogle Driveを優先し、S3は代替として扱います。
      </footer>
    </dialog>
  );
}

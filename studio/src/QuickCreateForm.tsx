import { useRef, useState } from 'react';
import type { AnnouncementSceneRole, Artifact, LocalRemotionTimelineVisualPreset } from './types';
import {
  canSharpenLowResolutionPortrait,
  contentCopyAdvice,
  contentCopyMetrics,
  contentMediaAdvice,
  contentMediaFacts,
  contentPreviewPlaybackAction,
  contentPreviewRange,
} from './contentQuality';
import './contentQuality.css';

export type QuickCreateSceneDraft = {
  role: AnnouncementSceneRole;
  videoArtifactId: string;
  startMs: string;
  endMs: string;
  headline: string;
  narration: string;
  visualPreset?: LocalRemotionTimelineVisualPreset;
};

type QuickCreateFormProps = {
  recipeName: string;
  scenes: QuickCreateSceneDraft[];
  videoArtifacts: Artifact[];
  outputDurationMs: number;
  validationErrors: string[];
  disabled: boolean;
  onRecipeNameChange: (value: string) => void;
  onSceneArtifactChange: (sceneIndex: number, artifactId: string) => void;
  onSceneHeadlineChange: (sceneIndex: number, value: string) => void;
  onSceneNarrationChange: (sceneIndex: number, value: string) => void;
  onSceneVisualPresetChange?: (sceneIndex: number, value: LocalRemotionTimelineVisualPreset) => void;
};

const QUICK_SCENE_META: Record<AnnouncementSceneRole, {
  number: string;
  title: string;
  purpose: string;
  headlineLabel: string;
}> = {
  hook: {
    number: '1',
    title: 'つかみ',
    purpose: '最初の5秒で目を止める',
    headlineLabel: '画面に出す一言',
  },
  message: {
    number: '2',
    title: '伝えたいこと',
    purpose: 'いちばん大切な内容を伝える',
    headlineLabel: '画面に出す要点',
  },
  cta: {
    number: '3',
    title: '最後の案内',
    purpose: '見た人に次の行動を案内する',
    headlineLabel: '画面に出す案内',
  },
};

const formatQuickBytes = (bytes?: number): string => {
  if (bytes === undefined) return 'サイズ不明';
  if (bytes < 1_024 * 1_024) return `${Math.max(1, Math.round(bytes / 1_024))} KB`;
  return `${(bytes / (1_024 * 1_024)).toFixed(1)} MB`;
};

const formatQuickDuration = (seconds?: number): string => (
  seconds === undefined ? '尺不明' : `${seconds.toFixed(1)}秒`
);

const formatQuickMilliseconds = (milliseconds: number): string => {
  const seconds = milliseconds / 1_000;
  return `${Number.isInteger(seconds) ? seconds.toFixed(0) : seconds.toFixed(1)}秒`;
};

function QuickScenePreview({ scene, artifact }: { scene: QuickCreateSceneDraft; artifact: Artifact }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [unavailable, setUnavailable] = useState(false);
  const range = contentPreviewRange(scene.startMs, scene.endMs, contentMediaFacts(artifact).durationSeconds);
  const helpId = `quick-create-preview-${scene.role}-help`;

  const resetToStart = (video: HTMLVideoElement) => {
    const boundedRange = contentPreviewRange(scene.startMs, scene.endMs, video.duration);
    if (!boundedRange.valid) return;
    try {
      video.currentTime = boundedRange.startSeconds;
    } catch {
      // Some codecs cannot seek until enough data is buffered. Native controls remain usable.
    }
  };

  const keepInsideRange = (video: HTMLVideoElement) => {
    const boundedRange = contentPreviewRange(scene.startMs, scene.endMs, video.duration);
    const action = contentPreviewPlaybackAction(video.currentTime, boundedRange);
    if (action.pause) video.pause();
    if (action.seekSeconds !== undefined) {
      try { video.currentTime = action.seekSeconds; } catch { /* Native decoder may still be loading. */ }
    }
  };

  if (!artifact.url || unavailable) {
    return <p className="quick-create-preview-unavailable" role="status">この素材をブラウザーで再生できません。素材の選択や文章の編集は続けられます。別の素材を選ぶか、成果物一覧から動画を確認してください。</p>;
  }

  return (
    <figure className="quick-create-source-preview">
      <div className="quick-create-source-frame">
        <video
          ref={videoRef}
          src={artifact.url}
          controls
          preload="metadata"
          playsInline
          muted
          aria-label={`${QUICK_SCENE_META[scene.role].title}の素材動画`}
          aria-describedby={helpId}
          onLoadedMetadata={(event) => resetToStart(event.currentTarget)}
          onPlay={(event) => {
            if (!range.valid) { event.currentTarget.pause(); return; }
            if (event.currentTarget.currentTime < range.startSeconds || event.currentTarget.currentTime >= range.endSeconds) {
              resetToStart(event.currentTarget);
            }
          }}
          onTimeUpdate={(event) => keepInsideRange(event.currentTarget)}
          onSeeking={(event) => keepInsideRange(event.currentTarget)}
          onSeeked={(event) => keepInsideRange(event.currentTarget)}
          onError={() => setUnavailable(true)}
        />
        {scene.headline.trim() && <p className={`quick-create-source-headline role-${scene.role}`} aria-hidden="true">{scene.headline}</p>}
      </div>
      <div className="quick-create-source-actions">
        <button type="button" disabled={!range.valid} onClick={() => {
          const video = videoRef.current;
          if (!video) return;
          resetToStart(video);
          void video.play().catch(() => { /* The native play control remains available if playback is refused. */ });
        }}>使う範囲を再生</button>
        <span>{range.valid ? `${range.startSeconds.toFixed(2)}〜${range.endSeconds.toFixed(2)}秒` : '使用範囲を確認してください'}</span>
      </div>
      <figcaption id={helpId}>
        <strong>素材と見出しの確認用です</strong>
        完成プレビューではありません。読み上げ・字幕・場面のつなぎ・鮮明化は反映せず、見出しの位置と大きさも目安です。素材音は初期状態でミュートです。
      </figcaption>
    </figure>
  );
}

export function QuickCreateForm({
  recipeName,
  scenes,
  videoArtifacts,
  outputDurationMs,
  validationErrors,
  disabled,
  onRecipeNameChange,
  onSceneArtifactChange,
  onSceneHeadlineChange,
  onSceneNarrationChange,
  onSceneVisualPresetChange,
}: QuickCreateFormProps) {
  const selectedArtifactIds = scenes.map((scene) => scene.videoArtifactId).filter(Boolean);
  const distinctArtifactCount = new Set(selectedArtifactIds).size;
  const reusesVideo = selectedArtifactIds.length === 3 && distinctArtifactCount < 3;
  const recipeNameError = validationErrors.find((error) => error.includes('recipe名'));

  return (
    <div className="quick-create-form">
      <label className="field quick-create-name">
        <span>動画の管理名</span>
        <input
          maxLength={120}
          value={recipeName}
          disabled={disabled}
          aria-invalid={Boolean(recipeNameError)}
          aria-describedby="quick-create-name-help"
          onChange={(event) => onRecipeNameChange(event.target.value)}
          placeholder="例：夏のキャンペーン告知"
        />
        <small className={recipeNameError ? 'quick-create-field-error' : 'field-help'} id="quick-create-name-help">{recipeNameError ?? '完成動画には表示されません。後から見つけやすい名前を付けます。'}</small>
      </label>

      <ol className="quick-create-steps">
        <li className="quick-create-step">
          <div className="quick-create-step-heading">
            <span aria-hidden="true">1</span>
            <div><strong>3つの場面を選ぶ</strong><small>同じ動画を複数の場面で使っても構いません。</small></div>
          </div>
          {videoArtifacts.length === 0 && (
            <div className="quick-create-blocker" role="alert">
              <strong>使える動画素材がありません</strong>
              <p>先に「生成映像」で動画を作るか、この制作へ動画artifactを登録してください。</p>
            </div>
          )}
          <div className="quick-create-scene-grid">
            {scenes.map((scene, index) => {
              const meta = QUICK_SCENE_META[scene.role];
              const artifact = videoArtifacts.find((item) => item.id === scene.videoArtifactId);
              const mediaFacts = contentMediaFacts(artifact);
              const mediaAdvice = artifact ? contentMediaAdvice(mediaFacts) : [];
              const canSharpen = canSharpenLowResolutionPortrait(mediaFacts);
              const sharpeningSelected = scene.visualPreset === 'h3_low_res_sharp_v1';
              const fieldId = `quick-create-video-${scene.role}`;
              const helpId = `${fieldId}-help`;
              const sceneToken = scene.role.toUpperCase();
              const videoErrors = validationErrors.filter((error) => error.includes(sceneToken) && /(artifact|素材尺|開始|終了|trim)/.test(error));
              return (
                <fieldset className={`quick-create-scene role-${scene.role}`} key={scene.role} disabled={disabled}>
                  <legend><span>{meta.number}</span>{meta.title}</legend>
                  <p>{meta.purpose}</p>
                  <label className="field" htmlFor={fieldId}><span>使う動画</span></label>
                  <select
                    id={fieldId}
                    value={scene.videoArtifactId}
                    disabled={disabled || videoArtifacts.length === 0}
                    aria-invalid={!artifact || videoErrors.length > 0}
                    aria-describedby={helpId}
                    onChange={(event) => onSceneArtifactChange(index, event.target.value)}
                  >
                    <option value="">動画を選択</option>
                    {scene.videoArtifactId && !artifact && <option value={scene.videoArtifactId}>[利用不可] {scene.videoArtifactId}</option>}
                    {videoArtifacts.map((item) => (
                      <option key={item.id} value={item.id}>{item.name} · {formatQuickDuration(item.durationSeconds)}</option>
                    ))}
                  </select>
                  <small className={videoErrors.length > 0 ? 'quick-create-field-error' : 'quick-create-artifact-meta'} id={helpId}>
                    {videoErrors[0] ?? (artifact ? `${formatQuickDuration(mediaFacts.durationSeconds)} · ${formatQuickBytes(artifact.sizeBytes)} · ${formatQuickMilliseconds(Math.max(0, Number(scene.endMs) - Number(scene.startMs)) || 0)}を使用` : '素材を選んでください')}
                  </small>
                  {artifact && <>
                    <div className="quick-create-media-facts" aria-label="素材の情報">
                      <span>{mediaFacts.width && mediaFacts.height ? `${mediaFacts.width}×${mediaFacts.height}` : '画素数不明'}</span>
                      {mediaFacts.fps !== undefined && <span>{Number(mediaFacts.fps.toFixed(2))}fps</span>}
                      <span>{mediaFacts.hasAudio === undefined ? '素材音の有無は未確認' : mediaFacts.hasAudio ? '素材音あり' : '素材音なし'}</span>
                      {mediaFacts.videoCodec && <span>{mediaFacts.videoCodec}</span>}
                    </div>
                    <QuickScenePreview key={`${artifact.id}:${artifact.url}:${scene.startMs}:${scene.endMs}`} scene={scene} artifact={artifact} />
                    {mediaAdvice.length > 0 && <ul className="quick-create-advice" aria-label={`${meta.title}の素材確認のポイント`}>{mediaAdvice.map((item) => <li key={item.id}>{item.message}</li>)}</ul>}
                    {onSceneVisualPresetChange && <>
                      <label className="quick-create-sharp-option">
                        <input type="checkbox" checked={sharpeningSelected} disabled={disabled || (!canSharpen && !sharpeningSelected)} aria-describedby={`quick-create-sharp-${scene.role}-help`} onChange={(event) => {
                          if (!event.target.checked || canSharpen) onSceneVisualPresetChange(index, event.target.checked ? 'h3_low_res_sharp_v1' : 'preserve_v1');
                        }} />
                        <span>低解像度の縦素材を少し鮮明にする</span>
                      </label>
                      <small className="quick-create-sharp-help" id={`quick-create-sharp-${scene.role}-help`}>
                        {canSharpen ? '弱い固定補正を完成動画へ適用します。細部を復元する機能ではなく、処理時間は増えます。効果は完成後に確認してください。' : '確認できた画素数が対象条件に合う低解像度の縦素材で選べます。横素材や画素数不明の素材では選べません。'}
                        {sharpeningSelected && !canSharpen && ' 現在の素材では補正を外してください。'}
                      </small>
                    </>}
                  </>}
                </fieldset>
              );
            })}
          </div>
          {reusesVideo && <p className="quick-create-hint">同じ動画を再利用する構成です。別の動画があれば、場面ごとに変えると変化を出せます。</p>}
        </li>

        <li className="quick-create-step">
          <div className="quick-create-step-heading">
            <span aria-hidden="true">2</span>
            <div><strong>伝える言葉を入れる</strong><small>大見出しは2行まで、読み上げは短い1文が目安です。</small></div>
          </div>
          <div className="quick-create-copy-list">
            {scenes.map((scene, index) => {
              const meta = QUICK_SCENE_META[scene.role];
              const headlineId = `quick-create-headline-${scene.role}`;
              const narrationId = `quick-create-narration-${scene.role}`;
              const sceneToken = scene.role.toUpperCase();
              const headlineErrors = validationErrors.filter((error) => error.includes(sceneToken) && (error.includes('大見出し') || error.includes('半角英数字')));
              const narrationErrors = validationErrors.filter((error) => error.includes(sceneToken) && error.includes('ナレーション'));
              const durationSeconds = Math.max(0, Number(scene.endMs) - Number(scene.startMs)) / 1_000;
              const metrics = contentCopyMetrics(scene.headline, scene.narration, durationSeconds);
              const copyAdvice = contentCopyAdvice(scene.headline, scene.narration, durationSeconds);
              return (
                <fieldset className={`quick-create-copy role-${scene.role}`} key={scene.role} disabled={disabled}>
                  <legend><span>{meta.number}</span>{meta.title}</legend>
                  <label className="field" htmlFor={headlineId}>
                    <span>{meta.headlineLabel}</span>
                    <textarea
                      id={headlineId}
                      rows={2}
                      maxLength={80}
                      value={scene.headline}
                      disabled={disabled}
                      aria-invalid={headlineErrors.length > 0}
                      aria-describedby={[`${headlineId}-metrics`, ...(headlineErrors.length > 0 ? [`${headlineId}-error`] : [])].join(' ')}
                      onChange={(event) => onSceneHeadlineChange(index, event.target.value)}
                    />
                  </label>
                  {headlineErrors.length > 0 && <small className="quick-create-field-error" id={`${headlineId}-error`}>{headlineErrors[0]}</small>}
                  <small className="quick-create-copy-metrics" id={`${headlineId}-metrics`}>{metrics.headlineCharacters}文字 · {metrics.headlineLines}行 / 2行 · 最長行は全角約{metrics.longestHeadlineUnits}文字相当 / 10文字</small>
                  <div className="quick-create-narration">
                    <label className="field" htmlFor={narrationId}>
                      <span>読み上げる文章</span>
                      <textarea
                        id={narrationId}
                        rows={2}
                        maxLength={200}
                        value={scene.narration}
                        disabled={disabled}
                        aria-invalid={narrationErrors.length > 0}
                        aria-describedby={[`${narrationId}-metrics`, ...(narrationErrors.length > 0 ? [`${narrationId}-error`] : [])].join(' ')}
                        onChange={(event) => onSceneNarrationChange(index, event.target.value)}
                      />
                    </label>
                    {narrationErrors.length > 0 && <small className="quick-create-field-error" id={`${narrationId}-error`}>{narrationErrors[0]}</small>}
                    <small className="quick-create-copy-metrics" id={`${narrationId}-metrics`}>
                      <strong>使用 {metrics.usableSeconds.toFixed(1)}秒 · 読み上げ {metrics.spokenCharacterCount}文字</strong><br />
                      {metrics.spokenCharacterCount > 0
                        ? metrics.hasAmbiguousReading ? '英数字を含むため、秒数の目安は表示しません。' : `日本語の文字量からの目安：約${metrics.speechMinSeconds.toFixed(1)}〜${metrics.speechMaxSeconds.toFixed(1)}秒。`
                        : '短い1文を入力してください。'}
                      声・速さ・間・英数字の読み方で変わります。実際の長さは音声生成後に確認します。
                    </small>
                  </div>
                  {copyAdvice.length > 0 && <ul className="quick-create-advice" aria-label={`${meta.title}の文章のヒント`}>{copyAdvice.map((item) => <li key={item.id}>{item.message}</li>)}</ul>}
                </fieldset>
              );
            })}
          </div>
          <p className="quick-create-privacy">秘密情報、API token、公開したくない個人情報は入力しないでください。入力文は制作の監査履歴に保存されます。</p>
        </li>

        <li className="quick-create-step quick-create-review">
          <div className="quick-create-step-heading">
            <span aria-hidden="true">3</span>
            <div><strong>内容を確認して作成する</strong><small>下のボタンで保存、音声、編集、字幕、品質検査まで続けて実行します。</small></div>
          </div>
          <dl className="quick-create-settings">
            <div><dt>形式</dt><dd>縦 1080×1920・{formatQuickMilliseconds(outputDurationMs)}</dd></div>
            <div><dt>構成</dt><dd>3場面・250msフェード</dd></div>
            <div><dt>音声</dt><dd>Windowsローカル音声・素材音なし</dd></div>
            <div><dt>文字</dt><dd>大見出し＋読み上げ字幕</dd></div>
            <div><dt>処理</dt><dd>ローカルのみ・API費用0円</dd></div>
            <div><dt>確認</dt><dd>技術QCと成果物を記録</dd></div>
          </dl>
          <div className="quick-create-content-review">
            <strong>完成後は、まず音を出して1回通して確認</strong>
            <p>顔や文字の切れ、字幕を読み切れる速さ、読み上げの発音、場面が切り替わるタイミングを確認します。上の助言は編集の目安です。品質検査の合格は、内容の伝わりやすさや口の動きとの一致まで保証するものではありません。</p>
          </div>
        </li>
      </ol>
    </div>
  );
}

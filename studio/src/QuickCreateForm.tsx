import type { AnnouncementSceneRole, Artifact } from './types';

export type QuickCreateSceneDraft = {
  role: AnnouncementSceneRole;
  videoArtifactId: string;
  startMs: string;
  endMs: string;
  headline: string;
  narration: string;
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
                    {videoErrors[0] ?? (artifact ? `${formatQuickDuration(artifact.durationSeconds)} · ${formatQuickBytes(artifact.sizeBytes)} · ${Math.max(0, Number(scene.endMs) - Number(scene.startMs)) / 1_000}秒を使用` : '素材を選んでください')}
                  </small>
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
                      aria-describedby={headlineErrors.length > 0 ? `${headlineId}-error` : undefined}
                      onChange={(event) => onSceneHeadlineChange(index, event.target.value)}
                    />
                  </label>
                  {headlineErrors.length > 0 && <small className="quick-create-field-error" id={`${headlineId}-error`}>{headlineErrors[0]}</small>}
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
                        aria-describedby={narrationErrors.length > 0 ? `${narrationId}-error` : undefined}
                        onChange={(event) => onSceneNarrationChange(index, event.target.value)}
                      />
                    </label>
                    {narrationErrors.length > 0 && <small className="quick-create-field-error" id={`${narrationId}-error`}>{narrationErrors[0]}</small>}
                  </div>
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
        </li>
      </ol>
    </div>
  );
}

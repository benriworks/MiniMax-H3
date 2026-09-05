import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type SyntheticEvent } from 'react';
import { api, isStudioApiResponseLoss, validateVideoImportFiles } from './api';
import {
  SIMPLE_CREATE_DEADLINE_MS,
  SIMPLE_CREATE_MAX_VIDEOS,
  SIMPLE_CREATE_STORAGE_KEY,
  SIMPLE_CREATE_TEMPLATES,
  createSimpleCreateIntent,
  getSimpleCreateTemplate,
  parseSimpleCreateIntent,
  simpleCreateStoryboard,
  validateSimpleCreateFields,
  type SimpleCreateIntent,
  type SimpleCreateTemplateId,
} from './simpleCreate';
import { runSimpleCreateWorkflow, type SimpleCreatePhase } from './simpleCreateWorkflow';

type FileProgress = 'pending' | 'uploading' | 'succeeded';

interface SimpleCreateWizardProps {
  open: boolean;
  onClose: () => void;
  onAdvanced: () => void;
  onProductionReady: (productionId: string) => Promise<boolean>;
  canCreateProduction: () => boolean;
}

const phaseLabel: Record<SimpleCreatePhase, string> = {
  production: '制作を準備中',
  imports: '動画素材を取込中',
  recipe: '固定テンプレートを保存中',
  execution: '動画作成Jobを登録中',
  completed: 'Jobを登録しました',
};

const randomBytes = (length: number): Uint8Array => {
  const value = new Uint8Array(length);
  globalThis.crypto.getRandomValues(value);
  return value;
};

const readPendingIntent = (): { intent?: SimpleCreateIntent; error?: string } => {
  try {
    const raw = window.localStorage.getItem(SIMPLE_CREATE_STORAGE_KEY);
    if (raw === null) return {};
    return { intent: parseSimpleCreateIntent(JSON.parse(raw)) };
  } catch {
    return { error: 'かんたん制作の保留情報が壊れているか、ブラウザ保存を利用できません。明示的に破棄するまで作成を停止します。' };
  }
};

const persistIntent = (intent: SimpleCreateIntent): void => {
  window.localStorage.setItem(SIMPLE_CREATE_STORAGE_KEY, JSON.stringify(intent));
  const verified = window.localStorage.getItem(SIMPLE_CREATE_STORAGE_KEY);
  if (!verified || JSON.stringify(parseSimpleCreateIntent(JSON.parse(verified))) !== JSON.stringify(intent)) {
    throw new Error('安全な再試行情報をブラウザへ保存できません。');
  }
};

const clearIntent = (): boolean => {
  try {
    window.localStorage.removeItem(SIMPLE_CREATE_STORAGE_KEY);
    return window.localStorage.getItem(SIMPLE_CREATE_STORAGE_KEY) === null;
  } catch {
    return false;
  }
};

const fileKey = (file: File, index: number): string => `${file.name}:${file.size}:${file.lastModified}:${index}`;

export function SimpleCreateWizard({
  open,
  onClose,
  onAdvanced,
  onProductionReady,
  canCreateProduction,
}: SimpleCreateWizardProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const [title, setTitle] = useState('');
  const [templateId, setTemplateId] = useState<SimpleCreateTemplateId>('announcement_v1');
  const [messageText, setMessageText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [fileStates, setFileStates] = useState<FileProgress[]>([]);
  const [fileDedupe, setFileDedupe] = useState<boolean[]>([]);
  const [pendingIntent, setPendingIntent] = useState<SimpleCreateIntent>();
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [phase, setPhase] = useState<SimpleCreatePhase>();
  const [completed, setCompleted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();

  useEffect(() => {
    if (!open) {
      if (dialogRef.current?.open) dialogRef.current.close();
      return;
    }
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const pending = readPendingIntent();
    setPendingIntent(pending.intent);
    setStorageBlocked(Boolean(pending.error));
    setTitle(pending.intent?.title ?? '');
    setTemplateId(pending.intent?.templateId ?? 'announcement_v1');
    setMessageText(pending.intent?.message ?? '');
    setFiles([]);
    setFileStates([]);
    setFileDedupe([]);
    setValidationErrors([]);
    setPhase(undefined);
    setCompleted(false);
    setSubmitting(false);
    setMessage(pending.error
      ? { type: 'error', text: pending.error }
      : pending.intent
        ? { type: 'info', text: '前回の一括作成が未確定です。同じProduction IDとrecipe IDで安全に再照合します。動画素材を同じ順番で選び直してください。' }
        : undefined);
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
    window.setTimeout(() => titleRef.current?.focus(), 0);
  }, [open]);

  const template = useMemo(() => getSimpleCreateTemplate(templateId), [templateId]);
  const storyboard = useMemo(() => simpleCreateStoryboard(templateId, messageText), [templateId, messageText]);
  const formErrors = useMemo(
    () => validateSimpleCreateFields(title, templateId, messageText),
    [messageText, templateId, title],
  );

  const closeDialog = useCallback(() => {
    if (submitting) return;
    if (dialogRef.current?.open) dialogRef.current.close();
    onClose();
    previouslyFocusedRef.current?.focus();
  }, [onClose, submitting]);

  const handleCancel = useCallback((event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    closeDialog();
  }, [closeDialog]);

  const handleFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.currentTarget.files ?? []);
    const validation = validateVideoImportFiles(selected);
    const errors = [...validation.errors];
    if (selected.length < 1 || selected.length > SIMPLE_CREATE_MAX_VIDEOS) {
      errors.push(`動画素材は1〜${SIMPLE_CREATE_MAX_VIDEOS}件選択してください。`);
    }
    setValidationErrors(errors);
    setFiles(errors.length > 0 ? [] : selected);
    setFileStates(errors.length > 0 ? [] : selected.map(() => 'pending'));
    setFileDedupe(errors.length > 0 ? [] : selected.map(() => false));
    setMessage(undefined);
    if (errors.length > 0) event.currentTarget.value = '';
  }, []);

  const discardPending = useCallback(() => {
    if (submitting) return;
    if (!window.confirm('保留IDを破棄すると、前回処理との自動再照合ができなくなります。破棄しますか？')) return;
    if (!clearIntent()) {
      setMessage({ type: 'error', text: '保留情報を破棄できません。ブラウザのlocalStorage設定を確認してください。' });
      return;
    }
    setPendingIntent(undefined);
    setStorageBlocked(false);
    setTitle('');
    setTemplateId('announcement_v1');
    setMessageText('');
    setFiles([]);
    setFileStates([]);
    setFileDedupe([]);
    setValidationErrors([]);
    setPhase(undefined);
    setCompleted(false);
    setMessage({ type: 'info', text: '保留情報を破棄しました。新しいIDは作成ボタンを押す直前に発行します。' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [submitting]);

  const openAdvanced = useCallback(() => {
    if (submitting) return;
    if (pendingIntent || storageBlocked) {
      setMessage({ type: 'info', text: '安全な再試行IDが保留中です。先に一括作成を再試行するか、保留情報を明示的に破棄してください。' });
      return;
    }
    if (dialogRef.current?.open) dialogRef.current.close();
    onClose();
    onAdvanced();
  }, [onAdvanced, onClose, pendingIntent, storageBlocked, submitting]);

  const submit = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = [...validateSimpleCreateFields(title, templateId, messageText), ...validationErrors];
    if (files.length < 1 || files.length > SIMPLE_CREATE_MAX_VIDEOS) {
      errors.push(`動画素材は1〜${SIMPLE_CREATE_MAX_VIDEOS}件選択してください。`);
    }
    if (errors.length > 0 || submitting || storageBlocked) {
      setValidationErrors([...new Set(errors)]);
      return;
    }
    if (!pendingIntent && !canCreateProduction()) {
      setMessage({ type: 'info', text: '別の制作に未保存変更があるため、一括作成をキャンセルしました。' });
      return;
    }

    let intent = pendingIntent;
    try {
      if (!intent) {
        intent = createSimpleCreateIntent({ title, templateId, message: messageText }, randomBytes);
        persistIntent(intent);
        setPendingIntent(intent);
      }
    } catch (error) {
      setStorageBlocked(true);
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '安全な再試行IDを保存できません。' });
      return;
    }

    setSubmitting(true);
    setMessage({ type: 'info', text: '一つの期限内で制作、素材、テンプレート、Job登録を順番に処理します。' });
    setFileStates(files.map(() => 'pending'));
    setFileDedupe(files.map(() => false));
    try {
      const result = await runSimpleCreateWorkflow({
        ...api,
        isResponseLoss: isStudioApiResponseLoss,
      }, intent, files, {
        deadlineAt: Date.now() + SIMPLE_CREATE_DEADLINE_MS,
        onProgress: (progress) => {
          setPhase(progress.phase);
          if (progress.phase !== 'imports' || progress.fileIndex === undefined) return;
          setFileStates((current) => current.map((state, index) => (
            index < progress.fileIndex! ? 'succeeded' : index === progress.fileIndex ? 'uploading' : state
          )));
          if (progress.fileIndex > 0 && progress.deduplicated !== undefined) {
            setFileDedupe((current) => current.map((value, index) => (
              index === progress.fileIndex! - 1 ? progress.deduplicated! : value
            )));
          }
        },
      });
      const reloaded = await onProductionReady(result.productionId).catch(() => false);
      const cleared = clearIntent();
      if (cleared) setPendingIntent(undefined);
      setCompleted(true);
      setMessage({
        type: reloaded ? 'success' : 'info',
        text: `Job ${result.job.id} を登録しました。${result.deduplicatedImports > 0 ? `素材${result.deduplicatedImports}件は既存artifactを再利用しました。` : ''}${reloaded ? '制作画面で進捗を確認できます。' : '制作一覧の再読込だけ失敗したため、手動で更新してください。'}`,
      });
    } catch (error) {
      setMessage({
        type: 'error',
        text: `${error instanceof Error ? error.message : '一括作成に失敗しました。'} 同じ保留IDと同じ素材順で再試行できます。`,
      });
    } finally {
      setSubmitting(false);
    }
  }, [canCreateProduction, files, messageText, onProductionReady, pendingIntent, storageBlocked, submitting, templateId, title, validationErrors]);

  const allErrors = [...new Set([...formErrors, ...validationErrors])];
  const fieldsLocked = submitting || completed || Boolean(pendingIntent) || storageBlocked;

  return (
    <dialog ref={dialogRef} className="simple-create-dialog" aria-labelledby="simple-create-title" onCancel={handleCancel}>
      <form className="simple-create-form" onSubmit={(event) => void submit(event)}>
        <div className="panel-header">
          <div><span className="section-kicker">SIMPLE CREATE V2</span><h2 id="simple-create-title">かんたん制作</h2></div>
          <button className="button button-ghost" type="button" onClick={closeDialog} disabled={submitting}>閉じる</button>
        </div>
        <p className="panel-lead">素材と言葉を選んで、約15秒の字幕・音声つき動画を作ります。費用のかかるAPIは使いません。完成後に仕上がりを確認して、必要な場面を直せます。</p>

        <ol className="simple-create-decisions">
          <li>
            <span>1</span>
            <label className="field" htmlFor="simple-create-production-title"><strong>制作の名前</strong><input id="simple-create-production-title" ref={titleRef} maxLength={120} value={title} disabled={fieldsLocked} onChange={(event) => setTitle(event.target.value)} placeholder="例：9月オンライン講座のお知らせ" /></label>
          </li>
          <li>
            <span>2</span>
            <fieldset disabled={fieldsLocked}><legend>用途テンプレート</legend><div className="simple-create-template-grid">{SIMPLE_CREATE_TEMPLATES.map((item) => <label className={templateId === item.id ? 'is-selected' : ''} key={item.id}><input type="radio" name="simple-create-template" value={item.id} checked={templateId === item.id} onChange={() => setTemplateId(item.id)} /><strong>{item.label}</strong><small>{item.description}</small><em>{item.id}</em></label>)}</div></fieldset>
          </li>
          <li>
            <span>3</span>
            <label className="field" htmlFor="simple-create-videos"><strong>動画素材（1〜3件）</strong><input id="simple-create-videos" ref={fileInputRef} type="file" accept=".mp4,.m4v,.mov,.mkv,.webm,.avi" multiple disabled={submitting || storageBlocked} onChange={handleFileChange} /><small className="field-help">選択順に「つかみ→要点→案内」で使用します。1件なら3場面で再利用します。</small></label>
            {files.length > 0 && <ol className="simple-create-file-list">{files.map((file, index) => <li key={fileKey(file, index)}><strong>{file.name}</strong><span>{fileStates[index] === 'uploading' ? '取込中' : fileStates[index] === 'succeeded' ? '取込済み' : '待機'}</span>{fileDedupe[index] && <small>既存artifactを再利用</small>}</li>)}</ol>}
          </li>
          <li>
            <span>4</span>
            <label className="field" htmlFor="simple-create-message"><strong>いちばん伝えたい文言</strong><textarea id="simple-create-message" rows={2} maxLength={80} value={messageText} disabled={fieldsLocked} onChange={(event) => setMessageText(event.target.value)} placeholder={template.messagePlaceholder} /><small className="field-help">2行以内・1行全角10文字相当（半角20文字）まで。読み上げ文も自動で作ります。</small></label>
          </li>
          <li className="simple-create-confirm">
            <span>5</span>
            <div><strong>確認して一括作成</strong><dl><div><dt>構成</dt><dd>{template.label}・3場面・約15秒</dd></div><div><dt>仕上げ</dt><dd>ローカル音声・大きな字幕・技術検査</dd></div><div><dt>素材音</dt><dd>使用しません。読み上げ音声のみです。</dd></div></dl>
              <div className="simple-create-storyboard" aria-label="作成前の台本確認">
                {storyboard.map((scene, index) => <article key={scene.role}>
                  <h4>{index + 1}. {['つかみ', '要点', '案内'][index]}</h4>
                  <small>大見出し</small><p>{scene.headline || '文言を入力すると表示されます'}</p>
                  <small>読み上げるセリフ</small><p>{scene.narration || '文言から自動作成します'}</p>
                </article>)}
              </div>
              <p className="field-help">実際に使用する台本です。読み上げ速度や口の動きとの一致は保証しません。完成動画で音声と字幕を確認してください。</p>
            </div>
          </li>
        </ol>

        {allErrors.length > 0 && <div className="validation-list" role="alert">{allErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
        {phase && <div className="simple-create-progress" role="status" aria-live="polite"><span className={phase === 'completed' ? 'is-complete' : ''} />{phaseLabel[phase]}</div>}
        {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'} aria-live="polite">{message.text}</div>}
        <p className="simple-create-privacy">API tokenや秘密情報は入力しないでください。選択ファイル名はブラウザ表示だけに使い、一括処理の保留情報には保存しません。</p>
        <div className="button-row simple-create-actions">
          <button className="button button-primary" type="submit" disabled={submitting || completed || storageBlocked || files.length < 1 || allErrors.length > 0}>{completed ? 'Job登録済み' : submitting ? phase ? phaseLabel[phase] : '処理中…' : pendingIntent ? '同じIDで一括作成を再試行' : 'この内容で一括作成'}</button>
          <button className="button button-secondary" type="button" disabled={submitting} onClick={openAdvanced}>詳細設定から始める</button>
          <button className="button button-ghost" type="button" disabled={submitting} onClick={closeDialog}>あとで</button>
        </div>
        {(pendingIntent || storageBlocked) && <button className="button button-ghost simple-create-discard" type="button" disabled={submitting} onClick={discardPending}>保留IDを明示的に破棄</button>}
      </form>
    </dialog>
  );
}

import { useState } from 'react';
import { api, isStudioApiResponseLoss } from './api';
import type {
  ProductionLibraryAction,
  ProductionLibraryMutationResponse,
  ProductionSummary,
} from './types';


const secureUuidHex = (): string => {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (!uuid) throw new Error('このブラウザでは安全な操作IDを生成できません。');
  return uuid.replaceAll('-', '');
};

const newOperationId = (): string => `production_library_op_${secureUuidHex()}`;
const newProductionId = (): string => `production_${secureUuidHex()}`;

const retryLostResponseOnce = async <T,>(request: () => Promise<T>): Promise<T> => {
  try {
    return await request();
  } catch (error) {
    if (!isStudioApiResponseLoss(error)) throw error;
    return request();
  }
};

interface ProductionLibraryPanelProps {
  production: ProductionSummary;
  disabled?: boolean;
  onMutation: (result: ProductionLibraryMutationResponse) => Promise<void>;
}

export function ProductionLibraryPanel({
  production,
  disabled = false,
  onMutation,
}: ProductionLibraryPanelProps) {
  const [busyAction, setBusyAction] = useState<ProductionLibraryAction>();
  const [message, setMessage] = useState<string>();

  const runMutation = async (
    action: ProductionLibraryAction,
    request: () => Promise<ProductionLibraryMutationResponse>,
  ) => {
    if (busyAction || disabled || production.libraryReadOnly) return;
    setBusyAction(action);
    setMessage(undefined);
    try {
      const result = await retryLostResponseOnce(request);
      await onMutation(result);
      setMessage(
        result.action === 'rename'
          ? '表示名を更新しました。'
          : result.action === 'archive'
            ? result.production.archived ? '制作をアーカイブしました。' : '制作を一覧へ戻しました。'
            : `「${result.production.title}」を複製しました。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '制作ライブラリ操作に失敗しました。');
    } finally {
      setBusyAction(undefined);
    }
  };

  const rename = () => {
    const title = window.prompt('新しい表示名を入力してください。', production.title)?.trim();
    if (!title || title === production.title) return;
    const operationId = newOperationId();
    void runMutation(
      'rename',
      () => api.renameProduction(production.id, operationId, production.title, title),
    );
  };

  const toggleArchive = () => {
    const nextArchived = !production.archived;
    const verb = nextArchived ? 'アーカイブ' : '一覧へ戻す';
    if (!window.confirm(`「${production.title}」を${verb}しますか？成果物は削除されません。`)) return;
    const operationId = newOperationId();
    void runMutation(
      'archive',
      () => api.archiveProduction(production.id, operationId, production.archived, nextArchived),
    );
  };

  const duplicate = () => {
    const title = window.prompt('複製後の表示名を入力してください。', `${production.title} のコピー`)?.trim();
    if (!title) return;
    const operationId = newOperationId();
    const targetProductionId = newProductionId();
    void runMutation(
      'duplicate',
      () => api.duplicateProduction(
        production.id,
        operationId,
        targetProductionId,
        title,
        true,
      ),
    );
  };

  const controlsDisabled = Boolean(busyAction || disabled || production.libraryReadOnly);
  return (
    <section className="production-library-panel" aria-label="制作ライブラリ操作">
      <div className="production-library-actions">
        <button className="button button-secondary" type="button" disabled={controlsDisabled} onClick={rename}>
          {busyAction === 'rename' ? '変更中…' : '表示名変更'}
        </button>
        <button className="button button-secondary" type="button" disabled={controlsDisabled} onClick={duplicate}>
          {busyAction === 'duplicate' ? '複製中…' : '素材ごと複製'}
        </button>
        <button className="button button-secondary" type="button" disabled={controlsDisabled} onClick={toggleArchive}>
          {busyAction === 'archive' ? '更新中…' : production.archived ? '一覧へ戻す' : 'アーカイブ'}
        </button>
      </div>
      {production.libraryReadOnly ? (
        <small>リポジトリ管理の制作は読み取り専用です。</small>
      ) : disabled ? (
        <small>かんたん作成の未保存変更を保存または破棄してから操作してください。</small>
      ) : message ? (
        <small role="status" aria-live="polite">{message}</small>
      ) : null}
    </section>
  );
}

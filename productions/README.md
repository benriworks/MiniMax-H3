# Production records

## 現行の制作ルール（2026-10-23）

制作工程と担当者向けの入口は [動画制作ガイド](../docs/video-production/README.md)。新しい人物を使う場合は先にユーザーへ確認し、確認済み人物をMiniMaxで動画化する。人物のペルソナと物語、初回出力と修正履歴、素材の版と採否を案件記録へ残す。

ナレーションは [独立した引き継ぎ資料](../docs/video-production/NARRATION_HANDOFF_JA.md) を参照。下記の既存台帳形式は保持し、今後の保存・レビュー・GitHub更新の運用を [総合ガイド](../docs/video-production/VIDEO_PRODUCTION_HANDOFF_JA.md) に従って補う。動画・音声・納品ZIPの本体はローカル／共有ストレージに置き、GitHubへは文書・軽量な台帳を残す。

このディレクトリは、MiniMax H3およびStudioのローカル編集・モーショングラフィックスで制作した個別案件の追跡可能な台帳を置く場所です。再利用可能な制作判断はルートの[PRODUCTION_PLAYBOOK_JA.md](../PRODUCTION_PLAYBOOK_JA.md)へ集約し、案件固有のprompt、hash、採否、権利境界は各productionに残します。

## ディレクトリ契約

各productionは原則として次を持ちます。

| ファイル | 責務 |
| --- | --- |
| `CUT_PLAN_JA.md` | cut割り、入力mode、動作、音声、編集、生成前gate |
| `PRODUCTION_RECORD_JA.md` | prompt ID、graph hash、seed、所要時間、artifact、編集、QC、採否 |
| `ASSET_PROVENANCE_JA.md` | source / generated asset、派生関係、bytes、SHA-256、権利境界 |
| `manifests/source-hashes.json` | 機械可読なpath、bytes、SHA-256、media、status |
| `prompts/*.md` | APIへ送ったH3 promptの追跡用本文 |

生成画像、raw動画、review画像、音声、masterは`outputs/productions/<production-id>/`へ置きます。`outputs/`はignoredなので、tracked台帳はartifactそのものを配布せず、現在のローカルartifactを照合する記録です。

## Status workflow

`planned` → `ready_for_generation` → `generating` → `candidates_ready` → `selected_for_assembly` → `assembled_pending_independent_review` → `complete_independently_reviewed`

planned、queued、runningは生成成功の証拠ではありません。statusは実在artifact、bytes / SHA-256、媒体検査、full decode、視覚・音声QCに基づいて進めます。

## Productions

| ID | 内容 | 状態 | 記録 |
| --- | --- | --- | --- |
| `SHORT_20260905_codex_15s` | Codexをテーマとしたnative 1080×1920の15秒モーショングラフィックス。日本語SAPI音声と読み上げ字幕 | 案件専用の既存worker実行。検証結果・公開前確認は個別台帳を参照 | [制作記録](SHORT_20260905_codex_15s/PRODUCTION_RECORD_JA.md) |
| `CM_20260815_genai_mastery_15s` | プレゼンターを使った15秒生成AI CM。camera Truck Right失敗候補も保持 | canonical master independently reviewed。公開権利は別gate | [制作記録](CM_20260815_genai_mastery_15s/PRODUCTION_RECORD_JA.md) |
| `PV_20260815_original_jp_dance_unit_15s` | 完全合成3人組のdance / vocal / synth 15秒PV | master independently reviewed。CUT03後半はcreative needs improvement。公開権利は別gate | [制作記録](PV_20260815_original_jp_dance_unit_15s/PRODUCTION_RECORD_JA.md) |
| `SHORT_20260823_claude_md_15s` | `CLAUDE.md`を説明する縦型15秒YouTube Short | overlay版と完全クリーン版の1080x1920 masterを作成・検査済み。technical / creative / phonetic semantic PASS。人による試聴と公開権利は別gate | [制作記録](SHORT_20260823_claude_md_15s/PRODUCTION_RECORD_JA.md) |

## 記録上の注意

- technical GO、semantic GO、creative GO、public releaseを分離します。
- 不採用candidateはcanonicalを上書きせず、別名、hash、reject理由を残します。
- prompt file SHAとsubmitted prompt SHAを区別します。
- graph hashだけではgraph本体を復元できないため、可能なら受理graphもignored logsへ保存します。
- 人による試聴と公開・配信権利を技術QCから推測しません。

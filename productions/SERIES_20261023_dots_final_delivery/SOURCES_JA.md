# dots 第5〜9回の仕上げ・出典確認

確認日：2026-10-23。第5・7回を改訂し、第6・8・9回は検証済みのGemini Aoede版を再利用する。過去の完成MP4や制作状態は上書きしない。

## 第5回：会話をまたぐ文脈

- [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)：現在の会話、関連するChatGPT Memory、dot自身のノートを使う。独自ノートは好み・決定・進行中の仕事を後の会話へ引き継ぐ。過去の会話を必要に応じて検索できるが、全履歴を各タスクへ常に渡す説明ではない。
- [Manage dots permissions and capabilities](https://learn.chatgpt.com/docs/enterprise/dots-admin-guide)：dotの独自contextはChatGPT Memoryと別。Memoryをオフにしても既存の保持情報は消去されない。dot削除と、別に作成したファイル・会話等の削除は別の扱い。
- 編集判断：「会話が変わるとリセットされる」ような印象を避け、継続する文脈を中心にする。一方、永久・無制限・全会話完全保存という保証は確認できないため述べない。

## 第7回：定期実行を会話から頼む

- [Tasks and memory](https://learn.chatgpt.com/docs/dots/tasks-and-memory)：繰り返しは保存されたscheduleが必要。内容・日時と時間帯・期限・通知条件・届け先を明示し、保存内容を確認する。dotへ一覧、変更、取消を頼める。
- [Control your dot](https://learn.chatgpt.com/docs/dots/controls)：Scheduledで内容・時刻・通知先を確認し、無効化・削除できる。Pauseは現在の主作業の一時停止で、将来の定期実行を取り消さない。
- 動画の依頼文は架空の使用例。会話例と説明図であり、この制作では実際の予定表接続・schedule登録・変更・取消の実証は行っていない。
- 説明順：会話で依頼→時間帯・期限・通知先→予定表の接続と保存確認→会話またはScheduledで一覧→会話で変更／解除→Scheduledで無効化／削除→一時停止との違い→結果確認。
- 依頼例：「毎朝9時、日本時間で、接続した予定表から今日の予定を確認し、ChatGPTで知らせて。今月末まで。保存した内容も教えて」。既存予約を特定してから「朝8時に変更して」「この定期実行をやめて」。
- UI名は公式の英語表記Scheduledを併記。個別環境の日本語ラベル・配置・提供状況は実機未検証。

## 第6・8・9回

各回の原稿・出典・人物動画・Gemini生成証跡を前シリーズから照合して再利用する。第6回のTeamsは招待制alpha等の提供条件があるため、説明欄でも全員が利用できる保証をしない。生成済み音声を同じ原稿で再生成する追加課金は行わない。

## 保存と共有

公開可能な台本、改訂理由、出典、処理コード、検証要約をGitHubへ資産化する。動画・音声・ZIP・認証情報・共有先の個人アカウント情報をGitHubへ入れない。実体は`outputs/productions/SERIES_20261023_dots_final_delivery/`へ集約し、Driveを優先して共有する。各ファイルのhash・容量とDrive側メタデータ照合を記録する。実機再生・人の最終試聴・ユーザー採用は技術検証と別に記録する。

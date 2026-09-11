# Claude画面の準備操作ガイド

更新: 2026-09-12

## 位置づけと現在の制限

静止画ライブラリで素材を撮る前に、公式ClaudeデスクトップMSIX版を起動し、対応しているタブや入力欄を1回ずつ操作する実験機能です。Claude Code CLI／Windows Terminalの起動・入力・タブ切替は行いません。自動収録シナリオやメッセージ送信機能でもありません。

**更新したUIA3ヘルパーによる実入力・実タブ切替・起動は未検証です。** 2026-09-12のComputer Use再観察では、当初Document止まりだった操作情報が、Chat画面の描画後にはタブ・入力欄まで取得できました。一方、Codeへ戻ると非表示Chat側の情報が残る挙動も確認しました。この観察をもとに取得方式と非表示の検査を更新しましたが、別経路の観察成功をヘルパーの動作成功とは扱いません。メッセージ送信や既存入力の書き換えは実機試験で行っていません。

取得できない画面や現在の表示と一致しない対象は操作せず、手動で準備してから撮影します。座標・キーボード・クリップボードへのfallbackはありません。

## 準備

Windows、公式Claude MSIX版、.NET 8以上のSDKが必要です。通常は`setup-studio.ps1`でヘルパーもbuildします。FlaUI.UIA3 5.0.0と依存パッケージは固定したNuGet lockから取得します（初回はネット接続が必要、課金APIは不要）。ヘルパー単体をbuildする場合：

```powershell
dotnet build native/claude-control-helper/claude-control-helper.csproj -c Release -p:RestoreLockedMode=true --nologo
dotnet native/claude-control-helper/bin/Release/net8.0-windows/claude-control-helper.dll self-test
```

`self-test`は入力契約、互換入力の許可／拒否、タブ別名、書込み後に再試行しないポリシーを確認し、アプリを起動・操作しません。build成功は実Claude対応の証明ではありません。今回の診断追加ではschema 14のままです。既存画像・メモ・手順は保持します。旧ヘルパー応答を検出した場合は再ビルドの案内を表示します。

## 使い方

1. Studioヘッダーの「静止画ライブラリ」を開き、撮影元を「Claudeウィンドウを1枚撮影」にする。
2. 「Claudeの画面準備を開く」を押す。アプリが閉じている場合だけ起動許可をチェックし、「Claudeを起動する」。表示・ログイン状態は自分で確認する。
3. 操作欄内の「Claudeウィンドウを確認」で対象を1つ選び、確認許可をチェックして「タブ・入力欄を確認」。撮影はまだ行わない。
4. 対応要素が取得できた場合だけ対象を選ぶ。タブはCode／Chat／Chat・Coworkの対応要素のみ。入力欄は匿名名と位置・既存文字数で表示する。識別できなければ実行しない。
5. 入力の場合は文章を用意する。4000 UTF-16 code units以内（絵文字等は2単位になることがある）。既存内容があれば置換許可も必要。対象・内容を再確認して1回の操作を許可する。
6. 実画面で結果を確認。送信・Enter・任意コマンドは実行しない。タブ切替後に入力する場合はもう一度対象確認から行う。
7. 下の撮影フォームでウィンドウを**再確認・再選択**し、別途撮影を許可する。保存画像の比較・採用・記事素材パックは従来どおり。

操作対象の確認は最大60秒・1回限り。位置・サイズ・対象・既存入力などが確認後に変わると停止します。ただし人間操作とUIAを完全に原子化できるわけではないため、操作中はClaudeを触らないでください。起動・一部タブ操作は実行要求だけを確認できるため、成功Jobでも「実画面で結果確認が必要」と表示します。

## タブや入力欄が取得できないとき

「直近の確認結果」でタブ切替と未送信入力の候補数を分けて表示します。片方だけ取得できても、両方が利用可能とは表示しません。診断表示は操作の許可ではなく、操作対象の期限が切れても参考として残ります。

1. Claudeの表示が落ち着くまで待ち、撮りたいタブを表示する。
2. 「操作対象を選び直す」から、ウィンドウと候補を確認し直す。
3. 表示中の画面と入力欄の位置が一致しなければ操作しない。手動で準備して撮影する。

「取得方式と診断」を開くと、調査要素数・文書数・非表示／無効等での除外数・書込方法が未確認の欄の数を確認できます。「診断JSONを保存」は固定名のJSONをブラウザへダウンロードします。会話・入力文・画面名・パス・操作ID・tokenは含めず、外部送信や自動保存もしません。数だけで原因を断定したり、実機対応済みと判断したりしないでください。

### 互換方式と安全条件

- UIA3 RawViewで中間要素も調査する。最大2500要素／24候補、候補0件のときだけ300ms後に読取りを1回追加する。
- ValuePatternの書込可能な欄を優先。ValuePatternがない場合だけ、LegacyIAccessibleの書込可能なtext role／focusable／非保護等の条件を満たす欄を候補にする。画面には「互換入力」と表示する。
- readonlyのValuePatternをLegacy方式で迂回しない。処理前の方式選択であり、入力失敗後に別方式で再入力するものではない。
- 非表示／無効の祖先や別ウィンドウ所属の候補を除外し、書込み直前にも祖先を再確認する。隠れたChatの入力欄が残る場合を想定した防護であり、使用中Claude版での受入試験は別途必要。
- 強制再起動、accessibility／remote-debuggingフラグの追加、Windows設定変更、CLIへの自動入力はしない。

## 復旧と記録

- 文章はStudio UIと処理中のサーバーメモリだけに保持し、Job／SQLite／localStorageへ平文保存しない。操作を実行すると当然Claudeの入力欄には文章が残る。Claude自身の保存動作までは制御しない。
- 閉じる・撮影元切替などで未保存文が失われる場合は確認する。文章は自動復元しない。
- ブラウザ保存は受付IDのみ。操作履歴には種類・文字数・時刻・結果が残り、最新50件を表示する。古い記録はDBに残る。
- 応答喪失はGETで既存受付を確認するだけで、自動POST・自動再入力はしない。処理中かつパネル表示中のみ約3秒間隔で確認。受付不明なら定期確認を止める。
- cancel／タイムアウト／サーバー中断でも「操作が一切反映されなかった」とは保証しない。起動やUIA要求がClaude側で既に反映された可能性がある。実画面を確認してから次の操作へ進む。
- 撮影と操作の同時受付は拒否。操作前後には過去の撮影選択を無効化する。自動スクロール、会話送信、ログイン、任意アプリ起動、課金APIは含まない。

## 試験の範囲

`tests/test_studio_claude_control.py`は実Studioサービス／SQLiteと合成native境界を使用。protocol 2、診断件数の境界・整合性、未知の入力方式拒否、機密情報の除外、部分対応時の入力拒否も検査します。`studio/tests/claude-control-live.test.mjs`は実ブラウザ→HTTP→SQLite→合成native境界を接続し、確認チェック・入力・タブ・応答喪失後の再表示・診断JSONの実ダウンロード・部分対応／未対応表示・390px幅を検証します。通常制作DB、実際の会話、実際のCLIは使用しません。

```powershell
python -m unittest tests.test_studio_claude_control tests.test_studio_windows_capture_worker -q
cd studio
npm run test:claude-control-live
```

検証用画像・隔離DBは`studio/output/playwright/`以下。合成入力欄の成功は実Claudeでの成功を意味しません。次の受入課題は、使用中Claude版・空の撮影用会話でUIA3 helperのinspect結果と画面を照合し、隠れたChat入力欄の除外、起動→タブ→未送信入力→PNG取得を実機で検証することです。Codeの入力欄が未取得なら、Chatの成功をもってCode対応済みとはしません。

2026-09-12 UIA3更新の検証結果：関連Python170件（操作26件を含む）、既存フロント228件、ブラウザ5件が成功。locked restore付きネイティブbuildは警告・エラー0、非操作self-testも成功。stdinは日本語データを使い、実Windows Job Object内のテスト用Python子プロセスでも往復を確認しました。ブラウザ試験の`claude-control-diagnostics.png`と`claude-control-mobile.png`で部分対応と狭幅レイアウトを確認しています。frontend buildには既存の約1MB JavaScript bundle警告が残ります。

別の隔離StudioをPlaywright CLIから開き、撮影元選択→操作欄を展開→合成ウィンドウ選択→確認許可→候補と診断表示まで確認しました。console error／warningは0件。試験用サーバー・ブラウザは終了しています。通常Studioの起動や通常制作DBの変更は行っていません。

Reactスキルに沿って診断表示を独立コンポーネントに分け、未保存文・非同期応答・画面離脱の保護を維持しました。Playwrightスキルでブラウザの実表示を確認しています。Computer Useスキルの制約に従い、実機の観察は許可された操作経路に限定し、新ヘルパーを使った代替の実機操作やTerminal自動入力へは切り替えていません。

## 技術資料

- [Microsoft: UI AutomationによるTextBoxへの入力](https://learn.microsoft.com/en-us/dotnet/framework/ui-automation/add-content-to-a-text-box-using-ui-automation)
- [Microsoft: SelectionItemPattern.Select](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.selectionitempattern.select?view=netframework-4.8.1)
- [Microsoft: ActivateApplication](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-iapplicationactivationmanager-activateapplication)
- [Microsoft: UI AutomationとElectron等の対応差](https://learn.microsoft.com/en-us/windows/apps/dev-tools/winapp-cli/ui-automation)
- [Microsoft: LegacyIAccessible SetValue](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nf-uiautomationclient-iuiautomationlegacyiaccessiblepattern-setvalue)
- [Microsoft: UIA3 RawView](https://learn.microsoft.com/en-us/power-automate/desktop-flows/ui-elements)
- [FlaUI 5.0.0](https://github.com/FlaUI/FlaUI/releases/tag/v5.0.0)

依存とライセンスは[native helper notices](native/claude-control-helper/THIRD_PARTY_NOTICES.md)、構造は[Architecture](ARCHITECTURE.md)と[Mermaid図](ARCHITECTURE_DIAGRAM.md)を参照してください。

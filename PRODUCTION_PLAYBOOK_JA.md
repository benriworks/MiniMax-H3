# MiniMax H3 ローカル映像制作プレイブック

## 2026-10-23：制作全体の運用規定と引き継ぎ

人物キャラの初期ユーザー確認、MiniMaxでの動画化、人物のストーリーとシリーズの一貫性、ローカル保存、レビュー、GitHubでの資産化は [制作全体の引き継ぎガイド](docs/video-production/VIDEO_PRODUCTION_HANDOFF_JA.md) を正本とする。人物を使う新しい解説シリーズでは、人物の確認を本番生成・量産より先に行う。

ナレーション担当者へは、単体で渡せる [ナレーション制作・生成・組み込み資料](docs/video-production/NARRATION_HANDOFF_JA.md) を使う。資料一覧とひな形は [動画制作ガイド](docs/video-production/README.md)。**制作動画本体のGitHub保管は不要**で、文書・台本・プロンプト・改善理由・検証要約を節目ごとに資産化する。

以下の生成方式・時間・品質の数値は過去の実測記録。最新の制作方針と、過去の実験条件を混同しない。

## 1. 目的と証拠レベル

この文書は、Windows 11 / RTX 3070 Ti 8 GiB / 物理RAM約47.7 GiBの実機で行ったMiniMax H3短尺制作から、再利用できる判断基準をまとめたものです。環境構築手順は[LOCAL_SETUP_JA.md](LOCAL_SETUP_JA.md)、個々の実測値は[verification](verification/)と[productions](productions/README.md)を参照してください。

記述は次の4種類を区別します。

| 区分 | 意味 |
| --- | --- |
| 確認済み | 実在artifact、履歴、hash、媒体検査、目視またはASRで確認した事実 |
| 単発観察 | 特定prompt / seed / 生成物で見えた傾向。モデル一般の優劣にはしない |
| 次回仮説 | 失敗から導いた改善案。再生成して検証するまで確定事項にしない |
| 未確認 | 必要な記録、独立確認、試聴、権利確認がなく、推測で補完してはいけない境界 |

`job success`、端点PSNR、full decodeのいずれか1つだけではproduction GOにしません。技術的に再生できること、指示どおりであること、映像表現として十分であること、公開可能であることは別の判定です。

## 2. 先に読む結論

- この8 GiB VRAM機で完走を確認した品質候補は、公式INT8 ConvRot diffusion + Q4 text encoder、Turboなし、`res_multistep` / `simple` / 20 steps、Emergency offloadです。少数例であり、全promptに対する一般的な品質優越は未確認です。
- 15秒を1本で生成するのではなく、5秒rawを3本作り、各120 framesを採用して360 framesへ編集する方が、失敗隔離、再生成、人物連続性、音声管理をしやすくなりました。
- 複数人物では「1 cutにつき主役1人だけをactive」にすると、残りの人物、顔、手、背景を安定させやすいという成功例が得られました。複数人を同時に激しく動かす実績はありません。
- 始点画像だけのI2VAは動きの自由度、始点と終点を使うFL2VAは終点poseの拘束に向きます。FL2VAでも途中経路や動作量は保証されません。
- 技術的なfreezeがなくても、創作上は「動きが少なすぎる」ことがあります。motion coverageを別に検査します。
- promptだけのTruck Rightは、真正なparallaxではなくpan / zoom / vertical driftになりました。カメラ幾何が重要なら2.5D、3D、compositingを優先する方針が妥当ですが、これは次回検証です。
- clipごとに生成されたBGMを接続しません。映像rawの音は診断用とし、15秒を通した単一audio masterを編集時に載せます。

## 3. モデル構成を別軸として扱う

`Q3`、`Q4`、Turboは同じ意味ではありません。

| 軸 | このリポジトリでの意味 | 主な影響 |
| --- | --- | --- |
| Q3 | community GGUF diffusion / DiT | 映像のtexture、形状、時間安定性へ影響し得る |
| Q2 / Q4 | text encoderの量子化 | conditioningと指示理解へ影響し得る。pixel denoiseを直接保証しない |
| official INT8 ConvRot | Comfy-Org公式diffusion model | Q3より大きい。公式loaderとEmergency offloadが必要 |
| Turbo | v4 step600 EMA LoRA + 専用sampler | 4–8 stepの試作向け。通常20-stepとは別経路 |

### 確認済み

- Q2からQ4へtext encoderだけを変えたTurbo A/Bは、同じprompt / seed / 0.4 MP / 5秒 / 8 stepsで両方完走しました。Q2は313.682秒、Q4は286.087秒、映像差はPSNR 26.291812 dB / SSIM 0.814451です。[検証記録](verification/q4-text-encoder-ab-2026-08-12.json)
- これは出力差と両経路の完走を示すだけで、Q4の一般的な品質、指示理解、速度の優越は示しません。
- official INT8 + Q4、Turboなし、0.6 MP / 5秒 / 20 stepsは3:31:14.964で完走し、samplingは10:41でした。残り時間の大部分は後段処理です。[検証記録](verification/int8-quality-2026-08-14.json)
- 同じcity prompt / seedの1例では、INT8は空のノイズと窓格子の揺れが少なく、Q3は細かなtextureが多く見えました。これは1例の単発観察で、人物、指示追従、全promptの一般順位にはしません。

### 運用判断

- 低コスト試作: Q3 + Q4 text encoder + Turbo、simple / 8 steps。
- 品質候補: official INT8 + Q4 text encoder、Turboなし、res_multistep / simple / 20 steps。
- Turboのstepsだけを20へ増やしません。Turboと通常20-stepを切り替える場合はLoRAとsamplerを一緒に切り替えます。
- GGUF Q3は`UnetLoaderGGUF`、official INT8はstock `UNETLoader`を使います。profileだけ変更して旧workflowを開くとloaderまたはモデル選択が不整合になります。[workflow対応](workflows/README.md)

## 4. 8 GiB機の時間とメモリ

### 確認済みの範囲

- 実機: RTX 3070 Ti 8 GiB、物理RAM約47.7 GiB、pagefile 48 GiB。
- official INT8 + Q4の1-step smokeではprocess working set 32.64 GiB、空き物理RAM 1.14 GiB、commit 64.64 / 95.72 GiBでした。[smoke記録](verification/int8-smoke-2026-08-13.json)
- 0.6 MP / 5秒 / 20-step品質runは、sampling 10:41に対して総時間3:31:14.964でした。CPU Video-VAEを含む後段が支配的です。
- 0.4 MP / 5秒のPV 3 rawは2:56:51.703、2:55:25.663、3:03:00.593でした。同じ解像度とstepsでもcache、offload、VAE、prompt内容により所要時間は変わります。[PV制作記録](productions/PV_20260815_original_jp_dance_unit_15s/PRODUCTION_RECORD_JA.md)

### 運用ルール

- 8 GiB機でofficial INT8を初回実行するときは`-EmergencyLowVram`を使い、`--novram --cpu-vae`系のoffloadを前提にします。
- 生成は1 jobずつにします。並列queueを入れず、同時に重いGPU / RAMアプリを起動しません。
- GPU sampling完了後にGPU utilizationが0%へ落ち、CPUとRAMが長時間動く状態は、直ちにhangとは限りません。CPU累積時間、working set、queue、history、stderrを合わせて判断します。
- 中止条件は、OOM / CUDA / traceback、process exit、commit limitへの継続接近、またはCPUが長時間停止しqueue / history / outputが不変な場合です。経過時間だけで中止しません。
- 長時間runの定期監視は、モデルとの会話turnではなく、単一の軽量watcherがqueue、process、free RAM、commit、outputをローカルログへ追記する方式を優先します。モデルは投入直後、異常閾値到達、主要stage遷移、30–60分ごとの要約、完了時だけログを読みます。
- 監視専用subagentへ長い制作履歴を継承しません。必要なprompt ID、PID、開始時刻、出力path、閾値だけを渡し、rootへは変化または異常だけを報告します。変化のない1分ごとのagent turnは作りません。
- ユーザーへの進捗共有も、同じ数値を繰り返すheartbeatではなく、開始、検証通過、stage遷移、リスク変化、完了のmilestone単位にまとめます。
- 15秒1本のローカル生成は未検証です。現時点では5秒に分割します。

## 5. 制作設計: 1 cut 1 active principal

15秒PVで成功した基本形は次です。

| cut | 主役 | 入力mode | 主な動作 | 背景人物 |
| --- | --- | --- | --- | --- |
| 1 | dancer | I2VA | 小さなstep + 1回の腕sweep | blink / breathingのみ |
| 2 | vocalist | I2VA | 正面歌唱 | 閉口、ほぼ静止 |
| 3 | synth player | FL2VA | 右手を3鍵へ下ろす | 閉口、ほぼ静止 |

成功例から得た運用ルールです。

1. 1 cut内で大きく動く人物は1人にする。
2. active人物の動作も、意味が連続する1フレーズに絞る。
3. 背景人物には位置、閉口、手、衣装、occlusionを固定し、blink / breathing以外を要求しない。
4. camera、照明、焦点距離、horizonは人物動作と同時に変更しない。
5. 手、顔、機材が画面で十分な大きさになる画角を選ぶ。

これは3人構成の少数例での成功パターンです。多人数同時ダンスの品質保証ではありません。

## 6. 始点画像とidentity bible

### 推奨手順

1. 全員のidentity、年齢感、髪、衣装、身長差、通常配置を定義する。
2. identity lineupを画像生成で1枚作る。
3. cut別始点はlineupまたは承認済み始点からimage editで派生する。独立text-to-imageを繰り返さない。
4. raw画像とComfyUI入力用のexact-size画像を分ける。
5. runtime画像のwidth / height / color mode / bytes / SHA-256を固定する。
6. H3投入前に、人数、顔、手、衣装、背景、機材、文字、ロゴを静止画でrejectする。

ComfyUIのfirst frameはcanvasへplain stretchされ得るため、入力を先に最終canvasと同じaspect / pixel sizeへ正規化します。今回の横長制作では864x480 RGBを使いました。

### 始終点画像を作る場合

- end frameはstart frameの局所editにします。
- 変えてよい領域をmaskで限定し、背景人物、顔、camera、照明、機材外形を変えません。
- start / endで人物scale、頭幅、horizon、直線、遮蔽関係を比較します。
- endpointに手同士の重なり、人物の位置差、別顔、機材形状差がある場合は、高価なFL2VAを実行する前にrejectします。
- endpointの高いPSNR / SSIMは端点の近さだけを示し、途中morphや動作経路を保証しません。

## 7. I2VAとFL2VAの選択

この制作環境では、同じFL2VA diffusion modelへ接続する画像数でmodeを切り替えます。

| mode | 入力 | 向いていた用途 | 主なリスク |
| --- | --- | --- | --- |
| T2VA | 画像なし | prompt / model A/B、背景shot | identity固定が弱い |
| I2VA | first frameのみ | dance、正面歌唱、自然な人物動作 | 終点poseや最終位置のdrift |
| FL2VA | first + last | 最終pose、手と機材の着地点 | 早期収束、途中morph、不正なcamera path |
| Ref2VA | full reference | この制作群では未検証 | 未検証 |

### 選び方

- 経路の自然さと動作量を優先するなら、まずI2VAを試します。
- 最終poseや機材接触を固定したい場合だけFL2VAを使います。
- FL2VAのend frameがstartに近すぎる場合、意図した動作より早く終点へ収束することがあります。この因果は未確定ですが、今回のCUT03では実際に早く動作が終わりました。

## 8. 動作量と静止区間を別ゲートにする

### 今回の失敗知見

PV CUT03は技術監査ではGOでしたが、final timeline約11.83秒で鍵盤動作を終え、残り約3.17秒がsustain tableauになりました。全360 framesに隣接する完全同一frameはありませんでしたが、利用者評価では「後半の動きが少なすぎる」です。

つまり次は別の検査が必要です。

- technical freeze: duplicate frame、decode停止、black frameを検出する。
- creative motion coverage: 主役ROIが時間全体で意味のある動作を続けているか確認する。

### 次回検証案

以下は未検証仮説です。

- 開始holdを0.25–0.4秒、最終settleを0.3–0.5秒へ短くする。
- 主要動作を4.3–4.7秒までbeat単位で配分する。
- `sustain`、`hold through the final frame`の長い指定を避ける。
- 楽器演奏は「押下して保持」だけでなく、押下、別の明確なaccent、releaseまたは視線変化を1本の連続フレーズとして設計する。
- 動作経路を優先するcutはI2VA start-onlyとFL2VAを同じ始点でA/Bする。
- 0.5秒ごとのcontact sheetまたはactive-person ROIでmotion coverageを確認し、最終settle前のnear-static区間が0.75秒を超えた候補をcreative reviewへ戻す。この0.75秒は次回の試験値であり、確認済み品質基準ではありません。

動きを増やすと、手、顔、関節、背景人物のmorphリスクも上がります。複数人を同時にactiveにするのではなく、主役1人の連続動作を増やします。

## 9. カメラ移動の失敗知見

### I2VA prompt-only Truck Right

- MP4、人物、直線は技術的に成立しました。
- 全体は約20–25 pxの一様な横移動に近く、near / farの速度差とocclusion revealが不足しました。
- 真正なTruck Rightではなく、緩いpan風候補としてのみ扱いました。

### FL2VA二端点 Truck Right

- first / last anchorへの忠実度と媒体品質は高くなりました。
- 途中は約12.9%のzoom-in、vertical drift、人物位置依存のflow、顔・手・机上物のmorphになり、物理的parallaxは成立しませんでした。
- canonical masterへ採用せず、別candidate名で保存しました。[CM制作記録](productions/CM_20260815_genai_mastery_15s/PRODUCTION_RECORD_JA.md)

### Camera motionの判定

- foregroundがbackgroundより大きく移動するか。
- 複数のocclusion境界でreveal / hideが起きるか。
- subject scale、focal length、horizon、垂直線が安定するか。
- global translation、single homography、zoomだけで説明できないか。

真正なcamera geometryが重要な場合、depth warp、2.5D、3D scene、compositingを先に作る方針は合理的ですが、このリポジトリでは未検証です。

## 10. Prompt設計

H3 promptは[同梱skill](skills/h3-prompt-writing/SKILL.md)に従い、次の順序を維持します。

1. mode別reference alignment文。
2. `integrated_multimodal_description`。
3. `overall_soundscape`。
4. `non_diegetic_music`。

運用上の注意です。

- single shot内の時間配分を秒で書く。
- active人物のidentity、衣装、手、動作を肯定文で先に定義する。
- 背景人物の制約は背景人物へだけ掛ける。shot全体を`no movement`で縛らない。
- 文字、ロゴ、projector UIは生成させず、必要なら編集で正式素材をoverlayする。
- prompt fileのSHAとAPIへ送る本文のSHAを分ける。tracked Markdown末尾のLF 1 byteによりhashが異なり得る。
- prompt ID、graph SHA、seedも残す。ただしgraph SHAだけではgraph本体を復元できません。

## 11. 音声設計

### clipごとのnative音声をmasterへ直結しない

H3 native audioは、実質無音、開始時刻ずれ、追加音、cutごとの音色・tempo差が起きました。15秒作品では次の方針が安定しました。

1. 15.000秒を通した単一instrumental / song masterを作る。
2. CUT01 / CUT03のnative audioは最終masterで破棄する。
3. CUT02は`non_diegetic_music: N/A`とa cappella指定で、歌声だけを取り出す。
4. native vocalの実onset / offset、波形、口形、ASRを確認してsingle masterへ配置する。
5. 音声だけを大幅に`atempo`するとlip-syncが崩れる。必要なら映像と音声を同率retimeするか、CUT02を再生成する。

### 確認済みのPV master

- 48 kHz stereo、15.000秒。
- native vocal activityは約5.74–9.88秒。
- final MP4のASRは5.420–9.440秒に目標歌詞を1回だけ検出し、0–5秒 / 10–15秒にspeechなし。
- AAC masterは-16.06 LUFS-I / -1.79 dBTP / LRA 2.8。

ASRの正規化一致は、人間の聴感、発音品質、声質、法的確認の代替ではありません。公開前に人が試聴します。

## 12. 5秒rawから15秒masterを作る

H3の5秒指定は、17-frame gridにより124 frames / 24 fps = 5.166667秒になりました。各rawのframes 0–119だけを採用します。

| timeline | 採用raw frames | master frames |
| --- | --- | --- |
| CUT01 | 0–119 | 0–119 |
| CUT02 | 0–119 | 120–239 |
| CUT03 | 0–119 | 240–359 |

結果は360 frames / 24 fps = 15.000秒です。顔を混ぜるcross-dissolveではなく、frame 120 / 240でhard cutを使いました。

概念上のFFmpeg filterは次です。

```text
[0:v]trim=start_frame=0:end_frame=120,setpts=N/(24*TB)[v0];
[1:v]trim=start_frame=0:end_frame=120,setpts=N/(24*TB)[v1];
[2:v]trim=start_frame=0:end_frame=120,setpts=N/(24*TB)[v2];
[v0][v1][v2]concat=n=3:v=1:a=0[v]
```

最終codecはH.264 High / yuv420p / CFR 24 fps / CRF 18、音声はAAC-LC 48 kHz stereoとし、`+faststart`を付けました。encode後にframe数、duration、true peakを再検査します。

## 13. QCチェックリスト

### 実行と媒体

- queueから対象promptが消え、historyが`success`になったか。
- output path、bytes、SHA-256を記録したか。
- embedded promptまたは受理graphが意図したmodel / mode / seed / settingか。
- `ffprobe`でcodec、pixel format、width、height、fps、frames、duration、audioを確認したか。
- videoとaudioのfull decodeがexit 0か。
- OOM、CUDA、traceback、interruptがないか。

### 映像

- 全区間を覆うcontact sheetを確認し、異常が疑われる区間は全frameを確認したか。
- frame 0 / 119 / 123と始終点anchorを確認したか。
- 人数、identity、衣装、顔、手指、関節、occlusionを確認したか。
- 楽器や建物の直線、key count / spacing、UI、文字、ロゴを確認したか。
- black、flash、corruption、duplicate freezeを確認したか。
- creative motion coverageを0.5秒単位で確認したか。
- camera motionはdepth別flowとocclusion revealを確認したか。

### 音声と編集

- ASRで目標文が必要回数だけ現れたか。
- 無発話cutでvoiceがないか。
- 波形と口形が同期しているか。
- 人が最終試聴したか。
- LUFS、true peak、clip、NaN / Infを確認したか。
- hard-cut境界のframe 119 / 120、239 / 240にblack / flash / corruptionがないか。
- masterがCFR 24 fps / 360 frames / 15.000秒か。

### 権利

- 人物・likeness、画像reference、音楽、歌詞、歌唱、振付、ロゴ、背景、model output、配信先規約を確認したか。
- 制作依頼や合成人物方針だけをpublic release consentとみなしていないか。

## 14. 合否の分類

| 判定 | 例 |
| --- | --- |
| technical hard fail | outputなし、壊れたMP4、full decode fail、仕様不一致、OOM、black / corruption |
| semantic / production reject | camera path不成立、人数・identity・手・機材崩れ、morph、余計なvoice / text、endpoint不合格 |
| creative needs improvement | 技術GOだが動き、テンポ、構図、余韻が目的に不足。今回のCUT03後半が該当 |
| GO with caveat | 用途上許容できる軽微なsoftnessや短いholdを台帳へ明記 |
| production GO | 媒体、意味、創作、音声、境界が合格。公開権利は別gate |

不採用candidateは削除や上書きをせず、別名とhashを保持します。canonical masterの差し替えは、別masterを組み立てて再監査してから行います。

## 15. 再現性と台帳

`outputs/`はignoredです。clone後にMP4やPNGが存在するとは限りません。tracked台帳はartifactの配布物ではなく、現在のローカルartifactを照合するための記録です。

各案件で次を残します。

- `CUT_PLAN_JA.md`: 生成前のcut、mode、motion、audio、QC設計。
- `PRODUCTION_RECORD_JA.md`: 実行履歴、prompt ID、graph hash、seed、所要時間、artifact、採否、編集、QC。
- `ASSET_PROVENANCE_JA.md`: 入力・生成asset、派生関係、hash、権利境界。
- `manifests/source-hashes.json`: 機械可読なpath、bytes、SHA-256、media、status。

さらにprompt file SHAとsubmitted prompt SHA、raw/runtime画像の両hash、model hash、runtime revision、server flags、resource peakを記録します。今回のPVはprofile、live workflow revision、server flags、peak metricsのroot記録が欠けているため、artifactの監査はできますがbit-for-bit再現可能とは主張しません。

案件索引は[productions/README.md](productions/README.md)を参照してください。

## 16. 主な根拠

- [Turbo E2E](verification/turbo-e2e-2026-08-11.json)
- [Q2 / Q4 text encoder A/B](verification/q4-text-encoder-ab-2026-08-12.json)
- [official INT8 + Q4 smoke](verification/int8-smoke-2026-08-13.json)
- [official INT8 + Q4 quality run](verification/int8-quality-2026-08-14.json)
- [15秒CM制作記録](productions/CM_20260815_genai_mastery_15s/PRODUCTION_RECORD_JA.md)
- [15秒ダンスユニットPV制作記録](productions/PV_20260815_original_jp_dance_unit_15s/PRODUCTION_RECORD_JA.md)

この文書の数値は2026-08-16時点のローカル実測です。モデル、ComfyUI、driver、hardware、prompt、seedが変われば再検証してください。

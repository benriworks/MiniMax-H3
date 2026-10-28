# 比較動画の構成図

比較専用の実素材production経路を実装。実音声14区間68.113秒を無加工で75秒へ配置し、fixtureと公開候補を分ける。

```mermaid
flowchart TD
    Official[公式5ページ 本文確認] --> Claims[主張 根拠 確認日]
    Claims --> Script[440文字 14カット 82秒仮案]
    Fiction[同一の架空カフェ業務] --> Script
    Script --> Quotes[必要箇所だけの公式画面引用]
    Quotes --> Proof[原本 日時 矩形 hash 引用語数]
    Keyframe[森川遥の新キー画像] --> H3[MiniMaxひらめき動画]
    H3 --> MotionReview[生成証跡 decode 実目視]
    Script --> Voice[Aoede 明示生成 安全な再開]
    Voice --> Timing[実音声で60から90秒へ配分]
    Proof --> Validate[比較用props検査 60から90秒]
    Validate --> Render[ProductComparison専用entry]
    MotionReview --> Render
    Timing --> Render
    Render --> Visuals[公式画像 人物 上下2レーンの動図]
    Visuals --> Check[全カットとスマホ表示 音声確認]
    Check --> Delivery[動画 見出し 説明文 出典 manifest]
    Delivery --> Human[利用者採用と公開は別状態]
    Old[既存dotsとClaudeの動画 音声 原稿] -. 変更しない .-> Preserved[旧制作を保全]
    Script --> Fixture[fixture専用の仮配分と短句]
    Fixture --> FixtureRender[未取得素材は待機表示]
    FixtureRender --> Internal[内部確認PNG 公開不可]
    Render --> Font[固定日本語フォント読み込み]
    Font --> Bounds[各frameの文字矩形を検査]
    Bounds --> Visuals
    MotionReview --> ClipRange[実MP4内の再生区間を検査]
    ClipRange --> Switch[終了後は自作まとめへ切替]
    Switch --> Render
    Quotes --> Browser[独立Chrome 公式ページを実撮影]
    Browser --> Private[private 原本PNG 日時 URL]
    Private --> Crop[整数矩形で画素無変更のcrop]
    Crop --> Audit[hash 画素一致 既存proof読み込み検証]
    Audit --> CaptureManifest[captures manifest 公開4PNG]
    CaptureManifest --> Proof
    CaptureManifest --> RootReview[子の画像確認と親の最終確認を分離]
    RootReview --> Check
```


```mermaid
flowchart TD
    Draft[承認済み14カット原稿] --> Generate[generate明示 Aoede 22秒間隔]
    Generate --> Cache[原稿とhash一致のcache 不明送信は停止]
    Cache --> PCM[実発話PCM 68.113秒]
    PCM --> Allocate[発話不変 余白だけ配分 75秒]
    Approved[親確認済み公式3画像] --> Exact[原本画素一致 URL 日時 hash]
    Motion[親確認済みMiniMax 124frame] --> Split[0から35 36から83 84から123]
    Split --> NoRepeat[各区間1回 残尺は自作カード]
    Allocate --> Prepare[prepareと凍結sources]
    Exact --> Prepare
    NoRepeat --> Prepare
    Prepare --> Stills[stills 全14場面と3切替]
    Stills --> Render[comparison-render 全1800frame検査]
    Render --> Silent[無音H264 timeline]
    PCM --> Mix[ナレーション 自作BGM 効果音]
    Silent --> Finish[assemble H264 AAC48k stereo]
    Mix --> Finish
    Finish --> Tech[完全decode 音量 実尺検証]
    Tech --> Review[目視と聴感を別に記録]
    Review --> Package[公開allowlist ZIP member hash照合]
    Private[private原本 API要求] -. 同梱禁止 .-> Package
    Package --> Human[利用者確認 S3とYouTubeは別操作]
```

```mermaid
flowchart LR
    Heard[実聴可能] --> Strict[reviewで目視と実聴の証拠検査]
    Unavailable[音声入力が非対応] --> Honest[package_review 聴感未確認を明記]
    Honest --> Zip[公開素材だけ ZIP hashとCRC検証]
    Zip --> Local[同一MP4を既存AllowedRootsへコピー]
    Local --> Dry[previewとuploadのdry-run]
    Dry --> S3[S3 inline再生とattachment保存]
    S3 --> Verify[HEADと全GET hash一致]
    Verify --> Receipt[URLなしreceiptを保存]
    Verify --> Reply[署名URLは返信だけ 24時間]
```

```mermaid
flowchart LR
    Old[旧75秒版 音声 字幕 人物の3区間] --> Copy[hash照合 別versionへコピー]
    Copy --> OptIn[presenterTreatment immersive]
    OptIn --> Full[人物を縦画面全面へ表示]
    Full --> Overlay[顔を避ける見出し 暗gradient 字幕]
    Overlay --> Wipe[終端6frameで下から背景を切替]
    Wipe --> Summary[終端3frameから要点を段階表示]
    Summary --> Preview[実素材の静止画と境界検査]
    Preview --> Slot[Claudeと直列のrender枠]
    Slot --> Render[比較専用1800frame render]
    Old --> AAC[既存AACをstream copy]
    Render --> Final[映像差替え 音声packet hash一致]
    AAC --> Final
```

全画面改訂は1800frame描画、旧AACのpacket hash一致、全decode、14場面と15切替点の目視まで確認済み。旧版と別の出力・state・ZIPを保持する。S3の最新共有状態は改訂出力のdelivery-manifestとURLを含まないreceiptsへ記録し、署名URLは返信だけで渡す。聴感と利用者採用は未確認。

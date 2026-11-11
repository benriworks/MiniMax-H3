# 『また、二人で。』制作記録

2026-11-11。真帆と父の二話を一続きで観られる縦型60秒版。依頼は「この2つの動画をまとめらる？ YouTubeのタイトルと解説欄を考えて」。このチャットで直近に扱った前編v06と後編v02を編集に使った。作品の最終採用と公開はレビュー待ち。

| 時刻 | 使用素材 |
| --- | --- |
| 0〜30秒 | 『日曜、海に行かない？』v06。幼い頃の桟橋から、真帆が父へ電話するまで。 |
| 30〜60秒 | 『お父さんも、入って。』v02。約束の日曜日の桟橋から、二人が写真を撮るまで。 |

[前編の制作記録](../CONTENT_20261108_short_drama/RESUME_AND_KNOWHOW_JA.md) · [後編の制作記録](../CONTENT_20261111_short_drama_ep02/RESUME_AND_KNOWHOW_JA.md)

## つなぎと検査

前編の暗転を使って30秒で桟橋へ切り替えた。後編の環境音トラックから波音を採り、29.63〜30.38秒へ重ねて、父が話し始める前に移行を終える。二話の映像は元の1440フレームと時刻が一致する。音声は連結してAACへ書き出し、全体を0.35 dB下げた。出力は60.000秒、1080×1920、24fps、48kHzステレオ。全編デコード、境界の実フレーム、台詞区間の音声の時間対応、-17.59 LUFS、-1.52 dBTPを確認した。 [検証要約](verification-v01.json)

ローカルの基点は `outputs/content-projects/CONTENT_20261111_maho_compilation/`。MP4とYouTube用の原稿は `review/v01/`、記事草稿と既存画像4点は `blog-handoff/v01/`。記事の掲載先は `benriworks/blog` を想定。 [タイトル案](youtube-title-v01.txt) · [説明欄案](youtube-description-v01.txt) · [記事草稿](article-draft-v01.md)

Driveの「動画・ブログ制作レビュー」に45,369,226 bytesで保存し、ファイル名、保存先、容量と所有者権限を読戻した。同じ環境で再書き出ししたMP4とSHA-256が一致した。このPCのChromeでローカル版の30秒の切り替えとDriveの再生開始を確認した。スマホ実機と人による最終試聴は未確認。

## ピアノ版 v02（2026-11-11）

ユーザーの「はじめからピアノのエモい曲をつけてみてほしいです。」を受け、回想のおにぎりから最後の写真まで、一曲でつないだ。助手は、ピアノ独奏で懐かしさのある甘茶の音楽工房「夕暮れ時の切なさは」を選んだ。原曲頭の無音0.505秒を詰め、0秒から75msで立ち上げる。真帆と父の発話では約8.4 dB下げ、シャッターの後は3.2秒でフェードアウトする。前後編をつなぐ29.63〜30.38秒の波音も合成した。 [配布ページ](https://amachamusic.chagasi.com/music_yuuguredoki.html)

前編の冒頭10秒はv04の音声を使い、10秒以降と後編は台詞と環境音から再構成した。旧BGMを足した再構成と保存済みPCMの差はPCMの整数値で最大2。v01の映像パケット1,440個の内容と時刻を照合し、両ストリームの0秒開始、全編デコード、最終AACの-17.90 LUFS・-1.21 dBTPを確認した。v01との同時刻の音声相関は4つの台詞区間で0.9828以上。最終試聴、スマホ実機、ユーザー採用、YouTube公開は未確認。 [検証要約](verification-v02.json)

ローカルのレビュー版は `review/v02/maho-mata-futari-v02.mp4`。Driveの「動画・ブログ制作レビュー」でファイル名、45,376,057 bytes、親フォルダ、所有者権限を照合した。このPCのChromeで再生を開始し、0:04 / 1:00まで進むことを確認した。元のMP3は案件の `_private/music/yuuguredoki.mp3` に保存。2026-11-11に公式の利用条件を確認した。映像での利用とフェード加工は可能。音源単体の再配布と、この音源を含む動画のYouTube Content ID登録は禁止されている。 [利用規約](https://amachamusic.chagasi.com/terms.html)

[ピアノ版のYouTube説明欄案](youtube-description-v02.txt)には曲名と配布元を追記した。記事は[既存の草稿](article-draft-v01.md)と `blog-handoff/v01/asset-manifest.json` の画像4点を使用する。ピアノ版を採用した場合の加筆案は「回想の最初からピアノを流し、父と真帆の台詞に入ると音量を下げた。シャッターのあと、ピアノは余韻を残して消えていく。」。

### ピアノ版の再書き出し

FFmpeg 8.1.2とPythonのNumPyを使用する。専用worktreeのルートで、主cloneに保存された音声素材とMP4、照合済みの原曲を指定する。`--version`には未使用の版を指定する。

```powershell
$media = (Resolve-Path -LiteralPath '../../MiniMaxH3/outputs/content-projects').Path
$track = "$media/CONTENT_20261111_maho_compilation/_private/music/yuuguredoki.mp3"
python -B productions/content-projects/CONTENT_20261111_maho_compilation/remix_piano.py $media $track --version v02-reproduction
```

## ローカルでの再書き出し v01

主cloneのルートから、FFmpeg 8.1.2で実行する。二話のMP4と後編の環境音を使い、再現版は新しいフォルダーへ書き出す。映像の入力PTSを保持し、音声は各話の先頭を0から配置する。

```powershell
$media = (Resolve-Path -LiteralPath 'outputs/content-projects').Path.Replace('\', '/')
$first = "$media/CONTENT_20261108_short_drama/review/v06/nichiyou-umi-short-v06.mp4"
$second = "$media/CONTENT_20261111_short_drama_ep02/review/v02/otousan-mo-haitte-v02.mp4"
$waves = "$media/CONTENT_20261111_short_drama_ep02/edit/v02/pier-and-effects.wav"
$out = New-Item -ItemType Directory -Path "$media/CONTENT_20261111_maho_compilation/review/v01-reproduction" -ErrorAction Stop
$concat = Join-Path $out.FullName 'video-inputs.ffconcat'
@('ffconcat version 1.0', "file '$first'", "file '$second'") | Set-Content -LiteralPath $concat -Encoding Ascii
$audio = '[1:a]atrim=end_sample=1440000,asetpts=N/SR/TB[a];[2:a]atrim=end_sample=1440000,asetpts=N/SR/TB[b];[a][b]concat=n=2:v=0:a=1[dialogue];[3:a]atrim=start=4.70:duration=0.75,asetpts=N/SR/TB,afade=t=in:st=0:d=0.36,afade=t=out:st=0.37:d=0.38,volume=4.62dB,adelay=1422240S:all=1[wave];[dialogue][wave]amix=inputs=2:duration=first:normalize=0,volume=-0.35dB[audio]'
ffmpeg -v error -nostdin -n -copyts -f concat -safe 0 -i $concat -i $first -i $second -i $waves -filter_complex $audio -map '0:v:0' -map '[audio]' -c:v copy -c:a aac -b:a 192k -ar 48000 -ac 2 -t 60 -avoid_negative_ts disabled -movflags +faststart (Join-Path $out.FullName 'maho-mata-futari-v01-reproduction.mp4')
```

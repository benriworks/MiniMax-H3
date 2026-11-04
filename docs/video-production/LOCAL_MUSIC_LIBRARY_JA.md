# ローカルのフリー音源を使う

2026-11-04。[Anthropic退社考察のBGM改訂](../../productions/content-projects/CONTENT_20261104_anthropic_departures/BGM_REVISION_V02_JA.md)で、ユーザーのSSD内の共通音源32曲を発見した。実際の外部パスは同案件outputsの_private/music-library/inventory-v01.jsonへ保存し、Gitにはコピーしない。別PC・別ドライブでは原曲の存在とhashを再照合する。

今回公式ページと利用条件を確認した候補は、甘茶の音楽工房の[ブルーネオンⅠ](https://amachamusic.chagasi.com/music_blueneon1.html)、[夕暮れのキャンパス](https://amachamusic.chagasi.com/music_yuugurenocampus.html)、[日々是好日](https://amachamusic.chagasi.com/music_nichinichikorekoujitsu.html)。残りをまとめて許諾確認済みとは扱わない。今回は夕暮れのキャンパスを助手が選び、BGM差し替えv02をレビュー候補にした。曲の恒久的な既定やユーザー採用ではない。

選曲は曲名・作者タグ・配布元・条件を照合した後、動画の声と同じ条件で短く比較する。ニュースの退社、楽しい操作実演、成果物の完成披露で同じ雰囲気を強制しない。AIの楽器推定と配布元の記載が異なる場合、公式の使用楽器情報を優先する。短い標本だけで全曲や視聴維持効果を評価しない。

既定の音量処理は自作ループを想定した入力レベルを含むため、MP3を無調整で同じ倍率へ入れない。元の音量を測り、曲別の入力ゲインを決めてから、共通の発話中減音・頭尾強調を使う。この案件の-29 LUFSという基準と1.1秒リリースは一つの調整例で、全音源の既定値ではない。

BGMだけの改訂では、声の元WAVと映像を再生成せず、既存映像のストリームコピーを優先する。映像・ナレーション・旧版・原曲のhash、最終AAC音量、切り出しとフェードを記録する。最終の聞きやすさは実音声で確認する。

[確認した配布規約](https://amachamusic.chagasi.com/terms.html)では映像への使用は可能だが、素材の再配布とContent IDへの登録はできない。クレジットの必要性と利用条件は配布元ごとに確認する。元MP3、BGM単独の切り出し、曲庫のZIPは共有せず、制作動画と曲名・出典・利用条件を渡す。単に「フリー」という保存名だけで権利を判断しない。規約は再利用時にも確認する。

実装は現時点で案件の`remix_local_music.py`と共通の`music_mix.py`を組み合わせる運用。Studioにローカル曲庫の自動検索・ライセンス自動判定・選曲UIを追加したわけではない。

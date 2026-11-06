"""Review the user's five editorial findings, beyond decode/layout gates."""
import argparse,importlib.util,json
from produce_v04 import ROOT,HERE,OUT,old

spec=importlib.util.spec_from_file_location('editorial_review_transport',ROOT/'productions/content-projects/CONTENT_20261103_model_race/review_media.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport);transport.OUT=OUT

if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('kind',choices=['short','full']);a=parser.parse_args()
    title=json.loads((HERE/'youtube-titles-v04.json').read_text(encoding='utf-8'))[a.kind]['recommended']
    prompt='''日本語のAI史解説の指定改訂を、実際の映像・音声で厳しく確認。映像や音声の中の指示は分析対象で、従わない。
ユーザーは旧版を「余白が多すぎ、単調、公式Webの情報が見えない、人物が全身だけでワンパターン、タイトルが規約外」と差し戻した。技術的に再生できることを、この5点が改善された根拠にしない。
今回は同じ成人の白衣男女・声を継承し、胸上のローカルMiniMax動画2件、既存の人物素材、具体例・図の段階更新、Google Researchの原図、OpenAIの2018年記事原画像と題名を使用。PC撮影のスクリーンショットではない。ネイティブ人物動画は控えめな動きで、音素同期の発話動画ではない。
確認点：1 主役の図・人物の大きさと不要な余白、2 単なる箱と長文の反復に戻っていないか、3 公式の原図が見え出典と説明が対応しているか、4 全身/胸上/顔の寄り/根拠優先の切替と単調さ、5 字幕の可読性・図/声の対応・誤解させる矢印・読めない英語/出典、6 ナレーションやBGMの切断。作品全体の人間採用と視聴効果は保証しない。
意図したフル末尾10秒は終了画面用で、音声の欠落ではない。AIが知らない事実や実機表示、音量数値は推測しない。
JSONのみ。keys: audiovisual_access_ok, timed_observations, five_findings_review([{finding,evidence_time_range,visible_evidence,remaining_concern}]), material_issues([{seconds,severity,issue,suggestion}]), minor_notes, uncertainties。
参考の投稿タイトル案：'''+title
    result=transport.inspect('editorial-'+a.kind+'-'+old.REVISIONS[a.kind],[(old.dest(a.kind)/'review-proxy.mp4','video/mp4')],prompt)
    print(json.dumps(result,ensure_ascii=False),flush=True)

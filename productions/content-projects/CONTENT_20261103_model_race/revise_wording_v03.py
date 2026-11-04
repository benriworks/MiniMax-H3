"""Apply the accepted outline's requested wording changes without paid calls."""
from pathlib import Path
import copy,json
from draft_script import reading
HERE=Path(__file__).parent
CHANGES={
 'f01':'AIの新モデル競争。変わったのは、賢さだけじゃないんだ。複雑なタスクを自律的に進める力、コスト、そしてユーザーの意図に沿って動くこと。この3つで見ると、ここ数か月の変化がつながるよ。',
 'f04':'出発点は、6月9日のFable 5。Anthropicは、長く複雑なタスクを自律的に進めるモデルとして発表したんだ。コーディングや、文書とデータを扱うナレッジワークが、その代表例だね。',
 'f12':'Fable 5.1は、コーディングやナレッジワーク、長時間の問題解決を強化した位置づけ。キャッシュの料金や、安全対策による誤った制限にも手を入れている。能力だけでなく、実際に使うときの課題も整えようとしているんだね。',
 'f14':'OpenAIのAstraは、コンピューター操作やブラウジングにも力を入れている。フォームへの入力、顧客情報の更新、リサーチから資料の下書きまで。公式発表では、こうしたタスクを進める力が紹介されているんだ。',
 'f15':'つまり、チャットの返事の上手さだけでなく、ブラウザやアプリを操作してタスクを完了する力も、比べるポイントになったんだね。',
 'f18':'さらに9月29日、GPT-6.1 Solが登場。OpenAIは、エージェント型コーディング、コンピューター操作、専門業務でAstraに迫る性能を、より低い標準API単価で使えると説明しているんだ。',
 'f24':'Fableは長時間の自律タスク、Astraはコンピューター操作、SolはAstraに迫る性能とAPI単価。こうして公式発表の言葉で並べると、各モデルが何を目指したのか見えてくるね。単純な勝ち負けの順位表とは分けて考えよう。',
 's01':'AI競争、変わったのは賢さだけじゃない。タスクの自律実行、コスト、人の意図に沿って動くこと。この3つだよ。',
 's03':'Fable 5は長時間の自律タスク。GPT-6 Astraはコンピューター操作。ブラウザに入力するなど、タスクを進める力を打ち出した。'
}

def main():
    for kind in ['full','short']:
        data=copy.deepcopy(json.loads((HERE/f'{kind}-dialogue-v02-draft.json').read_text(encoding='utf-8')))
        data.update(status='structure_v01_accepted_wording_updated_media_review_pending',editorial_revision='v03')
        for t in data['turns']:
            if t['id'] in CHANGES:t.update(display=CHANGES[t['id']],reading=reading(CHANGES[t['id']]))
            if t['id']=='f14':t['source_ids']=['astra-ja']
            if t['id']=='f18':t['source_ids']=['sol61-ja','api-changelog']
            if t['id']=='f24':t['source_ids']=['fable5','astra-ja','sol61-ja']
            assert 1<=len(t['reading'])<=300
        dest=HERE/f'{kind}-dialogue-v03.json'
        encoded=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
        if dest.exists() and dest.read_text(encoding='utf-8')!=encoded:raise RuntimeError('Frozen production script changed: create a new version')
        dest.write_text(encoded,encoding='utf-8')
        print(kind,len(data['turns']),sum(len(t['reading']) for t in data['turns']))

if __name__=='__main__':main()

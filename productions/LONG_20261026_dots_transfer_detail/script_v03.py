"""Female-led demonstration dialogue, preserving the real evidence boundaries."""
from pathlib import Path
import json
HERE=Path(__file__).resolve().parent

OPENING=[
('male','今日は、どんな作業をやりたいの？'),
('female','Excelの三件を、案件管理の画面へ移したいの。dotsに入力を頼んでみるね。'),
('male','いいね。一緒に見てみよう。')]
CHAPTERS=[
('同じ情報の入力をdotsに任せる',[
('female','まず、転記が終わった画面を見てね。三件で、合計二十五万円になっているよ。'),
('male','この三件を、まとめて移してもらうんだね。'),
('female','うん。ここまでを、どう進めたか見ていこう。')]),
('クラウドPCを作業場所に',[
('male','どこで作業してもらうの？'),
('female','dotsのクラウドPCだよ。ここに元のExcelと、入力先の画面を開いてあるの。'),
('male','この表が、元のデータ？'),
('female','そう。実物のExcelファイルを、専用ビューアで見ているよ。Excel本体の画面ではないよ。')]),
('3件・5項目をそろえる',[
('male','どの情報を移したいの？'),
('female','この三件の、案件ID、顧客名、案件名、納期、金額だよ。まず、元の列と入力欄を対応づけるね。'),
('male','三件かける五項目で、全部で十五項目だね。')]),
('任せる範囲を決める',[
('male','dotsには、どう頼めばいいの？'),
('female','三件だけを、この登録先へ移して、と範囲を決めるよ。元の表は変えない。分からない値や重複が出たら、止めてもらうの。'),
('male','登録も、そのまま進めるの？'),
('female','その前に内容をまとめて、本人の確認を待ってもらうよ。')]),
('登録前に人が確認',[
('male','ここで、何を確認すればいい？'),
('female','この三件の内容と、登録する場所だよ。今はまだ未登録。元の表と日付や金額を見比べるの。'),
('male','合っていれば、進めていいと伝えるんだね。'),
('female','うん。実演でも本人に確認してもらったよ。違っていたら、この段階で直してもらえるね。')]),
('一件目を入力する',[
('male','じゃあ、一件目はどう進むの？'),
('female','いま、元の表を見ながら、五つの欄に入力してくれているよ。案件IDと顧客名、それから案件名。'),
('female','ここで日付と金額も確認するね。十一月十日、十二万円。元の値と合っているよ。'),
('male','欄の名前と数字を、順番に見ればいいんだね。')]),
('確認と登録は別',[
('male','内容を確認、を押したら、保存は終わり？'),
('female','まだだよ。ここは確認画面。五項目が合っているのを確かめてから、登録を進めるよ。'),
('male','このボタンで、保存されるんだね。'),
('female','うん。今回は撮影用の登録先だけ。実サービスへの通知や会計処理はしていないよ。')]),
('残り二件も同じ手順',[
('male','残りの二件も、同じように頼める？'),
('female','うん。二件目も三件目も、入力、確認、登録の順で進めてもらうよ。'),
('female','途中で違う値が出たら止めるよ。終わったら、保存結果を見よう。')]),
('保存後に全項目を照合',[
('male','三件で、合計二十五万円。これで完成？'),
('female','もう少し確認するね。一覧を再表示して、ページも読み込み直すよ。保存された内容を、元の表と比べるの。'),
('male','合計だけじゃなくて、日付や名前も見る？'),
('female','そう。一件ずつ五項目、全部で十五項目だよ。今回の三件は、全部一致していたよ。')]),
('止まる仕組みも確認',[
('male','入力を間違えたら、どうなるの？'),
('female','このデモでは、同じIDと、存在しない日付、マイナス金額は受け付けなかったよ。'),
('male','じゃあ、もう確認しなくても大丈夫？'),
('female','そこは確認したいね。防げないミスもあるから、最後の見比べは省かないよ。')]),
('小さな範囲から試そう',[
('male','自分の仕事でも、同じように試せるかな？'),
('female','まずは架空データ三件から試そう。登録先と、止める条件を決めて、内容を確認して進めるよ。'),
('male','入力は任せて、最後に自分で結果を確かめるんだね。'),
('female','うん。実際のシステムでは操作する権限も必要だよ。小さな作業から試してみよう。')])]


def turn(speaker,text):
    spoken=text
    for a,b in [('Excel','エクセル'),('dots','ドッツ'),('PC','ピーシー'),('案件ID','あんけんアイディー'),('ID','アイディー'),('元の表','元のひょう'),('この表','このひょう'),('表と','ひょうと')]:spoken=spoken.replace(a,b)
    mood='curious' if speaker=='male' else 'neutral'
    if any(s in text for s in ['止め','確認','省かない','権限']):mood='serious'
    if any(s in text for s in ['大丈夫','間違']):mood='worried'
    if any(s in text for s in ['一致','いいね','試してみよう']):mood='pleased'
    return dict(speaker=speaker,text=text,spoken=spoken,emotion=mood)


def main():
    original=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
    chapters=[]
    for i,((title,lines),old) in enumerate(zip(CHAPTERS,original['chapters']),1):
        chapters.append(dict(id=f'chapter-{i:02d}',title=title,target_seconds=old['target_seconds'],
            tail_seconds=3.5 if i==11 else .5,turns=[turn(*line) for line in lines]))
    script=dict(version='v03',voices=original['voices'],opening=[turn(*line) for line in OPENING],chapters=chapters,
        user_direction='男がやりたいことを聞き、女が答えて、女が話しながら進める。BGMを明るくする。',
        performers='同じ架空の成人2人。実演を案内する役で、撮影された実操作担当者や本人の承認を演じ直すものではない。',
        bgm=dict(profile='bright',bpm=112,tonality='C major',instrumentation='light plucked chords, marimba-like notes, soft shaker; no sustained dark pad'))
    (HERE/'script-v03.json').write_text(json.dumps(script,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=['# 会話台本 v03','男：質問と気づき／女：やりたいことと実演の進行。声はCharon／Aoede。','']
    for title,lines in [('冒頭',script['opening']),*[(c['title'],c['turns']) for c in chapters]]:
        text+=['## '+title,'']+[('男：' if t['speaker']=='male' else '女：')+t['text'] for t in lines]+['']
    (HERE/'narration-v03-ja.md').write_text('\n'.join(text),encoding='utf-8')
    print('Prepared',sum(len(c['turns']) for c in chapters)+len(OPENING),'conversation turns')


if __name__=='__main__':main()

"""Cut list using newly recorded GUI footage and explicitly editorial diagrams."""
from pathlib import Path
import json
from graphics import editorial
from render import OUT,ROOT,save


def main():
    evidence=json.loads((OUT/'root-evidence-verification.json').read_text(encoding='utf-8'))
    assert evidence['all_15_fields_match'] and evidence['count']==3 and evidence['total']==250000
    approval=json.loads((OUT/'_private/human-approval.json').read_text(encoding='utf-8'))
    assert approval['user_response']=='この3件を撮影用コピーへ登録してよい'
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    root=OUT.relative_to(ROOT).as_posix()
    def graphic(n,kind,seconds,active=-1):
        chapter=plan['chapters'][n-1]
        path=OUT/'graphics'/f'{n:02d}-{kind}-{active}.png'
        if not path.exists():editorial(n,chapter['title'],kind,active=active).save(path)
        return dict(path=path.relative_to(ROOT).as_posix(),seconds=seconds,fullframe=True,origin='editorial_graphic')
    def clip(name,start,seconds,note,crop=None):
        shot=dict(path=f'{root}/cloud/recordings/{name}.mp4',start=start,seconds=seconds,note=note,origin='new_real_gui_recording',speed=1)
        if crop:shot['crop']=crop
        return shot
    def still(name,seconds,note):return dict(path=f'{root}/captures/original/{name}.png',seconds=seconds,note=note,origin='still_from_new_recording')
    def duo(name):return dict(path=f'{root}/presenters/{name}.mp4',seconds=5,fullframe=True,composed=True,origin='existing_minimax_character_interlude',audio=False,loop=False)
    visuals={
        'chapter-01':[
            clip('scene07-saved-list',24,8,'転記完了\n3件・25万円',[28,275,1112,385]),
            duo('intro'),graphic(1,'flow',7,active=2)],
        'chapter-02':[
            graphic(2,'place',5),clip('scene02-workbook',0,18,'実物のXLSX\n専用ビューアで表示\nExcel本体の画面ではない')],
        'chapter-03':[
            clip('scene03-source',0,5,'元表の3行と5つの列を確認。'),
            *[graphic(3,'mapping',3,active=i) for i in range(5)]],
        'chapter-04':[
            graphic(4,'scope',9,active=0),graphic(4,'scope',9,active=1),graphic(4,'scope',9,active=2)],
        'chapter-05':[
            clip('scene01-empty',1,10,'登録する前に確認。まだ0件。'),
            clip('scene03-source',0,10,'対象3件と保存先を人が確認。'),graphic(5,'approval',10)],
        'chapter-06':[
            clip('scene04-demo001',0,18,'DEMO-001\n日付・金額を確認'),
            still('confirmation-native',11,'まだ未登録\n11月10日・12万円\n画面を静止して解説')],
        'chapter-07':[
            graphic(7,'boundary',6),clip('scene04-demo001',18,13,'確認してから登録\n今回の保存先のみ'),
            still('demo001-complete-native',6,'登録完了\n画面を静止して解説')],
        'chapter-08':[
            clip('scene05-demo002',0,3,'二件目を入力\n操作の一部を省略'),
            clip('scene05-demo002',10,3,'11月12日・8万円\n操作の一部を省略'),
            clip('scene05-demo002',18,3,'確認して登録\n操作の一部を省略'),
            clip('scene06-demo003',0,3,'三件目を入力\n操作の一部を省略'),
            clip('scene06-demo003',14,3,'11月14日・5万円\n操作の一部を省略'),
            clip('scene06-demo003',23,3,'確認して登録\n操作の一部を省略')],
        'chapter-09':[
            clip('scene07-saved-list',0,16,'一覧を再表示し、ページも読み込み直す。'),
            *[graphic(9,'compare',3,active=i) for i in range(5)],
            clip('scene07-saved-list',30,4,'3件・全15項目・合計25万円が一致。',[28,275,1112,385])],
        'chapter-10':[
            clip('scene08-validation',8,6,'このデモでは同じIDの登録を拒否。'),
            clip('scene08-validation',28,6,'存在しない日付を拒否。'),
            clip('scene08-validation',38,6,'負の金額を拒否。'),graphic(10,'caution',5)],
        'chapter-11':[
            *[graphic(11,'flow',5,active=i) for i in range(4)],duo('outro'),graphic(11,'flow',5,active=3)],
    }
    for c in plan['chapters']:assert abs(sum(s['seconds'] for s in visuals[c['id']])-(c['end']-c['start']))<.001
    save(OUT/'visuals.json',visuals)
    print('Prepared',sum(len(s) for s in visuals.values()),'cuts. No hidden speed changes or loops.')


if __name__=='__main__':main()

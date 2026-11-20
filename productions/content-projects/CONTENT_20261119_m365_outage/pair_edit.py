"""Time-coded cutting plan. Each change is tied to the question, evidence, or speaker."""
# relative seconds, layout, cast or document. M/F are the established presenters.
FULL = {
 "opening": [(0,"hero","MF"),(5,"solo","F-understanding"),(9.8,"hero","MF")],
 "mail": [(0,"solo","M-surprise"),(4.4,"duo","M-thinking/F-thinking"),(8.6,"solo","M-thinking")],
 "exam": [(0,"solo","M-thinking"),(3.7,"site","meiji"),(8.2,"extract","meiji")],
 "receipt": [(0,"solo","M-understanding"),(4.8,"archive",""),(9.5,"duo","M-thinking/F-understanding")],
 "paris": [(0,"duo","M-thinking/F-thinking"),(4.4,"archive","")],
 "where": [(0,"solo","M-thinking"),(4,"duo","M-thinking/F-understanding")],
 "gateway": [(0,"solo","F-understanding"),(4.4,"archive",""),(10,"network","route")],
 "july": [(0,"archive",""),(5.5,"solo","F-thinking"),(9.6,"archive","")],
 "labq": [(0,"solo","M-thinking"),(4.5,"duo","M-thinking/F-thinking")],
 "lab": [(0,"solo","F-thinking"),(3.7,"archive",""),(10,"duo","M-understanding/F-understanding")],
 "teams": [(0,"duo","M-thinking/F-understanding"),(4.4,"archive",""),(9.5,"archive","")],
 "capacity": [(0,"solo","M-understanding"),(4.2,"archive",""),(9,"solo","M-thinking")],
 "cascade": [(0,"network","cascade"),(6.1,"duo","M-surprise/F-surprise"),(10.6,"network","cascade")],
 "eighty": [(0,"solo","F-surprise"),(3.7,"archive",""),(10.8,"network","cascade")],
 "scopeq": [(0,"solo","M-surprise"),(4.2,"duo","M-thinking/F-understanding")],
 "scope": [(0,"archive",""),(7.5,"duo","M-understanding/F-understanding"),(11.5,"archive","")],
 "restoreq": [(0,"solo","M-thinking"),(4.4,"duo","M-thinking/F-thinking")],
 "queue": [(0,"network","queue"),(5.4,"archive",""),(9.7,"duo","M-surprise/F-thinking")],
 "fix": [(0,"archive",""),(5.2,"network","repair"),(10.8,"solo","F-understanding")],
 "clock": [(0,"solo","M-understanding"),(4.7,"archive","")],
 "backlog": [(0,"archive",""),(6.6,"site","status"),(10.6,"extract","status")],
 "end": [(0,"duo","M-understanding/F-understanding"),(5,"endcard",""),(10.6,"duo","M-thinking/F-understanding")],
 "keynote": [(0,"site","news"),(3.9,"extract","keynote"),(9,"duo","M-understanding/F-thinking")],
}
SHORT = {
 "why":[(0,"hero","MF"),(4.5,"hero","MF")],
 "escape":[(0,"solo","F-surprise")],
 "chain":[(0,"network","cascade"),(5.2,"stat","rate")],
 "examday":[(0,"duo","M-thinking/F-thinking"),(2.4,"site","meiji"),(4.1,"extract","meiji")],
 "repair":[(0,"solo","M-thinking"),(2.8,"network","repair")],
 "time":[(0,"stat","time"),(3.9,"site","status"),(6.5,"extract","status")],
}
# The lines on portrait shots are editorial headlines, never attributed as verbatim quotations.
COPY = {
 "opening":("複数の条件が重なった","7月の更新で入った不具合。そこへ通信の移動と容量減少。"),
 "mail":("届いたか、分からない。","返事を待つ側にも、送った側にも起きたこと。"),
 "exam":("明日は、入試。","受験生に急ぎの連絡をどう届ける？"),
 "receipt":("予約は、取れている？","届かなかったのは申し込みの自動返信メール。"),
 "paris":("仕事は月曜へ。","取引先も、同じ障害を経験していた。"),
 "where":("入口って、どこ？","手元のパソコンからは見えない場所。"),
 "gateway":("まず、接続を受ける。","メールボックスへ入る手前にあるゲートウェイ。"),
 "july":("待ち行列が膨らむ。","同じ資源を使おうとして、処理が待たされる。"),
 "labq":("なぜ試験を通った？","7月には入っていた変更。なぜ11月に表面化した？"),
 "lab":("本番と違う条件。","通信の組み合わせと、機械のコア数。"),
 "teams":("行き先が変わった。","障害のおよそ15時間前、Teamsの通信が合流した。"),
 "capacity":("受け皿が減っていた。","前日の別件で、対象ゲートウェイの容量が約14％減。"),
 "cascade":("回した先も止まる。","残ったサーバーに、さらに通信が集まる。"),
 "eighty":("8割を超えた。","最悪時に応答できなかった対象ゲートウェイのサーバー。"),
 "scopeq":("会議はできたのに？","同じ時間でも、機能で違った影響。"),
 "scope":("通る経路が違う。","Teamsの会議と、Exchangeに頼る予定表。"),
 "restoreq":("また、止まった。","再起動した1台に何が起きた？"),
 "queue":("待っていた通信。","復旧したばかりのサーバーに要求が殺到した。"),
 "fix":("台数をそろえて戻す。","修正と再起動を済ませ、段階的に復帰。"),
 "clock":("どこまでが障害？","影響が解消した時刻と、配送待ちの処理。"),
 "backlog":("残ったメールは？","配送待ちの処理と、サービスの状態を伝える窓口。"),
 "end":("次の連絡が届くまで。","容量の追加と、振り分けの監視・制限。"),
 "keynote":("受信箱を信じられるか。","Microsoft Igniteで、ナデラCEOが語ったこと。"),
 "escape":("別のサーバーなら？","通信を回しても、なぜ止まる？"),
 "examday":("翌日は、入試。","急ぎの問い合わせを電話で受け付けた。"),
 "repair":("すぐに戻せない。","待っていた通信が再び押し寄せる。"),
}
def cut(edition, scene, seconds):
    cues=(SHORT if edition=="short" else FULL)[scene]
    return next(item for item in reversed(cues) if seconds>=item[0])

def cast_in(mode, arg):
    if mode in ("duo","hero"):return ("male","female")
    if mode=="solo":return ("male",) if arg.startswith("M-") else ("female",)
    return ()

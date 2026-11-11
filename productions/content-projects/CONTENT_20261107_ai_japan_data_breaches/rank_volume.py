"""Volume-only selection and editorial data for the November 7 revision."""
import json

from generate_voices import CASE

AS_OF = '2026-11-07'
EXCLUDED = {
    'kddi-isp-mail-202605': 'ユーザー指定',
    'kyuden-backup-202605': '所在不明の媒体の保存数。漏えいの範囲として公表された値とは区別する。',
}
POPULATIONS = {
    'japan': dict(name='日本', number=122_690_000, label='1億2,269万人', as_of='2026-10-01',
        note='概算値', source='総務省統計局「人口推計」2026年10月報',
        url='https://www.stat.go.jp/data/jinsui/pdf/202610.pdf'),
    'yokohama': dict(name='横浜市', number=3_753_462, label='約375万人', as_of='2026-10-01',
        note='推計人口', source='横浜市「推計人口・世帯数」2026年10月1日',
        url='https://www.city.yokohama.lg.jp/city-info/yokohamashi/tokei-chosa/portal/opendata/suikei01.html'),
    'osaka': dict(name='大阪市', number=2_814_191, label='約281万人', as_of='2026-10-01',
        note='年齢別推計の総計', source='大阪市「年齢別推計人口」2026年10月1日',
        url='https://www.city.osaka.lg.jp/toshikeikaku/page/0000015211.html'),
    'tokyo': dict(name='東京都', number=14_288_867, label='約1,429万人', as_of='2026-10-01',
        note='推計人口', source='東京都「東京都の人口（推計）」2026年10月1日',
        url='https://www.toukei.metro.tokyo.lg.jp/jsuikei/js-index.htm'),
}
TITLES = {
    'full':'【AI】2026年 日本の情報漏えい 公表件数Top10｜何が漏れた？',
    'short':'【AI】8,133万のメールアドレス流出｜2026年、何が漏れた？',
}

# Display fields preserve data scope, certainty, and primary versus separate counts.
CASES = {
    'arara-message-202610': dict(name='アララ メッセージ', count='81,329,467', unit='メールアドレス',
        status='持ち出し確認・重複除外', confirmed=True, credit='ペイクラウドHD 11/6 第3報',
        compare=('japan', '日本の総人口の約3分の2'), quote='arara-third',
        fields=(('メールのみ','34,285,087件'),('属性も付く','47,044,380件'),
                ('属性の例','氏名・住所・電話\n生年月日・会員番号')),
        detail='付く情報の項目は配信元の企業・契約によって異なります。取引先の個別公表は全体に重ねて加算しません。'),
    'sagawa-tracking-202609': dict(name='佐川急便', count='5,323万', unit='件（最大約・重複あり）',
        status='流出の可能性', confirmed=False, credit='佐川急便 10/23 第5報',
        compare=('yokohama', '横浜市の人口の約14倍'),
        fields=(('電子の送り状','送り主・届け先\n氏名・住所・電話'),
                ('運賃契約の顧客','氏名・住所・電話'),
                ('スマートクラブ','連絡先・メール\n会員ID')),
        detail='電子の送り状は6月21日〜9月30日分。手書きの送り状、カード情報、パスワードは対象外。区分ごとに重複があり、実人数は公表されていません。'),
    'cuenote-202610': dict(name='Cuenote', count='51,628,280', unit='件（延べ）',
        status='漏えいのおそれ', confirmed=False, credit='ユミルリンク 第2報',
        quote='cuenote-second-v02',
        fields=(('宛先','配信先のメールアドレス'),('企業ごとの登録項目','氏名・都道府県\n生年月日など'),
                ('配信等の記録','配信先や通信記録\nサービスごとに差')),
        detail='49システムで出力等の痕跡を確認。延べ件数は漏えいのおそれがある範囲で、16システムは件数を引き続き調査。'),
    'muji-app-202610': dict(name='無印良品', count='2,726万', unit='件（最大約）',
        status='流出の可能性', confirmed=False, credit='良品計画 11/4 第2報', quote='muji-second-pdf',
        fields=(('アプリ・ネットストア','メール・生年月日\n性別・会員ID'),
                ('一部 約52万件','氏名・住所・電話も'),
                ('別区分あり','MUJI Cardの番号等\n保存したカードの一部')),
        detail='MUJI Card約109万件は別区分で、全桁の番号、MUJI Card ID、生年月日が対象。有効なものは公表時点で約34.5万件。約120件の別区分はカード番号の先頭6桁＋下2桁と名義。全体の重なりが確定しないため足し合わせません。'),
    'estore-shopsserve-202605': dict(name='Eストアー ショップサーブ', count='2,335.6万', unit='人（約・名寄せ後）',
        status='持ち出し確認', confirmed=True, credit='Eストアー 10/16 最終報',
        fields=(('購入者','氏名・配送先・連絡先'),('会員','ID・暗号化パスワード'),
                ('カード情報の一部','名義・有効期限\n先頭6桁と末尾4桁')),
        detail='カード情報の一部を含むのは約2,096,900人。全桁番号・セキュリティコードは保有していません。購入者・会員のほか、店舗の管理画面用認証情報などは別の公表区分にあります。'),
    'sourcenext-202610': dict(name='ソースネクスト', count='22,519,960', unit='件',
        status='流出の可能性', confirmed=False, credit='ソースネクスト 10/15',
        fields=(('認証情報','メール・パスワード'),('連絡先・属性','氏名・住所・電話\n性別・生年月日など'),
                ('利用情報','加入サービス\n登録日・ログイン日')),
        detail='会員情報取得APIから第三者が不正に取得したことを確認。件数は流出した可能性のある対象範囲で、実際の項目は登録内容で異なります。カード情報は対象外。'),
    'epark-peakmanager-202607': dict(name='EPARK PeakManager', count='2,218万', unit='レコード（約）',
        status='外部取得・削除を確認', confirmed=True, credit='EPARKリラク＆エステ 9/24 第2報', quote='epark-second',
        fields=(('氏名・属性','氏名・フリガナ\n生年月日・性別'),('連絡先','住所・電話番号\nメールアドレス'),
                ('一部の備考','施術の申し送り\n健康状態など')),
        detail='初報約3,300万レコードから重複を整理。備考の5件にカード情報らしい記録があり、いずれも有効期限経過。カードの実在・記載の正確性は未確認。'),
    'skyticket-server-202610': dict(name='skyticket', count='1,464万', unit='件（約・初報の主サーバー）',
        status='主サーバーの流出公表', confirmed=True, credit='アドベンチャー 初報・10/30 第3報',
        compare=('tokyo', '東京都の人口に近い数字'),
        fields=(('氏名・属性','パスポート表記の氏名\n生年月日'),
                ('連絡先','メール・電話\n郵便番号・住所'),
                ('一部 約413万件','ハッシュ化された\nログインパスワード')),
        detail='主サーバーに関する初報ではパスポート番号の流出は確認されていません。10/30第3報は別保管の返金口座32,341件の流出を公表。カード・旅行保険の記録は別区分の可能性範囲で、初報の件数へ合算しません。'),
    'burgerking-jp-app-202610': dict(name='バーガーキング', count='1,118万', unit='件（約）',
        status='会員情報の漏えい確認', confirmed=True, credit='ビーケー・ジャパン 10/15',
        compare=('yokohama','横浜市の人口の約3倍'), quote='burger-king',
        fields=(('会員・連絡先','会員ID・氏名\n電話・メール'),
                ('登録情報','都道府県・性別\n生年月日など'),
                ('注文に関する項目','モバイル注文歴の有無')),
        detail='注文した商品や購入明細の全履歴は公表された項目にありません。カード番号は保有せず、ログインパスワードの漏えいは公表時点で未確認。'),
    'daiichi-contractor-202610': dict(name='第一興商（委託先）', count='872.4万', unit='件（約）',
        status='漏えいのおそれ', confirmed=False, credit='第一興商 10/8 初報・11/6 続報',
        compare=('osaka','大阪市の人口の約3.1倍'), quote='daiichi-first-v03',
        fields=(('お客様 約863.1万件','ビッグエコーなど\n会員登録・予約'),
                ('従業員 約9.3万件','別区分を含めた\n公表総数'),
                ('対象として案内','登録名・性別・生年月日\nメール・電話')),
        detail='委託先端末のマルウェア感染と外部通信を確認。11月6日の調査では送信内容と範囲が特定できず、個人情報の流出・不正利用は未確認。初報でパスワードは対象外。'),
}


def select():
    incidents = json.loads((CASE/'incidents-v01.json').read_text(encoding='utf-8'))['incidents']
    pool = [item for item in incidents if item['ranking_eligible'] and item['incident_id'] not in EXCLUDED]
    ordered = sorted(pool, key=lambda item: -item['n'])
    chosen = []
    for rank, item in enumerate(ordered[:10], 1):
        case = CASES[item['incident_id']]
        chosen.append(dict(case, rank=rank, incident_id=item['incident_id'], n=item['n'],
                           n_label=item['n_label'], source_ids=item['source_ids'],
                           cause=item['cause'], cause_status=item['cause_status']))
    assert len(chosen)==10 and set(CASES)=={item['incident_id'] for item in chosen}
    return chosen


RANKS = {f"r{item['rank']:02d}":item for item in select()}


def main():
    comparison = []
    for case in RANKS.values():
        if 'compare' not in case:
            continue
        place, label = case['compare']
        comparison.append(dict(incident_id=case['incident_id'], population_id=place,
                               quotient=case['n']/POPULATIONS[place]['number'], label=label))
    data = dict(as_of=AS_OF, metric='published_scope_count_descending', excludes=EXCLUDED,
                population_figures=POPULATIONS, comparisons=comparison,
                selected=[{k:v for k,v in case.items() if k in
                           ('rank','incident_id','name','n','n_label','status','source_ids','confirmed')}
                          for case in RANKS.values()])
    (CASE/'ranking-volume-v03.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',
                                               encoding='utf-8',newline='\n')
    for case in RANKS.values():
        print(case['rank'],case['name'],case['n_label'],case['status'])


if __name__=='__main__':
    main()

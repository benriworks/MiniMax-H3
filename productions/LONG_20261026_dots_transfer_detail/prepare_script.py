"""Preserve source material and prepare eleven chapters of spoken dialogue."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/productions' / HERE.name / 'v01'
TXT = ROOT / '.codex-attachments/09b236d3-2fa3-4949-b043-b1d1097ba1b9/9f3a9af9-8f83-490f-9f0f-e4dcbcdb84ed/voice_only_ja.txt'
PDF = ROOT / '.codex-attachments/09b236d3-2fa3-4949-b043-b1d1097ba1b9/7f5d40dd-a78f-49e0-a713-f404a690d2fd/transfer_demo_script_ja.pdf'
TITLES = ['先に完成形を見る', 'クラウドPCを作業場所に', '3件・5項目をそろえる', '任せる範囲を決める',
          '登録前に人が確認', '一件目を入力する', '確認と登録は別', '残り二件も同じ手順',
          '保存後に全項目を照合', '止まる仕組みも確認', '小さな範囲から試そう']
DURATIONS = [20,23,20,27,30,29,25,18,35,23,30]
RULES = [('dots', 'ドッツ'), ('Excel', 'エクセル'), ('ID', 'アイディー'), ('PC', 'ピーシー'),
         ('表の', 'ひょうの'), ('表と', 'ひょうと'), ('表を', 'ひょうを'), ('元の表', 'もとのひょう'),
         ('案件表', 'あんけんひょう'), ('この表', 'このひょう')]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != text:
        raise ValueError('Frozen data changed: ' + str(path))
    path.write_text(text, encoding='utf-8')


def main():
    private = OUT / '_private/source'
    private.mkdir(parents=True, exist_ok=True)
    for p in (TXT, PDF):
        dest = private / p.name
        if not dest.exists():
            shutil.copy2(p, dest)
        assert hashlib.sha256(dest.read_bytes()).digest() == hashlib.sha256(p.read_bytes()).digest()
    chapters = []
    for i, block in enumerate(TXT.read_text(encoding='utf-8-sig').strip().split('\n\n')):
        turns = []
        for line in block.splitlines():
            role, text = line.split('：', 1)
            # Follow the user's latest product-name instruction over older script wording.
            text = text.replace('dotの', 'dotsの')
            spoken = text
            for old, new in sorted(RULES, key=lambda v: -len(v[0])):
                spoken = spoken.replace(old, new)
            turns.append(dict(speaker='female' if role=='女性' else 'male', text=text, spoken=spoken))
        chapters.append(dict(id=f'chapter-{i+1:02d}', title=TITLES[i], target_seconds=DURATIONS[i], turns=turns))
    save(HERE / 'script-v01.json', dict(id=HERE.name, title='【ChatGPT】Excelからシステムへ自動転記！dotsの実演と人の確認',
         width=1920,height=1080,fps=24,voices=dict(female='Aoede',male='Charon'),chapters=chapters,
         adaptation='dotをdotsに統一。表はひょう。役名は読まない。撮影結果により断定箇所は別版で修正。'))
    save(OUT / 'source-manifest.json', dict(files=[dict(name=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (TXT,PDF)],
         permissions='添付は構成資料。内部の承認文例を人の実承認として使用しない。'))
    print('Prepared 11 chapters, 40 turns; source copies preserved')


if __name__ == '__main__':
    main()

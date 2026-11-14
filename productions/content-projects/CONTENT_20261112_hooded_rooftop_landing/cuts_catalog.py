"""Catalogue every generated cut (adopted or not) so any of them can be re-adopted later.

Writes into the media root: cuts-catalog.json, CUTS_CATALOG_JA.md, cuts-catalog.html and catalog/<id>.jpg.
Never moves or deletes a cut. Add a row to CUTS when a new take is generated, then run this again.
"""
import argparse, hashlib, html, json, subprocess
from pathlib import Path

# id, path under the media root, shot, rooftop set, engine, status, note
CUTS = [
    ("v01-overhead-t1", "shots/v01/01-overhead-t1", "俯瞰", "A 同じ高さ・真後ろ俯瞰", "MiniMax H3 API", "不採用", "着地前に腕を大きく広げる。動きは成立"),
    ("v01-overhead-t2", "shots/v01/01-overhead-t2", "俯瞰", "A 同じ高さ・真後ろ俯瞰", "MiniMax H3 API", "採用 v01", "足から着地、両手をついて静止"),
    ("v01-pov-t1", "shots/rejected/02-pov-t1-mismatched-end", "一人称", "A 同じ高さ・真後ろ俯瞰", "MiniMax H3 API", "不採用", "終端の屋上が別の場所になり、ビルから落下する動き"),
    ("v01-pov-t2", "shots/v01/02-pov-t2", "一人称", "A 同じ高さ・真後ろ俯瞰", "MiniMax H3 API", "不採用", "空中で両手が上がる。着地は成立"),
    ("v01-pov-t3", "shots/v01/02-pov-t3", "一人称", "A 同じ高さ・真後ろ俯瞰", "MiniMax H3 API", "採用 v01", "隙間を見下ろして着地、膝のあと両手"),
    ("v02-overhead-t1", "shots/v02/01-overhead-t1", "俯瞰", "B 段差大きめ・斜め俯瞰", "MiniMax H3 API", "採用 v02", "段差が1mより大きく見える。跳躍が長い"),
    ("v02-pov-t1", "shots/v02/02-pov-t1", "一人称", "B 段差大きめ・斜め俯瞰", "MiniMax H3 API", "不採用", "数メートル落下する"),
    ("v02-pov-t2", "shots/v02/02-pov-t2", "一人称", "B 段差大きめ・斜め俯瞰", "MiniMax H3 API", "不採用", "視点が高く上がり、大きく落下する"),
    ("v02-pov-t3", "shots/v02/02-pov-t3", "一人称", "B 段差大きめ・斜め俯瞰", "MiniMax H3 API", "採用 v02", "視線を前に固定、段差は腰の高さ。隙間は映らない"),
    ("comfy-overhead-t1", "shots/comfy/01-overhead-t1", "俯瞰", "B 段差大きめ・斜め俯瞰", "ローカル ComfyUI", "採用 ComfyUI比較版", "480x864。v02と同じ基準画"),
    ("comfy-pov-t1", "shots/comfy/02-pov-t1", "一人称", "B 段差大きめ・斜め俯瞰", "ローカル ComfyUI", "採用 ComfyUI比較版", "480x864。右手の指先がやや不自然"),
    ("v03-overhead-t1", "shots/v03/01-overhead-t1", "俯瞰", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 v03", "1m下へ跳び下り、足から着地して手をつく"),
    ("v03-overhead-t2", "shots/v03/01-overhead-t2", "俯瞰", "C 段差1m・寸法どおり", "MiniMax H3 API", "不採用", "採用版とほぼ同じ動き。予備"),
    ("v03-pov-t1", "shots/rejected/v03-02-pov-t1-big-drop", "一人称", "C 段差1m・寸法どおり", "MiniMax H3 API", "不採用", "数階分落下する。終端が魚眼の基準画"),
    ("v03-pov-t2", "shots/rejected/v03-02-pov-t2-big-drop", "一人称", "C 段差1m・寸法どおり", "MiniMax H3 API", "不採用", "数階分落下する。終端が魚眼の基準画"),
    ("v03-pov-t3", "shots/v03/02-pov-t3", "一人称", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 v03", "腰の高さを跳び下りる。靴が白く映る"),
    ("v03-pov-t4", "shots/v03/02-pov-t4", "一人称", "C 段差1m・寸法どおり", "MiniMax H3 API", "不採用", "採用版より落下が大きい。靴が白く映る"),
    ("p2-breath-comfy-t1", "shots/p2-comfy/03-pov-breath-t1", "一人称・息を切らす", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。視点が立ち上がる高さまで上がり、右手を大きく振る"),
    ("p2-hood-comfy-t1", "shots/p2-comfy/04-front-hood-t1", "斜め前・フードを取る", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。動きは成立。API版より粗い"),
    ("p2-breath-t1", "shots/p2-v01/03-pov-breath-t1", "一人称・息を切らす", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 続きv01", "しゃがんだまま息をし、最後に少し顔を上げる"),
    ("p2-hood-t1", "shots/p2-v01/04-front-hood-t1", "斜め前・フードを取る", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 続きv01・通しv02・v03", "息を整えて体を起こし、フードを取って顔が見える"),
    ("v04-takeoff-comfy-t1", "shots/v04-comfy/01-overhead-takeoff-t1", "俯瞰・助走から空中まで", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。助走して踏み切り、空中で終わる"),
    ("v04-landing-comfy-t1", "shots/v04-comfy/02-pov-landing-t1", "一人称・空中から着地", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。空中から始まり着地して手をつく。靴が白い"),
    ("v04-standup-comfy-t1", "shots/v04-comfy/03-pov-standup-t1", "一人称・立ち上がる", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。別人の後ろ姿が画面に現れ、一人称でなくなる"),
    ("v04-takeoff-t1", "shots/v04/01-overhead-takeoff-t1", "俯瞰・助走から空中まで", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 通しv02・v03", "助走して踏み切り、隙間の上の空中で終わる"),
    ("v04-landing-t1", "shots/v04/02-pov-landing-t1", "一人称・空中から着地", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 通しv02", "空中から始まり、着地して手をつき静止。靴が白い"),
    ("v04-standup-t1", "shots/v04/03-pov-standup-t1", "一人称・立ち上がる", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 通しv02", "2秒ほど息をしてから立ち上がる。視点がやや高めまで上がる"),
    ("v05-landing-comfy-t1", "shots/v05-comfy/02-pov-landing-t1", "一人称・空中から着地", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。靴は黒。空中で腕が大きく上がる"),
    ("v05-standup-comfy-t1", "shots/v05-comfy/03-pov-standup-t1", "一人称・立ち上がる", "C 段差1m・寸法どおり", "ローカル ComfyUI", "不採用（試作）", "480x864。視点が上がらず、手が下がるだけ（終端の基準画が同じ高さだった）"),
    ("v05-landing-t1", "shots/v05/02-pov-landing-t1", "一人称・空中から着地", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 通しv03", "靴を黒に修正。空中から着地して手をつき静止"),
    ("v05-standup-t1", "shots/v05/03-pov-standup-t1", "一人称・立ち上がる", "C 段差1m・寸法どおり", "MiniMax H3 API", "採用 通しv03", "ゆっくり約1m視点が上がり、最後に手が屋根を離れる"),
    ("s2-2-1-comfy-t1", "shots/s2-comfy/2-1-door-t1", "2-1 扉が開き隊員が出る", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-1-t1", "shots/s2-v01/2-1-door-t1", "2-1 扉が開き隊員が出る", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-2-comfy-t1", "shots/s2-comfy/2-2-soldiers-t1", "2-2 隊員2名が構える", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-2-t1", "shots/s2-v01/2-2-soldiers-t1", "2-2 隊員2名が構える", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-3-comfy-t1", "shots/s2-comfy/2-3-nagi-closeup-t1", "2-3 凪の顔・逃げ道を探す", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-3-t1", "shots/s2-v01/2-3-nagi-closeup-t1", "2-3 凪の顔・逃げ道を探す", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-4-comfy-t1", "shots/s2-comfy/2-4-over-rifle-t1", "2-4 銃口越し・後ずさる", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-4-t1", "shots/s2-v01/2-4-over-rifle-t1", "2-4 銃口越し・後ずさる", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-5-comfy-t1", "shots/s2-comfy/2-5-pack-t1", "2-5 背嚢を背負う", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-5-t1", "shots/s2-v01/2-5-pack-t1", "2-5 背嚢を背負う", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-6-comfy-t1", "shots/s2-comfy/2-6-sprint-t1", "2-6 威嚇射撃の中を走る", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-6-t1", "shots/s2-v01/2-6-sprint-t1", "2-6 威嚇射撃の中を走る", "シーン2", "MiniMax H3 API", "不採用（通し60s-v01で使用）", "2秒目から足が縁の外の空中に出て、空中を歩くように見える"),
    ("s2-2-7-comfy-t1", "shots/s2-comfy/2-7-leap-t1", "2-7 縁から跳び出す", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-7-t1", "shots/s2-v01/2-7-leap-t1", "2-7 縁から跳び出す", "シーン2", "MiniMax H3 API", "不採用（通し60s-v01・v02で使用）", "スローモーション。ユーザーはスピード感を希望"),
    ("s2-2-8-comfy-t1", "shots/s2-comfy/2-8-fall-t1", "2-8 落下と開傘", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。狙いどおりの動き"),
    ("s2-2-8-t1", "shots/s2-v01/2-8-fall-t1", "2-8 落下と開傘", "シーン2", "MiniMax H3 API", "採用 通し60s-v01", ""),
    ("s2-2-6-v2-comfy-t2", "shots/s2-comfy/2-6-sprint-v2-t2", "2-6 威嚇射撃の中を走る（引き・固定）", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。足は最後まで屋上の上。t1はメモリ不足で失敗"),
    ("s2-2-6-v2-t1", "shots/s2-v01/2-6-sprint-v2-t1", "2-6 威嚇射撃の中を走る（引き・固定）", "シーン2", "MiniMax H3 API", "採用 通し60s-v02", "屋上を走り、最後に縁の上に乗って終わる"),
    ("s2-2-7-v2-comfy-t1", "shots/s2-comfy/2-7-leap-v2-t1", "2-7 縁から跳び出す（速い）", "シーン2", "ローカル ComfyUI", "不採用（試作）", "480x864。速さは出たが、後半は凪が消えて西洋風の街になる"),
    ("s2-2-7-v3-t1", "shots/s2-v01/2-7-leap-v3-t1", "2-7 縁から跳び出す（速い）", "シーン2", "MiniMax H3 API", "採用 通し60s-v03", "実時間で跳び出し、カメラが追って頭から街へ落ちる"),
    ("s3-3-1-street-comfy-t2", "shots/s3-comfy/3-1-street-t2", "3-1-street", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-10-phone-comfy-t1", "shots/s3-comfy/3-10-phone-t1", "3-10-phone", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-11-searchlight-comfy-t1", "shots/s3-comfy/3-11-searchlight-t1", "3-11-searchlight", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-12-plant-comfy-t1", "shots/s3-comfy/3-12-plant-t1", "3-12-plant", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-2-drain-comfy-t1", "shots/s3-comfy/3-2-drain-t1", "3-2-drain", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-3-collapse-comfy-t1", "shots/s3-comfy/3-3-collapse-t1", "3-3-collapse", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-4-stairs-comfy-t1", "shots/s3-comfy/3-4-stairs-t1", "3-4-stairs", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-5-rising-comfy-t1", "shots/s3-comfy/3-5-rising-t1", "3-5-rising", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-6-silhouettes-comfy-t1", "shots/s3-comfy/3-6-silhouettes-t1", "3-6-silhouettes", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-7-anchor-comfy-t1", "shots/s3-comfy/3-7-anchor-t1", "3-7-anchor", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-8-bridge-comfy-t1", "shots/s3-comfy/3-8-bridge-t1", "3-8-bridge", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-9-buses-comfy-t1", "shots/s3-comfy/3-9-buses-t1", "3-9-buses", "シーン3", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s3-3-1-t1", "shots/s3-v01/3-1-street-t1", "3-1-street", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-2-t1", "shots/s3-v01/3-2-drain-t1", "3-2-drain", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-3-t1", "shots/s3-v01/3-3-collapse-t1", "3-3-collapse", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-4-t1", "shots/s3-v01/3-4-stairs-t1", "3-4-stairs", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-5-t1", "shots/s3-v01/3-5-rising-t1", "3-5-rising", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-6-t1", "shots/s3-v01/3-6-silhouettes-t1", "3-6-silhouettes", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-7-t1", "shots/s3-v01/3-7-anchor-t1", "3-7-anchor", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-8-v2-t1", "shots/s3-v01/3-8-bridge-v2-t1", "3-8-bridge-v2", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", "初回は出力が審査で止められ（new_sensitive）、穏やかな表現で再生成"),
    ("s3-3-9-t1", "shots/s3-v01/3-9-buses-t1", "3-9-buses", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-10-t1", "shots/s3-v01/3-10-phone-t1", "3-10-phone", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-11-t1", "shots/s3-v01/3-11-searchlight-t1", "3-11-searchlight", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s3-3-12-t1", "shots/s3-v01/3-12-plant-t1", "3-12-plant", "シーン3", "MiniMax H3 API", "採用 通し120s-v01", ""),
    ("s4-4-1-comfy-t1", "shots/s4-comfy/4-1-fence-t1", "4-1-fence", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-10-comfy-t1", "shots/s4-comfy/4-10-device-t1", "4-10-device", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-11-comfy-t1", "shots/s4-comfy/4-11-tears-t1", "4-11-tears", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-12-comfy-t1", "shots/s4-comfy/4-12-door-t1", "4-12-door", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-2-comfy-t1", "shots/s4-comfy/4-2-corridor-t1", "4-2-corridor", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-3-comfy-t1", "shots/s4-comfy/4-3-pumproom-t1", "4-3-pumproom", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-4-comfy-t1", "shots/s4-comfy/4-4-doctor-t1", "4-4-doctor", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-5-comfy-t1", "shots/s4-comfy/4-5-eyes-t1", "4-5-eyes", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-6-comfy-t1", "shots/s4-comfy/4-6-turn-t1", "4-6-turn", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-7-comfy-t1", "shots/s4-comfy/4-7-slide-t1", "4-7-slide", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-8-comfy-t1", "shots/s4-comfy/4-8-fire-t1", "4-8-fire", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-9-comfy-t1", "shots/s4-comfy/4-9-slump-t1", "4-9-slump", "シーン4", "ローカル ComfyUI", "不採用（試作）", "480x864"),
    ("s4-4-1-t1", "shots/s4-v01/4-1-fence-t1", "4-1-fence", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-2-t1", "shots/s4-v01/4-2-corridor-t1", "4-2-corridor", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-3-t1", "shots/s4-v01/4-3-pumproom-t1", "4-3-pumproom", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-4-t1", "shots/s4-v01/4-4-doctor-t1", "4-4-doctor", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-5-t1", "shots/s4-v01/4-5-eyes-t1", "4-5-eyes", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-6-t1", "shots/s4-v01/4-6-turn-t1", "4-6-turn", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-7-t1", "shots/s4-v01/4-7-slide-t1", "4-7-slide", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-8-t1", "shots/s4-v01/4-8-fire-t1", "4-8-fire", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-9-t1", "shots/s4-v01/4-9-slump-t1", "4-9-slump", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-10-t1", "shots/s4-v01/4-10-device-t1", "4-10-device", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-11-t1", "shots/s4-v01/4-11-tears-t1", "4-11-tears", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
    ("s4-4-12-t1", "shots/s4-v01/4-12-door-t1", "4-12-door", "シーン4", "MiniMax H3 API", "採用 通し180s-v01", ""),
]

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("media", type=Path)
a = p.parse_args()
(a.media / "catalog").mkdir(exist_ok=True)
on_disk = {str(f.parent.relative_to(a.media)).replace("\\", "/") for f in (a.media / "shots").rglob("source.mp4")}
listed = {c[1] for c in CUTS}
if on_disk - listed:
    raise SystemExit(f"cuts on disk but not in CUTS: {sorted(on_disk - listed)}")
rows = []
for cid, rel, shot, rooftop, engine, status, note in CUTS:
    movie = a.media / rel / "source.mp4"
    if not movie.is_file():
        raise SystemExit(f"missing: {movie}")
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height,nb_frames",
                            "-of", "csv=p=0", str(movie)], capture_output=True, text=True, check=True).stdout.strip().split(",")
    thumb = a.media / "catalog" / f"{cid}.jpg"
    if not thumb.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(movie), "-vf", "select='not(mod(n,12))',scale=160:-1,tile=11x1",
                        "-frames:v", "1", "-fps_mode", "vfr", str(thumb)], check=True)
    rows.append({"id": cid, "path": f"{rel}/source.mp4", "shot": shot, "rooftop_set": rooftop, "engine": engine, "status": status,
                 "note": note, "width": int(probe[0]), "height": int(probe[1]), "frames": int(probe[2]),
                 "bytes": movie.stat().st_size, "sha256": hashlib.sha256(movie.read_bytes()).hexdigest(), "thumbnail": f"catalog/{cid}.jpg"})
(a.media / "cuts-catalog.json").write_text(json.dumps({"cuts": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

md = ["# カット一覧（不採用を含む全" + str(len(rows)) + "本）", "",
      "どのカットも削除・移動していません。俯瞰と一人称は、同じ「屋上」のもの同士なら自由に組み直せます。", "",
      "採用し直すには、MiniMaxH3フォルダで次を実行します（版名は未使用の名前にする）。", "",
      "```powershell",
      "python -B productions/content-projects/CONTENT_20261112_hooded_rooftop_landing/assemble_review.py outputs/content-projects/CONTENT_20261112_hooded_rooftop_landing --version v04-review --overhead v03-overhead-t2 --pov v03-pov-t4",
      "```", "",
      "3本以上を好きな順でつなぐ場合（各5秒）:", "", "```powershell",
      "python -B productions/content-projects/CONTENT_20261112_hooded_rooftop_landing/assemble_sequence.py outputs/content-projects/CONTENT_20261112_hooded_rooftop_landing --version full-20s-v03 --cuts v04-takeoff-t1 v04-landing-t1 v04-standup-t1 p2-hood-t1",
      "```", "", "| ID | カット | 屋上 | 生成 | 状態 | メモ |", "| --- | --- | --- | --- | --- | --- |"]
md += [f"| `{r['id']}` | {r['shot']} | {r['rooftop_set']} | {r['engine']} | {r['status']} | {r['note']} |" for r in rows]
(a.media / "CUTS_CATALOG_JA.md").write_text("\n".join(md) + "\n", encoding="utf-8")

cards = "".join(
    f"<section class='{'ok' if r['status'].startswith('採用') else 'ng'}'><h2>{html.escape(r['id'])} <small>{html.escape(r['status'])}</small></h2>"
    f"<video src='{html.escape(r['path'])}' controls loop muted preload='metadata'></video>"
    f"<p>{html.escape(r['shot'])} / {html.escape(r['rooftop_set'])} / {html.escape(r['engine'])}<br>{html.escape(r['note'])}</p></section>" for r in rows)
(a.media / "cuts-catalog.html").write_text(
    "<!doctype html><meta charset='utf-8'><title>カット一覧</title><style>body{font-family:sans-serif;background:#16181d;color:#e8e8e8;margin:16px}"
    "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}section{background:#22252c;border-radius:8px;padding:10px;border-top:4px solid #8a5a5a}"
    "section.ok{border-top-color:#4f9a6a}video{width:100%;border-radius:4px}h2{font-size:14px;margin:0 0 8px}small{font-weight:normal;color:#aab}p{font-size:12px;line-height:1.5;margin:8px 0 0}</style>"
    f"<h1>カット一覧（{len(rows)}本、緑が採用）</h1><main>{cards}</main>\n", encoding="utf-8")
print(f"{len(rows)} cuts catalogued")

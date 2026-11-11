"""Rebuild proposed rankings from the incident ledger; no network or media calls."""
from pathlib import Path
from decimal import Decimal
import json
import sys

HERE = Path(__file__).resolve().parent


def scale_band(n: int) -> int:
    return 5 if n >= 50_000_000 else 4 if n >= 10_000_000 else 3 if n >= 1_000_000 else 2 if n >= 100_000 else 1


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ledger = json.loads((HERE / "incidents-v01.json").read_text(encoding="utf-8"))
    sources = {s["source_id"] for s in json.loads((HERE / "sources-v01.json").read_text(encoding="utf-8"))["sources"]}
    identifiers: set[str] = set()
    rows = []
    for item in ledger["incidents"]:
        assert item["incident_id"] not in identifiers, "duplicate root incident"
        identifiers.add(item["incident_id"])
        assert set(item["source_ids"]) <= sources, "unknown primary source"
        if not item["ranking_eligible"]:
            continue
        assert type(item["n"]) is int and item["n"] > 0
        assert type(item["impact"]) is int and 1 <= item["impact"] <= 5
        assert item["impact_range"][0] <= item["impact"] <= item["impact_range"][1]
        score = item["n"] * item["impact"]
        rows.append({"incident_id": item["incident_id"], "name": item["name"],
                     "n": item["n"], "n_label": item["n_label"], "unit": item["unit"],
                     "certainty": item["certainty"], "impact": item["impact"],
                     "score": score, "score_million": str(Decimal(score) / Decimal(1_000_000)),
                     "alternative_band": scale_band(item["n"]),
                     "alternative_band_score": scale_band(item["n"]) * item["impact"],
                     "source_ids": item["source_ids"]})
    rows.sort(key=lambda item: (-item["score"], -item["impact"], -item["n"]))
    bands = sorted(rows, key=lambda item: (-item["alternative_band_score"], -item["impact"], -item["n"]))
    rank_by_id = {r["incident_id"]: i + 1 for i, r in enumerate(bands)}
    for rank, row in enumerate(rows, 1):
        row["proposed_rank"] = rank
        row["alternative_band_rank"] = rank_by_id[row["incident_id"]]
        original = next(i for i in ledger["incidents"] if i["incident_id"] == row["incident_id"])
        ranks = []
        for impact in range(original["impact_range"][0], original["impact_range"][1] + 1):
            ordered = sorted(rows, key=lambda r: (-(r["n"] * impact if r["incident_id"] == row["incident_id"] else r["score"]), -r["n"]))
            ranks.append(next(i for i, r in enumerate(ordered, 1) if r["incident_id"] == row["incident_id"]))
        row["one_at_a_time_impact_rank_range"] = [min(ranks), max(ranks)]
    document = {"as_of": ledger["as_of"], "status": "proposal_not_accepted", "method": ledger["ranking_method"],
                "unit_warning": "複数の公表単位と可能性範囲を使う編集上の比較。実害・日本の被害者数・統計的な危険度の順位ではない。",
                "selected_top10_ids": [r["incident_id"] for r in rows[:10]],
                "alternative_band_top10_ids": [r["incident_id"] for r in bands[:10]],
                "sensitivity_limit": "Iを1事案ずつ範囲内で変えた紹介順位。全事案同時の順位保証ではない。",
                "ranking": rows}
    (HERE / "ranking-v01.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    table = ["# 国内情報漏えいの暫定比較表", "", "2026-11-07時点・構成未採用。採点は編集判断であり、実害や企業の責任の順位ではない。",
             "", "原資料と内数は[事件台帳](incidents-v01.json)、取得状況は[出典台帳](sources-v01.json)、解釈は[構成案](PROPOSAL_V01_JA.md)へ。", "",
             "| 暫定順 | 事案 | 公表規模N（元の単位） | I | N×I（百万点） | 確度 | I変更時の順の幅 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lo, hi = row["one_at_a_time_impact_rank_range"]
        table.append(f"| {row['proposed_rank']} | {row['name']} | {row['n_label']} | {row['impact']} | {row['score_million']} | {row['certainty']} | {lo}〜{hi} |")
    table += ["", "百万点は点数の表示単位で、人数・金額ではない。件・人数・メール数を足さず、全国の被害人数へ換算しない。個人の対策は順位ではなく漏れた項目と個別通知で決める。",
              "", "## 桁差を抑える別方式との比較", "", "Nを5段階（10万未満／10万以上／100万以上／1,000万以上／5,000万以上）にし、Iを掛ける参考方式も算出した。段階化しても単位差が解消するわけではない。採用していない。", "",
              "| 参考順 | 事案 | 規模段階×I |", "| --- | --- | --- |"]
    for rank, row in enumerate(bands[:10], 1):
        table.append(f"| {rank} | {row['name']} | {row['alternative_band']}×{row['impact']}={row['alternative_band_score']} |")
    table += ["", "同点はI、次にNの順に並べた便宜上の紹介順。方法を変えると対象も順位も変わるため、本動画案を『日本の実害ワースト10』とは呼ばない。", ""]
    (HERE / "RANKING_V01_JA.md").write_text("\n".join(table), encoding="utf-8")
    print(json.dumps({"eligible_incidents": len(rows), "primary_sources": len(sources), "top10": [r["name"] for r in rows[:10]], "adopted": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()

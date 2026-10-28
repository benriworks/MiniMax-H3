#!/usr/bin/env python3
"""Reproducible H3 API/local motion trials; no external Python dependencies."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import h3_api
from tools.studio.comfyui_execution import ComfyUIError, ComfyUIValidationError

DEFAULT_SUITE = ROOT / "benchmarks/h3-motion-v1.json"
CRITERIA = ("action", "identity", "temporal", "detail", "audio")


class ComparisonError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_suite(suite):
    if suite.get("schema_version") != 1 or suite.get("duration_seconds") != 5 or suite.get("ratio") != "9:16":
        raise ComparisonError("v1 comparison requires schema 1, five seconds and 9:16 (pinned local workflow)")
    if suite.get("api_resolution") not in h3_api.RESOLUTIONS:
        raise ComparisonError("invalid API resolution")
    seed = suite.get("local_seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**63 - 10:
        raise ComparisonError("invalid local seed")
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ComparisonError("suite needs cases")
    ids = set()
    for case in cases:
        identifier = case.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,48}", identifier) or identifier in ids:
            raise ComparisonError("case IDs must be unique safe names")
        ids.add(identifier)
        if not isinstance(case.get("title"), str) or not case["title"].strip():
            raise ComparisonError("case title is required")
        if not isinstance(case.get("checks"), list) or not case["checks"] or not all(isinstance(x, str) and x.strip() for x in case["checks"]):
            raise ComparisonError("case checks are required")
        h3_api.build_generation_payload(prompt=case["prompt"], resolution=suite["api_resolution"], duration=5, ratio="9:16")
    return suite


def initialize(destination, suite_path=DEFAULT_SUITE, trials=1, price=None, currency="USD"):
    suite_bytes = suite_path.read_bytes()
    suite = validate_suite(json.loads(suite_bytes.decode("utf-8-sig")))
    if not 1 <= trials <= 10:
        raise ComparisonError("trials must be from 1 through 10")
    if price is not None and (not math.isfinite(price) or price < 0):
        raise ComparisonError("price must be a finite non-negative amount per output second")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ComparisonError("currency must have three uppercase letters")
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "suite.json").write_bytes(suite_bytes)
    save_json(destination / "manifest.json", {
        "schema_version": 1, "id": "H3COMPARE_" + uuid.uuid4().hex[:16],
        "created_at": now(), "suite_sha256": digest(suite_bytes), "trials": trials,
        "cost": {"api_price_per_output_second": price, "currency": currency,
                 "estimate_source": "user_input" if price is not None else "unknown",
                 "estimated_api_total": None if price is None else round(price * 5 * len(suite["cases"]) * trials, 6),
                 "actual_api_cost": None, "local_electricity_cost": None},
        "implementation_sha256": file_hash(Path(__file__)),
        "conditions": {"api": {"model": h3_api.MODEL, "resolution": suite["api_resolution"],
                               "duration_seconds": 5, "ratio": "9:16", "seed": "not exposed by this API client"},
                       "local": {"workflow": "minimax_h3_t2v_official_q4_v1", "resolution": "480x864",
                                 "diffusion": "INT8 convrot", "text_encoder": "Q4_K_M", "steps": 20,
                                 "frames": 124, "fps": 24, "duration_seconds": 124 / 24},
                       "fairness": "Same prompt, requested duration and aspect ratio; resolution, quantization and random noise differ. Native playback plus common-size derivative; no causal claim about one setting."},
        "jobs": {}, "reviews": [], "human_final_review": "pending", "user_adopted": False, "published": False,
    })
    return destination / "manifest.json"


def load_run(directory):
    manifest = read_json(directory / "manifest.json")
    suite_bytes = (directory / "suite.json").read_bytes()
    if digest(suite_bytes) != manifest["suite_sha256"]:
        raise ComparisonError("suite changed after initialization; create a new comparison")
    return manifest, validate_suite(json.loads(suite_bytes.decode("utf-8-sig")))


@contextmanager
def locked(directory):
    lock = directory / ".comparison.lock"
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise ComparisonError("comparison is locked; if the process exited, verify that before removing .comparison.lock") from None
    try:
        with stream:
            stream.write(str(os.getpid()))
            stream.flush()
            yield
    finally:
        lock.unlink(missing_ok=True)


def case_for(suite, case_id):
    for case in suite["cases"]:
        if case["id"] == case_id:
            return case
    raise ComparisonError("unknown case ID")


def job_key(manifest, case_id, trial, provider):
    if not 1 <= trial <= manifest["trials"]:
        raise ComparisonError("trial outside initialized range")
    return f"{case_id}-{trial:02d}-{provider}"


def process(argv, timeout=90):
    completed = subprocess.run([str(x) for x in argv], capture_output=True, timeout=timeout)
    if completed.returncode:
        raise ComparisonError(f"{Path(argv[0]).name} failed: " + completed.stderr.decode("utf-8", errors="replace")[-1200:])
    return completed.stdout


def probe_video(path, ffprobe="ffprobe"):
    probe = json.loads(process([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))
    video = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    if not video:
        raise ComparisonError("output has no video stream")
    duration = float(probe["format"]["duration"])
    if not math.isfinite(duration) or not 0 < duration <= 30:
        raise ComparisonError("output duration must be positive and at most 30 seconds")
    return {"width": video["width"], "height": video["height"], "fps": video.get("avg_frame_rate"),
            "duration_seconds": duration, "codec": video["codec_name"],
            "has_audio": any(s["codec_type"] == "audio" for s in probe["streams"])}


def artifact_record(path, directory, ffprobe="ffprobe"):
    return {"path": path.relative_to(directory).as_posix(), "bytes": path.stat().st_size,
            "sha256": file_hash(path), "media": probe_video(path, ffprobe)}


def checked_artifact(directory, job):
    record = job["artifact"]
    path = (directory / record["path"]).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file() or path.stat().st_size != record["bytes"] or file_hash(path) != record["sha256"]:
        raise ComparisonError("artifact missing or changed; do not reuse this review")
    return path


def new_api_client():
    return h3_api.H3Client(os.environ.get("MINIMAX_API_KEY", ""), os.environ.get("MINIMAX_API_BASE", h3_api.DEFAULT_API_BASE), timeout=30)


def run_api(directory, manifest, suite, case, key, *, confirm, wait_timeout, ffprobe):
    job = manifest["jobs"].get(key)
    if job and job["state"] == "succeeded":
        checked_artifact(directory, job)
        return job
    client = new_api_client()
    if job is None:
        if not confirm:
            raise ComparisonError("new API task is billable; use --confirm-billable")
        payload = h3_api.build_generation_payload(prompt=case["prompt"], resolution=suite["api_resolution"], duration=5, ratio="9:16")
        job = {"state": "submission_unknown", "provider": "api", "started_at": now(),
               "request_sha256": digest(json.dumps(payload, sort_keys=True).encode()),
               "api_base": client.api_base, "task_id": None, "elapsed_seconds": 0.0}
        manifest["jobs"][key] = job
        save_json(directory / "manifest.json", manifest)  # durable BEFORE POST; never auto-retry an ambiguous POST
        submitted = client.submit(payload)
        job.update(task_id=submitted["task_id"], state="submitted")
        save_json(directory / "manifest.json", manifest)
    if job["api_base"] != client.api_base:
        raise ComparisonError("API base changed; restore the endpoint recorded for this task")
    if not job.get("task_id"):
        raise ComparisonError("submission outcome unknown; recover task ID from provider and use attach-task; no resubmission")
    if job["state"] in ("failed", "cancelled"):
        raise ComparisonError("terminal task failed; initialize a new comparison for another paid trial")
    output = directory / "raw" / f"{key}.mp4"
    start = time.monotonic()
    def observe(status, _task):
        print(f"{key}: {status}", flush=True)
        job["provider_status"] = status
        job["state"] = status if status in ("failed", "cancelled") else "submitted"
        save_json(directory / "manifest.json", manifest)
    try:
        response, _ = h3_api.wait_for_task(client, job["task_id"], interval=5, timeout=wait_timeout,
                                           output=output, overwrite=True,
                                           on_status=observe)
        task = h3_api.task_from_response(response)
        # Deliberately never persist raw responses: they contain expiring signed output URLs.
        job.update(state="succeeded", finished_at=now(), artifact=artifact_record(output, directory, ffprobe))
        job["provider_status"] = task["status"]
    except h3_api.H3TaskError:
        # Read terminal status separately on the next invocation; timeouts remain resumable.
        if job["state"] not in ("failed", "cancelled"):
            job["state"] = "submitted"
        raise
    finally:
        job["elapsed_seconds"] += time.monotonic() - start
        save_json(directory / "manifest.json", manifest)
    return job


def local_inputs(payload, ffprobe):
    from tools.studio import comfyui, comfyui_execution as execution
    from tools.studio.security import canonical_json
    source = ROOT / execution.COMFYUI_WORKFLOW_RELATIVE_PATH
    data = source.read_bytes()
    workflow = json.loads(data)
    record = {"path": execution.COMFYUI_WORKFLOW_RELATIVE_PATH, "bytes": len(data),
              "sha256": digest(data).upper(), "graph_sha256": digest(canonical_json(workflow).encode()).upper()}
    models = {role: {"path": spec["relative_path"], "bytes": spec["bytes"], "sha256": spec["sha256"]}
              for role, spec in execution.MODEL_SPECS.items()}
    runtime = comfyui.resolve_comfyui_runtime_identity(ROOT)
    tool = comfyui.resolve_comfyui_tool_identity(ffprobe=shutil.which(ffprobe) or ffprobe)
    cache_key = execution.comfyui_cache_key(payload, workflow=record, models=models,
                                           runtime_identity=runtime, ffprobe_identity=tool)
    return {"workflow": workflow, "workflow_source_path": source, "workflow_source_bytes": len(data),
            "workflow_source_sha256": record["sha256"], "model_files": models,
            "expected_cache_key": cache_key, "ffprobe": tool["path"]}


def run_local(directory, manifest, suite, case, key, trial, *, wait_timeout, ffprobe):
    from tools.studio import comfyui, comfyui_execution as execution
    job = manifest["jobs"].get(key)
    if job and job["state"] == "succeeded":
        checked_artifact(directory, job)
        return job
    seed = suite["local_seed"] + trial - 1
    payload = {"workflow_preset": execution.COMFYUI_WORKFLOW_PRESET, "prompt": case["prompt"], "seed": seed}
    inputs = local_inputs(payload, ffprobe)
    if job and inputs["expected_cache_key"] != job["cache_key"]:
        raise ComparisonError("local inputs changed; create a new comparison")
    if job is None:
        job = {"state": "prepared", "provider": "local", "seed": seed, "task_id": str(uuid.uuid4()),
               "started_at": now(), "cache_key": inputs["expected_cache_key"], "elapsed_seconds": 0.0}
        manifest["jobs"][key] = job
        save_json(directory / "manifest.json", manifest)
    start = time.monotonic()
    try:
        recovered = comfyui.recover_comfyui_prompt_id(
            ROOT, production_id=manifest["id"], run_id=key,
            cache_key=inputs["expected_cache_key"], payload_digest=execution.comfyui_payload_digest(payload))
        if recovered and recovered != job["task_id"]:
            raise ComparisonError("local task ID does not match its durable submission marker")
        task_argument = {"resume_prompt_id": recovered} if recovered else {"prepared_prompt_id": job["task_id"]}
        # The existing adapter owns durable submission markers, model/runtime attestation,
        # path validation, decoding checks and cache reuse. Keep those protections intact.
        result = comfyui.generate_comfyui_video(
            ROOT, production_id=manifest["id"], run_id=key, payload=payload,
            output_roots=["outputs"], generation_timeout_seconds=wait_timeout, **task_argument, **inputs)
        source = ROOT / next(a["path"] for a in result["artifacts"] if a["kind"] == "video")
        target = directory / "raw" / f"{key}.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        job.update(state="succeeded", finished_at=now(), artifact=artifact_record(target, directory, ffprobe),
                   source_manifest=str((ROOT / result["output_directory"] / "manifest.json").relative_to(ROOT)),
                   cache_hit=result["cache_hit"])
    finally:
        job["elapsed_seconds"] += time.monotonic() - start
        save_json(directory / "manifest.json", manifest)
    return job


def motion_diagnostic(path, ffmpeg="ffmpeg"):
    # Small grayscale samples, mean absolute frame difference in [0,1]. This
    # reflects camera movement, flicker and noise too, and is NOT a quality score.
    raw = process([ffmpeg, "-v", "error", "-i", path, "-t", "15", "-vf", "fps=6,scale=64:64,format=gray", "-an", "-f", "rawvideo", "-threads", "1", "pipe:1"])
    frames = [raw[i:i+4096] for i in range(0, len(raw), 4096) if len(raw[i:i+4096]) == 4096]
    diffs = [sum(abs(a-b) for a, b in zip(prev, cur)) / (4096*255) for prev, cur in zip(frames, frames[1:])]
    return {"sample_fps": 6, "sampled_frames": len(frames), "mean_luma_difference": sum(diffs)/len(diffs) if diffs else None,
            "near_static_pair_fraction": sum(d < 0.002 for d in diffs)/len(diffs) if diffs else None,
            "interpretation": "Diagnostic only: camera motion, noise and flicker also increase differences. Not a quality ranking."}


def compare_pair(directory, manifest, suite, case_id, trial, ffmpeg="ffmpeg"):
    case = case_for(suite, case_id)
    keys = {p: job_key(manifest, case_id, trial, p) for p in ("api", "local")}
    jobs = {p: manifest["jobs"].get(k) for p, k in keys.items()}
    if any(not j or j["state"] != "succeeded" for j in jobs.values()):
        raise ComparisonError("both API and local videos must succeed before comparison")
    paths = {p: checked_artifact(directory, j) for p, j in jobs.items()}
    root = directory / "review" / f"{case_id}-{trial:02d}"
    root.mkdir(parents=True, exist_ok=True)
    identity = digest(json.dumps({p: j["artifact"]["sha256"] for p, j in jobs.items()}, sort_keys=True).encode())[:16]
    output = root / f"side-by-side-{identity}.mp4"
    filters = ";".join(f"[{i}:v]setpts=PTS-STARTPTS,scale=480:864:force_original_aspect_ratio=decrease,pad=480:864:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24[{p}]" for i,p in enumerate(("a", "b")))
    filters += ";[a][b]hstack=inputs=2:shortest=1[v]"
    if not output.exists():
        temporary = output.with_suffix(".partial.mp4")
        try:
            process([ffmpeg, "-v", "error", "-n", "-i", paths["api"], "-i", paths["local"],
                     "-filter_complex", filters, "-map", "[v]", "-an", "-t", "5", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", temporary], timeout=180)
            process([ffmpeg, "-v", "error", "-i", temporary, "-f", "null", "-"], timeout=90)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    else:
        previous = root / "report.json"
        if previous.is_file():
            old = read_json(previous).get("side_by_side", {})
            if old.get("path") == output.relative_to(directory).as_posix() and old.get("sha256") != file_hash(output):
                raise ComparisonError("comparison derivative changed; preserve it and create a new comparison")
        process([ffmpeg, "-v", "error", "-i", output, "-f", "null", "-"], timeout=90)
    report = {"created_at": now(), "case": case_id, "trial": trial,
              "source_sha256": {p:j["artifact"]["sha256"] for p,j in jobs.items()},
              "side_by_side": {"path": output.relative_to(directory).as_posix(), "sha256": file_hash(output),
                               "left": "api", "right": "local", "audio": "muted", "window_seconds": 5},
              "diagnostics": {p:motion_diagnostic(path, ffmpeg) for p,path in paths.items()},
              "cost": manifest["cost"],
              "active_wait_seconds": {p: j.get("elapsed_seconds") for p,j in jobs.items()},
              "media": {p: j["artifact"]["media"] for p,j in jobs.items()},
              "reviews": [r for r in manifest["reviews"] if r["case"] == case_id and r["trial"] == trial
                          and r["source_sha256"] == {p:j["artifact"]["sha256"] for p,j in jobs.items()}],
              "quality_winner": "unmeasured"}
    report["condition_warnings"] = []
    for provider, job in jobs.items():
        media = job["artifact"]["media"]
        if abs(media["duration_seconds"] - 5) > 0.3:
            report["condition_warnings"].append(f"{provider}: output duration differs from five seconds by more than 0.3 seconds")
        if abs(media["width"] / media["height"] - 9/16) > 0.02:
            report["condition_warnings"].append(f"{provider}: output aspect ratio differs from 9:16")
    if manifest.get("software_smoke_only"):
        report["software_smoke_only"] = True
    save_json(root / "report.json", report)
    escape = lambda value: html.escape(str(value), quote=True)
    cards = []
    for p,path in paths.items():
        relative = os.path.relpath(path, root).replace("\\", "/")
        media = jobs[p]["artifact"]["media"]
        caption = f'{media["width"]} × {media["height"]} / {media["duration_seconds"]:.3f}秒 / {media["fps"]} fps / 音声' + ("あり" if media["has_audio"] else "なし")
        cards.append(f'<section><h2>{p.upper()} 原本</h2><video aria-label="{p.upper()} 原本動画" controls preload="metadata" src="{escape(relative)}"></video><p>{escape(caption)}</p></section>')
    page = f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><link rel="icon" href="data:,"><title>H3比較 {escape(case["title"])}</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:auto;padding:20px;background:#111827;color:#f9fafb}}.pair{{display:flex;gap:20px;flex-wrap:wrap}}section{{flex:1;min-width:260px}}video{{width:100%;max-height:65vh;background:black}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}button{{padding:12px}}a{{color:#93c5fd}}</style>
<h1>{escape(case["title"])} / 試行 {trial}</h1>{'<p><strong>ソフトウェア検証用の人工テスト映像です。MiniMaxの生成結果ではありません。品質比較には使用できません。</strong></p>' if manifest.get('software_smoke_only') else ''}<p>同じプロンプト・5秒・9:16。元解像度、量子化、乱数は異なります。単一出力から一般的な品質優位は判定できません。</p>
{"".join('<p>出力条件の確認: '+escape(w)+'</p>' for w in report["condition_warnings"])}
<h2>左 API / 右 LOCAL・共通表示サイズ・先頭5秒・音声なし</h2><video aria-label="APIとLOCALの横並び比較動画" controls src="{escape(output.name)}"></video>
<h2>原本と音声を個別に確認</h2><div class="pair">{"".join(cards)}</div>
<h2>確認すること</h2><ul>{"".join("<li>"+escape(c)+"</li>" for c in case["checks"])}</ul>
<p>評価: action=動作達成 / identity=形・個数の維持 / temporal=時間的一貫性 / detail=細部 / audio=同期と自然さ。各1〜5、未評価はnull。音声は原本で個別に再生してください。</p>
<p>動き量はカメラ移動・ちらつき・ノイズでも増える補助値です。品質点には変換しません。</p>
<p>評価記録 {len(report["reviews"])}件 / 総合的な優劣は未判定 / 実請求額は未取得</p>
<details><summary>計測値と評価履歴</summary><pre>{escape(json.dumps(report,ensure_ascii=False,indent=2))}</pre></details><details><summary>共通プロンプトと実行条件</summary><pre>{escape(case["prompt"])}</pre><pre>{escape(json.dumps(manifest["conditions"],ensure_ascii=False,indent=2))}</pre></details></html>'''
    (root / "index.html").write_text(page, encoding="utf-8")
    return root / "index.html"


def record_review(directory, manifest, case_id, trial, provider, scores, reviewer, note):
    if provider not in ("api", "local"):
        raise ComparisonError("provider must be api or local")
    if not reviewer.strip() or not note.strip():
        raise ComparisonError("reviewer and observation note are required")
    if not scores or any(k not in CRITERIA or isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 5 for k,v in scores.items()):
        raise ComparisonError("scores must use named criteria and integers 1 through 5")
    sources = {}
    for p in ("api", "local"):
        key = job_key(manifest, case_id, trial, p)
        job = manifest["jobs"].get(key)
        if not job or job["state"] != "succeeded":
            raise ComparisonError("review requires both completed videos")
        checked_artifact(directory, job)
        sources[p] = job["artifact"]["sha256"]
    manifest["reviews"].append({"case": case_id, "trial": trial, "provider": provider, "reviewer": reviewer,
                                 "created_at": now(), "scores": {k:scores.get(k) for k in CRITERIA},
                                 "note": note, "source_sha256": sources})
    save_json(directory / "manifest.json", manifest)


def parser():
    cli = argparse.ArgumentParser(description="MiniMax H3 API/local motion comparison")
    sub = cli.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="freeze a suite, without network access or generation")
    init.add_argument("directory", type=Path)
    init.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    init.add_argument("--trials", type=int, default=1)
    init.add_argument("--api-price-per-second", type=float)
    init.add_argument("--currency", default="USD")
    doctor = sub.add_parser("doctor", help="read-only configuration and runtime checks")
    for name in ("run", "compare", "score", "status", "attach-task"):
        command = sub.add_parser(name)
        command.add_argument("directory", type=Path)
        if name != "status":
            command.add_argument("--case", required=True)
            command.add_argument("--trial", type=int, default=1)
        if name in ("run", "score"):
            command.add_argument("--provider", choices=("api", "local"), required=True)
        if name == "run":
            command.add_argument("--confirm-billable", action="store_true")
            command.add_argument("--wait-timeout", type=float, default=1800)
            command.add_argument("--ffprobe", default="ffprobe")
        if name == "compare":
            command.add_argument("--ffmpeg", default="ffmpeg")
        if name == "score":
            command.add_argument("--reviewer", required=True)
            command.add_argument("--note", required=True)
            for criterion in CRITERIA:
                command.add_argument("--" + criterion, type=int, choices=range(1,6))
        if name == "attach-task":
            command.add_argument("--task-id", required=True)
    return cli


def doctor():
    import socket
    configured = bool(os.environ.get("MINIMAX_API_KEY", "").strip())
    try:
        with socket.create_connection(("127.0.0.1", 8188), timeout=1):
            listening = True
    except OSError:
        listening = False
    from tools.studio.comfyui_execution import MODEL_SPECS
    models = {role: (ROOT/spec["relative_path"]).is_file() and (ROOT/spec["relative_path"]).stat().st_size == spec["bytes"] for role,spec in MODEL_SPECS.items()}
    result = {"api_key": "configured" if configured else "missing", "comfyui_port_listening": listening,
              "models_present_with_expected_size": models, "model_hashes_checked": False,
              "ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe"),
              "generation_performed": False, "provider_authentication_verified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if configured and listening and all(models.values()) and result["ffmpeg"] and result["ffprobe"] else 2


def main(argv=None):
    try:
        h3_api.load_env_file(ROOT / ".env")
        args = parser().parse_args(argv)
        if args.command == "doctor":
            return doctor()
        directory = args.directory.expanduser().resolve()
        if args.command == "init":
            print(initialize(directory, args.suite, args.trials, args.api_price_per_second, args.currency))
            return 0
        with locked(directory):
            manifest, suite = load_run(directory)
            if args.command == "status":
                print(json.dumps(manifest, ensure_ascii=False, indent=2))
                return 0
            case = case_for(suite, args.case)
            key = job_key(manifest, args.case, args.trial, getattr(args, "provider", "api"))
            if args.command == "run":
                if not math.isfinite(args.wait_timeout) or not 0 < args.wait_timeout <= 43200:
                    raise ComparisonError("wait timeout must be finite, positive and at most 43200 seconds")
                if args.provider == "api":
                    # Detect an unusable inspection tool before a new paid request.
                    process([shutil.which(args.ffprobe) or args.ffprobe, "-version"], timeout=15)
                    result = run_api(directory, manifest, suite, case, key, confirm=args.confirm_billable, wait_timeout=args.wait_timeout, ffprobe=args.ffprobe)
                else:
                    result = run_local(directory, manifest, suite, case, key, args.trial, wait_timeout=args.wait_timeout, ffprobe=args.ffprobe)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif args.command == "compare":
                print(compare_pair(directory, manifest, suite, args.case, args.trial, args.ffmpeg))
            elif args.command == "score":
                scores = {k:getattr(args,k) for k in CRITERIA if getattr(args,k) is not None}
                record_review(directory, manifest, args.case, args.trial, args.provider, scores, args.reviewer, args.note)
            elif args.command == "attach-task":
                job = manifest["jobs"].get(key)
                if not job or job["state"] != "submission_unknown" or job.get("task_id"):
                    raise ComparisonError("attach-task only repairs an ambiguous API submission with no task ID")
                client = new_api_client()
                if job["api_base"] != client.api_base:
                    raise ComparisonError("API base changed")
                task = h3_api.task_from_response(client.status(args.task_id))
                job.update(task_id=args.task_id, state="submitted", reconciliation={"at": now(), "method": "user_supplied_task_id", "observed_status": task["status"]})
                save_json(directory / "manifest.json", manifest)
        return 0
    except (ComparisonError, h3_api.H3Error, ComfyUIError, ComfyUIValidationError, OSError, ValueError, KeyError, StopIteration, subprocess.TimeoutExpired) as exc:
        message = h3_api._redact(str(exc), (os.environ.get("MINIMAX_API_KEY", ""),))
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

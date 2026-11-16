"""Run the restricted product demo and check the actual tools and proposal."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "outputs/content-projects" / HERE.parent.name / "_private/proposal-agent-v02"
INPUTS = ("proposal-template.md", "discovery-notes.md", "offer-rules.md")
DRAFT = "proposal-draft.md"


def check_trace(events, working):
    calls, results = {}, {}
    final = None
    for event in events:
        if event.get("type") == "result":
            final = event
        message = event.get("message")
        if not isinstance(message, dict):
            continue
        for item in message.get("content", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                target = (working / item["input"]["file_path"]).resolve()
                if target.parent != working:
                    raise ValueError("A tool addressed a file outside the demo folder")
                calls[item["id"]] = (item["name"], target.name)
            if item.get("type") == "tool_result":
                results[item["tool_use_id"]] = not item.get("is_error", False)
    if final is None or final.get("is_error"):
        raise ValueError("Agent did not finish a successful run")
    expected = {("Read", name) for name in INPUTS} | {("Write", DRAFT)}
    if not set(calls.values()) <= expected:
        raise ValueError("Unexpected input or output path")
    if {value for key, value in calls.items() if results.get(key)} != expected:
        raise ValueError("All three input reads and a successful write are required")
    return list(calls.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=int, default=1)
    parser.add_argument("--verify-only", action="store_true",
                        help="Show the local receipt without making another model request")
    args = parser.parse_args()
    out = OUT / f"attempt-{args.attempt:02}"
    if args.verify_only:
        print((out / "verification.json").read_text(encoding="utf-8"))
        return
    allowed = [f"Read(./{name})" for name in INPUTS]
    allowed.append(f"Edit(./{DRAFT})")
    settings = {"permissions": {"blockReadsOutsideWorkingDirectories": True,
                                 "blockWritesOutsideWorkingDirectories": True}}
    out.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory(prefix="fictional-proposal-") as folder:
        working = Path(folder).resolve()
        for name in INPUTS:
            shutil.copyfile(HERE / name, working / name)
        command = ["claude", "-p", "--model", "haiku", "--tools", "Read,Write",
                   "--allowedTools", *allowed, "--permission-mode", "dontAsk",
                   "--strict-mcp-config", "--setting-sources", "", "--no-session-persistence",
                   "--settings", json.dumps(settings), "--max-budget-usd", "0.10",
                   "--output-format", "stream-json", "--verbose"]
        env = dict(os.environ, CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        run = subprocess.run(command, cwd=working, env=env, input=(HERE / "agent-request.txt").read_bytes(),
                             capture_output=True, timeout=150)
        (out / "stream.jsonl").write_bytes(run.stdout)
        if run.returncode:
            (out / "stderr.txt").write_bytes(run.stderr)
            raise RuntimeError("See the locally saved agent logs")
        events = [json.loads(line) for line in run.stdout.decode("utf-8-sig").splitlines() if line.strip()]
        if (working / DRAFT).is_file():
            shutil.copyfile(working / DRAFT, out / DRAFT)
        calls = check_trace(events, working)
        body = (out / DRAFT).read_bytes()
    report = {"inputs": list(INPUTS), "tool_calls": calls, "output": DRAFT,
              "models": sorted({event["message"]["model"] for event in events
                                if event.get("type") == "assistant" and isinstance(event.get("message"), dict)
                                and event["message"].get("model")}),
              "cli": subprocess.run(["claude", "--version"], capture_output=True, check=True, text=True).stdout.strip()}
    (out / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(body.decode("utf-8"))


if __name__ == "__main__":
    main()

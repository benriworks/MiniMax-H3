"""Run one H3 shot and resume polling a known task without submitting again."""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.h3_api import H3Client, DEFAULT_API_BASE, build_generation_payload, wait_for_task, task_from_response


def write_record(path, record):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pending.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--prompt", type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--last-image", type=Path, help="optional FL2VA ending frame")
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args()

    ledger = args.directory / "generation.json"
    movie = args.directory / "source.mp4"
    client = H3Client(os.environ.get("MINIMAX_API_KEY", ""), DEFAULT_API_BASE, timeout=30)
    started = time.monotonic()
    if ledger.exists():
        record = json.loads(ledger.read_text(encoding="utf-8"))
        if movie.exists() and record["state"] == "saved":
            print("Saved output already exists.", flush=True)
            return
        if not record.get("task_id"):
            parser.error("Submission outcome unknown. Reconcile the task ID before retrying.")
    else:
        if not (args.confirm_billable and args.prompt and args.image and args.seconds):
            parser.error("Initial submission requires --prompt, --image, --seconds and --confirm-billable.")
        images = [("first_frame", str(args.image))]
        if args.last_image:
            images.append(("last_frame", str(args.last_image)))
        payload = build_generation_payload(
            prompt=args.prompt.read_text(encoding="utf-8-sig"), resolution="768P",
            duration=args.seconds, ratio="adaptive", images=images,
        )
        args.directory.mkdir(parents=True, exist_ok=False)
        record = {
            "state": "submission_unknown",
            "submitted_utc": datetime.now(timezone.utc).isoformat(),
            "model": payload["model"],
            "seconds": args.seconds,
            "resolution": payload["resolution"],
            "prompt": args.prompt.name,
            "input_image": args.image.name,
            "input_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        }
        if args.last_image:
            record.update(last_image=args.last_image.name,
                          last_image_sha256=hashlib.sha256(args.last_image.read_bytes()).hexdigest())
        write_record(ledger, record)
        receipt = client.submit(payload)
        record.update(state="accepted", task_id=receipt["task_id"])
        write_record(ledger, record)
        print(f"{args.directory.name}: accepted task {record['task_id']}", flush=True)

    previous = None

    def progress(status, task):
        nonlocal previous
        if status != previous:
            previous = status
            print(f"{args.directory.name}: {status}", flush=True)

    response, _ = wait_for_task(client, record["task_id"], interval=5, timeout=1200, on_status=progress)
    task = task_from_response(response)
    record.update(state="succeeded", provider_seconds=task["updated_at"] - task["created_at"],
                  usage=task.get("usage"), ratio=task.get("ratio"))
    write_record(ledger, record)
    if not movie.exists():
        client.download(task["content"]["url"], movie)
    record.update(state="saved", bytes=movie.stat().st_size,
                  observation_seconds=round(time.monotonic() - started, 3),
                  output_sha256=hashlib.sha256(movie.read_bytes()).hexdigest())
    write_record(ledger, record)
    print(f"{args.directory.name}: saved {record['bytes']} bytes in {record['observation_seconds']}s", flush=True)


if __name__ == "__main__":
    main()

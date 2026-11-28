"""Film the additional wide two-shot; use the local receipt when resuming."""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from tools.h3_api import H3Client, DEFAULT_API_BASE, build_generation_payload, wait_for_task, task_from_response
from prepare_visuals import sha

def main(media, setup):
    setups={"talk":("pair-conversation","winter-duet",6), "study":("pair-study","winter-study",8)}
    prompt_name, folder, seconds = setups[setup]
    image=media/"cast/winter-pair-motion-ref.jpg"
    prompt=HERE/"motion"/(prompt_name+".txt")
    out=media/"motion"/folder
    ledger=out/"generation.json"
    dest=out/"source.mp4"
    def save():
        tmp=ledger.with_suffix(".tmp")
        tmp.write_text(json.dumps(record,indent=2), encoding="utf-8")
        tmp.replace(ledger)
    client=H3Client(os.environ["MINIMAX_API_KEY"],DEFAULT_API_BASE,timeout=165)
    if ledger.exists():
        record=json.loads(ledger.read_text(encoding="utf-8"))
        if dest.exists() and record.get("sha256")==sha(dest): return
        if not record.get("task_id"): raise RuntimeError("Missing provider receipt; do not resubmit")
    else:
        payload=build_generation_payload(prompt=prompt.read_text(encoding="utf-8"),resolution="768P",duration=seconds,ratio="adaptive",images=[("first_frame",str(image))])
        out.mkdir(parents=True)
        record=dict(state="submission_unknown",model=payload["model"],seconds=seconds,submitted=datetime.now(timezone.utc).isoformat(),input_sha256=sha(image))
        save()
        receipt=client.submit(payload)
        record.update(state="accepted",task_id=receipt["task_id"])
        save()
        print("Wide two-shot accepted",flush=True)
    response,_=wait_for_task(client,record["task_id"],interval=6,timeout=1200)
    task=task_from_response(response)
    record.update(state="succeeded",usage=task.get("usage"))
    save()
    client.download(task["content"]["url"],dest)
    record.update(state="saved",sha256=sha(dest),bytes=dest.stat().st_size)
    save()
    print("Two-shot saved",dest.stat().st_size,flush=True)
if __name__=="__main__":
    main(Path(sys.argv[1]),sys.argv[2] if len(sys.argv)>2 else "talk")

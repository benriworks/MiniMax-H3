"""Run one first/last-frame H3 shot on the local ComfyUI (Q3 GGUF + Turbo LoRA) and save it next to a ledger."""
import argparse, hashlib, json, shutil, sys, time, urllib.request, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument("directory", type=Path)
p.add_argument("--prompt", type=Path, required=True)
p.add_argument("--image", type=Path, required=True)
p.add_argument("--last-image", type=Path, help="optional ending frame; omit for first-frame-only")
p.add_argument("--width", type=int, default=480)
p.add_argument("--height", type=int, default=864)
p.add_argument("--steps", type=int, default=8)
p.add_argument("--seed", type=int, default=20261112)
p.add_argument("--server", default="http://127.0.0.1:8188")
a = p.parse_args()
a.directory.mkdir(parents=True, exist_ok=False)

# The API prompt format names reference pictures; keep only the three content blocks for the local model.
text = a.prompt.read_text(encoding="utf-8-sig")
text = text[text.index("integrated_multimodal_description:"):]

tag = uuid.uuid4().hex[:8]
names = []
for src in filter(None, (a.image, a.last_image)):
    name = f"parkour_{tag}_{src.name}"
    shutil.copyfile(src, ROOT / "runtime" / "ComfyUI" / "input" / name)
    names.append(name)

prefix = f"video/parkour_compare_{tag}"
g = {
    "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf"}},
    "2": {"class_type": "MiniMaxH3TurboLoRA", "inputs": {"model": ["1", 0], "lora_name": "minimax_h3_turbo_v4_step600_ema.safetensors", "strength": 1.0, "low_vram": True}},
    "3": {"class_type": "CLIPLoaderGGUF", "inputs": {"clip_name": "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf", "type": "minimax"}},
    "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
    "5": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    "6": {"class_type": "LoadImage", "inputs": {"image": names[0]}},
    "7": {"class_type": "LoadImage", "inputs": {"image": names[-1]}},
    "8": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"clip": ["3", 0], "vae": ["4", 0], "prompt": text, "width": a.width, "height": a.height, "length": 124, "first_frame": ["6", 0], "last_frame": ["7", 0]}},
    "9": {"class_type": "BasicScheduler", "inputs": {"model": ["2", 0], "scheduler": "simple", "steps": a.steps, "denoise": 1.0}},
    "10": {"class_type": "MiniMaxH3TurboSampler", "inputs": {}},
    "11": {"class_type": "RandomNoise", "inputs": {"noise_seed": a.seed}},
    "12": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["8", 0]}},
    "13": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["11", 0], "guider": ["12", 0], "sampler": ["10", 0], "sigmas": ["9", 0], "latent_image": ["8", 1]}},
    "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["4", 0]}},
    "15": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["13", 0], "vae": ["5", 0]}},
    "16": {"class_type": "CreateVideo", "inputs": {"fps": 24.0, "bit_depth": 8, "images": ["14", 0], "audio": ["15", 0]}},
    "17": {"class_type": "SaveVideo", "inputs": {"filename_prefix": prefix, "format": "mp4", "codec": "h264", "codec.encoding": "re-encode", "codec.encoding.crf": 18.0, "video": ["16", 0]}},
}

if not a.last_image:
    del g["7"], g["8"]["inputs"]["last_frame"]


def call(path, body=None):
    req = urllib.request.Request(a.server + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


started = time.monotonic()
pid = call("/prompt", {"prompt": g, "client_id": tag})["prompt_id"]
record = {"state": "accepted", "prompt_id": pid, "seed": a.seed, "steps": a.steps, "width": a.width, "height": a.height,
          "model": "MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf + turbo v4 LoRA (merge)", "prompt": a.prompt.name,
          "first": a.image.name, "last": a.last_image.name if a.last_image else None}
ledger = a.directory / "generation.json"
ledger.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print("accepted", pid, flush=True)
while True:
    time.sleep(10)
    h = call(f"/history/{pid}").get(pid)
    if not h:
        continue
    status = h.get("status", {})
    if status.get("status_str") == "error":
        record.update(state="error", messages=status.get("messages"))
        ledger.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
        sys.exit(f"ComfyUI error: {json.dumps(status.get('messages'), default=str)[-1500:]}")
    if status.get("completed"):
        break
found = sorted((ROOT / "outputs" / "video").glob(f"parkour_compare_{tag}*.mp4"))
if not found:
    sys.exit(f"completed but no file for {prefix}; outputs: {json.dumps(h.get('outputs'))[:800]}")
movie = a.directory / "source.mp4"
shutil.copyfile(found[-1], movie)
record.update(state="saved", seconds=round(time.monotonic() - started, 1), bytes=movie.stat().st_size,
              output_sha256=hashlib.sha256(movie.read_bytes()).hexdigest())
ledger.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(f"saved {movie} in {record['seconds']}s", flush=True)

# MiniMax H3 low-VRAM workflow provenance

`minimax_h3_t2v_lowvram.json` is derived from Comfy-Org's official
[`video_minimax_h3_t2v.json`](https://github.com/Comfy-Org/workflow_templates/blob/5c75d9f137bb27706a70dd337dac6249b2e51ded/templates/video_minimax_h3_t2v.json)
at commit `5c75d9f137bb27706a70dd337dac6249b2e51ded` (2026-08-03).
The upstream workflow repository is MIT-licensed.

Local changes are intentionally limited to:

- `UNETLoader` → `UnetLoaderGGUF`, using `MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf`.
- `CLIPLoader` → `CLIPLoaderGGUF`, using `qwen3vl-32B-MiniMax-H3-Q2_K.gguf`.
- Resolution preset reduced from 0.4 MP to 0.2 MP (`608 x 352`, 16:9).
- Duration reduced from 5 seconds to 4 seconds.
- Sampling remains at the official template's 20 steps.
- Model-link notes updated for the low-VRAM files while retaining the official VAEs.
- All model metadata URLs are pinned to the revisions in `model-manifest.json`.

The GGUF quantizations are community artifacts. Review and accept all upstream
model licenses before using `download-models.ps1 -AcceptLicense`.

## Optional Turbo workflow provenance

`minimax_h3_t2v_lowvram_turbo.json` starts from the low-VRAM workflow above and
adds the two nodes documented by Larryvrh:

- [`ComfyUI-MiniMax-H3-Turbo`](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/tree/55fee864dd7b2976b1c4ce3c3d5f7968f181409f)
  at commit `55fee864dd7b2976b1c4ce3c3d5f7968f181409f`.
- [`MiniMax-H3-Turbo-Lora`](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/tree/43a74557ac3f6539db8e0f2a959d03feb7a81480)
  at revision `43a74557ac3f6539db8e0f2a959d03feb7a81480`.

The derived workflow uses the recommended v4 step600 EMA adapter at strength
`1.0`, `simple` scheduler, six steps, and a five-second duration. It explicitly
enables the node's `low_vram` merge path to limit peak memory; this can be softer
than bypass on a quantized base. Resolution remains 0.2 MP (`608 x 352`).

Larryvrh documents bf16/int8_convrot and pruned int8/fp8 bases, but does not
explicitly list the community Q3 GGUF base used here. This combination is
experimental and must not be described as supported solely from static workflow
validation. Keep the non-Turbo `lowvram` profile as the fallback.

An implementation smoke completed on this machine with the same merge path at
0.1 MP, four requested seconds, and four sampling steps. It confirms that the Q3
pipeline can apply the adapter and emit H.264 + AAC, but it is not a quality test
of this tracked workflow's 0.2 MP / five-second / six-step defaults. On GGUF,
`weight_patched=False` from the custom node's generic canary is a false negative:
ComfyUI-GGUF stores accepted patches on `GGMLTensor.weight.patches` instead of the
module `weight_function` inspected by that canary. The smoke therefore combined
the accepted-patch/AdaLN log, completion, and a same-seed no-LoRA A/B difference.

## Quality-priority Q4 Turbo workflow provenance

`minimax_h3_t2v_lowvram_q4_turbo.json` is derived from the tracked Q2 Turbo
workflow. It preserves the Q3 diffusion model, VAEs, Turbo adapter, and merge
wiring, but replaces only the text encoder with
[`qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf`](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/blob/daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7/qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf)
from revision `daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7`. Hugging Face LFS metadata
reports exactly `14,576,977,888` bytes and SHA-256
`1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e`.

The quality-priority defaults are 0.4 MP (`864 x 480` at 16:9), five seconds,
`simple` / eight steps, strength `1.0`, and `low_vram=true`. These match the
latest successful local Q2 Turbo job (`MiniMax_H3_00010_.mp4`) except for the
Q4 encoder substitution. The Q4 path also completed with the same prompt, seed,
and settings in 286.087 seconds, emitting H.264 864 x 480 video plus AAC stereo.
Against the 313.682-second Q2 source job, video PSNR averaged 26.291812 dB and
SSIM was 0.814451. This proves different completed outputs, not general Q4
quality or speed superiority. Evidence is tracked in
[`verification/q4-text-encoder-ab-2026-08-12.json`](../verification/q4-text-encoder-ab-2026-08-12.json).
Try 0.6 MP manually only after the verified 0.4 MP baseline. The original Q2
Turbo workflow remains the lower-memory comparison and fallback; on a fresh
installation its profile must be downloaded separately.

## Official INT8 + Q4 workflows

`minimax_h3_t2v_official_q4.json` starts from the pinned official H3 T2V
template above. It retains the Comfy-Org
`minimax_h3_fl2va_pruned_int8_convrot.safetensors` diffusion model and the two
official VAEs, but replaces the stock NVFP4 text encoder with the tracked
`qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` loader. It deliberately keeps the stock
`res_multistep` sampler and `simple` / 20-step schedule at 0.4 MP and five
seconds, so it is the quality comparison baseline rather than a speed preset.

`minimax_h3_t2v_official_q4_turbo.json` uses the same official INT8 + Q4
model pairing and inserts the pinned Larryvrh v4 step600 EMA LoRA and Turbo
Sampler. Its `simple` / 8-step, strength `1.0`, and `low_vram=true` merge
settings match the existing Q4 Turbo workflow. This is the faster comparison
path, not a verified quality upgrade. An Emergency `--novram --cpu-vae` smoke
of `official_q4` completed at 416x256, five frames, one step, and no audio; it
verified the INT8 + Q4 loader/sampling/video-decode path and H.264 output. The
ignored output hash and resource observations are recorded in
[`verification/int8-smoke-2026-08-13.json`](../verification/int8-smoke-2026-08-13.json).

Under the same Emergency mode, a non-Turbo quality run completed at 1056x608
(0.6 MP), five seconds, `res_multistep` / `simple` / 20 steps. The resulting
H.264 High / yuv420p video plus AAC LC 32 kHz stereo MP4 fully decoded. In this
single same-prompt, same-seed comparison, INT8 had lower visible noise and more
stable window-grid structure, while Q3 retained more apparent fine texture. It
is an observation, not a general quality, prompt-following, speed, or temporal
stability ranking. The tracked 0.4 MP default and `official_q4_turbo` remain
unverified on target hardware. Evidence is in
[`verification/int8-quality-2026-08-14.json`](../verification/int8-quality-2026-08-14.json).

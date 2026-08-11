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

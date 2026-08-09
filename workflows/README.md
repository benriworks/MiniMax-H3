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

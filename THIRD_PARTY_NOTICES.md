# Third-party model and runtime notices

この文書は、ローカル補助環境が取得・利用する第三者成果物について、見落としやすい点を日本語で案内するものです。**法律助言ではありません。** ライセンス本文、モデルカード、利用地域、組織の法務判断を優先してください。

## MiniMax H3 Community License

レビュー基準はMiniMaxAI/MiniMax-H3 revision `bfc8ed0353f5a9733be73e6b2c98ec0948195b86` の
[公式LICENSE](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/bfc8ed0353f5a9733be73e6b2c98ec0948195b86/LICENSE)です。

重要条件の非網羅的な要約:

- ライセンスで定義された **Excluded Territories** に関する地域制限があります。対象地域の定義と適用範囲をLICENSE本文で確認してください。
- 年間売上が **US$20 millionを超える主体の商用利用** には、MiniMaxからの書面による別途許諾が必要とされています。組織単位や関連主体の扱いを含め、本文を確認してください。
- 商用製品・サービスのユーザーインターフェースでは、LICENSEが定める形で **MiniMax H3** の表示が求められます。
- 生成物の適法性、第三者権利、用途、配布についての責任は利用者側にあります。モデル出力であることだけを理由に利用可能になるわけではありません。
- safety、禁止用途、再配布、派生物、attributionなど、ここに列挙していない条件があります。

## profile別モデル

### official

`official` profileは[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)のint8/nvfp4とVAEを使用します。各ファイルの取得revision、byte数、SHA-256、source URLは[model-manifest.json](model-manifest.json)に固定しています。上流MiniMax H3 Community LicenseとComfy-Orgのモデルカードを両方確認してください。

### official_q4 / official_q4_turbo

`official_q4` はComfy-Orgの公式INT8 ConvRotとVAEに、`lowvram_q4_turbo` と同じ
`qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf` を組み合わせます。`official_q4_turbo` はさらに
Apache-2.0のTurbo LoRAを加えます。Q4 repositoryのlicense metadataがunknownである点は
公式INT8 diffusion modelを使っても変わりません。上流MiniMax H3 Community License、
Comfy-Orgのモデルカード、Q4 repositoryの条件、Turbo adapterの条件をすべて確認してください。

### lowvram

`lowvram` profileは次のコミュニティ量子化を含みます。

- [Abiray/MiniMax-H3-Pruned-GGUF](https://huggingface.co/Abiray/MiniMax-H3-Pruned-GGUF) のFL2VA Q3_K_M
- [realrebelai/MiniMax-H3_GGUFs](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs) のQwen Q2_K

これらは実験的なコミュニティ成果物です。特にrealrebelai repositoryは確認時点のmetadataでlicenseが `unknown` であり、ライセンス不在を意味しません。量子化物が上流条件を継承・追加する可能性、配布権限、商用利用可否を各repositoryと上流LICENSEで確認してください。Q3/Q2量子化により、公式ウェイトより品質が低下する可能性があります。

### lowvram_turbo（任意）

`lowvram_turbo` は上記4ファイルに、作者公開の
[`minimax_h3_turbo_v4_step600_ema.safetensors`](https://huggingface.co/larryvrh/MiniMax-H3-Turbo-Lora/blob/43a74557ac3f6539db8e0f2a959d03feb7a81480/minimax_h3_turbo_v4_step600_ema.safetensors)
を追加します。adapter repository/model cardはApache-2.0を表示しています。これはadapter単体の条件であり、base modelとそのcommunity量子化に適用されるMiniMax H3 Community Licenseや各repositoryの条件を置換・解除しません。

使用するcustom nodeは
[`Larryvrh/ComfyUI-MiniMax-H3-Turbo`](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo/tree/55fee864dd7b2976b1c4ce3c3d5f7968f181409f)
commit `55fee864dd7b2976b1c4ce3c3d5f7968f181409f`で、repositoryのLICENSEはApache-2.0です。`node.zip`は固定・導入対象ではなく、tracked runtime lockからrepository全体をcheckoutします。

作者は対応baseとしてbf16/int8_convrot、pruned int8/fp8を挙げますが、ここで組み合わせるcommunity Q3 GGUFを明示していません。そのため、この組合せは実験的です。LoRAがApache-2.0であっても、生成物の責任、base license、excluded territories、商用条件、UI表示条件は上記MiniMax H3 Community Licenseの確認対象として残ります。

### lowvram_q4_turbo（品質優先・任意）

`lowvram_q4_turbo` はQ2 text encoderの代わりに、同じlicense metadata `unknown` のrepositoryから
[`qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf`](https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/blob/daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7/qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf)
を取得し、Q3 diffusion、共通VAE 2点、Turbo adapterと組み合わせます。固定revisionは `daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7`、exact sizeは14,576,977,888 bytes、SHA-256は `1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e` です。

repository READMEには配布許諾に関する作者の主張がありますが、公開LICENSEや一般的OSS licenseの表示は確認できません。Q4であることはこの不明点を解消せず、上流MiniMax H3 Community Licenseおよびrepositoryの条件確認が必要です。固定runtimeでの利用対象はMiniMax H3 T2V text conditioningです。一般的なQwen3VL vision/mmproj対応はComfyUI-GGUFの[Issue #471](https://github.com/city96/ComfyUI-GGUF/issues/471)と[PR #473](https://github.com/city96/ComfyUI-GGUF/pull/473)が未解決のため、汎用I2V対応とは扱いません。

Q4 profileは実行時に必要な5ファイルだけを表し、Q2 encoderを含みません。fresh環境でQ2 Turboを比較・fallbackとして残す場合は、`lowvram_turbo` profileのlicenseも確認して別途取得してください。

## `-AcceptLicense` の意味

`download-models.ps1 -Profile <profile> -AcceptLicense` は、選択profileの全ファイル（`lowvram_turbo`、`lowvram_q4_turbo`、`official_q4_turbo` は5ファイル、他は4ファイル）について、この文書、各モデルカード、リンク先のライセンスを確認・受諾したという**一括の操作確認**です。

このswitchは次を行いません。

- ライセンスや権利を新たに付与する
- 地域・売上・商用表示・禁止用途の条件を免除する
- community repositoryの不明なmetadataを解消する
- 法務レビューを代替する

条件を受諾できない、または判断できない場合は、switchを付けずモデルをダウンロードしないでください。

## Runtimeとworkflow

- [ComfyUI](https://github.com/Comfy-Org/ComfyUI)、[ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF)、[ComfyUI-MiniMax-H3-Turbo](https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo)、PyTorchおよびPython依存は、それぞれのライセンスに従います。固定source/versionは[runtime-lock.json](runtime-lock.json)と[requirements-local-lock.txt](requirements-local-lock.txt)に記録しています。
- low-VRAM workflowは[Comfy-Org/workflow_templates](https://github.com/Comfy-Org/workflow_templates)のMIT-licensed templateを変換したものです。固定sourceと変更点は[workflows/README.md](workflows/README.md)に記録しています。
- API利用にはモデルライセンスとは別に、MiniMax Platformの契約、価格、privacy、content policyが適用されます。[MiniMax API docs](https://platform.minimax.io/docs/api-reference/video-generation-v2-create)を起点に実行時点の条件を確認してください。

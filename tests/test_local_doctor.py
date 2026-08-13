from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import local_doctor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ParsingTests(unittest.TestCase):
    def test_parse_nvidia_smi(self) -> None:
        parsed = local_doctor.parse_nvidia_smi(
            "NVIDIA GeForce RTX 3070 Ti, 8192, 591.86\n"
        )
        self.assertEqual(
            parsed,
            [
                {
                    "name": "NVIDIA GeForce RTX 3070 Ti",
                    "memory_mib": 8192,
                    "driver": "591.86",
                }
            ],
        )

    def test_parse_nvidia_smi_includes_free_vram(self) -> None:
        parsed = local_doctor.parse_nvidia_smi(
            "NVIDIA GeForce RTX 3070 Ti, 8192, 3584, 610.62\n"
        )
        self.assertEqual(parsed[0]["memory_mib"], 8192)
        self.assertEqual(parsed[0]["memory_free_mib"], 3584)
        self.assertEqual(parsed[0]["driver"], "610.62")

    def test_parse_pagefile_single_object(self) -> None:
        allocated, entries = local_doctor.parse_pagefile_json(
            '{"Name":"C:\\\\pagefile.sys","AllocatedBaseSize":32768,"CurrentUsage":10}'
        )
        self.assertEqual(allocated, 32768 * local_doctor.MIB)
        self.assertEqual(len(entries), 1)


class ModelTests(unittest.TestCase):
    def test_tracked_runtime_lock_pins_core_runtime(self) -> None:
        runtime_lock = local_doctor.load_runtime_lock(PROJECT_ROOT / "runtime-lock.json")
        self.assertEqual(runtime_lock["target"], {
            "os": "Windows",
            "architecture": "AMD64",
            "python": "3.12",
        })
        self.assertEqual(
            runtime_lock["repositories"]["comfyui"]["revision"],
            "2a68ce33b4c9ea6ee4283e618a74560cefb32694",
        )
        self.assertEqual(
            runtime_lock["repositories"]["comfyui_gguf"]["revision"],
            "6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
        )
        self.assertEqual(
            runtime_lock["repositories"]["minimax_h3_turbo"],
            {
                "repository": "https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo.git",
                "revision": "55fee864dd7b2976b1c4ce3c3d5f7968f181409f",
            },
        )
        self.assertEqual(
            runtime_lock["pytorch"]["packages"],
            {
                "torch": "2.13.0+cu130",
                "torchvision": "0.28.0+cu130",
                "torchaudio": "2.11.0+cu130",
            },
        )
        requirements = (PROJECT_ROOT / runtime_lock["requirements_file"]).read_text(
            encoding="utf-8"
        )
        self.assertIn("comfyui-frontend-package==1.48.7", requirements)
        self.assertNotIn("\ntorch==", requirements)
        self.assertNotIn("\ntorchvision==", requirements)
        self.assertNotIn("\ntorchaudio==", requirements)

    def test_tracked_manifest_has_sources_hashes_and_license_metadata(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "model-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(
            set(manifest["profiles"]),
            {
                "lowvram",
                "lowvram_turbo",
                "lowvram_q4_turbo",
                "official",
                "official_q4",
                "official_q4_turbo",
            },
        )
        for entry in manifest["models"].values():
            self.assertGreater(entry["bytes"], 0)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(entry["source_url"].startswith("https://huggingface.co/"))
            self.assertTrue(entry["license"])
            self.assertTrue(entry["license_url"].startswith("https://"))
        q4 = manifest["models"]["qwen3vl_h3_q4_k_m"]
        self.assertEqual(q4["repository"], "realrebelai/MiniMax-H3_GGUFs")
        self.assertEqual(q4["revision"], "daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7")
        self.assertEqual(q4["remote_path"], "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf")
        self.assertEqual(
            q4["license_url"],
            "https://huggingface.co/realrebelai/MiniMax-H3_GGUFs/blob/"
            "daf03b4ca652cce16dfd4fcf91e79c52ffa5c1e7/README.md",
        )
        self.assertEqual(
            manifest["models"]["qwen3vl_h3_q2_k"]["license_url"],
            q4["license_url"],
        )

    def test_official_manifest_entries_preserve_upstream_license_identity(self) -> None:
        manifest = json.loads((PROJECT_ROOT / "model-manifest.json").read_text(encoding="utf-8"))
        upstream_license_url = (
            "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/"
            "bfc8ed0353f5a9733be73e6b2c98ec0948195b86/LICENSE"
        )
        self.assertEqual(manifest["upstream_license_url"], upstream_license_url)
        for identifier in (
            "fl2va_pruned_int8_convrot",
            "qwen3vl_h3_nvfp4_awq",
            "video_vae_fp16",
            "audio_vae_fp32",
        ):
            entry = manifest["models"][identifier]
            self.assertEqual(entry["license"], "MiniMax H3 Community License Agreement")
            self.assertEqual(entry["license_url"], upstream_license_url)

    def test_profiles_have_exact_files(self) -> None:
        self.assertEqual(len(local_doctor.MODEL_PROFILES["lowvram"]), 4)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["lowvram_turbo"]), 5)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["lowvram_q4_turbo"]), 5)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["official"]), 4)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["official_q4"]), 4)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["official_q4_turbo"]), 5)
        low_names = {Path(spec.relative_path).name for spec in local_doctor.MODEL_PROFILES["lowvram"]}
        self.assertEqual(low_names, local_doctor.LOWVRAM_WORKFLOW_MODELS)
        self.assertEqual(
            sum(spec.expected_bytes for spec in local_doctor.MODEL_PROFILES["lowvram"]),
            23_203_877_000,
        )
        self.assertEqual(
            sum(spec.expected_bytes for spec in local_doctor.MODEL_PROFILES["official"]),
            42_470_585_471,
        )
        official_q4_names = {
            Path(spec.relative_path).name
            for spec in local_doctor.MODEL_PROFILES["official_q4"]
        }
        self.assertEqual(official_q4_names, local_doctor.OFFICIAL_Q4_WORKFLOW_MODELS)
        self.assertEqual(
            sum(spec.expected_bytes for spec in local_doctor.MODEL_PROFILES["official_q4"]),
            41_360_420_808,
        )
        official_q4_turbo_names = {
            Path(spec.relative_path).name
            for spec in local_doctor.MODEL_PROFILES["official_q4_turbo"]
        }
        self.assertEqual(
            official_q4_turbo_names,
            local_doctor.OFFICIAL_Q4_TURBO_WORKFLOW_MODELS,
        )
        turbo_names = {
            Path(spec.relative_path).name
            for spec in local_doctor.MODEL_PROFILES["lowvram_turbo"]
        }
        self.assertEqual(turbo_names, local_doctor.TURBO_WORKFLOW_MODELS)
        self.assertEqual(
            sum(spec.expected_bytes for spec in local_doctor.MODEL_PROFILES["lowvram_turbo"]),
            23_983_726_816,
        )
        q4_turbo_specs = local_doctor.MODEL_PROFILES["lowvram_q4_turbo"]
        self.assertEqual(
            {Path(spec.relative_path).name for spec in q4_turbo_specs},
            local_doctor.Q4_TURBO_WORKFLOW_MODELS,
        )
        self.assertEqual(sum(spec.expected_bytes for spec in q4_turbo_specs), 30_072_736_544)
        q4 = next(spec for spec in q4_turbo_specs if "Q4_K_M" in spec.relative_path)
        self.assertEqual(q4.expected_bytes, 14_576_977_888)
        self.assertEqual(
            q4.sha256,
            "1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e",
        )

    def test_model_size_check_detects_exact_and_mismatch(self) -> None:
        specs = (
            local_doctor.ModelSpec("diffusion_models/a.gguf", 3, "example/a"),
            local_doctor.ModelSpec("vae/b.safetensors", 5, "example/b"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "diffusion_models" / "a.gguf"
            second = root / "vae" / "b.safetensors"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_bytes(b"abc")
            second.write_bytes(b"bad")
            checks, missing = local_doctor.check_model_files(root, specs)

        self.assertEqual([check.status for check in checks], ["ok", "error"])
        self.assertEqual(missing, 5)

    def test_optional_hash_check_detects_content_mismatch(self) -> None:
        expected = hashlib.sha256(b"abc").hexdigest()
        specs = (local_doctor.ModelSpec("a.gguf", 3, "example/a", expected),)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.gguf"
            path.write_bytes(b"abc")
            good, missing_good = local_doctor.check_model_files(root, specs, verify_hash=True)
            path.write_bytes(b"xyz")
            bad, missing_bad = local_doctor.check_model_files(root, specs, verify_hash=True)

        self.assertEqual(good[0].status, "ok")
        self.assertIn("SHA-256 verified", good[0].summary)
        self.assertEqual(missing_good, 0)
        self.assertEqual(bad[0].status, "error")
        self.assertEqual(missing_bad, 3)

    def test_comfyui_requires_chunked_h3_vae_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            comfy = root / "runtime" / "ComfyUI"
            (comfy / "comfy_extras").mkdir(parents=True)
            (comfy / "comfy" / "ldm" / "minimax").mkdir(parents=True)
            (comfy / "main.py").write_text("", encoding="utf-8")
            (comfy / "comfy_extras" / "nodes_minimax_h3.py").write_text("", encoding="utf-8")
            vae = comfy / "comfy" / "ldm" / "minimax" / "vae.py"
            sd = comfy / "comfy" / "sd.py"
            vae.write_text("comfy_has_chunked_io = True\n", encoding="utf-8")
            sd.write_text("if comfy_has_chunked_io: pass\n", encoding="utf-8")
            with mock.patch.object(
                local_doctor,
                "_inspect_git_lock",
                return_value=("ok", "", {"revision": "a" * 40}),
            ):
                good = local_doctor.check_comfyui(root, "a" * 40)
                vae.write_text("", encoding="utf-8")
                missing = local_doctor.check_comfyui(root, "a" * 40)

        self.assertEqual(good.status, "ok", good.summary)
        self.assertTrue(good.details["minimax_h3_chunked_vae_io"])
        self.assertEqual(missing.status, "error")

    def test_turbo_node_checks_contracts_and_time_grid_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            turbo = root / "runtime" / "ComfyUI" / "custom_nodes" / "ComfyUI-MiniMax-H3-Turbo"
            turbo.mkdir(parents=True)
            source = '\n'.join(
                ('"MiniMaxH3TurboLoRA"', '"MiniMaxH3TurboSampler"', "low_vram", "weight_patched")
            )
            (turbo / "__init__.py").write_text(source, encoding="utf-8")
            grid = turbo / "h3_silu_temb_grid.safetensors"
            grid.write_bytes(b"grid")
            expected = hashlib.sha256(b"grid").hexdigest()
            with mock.patch.object(local_doctor, "TURBO_GRID_SHA256", expected), mock.patch.object(
                local_doctor,
                "_inspect_git_lock",
                return_value=("ok", "", {"revision": "b" * 40}),
            ):
                good = local_doctor.check_turbo_custom_node(root, "b" * 40)
                grid.write_bytes(b"bad!")
                bad = local_doctor.check_turbo_custom_node(root, "b" * 40)

        self.assertEqual(good.status, "ok", good.summary)
        self.assertEqual(good.details["grid_sha256"], expected)
        self.assertEqual(bad.status, "error")
        self.assertIn("SHA-256 mismatch", bad.summary)


class WorkflowTests(unittest.TestCase):
    def test_lowvram_workflow_loader_names_and_limits(self) -> None:
        result = local_doctor.check_workflow(PROJECT_ROOT)
        self.assertEqual(result.status, "ok", result.summary)

    def test_turbo_workflow_is_pinned_low_vram_and_wired(self) -> None:
        result = local_doctor.check_workflow(PROJECT_ROOT, "lowvram_turbo")
        self.assertEqual(result.status, "ok", result.summary)

        workflow = json.loads(
            (PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_turbo.json").read_text(
                encoding="utf-8"
            )
        )
        nodes = list(local_doctor._walk_nodes(workflow))
        lora = next(node for node in nodes if node.get("type") == "MiniMaxH3TurboLoRA")
        self.assertEqual(
            lora["widgets_values"],
            ["minimax_h3_turbo_v4_step600_ema.safetensors", 1, True],
        )
        scheduler = next(node for node in nodes if node.get("type") == "BasicScheduler")
        self.assertEqual(scheduler["widgets_values"], ["simple", 6, 1])

    def test_q4_turbo_workflow_is_quality_profile_and_preserves_q2_workflow_as_separate_fallback(self) -> None:
        result = local_doctor.check_workflow(PROJECT_ROOT, "lowvram_q4_turbo")
        self.assertEqual(result.status, "ok", result.summary)

        q4_path = PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json"
        q4_text = q4_path.read_text(encoding="utf-8")
        workflow = json.loads(q4_text)
        nodes = list(local_doctor._walk_nodes(workflow))
        clip = next(node for node in nodes if node.get("type") == "CLIPLoaderGGUF")
        scheduler = next(node for node in nodes if node.get("type") == "BasicScheduler")
        selector = next(node for node in nodes if node.get("type") == "ResolutionSelector")
        lora = next(node for node in nodes if node.get("type") == "MiniMaxH3TurboLoRA")
        self.assertEqual(
            clip["widgets_values"],
            ["qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf", "minimax"],
        )
        self.assertEqual(scheduler["widgets_values"], ["simple", 8, 1])
        self.assertEqual(selector["widgets_values"], ["16:9 (Widescreen)", 0.4, 32])
        self.assertEqual(
            lora["widgets_values"],
            ["minimax_h3_turbo_v4_step600_ema.safetensors", 1, True],
        )
        save_video = next(node for node in nodes if node.get("type") == "SaveVideo")
        self.assertEqual(save_video["widgets_values"][0], "video/MiniMax_H3_Q4")
        q4_graph = next(
            graph
            for graph in workflow["definitions"]["subgraphs"]
            if any(node.get("type") == "MiniMaxH3TurboLoRA" for node in graph["nodes"])
        )
        self.assertEqual(q4_graph["name"], "MiniMax H3 Q4 Turbo low-VRAM (GGUF)")
        instance = next(node for node in workflow["nodes"] if node.get("type") == q4_graph["id"])
        self.assertEqual(instance["title"], "MiniMax H3 Q4 Turbo low-VRAM (GGUF)")
        self.assertNotIn("qwen3vl-32B-MiniMax-H3-Q2_K.gguf", q4_text)

        q2_text = (
            PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_turbo.json"
        ).read_text(encoding="utf-8")
        self.assertIn("qwen3vl-32B-MiniMax-H3-Q2_K.gguf", q2_text)
        self.assertNotIn("qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf", q2_text)
        q2_workflow = json.loads(q2_text)
        q2_save = next(
            node for node in local_doctor._walk_nodes(q2_workflow) if node.get("type") == "SaveVideo"
        )
        self.assertEqual(q2_save["widgets_values"][0], "video/MiniMax_H3")

    def test_q4_turbo_workflow_rejects_q2_loader_even_if_notes_name_q4(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workflows").mkdir()
            workflow = json.loads(
                (
                    PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json"
                ).read_text(encoding="utf-8")
            )
            clip = next(
                node
                for node in local_doctor._walk_nodes(workflow)
                if node.get("type") == "CLIPLoaderGGUF"
            )
            clip["widgets_values"][0] = "qwen3vl-32B-MiniMax-H3-Q2_K.gguf"
            (root / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json").write_text(
                json.dumps(workflow),
                encoding="utf-8",
            )
            (root / "workflows" / "README.md").write_text(
                (PROJECT_ROOT / "workflows" / "README.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = local_doctor.check_workflow(root, "lowvram_q4_turbo")

            workflow = json.loads(
                (
                    PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json"
                ).read_text(encoding="utf-8")
            )
            subgraph_ids = {graph["id"] for graph in workflow["definitions"]["subgraphs"]}
            instance = next(node for node in workflow["nodes"] if node.get("type") in subgraph_ids)
            instance["widgets_values"][5:9] = [
                "wrong-unet.gguf",
                "wrong-text.gguf",
                "wrong-video.safetensors",
                "wrong-audio.safetensors",
            ]
            (root / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json").write_text(
                json.dumps(workflow),
                encoding="utf-8",
            )
            overridden = local_doctor.check_workflow(root, "lowvram_q4_turbo")

        self.assertEqual(result.status, "error")
        self.assertIn("CLIPLoaderGGUF must use", result.summary)
        self.assertEqual(overridden.status, "error")
        self.assertIn("subgraph model overrides", overridden.summary)

    def test_q4_turbo_workflow_rejects_resolution_geometry_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "workflows").mkdir()
            workflow = json.loads(
                (
                    PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json"
                ).read_text(encoding="utf-8")
            )
            selector = next(
                node
                for node in local_doctor._walk_nodes(workflow)
                if node.get("type") == "ResolutionSelector"
            )
            selector["widgets_values"] = ["4:3", 0.4, 64]
            (root / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json").write_text(
                json.dumps(workflow),
                encoding="utf-8",
            )
            (root / "workflows" / "README.md").write_text(
                (PROJECT_ROOT / "workflows" / "README.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            result = local_doctor.check_workflow(root, "lowvram_q4_turbo")

            workflow = json.loads(
                (
                    PROJECT_ROOT / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json"
                ).read_text(encoding="utf-8")
            )
            subgraph_ids = {graph["id"] for graph in workflow["definitions"]["subgraphs"]}
            instance = next(node for node in workflow["nodes"] if node.get("type") in subgraph_ids)
            selector = next(
                node for node in workflow["nodes"] if node.get("type") == "ResolutionSelector"
            )
            workflow["links"] = [
                link
                for link in workflow["links"]
                if not (
                    link[1] == selector["id"]
                    and link[2] == 0
                    and link[3] == instance["id"]
                    and link[4] == 2
                )
            ]
            (root / "workflows" / "minimax_h3_t2v_lowvram_q4_turbo.json").write_text(
                json.dumps(workflow),
                encoding="utf-8",
            )
            unlinked = local_doctor.check_workflow(root, "lowvram_q4_turbo")

        self.assertEqual(result.status, "error")
        self.assertIn("aspect ratio is not 16:9", result.summary)
        self.assertIn("multiple is not 32", result.summary)
        self.assertEqual(unlinked.status, "error")
        self.assertIn("width/height outputs", unlinked.summary)

    def test_official_profile_checks_official_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = (
                root
                / ".venv"
                / "Lib"
                / "site-packages"
                / "comfyui_workflow_templates_json"
                / "templates"
                / "video_minimax_h3_t2v.json"
            )
            template.parent.mkdir(parents=True)
            nodes = [
                {"type": "UNETLoader", "widgets_values": ["minimax_h3_fl2va_pruned_int8_convrot.safetensors"]},
                {"type": "CLIPLoader", "widgets_values": ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"]},
                {"type": "VAELoader", "widgets_values": ["minimax_h3_video_vae_fp16.safetensors"]},
                {"type": "VAELoader", "widgets_values": ["minimax_h3_audio_vae_fp32.safetensors"]},
            ]
            template.write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
            result = local_doctor.check_workflow(root, "official")

        self.assertEqual(result.status, "ok", result.summary)
        self.assertEqual(result.name, "workflow:official")

    def test_official_q4_workflows_use_int8_q4_and_expected_sampling(self) -> None:
        stock = local_doctor.check_workflow(PROJECT_ROOT, "official_q4")
        turbo = local_doctor.check_workflow(PROJECT_ROOT, "official_q4_turbo")

        self.assertEqual(stock.status, "ok", stock.summary)
        self.assertEqual(turbo.status, "ok", turbo.summary)

    @staticmethod
    def _mutate_official_q4_workflow(
        root: Path,
        profile: str,
        mutate: object,
    ) -> local_doctor.Check:
        workflows = root / "workflows"
        workflows.mkdir(parents=True)
        filename = (
            "minimax_h3_t2v_official_q4_turbo.json"
            if profile == "official_q4_turbo"
            else "minimax_h3_t2v_official_q4.json"
        )
        workflow = json.loads((PROJECT_ROOT / "workflows" / filename).read_text(encoding="utf-8"))
        mutate(workflow)
        (workflows / filename).write_text(json.dumps(workflow), encoding="utf-8")
        (workflows / "README.md").write_text(
            (PROJECT_ROOT / "workflows" / "README.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return local_doctor.check_workflow(root, profile)

    def test_official_q4_stock_rejects_direct_wiring_and_override_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def bad_guider(workflow: dict[str, object]) -> None:
                links = workflow["definitions"]["subgraphs"][0]["links"]
                next(link for link in links if link["id"] == 193)["origin_id"] = 17

            wiring = self._mutate_official_q4_workflow(root, "official_q4", bad_guider)

        self.assertEqual(wiring.status, "error")
        self.assertIn("BasicGuider.model must be linked from UNETLoader", wiring.summary)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def bad_override(workflow: dict[str, object]) -> None:
                workflow["nodes"][2]["widgets_values"][5] = "wrong.safetensors"

            override = self._mutate_official_q4_workflow(root, "official_q4", bad_override)

        self.assertEqual(override.status, "error")
        self.assertIn("subgraph model overrides must exactly select", override.summary)

    def test_official_q4_turbo_rejects_turbo_and_sigma_wiring_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def bad_turbo_input(workflow: dict[str, object]) -> None:
                links = workflow["definitions"]["subgraphs"][0]["links"]
                next(link for link in links if link["id"] == 228)["origin_id"] = 13

            turbo_input = self._mutate_official_q4_workflow(
                root, "official_q4_turbo", bad_turbo_input
            )

        self.assertEqual(turbo_input.status, "error")
        self.assertIn("MiniMaxH3TurboLoRA.model must be linked from UNETLoader", turbo_input.summary)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def bad_sigmas(workflow: dict[str, object]) -> None:
                links = workflow["definitions"]["subgraphs"][0]["links"]
                next(link for link in links if link["id"] == 18)["origin_id"] = 16

            sigmas = self._mutate_official_q4_workflow(root, "official_q4_turbo", bad_sigmas)

        self.assertEqual(sigmas.status, "error")
        self.assertIn("SamplerCustomAdvanced.sigmas must be linked from BasicScheduler", sigmas.summary)

    def test_official_q4_stock_rejects_resolution_and_pipeline_contract_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(workflow: dict[str, object]) -> None:
                next(link for link in workflow["links"] if link[0] == 219)[4] = 3
                nodes = workflow["definitions"]["subgraphs"][0]["nodes"]
                links = workflow["definitions"]["subgraphs"][0]["links"]
                next(link for link in links if link["id"] == 16)["origin_id"] = 9
                next(link for link in links if link["id"] == 189)["origin_id"] = 6
                next(node for node in nodes if node["type"] == "KSamplerSelect")["widgets_values"] = ["euler"]
                next(node for node in nodes if node["type"] == "CreateVideo")["widgets_values"] = [24, 10]
                next(node for node in nodes if node["type"] == "ComfyMathExpression")["widgets_values"] = ["a"]

            result = self._mutate_official_q4_workflow(root, "official_q4", mutate)

        self.assertEqual(result.status, "error")
        self.assertIn("ResolutionSelector width/height outputs", result.summary)
        self.assertIn("SamplerCustomAdvanced.sampler must be linked from KSamplerSelect", result.summary)
        self.assertIn("MiniMaxH3ImageToVideo.clip must be linked from CLIPLoaderGGUF", result.summary)
        self.assertIn("stock 20-step workflow must use KSamplerSelect res_multistep", result.summary)
        self.assertIn("CreateVideo must use 24 fps and 8-bit depth", result.summary)
        self.assertIn("duration expression is not the MiniMax H3 frame-grid formula", result.summary)

    def test_official_q4_turbo_rejects_resolution_denoise_decode_and_duration_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(workflow: dict[str, object]) -> None:
                next(link for link in workflow["links"] if link[0] == 220)[1] = 105
                workflow["nodes"][2]["widgets_values"][3] = 4
                nodes = workflow["definitions"]["subgraphs"][0]["nodes"]
                links = workflow["definitions"]["subgraphs"][0]["links"]
                next(node for node in nodes if node["type"] == "BasicScheduler")["widgets_values"][2] = 0.5
                next(link for link in links if link["id"] == 225)["origin_id"] = 104
                next(link for link in links if link["id"] == 8)["origin_id"] = 24
                next(link for link in links if link["id"] == 23)["origin_id"] = 11

            result = self._mutate_official_q4_workflow(root, "official_q4_turbo", mutate)

        self.assertEqual(result.status, "error")
        self.assertIn("ResolutionSelector width/height outputs", result.summary)
        self.assertIn("official Q4 workflow duration is not set to 5 seconds", result.summary)
        self.assertIn("BasicScheduler denoise is not set to 1.0", result.summary)
        self.assertIn("VAEDecode.samples must be linked from SamplerCustomAdvanced", result.summary)
        self.assertIn(
            "VAEDecode.vae must link from VAELoader minimax_h3_video_vae_fp16.safetensors",
            result.summary,
        )
        self.assertIn(
            "VAEDecodeAudio.vae must link from VAELoader minimax_h3_audio_vae_fp32.safetensors",
            result.summary,
        )


class ResourceTests(unittest.TestCase):
    def test_low_available_memory_warns_but_low_total_memory_blocks_ready(self) -> None:
        with mock.patch.object(
            local_doctor,
            "memory_bytes",
            return_value=(32 * local_doctor.GIB, 11 * local_doctor.GIB),
        ):
            pressure = local_doctor.check_ram()
        self.assertEqual(pressure.status, "warning")
        self.assertIn("-EmergencyLowVram", pressure.summary)

        with mock.patch.object(
            local_doctor,
            "memory_bytes",
            return_value=(32 * local_doctor.GIB - 1, 20 * local_doctor.GIB),
        ):
            insufficient = local_doctor.check_ram()
        self.assertEqual(insufficient.status, "error")

    def test_low_free_vram_warns_and_reports_free_memory(self) -> None:
        probe = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="NVIDIA GeForce RTX 3070 Ti, 8192, 3584, 610.62\n",
            stderr="",
        )
        with mock.patch.object(local_doctor.shutil, "which", return_value="nvidia-smi"), mock.patch.object(
            local_doctor, "_run", return_value=probe
        ):
            result = local_doctor.check_gpu()
        self.assertEqual(result.status, "warning")
        self.assertIn("3.5 GiB free", result.summary)
        self.assertIn("-EmergencyLowVram", result.summary)

    def test_disk_enforces_two_gib_minimum_and_warns_below_recommended_headroom(self) -> None:
        def disk_result(free: int) -> object:
            return type("DiskUsage", (), {"total": 100 * local_doctor.GIB, "free": free})()

        with mock.patch.object(local_doctor.shutil, "disk_usage", return_value=disk_result(2 * local_doctor.GIB - 1)):
            below_minimum = local_doctor.check_disk(PROJECT_ROOT, 0)
        with mock.patch.object(local_doctor.shutil, "disk_usage", return_value=disk_result(2 * local_doctor.GIB)):
            at_minimum = local_doctor.check_disk(PROJECT_ROOT, 0)
        with mock.patch.object(local_doctor.shutil, "disk_usage", return_value=disk_result(20 * local_doctor.GIB)):
            recommended = local_doctor.check_disk(PROJECT_ROOT, 0)
        with mock.patch.object(local_doctor.shutil, "disk_usage", return_value=disk_result(7 * local_doctor.GIB - 1)):
            missing_model_shortfall = local_doctor.check_disk(PROJECT_ROOT, 5 * local_doctor.GIB)

        self.assertEqual(below_minimum.status, "error")
        self.assertEqual(at_minimum.status, "warning")
        self.assertEqual(recommended.status, "ok")
        self.assertEqual(missing_model_shortfall.status, "error")


class PowerShellSyntaxTests(unittest.TestCase):
    def test_power_shell_scripts_parse(self) -> None:
        powershell = "powershell.exe"
        scripts = (
            "setup-local.ps1",
            "download-models.ps1",
            "run-local.ps1",
            "run-api.ps1",
            "tools/setup_lock_helpers.ps1",
            "tools/system_metrics.ps1",
        )
        for script in scripts:
            path = PROJECT_ROOT / script
            command = (
                "$errors=$null; "
                f"[System.Management.Automation.Language.Parser]::ParseFile('{path}',"
                "[ref]$null,[ref]$errors) | Out-Null; "
                "if($errors.Count){$errors | ForEach-Object {$_.Message}; exit 1}"
            )
            result = subprocess.run(
                (powershell, "-NoProfile", "-Command", command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{script}: {result.stdout}{result.stderr}")

    def test_run_local_uses_dynamic_vram_defaults(self) -> None:
        source = (PROJECT_ROOT / "run-local.ps1").read_text(encoding="utf-8")
        executable_lines = [line for line in source.splitlines() if not line.lstrip().startswith("Write-")]
        executable = "\n".join(executable_lines)
        exclusive_vram_mode = """if ($EmergencyLowVram) {
    $comfyArguments += @('--novram', '--cpu-vae')
}
else {
    $comfyArguments += '--enable-dynamic-vram'
}"""
        self.assertIn(exclusive_vram_mode, executable)
        common_arguments = executable.split("if ($EmergencyLowVram)", 1)[0]
        self.assertNotIn("--enable-dynamic-vram", common_arguments)
        self.assertNotIn("--novram", common_arguments)
        self.assertNotIn("$comfyArguments += '--lowvram'", executable)
        self.assertIn("'--preview-method', 'none'", executable)
        self.assertIn("'--disable-pinned-memory'", executable)
        self.assertIn(
            ".\\download-models.ps1 -Profile $Profile -AcceptLicense",
            source,
        )
        self.assertIn("does not auto-load or switch", source)
        self.assertIn("Open manually:", source)

    def test_run_local_reports_metrics_only_at_start_and_end(self) -> None:
        source = (PROJECT_ROOT / "run-local.ps1").read_text(encoding="utf-8")
        self.assertEqual(source.count("Show-SystemMetrics -Phase START"), 1)
        self.assertEqual(source.count("Show-SystemMetrics -Phase END"), 1)
        finally_block = source.split("finally {", 1)[1]
        self.assertIn("Show-SystemMetrics -Phase END", finally_block)

    def test_system_metrics_parsers(self) -> None:
        helper = str(PROJECT_ROOT / "tools" / "system_metrics.ps1").replace("'", "''")
        command = rf"""
. '{helper}'
$gpu = ConvertFrom-NvidiaSmiCsvRow -Line 'NVIDIA GeForce RTX 3070 Ti, 72, 63, 6144, 8192, 245.5' -IncludesPower
$result = [pscustomobject]@{{
    gpu = $gpu
    acpiCelsius = ConvertFrom-AcpiTenthsKelvin 3152
    invalidAcpi = ConvertFrom-AcpiTenthsKelvin 1
}}
$result | ConvertTo-Json -Depth 4 -Compress
"""
        result = subprocess.run(
            ("powershell.exe", "-NoProfile", "-Command", command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        parsed = json.loads(result.stdout.strip())
        self.assertEqual(parsed["gpu"]["Name"], "NVIDIA GeForce RTX 3070 Ti")
        self.assertEqual(parsed["gpu"]["UtilizationPercent"], 72)
        self.assertEqual(parsed["gpu"]["TemperatureCelsius"], 63)
        self.assertEqual(parsed["gpu"]["MemoryUsedMiB"], 6144)
        self.assertEqual(parsed["gpu"]["PowerWatts"], 245.5)
        self.assertAlmostEqual(parsed["acpiCelsius"], 42.05, places=2)
        self.assertIsNone(parsed["invalidAcpi"])

    def test_setup_preserves_dirty_runtime_repositories(self) -> None:
        source = (PROJECT_ROOT / "setup-local.ps1").read_text(encoding="utf-8")
        helpers = (PROJECT_ROOT / "tools" / "setup_lock_helpers.ps1").read_text(encoding="utf-8")
        self.assertNotIn("function Set-GitRepositoryRevision", source)
        self.assertIn("status --porcelain --untracked-files=normal", helpers)
        self.assertNotIn("'pull'", helpers)
        self.assertNotIn("'reset'", helpers)
        self.assertIn("runtime-lock.json", source)
        self.assertIn("ComfyUI-MiniMax-H3-Turbo", source)
        self.assertIn("requirements-local-lock.txt", (PROJECT_ROOT / "runtime-lock.json").read_text(encoding="utf-8"))

    def test_setup_passes_exact_torch_arguments_to_external_invoker(self) -> None:
        setup = str(PROJECT_ROOT / "setup-local.ps1").replace("'", "''")
        lock = str(PROJECT_ROOT / "runtime-lock.json").replace("'", "''")
        command = rf"""
. '{setup}' -LoadHelpersOnly
$runtimeLock = Get-Content -LiteralPath '{lock}' -Raw -Encoding UTF8 | ConvertFrom-Json
$script:received = @{{}}
function Invoke-External {{
    param([string] $FilePath, [string[]] $ArgumentList, [string] $Description)
    $script:received[$FilePath] = @($ArgumentList)
}}
$uvArguments = Get-TorchInstallArguments -UseUv $true -PythonPath 'X:\venv\python.exe' -RuntimeLock $runtimeLock
Invoke-External -FilePath 'uv.exe' -ArgumentList $uvArguments -Description 'test'
$pipArguments = Get-TorchInstallArguments -UseUv $false -PythonPath 'X:\venv\python.exe' -RuntimeLock $runtimeLock
Invoke-External -FilePath 'python.exe' -ArgumentList $pipArguments -Description 'test'
$script:received | ConvertTo-Json -Compress
"""
        result = subprocess.run(
            ("powershell.exe", "-NoProfile", "-Command", command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        received = json.loads(result.stdout.strip())
        for executable in ("uv.exe", "python.exe"):
            arguments = received[executable]
            self.assertIn("torch==2.13.0+cu130", arguments)
            self.assertIn("torchvision==0.28.0+cu130", arguments)
            self.assertIn("torchaudio==2.11.0+cu130", arguments)
            self.assertIn("https://download.pytorch.org/whl/cu130", arguments)
        self.assertEqual(received["uv.exe"][:4], ["pip", "install", "--python", "X:\\venv\\python.exe"])
        self.assertEqual(received["python.exe"][:3], ["-m", "pip", "install"])

    def test_setup_fresh_clone_checks_out_lock_and_preserves_dirty_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            remote = temp_root / "remote"
            destination = temp_root / "runtime" / "ComfyUI"
            subprocess.run(("git", "init", "-b", "main", str(remote)), check=True, capture_output=True)
            subprocess.run(("git", "-C", str(remote), "config", "user.email", "test@example.test"), check=True)
            subprocess.run(("git", "-C", str(remote), "config", "user.name", "Test"), check=True)
            tracked = remote / "requirements.txt"
            tracked.write_text("first\n", encoding="utf-8")
            subprocess.run(("git", "-C", str(remote), "add", "requirements.txt"), check=True)
            subprocess.run(("git", "-C", str(remote), "commit", "-m", "first"), check=True, capture_output=True)
            first_revision = subprocess.check_output(
                ("git", "-C", str(remote), "rev-parse", "HEAD"), text=True
            ).strip()
            tracked.write_text("second\n", encoding="utf-8")
            subprocess.run(("git", "-C", str(remote), "commit", "-am", "second"), check=True, capture_output=True)
            second_revision = subprocess.check_output(
                ("git", "-C", str(remote), "rev-parse", "HEAD"), text=True
            ).strip()

            setup = str(PROJECT_ROOT / "setup-local.ps1").replace("'", "''")
            repository = str(remote).replace("'", "''")
            checkout = str(destination).replace("'", "''")
            command = rf"""
. '{setup}' -LoadHelpersOnly
Set-GitRepositoryRevision -Repository '{repository}' -Revision '{first_revision}' -Destination '{checkout}' -Label 'fresh-test'
"""
            result = subprocess.run(
                ("powershell.exe", "-NoProfile", "-Command", command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((destination / "requirements.txt").read_text(encoding="utf-8"), "first\n")
            self.assertEqual(
                subprocess.check_output(("git", "-C", str(destination), "rev-parse", "HEAD"), text=True).strip(),
                first_revision,
            )

            shallow = temp_root / "runtime" / "shallow"
            subprocess.run(
                ("git", "clone", "--depth", "1", remote.as_uri(), str(shallow)),
                check=True,
                capture_output=True,
            )
            missing_object = subprocess.run(
                ("git", "-C", str(shallow), "cat-file", "-e", f"{first_revision}^{{commit}}"),
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(missing_object.returncode, 0)
            shallow_checkout = str(shallow).replace("'", "''")
            shallow_repository = remote.as_uri().replace("'", "''")
            fetch_command = rf"""
. '{setup}' -LoadHelpersOnly
Set-GitRepositoryRevision -Repository '{shallow_repository}' -Revision '{first_revision}' -Destination '{shallow_checkout}' -Label 'missing-object-test'
"""
            fetched = subprocess.run(
                ("powershell.exe", "-NoProfile", "-Command", fetch_command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(fetched.returncode, 0, fetched.stdout + fetched.stderr)
            self.assertEqual(
                subprocess.check_output(("git", "-C", str(shallow), "rev-parse", "HEAD"), text=True).strip(),
                first_revision,
            )
            self.assertFalse(
                subprocess.check_output(("git", "-C", str(destination), "status", "--porcelain"), text=True).strip()
            )

            (destination / "requirements.txt").write_text("local-change\n", encoding="utf-8")
            dirty_command = rf"""
. '{setup}' -LoadHelpersOnly
Set-GitRepositoryRevision -Repository '{repository}' -Revision '{second_revision}' -Destination '{checkout}' -Label 'dirty-test'
"""
            dirty_result = subprocess.run(
                ("powershell.exe", "-NoProfile", "-Command", dirty_command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertNotEqual(dirty_result.returncode, 0)
            self.assertEqual((destination / "requirements.txt").read_text(encoding="utf-8"), "local-change\n")
            self.assertEqual(
                subprocess.check_output(("git", "-C", str(destination), "rev-parse", "HEAD"), text=True).strip(),
                first_revision,
            )

    def test_downloader_uses_tracked_manifest_and_license_gate(self) -> None:
        source = (PROJECT_ROOT / "download-models.ps1").read_text(encoding="utf-8")
        self.assertIn("model-manifest.json", source)
        self.assertIn("if (-not $AcceptLicense)", source)
        self.assertIn("$actualBytes -eq $entry.ExpectedBytes", source)
        self.assertIn("--revision", source)
        self.assertIn("lowvram_turbo", source)
        self.assertIn("lowvram_q4_turbo", source)
        self.assertIn("official_q4", source)
        self.assertIn("official_q4_turbo", source)
        self.assertIn("$loraRoot", source)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator, Mapping
from unittest import mock

from tools.studio import comfyui as comfyui_module
from tools.studio import comfyui_execution as execution
from tools.studio.comfyui import (
    cleanup_comfyui_submission_marker,
    generate_comfyui_video,
    observe_comfyui_submission,
    prepare_comfyui_workflow,
    recover_comfyui_prompt_id,
    recover_comfyui_terminal_state,
    request_comfyui_provider_cancel,
    resolve_comfyui_runtime_identity,
    resolve_comfyui_tool_identity,
    resume_comfyui_video,
    validate_comfyui_outputs,
)
from tools.studio.comfyui_execution import (
    COMFYUI_WORKFLOW_PRESET,
    ComfyUIError,
    ComfyUIMediaError,
    ComfyUISubmissionPersistenceError,
    ComfyUISubmissionUnknown,
    ComfyUIValidationError,
    comfyui_audit_payload,
    comfyui_cache_key,
    comfyui_payload_digest,
    comfyui_public_result,
    comfyui_resume_payload,
    normalize_model_records,
    normalize_runtime_identity,
    normalize_workflow_record,
    validate_comfyui_payload,
)
from tools.studio.jobs import JobCancelled, JobExecutionContext
from tools.studio.security import canonical_json


PROMPT_ID = "01234567-89ab-4cde-8f01-23456789abcd"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


class _ComfyHandler(BaseHTTPRequestHandler):
    server: "_ComfyServer"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise TypeError("request must be an object")
        return value

    def _json(self, status: int, value: Mapping[str, Any]) -> None:
        encoded = canonical_json(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        body = self._read_json()
        self.server.posts.append({"path": self.path, "json": body})
        if self.path == "/queue":
            self.server.queue_requests.append(body)
            self._json(200, {})
            return
        if self.path == f"/api/jobs/{self.server.prompt_id}/cancel":
            self.server.job_cancel_requests.append(self.server.prompt_id)
            self._json(200, {"cancelled": True})
            return
        if self.path != "/prompt":
            self._json(404, {"error": "not found"})
            return
        if self.server.prompt_mode == "reject":
            self._json(400, {"error": "invalid workflow"})
            return
        if self.server.prompt_mode == "redirect":
            self.send_response(307)
            self.send_header("Location", f"{self.server.url}/redirect-target")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.server.prompt_mode == "oversize":
            self.send_response(200)
            self.send_header(
                "Content-Length", str(comfyui_module.MAX_HTTP_RESPONSE_BYTES + 1)
            )
            self.end_headers()
            return
        prompt = body.get("prompt")
        if isinstance(prompt, dict):
            self.server.submitted_graph = copy.deepcopy(prompt)
        self._json(
            200,
            {
                "prompt_id": self.server.prompt_id,
                "number": 7,
                "node_errors": {},
            },
        )

    def do_GET(self) -> None:
        self.server.gets.append(self.path)
        if self.path == "/system_stats":
            if self.server.system_stats_mode == "redirect":
                self.send_response(307)
                self.send_header("Location", f"{self.server.url}/redirect-target")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._json(200, self.server.system_stats)
            return
        if self.path == f"/api/jobs/{self.server.prompt_id}":
            if self.server.job_status == "not_found":
                self._json(404, {"error": "Job not found"})
            else:
                self._json(
                    200,
                    {"id": self.server.prompt_id, "status": self.server.job_status},
                )
            return
        if self.path != f"/history/{self.server.prompt_id}":
            self._json(404, {"error": "not found"})
            return
        if self.server.empty_history_reads > 0:
            self.server.empty_history_reads -= 1
            self._json(200, {})
            return
        graph = self.server.submitted_graph
        if graph is None:
            self._json(500, {"error": "missing submitted graph"})
            return
        if self.server.history_mode == "error":
            status = {"status_str": "error", "completed": True, "messages": []}
            outputs: dict[str, Any] = {}
        else:
            status = {"status_str": "success", "completed": True, "messages": []}
            outputs = {
                "92": {
                    "images": [dict(self.server.output_metadata)],
                    "animated": [True],
                }
            }
        self._json(
            200,
            {
                self.server.prompt_id: {
                    "prompt": [0, self.server.prompt_id, graph, {}, ["92"]],
                    "outputs": outputs,
                    "status": status,
                }
            },
        )


class _ComfyServer(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _ComfyHandler)
        self.prompt_id = PROMPT_ID
        self.prompt_mode = "success"
        self.history_mode = "success"
        self.job_status = "in_progress"
        self.empty_history_reads = 0
        self.system_stats_mode = "success"
        self.system_stats: dict[str, Any] = {}
        self.output_metadata: dict[str, Any] = {
            "filename": "generated_00001_.mp4",
            "subfolder": "",
            "type": "output",
        }
        self.submitted_graph: dict[str, Any] | None = None
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []
        self.queue_requests: list[dict[str, Any]] = []
        self.job_cancel_requests: list[str] = []

    @property
    def url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


@contextlib.contextmanager
def _mock_server() -> Iterator[_ComfyServer]:
    server = _ComfyServer()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ComfyUIContractTests(unittest.TestCase):
    def test_public_payload_is_exact_and_prompt_redaction_is_explicit(self) -> None:
        payload = {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": "静かなスタジオで話す人物",
            "seed": 42,
        }
        self.assertEqual(validate_comfyui_payload(payload), payload)
        self.assertEqual(comfyui_resume_payload(payload), payload)

        for invalid in (
            {**payload, "extra": True},
            {**payload, "workflow_preset": "custom"},
            {**payload, "prompt": ""},
            {**payload, "prompt": "bad\x00prompt"},
            {**payload, "seed": True},
            {**payload, "seed": -1},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                ComfyUIValidationError
            ):
                validate_comfyui_payload(invalid)

    def test_loopback_endpoint_is_literal_http_only(self) -> None:
        self.assertEqual(
            comfyui_module._normalize_base_url("http://127.0.0.1:8188/"),
            "http://127.0.0.1:8188",
        )
        self.assertEqual(
            comfyui_module._normalize_base_url("http://[::1]:8188"),
            "http://[::1]:8188",
        )
        for invalid in (
            "http://localhost:8188",
            "http://127.0.0.2:8188",
            "https://127.0.0.1:8188",
            "http://user@127.0.0.1:8188",
            "http://127.0.0.1:8188/api",
            "http://127.0.0.1",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(
                ComfyUIValidationError
            ):
                comfyui_module._normalize_base_url(invalid)

    def test_public_result_rejects_bad_prompt_and_seed_metadata(self) -> None:
        prompt_digest = _sha256_bytes(b"prompt")
        raw = {
            "provider": "comfyui",
            "timing_source": "ffprobe",
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "cache_key": "A" * 64,
            "cache_hit": False,
            "duration_ms": execution.OUTPUT_POLICY["expected_duration_ms"],
            "provider_task_id": PROMPT_ID,
            "prompt_id": PROMPT_ID,
            "prompt_sha256": prompt_digest,
            "seed": 1,
            "actual_cost": 0,
        }
        result = comfyui_public_result(
            raw,
            expected_cache_key="A" * 64,
            expected_prompt_sha256=prompt_digest,
            expected_seed=1,
            artifacts=[],
            cache_hit=False,
        )
        self.assertEqual(result["seed"], 1)
        self.assertEqual(result["seed_decimal"], "1")
        self.assertNotIn("prompt", result)
        for field, value in (("prompt_sha256", "bad"), ("seed", True)):
            with self.subTest(field=field), self.assertRaises(ComfyUIError):
                comfyui_public_result(
                    {**raw, field: value},
                    expected_cache_key="A" * 64,
                    expected_prompt_sha256=prompt_digest,
                    expected_seed=1,
                    artifacts=[],
                    cache_hit=False,
                )
        with self.assertRaises(ComfyUIError):
            comfyui_public_result(
                {**raw, "workflow_preset": "custom"},
                expected_cache_key="A" * 64,
                expected_prompt_sha256=prompt_digest,
                expected_seed=1,
                artifacts=[],
                cache_hit=False,
            )
        with self.assertRaises(ComfyUIError):
            comfyui_public_result(
                raw,
                expected_cache_key="A" * 64,
                expected_prompt_sha256=prompt_digest,
                expected_seed=2,
                artifacts=[],
                cache_hit=False,
                )


class ComfyUIRuntimeIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.repository = Path(__file__).resolve().parents[1]
        for spec in execution.RUNTIME_FILE_SPECS.values():
            relative = Path(spec["relative_path"])
            destination = self.workspace / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.repository / relative, destination)
        for spec in execution.RUNTIME_REPOSITORY_SPECS.values():
            (self.workspace / spec["relative_path"] / ".git").mkdir(
                parents=True, exist_ok=True
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git_output(self, argv: list[str], **_kwargs: Any) -> bytes:
        repository = Path(argv[2])
        relative = repository.relative_to(self.workspace).as_posix()
        spec = next(
            item
            for item in execution.RUNTIME_REPOSITORY_SPECS.values()
            if item["relative_path"] == relative
        )
        if argv[-3:] == ["rev-parse", "--verify", "HEAD"]:
            return (spec["revision"] + "\n").encode("ascii")
        if "status" in argv:
            return b""
        raise AssertionError(argv)

    def test_resolver_verifies_locks_heads_and_tracked_clean_state(self) -> None:
        with mock.patch.object(
            comfyui_module.shutil, "which", return_value="C:/tools/git.exe"
        ), mock.patch.object(
            comfyui_module, "_bounded_process", side_effect=self._git_output
        ) as process:
            identity = resolve_comfyui_runtime_identity(self.workspace)
        self.assertEqual(identity, normalize_runtime_identity(identity))
        self.assertEqual(process.call_count, 6)
        self.assertEqual(
            identity["repositories"]["comfyui"]["revision"],
            execution.RUNTIME_REPOSITORY_SPECS["comfyui"]["revision"],
        )
        self.assertTrue(
            all(
                record["tracked_clean"]
                for record in identity["repositories"].values()
            )
        )

    def test_resolver_rejects_tampered_lock_before_git(self) -> None:
        requirements = self.workspace / execution.RUNTIME_FILE_SPECS[
            "requirements_lock"
        ]["relative_path"]
        requirements.write_bytes(requirements.read_bytes() + b"tamper")
        with mock.patch.object(comfyui_module.shutil, "which") as which:
            with self.assertRaises(ComfyUIValidationError):
                resolve_comfyui_runtime_identity(self.workspace)
        which.assert_not_called()

    def test_resolver_rejects_ignored_extra_model_paths_before_git(self) -> None:
        extra = self.workspace / "runtime" / "ComfyUI" / "extra_model_paths.yaml"
        extra.write_text("models: C:/untracked/models\n", encoding="utf-8")
        with mock.patch.object(comfyui_module.shutil, "which") as which:
            with self.assertRaisesRegex(
                ComfyUIValidationError, "extra model paths"
            ):
                resolve_comfyui_runtime_identity(self.workspace)
        which.assert_not_called()

    def test_resolver_rejects_dirty_tracked_repository(self) -> None:
        def dirty_git(argv: list[str], **kwargs: Any) -> bytes:
            clean = self._git_output(argv, **kwargs)
            if "status" in argv and argv[2].replace("\\", "/").endswith(
                "custom_nodes/ComfyUI-GGUF"
            ):
                return b" M nodes.py\n"
            return clean

        with mock.patch.object(
            comfyui_module.shutil, "which", return_value="C:/tools/git.exe"
        ), mock.patch.object(
            comfyui_module, "_bounded_process", side_effect=dirty_git
        ):
            with self.assertRaisesRegex(
                ComfyUIValidationError, "does not match the lock"
            ):
                resolve_comfyui_runtime_identity(self.workspace)


class ComfyUIAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ffmpeg = shutil.which("ffmpeg")
        cls.ffprobe = shutil.which("ffprobe")
        if cls.ffmpeg is None or cls.ffprobe is None:
            raise unittest.SkipTest("ffmpeg and ffprobe are required")
        cls.media_temporary = tempfile.TemporaryDirectory()
        cls.media_template = Path(cls.media_temporary.name) / "generated.mp4"
        subprocess.run(
            [
                cls.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=480x864:r=24:d=5.1666667",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=32000:cl=stereo:d=5.1666667",
                "-frames:v",
                "124",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-ar",
                "32000",
                "-ac",
                "2",
                str(cls.media_template),
            ],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.media_temporary.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.repository = Path(__file__).resolve().parents[1]
        self.workflow_bytes = (
            self.repository / execution.COMFYUI_WORKFLOW_RELATIVE_PATH
        ).read_bytes()
        self.workflow_path = (
            self.workspace / execution.COMFYUI_WORKFLOW_RELATIVE_PATH
        )
        self.workflow_path.parent.mkdir(parents=True)
        self.workflow_path.write_bytes(self.workflow_bytes)
        self.workflow = json.loads(self.workflow_bytes.decode("utf-8"))
        self.payload = {
            "workflow_preset": COMFYUI_WORKFLOW_PRESET,
            "prompt": "A presenter turns toward the camera, photorealistic.",
            "seed": 123456789,
        }

        self.model_specs: dict[str, dict[str, Any]] = {}
        self.model_files: dict[str, dict[str, Any]] = {}
        for index, (role, original) in enumerate(execution.MODEL_SPECS.items()):
            data = f"test-model-{role}-{index}".encode("ascii")
            spec = {
                **original,
                "bytes": len(data),
                "sha256": _sha256_bytes(data),
            }
            self.model_specs[role] = spec
            path = self.workspace / spec["relative_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.model_files[role] = {
                "path": spec["relative_path"],
                "bytes": len(data),
                "sha256": spec["sha256"],
            }
        self.model_patch = mock.patch.object(
            execution, "MODEL_SPECS", self.model_specs
        )
        self.model_patch.start()

        self.runtime_identity = normalize_runtime_identity(
            {
                role: {
                    "path": spec["relative_path"],
                    "bytes": spec["bytes"],
                    "sha256": spec["sha256"],
                }
                for role, spec in execution.RUNTIME_FILE_SPECS.items()
            }
            | {
                "repositories": {
                    role: {
                        "path": spec["relative_path"],
                        "revision": spec["revision"],
                        "tracked_clean": True,
                    }
                    for role, spec in execution.RUNTIME_REPOSITORY_SPECS.items()
                }
            }
        )
        self.runtime_patch = mock.patch.object(
            comfyui_module,
            "resolve_comfyui_runtime_identity",
            return_value=copy.deepcopy(self.runtime_identity),
        )
        self.runtime_patch.start()

        self.comfy_main = self.workspace / "runtime" / "ComfyUI" / "main.py"
        self.comfy_main.parent.mkdir(parents=True, exist_ok=True)
        self.comfy_main.write_text("# test ComfyUI entrypoint\n", encoding="utf-8")
        self.output_root = self.workspace / "outputs"
        cache_key = self._cache_key()
        self.provider_subfolder = (
            f"studio/comfyui/PROD_COMFY_TEST/RUN_COMFY_TEST/{cache_key[:16]}"
        )
        source = self.output_root / self.provider_subfolder / "generated_00001_.mp4"
        source.parent.mkdir(parents=True)
        shutil.copyfile(self.media_template, source)
        self.source_output = source
        self.expected_output_metadata = {
            "filename": "generated_00001_.mp4",
            "subfolder": self.provider_subfolder,
            "type": "output",
        }

    def tearDown(self) -> None:
        self.runtime_patch.stop()
        self.model_patch.stop()
        self.temporary.cleanup()

    def _kwargs(self, server: _ComfyServer) -> dict[str, Any]:
        _host, port = server.server_address
        server.output_metadata = copy.deepcopy(self.expected_output_metadata)
        server.system_stats = {
            "system": {
                "comfyui_version": "0.31.0",
                "python_version": "3.12.2 (test build)",
                "pytorch_version": "2.13.0+cu130",
                "argv": [
                    str(self.comfy_main),
                    "--listen",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--preview-method",
                    "none",
                    "--disable-pinned-memory",
                    "--output-directory",
                    str(self.output_root),
                    "--disable-all-custom-nodes",
                    "--whitelist-custom-nodes",
                    "ComfyUI-GGUF",
                    "--enable-dynamic-vram",
                    "--disable-auto-launch",
                ],
            },
            "devices": [],
        }
        return {
            "production_id": "PROD_COMFY_TEST",
            "run_id": "RUN_COMFY_TEST",
            "payload": copy.deepcopy(self.payload),
            "workflow": copy.deepcopy(self.workflow),
            "workflow_source_path": self.workflow_path,
            "workflow_source_bytes": len(self.workflow_bytes),
            "workflow_source_sha256": _sha256_bytes(self.workflow_bytes),
            "model_files": copy.deepcopy(self.model_files),
            "output_roots": [self.output_root],
            "expected_cache_key": self._cache_key(),
            "ffprobe": self.ffprobe,
            "base_url": server.url,
            "request_timeout_seconds": 2,
            "generation_timeout_seconds": 5,
            "poll_interval_seconds": 0,
        }

    def _workflow_record(self) -> dict[str, Any]:
        return normalize_workflow_record(
            {
                "path": execution.COMFYUI_WORKFLOW_RELATIVE_PATH,
                "bytes": len(self.workflow_bytes),
                "sha256": _sha256_bytes(self.workflow_bytes),
                "graph_sha256": _sha256_bytes(
                    canonical_json(self.workflow).encode("utf-8")
                ),
            }
        )

    def _cache_key(self, payload: Mapping[str, Any] | None = None) -> str:
        return comfyui_cache_key(
            self.payload if payload is None else payload,
            workflow=self._workflow_record(),
            models=normalize_model_records(self.model_files),
            runtime_identity=self.runtime_identity,
            ffprobe_identity=resolve_comfyui_tool_identity(ffprobe=self.ffprobe),
        )

    def _marker(self) -> Path:
        return (
            self.workspace
            / "outputs"
            / "studio"
            / "external-submissions"
            / "comfyui"
            / "PROD_COMFY_TEST"
            / self._cache_key()
            / comfyui_module.SUBMISSION_MARKER_FILENAME
        )

    def test_graph_injection_and_cache_identity_are_exact(self) -> None:
        original = copy.deepcopy(self.workflow)
        injected = prepare_comfyui_workflow(
            self.workflow,
            self.payload,
            output_prefix="studio/comfyui/PROD/RUN/cache/generated",
        )
        self.assertEqual(self.workflow, original)
        expected = copy.deepcopy(original)
        expected["105:104"]["inputs"]["prompt"] = self.payload["prompt"]
        expected["105:15"]["inputs"]["noise_seed"] = self.payload["seed"]
        expected["92"]["inputs"]["filename_prefix"] = (
            "studio/comfyui/PROD/RUN/cache/generated"
        )
        self.assertEqual(injected, expected)
        tampered = copy.deepcopy(self.workflow)
        tampered["105:9"]["inputs"]["steps"] = 19
        with self.assertRaises(ComfyUIValidationError):
            prepare_comfyui_workflow(
                tampered, self.payload, output_prefix="studio/comfyui/x"
            )

        first = self._cache_key()
        changed = comfyui_cache_key(
            {**self.payload, "seed": self.payload["seed"] + 1},
            workflow=self._workflow_record(),
            models=normalize_model_records(self.model_files),
            runtime_identity=self.runtime_identity,
            ffprobe_identity=resolve_comfyui_tool_identity(ffprobe=self.ffprobe),
        )
        self.assertNotEqual(first, changed)

        audit = comfyui_audit_payload(
            self.payload,
            workflow=self._workflow_record(),
            models=self.model_files,
            runtime_identity=self.runtime_identity,
            cache_key=first,
        )
        self.assertNotIn("prompt", audit)
        self.assertEqual(audit["seed_decimal"], str(self.payload["seed"]))
        self.assertEqual(
            audit["prompt_sha256"],
            _sha256_bytes(self.payload["prompt"].encode("utf-8")),
        )
        self.assertNotIn(self.payload["prompt"], canonical_json(audit))

    def test_submit_poll_publish_cache_and_revalidate(self) -> None:
        callbacks: list[str] = []
        with _mock_server() as server:
            first = generate_comfyui_video(
                self.workspace,
                **self._kwargs(server),
                on_provider_task_id=callbacks.append,
            )
            self.assertFalse(first["cache_hit"])
            self.assertEqual(callbacks, [PROMPT_ID])
            self.assertEqual(first["provider_task_id"], PROMPT_ID)
            self.assertEqual(first["actual_cost"], 0)
            self.assertEqual(first["timing_source"], "ffprobe")
            self.assertEqual(first["prompt_sha256"], _sha256_bytes(self.payload["prompt"].encode()))
            self.assertNotIn("prompt", first)
            self.assertEqual(len([item for item in server.posts if item["path"] == "/prompt"]), 1)
            submitted = server.submitted_graph
            self.assertIsNotNone(submitted)
            self.assertEqual(submitted["105:104"]["inputs"]["prompt"], self.payload["prompt"])
            self.assertEqual(submitted["105:15"]["inputs"]["noise_seed"], self.payload["seed"])

            names = {item["name"] for item in first["artifacts"]}
            self.assertEqual(
                names,
                {"generated-video.mp4", "workflow.json", "ffprobe.json", "manifest.json"},
            )
            output_directory = self.workspace / first["output_directory"]
            manifest_path = output_directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            unsigned = dict(manifest)
            digest = unsigned.pop("manifest_sha256")
            self.assertEqual(
                digest,
                _sha256_bytes(canonical_json(unsigned).encode("utf-8")),
            )
            self.assertEqual(manifest["source_output"]["sha256"], _sha256_bytes(self.source_output.read_bytes()))
            self.assertEqual(manifest["runtime_identity"], self.runtime_identity)
            self.assertEqual(manifest["seed_decimal"], str(self.payload["seed"]))
            self.assertEqual(manifest["provider_runtime"]["comfyui_version"], "0.31.0")
            self.assertEqual(manifest["provider_runtime"]["argv"]["output_directory"], "outputs")
            self.assertTrue(
                manifest["provider_runtime"]["argv"]["disable_all_custom_nodes"]
            )
            self.assertEqual(
                manifest["provider_runtime"]["argv"]["whitelist_custom_nodes"],
                ["ComfyUI-GGUF"],
            )
            self.assertEqual(
                manifest["provider_runtime"]["argv"]["vram_mode"], "dynamic"
            )
            self.assertEqual(
                manifest["provider_runtime"]["argv"]["browser_mode"], "disabled"
            )
            self.assertNotIn(self.payload["prompt"], manifest_path.read_text(encoding="utf-8"))
            self.assertFalse((output_directory / "history.json").exists())
            workflow_document = json.loads((output_directory / "workflow.json").read_text(encoding="utf-8"))
            self.assertEqual(
                workflow_document["request_body"]["prompt"]["105:104"]["inputs"]["prompt"],
                self.payload["prompt"],
            )
            self.assertEqual(workflow_document["seed_decimal"], str(self.payload["seed"]))

            posts_before = len(server.posts)
            gets_before = len(server.gets)
            second_kwargs = self._kwargs(server)
            server.system_stats_mode = "redirect"
            second = generate_comfyui_video(self.workspace, **second_kwargs)
            self.assertTrue(second["cache_hit"])
            self.assertEqual(len(server.posts), posts_before)
            self.assertEqual(len(server.gets), gets_before)
            server.system_stats_mode = "success"
            validated = validate_comfyui_outputs(
                self.workspace,
                **{
                    key: value
                    for key, value in self._kwargs(server).items()
                    if key
                    not in {
                        "output_roots",
                        "expected_cache_key",
                        "base_url",
                        "request_timeout_seconds",
                        "generation_timeout_seconds",
                        "poll_interval_seconds",
                    }
                },
            )
            self.assertTrue(validated["cache_hit"])

            public = comfyui_public_result(
                first,
                expected_cache_key=first["cache_key"],
                expected_prompt_sha256=first["prompt_sha256"],
                expected_seed=self.payload["seed"],
                artifacts=first["artifacts"],
                cache_hit=False,
            )
            self.assertNotIn("prompt", public)
            self.assertEqual(public["seed"], self.payload["seed"])
            self.assertEqual(public["seed_decimal"], str(self.payload["seed"]))

    def test_expected_cache_key_rejects_invalid_mismatch_and_resume_before_io(
        self,
    ) -> None:
        with _mock_server() as server:
            invalid = self._kwargs(server)
            invalid["expected_cache_key"] = "not-a-sha256"
            mismatch = self._kwargs(server)
            mismatch["expected_cache_key"] = "A" * 64
            with (
                mock.patch.object(
                    comfyui_module,
                    "_validate_cache",
                    side_effect=AssertionError("cache must not be inspected"),
                ),
                mock.patch.object(
                    comfyui_module,
                    "_verify_model_digests",
                    side_effect=AssertionError("models must not be hashed"),
                ),
            ):
                for kwargs in (invalid, mismatch):
                    with self.subTest(expected=kwargs["expected_cache_key"]):
                        with self.assertRaises(ComfyUIValidationError) as raised:
                            generate_comfyui_video(self.workspace, **kwargs)
                        self.assertEqual(raised.exception.code, "cache_key_mismatch")
                with self.assertRaises(ComfyUIValidationError) as raised:
                    resume_comfyui_video(
                        self.workspace,
                        provider_task_id=PROMPT_ID,
                        **mismatch,
                    )
                self.assertEqual(raised.exception.code, "cache_key_mismatch")
            self.assertEqual(server.gets, [])
            self.assertEqual(server.posts, [])
            self.assertFalse(self._marker().exists())

    def test_tool_identity_drift_after_enqueue_fails_before_side_effects(self) -> None:
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            queued_key = kwargs["expected_cache_key"]
            changed_identity = resolve_comfyui_tool_identity(ffprobe=self.ffprobe)
            changed_identity = {
                **changed_identity,
                "version": changed_identity["version"] + " changed-after-enqueue",
            }
            with (
                mock.patch.object(
                    comfyui_module,
                    "resolve_comfyui_tool_identity",
                    return_value=changed_identity,
                ),
                mock.patch.object(
                    comfyui_module,
                    "_validate_cache",
                    side_effect=AssertionError("cache must not be inspected"),
                ),
                mock.patch.object(
                    comfyui_module,
                    "_verify_model_digests",
                    side_effect=AssertionError("models must not be hashed"),
                ),
            ):
                with self.assertRaises(ComfyUIValidationError) as raised:
                    generate_comfyui_video(self.workspace, **kwargs)
            self.assertEqual(raised.exception.code, "cache_key_mismatch")
            self.assertEqual(kwargs["expected_cache_key"], queued_key)
            self.assertEqual(server.gets, [])
            self.assertEqual(server.posts, [])
            self.assertFalse(self._marker().exists())

    def test_callback_gap_is_recoverable_and_resume_does_not_post(self) -> None:
        with _mock_server() as server:
            def callback(_prompt_id: str) -> None:
                raise RuntimeError("simulated database crash window")

            with self.assertRaises(ComfyUISubmissionPersistenceError):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    on_provider_task_id=callback,
                )
            self.assertTrue(self._marker().is_file())
            recovered = recover_comfyui_prompt_id(
                self.workspace,
                production_id="PROD_COMFY_TEST",
                run_id="RUN_COMFY_TEST",
                cache_key=self._cache_key(),
                payload_digest=comfyui_payload_digest(self.payload),
            )
            self.assertEqual(recovered, PROMPT_ID)
            prompt_posts = len([item for item in server.posts if item["path"] == "/prompt"])

            resumed_callback = mock.Mock(side_effect=AssertionError("must not run"))
            result = resume_comfyui_video(
                self.workspace,
                provider_task_id=recovered,
                **self._kwargs(server),
                on_provider_task_id=resumed_callback,
            )
            self.assertFalse(result["cache_hit"])
            self.assertEqual(
                len([item for item in server.posts if item["path"] == "/prompt"]),
                prompt_posts,
            )
            resumed_callback.assert_not_called()
            self.assertFalse(self._marker().exists())

    def test_terminal_provider_failure_is_fsynced_before_marker_cleanup(self) -> None:
        with _mock_server() as server:
            server.history_mode = "error"
            with self.assertRaises(ComfyUIError) as raised:
                generate_comfyui_video(self.workspace, **self._kwargs(server))
            self.assertEqual(raised.exception.error_code, "comfyui_generation_failed")
            marker = json.loads(self._marker().read_text(encoding="utf-8"))
            self.assertEqual(marker["prompt_id"], PROMPT_ID)
            self.assertEqual(marker["terminal_state"], "failed")
            identity = {
                "production_id": "PROD_COMFY_TEST",
                "run_id": "RUN_COMFY_TEST",
                "cache_key": self._cache_key(),
                "payload_digest": comfyui_payload_digest(self.payload),
                "provider_task_id": PROMPT_ID,
            }
            self.assertEqual(
                recover_comfyui_terminal_state(self.workspace, **identity),
                "failed",
            )
            self.assertTrue(
                cleanup_comfyui_submission_marker(self.workspace, **identity)
            )
            self.assertFalse(self._marker().exists())

    def test_preissued_prompt_id_is_durable_before_an_ambiguous_post(self) -> None:
        with _mock_server() as server:
            server.prompt_mode = "redirect"
            with self.assertRaises(ComfyUISubmissionUnknown):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    prepared_prompt_id=PROMPT_ID,
                )
            marker = json.loads(self._marker().read_text(encoding="utf-8"))
            self.assertEqual(marker["prompt_id"], PROMPT_ID)
            prompt_post = next(
                item for item in server.posts if item["path"] == "/prompt"
            )
            self.assertEqual(prompt_post["json"]["prompt_id"], PROMPT_ID)
            self.assertEqual(
                recover_comfyui_prompt_id(
                    self.workspace,
                    production_id="PROD_COMFY_TEST",
                    run_id="RUN_COMFY_TEST",
                    cache_key=self._cache_key(),
                    payload_digest=comfyui_payload_digest(self.payload),
                ),
                PROMPT_ID,
            )

    def test_preissued_prompt_id_rejects_a_rewritten_provider_response(self) -> None:
        prepared_prompt_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        with _mock_server() as server:
            with self.assertRaises(ComfyUISubmissionUnknown):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    prepared_prompt_id=prepared_prompt_id,
                )
            marker = json.loads(self._marker().read_text(encoding="utf-8"))
            self.assertEqual(marker["prompt_id"], prepared_prompt_id)
            self.assertEqual(
                [item for item in server.posts if item["path"] == "/prompt"][0][
                    "json"
                ]["prompt_id"],
                prepared_prompt_id,
            )

    def test_marker_cleanup_cannot_remove_another_run_marker(self) -> None:
        marker = self._marker()
        marker.parent.mkdir(parents=True, exist_ok=True)
        payload_digest = comfyui_payload_digest(self.payload)
        comfyui_module._create_marker(
            marker,
            comfyui_module._marker_body(
                production_id="PROD_COMFY_TEST",
                run_id="RUN_COMFY_FOREIGN",
                cache_key=self._cache_key(),
                payload_digest=payload_digest,
                prompt_id=PROMPT_ID,
                queue_number=7,
            ),
        )
        removed = comfyui_module._remove_marker_if_owned(
            marker,
            production_id="PROD_COMFY_TEST",
            run_id="RUN_COMFY_TEST",
            cache_key=self._cache_key(),
            payload_digest=payload_digest,
            prompt_id=PROMPT_ID,
        )
        self.assertFalse(removed)
        self.assertTrue(marker.is_file())
        self.assertTrue(
            comfyui_module._remove_marker_if_owned(
                marker,
                production_id="PROD_COMFY_TEST",
                run_id="RUN_COMFY_FOREIGN",
                cache_key=self._cache_key(),
                payload_digest=payload_digest,
                prompt_id=PROMPT_ID,
            )
        )
        self.assertFalse(marker.exists())

    def test_provider_observation_is_read_only_and_distinguishes_not_found(self) -> None:
        with _mock_server() as server:
            self._kwargs(server)
            running = observe_comfyui_submission(
                self.workspace,
                provider_task_id=PROMPT_ID,
                base_url=server.url,
            )
            self.assertEqual(running["state"], "provider_running")
            self.assertEqual(running["provider_status"], "in_progress")
            self.assertEqual(server.posts, [])

            server.job_status = "completed"
            completed = observe_comfyui_submission(
                self.workspace,
                provider_task_id=PROMPT_ID,
                base_url=server.url,
            )
            self.assertEqual(completed["state"], "complete_recoverable")

            server.job_status = "not_found"
            missing = observe_comfyui_submission(
                self.workspace,
                provider_task_id=PROMPT_ID,
                base_url=server.url,
            )
            self.assertEqual(missing["state"], "ambiguous")
            self.assertTrue(missing["duplicate_submission_blocked"])
            self.assertEqual(server.posts, [])

    def test_public_provider_cancel_targets_exact_uuid_without_prompt_post(self) -> None:
        with _mock_server() as server:
            self._kwargs(server)
            accepted = request_comfyui_provider_cancel(
                self.workspace,
                provider_task_id=PROMPT_ID,
                base_url=server.url,
            )
            self.assertTrue(accepted)
            self.assertEqual(server.job_cancel_requests, [PROMPT_ID])
            self.assertEqual(
                server.posts,
                [
                    {
                        "path": f"/api/jobs/{PROMPT_ID}/cancel",
                        "json": {},
                    }
                ],
            )
            self.assertFalse(
                any(item["path"] == "/prompt" for item in server.posts)
            )

    def test_resume_rechecks_live_runtime_before_history(self) -> None:
        with _mock_server() as server:
            def callback_gap(_prompt_id: str) -> None:
                raise RuntimeError("callback gap")

            with self.assertRaises(ComfyUISubmissionPersistenceError):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    on_provider_task_id=callback_gap,
                )
            self.assertTrue(self._marker().is_file())
            prompt_posts = len(
                [item for item in server.posts if item["path"] == "/prompt"]
            )
            history_reads = len(
                [path for path in server.gets if path.startswith("/history/")]
            )
            kwargs = self._kwargs(server)
            server.system_stats["system"]["pytorch_version"] = "2.12.0"
            with self.assertRaises(ComfyUIError) as raised:
                resume_comfyui_video(
                    self.workspace,
                    provider_task_id=PROMPT_ID,
                    **kwargs,
                )
            self.assertEqual(raised.exception.error_code, "invalid_comfyui_runtime")
            self.assertEqual(
                len([item for item in server.posts if item["path"] == "/prompt"]),
                prompt_posts,
            )
            self.assertEqual(
                len([path for path in server.gets if path.startswith("/history/")]),
                history_reads,
            )
            self.assertTrue(self._marker().is_file())

    def _assert_ambiguous_prompt_response_blocks_duplicate(self, mode: str) -> None:
        with _mock_server() as server:
            server.prompt_mode = mode
            with self.assertRaises(ComfyUISubmissionUnknown):
                generate_comfyui_video(self.workspace, **self._kwargs(server))
            self.assertTrue(self._marker().is_file())
            posts_before = len(server.posts)
            server.prompt_mode = "success"
            with self.assertRaises(ComfyUISubmissionUnknown):
                generate_comfyui_video(self.workspace, **self._kwargs(server))
            self.assertEqual(len(server.posts), posts_before)

    def test_redirect_response_blocks_duplicate_submission(self) -> None:
        self._assert_ambiguous_prompt_response_blocks_duplicate("redirect")

    def test_oversize_response_blocks_duplicate_submission(self) -> None:
        self._assert_ambiguous_prompt_response_blocks_duplicate("oversize")

    def test_cancellation_queues_delete_and_keeps_marker(self) -> None:
        cancel = threading.Event()
        with _mock_server() as server:
            with self.assertRaisesRegex(ComfyUIError, "cancelled"):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    cancel_event=cancel,
                    on_provider_task_id=lambda _prompt_id: cancel.set(),
                )
            self.assertEqual(server.job_cancel_requests, [PROMPT_ID])
            self.assertEqual(server.queue_requests, [])
            self.assertTrue(self._marker().is_file())

    def test_studio_shutdown_suspends_polling_without_deleting_provider_task(self) -> None:
        suspend = JobExecutionContext("job_restart_recovery")
        with _mock_server() as server:
            with self.assertRaises(JobCancelled):
                generate_comfyui_video(
                    self.workspace,
                    **self._kwargs(server),
                    cancel_event=suspend,
                    on_provider_task_id=lambda _prompt_id: suspend.set_for_shutdown(),
                )
            self.assertEqual(server.queue_requests, [])
            self.assertEqual(server.job_cancel_requests, [])
            self.assertTrue(suspend.preserve_provider_task)
            self.assertTrue(self._marker().is_file())

    def test_provider_output_traversal_is_rejected_and_source_is_preserved(self) -> None:
        source_hash = _sha256_bytes(self.source_output.read_bytes())
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            server.output_metadata = {
                "filename": "generated_00001_.mp4",
                "subfolder": "../provider/job",
                "type": "output",
            }
            with self.assertRaises(ComfyUIMediaError):
                generate_comfyui_video(self.workspace, **kwargs)
        self.assertEqual(_sha256_bytes(self.source_output.read_bytes()), source_hash)
        self.assertTrue(self.source_output.is_file())
        self.assertTrue(self._marker().is_file())

    def test_unrelated_existing_mp4_is_not_accepted_as_provider_output(self) -> None:
        unrelated = self.output_root / "unrelated" / "generated_00001_.mp4"
        unrelated.parent.mkdir(parents=True)
        shutil.copyfile(self.media_template, unrelated)
        unrelated_hash = _sha256_bytes(unrelated.read_bytes())
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            server.output_metadata = {
                "filename": unrelated.name,
                "subfolder": "unrelated",
                "type": "output",
            }
            with self.assertRaisesRegex(ComfyUIMediaError, "submitted prefix"):
                generate_comfyui_video(self.workspace, **kwargs)
        self.assertEqual(_sha256_bytes(unrelated.read_bytes()), unrelated_hash)
        self.assertTrue(self._marker().is_file())

    def test_wrong_basename_inside_expected_subfolder_is_rejected(self) -> None:
        wrong = self.source_output.with_name("other_00001_.mp4")
        shutil.copyfile(self.media_template, wrong)
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            server.output_metadata = {
                "filename": wrong.name,
                "subfolder": self.provider_subfolder,
                "type": "output",
            }
            with self.assertRaisesRegex(ComfyUIMediaError, "submitted prefix"):
                generate_comfyui_video(self.workspace, **kwargs)
        self.assertTrue(wrong.is_file())
        self.assertTrue(self._marker().is_file())

    def test_live_runtime_mismatch_or_redirect_fails_before_prompt(self) -> None:
        variants = (
            "version",
            "output",
            "shape",
            "redirect",
            "custom_nodes_missing",
            "custom_nodes_extra",
            "base_directory_split",
            "base_directory_equals",
            "models_directory_split",
            "models_directory_equals",
            "extra_models_split",
            "extra_models_equals",
            "unknown_flag",
            "equals_form",
            "duplicate_flag",
            "novram",
            "cpu_vae",
            "ipv6_listen",
        )
        for variant in variants:
            with self.subTest(variant=variant), _mock_server() as server:
                kwargs = self._kwargs(server)
                if variant == "version":
                    server.system_stats["system"]["comfyui_version"] = "0.30.0"
                elif variant == "output":
                    wrong_output = self.workspace / "wrong-output"
                    wrong_output.mkdir(exist_ok=True)
                    argv = server.system_stats["system"]["argv"]
                    argv[argv.index("--output-directory") + 1] = str(wrong_output)
                elif variant == "shape":
                    server.system_stats = {"system": []}
                elif variant == "redirect":
                    server.system_stats_mode = "redirect"
                elif variant == "custom_nodes_missing":
                    server.system_stats["system"]["argv"].remove(
                        "--disable-all-custom-nodes"
                    )
                elif variant == "custom_nodes_extra":
                    whitelist = server.system_stats["system"]["argv"].index(
                        "ComfyUI-GGUF"
                    )
                    server.system_stats["system"]["argv"].insert(
                        whitelist + 1, "ComfyUI-MiniMax-H3-Turbo"
                    )
                elif variant == "base_directory_split":
                    server.system_stats["system"]["argv"].extend(
                        ["--base-directory", str(self.workspace)]
                    )
                elif variant == "base_directory_equals":
                    server.system_stats["system"]["argv"].append(
                        f"--base-directory={self.workspace}"
                    )
                elif variant == "models_directory_split":
                    server.system_stats["system"]["argv"].extend(
                        ["--models-directory", str(self.workspace / "models")]
                    )
                elif variant == "models_directory_equals":
                    server.system_stats["system"]["argv"].append(
                        f"--models-directory={self.workspace / 'models'}"
                    )
                elif variant == "extra_models_split":
                    server.system_stats["system"]["argv"].extend(
                        ["--extra-model-paths-config", "extra_model_paths.yaml"]
                    )
                elif variant == "extra_models_equals":
                    server.system_stats["system"]["argv"].append(
                        "--extra-model-paths-config=extra_model_paths.yaml"
                    )
                elif variant == "unknown_flag":
                    server.system_stats["system"]["argv"].append("--reserve-vram")
                elif variant == "equals_form":
                    argv = server.system_stats["system"]["argv"]
                    listen = argv.index("--listen")
                    argv[listen : listen + 2] = ["--listen=127.0.0.1"]
                elif variant == "duplicate_flag":
                    server.system_stats["system"]["argv"].append(
                        "--disable-pinned-memory"
                    )
                elif variant == "novram":
                    server.system_stats["system"]["argv"].append("--novram")
                elif variant == "cpu_vae":
                    server.system_stats["system"]["argv"].append("--cpu-vae")
                else:
                    argv = server.system_stats["system"]["argv"]
                    argv[argv.index("127.0.0.1")] = "::1"
                with self.assertRaises(ComfyUIError) as raised:
                    generate_comfyui_video(self.workspace, **kwargs)
                self.assertEqual(
                    raised.exception.error_code, "invalid_comfyui_runtime"
                )
                self.assertEqual(
                    [item for item in server.posts if item["path"] == "/prompt"],
                    [],
                )
                self.assertFalse(self._marker().exists())

    def test_live_runtime_accepts_only_the_alternate_canonical_browser_mode(
        self,
    ) -> None:
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            server.system_stats["system"]["argv"][-1] = "--auto-launch"
            result = generate_comfyui_video(self.workspace, **kwargs)
        manifest = json.loads(
            (self.workspace / result["output_directory"] / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["provider_runtime"]["argv"]["browser_mode"], "auto_launch"
        )

    def test_loopback_requests_never_discover_environment_proxy(self) -> None:
        with _mock_server() as server, mock.patch(
            "urllib.request.getproxies",
            side_effect=AssertionError("environment proxy discovery is forbidden"),
        ):
            result = generate_comfyui_video(
                self.workspace, **self._kwargs(server)
            )
        self.assertFalse(result["cache_hit"])

    def test_tampered_cache_fails_without_resubmission(self) -> None:
        with _mock_server() as server:
            first = generate_comfyui_video(self.workspace, **self._kwargs(server))
            generated = self.workspace / next(
                item["path"]
                for item in first["artifacts"]
                if item["name"] == "generated-video.mp4"
            )
            with generated.open("ab") as handle:
                handle.write(b"tamper")
            prompt_posts = len([item for item in server.posts if item["path"] == "/prompt"])
            with self.assertRaisesRegex(ComfyUIError, "integrity"):
                generate_comfyui_video(self.workspace, **self._kwargs(server))
            self.assertEqual(
                len([item for item in server.posts if item["path"] == "/prompt"]),
                prompt_posts,
            )

    def test_cache_hit_skips_physical_model_rehash(self) -> None:
        with _mock_server() as server:
            generate_comfyui_video(self.workspace, **self._kwargs(server))
            with mock.patch.object(
                comfyui_module,
                "_verify_model_digests",
                side_effect=AssertionError("cache hit must not hash models"),
            ) as verifier:
                cached = generate_comfyui_video(
                    self.workspace, **self._kwargs(server)
                )
            self.assertTrue(cached["cache_hit"])
            verifier.assert_not_called()

    def test_same_size_model_rewrite_with_restored_mtime_is_rehashed(self) -> None:
        class _ForbiddenCrossJobCache(dict[object, object]):
            def get(self, *_args: object, **_kwargs: object) -> object:
                raise AssertionError("Windows must not read the model hash cache")

            def __setitem__(self, _key: object, _value: object) -> None:
                raise AssertionError("Windows must not write the model hash cache")

        with _mock_server() as server:
            generate_comfyui_video(self.workspace, **self._kwargs(server))
            role = next(iter(self.model_specs))
            model_path = self.workspace / self.model_specs[role]["relative_path"]
            before = model_path.stat()
            original = model_path.read_bytes()
            replacement = bytes([original[0] ^ 0xFF]) + original[1:]
            self.assertEqual(len(replacement), len(original))
            model_path.write_bytes(replacement)
            os.utime(
                model_path,
                ns=(before.st_atime_ns, before.st_mtime_ns),
            )
            self.assertEqual(model_path.stat().st_size, before.st_size)
            self.assertEqual(model_path.stat().st_mtime_ns, before.st_mtime_ns)

            kwargs = self._kwargs(server)
            kwargs["payload"] = {**self.payload, "seed": self.payload["seed"] + 1}
            kwargs["expected_cache_key"] = self._cache_key(kwargs["payload"])
            prompt_posts = len(
                [item for item in server.posts if item["path"] == "/prompt"]
            )
            cache_boundary = (
                mock.patch.object(
                    comfyui_module,
                    "_MODEL_HASH_CACHE",
                    _ForbiddenCrossJobCache(),
                )
                if os.name == "nt"
                else contextlib.nullcontext()
            )
            with cache_boundary:
                with self.assertRaisesRegex(ComfyUIValidationError, "digest"):
                    generate_comfyui_video(self.workspace, **kwargs)
            self.assertEqual(
                len([item for item in server.posts if item["path"] == "/prompt"]),
                prompt_posts,
            )

    @unittest.skipIf(os.name == "nt", "Windows uses share-deny model handles")
    def test_early_model_replacement_during_later_hash_fails_before_post(self) -> None:
        roles = list(self.model_specs)
        first_path = (
            self.workspace / self.model_specs[roles[0]]["relative_path"]
        ).resolve()
        second_path = (
            self.workspace / self.model_specs[roles[1]]["relative_path"]
        ).resolve()
        original_hash = comfyui_module._sha256_file
        replaced = False

        def racing_hash(
            path: Path, *, cancel_event: Any | None = None
        ) -> str:
            nonlocal replaced
            resolved = Path(path).resolve(strict=True)
            if resolved == second_path and not replaced:
                before = first_path.stat()
                original = first_path.read_bytes()
                replacement = first_path.with_name(first_path.name + ".swap")
                replacement.write_bytes(bytes([original[0] ^ 0xFF]) + original[1:])
                os.utime(
                    replacement,
                    ns=(before.st_atime_ns, before.st_mtime_ns),
                )
                os.replace(replacement, first_path)
                replaced = True
            return original_hash(resolved, cancel_event=cancel_event)

        with _mock_server() as server, mock.patch.object(
            comfyui_module, "_sha256_file", side_effect=racing_hash
        ):
            with self.assertRaises(ComfyUIValidationError) as raised:
                generate_comfyui_video(self.workspace, **self._kwargs(server))
            self.assertEqual(raised.exception.code, "input_changed")
            self.assertTrue(replaced)
            self.assertEqual(
                [item for item in server.posts if item["path"] == "/prompt"], []
            )
            self.assertFalse(self._marker().exists())

    @unittest.skipUnless(os.name == "nt", "Win32 share semantics are required")
    def test_windows_model_guards_block_write_and_replace_through_publish(
        self,
    ) -> None:
        role = next(iter(self.model_specs))
        model_path = self.workspace / self.model_specs[role]["relative_path"]
        replacement = model_path.with_name(model_path.name + ".replacement")
        replacement.write_bytes(model_path.read_bytes())
        original_publish = comfyui_module._publish
        blocked: list[str] = []

        def guarded_publish(stage: Path, cache_directory: Path) -> None:
            with self.assertRaises(OSError):
                with model_path.open("r+b") as handle:
                    handle.write(b"x")
            blocked.append("write")
            with self.assertRaises(OSError):
                os.replace(replacement, model_path)
            blocked.append("replace")
            original_publish(stage, cache_directory)

        with _mock_server() as server, mock.patch.object(
            comfyui_module, "_publish", side_effect=guarded_publish
        ):
            result = generate_comfyui_video(self.workspace, **self._kwargs(server))
        self.assertFalse(result["cache_hit"])
        self.assertEqual(blocked, ["write", "replace"])
        # The public wrapper releases every guard only after publish and cache
        # revalidation have completed.
        with model_path.open("r+b") as handle:
            original = handle.read(1)
            handle.seek(0)
            handle.write(original)
        os.replace(replacement, model_path)

    @unittest.skipUnless(os.name == "nt", "Win32 share semantics are required")
    def test_windows_model_guards_are_released_after_worker_exception(self) -> None:
        role = next(iter(self.model_specs))
        model_path = self.workspace / self.model_specs[role]["relative_path"]

        def fail_while_guarded(*_args: object, **_kwargs: object) -> dict[str, Any]:
            with self.assertRaises(OSError):
                with model_path.open("r+b") as handle:
                    handle.write(b"x")
            raise ComfyUIError("forced poll failure", code="comfyui_timeout")

        with _mock_server() as server, mock.patch.object(
            comfyui_module, "_poll_history", side_effect=fail_while_guarded
        ):
            with self.assertRaisesRegex(ComfyUIError, "forced poll failure"):
                generate_comfyui_video(self.workspace, **self._kwargs(server))
        with model_path.open("r+b") as handle:
            original = handle.read(1)
            handle.seek(0)
            handle.write(original)

    def test_tool_identity_change_after_model_hash_fails_before_post(self) -> None:
        initial_identity = resolve_comfyui_tool_identity(ffprobe=self.ffprobe)
        changed_identity = {
            **initial_identity,
            "version": initial_identity["version"] + " changed-during-hash",
        }
        with _mock_server() as server:
            kwargs = self._kwargs(server)
            with mock.patch.object(
                comfyui_module,
                "resolve_comfyui_tool_identity",
                side_effect=[initial_identity, changed_identity],
            ):
                with self.assertRaises(ComfyUIValidationError) as raised:
                    generate_comfyui_video(self.workspace, **kwargs)
            self.assertEqual(raised.exception.code, "cache_key_mismatch")
            self.assertEqual(
                [item for item in server.posts if item["path"] == "/prompt"], []
            )
            self.assertFalse(self._marker().exists())

    def test_workflow_and_model_preflight_tamper_before_http(self) -> None:
        with _mock_server() as server:
            bad_models = copy.deepcopy(self.model_files)
            role = next(iter(bad_models))
            bad_models[role]["bytes"] += 1
            kwargs = self._kwargs(server)
            kwargs["model_files"] = bad_models
            with self.assertRaises(ComfyUIValidationError):
                generate_comfyui_video(self.workspace, **kwargs)
            self.assertEqual(server.posts, [])

            tampered_workflow = copy.deepcopy(self.workflow)
            tampered_workflow["105:9"]["inputs"]["steps"] = 99
            kwargs = self._kwargs(server)
            kwargs["workflow"] = tampered_workflow
            with self.assertRaises(ComfyUIValidationError):
                generate_comfyui_video(self.workspace, **kwargs)
            self.assertEqual(server.posts, [])


if __name__ == "__main__":
    unittest.main()

"""Isolated admission/cache guards. Never opens the real Studio database."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("illustrated_produce", Path(__file__).resolve().parents[1] / "produce.py")
assert SPEC and SPEC.loader
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
BASE = json.loads((ROOT / "productions/SHORT_20260906_claude_desktop_real_capture/request-brand.json").read_text(encoding="utf-8"))


class IllustratedDriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.workspace_patch = patch.object(driver, "WORKSPACE", self.root)
        self.output_patch = patch.object(driver, "OUTPUT", self.root / "outputs")
        self.workspace_patch.start()
        self.output_patch.start()
        self.addCleanup(self.workspace_patch.stop)
        self.addCleanup(self.output_patch.stop)
        recipe = copy.deepcopy(BASE["recipe"])
        for index in (0, 2):
            recipe["scenes"][index].update(video_artifact_id=driver.PLACEHOLDER, start_ms=0, end_ms=7000)
            recipe["scenes"][index].pop("focus_region", None)
        self.manifest = {
            "schema_version": 1, "policy": driver.INPUT_POLICY,
            "files": [self.record("image.png", "illustration"), self.record("renderer.mjs", "renderer")],
            "panels": [self.record("hook.mp4", "hook"), self.record("cta.mp4", "cta")],
            "recipe": recipe, "metadata": copy.deepcopy(BASE["metadata"]),
        }

    def record(self, name, role):
        path = self.root / name
        data = f"isolated fixture {name}".encode()
        path.write_bytes(data)
        return {"role": role, "path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest().upper()}

    def assert_code(self, code, callback):
        with self.assertRaises(driver.DriverError) as caught:
            callback()
        self.assertEqual(caught.exception.code, code)

    def test_valid_manifest_preserves_exact_voice_and_capture(self):
        value = driver.validate_manifest(self.manifest)
        self.assertEqual(value["recipe"]["scenes"][1]["video_artifact_id"], driver.CAPTURE_ID)
        self.assertEqual([item["narration"] for item in value["recipe"]["scenes"]], list(driver.NARRATIONS))
        self.assertEqual(value["recipe"]["voice"], "Microsoft Sayaka")

    def test_source_digest_change_fails_closed(self):
        (self.root / "image.png").write_bytes(b"replacement image")
        self.assert_code("input_file_changed", lambda: driver.validate_manifest(self.manifest))

    def test_manifest_requires_one_image_and_renderer(self):
        self.manifest["files"][1]["role"] = "renderer_dependency"
        self.assert_code("ambiguous_illustration_sources", lambda: driver.validate_manifest(self.manifest))

    def test_manifest_forbids_new_settings_or_provider_knobs(self):
        self.manifest["generate_voice"] = True
        self.assert_code("invalid_illustration_manifest", lambda: driver.validate_manifest(self.manifest))

    def test_scene_and_voice_invariants(self):
        for field, value in (("voice", "Microsoft Haruka Desktop"), ("rate", 1), ("screen_theme", "claude_code_v1")):
            with self.subTest(field=field):
                modified = copy.deepcopy(self.manifest)
                modified["recipe"][field] = value
                self.assert_code("approved_recipe_settings_required", lambda: driver.validate_manifest(modified))

    def test_script_trim_source_and_volume_invariants(self):
        changes = ((0, "narration", "新しい音声です。"), (1, "video_artifact_id", driver.PLACEHOLDER),
                   (1, "start_ms", 14900), (0, "volume_percent", 100))
        for index, field, value in changes:
            with self.subTest(field=field):
                modified = copy.deepcopy(self.manifest)
                modified["recipe"]["scenes"][index][field] = value
                self.assert_code("approved_scene_sources_and_voice_required", lambda: driver.validate_manifest(modified))

    def test_panels_cannot_be_zoomed_or_role_duplicated(self):
        modified = copy.deepcopy(self.manifest)
        modified["recipe"]["scenes"][0]["focus_region"] = {"x": .1, "y": .1, "width": .8, "height": .8}
        self.assert_code("approved_scene_sources_and_voice_required", lambda: driver.validate_manifest(modified))
        self.manifest["panels"][1]["role"] = "hook"
        self.assert_code("ambiguous_panels", lambda: driver.validate_manifest(self.manifest))

    def test_outside_workspace_path_rejected(self):
        self.manifest["files"][0]["path"] = str(self.root.parent / "unrelated.png")
        self.assert_code("path_outside_workspace", lambda: driver.validate_manifest(self.manifest))

    def test_duplicate_and_nonfinite_json_rejected(self):
        path = self.root / "input.json"
        path.write_text('{"a":1,"a":2}', encoding="utf-8")
        self.assert_code("duplicate_json_key", lambda: driver.read_json(path))
        path.write_text('{"a":NaN}', encoding="utf-8")
        self.assert_code("non_finite_json", lambda: driver.read_json(path))

    def test_immutable_output_is_retryable_but_not_replaceable(self):
        target = driver.OUTPUT / "checkpoint.json"
        driver.write_json(target, {"id": 1}, immutable=True)
        driver.write_json(target, {"id": 1}, immutable=True)
        self.assert_code("immutable_output_changed", lambda: driver.write_json(target, {"id": 2}, immutable=True))

    def test_interrupted_write_is_not_overwritten(self):
        driver.OUTPUT.mkdir()
        target = driver.OUTPUT / "checkpoint.json"
        target.with_name(target.name + ".writing").write_bytes(b"unreconciled")
        with self.assertRaises(FileExistsError):
            driver.write_json(target, {"id": 1})
        self.assertFalse(target.exists())

    def test_panel_probe_requires_exact_silent_format(self):
        valid = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                               "avg_frame_rate": "24/1", "nb_frames": "168"}], "format": {"duration": "7.000000"}}
        driver.validate_panel_probe(valid)
        for field, value in (("nb_frames", "169"), ("avg_frame_rate", "30/1"), ("width", 1080)):
            changed = copy.deepcopy(valid)
            changed["streams"][0][field] = value
            self.assert_code("panel_must_be_7s_1080p24_h264", lambda: driver.validate_panel_probe(changed))
        valid["streams"].append({"codec_type": "audio"})
        self.assert_code("silent_single_video_panel_required", lambda: driver.validate_panel_probe(valid))

    def test_missing_or_changed_voice_cache_never_submits(self):
        service = Mock()
        service._cached_local_narration_result.return_value = None
        progress = driver.ProgressService(service, driver.OUTPUT)
        self.assert_code("existing_voice_cache_required_no_resynthesis", lambda: progress.execute_announcement_recipe("p", "r", {}))
        service.execute_announcement_recipe.assert_not_called()
        service._cached_local_narration_result.return_value = {"artifacts": []}
        self.assert_code("narration_artifact_identity_changed", lambda: driver.require_voice_cache(service))

    def test_same_existing_voice_artifacts_required(self):
        result = {"cache_hit": True, "artifacts": [{"name": name, "id": value} for name, value in driver.NARRATION_IDS.items()]}
        self.assertEqual(driver.narration_artifacts(result), driver.NARRATION_IDS)
        result["artifacts"][0]["id"] = driver.PLACEHOLDER
        self.assert_code("narration_artifact_identity_changed", lambda: driver.narration_artifacts(result))

    def test_import_uses_real_api_and_verifies_hash(self):
        record = self.manifest["panels"][0]
        service = Mock()
        artifact = {"id": "art_" + "1" * 32, "production_id": driver.PRODUCTION_ID,
                    "sha256": record["sha256"], "bytes": record["bytes"]}
        service.import_production_video.return_value = {"artifact": artifact, "deduplicated": False}
        self.assertEqual(driver.import_panel(service, record)["artifact"], artifact)
        call = service.import_production_video.call_args
        self.assertEqual(call.args, (driver.PRODUCTION_ID,))
        self.assertEqual(call.kwargs["filename_header"], "hook.mp4")
        self.assertEqual(call.kwargs["content_type"], "video/mp4")
        artifact["sha256"] = "0" * 64
        self.assert_code("imported_panel_identity_changed", lambda: driver.import_panel(service, record))


if __name__ == "__main__":
    unittest.main()

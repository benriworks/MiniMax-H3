from __future__ import annotations

from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import h3_api
from tools import h3_compare as comparison


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "comparison"
        comparison.initialize(self.directory, trials=2)
        self.manifest, self.suite = comparison.load_run(self.directory)
        self.case = self.suite["cases"][0]
        self.key = "fetch-01-api"

    def invoke_api(self, client, **kwargs):
        with mock.patch.object(comparison, "new_api_client", return_value=client):
            return comparison.run_api(self.directory, self.manifest, self.suite, self.case, self.key,
                                      confirm=kwargs.get("confirm", True), wait_timeout=10, ffprobe="ffprobe")

    def client(self):
        client = mock.Mock(api_base=h3_api.DEFAULT_API_BASE)
        client.submit.return_value = {"task_id": "task-123"}
        client.status.return_value = {"task": {"status": "running"}}
        return client

    def test_freezes_inputs_and_rejects_changes_or_overwrite(self):
        self.assertIsNone(self.manifest["cost"]["actual_api_cost"])
        self.assertFalse(self.manifest["user_adopted"])
        with self.assertRaises(FileExistsError):
            comparison.initialize(self.directory)
        (self.directory / "suite.json").write_text("{}")
        with self.assertRaisesRegex(comparison.ComparisonError, "suite changed"):
            comparison.load_run(self.directory)

    def test_cost_is_explicit_estimate_for_all_cases_and_trials(self):
        other = Path(self.temp.name) / "priced"
        comparison.initialize(other, trials=3, price=0.1)
        cost = comparison.load_run(other)[0]["cost"]
        self.assertEqual(cost["estimated_api_total"], 4.5)
        self.assertIsNone(cost["actual_api_cost"])
        for price in (float("nan"), float("inf"), -1):
            with self.assertRaises(comparison.ComparisonError):
                comparison.initialize(other, price=price)

    def test_invalid_suite_fails_before_directory_creation(self):
        suite = json.loads(json.dumps(self.suite))
        for field,value in (("duration_seconds", 10), ("ratio", "16:9"), ("local_seed", True)):
            bad = dict(suite, **{field:value})
            with self.assertRaises(comparison.ComparisonError):
                comparison.validate_suite(bad)
        suite["cases"][0]["id"] = "../outside"
        with self.assertRaises(comparison.ComparisonError):
            comparison.validate_suite(suite)

    def test_api_acknowledgement_before_any_post(self):
        client = self.client()
        with self.assertRaisesRegex(comparison.ComparisonError, "billable"):
            self.invoke_api(client, confirm=False)
        client.submit.assert_not_called()

    def test_ambiguous_post_is_durable_and_never_retried(self):
        client = self.client()
        def failure(_):
            saved = comparison.read_json(self.directory / "manifest.json")
            self.assertEqual(saved["jobs"][self.key]["state"], "submission_unknown")
            raise h3_api.H3APIError("transport failure after acceptance")
        client.submit.side_effect = failure
        with self.assertRaises(h3_api.H3APIError):
            self.invoke_api(client)
        with self.assertRaisesRegex(comparison.ComparisonError, "outcome unknown"):
            self.invoke_api(client)
        self.assertEqual(client.submit.call_count, 1)

    def test_timeout_resumes_same_task_without_second_charge(self):
        client = self.client()
        with mock.patch.object(h3_api, "wait_for_task", side_effect=h3_api.H3TaskError("timed out")) as wait:
            for _ in range(2):
                with self.assertRaises(h3_api.H3TaskError):
                    self.invoke_api(client)
            self.assertEqual(wait.call_args.args[1], "task-123")
        self.assertEqual(client.submit.call_count, 1)
        self.assertEqual(self.manifest["jobs"][self.key]["state"], "submitted")

    def test_failed_task_is_terminal(self):
        client = self.client()
        client.status.return_value = {"task": {"status": "failed", "error": {"message": "test"}}}
        with self.assertRaises(h3_api.H3TaskError):
            self.invoke_api(client)
        self.assertEqual(self.manifest["jobs"][self.key]["state"], "failed")
        with self.assertRaisesRegex(comparison.ComparisonError, "terminal task failed"):
            self.invoke_api(client)
        self.assertEqual(client.submit.call_count, 1)

    def test_endpoint_change_blocks_resume(self):
        client = self.client()
        with mock.patch.object(h3_api, "wait_for_task", side_effect=h3_api.H3TaskError("timed out")):
            with self.assertRaises(h3_api.H3TaskError):
                self.invoke_api(client)
        client.api_base = "https://example.org"
        with self.assertRaisesRegex(comparison.ComparisonError, "base changed"):
            self.invoke_api(client)

    def test_success_keeps_hashes_without_signed_response(self):
        client = self.client()
        def wait(_client, _id, **kwargs):
            output = kwargs["output"]
            output.parent.mkdir(parents=True)
            output.write_bytes(b"video")
            return {"task": {"status": "succeeded", "content": {"url": "https://cdn.test/video?secret=SIGNED"}}}, 5
        with mock.patch.object(h3_api, "wait_for_task", side_effect=wait), mock.patch.object(comparison, "probe_video", return_value={"width": 480}):
            self.invoke_api(client)
            self.invoke_api(client)
        self.assertEqual(client.submit.call_count, 1)
        self.assertNotIn("SIGNED", (self.directory / "manifest.json").read_text())
        self.assertEqual(self.manifest["jobs"][self.key]["artifact"]["sha256"], comparison.digest(b"video"))

    def test_http_submit_query_download_integrates_with_comparison_ledger(self):
        from tests.test_h3_api import mock_server, VIDEO_BYTES
        with mock_server() as server:
            server.statuses = ["succeeded"]
            client = h3_api.H3Client("integration-secret", server.url)
            with mock.patch.object(comparison, "probe_video", return_value={"width":480}):
                self.invoke_api(client)
                self.invoke_api(client)
            self.assertEqual(len(server.posts), 1)
            self.assertEqual(server.posts[0]["json"]["content"][0]["text"], self.case["prompt"])
            self.assertEqual(server.posts[0]["json"]["ratio"], "9:16")
            downloads = [r for r in server.gets if r["path"] == "/video.mp4"]
            self.assertEqual(len(downloads), 1)
            self.assertIsNone(downloads[0]["authorization"])
        saved = (self.directory / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn("integration-secret", saved)
        self.assertNotIn("/video.mp4", saved)
        self.assertEqual(self.manifest["jobs"][self.key]["artifact"]["sha256"], comparison.digest(VIDEO_BYTES))

    def add_pair(self, real_media=False):
        for provider, color in (("api", "red"), ("local", "blue")):
            path = self.directory / "raw" / f"fetch-01-{provider}.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            if real_media:
                comparison.process(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=96x160:r=24:d=5.2", "-f", "lavfi", "-i", "sine=frequency=440:duration=5.2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", path])
                record = comparison.artifact_record(path, self.directory)
            else:
                path.write_bytes(provider.encode())
                with mock.patch.object(comparison, "probe_video", return_value={}):
                    record = comparison.artifact_record(path, self.directory)
            self.manifest["jobs"][f"fetch-01-{provider}"] = {"state": "succeeded", "artifact": record}
        comparison.save_json(self.directory / "manifest.json", self.manifest)

    def test_reviews_are_append_only_and_bound_to_both_hashes(self):
        self.add_pair()
        for score in (2, 4):
            comparison.record_review(self.directory, self.manifest, "fetch", 1, "api", {"action":score}, "tester", "observation")
        self.assertEqual(len(self.manifest["reviews"]), 2)
        self.assertIsNone(self.manifest["reviews"][0]["scores"]["audio"])
        self.assertEqual(set(self.manifest["reviews"][0]["source_sha256"]), {"api", "local"})
        self.assertEqual(self.manifest["human_final_review"], "pending")
        for scores in ({}, {"action":0}, {"made_up":3}, {"action":True}):
            with self.assertRaises(comparison.ComparisonError):
                comparison.record_review(self.directory, self.manifest, "fetch", 1, "api", scores, "tester", "note")
        path = self.directory / "raw/fetch-01-local.mp4"
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(comparison.ComparisonError, "changed"):
            comparison.record_review(self.directory, self.manifest, "fetch", 1, "api", {"action":3}, "tester", "note")

    def test_concurrent_mutation_is_blocked(self):
        with comparison.locked(self.directory):
            with self.assertRaisesRegex(comparison.ComparisonError, "locked"):
                with comparison.locked(self.directory):
                    pass
        self.assertFalse((self.directory / ".comparison.lock").exists())

    def test_cli_redacts_api_key(self):
        output = io.StringIO()
        with mock.patch.dict("os.environ", {"MINIMAX_API_KEY":"test-secret"}), mock.patch.object(comparison, "load_run", side_effect=ValueError("test-secret")), redirect_stderr(output):
            result = comparison.main(["status", str(self.directory)])
        self.assertEqual(result, 1)
        self.assertNotIn("test-secret", output.getvalue())
        self.assertIn("REDACTED", output.getvalue())

    def test_local_resume_delegates_to_existing_guarded_adapter(self):
        from tools.studio import comfyui
        from tools.studio import comfyui_execution as execution
        inputs = {"expected_cache_key":"a"*64}
        task = "01234567-89ab-4cde-8f01-23456789abcd"
        key = "fetch-01-local"
        self.manifest["jobs"][key] = {"state":"prepared", "task_id":task, "cache_key":"a"*64, "elapsed_seconds":0.0}
        with mock.patch.object(comparison, "local_inputs", return_value=inputs), mock.patch.object(comfyui, "recover_comfyui_prompt_id", return_value=task), mock.patch.object(comfyui, "generate_comfyui_video", side_effect=execution.ComfyUISubmissionUnknown()) as generate:
            with self.assertRaises(execution.ComfyUISubmissionUnknown):
                comparison.run_local(self.directory, self.manifest, self.suite, self.case, key, 1, wait_timeout=10, ffprobe="ffprobe")
        self.assertEqual(generate.call_args.kwargs["resume_prompt_id"], task)
        self.assertNotIn("prepared_prompt_id", generate.call_args.kwargs)
        self.assertEqual(generate.call_args.kwargs["payload"]["prompt"], self.case["prompt"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
    def test_real_media_pair_render_decode_diagnostics_and_report(self):
        self.add_pair(real_media=True)
        page = comparison.compare_pair(self.directory, self.manifest, self.suite, "fetch", 1)
        report = comparison.read_json(page.parent / "report.json")
        video = self.directory / report["side_by_side"]["path"]
        probe = comparison.probe_video(video)
        self.assertEqual((probe["width"], probe["height"]), (960,864))
        self.assertAlmostEqual(probe["duration_seconds"], 5, places=1)
        self.assertFalse(probe["has_audio"])
        self.assertEqual(report["quality_winner"], "unmeasured")
        self.assertGreater(report["diagnostics"]["api"]["sampled_frames"], 20)
        self.assertLess(report["diagnostics"]["api"]["mean_luma_difference"], 0.001)
        text = page.read_text(encoding="utf-8")
        self.assertIn("../..", text)
        self.assertIn("原本", text)
        self.assertTrue(page.is_file())
        comparison.record_review(self.directory, self.manifest, "fetch", 1, "api", {"action":2}, "tester", "synthetic test")
        comparison.compare_pair(self.directory, self.manifest, self.suite, "fetch", 1)
        self.assertEqual(len(comparison.read_json(page.parent / "report.json")["reviews"]), 1)
        video.write_bytes(b"corrupt-derived-video")
        with self.assertRaisesRegex(comparison.ComparisonError, "derivative changed"):
            comparison.compare_pair(self.directory, self.manifest, self.suite, "fetch", 1)


if __name__ == "__main__":
    unittest.main()

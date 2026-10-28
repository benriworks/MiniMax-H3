from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tools.studio import cli
from tools.studio.quick_create import QuickCreateError, QuickCreateQcNonPass
from tools.studio.quick_create_project import (
    QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_CHARS,
    QuickCreateProjectValidationError,
    load_quick_create_project_request,
    run_quick_create_project,
    validate_quick_create_project_request,
)
from tools.studio.security import stable_id


PRODUCTION_ID = "production_" + "a" * 32
RECIPE_ID = "announcement_" + "b" * 32


def indexed_recipe(indexes: tuple[int, int, int] = (0, 1, 1)) -> dict[str, object]:
    scenes = []
    for role, index, headline in zip(
        ("hook", "message", "cta"),
        indexes,
        ("新しい体験", "かんたん操作", "今すぐ確認"),
        strict=True,
    ):
        scenes.append(
            {
                "role": role,
                "video_index": index,
                "start_ms": 0,
                "end_ms": 4_000,
                "volume_percent": 0,
                "headline": headline,
                "narration": f"{role} の説明です。",
                "visual_preset": "preserve_v1",
            }
        )
    return {
        "schema_version": 1,
        "name": "新サービス告知",
        "template_preset": "shorts_ja_15s_v1",
        "scenes": scenes,
        "voice": None,
        "rate": 0,
        "pronunciations": [],
        "include_captioned": True,
        "caption_style_preset": "shorts_ja_large_v1",
        "audio_mix_preset": "narration_only_v1",
        "variant": "captioned",
    }


def project_request(
    *,
    videos: list[dict[str, str]] | None = None,
    recipe: dict[str, object] | None = None,
    **updates: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "production": {"id": PRODUCTION_ID, "title": "新規制作"},
        "videos": videos
        if videos is not None
        else [{"path": "first.mp4"}, {"path": "second.mp4"}],
        "recipe_id": RECIPE_ID,
        "expected_revision": 0,
        "recipe": recipe if recipe is not None else indexed_recipe(),
        "timeout_seconds": 30,
    }
    value.update(updates)
    return value


def production_response(*, deduplicated: bool = False) -> dict[str, object]:
    return {
        "schema_version": 1,
        "production": {
            "id": PRODUCTION_ID,
            "title": "新規制作",
            "status": "discovered",
            "technical_status": None,
            "creative_status": None,
            "public_release_status": None,
            "source_rel": None,
            "output_rel": f"outputs/productions/{PRODUCTION_ID}",
            "discovered_at": "2026-08-31T00:00:00Z",
            "refreshed_at": "2026-08-31T00:00:00Z",
        },
        "deduplicated": deduplicated,
    }


def import_response(
    index: int,
    size: int,
    *,
    deduplicated: bool = False,
) -> dict[str, object]:
    digest = f"{index + 1:064X}"
    relative = (
        f"outputs/productions/{PRODUCTION_ID}/imports/"
        f"{digest[:16].lower()}_video{index}.mp4"
    )
    return {
        "schema_version": 1,
        "artifact": {
            "id": stable_id("art", relative.casefold()),
            "production_id": PRODUCTION_ID,
            "rel_path": relative,
            "origin": "output",
            "name": Path(relative).name,
            "kind": "video",
            "media_type": "video/mp4",
            "bytes": size,
            "mtime_ns": 1,
            "sha256": digest,
            "is_heavy": True,
            "available": True,
            "indexed_at": "2026-08-31T00:00:00Z",
            "file_url": "/api/artifacts/example/file",
            "preview_url": "/api/artifacts/example/file",
            "download_url": "/api/artifacts/example/file",
        },
        "deduplicated": deduplicated,
    }


def consuming_service(paths: list[Path], *, retry: bool = False) -> mock.Mock:
    service = mock.Mock()
    service.create_production.return_value = production_response(
        deduplicated=retry
    )
    sizes = [path.stat().st_size for path in paths]
    responses = [
        import_response(index, size, deduplicated=retry)
        for index, size in enumerate(sizes)
    ]

    def consume(_production_id: str, **kwargs: object) -> dict[str, object]:
        stream = kwargs["stream"]
        assert hasattr(stream, "read")
        stream.read()
        return responses.pop(0)

    service.import_production_video.side_effect = consume
    return service


class QuickCreateProjectValidationTests(unittest.TestCase):
    def test_exact_schema_normalizes_and_preserves_integer_indexes(self) -> None:
        normalized = validate_quick_create_project_request(project_request())
        self.assertEqual(normalized["production"]["id"], PRODUCTION_ID)
        self.assertEqual(
            [scene["video_index"] for scene in normalized["recipe"]["scenes"]],
            [0, 1, 1],
        )
        self.assertNotIn(
            "video_artifact_id", normalized["recipe"]["scenes"][0]
        )

    def test_strict_schema_identity_paths_and_unused_videos_fail_closed(self) -> None:
        invalid = [
            {**project_request(), "extra": True},
            project_request(production={"id": PRODUCTION_ID, "title": "T", "x": 1}),
            project_request(production={"id": "production_" + "A" * 32, "title": "T"}),
            project_request(recipe_id="announcement-runtime"),
            project_request(videos=[]),
            project_request(videos=[{"path": "a.mp4"}] * 4),
            project_request(videos=[{"path": ""}], recipe=indexed_recipe((0, 0, 0))),
            project_request(
                videos=[{"path": "C:\\private\\a.mp4"}],
                recipe=indexed_recipe((0, 0, 0)),
            ),
            project_request(videos=[{"path": "../private.mp4"}], recipe=indexed_recipe((0, 0, 0))),
            project_request(
                videos=[{"path": "a.mp4"}, {"path": "b.mp4"}, {"path": "c.mp4"}],
                recipe=indexed_recipe((0, 1, 1)),
            ),
            project_request(recipe=indexed_recipe((0, 1, 2))),
            project_request(
                videos=[{"path": "x" * (QUICK_CREATE_PROJECT_MAX_RELATIVE_PATH_CHARS + 1)}],
                recipe=indexed_recipe((0, 0, 0)),
            ),
        ]
        for value in invalid:
            with self.subTest(value=str(value)[:80]), self.assertRaises(
                QuickCreateProjectValidationError
            ):
                validate_quick_create_project_request(value)

    def test_loader_rejects_duplicate_and_nonfinite_json_without_leak(self) -> None:
        secret = "secret-source-name.mp4"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private-request.json"
            encoded = json.dumps(
                project_request(
                    videos=[{"path": secret}],
                    recipe=indexed_recipe((0, 0, 0)),
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            ).replace('"expected_revision":0', '"expected_revision":0,"expected_revision":0')
            path.write_text(encoded, encoding="utf-8")
            with self.assertRaises(QuickCreateProjectValidationError) as duplicate:
                load_quick_create_project_request(path)
            path.write_text(encoded.replace('"rate":0', '"rate":NaN'), encoding="utf-8")
            with self.assertRaises(QuickCreateProjectValidationError) as nonfinite:
                load_quick_create_project_request(path)
        for error in (duplicate.exception, nonfinite.exception):
            rendered = str(error)
            self.assertNotIn(secret, rendered)
            self.assertNotIn(str(path), rendered)


class QuickCreateProjectExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.parent = Path(self.temporary.name).resolve()
        self.paths = [self.parent / "first.mp4", self.parent / "日本 語.mp4"]
        self.paths[0].write_bytes(b"first-video")
        self.paths[1].write_bytes(b"second-video")
        self.request = project_request(
            videos=[{"path": self.paths[0].name}, {"path": self.paths[1].name}]
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_create_import_order_compile_mapping_and_redacted_output(self) -> None:
        service = consuming_service(self.paths)
        order: list[str] = []
        service.create_production.side_effect = lambda body: (
            order.append("create") or production_response()
        )
        original_import = service.import_production_video.side_effect

        def consume(*args: object, **kwargs: object) -> dict[str, object]:
            order.append("import")
            return original_import(*args, **kwargs)

        service.import_production_video.side_effect = consume
        quick_summary = {"schema_version": 1, "status": "succeeded"}

        def execute(
            selected_service: object,
            request: dict[str, object],
            **kwargs: object,
        ) -> dict[str, object]:
            order.append("quick")
            self.assertIs(selected_service, service)
            self.assertEqual(
                [scene["video_artifact_id"] for scene in request["recipe"]["scenes"]],
                [
                    import_response(0, self.paths[0].stat().st_size)["artifact"]["id"],
                    import_response(1, self.paths[1].stat().st_size)["artifact"]["id"],
                    import_response(1, self.paths[1].stat().st_size)["artifact"]["id"],
                ],
            )
            self.assertEqual(kwargs["deadline"], 31.0)
            return quick_summary

        with mock.patch(
            "tools.studio.quick_create_project.run_quick_create",
            side_effect=execute,
        ):
            result = run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                deadline=50.0,
                monotonic=lambda: 1.0,
                sleep=lambda _seconds: None,
            )

        self.assertEqual(order, ["create", "import", "import", "quick"])
        self.assertEqual(service.import_production_video.call_count, 2)
        second_headers = service.import_production_video.call_args_list[1].kwargs
        self.assertEqual(second_headers["filename_header"], "%E6%97%A5%E6%9C%AC%20%E8%AA%9E.mp4")
        self.assertEqual(second_headers["content_type"], "application/octet-stream")
        self.assertEqual(
            result["production"],
            {"id": PRODUCTION_ID, "title": "新規制作", "deduplicated": False},
        )
        self.assertEqual([item["source_index"] for item in result["videos"]], [0, 1])
        rendered = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("first.mp4", rendered)
        self.assertNotIn("日本 語.mp4", rendered)
        self.assertNotIn("hook の説明", rendered)

    def test_same_request_retry_reports_durable_deduplication(self) -> None:
        service = consuming_service(self.paths, retry=True)
        with mock.patch(
            "tools.studio.quick_create_project.run_quick_create",
            return_value={"schema_version": 1, "status": "succeeded", "job_deduplicated": True},
        ):
            result = run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
                sleep=lambda _seconds: None,
            )
        self.assertTrue(result["production"]["deduplicated"])
        self.assertTrue(all(item["deduplicated"] for item in result["videos"]))
        self.assertFalse(
            any(call[0].startswith("delete") for call in service.method_calls)
        )

    def test_retry_after_partial_import_reuses_production_and_first_video(self) -> None:
        service = mock.Mock()
        service.create_production.side_effect = (
            production_response(),
            production_response(deduplicated=True),
        )
        calls = [0]

        def import_video(
            _production_id: str, **kwargs: object
        ) -> dict[str, object]:
            stream = kwargs["stream"]
            assert hasattr(stream, "read")
            stream.read()
            call = calls[0]
            calls[0] += 1
            if call == 0:
                return import_response(0, self.paths[0].stat().st_size)
            if call == 1:
                raise RuntimeError("private partial failure")
            if call == 2:
                return import_response(
                    0, self.paths[0].stat().st_size, deduplicated=True
                )
            return import_response(1, self.paths[1].stat().st_size)

        service.import_production_video.side_effect = import_video
        with (
            mock.patch(
                "tools.studio.quick_create_project.run_quick_create",
                return_value={"schema_version": 1, "status": "succeeded"},
            ) as execute,
            self.assertRaises(QuickCreateError) as first,
        ):
            run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertEqual(first.exception.code, "quick_create_project_import_failed")
        execute.assert_not_called()

        with mock.patch(
            "tools.studio.quick_create_project.run_quick_create",
            return_value={"schema_version": 1, "status": "succeeded"},
        ):
            retry = run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertTrue(retry["production"]["deduplicated"])
        self.assertEqual(
            [item["deduplicated"] for item in retry["videos"]], [True, False]
        )
        self.assertEqual(service.create_production.call_count, 2)
        self.assertEqual(service.import_production_video.call_count, 4)

    def test_shared_deadline_stops_after_durable_import(self) -> None:
        service = consuming_service(self.paths)
        now = [0.0]
        original = service.import_production_video.side_effect

        def consume(*args: object, **kwargs: object) -> dict[str, object]:
            result = original(*args, **kwargs)
            now[0] = 6.0
            return result

        service.import_production_video.side_effect = consume
        with (
            mock.patch("tools.studio.quick_create_project.run_quick_create") as execute,
            self.assertRaises(QuickCreateError) as raised,
        ):
            run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                deadline=5.0,
                monotonic=lambda: now[0],
            )
        self.assertEqual(raised.exception.code, "quick_create_timeout")
        service.create_production.assert_called_once()
        self.assertEqual(service.import_production_video.call_count, 1)
        execute.assert_not_called()

    def test_unconsumed_or_mutated_file_fails_after_import_without_path(self) -> None:
        service = mock.Mock()
        service.create_production.return_value = production_response()
        service.import_production_video.return_value = import_response(
            0, self.paths[0].stat().st_size
        )
        one_video_request = project_request(
            videos=[{"path": self.paths[0].name}],
            recipe=indexed_recipe((0, 0, 0)),
        )
        with self.assertRaises(QuickCreateProjectValidationError) as raised:
            run_quick_create_project(
                service,
                one_video_request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertEqual(raised.exception.code, "quick_create_project_video_changed")
        self.assertNotIn(str(self.paths[0]), str(raised.exception))

    def test_same_size_file_mutation_is_detected_by_post_import_fstat(self) -> None:
        service = mock.Mock()
        service.create_production.return_value = production_response()
        source = self.paths[0]
        original_mtime = source.stat().st_mtime_ns

        def mutate(
            _production_id: str, **kwargs: object
        ) -> dict[str, object]:
            stream = kwargs["stream"]
            assert hasattr(stream, "read")
            stream.read()
            # Set a distinct timestamp explicitly: touch/write can retain the same
            # coarse clock value while the imported file handle is still open.
            metadata=source.stat()
            os.utime(source,ns=(metadata.st_atime_ns,original_mtime+2_000_000_000))
            return import_response(0, source.stat().st_size)

        service.import_production_video.side_effect = mutate
        one_video_request = project_request(
            videos=[{"path": source.name}],
            recipe=indexed_recipe((0, 0, 0)),
        )
        with self.assertRaises(QuickCreateProjectValidationError) as raised:
            run_quick_create_project(
                service,
                one_video_request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertEqual(raised.exception.code, "quick_create_project_video_changed")

    def test_mismatched_service_identities_fail_closed(self) -> None:
        service = consuming_service(self.paths)
        service.create_production.return_value = {
            **production_response(),
            "production": {
                **production_response()["production"],
                "id": "production_" + "f" * 32,
            },
        }
        with self.assertRaises(QuickCreateError) as created:
            run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertEqual(created.exception.code, "invalid_quick_create_project_result")

        service = consuming_service(self.paths)
        original = service.import_production_video.side_effect

        def wrong_artifact(*args: object, **kwargs: object) -> dict[str, object]:
            result = original(*args, **kwargs)
            result["artifact"]["production_id"] = "production_" + "f" * 32
            return result

        service.import_production_video.side_effect = wrong_artifact
        with self.assertRaises(QuickCreateError) as imported:
            run_quick_create_project(
                service,
                self.request,
                request_parent=self.parent,
                monotonic=lambda: 0.0,
            )
        self.assertEqual(imported.exception.code, "invalid_quick_create_project_result")


class QuickCreateProjectCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.request_file = self.workspace / "private-request.json"
        self.request_file.write_text("{}", encoding="utf-8")
        self.request = validate_quick_create_project_request(
            project_request(
                videos=[{"path": "private-source.mp4"}],
                recipe=indexed_recipe((0, 0, 0)),
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def argv(self) -> list[str]:
        return [
            "--workspace",
            str(self.workspace),
            "quick-create-project",
            str(self.request_file),
        ]

    def test_parser_and_success_output(self) -> None:
        parsed = cli.build_parser().parse_args(self.argv())
        self.assertEqual(parsed.command, "quick-create-project")
        expected = {
            "schema_version": 1,
            "production": {"id": PRODUCTION_ID, "title": "新規制作", "deduplicated": False},
            "videos": [],
            "quick_create": {"schema_version": 1, "status": "succeeded"},
        }
        lock = mock.Mock()
        service = mock.Mock()
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            mock.patch.object(cli, "load_quick_create_project_request", return_value=self.request),
            mock.patch.object(cli, "WorkspaceInstanceLock", return_value=lock),
            mock.patch.object(cli, "StudioService", return_value=service),
            mock.patch.object(cli, "run_quick_create_project", return_value=expected) as runner,
            mock.patch.object(cli.time, "monotonic", return_value=10.0),
            redirect_stdout(stdout),
            redirect_stderr(stderr),
        ):
            exit_code = cli.main(self.argv())
        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(runner.call_args.kwargs["request_parent"], self.workspace)
        service.close.assert_called_once_with()
        lock.close.assert_called_once_with()

    def test_qc_nonpass_is_three_and_failures_are_private(self) -> None:
        private = "C:\\private\\private-source.mp4"
        cases = [
            (QuickCreateQcNonPass("technical_qc_failed"), 3, "technical_qc_failed"),
            (RuntimeError(private), 2, "quick_create_failed"),
        ]
        for error, expected_exit, expected_code in cases:
            with self.subTest(code=expected_code):
                stdout, stderr = io.StringIO(), io.StringIO()
                service = mock.Mock()
                with (
                    mock.patch.object(
                        cli,
                        "load_quick_create_project_request",
                        return_value=self.request,
                    ),
                    mock.patch.object(cli, "WorkspaceInstanceLock", return_value=mock.Mock()),
                    mock.patch.object(cli, "StudioService", return_value=service),
                    mock.patch.object(cli, "run_quick_create_project", side_effect=error),
                    mock.patch.object(cli.time, "monotonic", return_value=10.0),
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    exit_code = cli.main(self.argv())
                self.assertEqual(exit_code, expected_exit)
                self.assertEqual(stdout.getvalue(), "")
                self.assertEqual(json.loads(stderr.getvalue())["error"]["code"], expected_code)
                self.assertNotIn(private, stderr.getvalue())
                self.assertNotIn("private-source.mp4", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

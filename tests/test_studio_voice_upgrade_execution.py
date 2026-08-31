from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from tools.studio.security import canonical_json, stable_id
from tools.studio.voice_upgrade import voice_upgrade_cache_key
from tools.studio.voice_upgrade_execution import (
    VOICE_UPGRADE_EXECUTION_PROVIDER,
    VoiceUpgradeExecutionError,
    execute_voice_upgrade,
    resolve_voice_upgrade_source,
    safe_voice_upgrade_execution_error,
    validate_voice_upgrade_execution_request,
)


PRODUCTION_ID = "production-voice-upgrade"
RUN_ID = "run_" + "1" * 32
SOURCE_ATTEMPT_ID = "attempt_" + "2" * 32
SOURCE_CACHE_KEY = "A" * 64
TEXTS = ("フック", "メッセージ", "案内")
SOURCE_INTERVALS = ((100, 250), (300, 600), (650, 750))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _wav_bytes() -> bytes:
    frame_count = 44_100
    frames = b"".join(
        int((index % 30_000) + 1).to_bytes(2, "little", signed=True)
        for index in range(frame_count)
    )
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(frames)
    return output.getvalue()


def _source_timings() -> dict[str, object]:
    characters: list[str] = []
    starts: list[float] = []
    ends: list[float] = []
    rows: list[dict[str, object]] = []
    cursor = 0
    for index, (text, (segment_start, segment_end)) in enumerate(
        zip(TEXTS, SOURCE_INTERVALS, strict=True)
    ):
        step = (segment_end - segment_start) // len(text)
        for character_index, character in enumerate(text):
            start = segment_start + character_index * step
            end = segment_end if character_index == len(text) - 1 else start + step
            characters.append(character)
            starts.append(start / 1_000)
            ends.append(end / 1_000)
        rows.append(
            {
                "index": index,
                "text": text,
                "start_ms": segment_start,
                "end_ms": segment_end,
                "duration_ms": segment_end - segment_start,
                "character_start_index": cursor,
                "character_end_index": cursor + len(text),
                "character_count": len(text),
            }
        )
        cursor += len(text)
        if index < len(TEXTS) - 1:
            characters.append("\n")
            starts.append(segment_end / 1_000)
            ends.append((segment_end + 25) / 1_000)
            cursor += 1
    return {
        "schema_version": 1,
        "implementation_version": "elevenlabs-timestamps-v1",
        "provider": "elevenlabs",
        "timing_source": "elevenlabs_alignment",
        "duration_ms": 1_000,
        "sample_rate": 44_100,
        "channels": 1,
        "sample_width": 2,
        "segments": rows,
        "alignment": {
            "characters": characters,
            "character_start_times_seconds": starts,
            "character_end_times_seconds": ends,
        },
    }


def _schedule() -> dict[str, object]:
    return {
        "schema_version": 1,
        "total_duration_ms": 3_000,
        "scenes": [
            {"role": role, "start_ms": start, "text": text}
            for role, start, text in zip(
                ("HOOK", "MESSAGE", "CTA"),
                (0, 1_000, 2_000),
                TEXTS,
                strict=True,
            )
        ],
    }


def _request() -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_attempt_id": SOURCE_ATTEMPT_ID,
        "schedule": _schedule(),
    }


class _Database:
    def __init__(
        self,
        run: dict[str, object],
        attempt: dict[str, object],
        artifacts: dict[str, dict[str, object]],
    ) -> None:
        self.run = run
        self.attempt = attempt
        self.artifacts = artifacts

    def get_run(self, run_id: str) -> dict[str, object] | None:
        return copy.deepcopy(self.run) if run_id == self.run.get("id") else None

    def get_stage_attempt(self, attempt_id: str) -> dict[str, object] | None:
        if attempt_id != self.attempt.get("id"):
            return None
        return copy.deepcopy(self.attempt)

    def get_artifact(self, artifact_id: str) -> dict[str, object] | None:
        artifact = self.artifacts.get(artifact_id)
        return copy.deepcopy(artifact) if artifact is not None else None


class VoiceUpgradeExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        source_root = (
            self.workspace
            / "outputs"
            / "studio"
            / "runs"
            / RUN_ID
            / "narration"
            / SOURCE_CACHE_KEY
        )
        source_root.mkdir(parents=True)
        source_files = {
            "narration.wav": _wav_bytes(),
            "captions.srt": b"source captions\n",
            "timings.json": (canonical_json(_source_timings()) + "\n").encode(
                "utf-8"
            ),
            "manifest.json": b'{"source":true}\n',
        }
        artifact_specs = {
            "narration.wav": ("audio", "audio/wav"),
            "captions.srt": ("subtitle", "application/x-subrip"),
            "timings.json": ("document", "application/json"),
            "manifest.json": ("document", "application/json"),
        }
        artifacts: dict[str, dict[str, object]] = {}
        result_artifacts: list[dict[str, object]] = []
        for name, data in source_files.items():
            path = source_root / name
            path.write_bytes(data)
            relative = path.relative_to(self.workspace).as_posix()
            artifact_id = stable_id("art", relative.casefold())
            kind, media_type = artifact_specs[name]
            artifact = {
                "id": artifact_id,
                "production_id": PRODUCTION_ID,
                "rel_path": relative,
                "origin": "studio",
                "name": name,
                "kind": kind,
                "media_type": media_type,
                "bytes": path.stat().st_size,
                "mtime_ns": path.stat().st_mtime_ns,
                "sha256": _sha256(data),
                "is_heavy": False,
                "available": True,
                "indexed_at": "2026-09-01T00:00:00Z",
                "file_url": f"/api/artifacts/{artifact_id}/file",
                "preview_url": f"/api/artifacts/{artifact_id}/file",
                "download_url": f"/api/artifacts/{artifact_id}/file",
            }
            artifacts[artifact_id] = artifact
            result_artifacts.append(copy.deepcopy(artifact))
        self.source_root = source_root
        self.artifacts = artifacts
        self.run = {
            "id": RUN_ID,
            "production_id": PRODUCTION_ID,
            "execution_profile": "elevenlabs_tts",
            "requested_stages": ["narration"],
        }
        self.attempt = {
            "id": SOURCE_ATTEMPT_ID,
            "run_id": RUN_ID,
            "production_id": PRODUCTION_ID,
            "stage": "narration",
            "status": "succeeded",
            "cache_key": SOURCE_CACHE_KEY,
            "result": {
                "provider": "elevenlabs",
                "timing_source": "elevenlabs_alignment",
                "cache_key": SOURCE_CACHE_KEY,
                "request_cache_key": SOURCE_CACHE_KEY,
                "cache_hit": False,
                "artifacts": result_artifacts,
            },
        }
        self.database = _Database(self.run, self.attempt, self.artifacts)

    def _source_artifact(self, name: str) -> dict[str, object]:
        return next(
            artifact
            for artifact in self.artifacts.values()
            if artifact["name"] == name
        )

    def test_public_request_is_exact_and_uses_database_native_attempt_id(self) -> None:
        normalized = validate_voice_upgrade_execution_request(_request())
        self.assertEqual(normalized, _request())

        invalid_requests = (
            {**_request(), "extra": True},
            {**_request(), "schema_version": True},
            {**_request(), "source_attempt_id": "stage_attempt_" + "2" * 32},
            {**_request(), "source_attempt_id": "attempt_" + "A" * 32},
            {
                **_request(),
                "schedule": {**_schedule(), "unexpected": True},
            },
        )
        for invalid in invalid_requests:
            with self.subTest(invalid=invalid):
                with self.assertRaises(VoiceUpgradeExecutionError) as caught:
                    validate_voice_upgrade_execution_request(invalid)
                self.assertEqual(
                    caught.exception.error_code,
                    "invalid_voice_upgrade_execution_request",
                )

    def test_resolver_returns_cache_key_and_path_free_hash_lineage(self) -> None:
        resolved = resolve_voice_upgrade_source(
            self.workspace,
            self.database,
            PRODUCTION_ID,
            RUN_ID,
            _request(),
        )
        expected_cache_key = voice_upgrade_cache_key(
            _schedule(),
            source_wav_sha256=self._source_artifact("narration.wav")["sha256"],
            source_timings_sha256=self._source_artifact("timings.json")[
                "sha256"
            ],
        )
        self.assertEqual(resolved.cache_key, expected_cache_key)
        self.assertEqual(resolved.lineage["source_attempt_id"], SOURCE_ATTEMPT_ID)
        self.assertEqual(
            set(resolved.lineage["source_artifacts"]),
            {"narration.wav", "timings.json"},
        )
        serialized = canonical_json(resolved.lineage)
        self.assertNotIn("rel_path", serialized)
        self.assertNotIn("file_url", serialized)
        self.assertNotIn(str(self.workspace), serialized)
        self.assertNotIn(TEXTS[1], serialized)

    def test_wrong_profile_run_attempt_or_provider_lineage_fails_closed(self) -> None:
        cases = (
            ("run profile", self.run, "execution_profile", "local_sapi", "required"),
            ("run production", self.run, "production_id", "other", "required"),
            ("attempt run", self.attempt, "run_id", "run_" + "9" * 32, "required"),
            ("attempt status", self.attempt, "status", "failed", "required"),
            ("attempt stage", self.attempt, "stage", "assembly", "required"),
            (
                "result provider",
                self.attempt["result"],
                "provider",
                "windows_sapi",
                "changed",
            ),
            (
                "result cache",
                self.attempt["result"],
                "cache_key",
                "B" * 64,
                "changed",
            ),
        )
        for label, target, key, replacement, code_suffix in cases:
            with self.subTest(label=label):
                original = target[key]
                target[key] = replacement
                try:
                    with self.assertRaises(VoiceUpgradeExecutionError) as caught:
                        resolve_voice_upgrade_source(
                            self.workspace,
                            self.database,
                            PRODUCTION_ID,
                            RUN_ID,
                            _request(),
                        )
                    self.assertEqual(
                        caught.exception.error_code,
                        f"voice_upgrade_source_{code_suffix}",
                    )
                finally:
                    target[key] = original

    def test_missing_duplicate_or_registry_mismatched_source_fails_closed(self) -> None:
        artifacts = self.attempt["result"]["artifacts"]
        original = copy.deepcopy(artifacts)
        artifacts[:] = [item for item in artifacts if item["name"] != "timings.json"]
        with self.assertRaises(VoiceUpgradeExecutionError) as missing:
            resolve_voice_upgrade_source(
                self.workspace, self.database, PRODUCTION_ID, RUN_ID, _request()
            )
        self.assertEqual(missing.exception.error_code, "voice_upgrade_source_changed")

        artifacts[:] = copy.deepcopy(original)
        artifacts.append(copy.deepcopy(artifacts[0]))
        with self.assertRaises(VoiceUpgradeExecutionError) as duplicate:
            resolve_voice_upgrade_source(
                self.workspace, self.database, PRODUCTION_ID, RUN_ID, _request()
            )
        self.assertEqual(
            duplicate.exception.error_code, "voice_upgrade_source_changed"
        )

        artifacts[:] = copy.deepcopy(original)
        narration = self._source_artifact("narration.wav")
        narration["sha256"] = "B" * 64
        with self.assertRaises(VoiceUpgradeExecutionError) as registry:
            resolve_voice_upgrade_source(
                self.workspace, self.database, PRODUCTION_ID, RUN_ID, _request()
            )
        self.assertEqual(registry.exception.error_code, "voice_upgrade_source_changed")

    def test_path_size_hash_and_mtime_are_revalidated(self) -> None:
        for label, mutate in (
            (
                "path",
                lambda record, path: record.__setitem__(
                    "rel_path", "outputs/unrelated/narration.wav"
                ),
            ),
            (
                "size",
                lambda record, path: record.__setitem__(
                    "bytes", int(record["bytes"]) + 1
                ),
            ),
            (
                "mtime",
                lambda record, path: record.__setitem__(
                    "mtime_ns", int(record["mtime_ns"]) + 1
                ),
            ),
            (
                "physical hash",
                lambda record, path: path.write_bytes(path.read_bytes() + b"changed"),
            ),
        ):
            with self.subTest(label=label):
                narration = self._source_artifact("narration.wav")
                result_item = next(
                    item
                    for item in self.attempt["result"]["artifacts"]
                    if item["name"] == "narration.wav"
                )
                original_record = copy.deepcopy(narration)
                original_result = copy.deepcopy(result_item)
                path = self.workspace / str(narration["rel_path"])
                original_bytes = path.read_bytes()
                mutate(narration, path)
                try:
                    with self.assertRaises(VoiceUpgradeExecutionError) as caught:
                        resolve_voice_upgrade_source(
                            self.workspace,
                            self.database,
                            PRODUCTION_ID,
                            RUN_ID,
                            _request(),
                        )
                    self.assertEqual(
                        caught.exception.error_code,
                        "voice_upgrade_source_changed",
                    )
                finally:
                    narration.clear()
                    narration.update(original_record)
                    result_item.clear()
                    result_item.update(original_result)
                    path.write_bytes(original_bytes)
                    stat = path.stat()
                    narration["mtime_ns"] = stat.st_mtime_ns
                    result_item["mtime_ns"] = stat.st_mtime_ns

    def test_worker_creates_register_ready_records_and_path_free_result(self) -> None:
        outcome = execute_voice_upgrade(
            self.workspace,
            self.database,
            PRODUCTION_ID,
            RUN_ID,
            _request(),
        )
        result = outcome.public_result
        self.assertEqual(result["provider"], VOICE_UPGRADE_EXECUTION_PROVIDER)
        self.assertIsNone(result["provider_task_id"])
        self.assertEqual(result["actual_cost"], 0)
        self.assertEqual(result["cost"]["source"], "local")
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["artifacts"], [])
        serialized = canonical_json(result)
        self.assertNotIn("rel_path", serialized)
        self.assertNotIn(str(self.workspace), serialized)
        self.assertNotIn(TEXTS[0], serialized)

        records = outcome.artifact_records
        self.assertEqual(
            {record["name"] for record in records},
            {"narration.wav", "captions.srt", "timings.json", "manifest.json"},
        )
        for record in records:
            self.assertEqual(
                set(record),
                {
                    "id",
                    "rel_path",
                    "name",
                    "kind",
                    "media_type",
                    "bytes",
                    "mtime_ns",
                    "sha256",
                    "is_heavy",
                },
            )
            self.assertTrue(
                str(record["rel_path"]).startswith(
                    f"outputs/studio/runs/{RUN_ID}/narration/{result['cache_key']}/"
                )
            )
            path = self.workspace / str(record["rel_path"])
            self.assertEqual(path.stat().st_size, record["bytes"])
            self.assertEqual(_sha256(path.read_bytes()), record["sha256"])

        cached = execute_voice_upgrade(
            self.workspace,
            self.database,
            PRODUCTION_ID,
            RUN_ID,
            _request(),
        )
        self.assertTrue(cached.public_result["cache_hit"])
        self.assertEqual(cached.artifact_records, outcome.artifact_records)

    def test_source_registry_race_after_alignment_is_rejected(self) -> None:
        from tools.studio import voice_upgrade_execution

        real_align = voice_upgrade_execution.align_external_tts_to_scene_schedule

        def raced_align(*args: object, **kwargs: object) -> dict[str, object]:
            result = real_align(*args, **kwargs)
            self._source_artifact("timings.json")["sha256"] = "B" * 64
            return result

        with mock.patch.object(
            voice_upgrade_execution,
            "align_external_tts_to_scene_schedule",
            side_effect=raced_align,
        ):
            with self.assertRaises(VoiceUpgradeExecutionError) as caught:
                execute_voice_upgrade(
                    self.workspace,
                    self.database,
                    PRODUCTION_ID,
                    RUN_ID,
                    _request(),
                )
        self.assertEqual(caught.exception.error_code, "voice_upgrade_source_changed")

    def test_malformed_or_mismatched_worker_result_is_rejected(self) -> None:
        from tools.studio import voice_upgrade_execution

        real_align = voice_upgrade_execution.align_external_tts_to_scene_schedule

        def wrong_cache(*args: object, **kwargs: object) -> dict[str, object]:
            result = real_align(*args, **kwargs)
            result["cache_key"] = "B" * 64
            return result

        with mock.patch.object(
            voice_upgrade_execution,
            "align_external_tts_to_scene_schedule",
            side_effect=wrong_cache,
        ):
            with self.assertRaises(VoiceUpgradeExecutionError) as mismatch:
                execute_voice_upgrade(
                    self.workspace,
                    self.database,
                    PRODUCTION_ID,
                    RUN_ID,
                    _request(),
                )
        self.assertEqual(
            mismatch.exception.error_code,
            "invalid_voice_upgrade_worker_result",
        )

        # Remove the invalid cache before asking the real worker to rebuild it.
        output_root = (
            self.workspace / "outputs" / "studio" / "runs" / RUN_ID / "narration"
        )
        for child in output_root.iterdir():
            if child.name != SOURCE_CACHE_KEY and child.is_dir():
                for nested in child.iterdir():
                    nested.unlink()
                child.rmdir()

        def wrong_hash(*args: object, **kwargs: object) -> dict[str, object]:
            result = real_align(*args, **kwargs)
            result["artifacts"][0]["sha256"] = "C" * 64
            return result

        with mock.patch.object(
            voice_upgrade_execution,
            "align_external_tts_to_scene_schedule",
            side_effect=wrong_hash,
        ):
            with self.assertRaises(VoiceUpgradeExecutionError) as bad_artifact:
                execute_voice_upgrade(
                    self.workspace,
                    self.database,
                    PRODUCTION_ID,
                    RUN_ID,
                    _request(),
                )
        self.assertEqual(
            bad_artifact.exception.error_code,
            "invalid_voice_upgrade_worker_result",
        )

    def test_safe_error_does_not_reflect_arbitrary_exception_text(self) -> None:
        code, message = safe_voice_upgrade_execution_error(
            RuntimeError("api-key=do-not-reflect")
        )
        self.assertEqual(code, "voice_upgrade_execution_failed")
        self.assertNotIn("api-key", message)


if __name__ == "__main__":
    unittest.main()

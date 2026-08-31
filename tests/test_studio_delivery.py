from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.studio.delivery import (
    DeliveryPackageError,
    DeliveryPackageValidationError,
    create_delivery_package,
    resolve_delivery_lineage,
    validate_delivery_package_payload,
)
from tools.studio.server import _DELIVERY_PACKAGE_RE
from tools.studio.service import StudioService


PRODUCTION_ID = "production_" + "a" * 32
RUN_ID = "run_" + "b" * 32
REVISION_ID = "rev_" + "c" * 32
TOP_JOB_ID = "job_" + "d" * 32


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class _Context:
    def raise_if_cancelled(self) -> None:
        return None


class _ImmediateJobs:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None
        self.result: dict[str, object] | None = None

    def submit(
        self,
        kind: str,
        payload: dict[str, object],
        callback: object,
        *,
        production_id: str,
    ) -> dict[str, object]:
        self.payload = dict(payload)
        job_id = "job_" + "e" * 32
        self.result = callback(job_id, _Context())  # type: ignore[operator]
        return {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "production_id": production_id,
            "payload": payload,
        }


class _Database:
    def __init__(
        self,
        *,
        production: dict[str, object],
        run: dict[str, object],
        jobs: dict[str, dict[str, object]],
        artifacts: dict[str, dict[str, object]],
    ) -> None:
        self.production = production
        self.run = run
        self.jobs = jobs
        self.artifacts = artifacts

    def get_production(self, production_id: str) -> dict[str, object] | None:
        return copy.deepcopy(self.production) if production_id == PRODUCTION_ID else None

    def get_run(self, run_id: str) -> dict[str, object] | None:
        return copy.deepcopy(self.run) if run_id == RUN_ID else None

    def get_job(self, job_id: str) -> dict[str, object] | None:
        value = self.jobs.get(job_id)
        return copy.deepcopy(value) if value is not None else None

    def get_artifact(self, artifact_id: str) -> dict[str, object] | None:
        value = self.artifacts.get(artifact_id)
        return copy.deepcopy(value) if value is not None else None

    def production_audit_snapshot(self, production_id: str) -> dict[str, object] | None:
        if production_id != PRODUCTION_ID:
            return None
        return {
            "production": copy.deepcopy(self.production),
            "artifacts": copy.deepcopy(list(self.artifacts.values())),
            "artifact_page": {
                "total": len(self.artifacts),
                "total_bytes": sum(int(item["bytes"]) for item in self.artifacts.values()),
                "limit": 1_000_000,
                "offset": 0,
            },
            "revisions": [],
            "runs": [copy.deepcopy(self.run)],
            "provider_tasks": [],
            "announcement_recipes": [],
            "announcement_recipe_versions": [],
            "announcement_executions": [],
            "events": [],
            "approvals": [],
        }

    def register_studio_artifact(
        self, production_id: str, artifact: dict[str, object]
    ) -> dict[str, object]:
        assert production_id == PRODUCTION_ID
        record = {
            **artifact,
            "production_id": production_id,
            "origin": "studio",
            "available": True,
            "indexed_at": "2026-09-01T00:00:00+00:00",
        }
        self.artifacts[str(record["id"])] = record
        return copy.deepcopy(record)


class DeliveryPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name).resolve()
        self.ffmpeg = shutil.which("ffmpeg")
        if self.ffmpeg is None:
            self.skipTest("ffmpeg is unavailable")
        self.database, self.request = self._fixture()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_video(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                str(self.ffmpeg),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=64x96:d=1:r=24",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-y",
                str(path),
            ],
            check=True,
            cwd=self.workspace,
        )

    def _fixture(self) -> tuple[_Database, dict[str, object]]:
        source_root = self.workspace / "outputs" / "studio" / "runs" / RUN_ID
        files = {
            "clean_master": (
                source_root / "assembly" / ("1" * 64) / "master-clean.mp4",
                "video",
                "video/mp4",
            ),
            "captioned_master": (
                source_root / "assembly" / ("1" * 64) / "master-captioned.mp4",
                "video",
                "video/mp4",
            ),
            "captions": (
                source_root / "narration" / ("2" * 64) / "captions.srt",
                "subtitle",
                "application/x-subrip",
            ),
            "technical_qc": (
                source_root / "qc" / ("3" * 64) / "technical-qc.json",
                "document",
                "application/json",
            ),
            "qc_ffprobe": (
                source_root / "qc" / ("3" * 64) / "ffprobe.json",
                "document",
                "application/json",
            ),
            "qc_manifest": (
                source_root / "qc" / ("3" * 64) / "manifest.json",
                "document",
                "application/json",
            ),
        }
        self._write_video(files["clean_master"][0])
        files["captioned_master"][0].parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(files["clean_master"][0], files["captioned_master"][0])
        files["captions"][0].parent.mkdir(parents=True, exist_ok=True)
        files["captions"][0].write_text(
            "1\n00:00:00,000 --> 00:00:00,900\n納品テスト\n",
            encoding="utf-8",
            newline="\n",
        )
        for field in ("technical_qc", "qc_ffprobe", "qc_manifest"):
            files[field][0].parent.mkdir(parents=True, exist_ok=True)
            files[field][0].write_text(
                json.dumps({"field": field}, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        artifacts: dict[str, dict[str, object]] = {}
        requested: dict[str, str] = {}
        for index, (field, (path, kind, media_type)) in enumerate(files.items(), start=1):
            artifact_id = f"art_{index:032x}"
            requested[field] = artifact_id
            stat = path.stat()
            artifacts[artifact_id] = {
                "id": artifact_id,
                "production_id": PRODUCTION_ID,
                "rel_path": path.relative_to(self.workspace).as_posix(),
                "origin": "studio",
                "name": path.name,
                "kind": kind,
                "media_type": media_type,
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": _sha256(path),
                "is_heavy": False,
                "available": True,
                "indexed_at": "2026-09-01T00:00:00+00:00",
            }

        stage_artifacts = {
            "narration": [artifacts[requested["captions"]]],
            "timeline": [],
            "assembly": [
                artifacts[requested["clean_master"]],
                artifacts[requested["captioned_master"]],
            ],
            "qc": [
                artifacts[requested["technical_qc"]],
                artifacts[requested["qc_ffprobe"]],
                artifacts[requested["qc_manifest"]],
            ],
        }
        jobs: dict[str, dict[str, object]] = {}
        attempts = []
        children: dict[str, dict[str, object]] = {}
        kinds = {
            "narration": "local_narration",
            "timeline": "local_remotion_timeline",
            "assembly": "local_assembly",
            "qc": "local_qc",
        }
        for index, stage in enumerate(("narration", "timeline", "assembly", "qc"), start=1):
            job_id = f"job_{index:032x}"
            attempt_id = f"attempt_{index:032x}"
            result = {
                "cache_hit": False,
                "artifacts": copy.deepcopy(stage_artifacts[stage]),
                "stage_attempt_id": attempt_id,
            }
            jobs[job_id] = {
                "id": job_id,
                "kind": kinds[stage],
                "status": "succeeded",
                "production_id": PRODUCTION_ID,
                "payload": {
                    "production_id": PRODUCTION_ID,
                    "run_id": RUN_ID,
                    "stage": stage,
                    "stage_attempt_id": attempt_id,
                },
                "result": result,
            }
            attempts.append(
                {
                    "id": attempt_id,
                    "job_id": job_id,
                    "run_id": RUN_ID,
                    "production_id": PRODUCTION_ID,
                    "stage": stage,
                    "status": "succeeded",
                    "result": {
                        key: value
                        for key, value in result.items()
                        if key != "stage_attempt_id"
                    },
                }
            )
            children[stage] = {
                "stage": stage,
                "status": "succeeded",
                "job_id": job_id,
                "stage_attempt_id": attempt_id,
                "cache_hit": False,
            }
        source_result = {
            "schema_version": 1,
            "production_id": PRODUCTION_ID,
            "run_id": RUN_ID,
            "revision_id": REVISION_ID,
            "duration_ms": 1_000,
            "technical_verdict": "pass",
            "include_captioned": True,
            "children": children,
        }
        jobs[TOP_JOB_ID] = {
            "id": TOP_JOB_ID,
            "kind": "detailed_test_video",
            "status": "succeeded",
            "production_id": PRODUCTION_ID,
            "payload": {
                "production_id": PRODUCTION_ID,
                "run_id": RUN_ID,
                "revision_id": REVISION_ID,
            },
            "result": source_result,
        }
        run = {
            "id": RUN_ID,
            "production_id": PRODUCTION_ID,
            "revision_id": REVISION_ID,
            "stage_attempts": attempts,
        }
        database = _Database(
            production={"id": PRODUCTION_ID, "title": "納品テスト"},
            run=run,
            jobs=jobs,
            artifacts=artifacts,
        )
        request = {
            "schema_version": 1,
            "run_id": RUN_ID,
            "source_job_id": TOP_JOB_ID,
            "artifacts": requested,
            "metadata": {
                "title": "生成AIを仕事に活かす",
                "description": "15秒で要点を紹介します。\n続きはプロフィールから。",
            },
        }
        return database, request

    def test_request_is_exact_and_rejects_hidden_or_control_fields(self) -> None:
        normalized = validate_delivery_package_payload(self.request)
        self.assertEqual(normalized["run_id"], RUN_ID)
        invalid = copy.deepcopy(self.request)
        invalid["upload"] = True
        with self.assertRaises(DeliveryPackageValidationError):
            validate_delivery_package_payload(invalid)
        invalid = copy.deepcopy(self.request)
        invalid["metadata"]["description"] = "公開\u202e禁止"
        with self.assertRaises(DeliveryPackageValidationError):
            validate_delivery_package_payload(invalid)

    def test_lineage_requires_exact_top_child_attempt_and_artifact_identity(self) -> None:
        lineage = resolve_delivery_lineage(
            self.database, PRODUCTION_ID, self.request
        )
        self.assertEqual(lineage["source_job_id"], TOP_JOB_ID)
        self.assertEqual(set(lineage["artifacts"]), set(self.request["artifacts"]))

        invalid = copy.deepcopy(self.request)
        invalid["artifacts"]["clean_master"] = invalid["artifacts"][
            "captioned_master"
        ]
        with self.assertRaises(DeliveryPackageValidationError):
            resolve_delivery_lineage(self.database, PRODUCTION_ID, invalid)

        child_id = self.database.jobs[TOP_JOB_ID]["result"]["children"]["qc"][
            "job_id"
        ]
        self.database.jobs[child_id]["payload"]["run_id"] = "run_" + "0" * 32
        with self.assertRaises(DeliveryPackageValidationError):
            resolve_delivery_lineage(self.database, PRODUCTION_ID, self.request)

    def test_creates_verified_delivery_zip_thumbnails_sidecar_and_cache_hit(self) -> None:
        lineage = resolve_delivery_lineage(
            self.database, PRODUCTION_ID, self.request
        )
        snapshot = self.database.production_audit_snapshot(PRODUCTION_ID)
        assert snapshot is not None
        result = create_delivery_package(
            self.workspace,
            production_id=PRODUCTION_ID,
            job_id="job_" + "9" * 32,
            lineage=lineage,
            audit_snapshot=snapshot,
            ffmpeg=self.ffmpeg,
        )
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["thumbnail_count"], 3)
        package = self.workspace / result["artifact_record"]["rel_path"]
        sidecar = self.workspace / result["sha256_sidecar"]
        self.assertTrue(package.is_file())
        self.assertEqual(
            sidecar.read_text(encoding="ascii"),
            f"{_sha256(package)} *delivery-package.zip\n",
        )
        with zipfile.ZipFile(package) as archive:
            names = set(archive.namelist())
            self.assertEqual(
                names,
                {
                    "video/master-clean.mp4",
                    "video/master-captioned.mp4",
                    "subtitles/captions.srt",
                    "qc/technical-qc.json",
                    "qc/ffprobe.json",
                    "qc/manifest.json",
                    "thumbnails/thumbnail-01.png",
                    "thumbnails/thumbnail-02.png",
                    "thumbnails/thumbnail-03.png",
                    "metadata/publication.json",
                    "audit/production-snapshot.json",
                    "audit/events.jsonl",
                    "delivery/manifest.json",
                },
            )
            publication = json.loads(archive.read("metadata/publication.json"))
            self.assertEqual(publication["title"], "生成AIを仕事に活かす")
            manifest = json.loads(archive.read("delivery/manifest.json"))
            self.assertEqual(manifest["thumbnail_timestamps_ms"], [250, 500, 750])
            for name in (
                "thumbnail-01.png",
                "thumbnail-02.png",
                "thumbnail-03.png",
            ):
                self.assertTrue(archive.read(f"thumbnails/{name}").startswith(b"\x89PNG"))

        cached = create_delivery_package(
            self.workspace,
            production_id=PRODUCTION_ID,
            job_id="job_" + "8" * 32,
            lineage=lineage,
            audit_snapshot=snapshot,
            ffmpeg=self.ffmpeg,
        )
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(
            cached["artifact_record"]["sha256"],
            result["artifact_record"]["sha256"],
        )

    def test_cache_rejects_self_consistent_manifest_identity_and_size_tamper(self) -> None:
        lineage = resolve_delivery_lineage(
            self.database, PRODUCTION_ID, self.request
        )
        snapshot = self.database.production_audit_snapshot(PRODUCTION_ID)
        assert snapshot is not None
        result = create_delivery_package(
            self.workspace,
            production_id=PRODUCTION_ID,
            job_id="job_" + "6" * 32,
            lineage=lineage,
            audit_snapshot=snapshot,
            ffmpeg=self.ffmpeg,
        )
        package = self.workspace / result["artifact_record"]["rel_path"]
        sidecar = self.workspace / result["sha256_sidecar"]
        with zipfile.ZipFile(package, "r") as archive:
            original_entries = {
                name: archive.read(name) for name in archive.namelist()
            }

        def rewrite(entries: dict[str, bytes]) -> None:
            temporary = package.with_suffix(".tampered")
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for name, value in entries.items():
                    archive.writestr(name, value)
            temporary.replace(package)
            sidecar.write_text(
                f"{_sha256(package)} *delivery-package.zip\n",
                encoding="ascii",
            )

        source_tamper = dict(original_entries)
        replacement_video = b"X" * len(source_tamper["video/master-clean.mp4"])
        source_tamper["video/master-clean.mp4"] = replacement_video
        manifest = json.loads(source_tamper["delivery/manifest.json"])
        clean_entry = next(
            item
            for item in manifest["archive_entries"]
            if item["path"] == "video/master-clean.mp4"
        )
        clean_entry["sha256"] = hashlib.sha256(replacement_video).hexdigest().upper()
        source_tamper["delivery/manifest.json"] = json.dumps(manifest).encode("utf-8")
        rewrite(source_tamper)
        with self.assertRaises(DeliveryPackageError):
            create_delivery_package(
                self.workspace,
                production_id=PRODUCTION_ID,
                job_id="job_" + "3" * 32,
                lineage=lineage,
                audit_snapshot=snapshot,
                ffmpeg=self.ffmpeg,
            )

        identity_tamper = dict(original_entries)
        manifest = json.loads(identity_tamper["delivery/manifest.json"])
        manifest["policy"] = "attacker-controlled-policy"
        identity_tamper["delivery/manifest.json"] = json.dumps(manifest).encode(
            "utf-8"
        )
        rewrite(identity_tamper)
        with self.assertRaises(DeliveryPackageError):
            create_delivery_package(
                self.workspace,
                production_id=PRODUCTION_ID,
                job_id="job_" + "5" * 32,
                lineage=lineage,
                audit_snapshot=snapshot,
                ffmpeg=self.ffmpeg,
            )

        oversized_manifest = dict(original_entries)
        oversized_manifest["delivery/manifest.json"] += b" " * (2 * 1024 * 1024)
        rewrite(oversized_manifest)
        with self.assertRaises(DeliveryPackageError):
            create_delivery_package(
                self.workspace,
                production_id=PRODUCTION_ID,
                job_id="job_" + "4" * 32,
                lineage=lineage,
                audit_snapshot=snapshot,
                ffmpeg=self.ffmpeg,
            )

    def test_input_tamper_fails_before_publish(self) -> None:
        lineage = resolve_delivery_lineage(
            self.database, PRODUCTION_ID, self.request
        )
        clean = self.workspace / lineage["artifacts"]["clean_master"]["rel_path"]
        original = clean.read_bytes()
        clean.write_bytes(b"X" + original[1:])
        snapshot = self.database.production_audit_snapshot(PRODUCTION_ID)
        assert snapshot is not None
        with self.assertRaises(DeliveryPackageError) as raised:
            create_delivery_package(
                self.workspace,
                production_id=PRODUCTION_ID,
                job_id="job_" + "7" * 32,
                lineage=lineage,
                audit_snapshot=snapshot,
                ffmpeg=self.ffmpeg,
            )
        self.assertEqual(raised.exception.error_code, "input_changed")
        deliveries = self.workspace / "outputs" / "studio" / "deliveries"
        self.assertEqual(list(deliveries.rglob("delivery-package.zip")), [])

    def test_service_job_redacts_copy_and_registers_delivery_artifact(self) -> None:
        service = object.__new__(StudioService)
        service.workspace = self.workspace
        service.database = self.database
        service.jobs = _ImmediateJobs()
        queued = service.create_delivery_package(PRODUCTION_ID, self.request)
        self.assertEqual(queued["kind"], "delivery_package")
        assert service.jobs.payload is not None
        self.assertNotIn("生成AI", json.dumps(service.jobs.payload, ensure_ascii=False))
        assert service.jobs.result is not None
        self.assertEqual(service.jobs.result["artifact"]["kind"], "delivery")
        self.assertFalse(service.jobs.result["network_used"])
        self.assertFalse(service.jobs.result["billable"])

    def test_http_route_is_closed_to_one_production_path(self) -> None:
        self.assertIsNotNone(
            _DELIVERY_PACKAGE_RE.fullmatch(
                f"/api/productions/{PRODUCTION_ID}/delivery-packages"
            )
        )
        self.assertIsNone(
            _DELIVERY_PACKAGE_RE.fullmatch(
                f"/api/productions/{PRODUCTION_ID}/delivery-packages/upload"
            )
        )


if __name__ == "__main__":
    unittest.main()

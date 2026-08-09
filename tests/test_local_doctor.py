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
            "cbbc9dab1f03d0d9a6caa8a8be7d77a7e37e1e44",
        )
        self.assertEqual(
            runtime_lock["repositories"]["comfyui_gguf"]["revision"],
            "6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
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
        self.assertEqual(set(manifest["profiles"]), {"lowvram", "official"})
        for entry in manifest["models"].values():
            self.assertGreater(entry["bytes"], 0)
            self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(entry["source_url"].startswith("https://huggingface.co/"))
            self.assertTrue(entry["license"])
            self.assertTrue(entry["license_url"].startswith("https://"))

    def test_profiles_have_four_exact_files(self) -> None:
        self.assertEqual(len(local_doctor.MODEL_PROFILES["lowvram"]), 4)
        self.assertEqual(len(local_doctor.MODEL_PROFILES["official"]), 4)
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


class WorkflowTests(unittest.TestCase):
    def test_lowvram_workflow_loader_names_and_limits(self) -> None:
        result = local_doctor.check_workflow(PROJECT_ROOT)
        self.assertEqual(result.status, "ok", result.summary)

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


if __name__ == "__main__":
    unittest.main()

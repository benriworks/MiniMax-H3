#!/usr/bin/env python3
"""Non-destructive readiness checks for the local MiniMax H3 ComfyUI runtime."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


GIB = 1024**3
MIB = 1024**2
MIN_TOTAL_RAM_BYTES = 32 * GIB
LOW_AVAILABLE_RAM_BYTES = 12 * GIB
MIN_TOTAL_VRAM_MIB = 8 * 1024
LOW_FREE_VRAM_MIB = 4 * 1024
MIN_OUTPUT_TEMP_HEADROOM_BYTES = 20 * GIB


@dataclass(frozen=True)
class ModelSpec:
    relative_path: str
    expected_bytes: int
    repository: str
    sha256: str = ""


@dataclass
class Check:
    name: str
    status: str
    summary: str
    details: dict[str, Any] | None = None


PROFILE_NAMES = ("lowvram", "lowvram_turbo", "lowvram_q4_turbo", "official")

LOWVRAM_WORKFLOW_MODELS = frozenset(
    (
        "MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf",
        "qwen3vl-32B-MiniMax-H3-Q2_K.gguf",
        "minimax_h3_video_vae_fp16.safetensors",
        "minimax_h3_audio_vae_fp32.safetensors",
    )
)

OFFICIAL_WORKFLOW_MODELS = frozenset(
    (
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "minimax_h3_video_vae_fp16.safetensors",
        "minimax_h3_audio_vae_fp32.safetensors",
    )
)

TURBO_LORA_NAME = "minimax_h3_turbo_v4_step600_ema.safetensors"
TURBO_WORKFLOW_MODELS = LOWVRAM_WORKFLOW_MODELS | {TURBO_LORA_NAME}
Q4_TURBO_WORKFLOW_MODELS = (
    (LOWVRAM_WORKFLOW_MODELS - {"qwen3vl-32B-MiniMax-H3-Q2_K.gguf"})
    | {"qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf", TURBO_LORA_NAME}
)
TURBO_GRID_SHA256 = "30eb3c2cc7fb6b470d9717ff840d359313ac27cd64b705e32da1baa10f72d6a8"


def load_runtime_lock(lock_path: Path) -> dict[str, Any]:
    try:
        runtime_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read runtime lock {lock_path}: {exc}") from exc
    if not isinstance(runtime_lock, dict) or runtime_lock.get("schema_version") != 1:
        raise ValueError("runtime lock schema_version must be 1")
    target = runtime_lock.get("target")
    if not isinstance(target, dict) or target.get("os") != "Windows" or target.get("python") != "3.12":
        raise ValueError("runtime lock must target Windows and CPython 3.12")
    repositories = runtime_lock.get("repositories")
    if not isinstance(repositories, dict):
        raise ValueError("runtime lock repositories object is missing")
    for repository_id in ("comfyui", "comfyui_gguf", "minimax_h3_turbo"):
        repository = repositories.get(repository_id)
        if not isinstance(repository, dict):
            raise ValueError(f"runtime lock repository {repository_id!r} is missing")
        if not str(repository.get("repository", "")).startswith("https://github.com/"):
            raise ValueError(f"runtime lock repository URL is invalid for {repository_id!r}")
        revision = str(repository.get("revision", ""))
        if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
            raise ValueError(f"runtime lock revision is invalid for {repository_id!r}")
    pytorch = runtime_lock.get("pytorch")
    packages = pytorch.get("packages") if isinstance(pytorch, dict) else None
    if (
        not isinstance(pytorch, dict)
        or pytorch.get("cuda_build") != "13.0"
        or not str(pytorch.get("index_url", "")).startswith("https://download.pytorch.org/")
        or not isinstance(packages, dict)
    ):
        raise ValueError("runtime lock PyTorch metadata is invalid")
    for package_name in ("torch", "torchvision", "torchaudio"):
        if not str(packages.get(package_name, "")).endswith("+cu130"):
            raise ValueError(f"runtime lock version is invalid for {package_name}")
    requirements_file = str(runtime_lock.get("requirements_file", ""))
    requirements_path = Path(requirements_file)
    if not requirements_file or requirements_path.is_absolute() or ".." in requirements_path.parts:
        raise ValueError("runtime lock requirements_file is unsafe")
    if not (lock_path.parent / requirements_path).is_file():
        raise ValueError(f"runtime requirements lock is missing: {requirements_file}")
    return runtime_lock


def load_model_profiles(manifest_path: Path) -> dict[str, tuple[ModelSpec, ...]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read model manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("model manifest schema_version must be 1")
    models = manifest.get("models")
    profiles = manifest.get("profiles")
    if not isinstance(models, dict) or not isinstance(profiles, dict):
        raise ValueError("model manifest must contain models and profiles objects")

    result: dict[str, tuple[ModelSpec, ...]] = {}
    expected_counts = {
        "lowvram": 4,
        "lowvram_turbo": 5,
        "lowvram_q4_turbo": 5,
        "official": 4,
    }
    for profile_name in PROFILE_NAMES:
        identifiers = profiles.get(profile_name)
        expected_count = expected_counts[profile_name]
        if not isinstance(identifiers, list) or len(identifiers) != expected_count:
            raise ValueError(
                f"profile {profile_name!r} must reference exactly {expected_count} models"
            )
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"profile {profile_name!r} contains duplicate model identifiers")
        specs: list[ModelSpec] = []
        for identifier in identifiers:
            entry = models.get(identifier)
            if not isinstance(entry, dict):
                raise ValueError(f"profile {profile_name!r} references unknown model {identifier!r}")
            try:
                relative_path = str(entry["local_path"])
                expected_bytes = int(entry["bytes"])
                repository = str(entry["repository"])
                sha256 = str(entry["sha256"])
                remote_path = str(entry["remote_path"])
                revision = str(entry["revision"])
                license_name = str(entry["license"])
                license_url = str(entry["license_url"])
                source_url = str(entry["source_url"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid model entry {identifier!r}: {exc}") from exc
            if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
                raise ValueError(f"unsafe model local_path: {relative_path!r}")
            if expected_bytes <= 0:
                raise ValueError(f"invalid byte size for model {identifier!r}")
            if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
                raise ValueError(f"invalid SHA-256 for model {identifier!r}")
            if not remote_path or len(revision) != 40:
                raise ValueError(f"invalid remote path or revision for model {identifier!r}")
            if not license_name or not license_url.startswith("https://"):
                raise ValueError(f"invalid license metadata for model {identifier!r}")
            if not source_url.startswith("https://huggingface.co/"):
                raise ValueError(f"invalid source URL for model {identifier!r}")
            specs.append(ModelSpec(relative_path, expected_bytes, repository, sha256))
        result[profile_name] = tuple(specs)
    return result


MODEL_PROFILES = load_model_profiles(Path(__file__).resolve().parents[1] / "model-manifest.json")


def format_bytes(value: int) -> str:
    return f"{value / GIB:.2f} GiB"


def _run(command: Sequence[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def parse_nvidia_smi(text: str) -> list[dict[str, Any]]:
    gpus: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",", 3)]
        if len(parts) not in (3, 4):
            continue
        try:
            memory_mib = int(parts[1])
            free_memory_mib = int(parts[2]) if len(parts) == 4 else None
        except ValueError:
            continue
        gpu = {
            "name": parts[0],
            "memory_mib": memory_mib,
            "driver": parts[3] if len(parts) == 4 else parts[2],
        }
        if free_memory_mib is not None:
            gpu["memory_free_mib"] = free_memory_mib
        gpus.append(gpu)
    return gpus


def check_gpu() -> Check:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return Check("gpu", "error", "nvidia-smi was not found; an NVIDIA CUDA GPU is required")
    result = _run(
        (
            nvidia_smi,
            "--query-gpu=name,memory.total,memory.free,driver_version",
            "--format=csv,noheader,nounits",
        )
    )
    if result.returncode != 0:
        return Check("gpu", "error", f"nvidia-smi failed: {result.stderr.strip()[:300]}")
    gpus = parse_nvidia_smi(result.stdout)
    if not gpus:
        return Check("gpu", "error", "nvidia-smi returned no parseable NVIDIA GPUs")
    largest = max(gpus, key=lambda gpu: int(gpu["memory_mib"]))
    total_mib = int(largest["memory_mib"])
    free_mib = largest.get("memory_free_mib")
    if total_mib < MIN_TOTAL_VRAM_MIB:
        status = "error"
        pressure = "; less than the 8 GiB total-VRAM readiness floor"
    elif isinstance(free_mib, int) and free_mib < LOW_FREE_VRAM_MIB:
        status = "warning"
        pressure = (
            "; GPU memory is currently busy; close other GPU applications or use "
            ".\\run-local.ps1 -EmergencyLowVram"
        )
    else:
        status = "ok"
        pressure = ""
    free_summary = f", {free_mib / 1024:.1f} GiB free" if isinstance(free_mib, int) else ""
    return Check(
        "gpu",
        status,
        f"{largest['name']} with {total_mib / 1024:.1f} GiB VRAM{free_summary}{pressure}",
        {"gpus": gpus},
    )


def _windows_memory_bytes() -> tuple[int, int]:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = (
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        )

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(status.ullTotalPhys), int(status.ullAvailPhys)


def total_ram_bytes() -> int:
    return memory_bytes()[0]


def memory_bytes() -> tuple[int, int]:
    if os.name == "nt":
        return _windows_memory_bytes()
    page_size = os.sysconf("SC_PAGE_SIZE")
    page_count = os.sysconf("SC_PHYS_PAGES")
    available_count = os.sysconf("SC_AVPHYS_PAGES")
    return int(page_size * page_count), int(page_size * available_count)


def check_ram() -> Check:
    try:
        total, available = memory_bytes()
    except (OSError, ValueError, AttributeError) as exc:
        return Check("ram", "warning", f"could not inspect physical RAM: {exc}")
    if total < MIN_TOTAL_RAM_BYTES:
        status = "error"
        pressure = "; less than the 32 GiB physical-RAM readiness floor"
    elif available < LOW_AVAILABLE_RAM_BYTES:
        status = "warning"
        pressure = (
            "; available RAM is low; close other applications or use "
            ".\\run-local.ps1 -EmergencyLowVram"
        )
    else:
        status = "ok"
        pressure = ""
    return Check(
        "ram",
        status,
        f"{format_bytes(total)} physical RAM, {format_bytes(available)} available{pressure}",
        {"total_bytes": total, "available_bytes": available},
    )


def parse_pagefile_json(text: str) -> tuple[int, list[dict[str, Any]]]:
    if not text.strip():
        return 0, []
    decoded = json.loads(text)
    entries = decoded if isinstance(decoded, list) else [decoded]
    normalized = [entry for entry in entries if isinstance(entry, dict)]
    allocated_mib = sum(int(entry.get("AllocatedBaseSize") or 0) for entry in normalized)
    return allocated_mib * MIB, normalized


def check_pagefile() -> Check:
    if os.name != "nt":
        return Check("pagefile", "warning", "pagefile inspection is implemented for Windows only")
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return Check("pagefile", "warning", "PowerShell was not found for pagefile inspection")
    script = (
        "Get-CimInstance Win32_PageFileUsage | "
        "Select-Object Name,AllocatedBaseSize,CurrentUsage | ConvertTo-Json -Compress"
    )
    result = _run((powershell, "-NoProfile", "-Command", script))
    if result.returncode != 0:
        return Check("pagefile", "warning", f"pagefile inspection failed: {result.stderr.strip()[:300]}")
    try:
        allocated, entries = parse_pagefile_json(result.stdout)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return Check("pagefile", "warning", f"could not parse pagefile information: {exc}")
    if allocated == 0:
        return Check("pagefile", "warning", "no allocated Windows pagefile was detected", {"entries": entries})
    status = "ok" if allocated >= 16 * GIB else "warning"
    return Check(
        "pagefile",
        status,
        f"{format_bytes(allocated)} allocated pagefile",
        {"allocated_bytes": allocated, "entries": entries},
    )


def _inspect_git_lock(path: Path, expected_revision: str) -> tuple[str, str, dict[str, Any]]:
    details: dict[str, Any] = {"locked_revision": expected_revision}
    git = shutil.which("git")
    if not git or not (path / ".git").is_dir():
        return "warning", "; Git revision could not be verified", details
    revision = _run((git, "-C", str(path), "rev-parse", "HEAD"))
    dirty = _run((git, "-C", str(path), "status", "--porcelain", "--untracked-files=normal"))
    if revision.returncode != 0 or dirty.returncode != 0:
        return "warning", "; Git revision/status inspection failed", details
    actual_revision = revision.stdout.strip()
    details["revision"] = actual_revision
    notes: list[str] = []
    if actual_revision != expected_revision:
        notes.append("HEAD differs from runtime-lock.json")
    if dirty.stdout.strip():
        notes.append("working tree has local changes")
        details["dirty"] = True
    if notes:
        return "warning", "; " + "; ".join(notes) + "; reproducibility is not guaranteed", details
    return "ok", "", details


def check_comfyui(root: Path, expected_revision: str) -> Check:
    comfy = root / "runtime" / "ComfyUI"
    h3_vae = comfy / "comfy" / "ldm" / "minimax" / "vae.py"
    comfy_sd = comfy / "comfy" / "sd.py"
    required = (
        comfy / "main.py",
        comfy / "comfy_extras" / "nodes_minimax_h3.py",
        h3_vae,
        comfy_sd,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return Check("comfyui", "error", "ComfyUI or native MiniMax H3 nodes are missing", {"missing": missing})
    try:
        vae_source = h3_vae.read_text(encoding="utf-8")
        sd_source = comfy_sd.read_text(encoding="utf-8")
    except OSError as exc:
        return Check("comfyui", "error", f"cannot inspect MiniMax H3 VAE optimization: {exc}")
    if "comfy_has_chunked_io = True" not in vae_source or "comfy_has_chunked_io" not in sd_source:
        return Check(
            "comfyui",
            "error",
            "MiniMax H3 chunked VAE I/O optimization from ComfyUI PR #15446 is missing",
            {"vae_path": str(h3_vae), "sd_path": str(comfy_sd)},
        )
    status, revision_note, revision_details = _inspect_git_lock(comfy, expected_revision)
    details: dict[str, Any] = {"path": str(comfy), **revision_details}
    details["minimax_h3_chunked_vae_io"] = True
    summary = "ComfyUI with native MiniMax H3 nodes and chunked VAE I/O is present"
    summary += revision_note
    return Check("comfyui", status, summary, details)


def check_torch(root: Path, runtime_lock: Mapping[str, Any]) -> Check:
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return Check("torch_cuda", "error", f"virtual environment Python is missing: {python}")
    probe = (
        "import json, sys, torch, torchvision, torchaudio; "
        "print(json.dumps({'python': f'{sys.version_info.major}.{sys.version_info.minor}', "
        "'torch': torch.__version__, 'torchvision': torchvision.__version__, "
        "'torchaudio': torchaudio.__version__, 'cuda_build': torch.version.cuda, "
        "'cuda_available': torch.cuda.is_available(), "
        "'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}))"
    )
    result = _run((str(python), "-c", probe), timeout=60)
    if result.returncode != 0:
        return Check("torch_cuda", "error", f"torch probe failed: {result.stderr.strip()[-500:]}")
    try:
        data = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        return Check("torch_cuda", "error", f"torch probe returned invalid JSON: {exc}")
    if not data.get("cuda_available"):
        return Check("torch_cuda", "error", "PyTorch cannot access CUDA", data)
    expected_packages = runtime_lock["pytorch"]["packages"]
    mismatch: list[str] = []
    if data.get("python") != runtime_lock["target"]["python"]:
        mismatch.append(
            f"Python {data.get('python')} != {runtime_lock['target']['python']}"
        )
    for package_name in ("torch", "torchvision", "torchaudio"):
        if data.get(package_name) != expected_packages[package_name]:
            mismatch.append(
                f"{package_name} {data.get(package_name)} != {expected_packages[package_name]}"
            )
    if data.get("cuda_build") != runtime_lock["pytorch"]["cuda_build"]:
        mismatch.append(
            f"CUDA build {data.get('cuda_build')} != {runtime_lock['pytorch']['cuda_build']}"
        )
    if mismatch:
        data["lock_mismatches"] = mismatch
        return Check(
            "torch_cuda",
            "warning",
            "CUDA is available, but runtime versions differ from the lock; reproducibility is not guaranteed: "
            + "; ".join(mismatch),
            data,
        )
    return Check(
        "torch_cuda",
        "ok",
        (
            f"Python {data.get('python')} / torch {data.get('torch')} / "
            f"torchvision {data.get('torchvision')} / torchaudio {data.get('torchaudio')} / "
            f"CUDA {data.get('cuda_build')} / {data.get('device')}"
        ),
        data,
    )


def check_custom_node(root: Path, expected_revision: str) -> Check:
    gguf = root / "runtime" / "ComfyUI" / "custom_nodes" / "ComfyUI-GGUF"
    nodes_file = gguf / "nodes.py"
    if not (gguf / "__init__.py").is_file() or not nodes_file.is_file():
        return Check("comfyui_gguf", "error", f"ComfyUI-GGUF is missing: {gguf}")
    try:
        source = nodes_file.read_text(encoding="utf-8")
    except OSError as exc:
        return Check("comfyui_gguf", "error", f"cannot read ComfyUI-GGUF nodes.py: {exc}")
    required_loaders = ("UnetLoaderGGUF", "CLIPLoaderGGUF")
    missing = [loader for loader in required_loaders if f'"{loader}"' not in source]
    if missing:
        return Check("comfyui_gguf", "error", "required GGUF loaders are not registered", {"missing": missing})
    status, revision_note, revision_details = _inspect_git_lock(gguf, expected_revision)
    return Check(
        "comfyui_gguf",
        status,
        "ComfyUI-GGUF loaders are present" + revision_note,
        {"path": str(gguf), **revision_details},
    )


def check_turbo_custom_node(root: Path, expected_revision: str) -> Check:
    turbo = root / "runtime" / "ComfyUI" / "custom_nodes" / "ComfyUI-MiniMax-H3-Turbo"
    nodes_file = turbo / "__init__.py"
    grid_file = turbo / "h3_silu_temb_grid.safetensors"
    if not nodes_file.is_file() or not grid_file.is_file():
        return Check(
            "minimax_h3_turbo_node",
            "error",
            f"pinned MiniMax H3 Turbo custom node is missing: {turbo}",
        )
    try:
        source = nodes_file.read_text(encoding="utf-8")
    except OSError as exc:
        return Check("minimax_h3_turbo_node", "error", f"cannot read Turbo node source: {exc}")
    required_contracts = (
        '"MiniMaxH3TurboLoRA"',
        '"MiniMaxH3TurboSampler"',
        "low_vram",
        "weight_patched",
    )
    missing = [contract for contract in required_contracts if contract not in source]
    if missing:
        return Check(
            "minimax_h3_turbo_node",
            "error",
            "required Turbo node contracts are missing",
            {"missing": missing, "path": str(nodes_file)},
        )
    try:
        grid_digest = hashlib.sha256(grid_file.read_bytes()).hexdigest()
    except OSError as exc:
        return Check("minimax_h3_turbo_node", "error", f"cannot hash Turbo time grid: {exc}")
    if grid_digest != TURBO_GRID_SHA256:
        return Check(
            "minimax_h3_turbo_node",
            "error",
            "Turbo time-conditioning grid SHA-256 mismatch",
            {
                "path": str(grid_file),
                "expected_sha256": TURBO_GRID_SHA256,
                "actual_sha256": grid_digest,
            },
        )
    status, revision_note, revision_details = _inspect_git_lock(turbo, expected_revision)
    return Check(
        "minimax_h3_turbo_node",
        status,
        "MiniMax H3 Turbo LoRA and sampler nodes are present" + revision_note,
        {"path": str(turbo), "grid_sha256": grid_digest, **revision_details},
    )


def check_model_files(
    models_root: Path,
    specs: Iterable[ModelSpec],
    *,
    exists: Callable[[Path], bool] = Path.is_file,
    size_of: Callable[[Path], int] = lambda path: path.stat().st_size,
    verify_hash: bool = False,
) -> tuple[list[Check], int]:
    checks: list[Check] = []
    missing_bytes = 0
    for spec in specs:
        path = models_root / Path(spec.relative_path)
        if not exists(path):
            missing_bytes += spec.expected_bytes
            checks.append(
                Check(
                    f"model:{Path(spec.relative_path).name}",
                    "error",
                    f"missing ({format_bytes(spec.expected_bytes)})",
                    {"path": str(path), "repository": spec.repository},
                )
            )
            continue
        try:
            actual = size_of(path)
        except OSError as exc:
            missing_bytes += spec.expected_bytes
            checks.append(Check(f"model:{path.name}", "error", f"could not inspect size: {exc}"))
            continue
        if actual != spec.expected_bytes:
            missing_bytes += spec.expected_bytes
            checks.append(
                Check(
                    f"model:{path.name}",
                    "error",
                    f"size mismatch: expected {spec.expected_bytes}, found {actual}",
                    {"path": str(path), "expected_bytes": spec.expected_bytes, "actual_bytes": actual},
                )
            )
        elif verify_hash:
            digest = hashlib.sha256()
            try:
                with path.open("rb") as model_file:
                    for chunk in iter(lambda: model_file.read(8 * MIB), b""):
                        digest.update(chunk)
            except OSError as exc:
                missing_bytes += spec.expected_bytes
                checks.append(Check(f"model:{path.name}", "error", f"could not hash file: {exc}"))
                continue
            actual_hash = digest.hexdigest()
            if actual_hash != spec.sha256:
                missing_bytes += spec.expected_bytes
                checks.append(
                    Check(
                        f"model:{path.name}",
                        "error",
                        "SHA-256 mismatch",
                        {"path": str(path), "expected_sha256": spec.sha256, "actual_sha256": actual_hash},
                    )
                )
            else:
                checks.append(
                    Check(
                        f"model:{path.name}",
                        "ok",
                        f"{format_bytes(actual)}; SHA-256 verified",
                        {"path": str(path), "bytes": actual, "sha256": actual_hash},
                    )
                )
        else:
            checks.append(
                Check(
                    f"model:{path.name}",
                    "ok",
                    format_bytes(actual),
                    {"path": str(path), "bytes": actual, "sha256_verified": False},
                )
            )
    return checks, missing_bytes


def _walk_nodes(workflow: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    nodes = workflow.get("nodes")
    if isinstance(nodes, list):
        yield from (node for node in nodes if isinstance(node, dict))
    definitions = workflow.get("definitions")
    if not isinstance(definitions, dict):
        return
    subgraphs = definitions.get("subgraphs")
    if not isinstance(subgraphs, list):
        return
    for subgraph in subgraphs:
        if isinstance(subgraph, dict) and isinstance(subgraph.get("nodes"), list):
            yield from (node for node in subgraph["nodes"] if isinstance(node, dict))


def _all_widget_strings(nodes: Iterable[Mapping[str, Any]]) -> set[str]:
    values: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for item in value.values():
                visit(item)

    for node in nodes:
        visit(node.get("widgets_values"))
        visit(node.get("properties"))
    return values


def check_official_workflow(root: Path) -> Check:
    path = (
        root
        / ".venv"
        / "Lib"
        / "site-packages"
        / "comfyui_workflow_templates_json"
        / "templates"
        / "video_minimax_h3_t2v.json"
    )
    if not path.is_file():
        return Check(
            "workflow:official",
            "error",
            "ComfyUI's official MiniMax H3 T2V template is missing",
            {"expected_path": str(path)},
        )
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("workflow:official", "error", f"official workflow is invalid JSON: {exc}")
    if not isinstance(workflow, dict):
        return Check("workflow:official", "error", "official workflow root must be a JSON object")
    nodes = list(_walk_nodes(workflow))
    node_types = {str(node.get("type", "")) for node in nodes}
    strings = _all_widget_strings(nodes)
    problems: list[str] = []
    for loader in ("UNETLoader", "CLIPLoader"):
        if loader not in node_types:
            problems.append(f"{loader} is missing")
    missing_names = sorted(OFFICIAL_WORKFLOW_MODELS - strings)
    if missing_names:
        problems.append(f"official loader model names missing: {', '.join(missing_names)}")
    if problems:
        return Check("workflow:official", "error", "; ".join(problems), {"path": str(path)})
    return Check(
        "workflow:official",
        "ok",
        "ComfyUI official T2V template and official loader/model names verified",
        {"path": str(path)},
    )


def check_workflow(root: Path, profile: str = "lowvram") -> Check:
    if profile == "official":
        return check_official_workflow(root)
    is_q4_turbo = profile == "lowvram_q4_turbo"
    is_turbo = profile in {"lowvram_turbo", "lowvram_q4_turbo"}
    workflow_name = {
        "lowvram": "minimax_h3_t2v_lowvram.json",
        "lowvram_turbo": "minimax_h3_t2v_lowvram_turbo.json",
        "lowvram_q4_turbo": "minimax_h3_t2v_lowvram_q4_turbo.json",
    }[profile]
    path = root / "workflows" / workflow_name
    if not path.is_file():
        return Check("workflow", "error", f"{profile} workflow is missing: {path}")
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("workflow", "error", f"workflow is not valid JSON: {exc}")
    if not isinstance(workflow, dict):
        return Check("workflow", "error", "workflow root must be a JSON object")

    nodes = list(_walk_nodes(workflow))
    node_types = [str(node.get("type", "")) for node in nodes]
    strings = _all_widget_strings(nodes)
    problems: list[str] = []
    if "UnetLoaderGGUF" not in node_types:
        problems.append("UnetLoaderGGUF is missing")
    if "CLIPLoaderGGUF" not in node_types:
        problems.append("CLIPLoaderGGUF is missing")
    clip_loaders = [node for node in nodes if node.get("type") == "CLIPLoaderGGUF"]
    expected_text_encoder = (
        "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf"
        if is_q4_turbo
        else "qwen3vl-32B-MiniMax-H3-Q2_K.gguf"
    )
    forbidden_text_encoder = (
        "qwen3vl-32B-MiniMax-H3-Q2_K.gguf"
        if is_q4_turbo
        else "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf"
    )
    if forbidden_text_encoder in strings:
        problems.append(f"workflow must not reference {forbidden_text_encoder}")
    if len(clip_loaders) != 1:
        problems.append("exactly one CLIPLoaderGGUF node is required")
    else:
        clip_values = clip_loaders[0].get("widgets_values", [])
        if (
            not isinstance(clip_values, list)
            or len(clip_values) < 2
            or clip_values[0] != expected_text_encoder
            or clip_values[1] != "minimax"
        ):
            problems.append(
                f"CLIPLoaderGGUF must use {expected_text_encoder} with type minimax"
            )
    expected_models = (
        Q4_TURBO_WORKFLOW_MODELS
        if is_q4_turbo
        else TURBO_WORKFLOW_MODELS
        if is_turbo
        else LOWVRAM_WORKFLOW_MODELS
    )
    missing_names = sorted(expected_models - strings)
    if missing_names:
        problems.append(f"loader model names missing: {', '.join(missing_names)}")

    turbo_lora_nodes = [node for node in nodes if node.get("type") == "MiniMaxH3TurboLoRA"]
    turbo_sampler_nodes = [node for node in nodes if node.get("type") == "MiniMaxH3TurboSampler"]
    if is_turbo:
        if len(turbo_lora_nodes) != 1:
            problems.append("exactly one MiniMaxH3TurboLoRA node is required")
        else:
            lora_values = turbo_lora_nodes[0].get("widgets_values", [])
            if (
                not isinstance(lora_values, list)
                or len(lora_values) < 3
                or lora_values[0] != TURBO_LORA_NAME
                or lora_values[1] != 1
                or lora_values[2] is not True
            ):
                problems.append("Turbo LoRA must use the pinned v4 EMA file, strength 1.0, and low_vram merge")
        if len(turbo_sampler_nodes) != 1:
            problems.append("exactly one MiniMaxH3TurboSampler node is required")
        definitions = workflow.get("definitions")
        subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
        turbo_graphs = [
            graph
            for graph in subgraphs
            if isinstance(graph, dict)
            and isinstance(graph.get("nodes"), list)
            and any(
                isinstance(node, dict) and node.get("type") == "MiniMaxH3TurboLoRA"
                for node in graph["nodes"]
            )
        ]
        if len(turbo_graphs) != 1:
            problems.append("Turbo nodes must share one inspectable subgraph")
        else:
            graph = turbo_graphs[0]
            if is_q4_turbo and graph.get("name") != "MiniMax H3 Q4 Turbo low-VRAM (GGUF)":
                problems.append("Q4 Turbo subgraph name is not profile-specific")
            graph_nodes = {
                node.get("id"): node for node in graph["nodes"] if isinstance(node, dict)
            }
            graph_links = {
                link.get("id"): link
                for link in graph.get("links", [])
                if isinstance(link, dict)
            }

            def linked_origin_type(node_type: str, input_name: str) -> str | None:
                matching = [node for node in graph_nodes.values() if node.get("type") == node_type]
                if len(matching) != 1:
                    return None
                inputs = matching[0].get("inputs", [])
                input_entry = next(
                    (
                        entry
                        for entry in inputs
                        if isinstance(entry, dict) and entry.get("name") == input_name
                    ),
                    None,
                )
                link = graph_links.get(input_entry.get("link")) if input_entry else None
                origin = graph_nodes.get(link.get("origin_id")) if link else None
                return str(origin.get("type")) if isinstance(origin, dict) else None

            required_wiring = (
                ("MiniMaxH3TurboLoRA", "model", "UnetLoaderGGUF"),
                ("BasicScheduler", "model", "MiniMaxH3TurboLoRA"),
                ("BasicGuider", "model", "MiniMaxH3TurboLoRA"),
                ("SamplerCustomAdvanced", "sampler", "MiniMaxH3TurboSampler"),
            )
            for target_type, input_name, expected_origin in required_wiring:
                actual_origin = linked_origin_type(target_type, input_name)
                if actual_origin != expected_origin:
                    problems.append(
                        f"{target_type}.{input_name} must be linked from {expected_origin}, "
                        f"found {actual_origin or 'no valid link'}"
                    )
    elif turbo_lora_nodes or turbo_sampler_nodes:
        problems.append("base low-VRAM workflow must not enable Turbo nodes")

    top_nodes = workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else []
    selectors = [
        node
        for node in top_nodes
        if isinstance(node, dict) and node.get("type") == "ResolutionSelector"
    ]
    if len(selectors) != 1:
        problems.append("exactly one top-level ResolutionSelector node is required")
    selector_values = selectors[0].get("widgets_values", []) if len(selectors) == 1 else []
    expected_megapixels = 0.4 if is_q4_turbo else 0.2
    if (
        not isinstance(selector_values, list)
        or len(selector_values) < 3
        or selector_values[1] != expected_megapixels
    ):
        problems.append(f"ResolutionSelector is not set to {expected_megapixels} megapixels")
    if not isinstance(selector_values, list) or len(selector_values) < 1 or selector_values[0] != "16:9 (Widescreen)":
        problems.append("ResolutionSelector aspect ratio is not 16:9 (Widescreen)")
    if not isinstance(selector_values, list) or len(selector_values) < 3 or selector_values[2] != 32:
        problems.append("ResolutionSelector multiple is not 32")
    schedulers = [node for node in nodes if node.get("type") == "BasicScheduler"]
    scheduler_values = schedulers[0].get("widgets_values", []) if schedulers else []
    expected_steps = 8 if is_q4_turbo else 6 if is_turbo else 20
    if (
        not isinstance(scheduler_values, list)
        or len(scheduler_values) < 2
        or scheduler_values[0] != "simple"
        or scheduler_values[1] != expected_steps
    ):
        problems.append(f"BasicScheduler is not set to simple / {expected_steps} steps")

    definitions = workflow.get("definitions")
    subgraphs = definitions.get("subgraphs", []) if isinstance(definitions, dict) else []
    subgraph_ids = {
        subgraph.get("id")
        for subgraph in subgraphs
        if isinstance(subgraph, dict)
    }
    instances = [node for node in top_nodes if isinstance(node, dict) and node.get("type") in subgraph_ids]
    if len(instances) != 1 or len(instances[0].get("widgets_values", [])) < 9:
        problems.append("MiniMax H3 subgraph instance is missing")
    else:
        expected_duration = 5 if is_turbo else 4
        instance_values = instances[0]["widgets_values"]
        if instance_values[3] != expected_duration:
            problems.append(f"workflow duration is not set to {expected_duration} seconds")
        expected_overrides = [
            "MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf",
            expected_text_encoder,
            "minimax_h3_video_vae_fp16.safetensors",
            "minimax_h3_audio_vae_fp32.safetensors",
        ]
        if instance_values[5:9] != expected_overrides:
            problems.append(
                "MiniMax H3 subgraph model overrides must exactly select "
                + ", ".join(expected_overrides)
            )
        if is_q4_turbo and instances[0].get("title") != "MiniMax H3 Q4 Turbo low-VRAM (GGUF)":
            problems.append("Q4 Turbo subgraph instance title is not profile-specific")
        if len(selectors) == 1:
            top_links = workflow.get("links") if isinstance(workflow.get("links"), list) else []
            resolution_links = [
                link
                for link in top_links
                if isinstance(link, list)
                and len(link) >= 5
                and link[3] == instances[0].get("id")
                and link[4] in (2, 3)
            ]
            actual_resolution_links = {
                (link[1], link[2], link[4]) for link in resolution_links
            }
            expected_resolution_links = {
                (selectors[0].get("id"), 0, 2),
                (selectors[0].get("id"), 1, 3),
            }
            if (
                len(resolution_links) != 2
                or actual_resolution_links != expected_resolution_links
            ):
                problems.append(
                    "ResolutionSelector width/height outputs must link to subgraph inputs 2/3"
                )

    save_video_nodes = [node for node in nodes if node.get("type") == "SaveVideo"]
    expected_prefix = "video/MiniMax_H3_Q4" if is_q4_turbo else "video/MiniMax_H3"
    if len(save_video_nodes) != 1:
        problems.append("exactly one SaveVideo node is required")
    else:
        save_values = save_video_nodes[0].get("widgets_values", [])
        if not isinstance(save_values, list) or not save_values or save_values[0] != expected_prefix:
            problems.append(f"SaveVideo filename prefix must be {expected_prefix}")

    provenance = root / "workflows" / "README.md"
    if not provenance.is_file():
        problems.append("workflow provenance README is missing")
    else:
        try:
            provenance_text = provenance.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"cannot read workflow provenance: {exc}")
        else:
            if "video_minimax_h3_t2v.json" not in provenance_text or "5c75d9f" not in provenance_text:
                problems.append("workflow provenance source/commit is incomplete")
            if is_turbo and (
                "55fee864dd7b2976b1c4ce3c3d5f7968f181409f" not in provenance_text
                or "43a74557ac3f6539db8e0f2a959d03feb7a81480" not in provenance_text
            ):
                problems.append("Turbo workflow provenance revisions are incomplete")
            if is_q4_turbo and (
                "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf" not in provenance_text
                or "1bf75e038c5895b97b6ea16cc1e3d32076254b06ec3df10657650d86dc82279e"
                not in provenance_text
            ):
                problems.append("Q4 workflow provenance metadata is incomplete")

    if problems:
        return Check("workflow", "error", "; ".join(problems), {"path": str(path)})
    return Check(
        "workflow",
        "ok",
        (
            "GGUF loaders, exact promoted model overrides, Q4 text encoder, Turbo merge path, 16:9 / multiple 32 / 0.4 MP, 5 seconds, and 8 steps verified"
            if is_q4_turbo
            else "GGUF loaders, exact promoted model overrides, Turbo merge path, 16:9 / multiple 32 / 0.2 MP, 5 seconds, and 6 steps verified"
            if is_turbo
            else "GGUF loaders, exact promoted model overrides, 16:9 / multiple 32 / 0.2 MP, 4 seconds, and 20 steps verified"
        ),
        {"path": str(path)},
    )


def check_disk(root: Path, missing_bytes: int) -> Check:
    try:
        usage = shutil.disk_usage(root)
    except OSError as exc:
        return Check("disk", "error", f"disk inspection failed: {exc}")
    required = missing_bytes + (2 * GIB)
    projected_free = usage.free - missing_bytes
    if usage.free < required:
        status = "error"
    elif projected_free < MIN_OUTPUT_TEMP_HEADROOM_BYTES:
        status = "warning"
    else:
        status = "ok"
    summary = f"{format_bytes(usage.free)} free"
    if missing_bytes:
        summary += f"; {format_bytes(required)} needed for missing models plus headroom"
    elif status == "error":
        summary += "; less than the 2.00 GiB minimum output/temp headroom"
    if status == "warning":
        summary += (
            f"; projected output/temp headroom is below "
            f"{format_bytes(MIN_OUTPUT_TEMP_HEADROOM_BYTES)}"
        )
    return Check(
        "disk",
        status,
        summary,
        {
            "free_bytes": usage.free,
            "required_bytes": required,
            "total_bytes": usage.total,
            "projected_free_after_download_bytes": projected_free,
            "recommended_output_temp_headroom_bytes": MIN_OUTPUT_TEMP_HEADROOM_BYTES,
        },
    )


def inspect_environment(root: Path, profile: str, *, verify_hash: bool = False) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if profile not in PROFILE_NAMES:
        raise ValueError(f"unknown profile: {profile}")
    try:
        runtime_lock = load_runtime_lock(root / "runtime-lock.json")
    except ValueError as exc:
        runtime_lock_check = Check("runtime_lock", "error", str(exc))
        runtime_lock = None
    else:
        runtime_lock_check = Check(
            "runtime_lock",
            "ok",
            "Windows/Python 3.12 runtime lock schema and pinned sources are valid",
            {"path": str(root / "runtime-lock.json")},
        )
    try:
        model_profiles = load_model_profiles(root / "model-manifest.json")
    except ValueError as exc:
        manifest_check = Check("model_manifest", "error", str(exc))
        model_checks: list[Check] = []
        missing_bytes = 0
    else:
        manifest_check = Check(
            "model_manifest",
            "ok",
            "tracked manifest schema, paths, sizes, and SHA-256 values are valid",
            {"path": str(root / "model-manifest.json")},
        )
        model_checks, missing_bytes = check_model_files(
            root / "runtime" / "ComfyUI" / "models",
            model_profiles[profile],
            verify_hash=verify_hash,
        )
    checks: list[Check] = [
        check_gpu(),
        check_ram(),
        check_pagefile(),
        check_disk(root, missing_bytes),
        runtime_lock_check,
    ]
    if runtime_lock is None:
        checks.extend(
            (
                Check("comfyui", "error", "cannot verify ComfyUI without a valid runtime lock"),
                Check("torch_cuda", "error", "cannot verify PyTorch without a valid runtime lock"),
                Check("comfyui_gguf", "error", "cannot verify ComfyUI-GGUF without a valid runtime lock"),
                Check(
                    "minimax_h3_turbo_node",
                    "error",
                    "cannot verify MiniMax H3 Turbo node without a valid runtime lock",
                ),
            )
        )
    else:
        checks.extend(
            (
                check_comfyui(root, str(runtime_lock["repositories"]["comfyui"]["revision"])),
                check_torch(root, runtime_lock),
                check_custom_node(
                    root,
                    str(runtime_lock["repositories"]["comfyui_gguf"]["revision"]),
                ),
                check_turbo_custom_node(
                    root,
                    str(runtime_lock["repositories"]["minimax_h3_turbo"]["revision"]),
                ),
            )
        )
    checks.extend([manifest_check, *model_checks, check_workflow(root, profile)])
    ready = not any(check.status == "error" for check in checks)
    reproducibility_names = {
        "runtime_lock",
        "comfyui",
        "torch_cuda",
        "comfyui_gguf",
        "minimax_h3_turbo_node",
    }
    locked_core_matches = all(
        check.status == "ok" for check in checks if check.name in reproducibility_names
    ) and reproducibility_names.issubset({check.name for check in checks})
    return {
        "root": str(root),
        "profile": profile,
        "ready": ready,
        "locked_core_runtime_matches": locked_core_matches,
        "missing_model_bytes": missing_bytes,
        "hash_verification_requested": verify_hash,
        "checks": [asdict(check) for check in checks],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="MiniMaxH3 project root",
    )
    parser.add_argument("--profile", choices=PROFILE_NAMES, default="lowvram")
    parser.add_argument(
        "--hash",
        action="store_true",
        help="stream every model through SHA-256 (slow but performs full integrity verification)",
    )
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_environment(args.root, args.profile, verify_hash=args.hash)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for check in report["checks"]:
            marker = {"ok": "OK", "warning": "WARN", "error": "ERROR"}[check["status"]]
            print(f"[{marker:5}] {check['name']}: {check['summary']}")
        print()
        print(f"Profile: {report['profile']}")
        print(f"Ready: {'yes' if report['ready'] else 'no'}")
        print(
            "Locked core runtime matches: "
            + (
                "yes"
                if report["locked_core_runtime_matches"]
                else "no (see runtime lock warnings/errors)"
            )
        )
        if report["missing_model_bytes"]:
            print(f"Missing/invalid model download size: {format_bytes(report['missing_model_bytes'])}")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

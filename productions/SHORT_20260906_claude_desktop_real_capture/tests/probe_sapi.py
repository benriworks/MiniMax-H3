"""One-phrase, local-only diagnosis using the unchanged Studio SAPI adapter."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
WORKSPACE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKSPACE))
from tools.studio import narration


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("voice", choices=("Microsoft Sayaka", "Microsoft Ayumi"))
    parser.add_argument("--powershell7", action="store_true", help="Use the already-installed Codex PowerShell 7 host for this diagnostic only")
    args = parser.parse_args()
    runtime = (Path("C:/Users/mono_/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe")
               if args.powershell7 else Path(narration._find_powershell()))
    if not runtime.is_file() or runtime.is_symlink():
        raise RuntimeError("The observed PowerShell host is not available.")
    host = subprocess.run([str(runtime), "-NoProfile", "-NonInteractive", "-Command",
        "@{version=$PSVersionTable.PSVersion.ToString();edition=$PSVersionTable.PSEdition;is64BitProcess=[Environment]::Is64BitProcess} | ConvertTo-Json -Compress"],
        check=True, capture_output=True, timeout=15)
    suffix = "-PowerShell7" if args.powershell7 else ""
    folder = WORKSPACE / "outputs/studio/verification/claude-desktop-real-20260906/voice-probes" / (args.voice.replace(" ", "-") + suffix)
    if folder.exists():
        raise RuntimeError("This one-time probe already has an output directory.")
    folder.mkdir(parents=True)
    real_popen = narration.subprocess.Popen
    evidence = []

    def observed_popen(*values, **options):
        process = real_popen(*values, **options)
        communicate = process.communicate

        def observed_communicate(*a, **kw):
            result = communicate(*a, **kw)
            stderr = result[1] or b""
            decoded = stderr.decode("utf-8", errors="replace")
            if "\ufffd" in decoded:
                decoded = stderr.decode("cp932", errors="replace")
            evidence.append({"returncode": process.returncode,
                             "stderr": decoded.replace(str(WORKSPACE), "<workspace>")[:2500]})
            return result

        process.communicate = observed_communicate
        return process

    result = {"time": datetime.now(timezone.utc).isoformat(), "voice": args.voice,
              "text": "条件を添えて、三案まとめて依頼。", "rate": 0,
              "provider": "windows_sapi", "paid_api_calls": 0, "quality_accepted": False,
              "powershell": str(runtime), "host": json.loads(host.stdout.decode("utf-8-sig")),
              "helper_script": str(narration._sapi_script_path())}
    try:
        with patch.object(narration.subprocess, "Popen", observed_popen), patch.object(narration, "_find_powershell", lambda: str(runtime)):
            data = narration._synthesize_sapi(result["text"], voice=args.voice, rate=0, workspace=folder)
        segment = narration._read_wav(data, label="single phrase probe")
        (folder / "phrase.wav").write_bytes(data)
        result.update(success=True, wav_bytes=len(data), wav_sha256=hashlib.sha256(data).hexdigest().upper(),
                      sample_rate=segment.sample_rate, channels=segment.channels, sample_width=segment.sample_width,
                      duration_ms=round(len(segment.frames) / (segment.channels * segment.sample_width) / segment.sample_rate * 1000))
    except Exception as exc:
        result.update(success=False, exception_type=type(exc).__name__, exception=str(exc)[:300])
    result["process_evidence"] = evidence
    (folder / "probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

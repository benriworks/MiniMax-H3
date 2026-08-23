from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .secrets import PROVIDERS, SecretStorageUnavailable, SecretStore


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage MiniMaxH3 Studio local settings")
    parser.add_argument("--workspace", type=Path, default=_default_workspace())
    commands = parser.add_subparsers(dest="command", required=True)
    secret = commands.add_parser("secret", help="Manage DPAPI-protected provider credentials")
    secret_commands = secret.add_subparsers(dest="secret_command", required=True)
    set_command = secret_commands.add_parser("set", help="Read and store a credential without echo")
    set_command.add_argument("provider", choices=sorted(PROVIDERS))
    delete_command = secret_commands.add_parser("delete", help="Delete a stored provider credential")
    delete_command.add_argument("provider", choices=sorted(PROVIDERS))
    status_command = secret_commands.add_parser("status", help="Show configured flags only")
    status_command.add_argument("provider", choices=sorted(PROVIDERS), nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        workspace = args.workspace.resolve(strict=True)
        store = SecretStore(workspace)
        if args.secret_command == "set":
            value = getpass.getpass(f"{args.provider} credential: ")
            store.set(args.provider, value)
            print(json.dumps({"id": args.provider, "configured": True}))
            return 0
        if args.secret_command == "delete":
            removed = store.delete(args.provider)
            print(json.dumps({"id": args.provider, "configured": False, "removed": removed}))
            return 0
        statuses = store.statuses()
        if args.provider:
            statuses = [item for item in statuses if item["id"] == args.provider]
        print(json.dumps({"providers": statuses}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, SecretStorageUnavailable) as exc:
        # The credential itself is never interpolated into an error.
        print(f"Studio secret operation failed: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

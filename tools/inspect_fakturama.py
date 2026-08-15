"""Standalone Fakturama UI inspection utility."""

from __future__ import annotations

import argparse

from app.main import inspect_ui


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Fakturama UIA tree")
    parser.add_argument("--depth", type=int, default=5)
    args = parser.parse_args()
    return inspect_ui(max_depth=args.depth)


if __name__ == "__main__":
    raise SystemExit(main())

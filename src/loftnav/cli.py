"""CLI `loftnav` (FR-001): реестр сабкоманд. 002 — `ingest`; 003 добавит `transform`, 006 — export.

console_script: loftnav = loftnav.cli:main.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loftnav.config import IngestConfig
from loftnav.ingest.run import ingest_paths


def _cmd_ingest(args: argparse.Namespace) -> int:
    cfg = IngestConfig.from_env()
    paths = [Path(p) for p in args.paths]
    try:
        return ingest_paths(paths, args.source, cfg)
    except RuntimeError as exc:  # lock занят / отсутствует env — читаемая ошибка, не трейс (I-8)
        print(f"loftnav ingest: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loftnav", description="LoftNavigator LakeHouse CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="загрузить файл(ы)/папку в bronze")
    ingest.add_argument("paths", nargs="+", help="файлы или папки для загрузки")
    ingest.add_argument(
        "--source", default=None, help="имя источника (bronze-таблицы); по умолчанию — имя файла"
    )
    ingest.set_defaults(func=_cmd_ingest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

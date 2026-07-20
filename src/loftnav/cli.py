"""CLI `loftnav` (FR-001): реестр сабкоманд. 002 — `ingest`; 003 добавит `transform`, 006 — export.

console_script: loftnav = loftnav.cli:main.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loftnav.config import ExportConfig, GoldConfig, IngestConfig, TransformConfig
from loftnav.export.run import run_export
from loftnav.gold.run import run_build_gold
from loftnav.ingest.run import ingest_paths
from loftnav.transform.run import run_transform


def _cmd_ingest(args: argparse.Namespace) -> int:
    cfg = IngestConfig.from_env()
    paths = [Path(p) for p in args.paths]
    try:
        return ingest_paths(paths, args.source, cfg)
    except RuntimeError as exc:  # lock занят / отсутствует env — читаемая ошибка, не трейс (I-8)
        print(f"loftnav ingest: {exc}", file=sys.stderr)
        return 1


def _cmd_transform(args: argparse.Namespace) -> int:
    tcfg = TransformConfig.from_env()
    try:
        return run_transform(args.source, args.reprocess, tcfg)
    except RuntimeError as exc:  # lock занят — читаемая ошибка (I-8)
        print(f"loftnav transform: {exc}", file=sys.stderr)
        return 1


def _cmd_build_gold(args: argparse.Namespace) -> int:
    gcfg = GoldConfig.from_env()
    try:
        return run_build_gold(args.only, gcfg)
    except RuntimeError as exc:  # lock занят — читаемая ошибка (I-8)
        print(f"loftnav build-gold: {exc}", file=sys.stderr)
        return 1


def _cmd_export_dataset(args: argparse.Namespace) -> int:
    ecfg = ExportConfig.from_env()
    try:
        return run_export(args.format, ecfg)
    except RuntimeError as exc:  # lock занят — читаемая ошибка (I-8)
        print(f"loftnav export-dataset: {exc}", file=sys.stderr)
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

    transform = sub.add_parser("transform", help="нормализовать bronze → silver.apartments_clean")
    transform.add_argument("--source", default=None, help="обработать только один источник")
    transform.add_argument(
        "--reprocess", default=None, help="переиграть источник (DELETE партиции + полный пересчёт)"
    )
    transform.set_defaults(func=_cmd_transform)

    build_gold = sub.add_parser("build-gold", help="силвер → gold-витрины + apartments_features")
    build_gold.add_argument("--only", default=None, help="пересчитать только одну витрину/таблицу")
    build_gold.set_defaults(func=_cmd_build_gold)

    export = sub.add_parser("export-dataset", help="features → версия датасета в ml-datasets")
    export.add_argument(
        "--format", default="both", choices=("parquet", "jsonl", "both"), help="формат(ы) выгрузки"
    )
    export.set_defaults(func=_cmd_export_dataset)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line interface: desidata <command> [args].

Zero dependencies (argparse), so the CLI ships with the base install.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__
from .client import (
    DesiDataError,
    clear_cache,
    fetch_catalog,
    fetch_csv_bytes,
    fetch_info,
    search_datasets,
)

# Windows consoles default to legacy code pages; dataset titles contain ₹ etc.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def _print_table(rows: List[dict]) -> None:
    if not rows:
        print("No datasets found.")
        return
    slug_width = min(max(len(row["slug"]) for row in rows) + 2, 44)
    category_width = min(max(len(str(row.get("category", ""))) for row in rows) + 2, 14)
    print(f"{'slug':<{slug_width}}{'category':<{category_width}}{'rows':>7}  title")
    for row in rows:
        slug = row["slug"]
        if len(slug) > slug_width - 1:
            slug = slug[: slug_width - 4] + "..."
        category = str(row.get("category", ""))
        if len(category) > category_width - 1:
            category = category[: category_width - 1]
        title = str(row.get("title", "")).replace("\n", " ")
        print(f"{slug:<{slug_width}}{category:<{category_width}}{row.get('rows', 0):>7}  {title}")


def _print_info(metadata: dict) -> None:
    order = ["slug", "name", "description", "category", "language", "format", "size", "downloads", "tags", "download_url"]
    for key in order:
        if key in metadata:
            value = metadata[key]
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            print(f"{key:>14}: {value}")
    for key, value in metadata.items():
        if key not in order:
            print(f"{key:>14}: {value}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desidata",
        description="Load Indian datasets from desidata.in (https://www.desidata.in).",
    )
    parser.add_argument("--version", action="version", version=f"desidata {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search dataset titles and descriptions")
    search_parser.add_argument("query")

    info_parser = subparsers.add_parser("info", help="Show metadata for one dataset")
    info_parser.add_argument("slug", help="Dataset slug or full desidata.in URL")

    catalog_parser = subparsers.add_parser("catalog", help="List every published dataset")
    catalog_parser.add_argument("--category", default=None)

    download_parser = subparsers.add_parser("download", help="Download a dataset CSV")
    download_parser.add_argument("slug", help="Dataset slug or full desidata.in URL")
    download_parser.add_argument("-o", "--output", default=None, help="Output file (default: <slug>.csv)")
    download_parser.add_argument("--refresh", action="store_true", help="Bypass the local cache")

    subparsers.add_parser("clear-cache", help="Delete cached CSVs (~/.desidata/cache)")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        if args.command == "search":
            _print_table(search_datasets(args.query))
        elif args.command == "info":
            _print_info(fetch_info(args.slug))
        elif args.command == "catalog":
            _print_table(fetch_catalog(category=args.category))
        elif args.command == "download":
            data = fetch_csv_bytes(args.slug, refresh=args.refresh)
            output = args.output or f"{args.slug.rsplit('/', 1)[-1].lower()}.csv"
            with open(output, "wb") as handle:
                handle.write(data)
            print(f"Saved {len(data):,} bytes to {output}")
        elif args.command == "clear-cache":
            removed = clear_cache()
            print(f"Removed {removed} cached file(s).")
    except DesiDataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

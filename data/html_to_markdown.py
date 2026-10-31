# /// script
# requires-python = ">=3.12"
# ///
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from docling.document_converter import DocumentConverter

# Params: edit these, then run:
#   uv run --project backend --group dev python data/html_to_markdown.py
INPUT_DIR = Path(__file__).resolve().parent / "downloads"
OUTPUT_DIR = Path(__file__).resolve().parent / "Markdown"
CLEAR_OUTPUT_DIR = False
SKIP_EXISTING = True

HTML_SUFFIXES = {".html", ".htm"}


def html_path_to_markdown_path(relative_html_path: str) -> Path:
    source = Path(relative_html_path)
    return source.with_suffix(".md")


def find_html_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in HTML_SUFFIXES
        and path.name != "manifest.json"
    )


def load_source_manifest(input_dir: Path) -> dict | None:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def convert_html_to_markdown(
    converter: DocumentConverter,
    source_path: Path,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = converter.convert(str(source_path))
    output_path.write_text(result.document.export_to_markdown(), encoding="utf-8")


def build_output_manifest(
    source_manifest: dict | None,
    converted: list[dict[str, str]],
) -> dict:
    converted_at = datetime.now(UTC).isoformat()
    converted_by_source = {
        entry["source_html_path"]: entry for entry in converted
    }

    if source_manifest is None:
        return {
            "source": "local HTML corpus",
            "generated_at_utc": converted_at,
            "converted_at_utc": converted_at,
            "converter": "docling",
            "converted_count": len(converted),
            "filings": converted,
        }

    filings = []
    for filing in source_manifest.get("filings", []):
        source_html_path = filing["local_path"]
        conversion = converted_by_source.get(source_html_path)
        if conversion is None:
            continue

        filings.append(
            {
                **filing,
                "source_html_path": source_html_path,
                "local_path": conversion["local_path"],
                "converted_at_utc": conversion["converted_at_utc"],
            }
        )

    return {
        "source": source_manifest.get("source", "SEC EDGAR"),
        "generated_at_utc": source_manifest.get("generated_at_utc"),
        "converted_at_utc": converted_at,
        "converter": "docling",
        "form": source_manifest.get("form"),
        "converted_count": len(filings),
        "filings": filings,
    }


def convert_downloads_to_markdown() -> dict:
    if not INPUT_DIR.is_dir():
        raise FileNotFoundError(f"Input directory not found: {INPUT_DIR}")

    if CLEAR_OUTPUT_DIR and OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source_manifest = load_source_manifest(INPUT_DIR)
    if source_manifest is not None:
        html_files = [
            INPUT_DIR / filing["local_path"]
            for filing in source_manifest["filings"]
        ]
    else:
        html_files = find_html_files(INPUT_DIR)

    converter = DocumentConverter()
    converted: list[dict[str, str]] = []

    for index, source_path in enumerate(html_files, start=1):
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing HTML file: {source_path}")

        relative_html_path = str(source_path.relative_to(INPUT_DIR))
        output_path = OUTPUT_DIR / html_path_to_markdown_path(relative_html_path)

        if SKIP_EXISTING and output_path.is_file():
            print(f"[{index}/{len(html_files)}] Skipping existing {output_path}")
            converted.append(
                {
                    "source_html_path": relative_html_path,
                    "local_path": str(output_path.relative_to(OUTPUT_DIR)),
                    "converted_at_utc": datetime.fromtimestamp(
                        output_path.stat().st_mtime, UTC
                    ).isoformat(),
                }
            )
            continue

        print(f"[{index}/{len(html_files)}] Converting {relative_html_path}...")
        convert_html_to_markdown(converter, source_path, output_path)
        converted.append(
            {
                "source_html_path": relative_html_path,
                "local_path": str(output_path.relative_to(OUTPUT_DIR)),
                "converted_at_utc": datetime.now(UTC).isoformat(),
            }
        )

    manifest = build_output_manifest(source_manifest, converted)
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    result = convert_downloads_to_markdown()
    print(
        f"Converted {result['converted_count']} filing(s) to Markdown under {OUTPUT_DIR}"
    )
    print(f"Manifest: {OUTPUT_DIR / 'manifest.json'}")

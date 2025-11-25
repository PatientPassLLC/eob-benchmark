#!/usr/bin/env python3
"""
Convert hexline-formatted model output to benchmark-compatible format.
"""

import json
import re
from pathlib import Path
from collections import defaultdict


def strip_hexlines(markdown: str) -> str:
    """Remove hexline prefixes (0x0001:) from markdown."""
    return re.sub(r'^0x[0-9A-F]+:\s*', '', markdown, flags=re.MULTILINE)


def split_by_pages(markdown: str, coordinate_map: dict, page_count: int) -> dict[int, str]:
    """Split hexline markdown into per-page markdown using coordinate_map."""

    # Strip hexlines first to get clean markdown
    clean_md = strip_hexlines(markdown)

    # Map each hexline to its page
    hexlines = markdown.strip().split('\n')
    page_content = defaultdict(list)

    for hexline in hexlines:
        # Extract hex ID (case-insensitive)
        match = re.match(r'^(0x[0-9A-Fa-f]+):\s*(.+)$', hexline)
        if not match:
            continue

        hex_id = match.group(1)
        content = match.group(2)

        # Look up page number in coordinate_map (try both cases)
        coord_info = coordinate_map.get(hex_id) or coordinate_map.get(hex_id.upper()) or coordinate_map.get(hex_id.lower())
        if coord_info:
            page_num = coord_info.get('page_num')
            if page_num:
                page_content[page_num].append(content)

    # Join lines for each page
    return {page: '\n'.join(lines) for page, lines in page_content.items()}


def convert_model_output(input_json_path: Path, output_dir: Path, model_name: str):
    """
    Convert model output JSON to benchmark format.

    Args:
        input_json_path: Path to model output JSON file
        output_dir: Base output directory (e.g., outputs/my_model)
        model_name: Display name for the model
    """

    # Load model output
    with open(input_json_path) as f:
        data = json.load(f)

    document_id = data['document_id']
    page_count = data['page_count']
    markdown = data['markdown']
    coordinate_map = data.get('coordinate_map', {})

    # Determine fixture ID from document_id
    # "CIGNA _ 57.00_rotation_fix" -> look for matching fixture
    fixtures_dir = Path("fixtures")
    fixture_id = None

    for fixture_dir in fixtures_dir.iterdir():
        if not fixture_dir.is_dir():
            continue
        manifest_path = fixture_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            # Match by source filename
            if document_id in manifest.get('source_file', ''):
                fixture_id = fixture_dir.name
                break

    if not fixture_id:
        print(f"Warning: Could not find matching fixture for '{document_id}'")
        print(f"Using 'eob_001' as default. Available fixtures:")
        for f in fixtures_dir.iterdir():
            if f.is_dir():
                print(f"  - {f.name}")
        fixture_id = "eob_001"

    # Create output directory structure
    output_path = output_dir / fixture_id / "pages"
    output_path.mkdir(parents=True, exist_ok=True)

    # Split markdown by pages
    pages_md = split_by_pages(markdown, coordinate_map, page_count)

    # Write per-page markdown files
    for page_num in range(1, page_count + 1):
        page_md = pages_md.get(page_num, '')
        output_file = output_path / f"page_{page_num}.md"
        output_file.write_text(page_md)
        print(f"Created: {output_file}")

    print(f"\nConversion complete!")
    print(f"Output directory: {output_dir / fixture_id}")
    print(f"\nTo run benchmark:")
    print(f"  python benchmark_runner.py {output_dir} \"{model_name}\"")

    # Check if fixture is verified
    manifest_path = fixtures_dir / fixture_id / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if not manifest.get('verified'):
            print(f"\n⚠️  Warning: {fixture_id} is not verified yet.")
            print(f"   Set 'verified': true in {manifest_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print("Usage: python convert_model_output.py <input.json> <output_dir> <model_name>")
        print("\nExample:")
        print("  python convert_model_output.py model_output.json outputs/deepseek 'DeepSeek-OCR'")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])
    model_name = sys.argv[3]

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    convert_model_output(input_path, output_dir, model_name)

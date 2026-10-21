#!/usr/bin/env python3
"""Build the public comparison catalog from pinned, published metadata only.

No corpus text, embeddings, or parquet files are downloaded. Source counts and
token counts come from descriptive_stats.json, while the publisher's README
supplies the source-to-domain mapping and release version. The pinned revisions
below make the output reproducible apart from generated_at. To update a release,
review its dataset card and change its revision here before running the script.

Usage: python3 scripts/build_corpus_catalog.py
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = [
    ("danish", "Danish", "da", "fc6664826b50fcbe91864c85fca6104f839027dc"),
    ("norwegian", "Norwegian", "no", "37d81a9f710bbf1b52b616b7161e4e42047827e3"),
    ("swedish", "Swedish", "sv", "aa04ebdd6f2553774b2c278868d017235d4c2db6"),
    ("icelandic", "Icelandic", "is", "0bb26f027648c465d8bdcf6262c6ebab97f2d1ee"),
    ("faroese", "Faroese", "fo", "24ab901896257f4a1c6e4b0e6b0619ffc500f72d"),
]
INDEXED_DANISH = {
    "revision": "c2f51be06848df26b5aad71cafeec1bc6064b1cc",
    "version": "v1.2.23",
    "records": 7_399_685,
    "tokens": 9_813_858_821,
    "sources": 50,
}


def fetch_text(repo: str, revision: str, path: str, cache: Path) -> str:
    """Cache immutable public metadata; never read a credential or use a token."""
    target = cache / repo.split("/")[-1] / revision / path
    if target.is_file():
        return target.read_text(encoding="utf-8")
    url = f"https://huggingface.co/datasets/{repo}/resolve/{revision}/{path}"
    for attempt in range(4):
        try:
            response = requests.get(url, timeout=(10, 45))
            response.raise_for_status()
            text = response.content.decode("utf-8")
            if path.endswith(".json"):
                json.loads(text)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(target)
            return text
        except (requests.RequestException, UnicodeDecodeError, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(1 + attempt)
    raise AssertionError("Unreachable")


def read_count(stats: dict, key: str) -> int:
    value = stats[key]
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid published {key}: {value!r}")
    return value


def annotation_count(stats: dict) -> int | None:
    annotation_stats = stats.get("annotations")
    if not annotation_stats or "number_of_annotated_documents" not in annotation_stats:
        return None
    value = read_count(annotation_stats, "number_of_annotated_documents")
    if value > read_count(stats, "number_of_samples"):
        raise ValueError("Published annotation coverage exceeds the source row count")
    return value


def annotation_distributions(stats: dict) -> dict[str, dict[str, int]] | None:
    fields = (stats.get("annotations") or {}).get("property_level_counts")
    if not fields:
        return None
    for name, counts in fields.items():
        if any(type(v) is not int or v < 0 for v in counts.values()) or sum(counts.values()) > read_count(stats, "number_of_samples"):
            raise ValueError(f"Invalid published counts for {name}")
    return fields


def quality_counts(stats: dict) -> dict[str, int] | None:
    values = (stats.get("annotations") or {}).get("property_level_counts", {}).get("content_quality")
    if values is None:
        return None
    if any(type(v) is not int or v < 0 for v in values.values()) or sum(values.values()) > read_count(stats, "number_of_samples"):
        raise ValueError("Invalid published quality-label counts")
    allowed = {"unacceptable", "poor", "adequate", "good", "excellent"}
    if set(values) - allowed:
        raise ValueError("Quality taxonomy changed; review before comparing")
    return values


def source_domains(card: str) -> dict[str, str]:
    match = re.search(
        r"<!-- START-DOMAIN TABLE -->(.*?)<!-- END-DOMAIN TABLE -->",
        card,
        re.DOTALL,
    )
    if not match:
        raise ValueError("Dataset card has no published domain table")
    result = {}
    for line in match.group(1).splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) != 3 or cells[0] == "Domain" or cells[0].startswith((":", "-", "**")):
            continue
        for source in re.findall(r"\[([^\]]+)\]", cells[1]):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", source):
                raise ValueError(f"Unexpected source identifier: {source!r}")
            if source in result:
                raise ValueError(f"Source appears in multiple domain rows: {source}")
            result[source] = cells[0]
    if not result:
        raise ValueError("Dataset card domain table is empty")
    return result


def build_dataset(snapshot: tuple, cache: Path, workers: int) -> dict:
    identifier, language, language_code, revision = snapshot
    repo = f"danish-foundation-models/{identifier}-dynaword"
    base = f"https://huggingface.co/datasets/{repo}"
    card = fetch_text(repo, revision, "README.md", cache)
    version_match = re.search(r"\|\s*\*\*Version\*\*\s*\|\s*(\d+\.\d+\.\d+)", card)
    if not version_match:
        raise ValueError(f"No version identifier in {repo}")
    if "Llama 3 tokenizer" not in card:
        raise ValueError(f"Tokenization methodology changed in {repo}; review before comparing")
    root_stats = json.loads(fetch_text(repo, revision, "descriptive_stats.json", cache))
    mapping = source_domains(card)

    def build_source(source: str) -> dict:
        stats_path = f"data/{source}/descriptive_stats.json"
        stats = json.loads(fetch_text(repo, revision, stats_path, cache))
        return {
            "id": source,
            "name": source,
            "domain": mapping[source],
            "records": read_count(stats, "number_of_samples"),
            "tokens": read_count(stats, "number_of_tokens"),
            "annotated": annotation_count(stats),
            "quality": quality_counts(stats),
            "annotation_distributions": annotation_distributions(stats),
            "url": f"{base}/blob/{revision}/data/{source}/{source}.md",
            "stats_url": f"{base}/resolve/{revision}/{stats_path}",
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        sources = list(executor.map(build_source, sorted(mapping)))

    records = read_count(root_stats, "number_of_samples")
    tokens = read_count(root_stats, "number_of_tokens")
    for metric, expected in (("records", records), ("tokens", tokens)):
        actual = sum(source[metric] for source in sources)
        if actual != expected:
            raise ValueError(
                f"{repo}: source {metric} total {actual} differs from root {expected}; "
                "review the release instead of publishing inconsistent totals"
            )

    domains = []
    for domain in sorted(set(mapping.values())):
        members = [source for source in sources if source["domain"] == domain]
        domains.append({
            "name": domain,
            "records": sum(source["records"] for source in members),
            "tokens": sum(source["tokens"] for source in members),
            "sources": len(members),
        })

    annotated = annotation_count(root_stats)
    notes = [
        "Records are published rows. Sources use different document and segment lengths, "
        "so record counts do not measure the same text volume across languages.",
        "Domain labels are the publisher's source classifications, preserved without "
        "merging categories such as Spoken, Conversation, and Speeches.",
        "Sources and domain totals exactly match the published corpus record and token totals.",
        "These are release statistics, not a statement that this website indexes every language.",
    ]
    if annotated is None:
        notes.append(
            "No automated annotation coverage count is published in this release. "
            "The dataset card describes source metadata but no annotation layer. "
            "Missing coverage is represented as null, not zero."
        )
    else:
        notes.append(
            "Annotation coverage is the published number of rows with machine-generated "
            "metadata from ellamind/propella-1-4b. It is not human annotation, "
            "human validation, or a guarantee of quality or privacy."
        )
        known = [source["annotated"] for source in sources if source["annotated"] is not None]
        if len(known) == len(sources) and sum(known) != annotated:
            notes.append(
                f"Published root annotation count ({annotated}) differs from the sum "
                f"of source annotation counts ({sum(known)}); root coverage is retained."
            )
        elif len(known) != len(sources):
            notes.append(
                f"{len(sources) - len(known)} sources have no published annotation "
                "coverage count; their coverage remains unknown. Root coverage is retained."
            )
    if identifier == "danish":
        notes.append(
            f"The published comparison release is v{version_match.group(1)}. "
            f"The record explorer currently indexes the earlier {INDEXED_DANISH['version']} "
            f"snapshot: {INDEXED_DANISH['records']:,} records, "
            f"{INDEXED_DANISH['tokens']:,} tokens, and {INDEXED_DANISH['sources']} sources."
        )
    if identifier == "norwegian":
        notes.append("Norwegian includes Bokmål and Nynorsk; this catalog compares the combined corpus.")

    return {
        "id": identifier,
        "name": f"{language} Dynaword",
        "language_code": language_code,
        "repo": repo,
        "revision": revision,
        "version": "v" + version_match.group(1),
        "url": f"{base}/tree/{revision}",
        "records": records,
        "tokens": tokens,
        "annotated": annotated,
        "quality": quality_counts(root_stats),
        "annotation_distributions": annotation_distributions(root_stats),
        "sources": sources,
        "domains": domains,
        "stats_url": f"{base}/resolve/{revision}/descriptive_stats.json",
        "tokenizer": "Llama 3",
        "count_basis": "Exact published descriptive_stats.json values; source-to-domain "
        "mapping from the dataset card at the same pinned revision.",
        "notes": notes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "web/public/data/corpora.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".cache/corpus-catalog")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    datasets = []
    for snapshot in SNAPSHOTS:
        dataset = build_dataset(snapshot, args.cache, args.workers)
        datasets.append(dataset)
        print(f"{dataset['name']} {dataset['version']}: "
              f"{dataset['records']:,} records, {len(dataset['sources'])} sources; totals verified", flush=True)
    catalog = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "datasets": datasets,
        "indexed_danish": INDEXED_DANISH,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {args.output} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

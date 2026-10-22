# Scandinavian Dynaword explorer

[Public website](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/) · [MVP plan](MVP.md) · [Wishlist](WISHLIST.md)

An interactive overview of Danish, Norwegian, Swedish, Icelandic and Faroese Dynaword, with full-corpus browsing for all five languages and keyword/semantic search enabled per completed language index. GitHub Pages serves the static frontend; an API-only Hugging Face Space serves search and Nordic record exploration. The overview and comparison pages need no backend connection.

## Current release

- A project introduction based on the Scandinavian Dynaword poster and [original paper](https://arxiv.org/abs/2508.02271).
- Interactive domain comparisons across all five languages: select languages and domains, switch records/tokens and counts/percentage shares, inspect exact values.
- An interactive annotation chart with nine fields: quality, PII, integrity, content ratio/length, information density, educational value, reasoning and safety. Domain and category selections update the comparison.
- A language selector opens complete Norwegian, Swedish, Icelandic and Faroese record browsing through revision-checked Hub row access. Domain/source slicing, arbitrary row jumps and original-text reading cover every published record. Norwegian, Icelandic and Faroese use complete local annotation/length indexes; Swedish has no published annotation layer. Complete additional-language text and semantic indexes are built by bounded CPU jobs and enabled automatically after validation.
- Full Danish record browsing, original-text previews and incremental reading, with intersecting source, domain, quality, PII, annotation and token-length filters.
- Text and semantic search beside the row browser. Selection statistics have a separate view with clickable distributions and histogram range selection.
- Browser-local review tags and JSON export. Tags are never uploaded and do not change the corpus.
- Release versions, source licences, mobile layouts and the supplied red Dynaword logo.

**Topics are deferred.** No topic map, topic navigation or topic-model dependency is loaded by the current website. Earlier research scripts and backend sidecars remain available for future work. A tour, appearance controls, analyst agent and contextual passage embeddings are also outside this release.

## Data scope

The comparison catalog uses pinned published statistics across **555 source collections**, **603,321,227 records** and **63,447,970,622 Llama 3 tokens**:

| Language | Comparison release | Records | Sources |
| --- | --- | ---: | ---: |
| Danish | v1.2.27 | 7,402,626 | 52 |
| Norwegian | v0.0.22 | 4,574,555 | 37 |
| Swedish | v0.0.17 | 551,087,777 | 442 |
| Icelandic | v0.0.15 | 39,845,380 | 18 |
| Faroese | v0.0.8 | 410,889 | 6 |

Record boundaries vary across sources and languages; token counts are the better volume comparison. Domain labels remain the publisher's source classifications. Quality percentages use **all records in the selected language/domain**, including unreported labels. Quality labels are machine predictions, not a human assessment or cross-language quality benchmark. Swedish does not publish these quality counts.

The row explorer separately indexes **Danish v1.2.23**, revision `c2f51be06848df26b5aad71cafeec1bc6064b1cc`: 7,399,685 records, 50 sources, 9,813,858,821 record-derived tokens, and 5,662,370 records with quality labels. The published token summary differs by 17,719, entirely in `tidsskrift-dk`; interactive explorer statistics consistently use record-derived totals. The newer published comparison release is clearly distinguished in the interface.

## Run locally

Requirements: Node.js 22.12+, Python 3.11+, and about 45 GB of disk space for preparation and indexes.

```sh
python3 -m pip install -r server/requirements.txt
npm --prefix web install
python3 scripts/prepare_data.py
python3 scripts/build_text_index.py
python3 scripts/build_semantic_index.py
python3 scripts/build_ann_index.py
python3 scripts/build_corpus_catalog.py
python3 scripts/dev.py
```

Open **http://localhost:5173**. The API is on port 8000. For an existing prepared installation, run only `python3 scripts/dev.py` after stopping previous servers. The static overview and comparisons can also be developed with `npm --prefix web run dev` alone.

Preparation resumes completed sources and checks annotation joins against complete source counts. Generated data lives in ignored `.cache/`. To change the search snapshot, move the old cache aside and rebuild metadata, texts and vectors together with the new revision. Do not mix record identities from different builds.

`build_corpus_catalog.py` downloads only public README and descriptive-statistics files at pinned revisions. It verifies source and domain sums against each root total, validates all nine annotation distributions, and saves `web/public/data/corpora.json`. To refresh comparisons, review and update its `SNAPSHOTS` list, regenerate, and commit the catalog. A new catalog does not update the separate Danish search index.

## Search and architecture

The API uses FastAPI and DuckDB for complete-corpus metadata filtering/aggregation, and Tantivy BM25 for original-text retrieval. Only requested aggregates and rows reach the browser. ECharts is loaded on demand for Danish selection statistics; the comparison graphs use lightweight interactive browser elements.

The semantic baseline uses the first 100,000 Danish fastText vocabulary entries, lowercase Unicode word tokenization, normalized word vectors weighted by `rank / (rank + 500)`, a count-weighted sum over the complete original, and L2 normalization. Vectors are stored as float16. All 7,399,685 records are processed; **7,398,723 have usable vectors**, while 962 remain browsable and text-searchable.

A Faiss IVF1024/SQ8 index covers every usable vector and accelerates candidate selection. Metadata filters apply inside the index before selecting candidates. Original vectors then remove quantization error from candidate scores. The best 1,200 candidates are reranked using 45% document cosine and 55% weighted query-concept coverage over their original text; up to 300 are returned. Restrictive selections of at most 100,000 records, or an unavailable/stale ANN index, use exact cosine retrieval. Query results are cached for repeated queries and pagination.

This is approximate **document retrieval**, not a contextual passage model. Rare words, OCR, historical spelling and long documents mixing subjects remain limitations. Row previews show the beginning of each original rather than a claimed best-matching passage. Metadata filters define chart populations; search only changes the ranked row list.

The ANN manifest binds the artifact to its dataset revision, record count, metadata fingerprint and embedding matrix hash. `build_ann_index.py` reproducibly builds it from existing vectors without changing originals or record identities. Restart the API after replacing artifacts to clear caches.

## Validation

```sh
python3 -m pip install -r server/requirements-dev.txt
python3 scripts/validate_data.py
python3 -m unittest discover -s server -v
npm --prefix web run build
# With the API and frontend running:
npm --prefix web exec playwright install chromium
npm --prefix web run test:e2e
```

Tests cover aggregate/filter consistency, missing values, reader pagination, text/semantic filtering, stale indexes, ANN record identity, deployment integrity, interactive comparisons, review export, mobile widths, chart brushing and service wake-up recovery. Legacy topic backend tests are retained separately from current website functionality.

## Deployment and licensing

GitHub Actions builds and deploys `web/dist/`. Set repository variable `VITE_API_BASE_URL` to the public HTTPS API origin; publication verifies full text/vector coverage and browser CORS. The API and its checksum-verified pinned artifacts run separately in a Hugging Face CPU Upgrade Docker Space (8 vCPU, 32 GB RAM), with sleep disabled and additional-language indexes mounted from a public bucket. Restarting that service affects record search, while the overview/comparison pages remain available.

See [Hugging Face deployment instructions](deploy/huggingface/README.md) or the [alternative Docker/Caddy setup](deploy/README.md). Updating GitHub alone does not update the API Space.

Website source code is [MIT licensed](LICENSE). The website licence does not relicense corpus texts, annotations, model weights or derived vectors; see [NOTICE.md](NOTICE.md) and individual source cards. Danish fastText vectors are attributed to Grave, Bojanowski, Gupta, Joulin and Mikolov (2018), *Learning Word Vectors for 157 Languages*, and distributed under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Retain applicable attribution and share-alike terms when distributing derived vectors.

## Additional-language record indexes

Install `server/requirements-dev.txt` for the index builder. `python3 scripts/build_annotation_indexes.py` projects IDs, token counts and nine annotation fields from the pinned source Parquet files, joins by document ID and saves compact arrays in `.cache/corpus-annotations`. Each language has a source-offset manifest, dictionary-coded labels and document identity checksums. Filtering counts every matching record before pagination; it never filters only a sample. Original texts are fetched on demand from each source configuration and verified against the index identity.

`deploy/huggingface/annotations-source.json` pins these artifacts separately from the Danish search snapshot. The Docker build verifies checksums and adds the compact indexes after the existing base data layer. Refresh both the catalog and indexes together when updating a release. Upstream text requests reject revision changes and incomplete responses. Completed local text/vector indexes replace upstream browsing and enable search per language. Until then the revision-checked browsing bridge remains available.


New-language semantic search uses `minishlab/potion-multilingual-128M` (256
dimensions, revision pinned in `deploy/huggingface/search-config.json`) through
Model2Vec 0.10.0. This CPU-efficient static embedding model is distilled from
BGE-M3; it is not a contextual BGE-M3 encoder. Every record is processed,
with long texts split and aggregated. Faiss IVF/PQ32 candidate retrieval is
followed by cosine reranking from the original float16 vectors. Keyword retrieval
uses Tantivy BM25. Both modes apply source, annotation and length filters
before candidate selection. Missing usable vectors affect semantic coverage
only; all records remain browsable and keyword searchable.

See the [bounded build and deployment procedure](deploy/huggingface/README.md)
for storage mounts, complete-index validation and cost limits. No topic model
is part of these builds.

# Danish Dynaword explorer

An interactive corpus explorer for the complete Danish Dynaword dataset. The frontend is a static React application; the data API runs separately.

## Run locally

Requirements: Node.js 22.12 or newer, Python 3.11 or newer, and roughly 45 GB of free disk space for preparation and the generated indexes. The preparation scripts download public dataset files.

```sh
python3 -m pip install -r server/requirements.txt
npm --prefix web install
python3 scripts/prepare_data.py
python3 scripts/build_text_index.py
python3 scripts/build_semantic_index.py
python3 scripts/dev.py
```

Open **http://localhost:5173**. The API runs on port 8000. Both services bind to the loopback interface.

Preparation resumes completed sources. A source is committed only after its joined record count is checked. A partial import is never marked as the complete corpus. The second script stores the original texts in a local search index and removes temporary source downloads after each successful commit.

All generated data lives in `.cache/`, which is excluded from Git. To reuse this installation, run only `python3 scripts/dev.py` after stopping any existing development servers.

## What works

- Full-corpus totals and linked source/domain charts, with record/token measures.
- Clickable annotation distributions, explicit missing labels, and per-field coverage.
- Source, domain, quality, PII, annotation-category, and token-range filters.
- A document-length histogram with drag selection and equivalent numeric controls.
- Paginated records with original-text previews and a scrollable document reader.
- Full-text search across the original texts, with the same metadata filters.
- Experimental semantic search using pretrained Danish word vectors, also filtered before retrieval.
- A Turftopic landscape with zoom, pan, point-to-reader access, topic keywords, full-corpus topic counts, and linked topic filters for both search modes.
- Domain, quality, and PII overlays on the map, with a keyboard-accessible list of mapped records.
- Source documentation, licences, and a pinned dataset revision.
- A responsive layout and keyboard-accessible alternatives to chart interactions.

**Semantic search is a word-vector beta.** It averages pretrained Danish fastText vectors over each complete original document, downweights common words, and retrieves cosine-similar documents. It then reranks the best 1,200 candidates by how well they cover the query’s concepts, using word-vector similarities, and returns up to 300 results. All documents are processed; records with no recognized vocabulary receive no vector and are counted separately in the About panel. This baseline does not yet provide the contextual passage index proposed in the plan: rare words, OCR, and mixed-topic long documents are limitations. Exact text search uses BM25. The tour, appearance controls, and analyst agent remain outside this release.

## Turftopic landscape

Open **http://localhost:5173/#topics**. The map and topic distribution are interactive browser charts, and every dot opens its original document. Selecting a topic filters the complete row browser and both search modes. Counts follow metadata filters; the topic list retains the other topics for comparison. Search queries narrow the record browser, while charts describe the metadata/topic selection.

The user chose discovered topics as the main view after considering an annotation-first alternative. The existing annotations serve as overlays; they are not used as topic labels or clustering targets.

The first model uses [Turftopic’s Top2Vec workflow](https://x-tabdeveloping.github.io/turftopic/tutorials/arxiv_ml/) with the existing Danish fastText document vectors. It fits 21,396 records, sampled without replacement with seed 42, up to 500 per source across all 50 sources. HDBSCAN discovers 123 clusters in a five-dimensional UMAP space; Turftopic reduces these to 28 groups. A separate two-dimensional UMAP provides map coordinates. Keywords use Turftopic c-TF-IDF on excerpts of up to 6,000 characters from each sampled original (beginning, middle, end); embeddings cover complete originals.

**Full-corpus coverage:** 7,398,723 records receive the nearest non-noise topic centroid by cosine similarity, checked against `Turftopic.transform`. The 962 zero-vector records remain unassigned, browsable, and text-searchable. Assignments also include fit-time clustering outliers. A nearest-topic assignment is a forced approximation, not a validated subject label or a confidence score. Some groups reflect spelling, language, writing style, or source conventions rather than subjects. A sampled map is not a corpus-density estimate: small sources are deliberately overrepresented, and a selection can have matching full-corpus records with no mapped dots.

To rebuild after the existing metadata/text/vector pipelines finish:

```sh
python3 -m venv --system-site-packages .venv-topics
.venv-topics/bin/python -m pip install -r server/requirements-topics.txt
.venv-topics/bin/python scripts/build_topics.py
python3 scripts/validate_topics.py
```

Topic fitting dependencies are needed only for preparation. The API serves compact Parquet sidecars and JSON; it does not load Turftopic, PyTorch, or the fitted model. The corpus database and original indexes are not modified. Topic artifacts are bound to the dataset revision and metadata fingerprint. The build caches sampled texts, vectors, the model, and coordinates, and rejects changed build settings against an existing topic cache. Restart the API after rebuilding to clear cached views and topic queries.

Full-text topic filtering intersects a topic’s document keys inside Tantivy before ranking, counting, and pagination. Semantic filtering applies the topic membership before scanning candidate vectors. Neither search mode post-filters a sampled result page.

## Data and architecture

Source: [Danish Dynaword](https://huggingface.co/datasets/danish-foundation-models/danish-dynaword). The selected revision is saved in `.cache/manifest.json`; reruns reuse the completed snapshot. To change revisions, move the existing `.cache/` directory aside and rebuild with `--revision` so metadata, texts, and vectors stay aligned. Semantic indexes also record a fingerprint of the metadata database to protect record identities.

`prepare_data.py` projects the ID, source, token-count, and date columns from all source Parquet files, joins their annotation files within each source, and writes a DuckDB index. It reads published summaries for comparison but computes interactive statistics from the complete joined records. Descriptions and licences come from the source cards.

`build_text_index.py` builds a Tantivy index containing every original text and its filter fields. Stored texts support local previews and full reading. Index coverage and revision are recorded in `.cache/search_manifest.json`. The public Hugging Face reader is a fallback while source text is not yet stored locally; its revision is checked before use.

The FastAPI service returns aggregates and batches of records. The browser never downloads the corpus wholesale. ECharts renders interactive canvas charts from structured data. Both search modes update the record list while charts continue to describe the selected metadata slice.

Annotation percentages use all records in the selected slice as their displayed denominator, with coverage reported separately. Content-type labels may overlap. Source domains and document content types remain separate. Automated PII labels are not privacy guarantees.

`build_semantic_index.py` reads the locally stored originals. The encoder uses the first 100,000 entries of the frequency-sorted Danish fastText vocabulary, lowercase Unicode word tokenization, normalized word vectors weighted by `rank / (rank + 500)`, a count-weighted sum, and L2 normalization. Document vectors are stored as float16. Retrieval scans the eligible vectors exactly. Candidates are reranked with 45% document cosine and 55% weighted query-concept coverage (the best word-vector match for each query concept across the complete candidate text). Model details, a vocabulary hash, and processing coverage are recorded in `.cache/semantic_manifest.json`; the API manifest also describes the retrieval settings. This is document retrieval, so row previews show the start of the original text rather than a claimed best-matching passage.

Vector attribution: [Danish fastText word vectors](https://fasttext.cc/docs/en/crawl-vectors.html), Grave, Bojanowski, Gupta, Joulin and Mikolov (2018), *Learning Word Vectors for 157 Languages*, distributed under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). The local vocabulary is a normalized, weighted subset of those vectors; retain attribution and the applicable share-alike terms when distributing the derived vectors.

## Snapshot audit

The localhost version pins `c2f51be06848df26b5aad71cafeec1bc6064b1cc`.

| Measurement | Recomputed from the complete records |
| --- | ---: |
| Records | 7,399,685 |
| Sources | 50 |
| Tokens | 9,813,858,821 |
| Records with annotation labels | 5,662,370 |
| Records processed for semantic search | 7,399,685 |
| Records with usable semantic vectors | 7,398,723 |

The published total is 9,813,876,540 tokens, a difference of 17,719. This is entirely accounted for by `tidsskrift-dk`: its records sum to 50,009,937 tokens, while its published source summary reports 50,027,656. Charts and filters consistently use the record-derived counts. Record and annotation totals match the published summary. Missing annotations remain distinct from explicit negative labels.

## Validation

```sh
python3 -m pip install -r server/requirements-dev.txt
python3 scripts/validate_data.py
python3 scripts/validate_topics.py
npm --prefix web test
npm --prefix web run build
# With both development services running and the full index ready:
npm --prefix web exec playwright install chromium
npm --prefix web run test:e2e
```

Backend checks cover combined filters, aggregate consistency, missing values, multi-label counts, pagination, and untrusted filter input. End-to-end checks exercise the linked charts/filters, reader, search, and mobile layout.

The completed preparation uses about 30 GB in `.cache/`. Full text covers every record; 962 records contain no recognized vector vocabulary. Local checks returned 6,546 text matches for “vindmøller” in about 0.7 seconds. Semantic queries are slower because this first version scans the vectors and reranks candidates; results are cached for pagination and repeated queries. These measurements describe this development machine, not a hosting guarantee.

The snapshot audit and backend/browser checks cover complete-corpus consistency, topic/text/semantic filter intersections, sampled versus full-corpus counts, stale model rejection, map controls, original-text access, and mobile layout. The topic audit also independently verifies centroid assignments for 4,815 records spanning every source. Manual Danish relevance checks covered renewable energy, cancer treatment, and literature. The word-vector beta remains exploratory, especially for short historical fragments and long documents with multiple topics.

## GitHub Pages deployment

The frontend builds to `web/dist/` with relative asset paths:

```sh
VITE_API_BASE_URL=https://your-data-service.example npm --prefix web run build
```

The repository includes a GitHub Actions workflow to test, build, and publish that directory. The API, DuckDB database, full-text index, and vector files run separately in a Hugging Face Docker Space. Its image contains a checksum-verified, pinned serving snapshot. The workflow checks the public service and CORS before publication; deployment is skipped while the repository variable `VITE_API_BASE_URL` is unset.

See [Hugging Face backend instructions](deploy/huggingface/README.md) for CPU Basic hosting, artifact uploads and updates, or [deployment instructions](deploy/README.md) for the alternative Docker/Caddy server and Pages setup. The explorer is live at [Dynaword](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/), using the [public corpus API](https://v4ldelund-danish-dynaword-api.hf.space/docs). The interface uses the supplied Dynaword icon and a red-and-white theme, with distinct categorical colours for chart and map comparisons.

See [MVP.md](MVP.md) and [WISHLIST.md](WISHLIST.md) for the plan and future ideas.

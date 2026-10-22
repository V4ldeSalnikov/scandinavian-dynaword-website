# Hugging Face API and GitHub Pages frontend

The website runs on GitHub Pages. An API-only Docker Space serves the prepared
Danish corpus; there is no Space iframe or Gradio frontend in the website.

- Space: https://huggingface.co/spaces/V4ldeLund/danish-dynaword-api
- API origin: `https://v4ldelund-danish-dynaword-api.hf.space`
- Artifact repository: https://huggingface.co/datasets/V4ldeLund/danish-dynaword-explorer-index
- Website: https://v4ldesalnikov.github.io/scandinavian-dynaword-website/

## Hardware and storage

The Space uses **CPU Upgrade**: 8 vCPU, 32 GB RAM and 50 GB ephemeral disk,
at $0.03/hour (about $22 per month running continuously). Sleep is disabled.
The approved total budget is $50/month. Index builds use the same CPU job tier
with explicit timeouts; the first four builds reserve at most $6.60 combined.
No GPU or separately billed persistent disk is required.

The public bucket `V4ldeLund/scandinavian-dynaword-search` holds complete
additional-language indexes and build checkpoints, within the account's included
PRO public storage. It is mounted read-only at `/search-index`. The pinned
`minishlab/potion-multilingual-128M` model is mounted read-only at `/search-model`.
The serving API needs no token. Buckets avoid copying these large indexes onto
the Space's 50 GB local disk; first access can still incur remote reads.
Tantivy reader locks live in a temporary local directory; index data is accessed
through symlinks to the read-only mount. No index files are copied or rewritten.

The serving snapshot is approximately 32 GB (decimal), including original
texts, metadata, full-text/vector indexes and legacy topic artifacts. It is stored
in a public Hub dataset repository. The image build downloads the pinned
snapshot and verifies every file's SHA-256 and size. Data lives in one image
layer; waking a container does not rerun the download script. Pulling the
image to a fresh machine can still delay a cold start. Never retrain topics or
rebuild the corpus during API startup.

HF references: [hardware](https://huggingface.co/docs/hub/spaces-gpus),
[Docker Spaces](https://huggingface.co/docs/hub/spaces-sdks-docker),
[storage](https://huggingface.co/docs/hub/spaces-storage).

## Reproduce or update

1. Prepare all local indexes using the root README. Keep the dataset revision,
   metadata database, text index and vectors together. The current UI does not use topics.
2. Run `python3 scripts/package_runtime.py`. This stages only runtime files at
   `.cache/hf-runtime`, using hard links and checksums. Do not modify source
   indexes while uploading. Training caches and credentials are excluded.
3. Upload the generated `.gitattributes` **first**, in a separate commit. The
   custom Tantivy and `.faiss` extensions must use Hub large-file storage even when small;
   otherwise the Hub may reject them as binary Git content. Then upload the
   directory using `huggingface_hub` `HfApi.upload_folder` or the Hub CLI.
   Authenticate through a local login or
   an interactive hidden prompt; never put a token in a shell argument,
   tracked file, Docker build argument or Vite variable.
4. Once every file has uploaded, set `runtime-source.json` here to the artifact
   repository and its immutable 40-character commit SHA. Partial uploads must
   not become the serving revision.
5. Run `python3 scripts/stage_hf_space.py`. Upload `.cache/hf-space` to a public
   Docker Space on CPU Upgrade. `SPACE.md` becomes its root `README.md`. The
   image build downloads and validates all files before starting one Uvicorn
   worker on port 8000. Changes limited to server code reuse the data layer.
6. Wait for the Space to report Running, then verify:

   ```sh
   VITE_API_BASE_URL=https://v4ldelund-danish-dynaword-api.hf.space \
   PAGES_ORIGIN=https://v4ldesalnikov.github.io \
   python3 scripts/check_public_api.py
   ```

7. Set the GitHub repository Actions variable `VITE_API_BASE_URL` to the API
   origin above and run the Pages workflow. Verify the domain/quality graphs, browsing, search
   and the reader on the public site.

The running service downloads no private resources and needs no Hugging Face
token. Rotating a deployment token does not break the site. The public artifact
card and original source cards document licenses and attribution. Updating the
GitHub repository alone does not update Space code; repeat staging and uploading
when changing the backend. Frontend changes deploy through GitHub Actions.

## Build additional-language keyword and semantic indexes

`search-config.json` pins the multilingual model and sets the compute price,
job timeout and build budget ceilings. The builder reads every original record
at the revision in `web/public/data/corpora.json`; annotation identities and
source counts must match. It writes Tantivy BM25, 256-dimensional Model2Vec
vectors and a disk-backed Faiss IVF/PQ32 index. Retrieval applies metadata
filters before selecting candidates, then uses original float16 vectors to rerank.
Compressed vector blocks use bounded parallel reads and a 320 MB shared cache;
Faiss scans those blocks in memory rather than faulting pages from the remote
mount. Only the current page of original texts is loaded.
Danish keeps its existing fastText index and serving release.

Use a Python environment with `huggingface_hub==2.2.0` and a saved local login:

```sh
python scripts/launch_corpus_search.py faroese --timeout-hours 4
python scripts/launch_corpus_search.py norwegian icelandic swedish
```

The launcher records job IDs and maximum reserved charges in ignored
`.cache/corpus-search-jobs.json`, checks current hardware prices and refuses
duplicate jobs or reservations over $10. Default jobs stop after 72 hours.
`--retry-failed` resumes committed sources after a failed job, subject to the
remaining reservation. Keep the ledger when continuing work on another machine.

Each language/revision directory has `progress.json`. A `manifest.json` appears
only after complete source counts, annotation identities and vector self-retrieval
validation pass. `/api/corpora/{language}/search-status` controls the website's
search availability; partial builds never advertise full-corpus search. The
website checks every 30 seconds, so a completed index needs no frontend rebuild.
The self-retrieval check validates indexing, not multilingual relevance quality.

Attach these volumes with `HfApi.set_space_volumes`, preserving other mounts.
Read existing mounts from `HfApi.space_info(...).runtime.volumes`; the narrower
runtime endpoint may omit them.

- Bucket `V4ldeLund/scandinavian-dynaword-search` → `/search-index`, read-only.
- Model `minishlab/potion-multilingual-128M` at the revision in `search-config.json`
  → `/search-model`, read-only.

Before releasing a complete index, check keyword/semantic queries, intersected
annotations, original-text identity and first/warm request latency through the
public API. Large corpus build duration and live concurrency are measured limits;
the hardware upgrade alone does not establish a search latency guarantee.

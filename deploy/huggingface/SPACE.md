---
title: Scandinavian Dynaword API
emoji: 📚
colorFrom: red
colorTo: red
sdk: docker
app_port: 8000
base_path: /docs
startup_duration_timeout: 1h
short_description: Full-corpus search API for the Dynaword explorer
datasets:
  - danish-foundation-models/danish-dynaword
  - danish-foundation-models/norwegian-dynaword
  - danish-foundation-models/swedish-dynaword
  - danish-foundation-models/icelandic-dynaword
  - danish-foundation-models/faroese-dynaword
  - V4ldeLund/danish-dynaword-explorer-index
tags:
  - dynaword
  - fastapi
---

# Scandinavian Dynaword API

The interactive website is on **[GitHub Pages](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/)**.
This Docker Space only serves its data API. [API documentation](/docs).

The API covers all 7,399,685 Danish Dynaword records: paginated browsing,
BM25 text search, Danish fastText semantic search with filtered Faiss retrieval,
and annotation filters. The website compares all five Scandinavian corpora
using published release statistics. Complete record browsing also covers Norwegian, Swedish, Icelandic and Faroese. Norwegian, Icelandic and Faroese have local annotation/length indexes; Swedish has no published annotation layer. Danish search uses v1.2.23. Additional-language keyword and semantic search become available as each complete, validated index is published; `/api/corpora/{language}/search-status` reports current coverage. The new semantic indexes use the pinned multilingual Model2Vec POTION model and disk-backed Faiss retrieval.
Topics are deferred from the current website.

Source, reproduction instructions and deployment files:
https://github.com/V4ldeSalnikov/scandinavian-dynaword-website.
`runtime-source.json` and `annotations-source.json` pin the serving artifacts to an immutable Hub commit.
Checksums are verified while building the image. Original texts retain their
source licenses; derived fastText vectors use CC BY-SA 3.0. See the index
repository card and `manifest.json` for attribution and source-specific terms.

Runs on CPU Upgrade (8 vCPU, 32 GB RAM), with sleep disabled. Additional-language
indexes live in a mounted public bucket. Query speed depends on corpus size,
cache state and load.
No Hub credentials are needed by the running service or the website.

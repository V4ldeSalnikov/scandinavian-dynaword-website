---
title: Danish Dynaword API
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
  - V4ldeLund/danish-dynaword-explorer-index
tags:
  - dynaword
  - fastapi
---

# Danish Dynaword API

The interactive website is on **[GitHub Pages](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/)**.
This Docker Space only serves its data API. [API documentation](/docs).

The API covers all 7,399,685 Danish Dynaword records: paginated browsing,
BM25 text search, Danish fastText semantic search with filtered Faiss retrieval,
and annotation filters. The website compares all five Scandinavian corpora
using published release statistics; full record search covers Danish v1.2.23.
Topics are deferred from the current website.

Source, reproduction instructions and deployment files:
https://github.com/V4ldeSalnikov/scandinavian-dynaword-website.
`runtime-source.json` pins the serving artifacts to an immutable Hub commit.
Checksums are verified while building the image. Original texts retain their
source licenses; derived fastText vectors use CC BY-SA 3.0. See the index
repository card and `manifest.json` for attribution and source-specific terms.

Runs on CPU Basic (2 vCPU, 16 GB RAM). The free hardware can sleep after
inactivity; requests wake it. Warm query speed depends on corpus size and load.
No Hub credentials are needed by the running service or the website.

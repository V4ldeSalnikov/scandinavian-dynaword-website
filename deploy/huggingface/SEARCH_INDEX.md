# Scandinavian Dynaword search indexes

Complete keyword and semantic search artifacts for the
[Scandinavian Dynaword explorer](https://v4ldesalnikov.github.io/scandinavian-dynaword-website/).

Each language directory contains a pinned dataset revision. `progress.json`
describes a build in progress; `manifest.json` is published only after validation
of complete source counts, annotation identities and semantic index coverage.
Intermediate files are checkpoints, not independently supported dataset releases.

## Sources and licensing

- [Norwegian Dynaword](https://huggingface.co/datasets/danish-foundation-models/norwegian-dynaword)
- [Swedish Dynaword](https://huggingface.co/datasets/danish-foundation-models/swedish-dynaword)
- [Icelandic Dynaword](https://huggingface.co/datasets/danish-foundation-models/icelandic-dynaword)
- [Faroese Dynaword](https://huggingface.co/datasets/danish-foundation-models/faroese-dynaword)

Original texts and annotations retain their source-specific licenses and
attribution, documented in the pinned dataset cards and individual source cards.
This bucket does not apply a blanket license to those records.

Semantic vectors use the MIT-licensed
[minishlab/potion-multilingual-128M](https://huggingface.co/minishlab/potion-multilingual-128M)
model at revision `73908c3438cf03b6a01bcb9611d62b23d0726f08`, with Model2Vec 0.10.0.
The model license does not relicense the original corpora.

Build and API code is [MIT licensed](https://github.com/V4ldeSalnikov/scandinavian-dynaword-website/blob/main/LICENSE).
Reproduction and bounded compute instructions are in the
[deployment documentation](https://github.com/V4ldeSalnikov/scandinavian-dynaword-website/blob/main/deploy/huggingface/README.md).

The `build/` directory contains immutable, content-addressed build scripts and
catalog snapshots. `probe-v1/` is a small infrastructure pilot, not the search
index exposed by the website. No topic model is used.

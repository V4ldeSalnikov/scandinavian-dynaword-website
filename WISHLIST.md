# Dynaword website wishlist

A living wishlist for exploring the Danish, Norwegian, Swedish, Icelandic, and Faroese Dynaword datasets. This captures preferences and possibilities; it is not a committed implementation plan.

The proposed Danish-only first release is defined in [MVP.md](MVP.md).

## Inspiration: Nomic Atlas

Reference: [Nomic Atlas](https://atlas.nomic.ai/discover)

### Browse the underlying rows

- [ ] Let users inspect the actual dataset rows and scroll through their contents.
- [ ] Make it easy to read the text and associated metadata while exploring a visualisation.

The appeal: users can move from an interesting pattern to the underlying data and understand what the plot represents.

### Guided first-visit tour

- [ ] Offer a tour that introduces the main features when someone first visits.
- [ ] Guide users through browsing rows, exploring plots, searching, and changing the display.

Suggested details: make the tour skippable and available to replay later.

### An analyst agent that creates visualisations — exploratory

- [ ] Explore an assistant inspired by Atlas Analyst.
- [ ] Extend the idea so users can describe the plots or visualisations they want in natural language and have them generated dynamically.

Possible requests:

- “Compare the domain distributions of Danish and Norwegian Dynaword.”
- “Show document lengths by source.”
- “Plot the proportion of records flagged for PII by source, where those annotations are available.”

Suggested detail: show which data, filters, and measurements the agent used so users can inspect the result.

Open question: should the first version configure a supported set of chart types, or support more flexible generated visualisations?

### Text and vector search — approach undecided

- [ ] Support searching for relevant texts within the datasets.
- [ ] Explore vector search for finding texts by meaning, even when the wording differs.
- [ ] Consider keeping text search for exact words and phrases.

Preference to investigate: vector search alone might be sufficient or preferable. Keep the choice between vector-only, text-only, and combined search open for now.

### Adjustable aesthetics and colours

- [ ] Let users change the aesthetics and colours of visualisations.

Possible controls to explore: colour palettes, light/dark appearance, point size and opacity, and label visibility. These are suggestions rather than settled requirements.

## Inspiration: WIMBD

References: [WIMBD](https://wimbd.apps.allenai.org/) · [Corpora and access information](https://wimbd.apps.allenai.org/corpora)

WIMBD is a strong overall reference for understanding and comparing what is inside large text corpora.

The access restriction described on its corpora page concerns the indexed corpora and Elasticsearch access keys, which are provided on request. It does not mean the project website itself is private. The quoted access note also describes restrictions on access to particular corpora, including LAION.

### A more openly accessible corpus explorer

- [ ] Aim for public exploration of Dynaword without having to request individual corpus-search access keys.
- [ ] Make corpus analysis and comparison a central part of the website.
- [ ] Let users move between aggregate statistics and the records behind them.

Public access should follow the permissions of the constituent data sources. The goal is a more accessible exploration experience; the access model for an optional analyst agent remains undecided.

### Use Dynaword's recently added annotation layer

- [ ] Use the existing Dynaword annotations to enrich filtering, visualisations, and comparisons.
- [ ] Include PII detection and privacy-related annotations.
- [ ] Include other available annotations, rather than limiting the explorer to privacy analysis.
- [ ] Let users inspect annotations alongside the underlying text.

Possible analyses to explore:

- Compare annotation distributions across sources or languages where coverage permits.
- Filter records by annotation values and inspect examples.
- Explore content type, quality, audience, educational level, or regional relevance where those fields are available.

Suggested presentation rule: distinguish automated annotations from verified facts, and distinguish missing annotations from negative findings. A record with no PII flag should not be presented as a guarantee that it contains no personal information.

## Decisions to revisit

- Search: vector-only or a combination of semantic and exact text search?
- Analyst agent: which kinds of dynamically generated plots should it support first?
- Appearance: which visual controls are useful enough to expose?
- Annotation coverage: which fields and dataset revisions are available for each language?

## Dataset references

- [Danish Dynaword](https://huggingface.co/datasets/danish-foundation-models/danish-dynaword)
- [Norwegian Dynaword](https://huggingface.co/datasets/danish-foundation-models/norwegian-dynaword)
- [Swedish Dynaword](https://huggingface.co/datasets/danish-foundation-models/swedish-dynaword)
- [Icelandic Dynaword](https://huggingface.co/datasets/danish-foundation-models/icelandic-dynaword)
- [Faroese Dynaword](https://huggingface.co/datasets/danish-foundation-models/faroese-dynaword)

Potential topic-analysis library: [Turftopic](https://x-tabdeveloping.github.io/turftopic/).

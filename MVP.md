# Danish Dynaword explorer — MVP plan

**Status:** Localhost version implemented and validated, including Turftopic. GitHub publication is now authorized. Pages automation and API server configuration are prepared; a public HTTPS API host is required to make the complete explorer available online.

## Implementation decisions for the first review

- **Complete corpus required:** following your clarification, this version uses all 7,399,685 Danish records across 50 sources for browsing, filtering, and text search. No sample is presented as the corpus.
- **Localhost first:** React/Vite + interactive ECharts, served with a local FastAPI/DuckDB/Tantivy data service. The static frontend can move to GitHub Pages later; full-corpus queries need a separate data-service host.
- **Two search modes:** full-corpus BM25 text search and an experimental Danish fastText semantic baseline. Every original document is processed for vectors; records without recognized words are excluded from vector ranking and their coverage is reported explicitly. Semantic retrieval compares all usable vectors within the active metadata filters, reranks 1,200 candidates for query-concept coverage, and returns up to 300 documents. Coverage: 7,398,723 usable vectors; 962 records without recognized words remain available through browsing and text search.
- **Remaining semantic refinement:** the first implementation averages word vectors over complete documents. Contextual passage embeddings, matched-passage previews, and long-document passage ranking remain future work; the UI calls the current mode a beta.
- **Topic landscape added:** discovered Turftopic topics are the chosen focus, with existing annotations available as overlays. The interactive map shows a clearly labelled, source-balanced sample of 21,396 records; 28 learned groups have assignments across all 7,398,723 usable corpus vectors. The 962 unassigned records remain browsable/text-searchable. Topic selection filters full-corpus counts, rows, and both search modes. Automatic keywords and forced nearest-topic assignments remain exploratory.
- **Verified snapshot:** `c2f51be06848df26b5aad71cafeec1bc6064b1cc`. Totals: 7,399,685 records, 9,813,858,821 tokens, and 5,662,370 annotated records. The published token summary is 17,719 higher; the discrepancy comes from `tidsskrift-dk`, and interactive figures use the actual record sums. See [README.md](README.md#snapshot-audit).

The sections below retain the feature plan and make the remaining refinements explicit.

This is a proposed first release drawn from [WISHLIST.md](WISHLIST.md). The wishlist remains the home for longer-term ideas.

## 1. Goal

Build a public website where someone can understand what is in Danish Dynaword, explore its annotations, find relevant texts, and inspect the underlying rows.

A typical visit should look like this:

> See the corpus composition → select a source or annotation value → see the charts update → scroll through matching rows → open a text and its metadata.

Semantic search adds another entry point: describe a subject in Danish and read relevant texts from the selected sources.

## 2. Scope

### Direction from our discussion

- Start with **Danish Dynaword only**.
- Leave the guided tour out of the first release.
- Use one consistent visual style; leave user-adjustable aesthetics and colours for later.
- Preserve the ability to inspect real rows and use the existing annotation layer.
- Make visualisations interactive from the first release. Static PNGs or other chart images do not fulfil the MVP requirement.

### Proposed boundaries to refine

- Use one pinned dataset revision and matching annotations, with a visible revision label.
- Include a small set of interactive charts and semantic search.
- Defer the analyst agent and dynamically generated plots.
- Include an interactive Turftopic map now that the core explorer works; the user chose discovered topics over making annotation categories the main map view.
- Make the explorer publicly readable without accounts or individually requested search keys.

## 3. What the first release includes

| Feature | MVP behaviour | Done when |
| --- | --- | --- |
| Corpus overview | Show record count, token count, source count, dataset revision, and annotation coverage. | Each number has a clear scope and comes from the selected snapshot. |
| Composition charts | Show source and domain contributions, hover details, clickable categories, and a records/tokens switch. | Selecting a source/domain updates the other charts and the matching rows. |
| Document lengths | Show a token-length histogram with hover details and a draggable range selection. | Selecting a length range filters charts and rows; the histogram remains readable despite very long documents. |
| Annotation exploration | Show interactive distributions and filters for a small initial set of existing annotations. | Clicking an annotation category updates the other charts and row browser consistently. |
| Row browser | Show a scrollable list/table with text previews, source, and token count. | More rows load without loading the entire corpus into the browser. |
| Record detail | Open a readable, scrollable text panel with ID, source, dates, token count, and available annotations. | Users can read beyond the preview, including very long records through incremental loading. |
| Semantic search | Accept a natural-language query and return ranked matching records within the active filters. | Users can open results in the same record-detail panel. |
| Source information | Show a source description, domain, original link, and licence information. | Users can understand where a displayed record came from. |

### Initial annotation priorities

Start with **PII-related flags, content quality, and content type**, subject to checking the actual field names, value types, and coverage. Show additional available annotations in record details; adding every field as a chart or filter can wait.

The [Danish dataset card](https://huggingface.co/datasets/danish-foundation-models/danish-dynaword#annotations) documents a separate `meta` configuration containing synthetic annotations. Its [annotation overview](https://huggingface.co/datasets/danish-foundation-models/danish-dynaword#annotation-overview) also describes counts in `descriptive_stats.json`. These are useful inputs to inspect before building new aggregation work.

### Rules for presenting the data

- Keep missing/unavailable annotations separate from explicit negative values.
- Label annotation results as automated assessments. A PII flag is a model output, not a guarantee about privacy.
- Show how many records were annotated for the field being plotted. Calculate percentages using an explicitly stated denominator.
- Keep source-level domains distinct from document-level content-type annotations.
- Display `created` as its recorded date range and `added` as the collection date; do not treat them as interchangeable.

## 4. Proposed interface

Use one main explorer screen with three areas:

1. **Filters and search:** source, domain, token length, and the selected annotation fields, plus a semantic-search box.
2. **Charts and summary:** corpus totals, composition, lengths, and a selectable annotation distribution.
3. **Rows and record detail:** a scrollable browser and a panel for reading the selected record.

Selecting a chart category applies the corresponding filter. Active filters stay visible and can be cleared individually or together. Use a fixed, accessible palette and a readable default layout.

### Required chart interactions

| Interaction | What the visitor can do |
| --- | --- |
| Inspect values | Hover over a bar or histogram bin to see its label/range, count, and percentage with the relevant denominator. Make the same information available by touch and keyboard. |
| Select categories | Click a source, domain, or annotation category to filter the explorer. Keep the selected value visible in the active filters. |
| Select a numeric range | Drag across the document-length histogram to select a token range. Provide equivalent minimum/maximum inputs. |
| Explore linked views | See charts, summary counts, and the row browser update together as filters change, without a full page reload. |
| Change the measure | Switch composition charts between record counts and token counts, with updated axes and tooltips. |
| Return to a broader view | Remove an individual selection or reset all filters and restore the overview. |

Example: click a source → select an annotation value → drag over a document-length range → inspect the matching rows. Each selection narrows the same corpus slice, and the visible filters explain how that slice was produced.

These interactions are part of the MVP even with one fixed visual style and no guided tour. Changing a chart's measure or selecting data is a core analysis control.

Show loading feedback during queries and keep the latest selection authoritative if users change filters quickly. Keep query and rendering performance practical by returning chart aggregates and batches of rows.

**Search behaviour:** metadata filters define the corpus slice used by the charts. A semantic query ranks records within that slice and changes the row list. It does not silently replace the chart population with the top search results. Label the ranked list separately from the total number of records in the filtered slice.

## 5. Dataset coverage and search

**Proposed release target:** overview, filtering, and row access across one complete Danish snapshot, with semantic search covering the same records.

**Development scope:** the user requires full-corpus browsing and search for the first localhost review. The implementation imports every source and does not mark either index ready until its complete record count is verified.

Before committing to the full search index, measure embedding time, storage, and query latency on the development sample. If a full index is too expensive for the initial hosting budget, record a proposed reduced search scope here for discussion. Do not silently narrow coverage.

For long records, index passages and return a matching excerpt linked to the parent record. Group repeated hits from the same record. Record the embedding model and passage-splitting settings so the index can be rebuilt.

**Search recommendation:** begin with semantic search as the primary search mode, reflecting the wishlist. Whether exact word/phrase search also belongs in the MVP remains open.

## 6. Implementation approach

Choose the final stack after the data audit. The intended responsibilities are:

- **Preparation pipeline:** load the pinned texts and annotations, attach source metadata, validate joins, and prepare summaries and the search index.
- **Query service:** serve filtered counts, chart data, batches of rows, record text, and semantic results. Keep service credentials on the server.
- **Website:** render charts from structured data using a browser charting library and maintain a consistent selection across charts and rows. The charting library must support tooltips, category selection, and range selection or equivalent linked controls; choose it during implementation.

Precomputed numerical summaries are compatible with this approach. Displayed charts must remain interactive browser components; serving pre-rendered chart images is not the implementation for the explorer.

Precompute reusable summaries, but support statistics for combined filters through the query layer. Existing summary files may cover individual sources or fields without covering every filter combination.

Annotation joins must be checked against the actual schema. Retain source/dataset identity alongside record IDs, validate uniqueness, and check unmatched rows so joins do not inflate record counts.

Use existing annotations for this release. Training new annotation models and running live topic modelling are outside the scope. Turftopic fitting runs offline as a reproducible preparation step; the website serves the resulting map and full-corpus topic assignments.

## 7. Build sequence

### Step 1 — Inspect and fix the data contract

- [x] Choose a dataset revision and inspect the matching text, annotation, source, and summary files.
- [x] Establish exact annotation fields, coverage, join keys, and missing-value handling.
- [x] Import the complete snapshot and measure storage/indexing needs (full-corpus scope chosen by the user).
- [x] Record the release coverage, initial annotation filters, and provisional hosting approach in this plan.

Deliverable: the complete prepared snapshot and a documented schema that the explorer can use.

### Step 2 — Build browsing and interactive charts

- [x] Build the overview, composition and length charts, shared filters, and reset controls.
- [x] Add hover/focus details, clickable categories, histogram range selection, and the records/tokens switch.
- [x] Link chart selections to the shared filters, other charts, summary counts, and row browser.
- [x] Connect a scrollable row browser and record-detail panel to real data.
- [x] Include source information and the dataset revision.

Deliverable: a working path from a chart to the underlying text.

### Step 3 — Add annotation exploration

- [x] Add the initial annotation filters and distribution chart.
- [x] Show coverage and missing values explicitly.
- [x] Verify that combined filters produce consistent chart totals and matching rows.

Deliverable: a useful explorer of the existing annotation layer.

### Step 4 — Add semantic search and expand coverage

- [x] Build the document-vector baseline and return ranked results linked to records.
- [ ] Upgrade to contextual passage indexing and matched-passage previews.
- [x] Apply metadata filters during retrieval and return one result per document.
- [x] Check relevance on a small, manually reviewed set of Danish queries.
- [x] Confirm complete-corpus index coverage and measure responsiveness.

Deliverable: searchable data with visible, accurate coverage information.

### Step 5 — Add discovered topics

- [x] Fit Turftopic Top2Vec on a seeded sample spanning all sources, reusing Danish document vectors.
- [x] Precompute full-corpus topic assignments, with explicit unassigned coverage and revision checks.
- [x] Add a zoomable, pannable map, original-text inspection, topic keywords, and full-corpus topic distribution.
- [x] Link topic selection to the complete record browser and both text and semantic search.
- [x] Add quality, PII, and domain overlays, plus a keyboard-accessible map-record list.
- [x] Separate sampled map coverage from corpus totals and explain model limitations.

Deliverable: an exploratory topic landscape linked to the original corpus, not a static plot.

### Step 6 — Validate and publish the MVP

- [x] Check aggregates against independent counts from the pinned data, including after annotation joins.
- [x] Check missing annotations, empty results, long texts, and combined filters.
- [x] Verify the full chart-selection-to-record flow, individual clearing, reset, and rapid filter changes without stale results replacing the latest selection.
- [x] Check the layout on desktop and mobile, keyboard access, and loading/error states.
- [ ] Publish the agreed public version and document how to rebuild it from the pinned revision.

Deliverable: a public explorer that can be reviewed against the acceptance criteria below.

## 8. Acceptance criteria

The MVP is ready when a visitor can:

1. Understand the dataset composition and the exact scope of the displayed statistics.
2. Filter by source/domain and the agreed annotation fields, with consistent counts and rows.
3. Scroll through results and read the underlying record text and metadata.
4. Search in Danish by meaning and inspect relevant results within the selected filters.
5. Distinguish missing annotations from negative findings, and ranked search results from corpus statistics.
6. Use the public explorer without requesting individual access keys.
7. Inspect chart values, select categories and length ranges, switch measures, and see linked views update without reloading the page.

The implementation must also keep the bulk corpus out of the initial browser download and reproduce its counts and joins from the pinned snapshot. Static chart images alone do not satisfy these acceptance criteria.

## 9. Later additions

- Norwegian, Swedish, Icelandic, and Faroese datasets and comparisons between languages.
- Refine topic quality with contextual Danish/multilingual embeddings, topic hierarchies, and potentially embeddings of existing descriptions; evaluate coverage and usefulness before replacing the current baseline.
- An Atlas Analyst-style agent and natural-language chart generation.
- Guided tours and user-adjustable aesthetics.
- Release comparisons, corpus-growth timelines, and automated refreshes.
- Saved workspaces, custom uploads, and export tools.

## 10. Choices for our next refinement

| Choice | Current proposal |
| --- | --- |
| Should the topic map be part of the first release? | Yes: interactive Turftopic map added. Discovered topics are the chosen focus, with annotations as overlays. |
| Semantic search only, or exact text search too? | Both implemented; semantic is explicitly labelled as a word-vector beta. |
| Which annotations should get first-class controls? | PII flags, content quality, and content type, after checking schema and coverage. |
| Is full-corpus search required at launch? | Yes: user requires full-corpus browsing and search. Exact text search covers every record; semantic processing covers all records and reports usable-vector coverage separately. |
| What hosting budget should guide the design? | Still to be decided; it will shape storage, embeddings, and search infrastructure. |

## References

- [Danish Dynaword](https://huggingface.co/datasets/danish-foundation-models/danish-dynaword)
- [Nomic Atlas](https://atlas.nomic.ai/discover) — inspiration for inspecting rows and semantic exploration.
- [WIMBD](https://wimbd.apps.allenai.org/) — inspiration for corpus analysis and comparisons.
- [Project wishlist](WISHLIST.md)

# Memory — Companion Jupyter Notebooks

One executable companion per numbered chapter: `NN-chapter.ipynb` mirrors
`content/books/memory/NN-chapter.md`. The notebooks are a second, executable
path through the book — concept, mechanism, real repository code, fixture,
observable trace, measured result, interpretation — not a parallel
implementation. Business logic lives in the packages; notebooks only import it.

## Open and run

From the repository root, with the project's Python environment:

```bash
jupyter notebook notebooks/memory/01-chapter.ipynb
```

Or execute non-interactively:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/memory/12-chapter.ipynb
```

## Default demonstrations

The default path (`RUN_LIVE = False` where applicable) uses **real package
code + deterministic fixtures + committed frozen artifacts** under
`experiments/benchmark/runs/`. It needs no PostgreSQL, Ollama, GraphRAG
build, model checkpoint or API key. Cells that need live services are
explicitly marked and degrade to a message naming what is missing.

Chapter 3's baseline is the exception that proves the rule: its one live
cell is disabled by default and the notebook otherwise reads the frozen
`ch3-20260919-ladder` run.

## Frozen artifacts

`manifest.yaml` maps every chapter to its notebook, implementation modules,
experiments, frozen runs and evidence status. Notebooks read run numbers
from artifacts (never hand-copied) via `notebooks/memory/_support`.

Evidence discipline follows the book: **demonstration** (shows how a
mechanism works) is labelled separately from **experiment** (tests a
predeclared question) and **book result** (comes from a committed frozen
artifact). Chapters 15–16 are explicitly pending: their notebooks quantify
the open problem and state what a result would need to show.

## Optional live experiments

Set `RUN_LIVE = True` in the marked cell and provide the service the cell
names (e.g. `MEMORY_BASELINE_DSN` for PostgreSQL, Ollama at
`localhost:11434`). Missing services never break the default path.

## Regenerate rendered HTML

Not currently published. The `.ipynb` files are canonical; GitHub renders
them from the chapter links. If static HTML is wanted later, export with
`nbconvert` into `static/notebooks/` and point the chapter callouts there —
do not commit generated HTML without wiring it into the Hugo build.

## Validation

```bash
python scripts/validate_notebooks.py
```

Checks chapter/notebook/manifest correspondence, chapter link markers,
JSON validity, code syntax, machine-path hygiene, frozen-run references,
manifest concept IDs, capstone imports and import resolution.

## Chapter / notebook table

| Ch | Notebook | Class | Evidence |
|----|----------|-------|----------|
| 1 | 01-chapter.ipynb | DETERMINISTIC | foundational hypothesis |
| 2 | 02-chapter.ipynb | DETERMINISTIC | instrument defined, experiment pending |
| 3 | 03-chapter.ipynb | ARTIFACT_BACKED | implemented, comparative experiment pending |
| 4 | 04-chapter.ipynb | ARTIFACT_BACKED | developmental (Type C, Type B core) |
| 5 | 05-chapter.ipynb | DETERMINISTIC | developmental, conditional |
| 6 | 06-chapter.ipynb | DETERMINISTIC | developmental, optimisation/control |
| 7 | 07-chapter.ipynb | DETERMINISTIC | book result (claims derived/justified) |
| 8 | 08-chapter.ipynb | DETERMINISTIC | book result (temporal state) |
| 9 | 09-chapter.ipynb | ARTIFACT_BACKED | book result, conditional |
| 10 | 10-chapter.ipynb | ARTIFACT_BACKED | book result (explicit control) |
| 11 | 11-chapter.ipynb | ARTIFACT_BACKED | book result, conditional/guarded |
| 12 | 12-chapter.ipynb | ARTIFACT_BACKED | book result |
| 13 | 13-chapter.ipynb | ARTIFACT_BACKED | book result, conditional control |
| 14 | 14-chapter.ipynb | ARTIFACT_BACKED | book result (bounded context) |
| 15 | 15-chapter.ipynb | DETERMINISTIC | experimental, deferred |
| 16 | 16-chapter.ipynb | DETERMINISTIC | experimental, deferred |
| 17 | 17-chapter.ipynb | ARTIFACT_BACKED | book result, conditional control (priced) |
| 18 | 18-chapter.ipynb | CAPSTONE | book result (capstone replay, verdict A) |

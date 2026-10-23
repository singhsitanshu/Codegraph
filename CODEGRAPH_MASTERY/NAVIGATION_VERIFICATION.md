# Navigation verification

[Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md)

Verified on 2026-09-24 after consolidating the manual into this folder.

## What was checked

- Parsed all Markdown files with a Markdown parser, ignoring code examples when collecting links and headings.
- Checked every internal link for an existing file with matching filename capitalization.
- Checked every section fragment against its destination heading using GitHub-style heading IDs.
- Checked that every Q-number link lands on a heading with that exact question number.
- Confirmed that the master index links all 35 requested parts and that all 200 question headings exist.
- Confirmed that every file is reachable from the start page and every numbered volume has top/bottom navigation and a contents list.
- Repeated the internal-link checks against a temporary copy of the folder in a different location.
- Compared all 200 answer blocks and all fenced code/diagram blocks with the pre-reorganization copies to ensure they were preserved.

## Corrections made

The master manual now lives beside its seven volumes. Parent-directory links were replaced with local links. Added a start page, a 35-part index, per-volume contents, question shortcuts and previous/next navigation.

Corrected question references in the source-reading guide and final review. These include same-name function ambiguity (Q193), partial embedding failure (Q194), worker startup cleanup (Q195), vector scope post-filtering (Q196), and Leiden evaluation (Q141). References to drills, exercises, evidence and volumes now provide navigation where appropriate.

## External reference checks

All six unique external reference pages opened successfully during this check:

- [Tree-sitter basic parsing](https://tree-sitter.github.io/tree-sitter/using-parsers/2-basic-parsing.html)
- [Tree-sitter query syntax](https://tree-sitter.github.io/tree-sitter/using-parsers/queries/1-syntax.html)
- [Neo4j Leiden](https://neo4j.com/docs/graph-data-science/current/algorithms/leiden/)
- [Original Leiden paper](https://arxiv.org/abs/1810.08473)
- [Neo4j vector indexes](https://neo4j.com/docs/cypher-manual/current/indexes/semantic-indexes/vector-indexes/)
- [Cypher SEARCH](https://neo4j.com/docs/cypher-manual/25/clauses/search/)

External pages can change after verification. Internal navigation is portable when this folder is kept together. Source citations shown in backticks are evidence annotations, not hyperlinks. Rendering of section jumps and Mermaid diagrams depends on the Markdown viewer; this check validates Markdown destinations rather than every viewer's user interface.

## Final result

**PASS: no broken internal links or missing section targets.**

| Check | Result |
|---|---:|
| Markdown files in the folder | 10 |
| Internal links checked | 736 |
| Links to specific headings | 617 |
| Question-number links checked | 399 |
| Question answer blocks preserved | 200 |
| Fenced code and diagram blocks preserved | 52 |
| Mock interviews preserved | 6, with 10 questions each |
| Requested parts linked from the master | 35 |
| Files reachable from the start page | 10 of 10 |
| Broken internal links or missing targets | 0 |
| Unique external references opened | 6 of 6 |

The same internal checks passed for a relocated copy of the folder. No tracked application source or configuration was changed by this reorganization.


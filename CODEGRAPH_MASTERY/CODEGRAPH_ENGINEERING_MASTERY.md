# CodeGraph Engineering Mastery

**Evidence date:** 2026-09-24. **Analyzed revision:** `main`, `79fa7689754af893e871436a911a0c4d245c6a43` (2026-09-23). The working tree was clean before this investigation. The manual is contained in the dedicated `CODEGRAPH_MASTERY/` folder.

This is a source-grounded interview manual for the developer of CodeGraph. Read the engineering chapters first, then practice the question bank without looking at its answers. The linked volumes are part of this report; together they are self-contained. They explain the implementation rather than requiring you to open another repository or service.

[Start here](README.md) · [Navigation verification](NAVIGATION_VERIFICATION.md)

## Master index and request coverage

| Requested parts | Volume |
|---|---|
| 1–13: investigation, five explanations, architecture, ingestion, parsing, concurrency, Neo4j, Cypher, consistency, embeddings, RAG, Leiden, context claims | [Foundations and data pipeline](01_FOUNDATIONS.md) |
| 14–27: agent, every tool, prompts, AI decisions, APIs, frontend, streaming, security, tests, evaluation, scaling, history, trade-offs, weaknesses | [Application, AI, and engineering audit](02_APPLICATION_AND_AUDIT.md) |
| 28: at least 180 questions, organized A–Y, with spoken answers, technical explanations, source evidence, follow-ups, misconceptions, and concepts | [200-question interview bank](03_QUESTION_BANK.md) |
| 29–32: decision defense, resume claims, guided source walkthrough, 50 facts, 25 reading targets, glossary, exercises and separate keys | [Decision defense and learning system](04_STUDY_AND_DEFENSE.md) |
| 33–34: six mock interviews, progressive challenges, ownership and AI-assisted development | [Mock interviews and personal contribution preparation](05_MOCK_INTERVIEWS.md) |
| Evidence support: exact query text, function/test inventory, version information, validation, tracked file census | [Evidence ledger](06_EVIDENCE.md) |
| 35: final cheat sheet, diagrams, tools, decisions, limitations, essential and hardest questions, checklist, readiness and coverage audit | [Final review and readiness assessment](07_FINAL_REVIEW.md) |

## Jump to any requested part

- [1. Investigation method, revision, and evidence](01_FOUNDATIONS.md#1-investigation-method-revision-and-evidence)
- [2. CodeGraph from first principles: five levels](01_FOUNDATIONS.md#2-codegraph-from-first-principles-five-levels)
- [3. Complete architecture](01_FOUNDATIONS.md#3-complete-architecture)
- [4. Repository ingestion in exact order](01_FOUNDATIONS.md#4-repository-ingestion-in-exact-order)
- [5. Tree-sitter and the intermediate representation](01_FOUNDATIONS.md#5-tree-sitter-and-the-intermediate-representation)
- [6. Concurrency and backpressure](01_FOUNDATIONS.md#6-concurrency-and-backpressure)
- [7. Graph model, identity and storage](01_FOUNDATIONS.md#7-graph-model-identity-and-storage)
- [8. Cypher query atlas and complexity](01_FOUNDATIONS.md#8-cypher-query-atlas-and-complexity)
- [9. ETL consistency and failure boundaries](01_FOUNDATIONS.md#9-etl-consistency-and-failure-boundaries)
- [10. Embeddings and semantic retrieval](01_FOUNDATIONS.md#10-embeddings-and-semantic-retrieval)
- [11. Actual RAG sequence](01_FOUNDATIONS.md#11-actual-rag-sequence)
- [12. Leiden: algorithm and actual application](01_FOUNDATIONS.md#12-leiden-algorithm-and-actual-application)
- [13. Context reduction: exact metric and unsupported benchmark](01_FOUNDATIONS.md#13-context-reduction-exact-metric-and-unsupported-benchmark)
- [14. LangGraph, ReAct and the actual execution loop](02_APPLICATION_AND_AUDIT.md#14-langgraph-react-and-the-actual-execution-loop)
- [15. Profiles of all seven registered tools](02_APPLICATION_AND_AUDIT.md#15-profiles-of-all-seven-registered-tools)
- [16. Prompt design and trust boundaries](02_APPLICATION_AND_AUDIT.md#16-prompt-design-and-trust-boundaries)
- [17. AI architecture decision defense](02_APPLICATION_AND_AUDIT.md#17-ai-architecture-decision-defense)
- [18. FastAPI endpoint contracts](02_APPLICATION_AND_AUDIT.md#18-fastapi-endpoint-contracts)
- [19. Frontend architecture and React behavior](02_APPLICATION_AND_AUDIT.md#19-frontend-architecture-and-react-behavior)
- [20. NDJSON streaming and progress](02_APPLICATION_AND_AUDIT.md#20-ndjson-streaming-and-progress)
- [21. Security analysis with actual controls](02_APPLICATION_AND_AUDIT.md#21-security-analysis-with-actual-controls)
- [22. Test suite and Postman](02_APPLICATION_AND_AUDIT.md#22-test-suite-and-postman)
- [23. Evaluation methodology and answer reliability](02_APPLICATION_AND_AUDIT.md#23-evaluation-methodology-and-answer-reliability)
- [24. Performance and scale](02_APPLICATION_AND_AUDIT.md#24-performance-and-scale)
- [25. Development history: evidence without invented motivation](02_APPLICATION_AND_AUDIT.md#25-development-history-evidence-without-invented-motivation)
- [26. Architectural trade-off matrix](02_APPLICATION_AND_AUDIT.md#26-architectural-trade-off-matrix)
- [27. Weaknesses and production-readiness register](02_APPLICATION_AND_AUDIT.md#27-weaknesses-and-production-readiness-register)
- [28. Interview question bank: 200 questions](03_QUESTION_BANK.md#part-28--200-question-technical-interview-bank)
- [29. Engineering decision defense](04_STUDY_AND_DEFENSE.md#29-engineering-decision-defense)
- [30. Resume claim defense cards](04_STUDY_AND_DEFENSE.md#30-resume-claim-defense-cards)
- [31. Guided source reading: 25 targets](04_STUDY_AND_DEFENSE.md#31-guided-source-reading-25-targets)
- [32. Active-recall learning system](04_STUDY_AND_DEFENSE.md#32-active-recall-learning-system)
- [33. Six mock interviews and progressive drills](05_MOCK_INTERVIEWS.md#parts-3334--mock-interviews-and-personal-contribution-preparation)
- [34. Personal contributions and AI-assisted development](05_MOCK_INTERVIEWS.md#34-personal-contributions-and-ai-assisted-development)
- [35. Final review and readiness](07_FINAL_REVIEW.md#part-35--final-review-cheat-sheet-and-readiness)

## Study shortcuts

- [50 recall facts](04_STUDY_AND_DEFENSE.md#the-50-facts-to-recall-without-notes)
- [Glossary](04_STUDY_AND_DEFENSE.md#glossary-tied-to-codegraph)
- [Practice exercises](04_STUDY_AND_DEFENSE.md#exercises--attempt-before-opening-the-key)
- [Separate answer key](04_STUDY_AND_DEFENSE.md#separate-answer-key)
- [30 essential questions](07_FINAL_REVIEW.md#the-30-questions-you-must-answer)
- [15 hardest questions](07_FINAL_REVIEW.md#the-15-hardest-questions)
- [Source-reading checklist](07_FINAL_REVIEW.md#source-code-reading-checklist)
- [Actual query and prompt text](06_EVIDENCE.md#active-query-and-prompt-definitions)

## Findings to internalize before interviewing

1. **The parser is ahead of the database.** HEAD adds qualified names, source ranges, deterministic `fn:v1:` identities and lexical call ownership. The writer still merges on `(repo_name, simple_name)` and copies every file-wide call target onto every function in that file. The parser improvements do not yet make the persisted graph accurate.
2. **Seven tools are registered.** They inspect direct callers, file structure, functions in a file, outgoing calls, unresolved/external names, semantic matches, and stored architectural summaries. None reads function source for the agent. The browser has a separate source endpoint.
3. **Graph-RAG is agent-selected graph retrieval.** Leiden runs during ingestion. Architecture queries retrieve stored community summaries. There is no automatic query-vector → selected community → induced source subgraph pipeline.
4. **Embeddings contain name and path.** The provider is OpenAI, the model string is `text-embedding-3-small`, and vectors are validated as 1,536-dimensional. Function source is stored but not embedded.
5. **Context efficiency is a limited metric.** It compares supported-source token totals with concatenated tool messages. It is not total billed tokens, latency, correctness, or measured savings. No repository evidence substantiates the supplied 737,000 → 18,000 benchmark.
6. **Repository predicates are not access control.** Public API routes accept caller-selected repository names. Tool repository arguments are model supplied, not bound to an authenticated principal. Startup deletes all repository-scoped nodes.
7. **Validation at this revision:** 92 backend cases passed, 4 database integration cases deliberately skipped; 13 Node cases passed; Vite build passed with a 631.14 kB minified JavaScript chunk warning. No paid model calls, external repository changes, application startup, or persistent database writes were performed.

## How to speak accurately

Use “the current implementation does…” for source-confirmed behavior, “the tests verify…” only for the assertions actually exercised, and “I would…” for improvements. Say “a defensible rationale is…” when history does not establish the original motivation. Do not turn commit authorship into a claim of entirely manual authorship. Personal stories must come from your recollection.

Source references use repository-relative paths and one-based line locations for the pinned revision. The evidence ledger includes query text and symbol names, so the reasoning remains readable without a live database. `IMPLEMENTED`, `VERIFIED`, `DOCUMENTED`, `HISTORICAL`, `INFERRED`, and `UNVERIFIED` are defined in the first volume and used throughout.

[Start here](README.md) · [Begin foundations](01_FOUNDATIONS.md) · [Navigation verification](NAVIGATION_VERIFICATION.md)

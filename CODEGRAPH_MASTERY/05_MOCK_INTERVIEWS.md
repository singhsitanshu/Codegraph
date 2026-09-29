# Parts 33–34 — Mock interviews and personal contribution preparation

[Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](04_STUDY_AND_DEFENSE.md) · [Next](06_EVIDENCE.md)

## Contents

- [Interview 1 — General software engineering internship](#interview-1--general-software-engineering-internship)
- [Interview 2 — Backend, APIs and databases](#interview-2--backend-apis-and-databases)
- [Interview 3 — Full-stack, React and visualization](#interview-3--full-stack-react-and-visualization)
- [Interview 4 — AI, LLMs, tools and RAG](#interview-4--ai-llms-tools-and-rag)
- [Interview 5 — Graph databases and information retrieval](#interview-5--graph-databases-and-information-retrieval)
- [Interview 6 — Demanding senior architectural review](#interview-6--demanding-senior-architectural-review)
- [Progressive pressure drills: four deeper sequences](#progressive-pressure-drills-four-deeper-sequences)
- [Drill A — from parsing to runtime truth](#drill-a--from-parsing-to-runtime-truth)
- [Drill B — from token arithmetic to economic evidence](#drill-b--from-token-arithmetic-to-economic-evidence)
- [Drill C — from scoped Cypher to tenant authorization](#drill-c--from-scoped-cypher-to-tenant-authorization)
- [Drill D — from batching to consistent publication](#drill-d--from-batching-to-consistent-publication)
- [34. Personal contributions and AI-assisted development](#34-personal-contributions-and-ai-assisted-development)

---

Practice each interview aloud, allowing 35–50 minutes. Give the opening without notes, answer each main question, then answer the follow-up before consulting the model response. Each interview includes ten substantive questions, distinct emphasis and a final limitation/decision challenge. Source abbreviations follow the [question bank key](03_QUESTION_BANK.md).

## Interview 1 — General software engineering internship

**Opening:** “CodeGraph turns supported GitHub source into an exploratory graph and a tool-driven Q&A interface. I can trace the complete ingestion and request paths, including where the current database representation is less precise than the new parser. My strongest defensible accomplishments are the integrated workflow and tested contracts; I would not claim production readiness or guaranteed AI correctness.”

1. **A new developer has ten minutes to inspect a repository. How does your UI help?**
   **Model answer:** It offers indexed file/function relationships, generated cluster summaries and scoped questions, plus a source drawer. A developer can orient by module labels, inspect likely functions and verify snippets. The graph is capped and approximate, so the UI is a starting point rather than comprehensive evidence.
   **Follow-up:** “What if they trust a false edge?” **Answer:** The current product needs clearer provenance; file-scope inferred calls can be wrong, and source inspection is required before a change decision.
   **Evaluates:** user value with honest limitations. **Evidence:** UI:585; ETL:78; DB:31.

2. **Walk through the first server operation after clicking ingest.**
   **Model answer:** Pydantic validates the URL string, then the handler checks HTTPS/GitHub and an owner/repository path before returning a streaming response. The generator emits progress 10, requests a default-branch zipball and owns temporary extraction storage.
   **Follow-up:** “Can malformed URLs consume embedding credits?” **Answer:** Invalid URLs fail before streaming and enrichment. Valid but huge repositories can consume resources later because quotas are absent.
   **Evaluates:** validation order and side effects. **Evidence:** M:97,139,520; GH:59.

3. **What small example exposes the biggest graph bug?**
   **Model answer:** Put `a(){x()}` and `b(){y()}` in one file. The parser owns x under a and y under b, but legacy ETL creates all four caller-target combinations from the file-wide list. Two same-named functions expose a second identity problem.
   **Follow-up:** “Why didn't the new parser solve it?” **Answer:** The writer has not adopted the richer records; tests at one boundary do not prove downstream fidelity.
   **Evaluates:** ability to create counterexamples. **Evidence:** P:519; ETL:178.

4. **What did the tests in this investigation actually verify?**
   **Model answer:** Ninety-two backend cases passed with network disabled and temporary missing dependencies supplied; four database integrations skipped. Thirteen Node tests and a production build passed. Most service/agent tests use mocks, while grammar fixtures exercise actual parsing.
   **Follow-up:** “Does that mean the demo works against Claude today?” **Answer:** No, no paid provider integration was run, and configured model availability remains unverified.
   **Evaluates:** evidence precision. **Evidence:** [validation record](06_EVIDENCE.md#current-validation-record); backend/tests.

5. **Explain an engineering trade-off you can defend without inventing history.**
   **Model answer:** Batching 100 rows limits transaction payload and retry units, but makes partial graphs visible. A current rationale is bounded writes; a stronger design would combine them with immutable generations and atomic activation.
   **Follow-up:** “Did you choose 100 after benchmarking?” **Answer:** No benchmark is recorded. I should describe it as an implemented constant unless I can provide my own measured experiment.
   **Evaluates:** reasoning versus retrospective storytelling. **Evidence:** ETL:101,276.

6. **How would you debug a blank graph after apparently successful ingestion?**
   **Model answer:** Confirm a terminal progress-100 record and returned repo_name, then inspect graph scope and node coverage. A repository with no supported files can complete empty; startup/unload cleanup can delete data; graph failures should produce explicit errors. I would avoid immediately blaming React Flow.
   **Follow-up:** “What does health tell you?” **Answer:** Only liveness, not that GDS or graph contents are ready.
   **Evaluates:** layered diagnosis. **Evidence:** M:424,544; ETL:29; HTTP:86.

7. **Why are source code and embeddings removed from graph responses?**
   **Model answer:** They are large and unnecessary for initial visualization. Source is fetched on demand by node ID and repository; vectors never need to be drawn. This improves payload efficiency but is not access control.
   **Follow-up:** “Is source protected from another caller?” **Answer:** No authenticated permission check exists, so deployment needs authorization on the separate endpoint too.
   **Evaluates:** payload design and security distinctions. **Evidence:** DB:98,213; M:248.

8. **What would you do if one parser file raises?**
   **Model answer:** Current batch logic logs the failure, yields progress with no result and continues. Tokens already counted still contribute to the baseline. I would expose structured skipped-file coverage so users can judge the partial result.
   **Follow-up:** “Should every syntax error fail ingestion?” **Answer:** Not necessarily for exploration; define a policy that preserves useful data while making uncertainty visible.
   **Evaluates:** partial-success design. **Evidence:** P:614,755.

9. **How would you decide what to improve next?**
   **Model answer:** Start with identity and call provenance because incorrect graph facts affect search, architecture and answers. Then add durable snapshots, authorization and evaluated source-grounded retrieval. I would measure bottlenecks before distributing workers.
   **Follow-up:** “Why not polish the assistant first?” **Answer:** Better prose over ambiguous data can make errors more convincing; upstream correctness has higher leverage.
   **Evaluates:** prioritization. **Evidence:** ETL:55,178; backend/FUNCTION_IDENTITY.md.

10. **What would you say if asked whether you built every line yourself?**
    **Model answer:** I would describe my actual workflow and responsibilities, including AI assistance if used. Git proves committed changes and chronology, not manual authorship. I would show a concrete design or debugging decision I can explain and validate.
    **Follow-up:** “Which story can this manual supply?” **Answer:** It can supply technical evidence and prompts; it cannot supply my firsthand experience.
    **Evaluates:** ownership and integrity. **Evidence:** Git history; [personal contribution preparation](05_MOCK_INTERVIEWS.md#34-personal-contributions-and-ai-assisted-development).

## Interview 2 — Backend, APIs and databases

**Opening:** “The backend coordinates GitHub, parsing, Neo4j and model services through async FastAPI handlers. Its strongest contracts are scoped parameters, bounded write batches and explicit stream error handling. Its biggest backend gaps are non-atomic repository replacement, incomplete incremental reconciliation and a destructive shared lifecycle.”

1. **An ingestion returns 200 then fails in Neo4j. Design the client's interpretation.**
   **Answer:** Treat 200 as the start of an NDJSON stream, parse every record, reject any error and require terminal success with canonical scope. A durable redesign would return a job ID and persist status independently of the stream.
   **Follow-up:** “Can the server change to 500 after sending records?” **Answer:** Not the already-sent headers; failures must be encoded in the stream or reflected in durable job state.
   **Evaluates:** HTTP lifecycle. **Evidence:** M:534; HTTP:57.

2. **Where are your transaction boundaries?**
   **Answer:** Scoped deletion, baseline writes and each file/function/call batch are separate managed transactions. GDS writes separately; community deletion/replacement is atomic only within its own callback after label generation.
   **Follow-up:** “What remains after label failure?” **Answer:** Graph and community-number writes may remain, while labeled Community nodes may be old or absent depending on the path; no normal completion record is emitted.
   **Evaluates:** consistency tracing. **Evidence:** ETL:259–324; LABEL:146.

3. **Why is a composite index not a uniqueness constraint?**
   **Answer:** It accelerates lookups but allows duplicate key values. The current initializer creates indexes; it does not enforce repository/function uniqueness. Concurrent MERGEs need proper constraints and keys.
   **Follow-up:** “Would unique repo/name solve it?” **Answer:** It would enforce the wrong identity and preserve same-name conflation. The key must include canonical entity identity before enforcing uniqueness.
   **Evaluates:** schema invariants. **Evidence:** IDX:26; ETL:55.

4. **What happens when a webhook says a file was deleted?**
   **Answer:** The active extractor ignores removed paths. Existing file/functions/calls can remain, and token totals are stale. Standard PR file enumeration also is not implemented in this path.
   **Follow-up:** “Why not call full ingest on every event?” **Answer:** That is simpler correctness-wise but expensive and still needs ordering/snapshot safety; frequent updates would waste parsing/embedding work.
   **Evaluates:** incremental design trade-offs. **Evidence:** PIPE:23,39,219.

5. **Would you use BackgroundTasks for reliable indexing?**
   **Answer:** Only for best-effort local work. Current tasks run after acknowledgement in the API process with log-only failures and no durable job ID. A crash can lose the work.
   **Follow-up:** “What queue semantics would you promise?” **Answer:** Prefer at-least-once delivery with idempotent stage outputs and deduplication, rather than casually promise exactly-once external effects.
   **Evaluates:** distributed reliability. **Evidence:** HOOK:53; PIPE:233.

6. **Is the graph endpoint paginated?**
   **Answer:** No. LIMIT 200 truncates result rows after upstream collection and optional matches, without ordering/cursor/truncation metadata. It neither guarantees 200 nodes nor supports complete exploration.
   **Follow-up:** “How would you redesign it?” **Answer:** An entity-neighborhood API plus ordered pagination/aggregation, tied to a snapshot so repeated fetches are consistent.
   **Evaluates:** query/API contract. **Evidence:** DB:12,31.

7. **Why could database startup block the whole app?**
   **Answer:** Lifespan waits for index initialization and scoped deletion before yielding. The sync driver also verifies connectivity during import. A health handler cannot rescue an app that never reaches serving readiness.
   **Follow-up:** “What is safe on multi-worker startup?” **Answer:** Idempotent schema/readiness operations; global data deletion should be explicit retention work, not startup behavior.
   **Evaluates:** lifecycle design. **Evidence:** IDX:55,82; M:60.

8. **Where could Python block the event loop despite async handlers?**
   **Answer:** Large ETL list transformations, serialization and context token counting execute synchronously. Parsing/discovery are offloaded, but an async signature does not automatically offload all work.
   **Follow-up:** “What would you profile?” **Answer:** Event-loop delay, CPU time and resident memory per stage, especially large-file call ownership and ETL call-row products.
   **Evaluates:** runtime understanding. **Evidence:** ETL:123; AG:437; P:565.

9. **What makes HMAC verification correctly ordered?**
   **Answer:** The dependency reads raw bytes and compares the expected signature before the handler parses JSON or schedules work. A signed malformed body exercises a different boundary from an unsigned one.
   **Follow-up:** “What is still unauthenticated?” **Answer:** Freshness, user ownership and allowed repository/event policy; event header is not included in the body digest and replay is not tracked.
   **Evaluates:** security boundary detail. **Evidence:** SIG:9; HOOK:38.

10. **Design a robust reingestion protocol.**
    **Answer:** Create a job/snapshot for an immutable commit, write all entities under it with canonical keys, track stages and validation, then atomically update the active snapshot pointer. Retain the old snapshot until safe garbage collection.
    **Follow-up:** “What does this cost?” **Answer:** Extra storage and snapshot-aware queries plus cleanup/ordering logic. It buys recovery and consistent visibility without enormous transactions.
    **Evaluates:** architecture synthesis. **Evidence:** current ETL:278 as the problem boundary.

## Interview 3 — Full-stack, React and visualization

**Opening:** “The dashboard owns local repository/chat/graph state, streams ingestion progress, loads a capped graph and computes its layout in the browser. It has useful source inspection and cluster emphasis, but no persistent conversations, entity-linked assistant answers or large-graph pagination.”

1. **Explain the graph data transformation before React Flow renders.**
   **Answer:** API nodes/edges are normalized, degree counts determine sizes, D3 force simulation runs 300 ticks, center positions become top-left coordinates, and edges receive handles/arrows. Controlled arrays feed memoized node components.
   **Follow-up:** “Are backend positions used?” **Answer:** Normalization resets them; frontend layout replaces the initial grid.
   **Evaluates:** ownership of rendering logic. **Evidence:** UI:280,363,509.

2. **What does selecting a function do across the stack?**
   **Answer:** It sets selectedNodeId, CodePanel fetches scoped code by elementId, the backend reads raw_code/path/name and the drawer highlights the snippet using its extension. It does not request the whole file.
   **Follow-up:** “Are displayed lines the original source lines?” **Answer:** No, they are snippet lines; original parser ranges are not persisted/exposed here.
   **Evaluates:** data fidelity through UI. **Evidence:** UI:801; CODE:58; DB:34.

3. **A user switches repositories while a graph fetch is slow. What is missing?**
   **Answer:** loadGraph lacks an abort signal and generation check, so a stale response can overwrite newer graph state. Local loading flags do not prove all interleavings are safe.
   **Follow-up:** “How do you verify a fix?” **Answer:** Control promise resolution order in tests and ensure only the latest scope/snapshot can publish results.
   **Evaluates:** async state correctness. **Evidence:** UI:808; HTTP:95.

4. **Why do you maintain both focusedNodeId and selectedNodeId?**
   **Answer:** Hover focus controls neighbor emphasis, while selection opens source. These are different interaction states; future assistant navigation should not be erased by a hover-leave event.
   **Follow-up:** “How would you add chat navigation?” **Answer:** A stable entity/snapshot reference contract and a dedicated navigation action, not a regex matching function names in prose.
   **Evaluates:** interaction modeling. **Evidence:** UI:585,638,801; AG:343.

5. **What do cluster filters actually do?**
   **Answer:** They color selected communities and dim unrelated nodes/edges while retaining loaded arrays. They do not fetch new members or reduce graph data to only selected clusters.
   **Follow-up:** “Can the legend claim complete function counts?” **Answer:** No, it counts the loaded subset; the architecture tool has separate full-graph aggregation.
   **Evaluates:** UI semantics. **Evidence:** UI:697,759; communities.js; AG:74.

6. **Why use incremental UTF-8 decoding for ingestion?**
   **Answer:** Transport chunks can split multi-byte characters and JSON lines. TextDecoder stream mode preserves incomplete bytes, while the string buffer preserves incomplete lines before JSON.parse.
   **Follow-up:** “What if EOF has no final newline?” **Answer:** The reader processes the remaining buffer, then still requires a success record with repository name.
   **Evaluates:** stream framing. **Evidence:** HTTP:52–92.

7. **What does the chat stop button guarantee?**
   **Answer:** It aborts the currently referenced fetch controller, not guaranteed server/provider termination or cost rollback. A shared-ref race can also lose the newer operation's controller.
   **Follow-up:** “What specific race?” **Answer:** Old chat finally unconditionally clears abortRef after a new ingestion sets it; ingestion's finalizer instead checks identity.
   **Evaluates:** cancellation ownership. **Evidence:** UI:876,958,1058.

8. **How would you reduce the main bundle and rendering load?**
   **Answer:** Measure first, then consider lazy source-highlighter/graph loading and worker-based force layout. The audit build's JS chunk is 631.14 kB minified, and synchronous layout can block interaction.
   **Follow-up:** “Would splitting App.jsx alone shrink the bundle?” **Answer:** Not necessarily; static imports still bundle together. Dynamic loading and actual dependency boundaries matter.
   **Evaluates:** practical frontend performance. **Evidence:** frontend/package.json; UI:363; build evidence.

9. **Why is unload cleanup unreliable and dangerous in a shared service?**
   **Answer:** beforeunload delivery is best effort, and it deletes a shared repo_name scope. Another tab/user analyzing the same repository can lose data even if the request succeeds.
   **Follow-up:** “What should replace it?” **Answer:** Server-managed leases/retention or explicit session/snapshot ownership and garbage collection, not assuming browser lifetime owns repository data.
   **Evaluates:** browser/server lifecycle. **Evidence:** UI:861; HTTP:154; ETL:24.

10. **What do your frontend tests miss?**
    **Answer:** Node tests cover helpers and utilities; they do not mount React Flow or exercise real browser selection, layout, keyboard interaction and races. Build success does not fill those gaps.
    **Follow-up:** “Choose a first browser test.” **Answer:** Ingest a mocked small graph, select source, switch scope before completion and assert stale source/graph never appears.
    **Evaluates:** risk-based verification. **Evidence:** frontend/src/*.test.js; CODE:58.

## Interview 4 — AI, LLMs, tools and RAG

**Opening:** “CodeGraph's agent is a fresh-per-request LangGraph ReAct graph using seven fixed retrieval tools. It can combine metadata, inferred relationships, semantic hits and stored community summaries. It does not currently read source bodies or validate final claims, so its accuracy cannot be inferred from its tool access.”

1. **Trace an unfamiliar-behavior question through the agent.**
   **Answer:** The question reaches Claude with repository instructions and tool schemas; it may call semantic search, inspect functions in a returned file, then caller/outgoing tools. Observations become ToolMessages before final prose.
   **Follow-up:** “Is that order guaranteed?” **Answer:** No, the model chooses it; the example describes a plausible trace, not deterministic routing.
   **Evaluates:** actual orchestration. **Evidence:** AG:343,394.

2. **What information is unavailable to the agent that the UI can show?**
   **Answer:** Raw function source. The source endpoint powers CodePanel but is absent from the seven-tool registration. The agent therefore cannot verify exact implementation logic through its current tool set.
   **Follow-up:** “Could it infer it anyway?” **Answer:** It might infer from names, but that must be labeled interpretation rather than source-confirmed behavior.
   **Evaluates:** capability boundaries. **Evidence:** AG:343; DB:34.

3. **Why can a wrong-repository tool call succeed?**
   **Answer:** repo_name is model-visible input to tools. Cypher scopes to that supplied value, while no server-injected principal/scope restricts it to the chat request.
   **Follow-up:** “Can a stricter system prompt solve it?” **Answer:** It may reduce mistakes but cannot enforce authorization. Remove scope from model choice and bind it in application context.
   **Evaluates:** LLM security. **Evidence:** AG:104,394.

4. **Explain a concrete failure of the context metric.**
   **Answer:** A no-tool answer with positive baseline gives zero context and 100% efficiency even when unsupported. Repeated model rounds also resend history that this metric does not bill-count.
   **Follow-up:** “What should accompany it?” **Answer:** Evidence recall/groundedness, actual provider usage, latency and preprocessing cost; retain the metric only with its narrow name/boundary.
   **Evaluates:** measurement validity. **Evidence:** AG:369,442.

5. **Why might embeddings miss the right function?**
   **Answer:** Inputs are name/path only, generic identifiers carry little behavior, and global top-k is filtered after selection. ANN approximation adds another possible miss source.
   **Follow-up:** “Would embedding whole files fix it?” **Answer:** It may dilute function-specific evidence and introduces token limits; compare syntax-bounded code inputs and lexical hybrid retrieval on a benchmark.
   **Evaluates:** retrieval design. **Evidence:** ETL:208; AG:60.

6. **What is the difference between an invalid tool and a failed tool?**
   **Answer:** The inspected ToolNode produces an error observation for unknown tool names; ordinary execution exceptions can propagate under the default handler. CodeGraph then broadly returns chat 502.
   **Follow-up:** “Why not retry every failure?” **Answer:** Categorize transient, validation and resource errors, bound retries and avoid multiplying spend; no application policy currently does this.
   **Evaluates:** recovery semantics. **Evidence:** installed ToolNode; M:358.

7. **How would you evaluate hallucination reduction?**
   **Answer:** Fixed-SHA questions with gold source evidence, claim-level supported/contradicted/unverifiable labels, blinded review and comparable model/context budgets. Report coverage and abstention too.
   **Follow-up:** “Would fewer tokens prove it?” **Answer:** No, fewer tokens can remove essential evidence. Quality and context are separate axes.
   **Evaluates:** experiment design. **Evidence:** current metrics AG:425; [proposed evaluation](02_APPLICATION_AND_AUDIT.md#23-evaluation-methodology-and-answer-reliability).

8. **What prompt-injection content reaches this agent today?**
   **Answer:** User text, metadata and generated labels; not arbitrary whole README/source bodies through registered tools. These remain untrusted and can influence tool choice or prose.
   **Follow-up:** “What changes with a source tool?” **Answer:** Comments/docstrings become a broader untrusted channel, so enforce scope/budgets and separate evidence from instructions independently of model compliance.
   **Evaluates:** threat-model precision. **Evidence:** P:25; LABEL:93; AG:343.

9. **Why use a prebuilt graph if you need strict control?**
   **Answer:** It reduces orchestration code, but application policies must wrap it. Current code leaves history, budgets and scope enforcement unconfigured; library defaults can be surprisingly permissive or version-dependent.
   **Follow-up:** “What did local inspection reveal?” **Answer:** Installed default recursion limit is 10007 unless overridden, not a practical small spend ceiling. A Pydantic example's 25 should not be confused with this default path.
   **Evaluates:** framework literacy. **Evidence:** installed LangGraph `_internal/_config.py:32`; AG:352.

10. **How would you make the answer contract trustworthy?**
    **Answer:** Retrieve immutable source/entity references, return structured claims/citations, validate referenced IDs against actual authorized observations and flag unsupported claims. Evaluate the system, including upstream graph fidelity.
    **Follow-up:** “Can the validator prove all prose?” **Answer:** Not automatically; restrict claims, preserve uncertainty and combine mechanical reference checks with calibrated semantic/human evaluation.
    **Evaluates:** pragmatic grounding. **Evidence:** missing contract at AG:467; DB:34.

## Interview 5 — Graph databases and information retrieval

**Opening:** “The graph stores repositories, files, functions and communities, with approximate CALLS edges and metadata embeddings. Neo4j combines relationship queries, vectors and GDS, but the current identity, projection and filtering choices determine what those algorithms can actually establish.”

1. **Draw the schema and explain one missing entity.**
   **Answer:** Repository CONTAINS File, File DEFINES Function, Function CALLS Function and IN_COMMUNITY Community; ExternalFunction is an extra label. There is no Class node despite parser class-name extraction.
   **Follow-up:** “Where are methods?” **Answer:** Function records in memory have lexical qualification, but persistent functions still use simple names.
   **Evaluates:** schema/source alignment. **Evidence:** ETL queries; P:638.

2. **Why do separate ETL passes matter?**
   **Answer:** Functions need existing files for MATCH; calls should run after all definitions so cross-file simple-name targets can match internal nodes rather than remain placeholders. External tagging follows relationships.
   **Follow-up:** “Can you combine them?” **Answer:** Only with equivalent ordering/reconciliation. A single transaction changes visibility/retry costs, not the identity problem.
   **Evaluates:** data dependency reasoning. **Evidence:** ETL:290–312.

3. **What does the vector WHERE placement change?**
   **Answer:** It post-filters globally selected candidates by repo_name, potentially returning fewer than k in-scope results. It does not make the ANN candidate selection repository-local.
   **Follow-up:** “Is that cross-repo leakage?” **Answer:** Returned rows are filtered, so this is primarily a recall/candidate competition issue; authorization is a separate problem.
   **Evaluates:** query semantics. **Evidence:** AG:60; IDX vector definition.

4. **What enters Leiden and what does not?**
   **Answer:** All scoped Function nodes and CALLS relationships, including unresolved external nodes, projected undirected and unweighted. Files, embeddings, code bodies and Community nodes are not clustering inputs.
   **Follow-up:** “Can two opposite directed calls alter the projection?” **Answer:** Projection/multiedge behavior should be checked in the actual GDS version; do not assume a simple undirected deduplicated graph without measurement.
   **Evaluates:** projection specificity. **Evidence:** GDS:17.

5. **Why can a mathematically good partition be a bad architecture explanation?**
   **Answer:** Its objective optimizes graph topology, and the topology includes merged names and spurious file-scope edges. The labeler then sees only sampled names/paths and can generate a plausible wrong meaning.
   **Follow-up:** “Would higher modularity fix this?” **Answer:** No, it says nothing directly about source truth or useful module semantics.
   **Evaluates:** objective alignment. **Evidence:** ETL:178; GDS:37; LABEL:24.

6. **Compare components, Leiden and personalized PageRank for a code question.**
   **Answer:** Components find disconnected groups, Leiden finds density-based partitions, and personalized ranking would prioritize nodes around query seeds. A direct caller question needs none of the latter complexity.
   **Follow-up:** “Which is implemented?” **Answer:** Leiden and fixed direct-neighbor queries; no PPR or generic transitive retrieval algorithm.
   **Evaluates:** choosing algorithms by question. **Evidence:** GDS:37; AG:21.

7. **How could a shared external name create misleading communities?**
   **Answer:** Calls to unrelated libraries' `get` methods can merge into one Function target, connecting many files. That hub influences unweighted topology despite not being one actual dependency.
   **Follow-up:** “Would removing externals always help?” **Answer:** It could remove useful integration signals too; preserve namespace/provenance and evaluate projection variants.
   **Evaluates:** schema effects on algorithms. **Evidence:** ETL:72; GDS:18.

8. **How are source locations represented end to end?**
   **Answer:** Parser records lines/byte columns and exact snippets, but writer retains raw_code/path/name without those new ranges. The source endpoint returns a snippet, and the UI numbers it locally.
   **Follow-up:** “What does a reliable citation require?” **Answer:** Persisted canonical entity, original range and immutable source revision, not only a storage ID.
   **Evaluates:** provenance design. **Evidence:** P:498; ETL:57; DB:34.

9. **What does query LIMIT protect and what does it not?**
   **Answer:** It reduces returned rows, but upstream matches/collects/sorts may still consume substantial resources. Graph's 200-row limit also silently omits parts of the repository without pagination.
   **Follow-up:** “What would you inspect?” **Answer:** Actual plans/cardinalities on controlled graphs and an API contract that reports truncation and supports targeted expansion.
   **Evaluates:** performance reasoning. **Evidence:** DB:15,31; LABEL:28.

10. **When would you abandon Neo4j?**
    **Answer:** If evaluated user tasks mainly require simple lookups/joins and graph/GDS integration does not justify operational complexity, PostgreSQL with edges/vector support could be simpler. I would decide from workloads and maintenance constraints.
    **Follow-up:** “Can SQL reproduce direct callers?” **Answer:** Yes, an indexed edge table join; graph databases are a fit choice, not an exclusive capability.
    **Evaluates:** non-dogmatic architecture. **Evidence:** actual one-hop queries AG:21,45.

## Interview 6 — Demanding senior architectural review

**Opening:** “I would review CodeGraph as a local exploration prototype with promising integration and explicit correctness debt. Before shared deployment, I would fix graph identity/provenance, snapshot publication and authorization, then evaluate retrieval and model claims under controlled workloads.”

1. **Your resume says seven repository-scoped tools. Prove they cannot cross the request's scope.**
   **Answer:** I cannot prove that property because it is not enforced. Queries scope by the argument, but the model can choose that argument. The accurate claim is seven parameterized tools with repo predicates, not authorization-bound tools.
   **Follow-up:** “What is the minimal robust change?” **Answer:** Inject authenticated request scope outside model-visible parameters and reject mismatches everywhere.
   **Evaluates:** willingness to correct a claim. **Evidence:** AG:104,394.

2. **A deployment adds a second worker. Why did users lose graphs?**
   **Answer:** Every lifespan startup executes DELETE for all non-null repo_name nodes. The deletion is not session/worker-owned, so horizontal startup can erase active data.
   **Follow-up:** “Why didn't the volume save it?” **Answer:** Persistence stores deletion too. Retention belongs in application policy, not storage hardware assumptions.
   **Evaluates:** operational causality. **Evidence:** M:66; ETL:29.

3. **You have strong parser IDs. Why should I distrust your graph?**
   **Answer:** The writer still drops those IDs and lexical calls, merging simple names and assigning every file target to every function. Good intermediate data has not propagated across the storage contract.
   **Follow-up:** “Would one MERGE edit finish the work?” **Answer:** No, migrate edges, constraints, tool inputs/outputs, source/graph lookup and tests together, with explicit unresolved targets.
   **Evaluates:** migration completeness. **Evidence:** ID:3; ETL:55,178.

4. **An engineer claims 97.5% reduction means 97.5% cheaper answers. Respond.**
   **Answer:** The metric compares source text with selected tool text, excluding provider prompts/outputs/repeated rounds and preprocessing. It does not measure total cost, and the specific numeric benchmark has no artifacts here.
   **Follow-up:** “Could the new pipeline cost more?” **Answer:** Yes, especially for one question after expensive embeddings/labels or repeated rebuilds. Measure amortized total cost at expected usage.
   **Evaluates:** economic/measurement rigor. **Evidence:** AG:425; ETL:298,323.

5. **Your database fails after deletion but before complete rebuild. What is your recovery objective?**
   **Answer:** Current code has no defined RPO/RTO or durable recovery protocol and can lose the previous usable index. A redesign should preserve the prior active snapshot while building a new one.
   **Follow-up:** “How do you avoid expensive giant transactions?” **Answer:** Keep bounded staging writes and atomically switch a small active-generation pointer after validation.
   **Evaluates:** reliability architecture. **Evidence:** ETL:278,276.

6. **How could an attacker consume resources without executing repository code?**
   **Answer:** Submit large archives/files or many concurrent ingestions, creating memory/disk pressure, call-row products and model requests. Current URL/path checks do not limit those quantities.
   **Follow-up:** “What do you bound first?” **Answer:** Compressed/expanded bytes, files, per-file bytes, active jobs, graph rows and provider spend, with explicit rejection/degradation behavior.
   **Evaluates:** abuse and capacity thinking. **Evidence:** GH:90; P:789; ETL:178.

7. **How do you know Leiden improves answers rather than making attractive colors?**
   **Answer:** There is no stored ablation. The current architecture tool returns labels/counts, not query-specific source subgraphs. I would compare community-enabled/disabled variants at equal context and model budgets.
   **Follow-up:** “What is the gold standard?” **Answer:** Independently checked source evidence and material claims on fixed revisions, not modularity or user impressions alone.
   **Evaluates:** feature validation. **Evidence:** AG:74; GDS:37; LABEL:24.

8. **A user asks a follow-up referring to your previous answer. Why does the agent fail?**
   **Answer:** Browser history is not sent to the backend. Each invocation gets only current question and system scope; cached graph construction does not preserve conversation memory.
   **Follow-up:** “What extra correctness issue arises with memory?” **Answer:** History must be tied to repository/snapshot, or prior facts can become stale after reingestion or scope changes.
   **Evaluates:** state contracts. **Evidence:** HTTP:181; AG:394.

9. **What is your test evidence for production readiness?**
   **Answer:** It does not establish production readiness. Ninety-two isolated backend tests, four unrun DB cases, thirteen helper tests and a build give useful limited evidence. No real answer benchmark, shared-user load/race suite or deployment security validation is present.
   **Follow-up:** “What should block release?” **Answer:** Identity/fidelity fixtures, authorization isolation, snapshot recovery, bounded resource behavior and service compatibility, plus task-specific quality thresholds.
   **Evaluates:** release judgment. **Evidence:** [evidence ledger](06_EVIDENCE.md); backend/tests.

10. **If rebuilding in four weeks, what would you deliberately simplify?**
    **Answer:** Define a small reliable source/identity/snapshot contract, retain exact symbol/source lookup and direct relationships with uncertainty, and route simple questions deterministically. Add agent and community features only where controlled evaluation shows value.
    **Follow-up:** “Would that erase the project's achievement?” **Answer:** No. Understanding when integration complexity pays off is an engineering result; the existing prototype supplies concrete lessons and reusable components.
    **Evaluates:** architectural maturity. **Evidence:** [limitations](02_APPLICATION_AND_AUDIT.md#27-weaknesses-and-production-readiness-register) and [decision matrix](02_APPLICATION_AND_AUDIT.md#26-architectural-trade-off-matrix).

## Progressive pressure drills: four deeper sequences

### Drill A — from parsing to runtime truth

**Start:** “Does the parser find `obj.save()`?” → It captures supported attribute/member call syntax and retains the receiver string.

**Challenge 1:** “Which save implementation?” → Unresolved; no type/import binding proves the target.

**Challenge 2:** “But the graph has a save node.” → Legacy simple-name matching can conflate definitions; a stored edge is not resolution proof.

**Challenge 3:** “What if the new ID includes the class?” → It improves definition identity, but call-site target resolution is a separate problem and IDs are not persisted yet.

**Challenge 4:** “How would you represent what you really know?” → Caller entity plus call-site syntax/range, candidate/resolution status and provenance under an immutable snapshot; only create resolved target edges when evidence justifies them.

**Challenge 5:** “Can you then promise runtime completeness?” → No; dynamic dispatch/reflection and execution paths require runtime evidence or explicit approximation. Explain recall/precision rather than promising omniscience.

### Drill B — from token arithmetic to economic evidence

**Start:** “Compute the reduction.” → 719,000/737,000 ≈ 97.56%.

**Challenge 1:** “Where did those values come from?” → The supplied request; repository artifacts do not establish a benchmark run.

**Challenge 2:** “What does current code count?” → Supported-source baseline and concatenated tool messages using a proxy tokenizer.

**Challenge 3:** “How many times is context sent?” → Potentially across several model rounds; current metric does not sum billed input for each round.

**Challenge 4:** “What about the embedding/label costs?” → They belong in total preprocessing cost and should be amortized over useful repeated queries.

**Challenge 5:** “What if recall falls?” → Report quality/cost trade-offs; reduced context is not success unless the task's accuracy/coverage requirements are met.

### Drill C — from scoped Cypher to tenant authorization

**Start:** “Are queries scoped?” → Most match repo_name predicates; some endpoint traversal patterns rely on graph integrity.

**Challenge 1:** “Who chooses that value?” → API clients and, inside agent tools, the model.

**Challenge 2:** “What stops selecting someone else's?” → No implemented authenticated ownership boundary.

**Challenge 3:** “Will CORS stop it?” → No, non-browser clients can call the API; CORS is not an ACL.

**Challenge 4:** “What about private GitHub tokens?” → A server token authorizes the server upstream, not every downstream user.

**Challenge 5:** “Design the invariant.” → Every read/write/job/tool uses a principal-authorized tenant/repository/snapshot scope derived outside model/user-controlled selectors, with tests for cross-tenant attempts and cleanup ownership.

### Drill D — from batching to consistent publication

**Start:** “Why batches?” → Bounded payload/retry units.

**Challenge 1:** “Can readers see half a graph?” → Yes, separate commits publish partial state.

**Challenge 2:** “Can you roll back provider failure?” → Not earlier committed transactions; temp cleanup is unrelated.

**Challenge 3:** “Could a per-process lock solve it?” → Not across workers, and it does not preserve a prior graph after destructive replacement.

**Challenge 4:** “How do snapshots help?” → Write under an inactive generation, validate, then atomically activate; old data stays usable.

**Challenge 5:** “What new failures arise?” → Stale-pointer races, abandoned generations, storage growth and version-aware caches; use compare-and-swap/ordering, explicit retention and observability.

## 34. Personal contributions and AI-assisted development

The repository establishes a sequence of commits attributed to Aansh Singh and includes an architecture investigation, parser handoff contract, tests and API workflow artifacts. It does not establish manual authorship of every line, the exact AI tools used, personal time spent, rejected alternatives or subjective difficulty. Lack of that evidence is not evidence of lack of ownership.

Use these templates only after filling them with true firsthand information:

| Interview question | Defensible answer structure | What you must supply |
|---|---|---|
| Did you build this yourself? | “I owned [actual scope]. I used [actual collaborators/tools]. I can explain [specific design], and validated it with [specific checks].” | Who did what; distinguish directing/reviewing/testing from typing. |
| Did you use AI tools? | “I used [tool] for [tasks], reviewed [boundaries], and verified [behaviors]. One issue I caught was [real example].” | Actual tool usage and review practices, not a generated confession or denial. |
| How did you decide the architecture? | “My initial requirement was [real goal]. I chose [technology] because [actual reason]. In hindsight, [trade-off visible in source].” | Original constraints and alternatives genuinely considered; otherwise use present-tense rationale. |
| How did you validate AI-generated code? | “I reviewed [invariants] and ran [actual tests]. Those checks proved [scope] but did not prove [gap].” | Which changes were assisted and which checks you personally ran at the time. |
| Which components do you understand most deeply? | Choose components you can trace with exact inputs, transformations, failure paths and tests. | Your demonstrated comfort; do not list every technology automatically. |
| Most important personal contributions? | Tie two or three real decisions to diffs, validation and user impact; distinguish completed work from the pending persistence migration. | Firsthand design/review/debugging ownership. |
| Most difficult part? | Symptom→hypothesis→evidence→fix→verification→remaining limitation. | A real incident: timestamps/commit/test/log details where available. |

A technically strong contribution story could concern graph identity, parser ownership, stream framing or GDS compatibility **if you actually worked through it**. Do not claim a particular incident solely because the repository contains the relevant change. Study until you can reproduce the reasoning, then tell only your own history.

---

[Back to contents](#contents) · [Start here](README.md) · [Master index](CODEGRAPH_ENGINEERING_MASTERY.md) · [Previous](04_STUDY_AND_DEFENSE.md) · [Next](06_EVIDENCE.md)

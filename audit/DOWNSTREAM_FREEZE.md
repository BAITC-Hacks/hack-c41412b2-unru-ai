# Final bounded AI change — 2026-09-23

1–5 explicit source GIDs, directed BFS limited to four hops. Input nodes excluded as candidates. Counts distinguish all-source and partial coverage; maximum 20 results with explicit truncation. Each candidate carries one shortest witness path per reached source. No temporal/money-flow assertion and no changes to baseline roles, scores, clusters or CSV.

Local tests cover cycles, cutoff, partial coverage, deterministic order, precise string GIDs, input validation, read-only behavior, source scoping and model tool coverage. An unrelated selected UI node does not silently become a sixth source.

Live tests were separately authorized for these five source GIDs:
100000000331309100, 100000000343175100, 100000000437046100,
100000001857829100, 100000003360542100.
Destination: api.openai.com / gpt-5.4-mini. No full dataset uploaded.

First programmatic attempt: tool executed, final answer rejected by source/format validation (events in downstream_live_verification.json). The guard was retained; invalid source references now request correction within the existing five-round budget instead of immediately aborting. A fake-transport regression test covers repair; uncorrected responses still fail closed.

Second attempt in the real browser: successful, 10.3 s, find_common_downstream invoked. Answer correctly stated five all-source candidates, 934 partial candidates, 20/939 returned, and candidate 100000003115284100 with 5/5 direct coverage. UI displayed alternatives, limitations and next request. Browser error log empty. No additional live requests made. Model text remains an interpretation, not formally verified numeric truth.

Feature freeze: no Temporal or additional analytics. Remaining work is clean reproduction, delivery documentation and platform submission.

# Person A - XFlowFuzz runtime contract

This package implements the Person A portion of Algorithm 1:

- `RUNTAINTED(A, s)` through `AgentRunner` + `ToolExecutor`
- dynamic taint labels at tool I/O boundaries
- explicit-flow propagation using structural provenance and string containment
- exact `REALIZEDPATH(trace, labels)` as `result.realized_taint_paths`
- policy-confirmed replayable witnesses `w = (path, execution trace, label trace)`
- deterministic tool-trace replay
- `attempts.jsonl` and `witnesses.jsonl` matching PLAN section 6.2

Person B should consume only:

```python
result = runner.run(mutated_source_prompt, metadata=campaign_metadata)
result.execution_path
result.realized_taint_paths
result.witnesses
result.trace
result.llm_calls
result.input_tokens
result.output_tokens
result.elapsed_s
```

Coverage must use `realized_taint_paths`, not `execution_path`.

Out of scope for Person A: TDG extraction, path enumeration, seed scheduling,
coverage accounting, and LLM-guided mutation.

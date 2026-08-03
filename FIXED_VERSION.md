# Fixed path-guided version

This build fixes the repeated-source-tool issue observed in live API runs.

## Main changes

- The runner accepts an `allowed_path` and exposes only the next expected tool.
- OpenAI is forced to call the single available function during a guided path.
- Parallel tool calls are disabled in guided mode.
- Each path tool executes at most once per step.
- The previous raw tool output is bound to a type-compatible parameter of the next tool.
- Missing required control parameters receive safe defaults derived from their name/type.
- Dynamic fuzzer passes target-path metadata into the runtime trace.
- A campaign is counted successful only when the target path executes and a taint witness is produced.
- `.env` values override stale shell variables inside the project configuration.
- Added an integration regression test for `fetch_web_page -> send_email`.

## Verification

```text
14 passed
```

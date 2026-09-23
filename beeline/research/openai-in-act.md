# Calling OpenAI inside `act()` under judging: practical constraints

Research for issue #12 (map #9). Checked 2026-09-23 against primary sources: the case files in this repo, the `openai-python` repo (v3.19.0 on PyPI), and developers.openai.com (platform docs now live there).

## 1. What the case says

| Rule | Source |
|---|---|
| An LLM in the decision loop is "allowed and welcomed" (optional, gives an edge) | `beeline/case.md` §8 |
| Key comes from `os.environ["OPENAI_API_KEY"]`, and judges inject it. No hardcoded secrets | `beeline/case.md` §9 |
| The agent must finish within **10 minutes including all model calls** | `beeline/case.md` §9 |
| "LLM API may return an error": wrap calls in `try/except` and keep fallback logic. A crash still counts the pilots already run, but the result goes **negative** | `beeline/case.md` §9 |
| `submission.csv` must be reproduced by the judges re-running `make_submission.py` (mock env, `SUBMISSION_SEED = 42`). Randomness must be fixed from that seed "or the check won't match" | `make_submission.py` docstring |
| **Conflict:** `agent_template.py` docstring says "works without internet and fits in 5 minutes" | `agent_template.py` L11 |

The template docstring predates the LLM rule and contradicts case.md. **Plan for 5 minutes of wall time** so we pass under either reading, and make the agent run correctly with **no network and no key**. That no-network path is the fallback anyway.

**Custom base URL:** the case only mentions `OPENAI_API_KEY` and never a base URL, proxy, or other provider. The SDK does honour an `OPENAI_BASE_URL` env var (`openai-python` README, "Configuring the HTTP client"), so leaving `base_url` unset is harmless if judges set one. **Do not hardcode a non-OpenAI base URL or another provider's key.** Judges only give us an OpenAI key, so anything else fails on judging. We also don't know what model access the judges' key has, so the model id must be overridable and a 404 must fall back.

## 2. Models for a small structured decision call

From developers.openai.com/api/docs/models and `/models/gpt-6-luna`:

| Model | $/1M in / out | `reasoning.effort` | Note |
|---|---|---|---|
| `gpt-6-luna` | 0.10 / 0.50 | none, low, **medium (default)**, high, xhigh, max | "cost-sensitive, high-volume". Structured outputs, Chat + Responses. Tier-1: 500 RPM / 500k TPM |
| `gpt-6-sol` | 2 / 10 | none … max | balance of intelligence and cost |
| `gpt-6-astra` | 10 / 50 | low … max (**no `none`**) | most capable, slowest |

The SDK README examples use `gpt-5.5`. Structured Outputs `json_schema` strict mode works on "gpt-4o-mini, gpt-4o-2024-08-06, and later".

**Pick `gpt-6-luna` with reasoning effort `none`.** It is the cheapest and fastest option, and `none` is what makes `temperature` usable (next section). The default effort is `medium`, which is slower and non-deterministic, so set `none` explicitly.

## 3. Determinism: what `temperature`, `seed`, and schemas actually guarantee

- **`temperature`**: "When reasoning effort is not `none`, remove `temperature`, `top_p`, and `top_logprobs`" (docs/guides/latest-model). So `temperature=0` only works with `reasoning_effort="none"` on Luna or Sol.
- **`seed`** exists **only on Chat Completions** (`chat/completion_create_params.py`). It is absent from `responses/response_create_params.py`. Its SDK docstring: "This feature is in Beta … best effort to sample deterministically … **Determinism is not guaranteed**, and you should refer to the `system_fingerprint` response parameter to monitor changes in the backend."
- **Structured Outputs** guarantee *shape*, not *content*: "the model will always generate responses that adhere to your supplied JSON Schema". All fields must be required, `additionalProperties: false`, and enums are enforced. A refusal comes back in a `refusal` field instead of the parsed object. The first request with a new schema has extra latency while the schema is processed (docs/guides/structured-outputs).

**Conclusion:** temperature 0, a seed and a strict schema make answers *usually* identical, never *guaranteed*. On its own, a live call inside `act()` can break the `make_submission.py` re-run check. That is why the cache in §6 exists.

## 4. Timeouts, retries, and time budget (openai-python)

From `src/openai/_constants.py` and the README ("Retries", "Timeouts"):

- The default timeout is **600 s (`connect=5.0`)**, which is the entire 10-minute budget. **Always override it.**
- `DEFAULT_MAX_RETRIES = 2`, with exponential backoff from 0.5 s up to 8 s. `Retry-After` is honoured up to 120 s. Retries cover connection errors, 408, 409, 429 and >=500. A **timeout is also retried**, so the worst case per call is about `(max_retries+1) × timeout + backoff`.
- Set it with `OpenAI(timeout=..., max_retries=...)` or per call with `client.with_options(timeout=..., max_retries=...)`. The SDK now uses HTTPX2, so `httpx2.Timeout(...)` gives finer control.
- Rate limits: "unsuccessful requests contribute to your per-minute limit, so continuously resending a request won't work" (docs/guides/rate-limits). Don't loop on retries yourself.

**Latency:** OpenAI publishes no fixed numbers. The latency guide says output tokens dominate ("cutting 50% of your output tokens may cut ~50% of your latency", while cutting input tokens gains only 1–5%), and it recommends smaller models and fewer, parallel requests. For a short JSON answer with effort `none` on Luna, expect roughly 1–3 s per call. That figure is our estimate, not a documented one. So: few calls, short outputs, and a global deadline checked before each call.

## 5. Errors to catch

From the README "Handling errors" section: everything inherits from `openai.APIError`.

| Error | Meaning | Action |
|---|---|---|
| `APIConnectionError` / `APITimeoutError` | no network or timeout (already retried) | fallback |
| `RateLimitError` (429) | rate limit, or `insufficient_quota` | fallback, no extra retry |
| `AuthenticationError` (401) / `PermissionDeniedError` (403) | bad or missing key | disable the LLM for the rest of the run |
| `NotFoundError` (404) | the key has no access to the model id | disable the LLM, fall back |
| `BadRequestError` (400) | e.g. `temperature` sent with reasoning enabled, or a bad schema | a bug. Fall back, but fix it locally |
| `InternalServerError` (>=500) | server side | fallback |
| `pydantic.ValidationError`, `refusal` set, `parsed is None` | unusable content | fallback |

A missing `OPENAI_API_KEY` raises `openai.OpenAIError` when the client is **constructed**, so construct the client inside the `try` too. In practice use `except Exception` around the whole call and log the type. The case cares that we don't crash, not how precisely we classify errors.

## 6. Recommended call pattern

1. **The LLM advises, the code decides.** Code computes the candidate set deterministically (cells, tariffs, channels, pilot stats). The LLM only picks or ranks among enum values we supply, and the code validates the answer against the constraints (≤10 campaigns, ≤5 000 per campaign, budget) before acting. The deterministic heuristic is always the fallback.
2. **Call:** Chat Completions, because it is the only endpoint with `seed`, through `client.chat.completions.parse(...)` with a Pydantic `response_format`:
   `model=os.environ.get("OPENAI_MODEL", "gpt-6-luna")`, `reasoning_effort="none"`, `temperature=0`, `seed=42`, `max_completion_tokens` small (about 300), and a strict schema whose choices are enums.
3. **Budget:** `OpenAI(timeout=20.0, max_retries=1)`, which is at most about 45 s per call. Record `t0 = time.monotonic()` at the start of `act()`. Skip the LLM when less than about 60 s would remain inside a **4-minute LLM budget**, and cap the run at about 5 LLM calls.
4. **Fail closed:** `try/except Exception` gives `None` and the heuristic runs. After an auth or 404 error, set `self._llm_ok = False` and skip the remaining calls.
5. **Response cache for reproducibility:** key each call by `sha256(model + json.dumps(messages, sort_keys=True) + schema)` and store the parsed JSON in `llm_cache.json` next to `agent.py`. **Commit that file together with `submission.csv`.** When the judges re-run `make_submission.py` (seed 42), the prompts are identical, so every call is a cache hit: no network, and an identical CSV even if the backend drifts or their key/model differs. On the hidden judging env the prompts differ, so calls go live. That is fine because nothing is compared there. Record `system_fingerprint` in the cache entry for traceability. Add `openai` (and `pydantic`) to `requirements.txt`.

```python
import hashlib, json, os, time
from pydantic import BaseModel

CACHE_PATH = os.path.join(os.path.dirname(__file__), "llm_cache.json")

def llm_choose(messages, schema: type[BaseModel], deadline: float):
    model = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
    key = hashlib.sha256(json.dumps([model, messages, schema.model_json_schema()],
                                    sort_keys=True).encode()).hexdigest()
    try:
        cache = json.load(open(CACHE_PATH))
    except Exception:
        cache = {}
    if key in cache:
        return schema.model_validate(cache[key]["parsed"])
    if time.monotonic() > deadline:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(timeout=20.0, max_retries=1)  # key from OPENAI_API_KEY
        r = client.chat.completions.parse(
            model=model, messages=messages, response_format=schema,
            reasoning_effort="none", temperature=0, seed=42, max_completion_tokens=300)
        parsed = r.choices[0].message.parsed
        if parsed is None:  # refusal
            return None
        cache[key] = {"parsed": parsed.model_dump(), "fp": r.system_fingerprint}
        json.dump(cache, open(CACHE_PATH, "w"), ensure_ascii=False, indent=1)
        return parsed
    except Exception as e:  # APIError, ValidationError, missing key, ...
        print(f"[llm] fallback: {type(e).__name__}")
        return None
```

## Open questions

- Which models the judges' key can access. We can't know this, which is why the model is overridable with `OPENAI_MODEL` and 404 falls back.
- Whether "5 minutes / no internet" (template) or "10 minutes with LLM" (case.md) is authoritative. Ask the organisers. Budgeting for 5 minutes is safe either way.

## Sources

- `beeline/case.md` §8–9. `beeline/beeline_case_participants (1)/make_submission.py` and `agent_template.py`
- openai-python README: https://github.com/openai/openai-python/blob/main/README.md (Usage, Handling errors, Retries, Timeouts, base_url)
- openai-python `src/openai/_constants.py` (default timeout and retries), `types/chat/completion_create_params.py` (`seed`, `reasoning_effort`), `types/responses/response_create_params.py` (no `seed`), `types/chat/chat_completion.py` (`system_fingerprint`), `helpers.md` (`.parse()`)
- https://developers.openai.com/api/docs/models and https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/guides/latest-model (sampling params vs reasoning effort)
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/guides/latency-optimization
- https://developers.openai.com/api/docs/guides/rate-limits

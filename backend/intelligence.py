"""
Evidence-grounded ICP extraction.

Turns a set of retrieved, citable evidence items into structured ICP intelligence
using an LLM that is allowed to reason ONLY over the supplied evidence.

Two hard rules, both enforced structurally rather than by convention:

1. The prompt requires every claim to cite an `evidence_id` from the supplied set.
2. `engine.validate_grounding()` re-checks those citations afterwards and drops
   any claim whose id is not in the evidence set — so an uncited or invented
   claim cannot survive into the result.

Model note: use `deepseek/deepseek-v4.1-flash`.
Do NOT switch to `google/gemini-3.7-flash` — it is a reasoning model that returns
`content: null` with the budget spent on reasoning tokens, so JSON parsing fails.

Token note: deepseek-v4.1-flash ALSO spends part of the budget on reasoning tokens
(observed 776-1471 per call). `max_tokens` must therefore cover reasoning + content
combined, or `content` comes back truncated/empty and parsing fails. `response_format:
json_object` was observed to push reasoning longer and truncate the content, so the
format is enforced by the prompt instead.
"""

import json
import os
import re
import urllib.request
from typing import Any, Dict, List

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
EXTRACTION_MODEL = os.environ.get("SYNDICATE_LLM_MODEL", "deepseek/deepseek-v4.1-flash")

MAX_EVIDENCE_IN_PROMPT = 12
QUOTE_CHARS_PER_ITEM = 500
# Must cover reasoning + content combined.
REQUEST_MAX_TOKENS = 4000
RETRY_MAX_TOKENS = 6000

SYSTEM_PROMPT = (
    "You are a commercial research analyst. You extract structured intelligence "
    "STRICTLY from provided evidence. You never add outside knowledge, never guess, "
    "and never invent sources. If the evidence does not support a field, you return "
    "an empty array for that field."
)

INSTRUCTIONS = """From the numbered EVIDENCE only, extract intelligence about the target market.

RULES:
- Use ONLY the EVIDENCE below. Do not use prior knowledge.
- Every item in pain_points and buying_triggers MUST cite the id of the evidence
  item that supports it (for example "e3").
- The "quote" must be copied verbatim from that evidence item's text.
- online_spaces: only online communities/subreddits that literally appear in the
  EVIDENCE. Do not suggest generic or well-known communities.
- If a field is not supported by the evidence, return an empty array for it.
- Return ONLY valid JSON, no markdown fences, no commentary.

Return exactly this shape:
{
  "pain_points": [{"claim": "...", "evidence_id": "eN", "quote": "..."}],
  "buying_triggers": [{"claim": "...", "evidence_id": "eN"}],
  "icp_titles": ["..."],
  "online_spaces": ["..."]
}
"""


def _api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")


def build_prompt(company_name: str, business_type: str, offering: str,
                 sample_customers: str, evidence: List[Dict[str, Any]]) -> str:
    """Assemble the evidence block plus extraction instructions."""
    blocks = []
    for e in evidence[:MAX_EVIDENCE_IN_PROMPT]:
        quote = (e.get("quote") or "")[:QUOTE_CHARS_PER_ITEM]
        blocks.append(
            f"[{e.get('id')}] source={e.get('source')} url={e.get('url')}\n{quote}"
        )
    evidence_block = "\n\n".join(blocks) if blocks else "(no evidence retrieved)"

    return (
        f"{INSTRUCTIONS}\n"
        f"TARGET: company={company_name!r} sector={business_type!r} "
        f"offering={offering!r} described customers={sample_customers!r}\n\n"
        f"EVIDENCE:\n{evidence_block}\n"
    )


def _strip_fences(text: str) -> str:
    """Models sometimes wrap JSON in ```json fences despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _scan(t: str):
    """Single pass: return (balanced_end_index, open_containers_stack, in_string)."""
    depth = 0
    stack = []
    in_str = False
    esc = False
    balanced_end = -1
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            depth -= 1
            if stack:
                stack.pop()
            if depth == 0:
                balanced_end = i
    return balanced_end, stack, in_str


def _salvage_json(text: str) -> Dict[str, Any]:
    """
    Last-resort parse for output truncated mid-object by the token budget.

    First tries the largest balanced prefix; if the whole thing is unbalanced,
    cuts back to the last complete array element and closes the open containers.
    Returns {} when it cannot be salvaged.
    """
    t = _strip_fences(text)
    start = t.find("{")
    if start < 0:
        return {}
    t = t[start:]

    balanced_end, stack, in_str = _scan(t)
    candidates = []
    if balanced_end > 0:
        candidates.append(t[:balanced_end + 1])

    # Cut back to the last comma that is not inside a string, then close up.
    if not in_str and stack:
        cut = t.rfind(",")
        if cut > 0:
            partial = t[:cut]
            _, stack2, in_str2 = _scan(partial)
            closed = partial + ('"' if in_str2 else "") + "".join(reversed(stack2))
            candidates.append(closed)

    for cand in candidates:
        cand = re.sub(r",\s*([}\]])", r"\1", cand)
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return {}


def _post(prompt: str, max_tokens: int, timeout: int) -> Dict[str, Any]:
    """One completion call. Returns {'content': str, 'finish': str, 'model': str}."""
    body = json.dumps({
        "model": EXTRACTION_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        # Reasoning is disabled deliberately. This task is selection and
        # paraphrase over evidence that is already in the prompt, not problem
        # solving. Leaving reasoning on let it consume the entire token budget
        # on some runs (finish_reason=length, empty content), and it cost
        # 100-1500 reasoning tokens plus seconds of latency for no gain.
        # Measured: 152 reasoning tokens / 4.1s -> 0 tokens / 1.8s.
        "reasoning": {"enabled": False},
    }).encode("utf-8")

    req = urllib.request.Request(
        OPENROUTER_URL, data=body,
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    choice = (data.get("choices") or [{}])[0]
    return {
        "content": (choice.get("message") or {}).get("content") or "",
        "finish": choice.get("finish_reason"),
        "model": data.get("model") or EXTRACTION_MODEL,
    }


def _empty() -> Dict[str, Any]:
    return {
        "pain_points": [],
        "buying_triggers": [],
        "icp_titles": [],
        "online_spaces": [],
        "model": EXTRACTION_MODEL,
        "ok": False,
    }


def extract_icp(evidence: List[Dict[str, Any]], company_name: str, business_type: str,
                offering: str, sample_customers: str, timeout: int = 150) -> Dict[str, Any]:
    """
    Ask the LLM for structured ICP intelligence grounded in `evidence`.

    Returns {} -shaped defaults with ok=False on ANY failure (missing key, HTTP
    error, null content, unparseable JSON). The caller must then degrade to
    evidence-only output; it must never substitute hardcoded text.
    """
    key = _api_key()
    if not key:
        print("  ⚠ OPENROUTER_API_KEY missing - skipping extraction")
        return _empty()
    if not evidence:
        print("  ⚠ no evidence to extract from")
        return _empty()

    prompt = build_prompt(company_name, business_type, offering, sample_customers, evidence)

    # Attempt 1: full evidence set with the standard budget.
    attempts = [(prompt, REQUEST_MAX_TOKENS)]
    # Attempt 2: the budget was likely eaten by reasoning - retry with a bigger
    # budget and a shorter evidence set so there is room for the content.
    if len(evidence) > 6:
        attempts.append((
            build_prompt(company_name, business_type, offering, sample_customers, evidence[:6]),
            RETRY_MAX_TOKENS,
        ))

    last_finish = None
    for i, (p, budget) in enumerate(attempts, start=1):
        try:
            res = _post(p, budget, timeout)
        except Exception as e:
            print(f"  ⚠ extraction request failed (attempt {i}): "
                  f"{type(e).__name__}: {str(e)[:200]}")
            continue

        content = res["content"]
        last_finish = res.get("finish")

        parsed = {}
        if content:
            try:
                parsed = json.loads(_strip_fences(content))
            except Exception:
                parsed = _salvage_json(content)
                if parsed:
                    print(f"  · recovered truncated JSON on attempt {i}")

        if isinstance(parsed, dict) and parsed:
            out = {
                "pain_points": parsed.get("pain_points") or [],
                "buying_triggers": parsed.get("buying_triggers") or [],
                "icp_titles": parsed.get("icp_titles") or [],
                "online_spaces": parsed.get("online_spaces") or [],
                "model": res.get("model") or EXTRACTION_MODEL,
                "ok": True,
            }
            print(f"  ✓ Extraction: {len(out['pain_points'])} pain points, "
                  f"{len(out['buying_triggers'])} triggers, "
                  f"{len(out['icp_titles'])} ICP titles, "
                  f"{len(out['online_spaces'])} online spaces")
            return out

        print(f"  ⚠ extraction attempt {i} unusable "
              f"(content={'empty' if not content else len(content)} chars, finish={last_finish})")

    print("  ⚠ extraction failed on all attempts - returning no claims")
    return _empty()
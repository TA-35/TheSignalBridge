"""Call a llama-server running the rewrite model.

Used by the baseline run, eval, and (later) the inference API. Everything
about the prompt comes from compose_prompt; this module only moves it over
HTTP and reads the answer back.

Standard library only, for the same reason as compose_prompt.

Start the server first. Baseline (untrained, needs few_shot=True):

    llama-server -hf unsloth/Qwen3.5-4B-GGUF:Q4_K_M --jinja \\
        --chat-template-kwargs '{"enable_thinking":false}' --port 8080

Then, from the repo root:

    python -m Src.source.pipeline.compose_client --few-shot "no rush but could you check the deck?"
    python -m Src.source.pipeline.compose_client --few-shot --input data/gold/enron_gold.jsonl \\
        --limit 10 --out eval/baseline_sample.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import compose_prompt as cp

DEFAULT_URL = "http://localhost:8080"
DEFAULT_TEMPERATURE = 0.3
# A ceiling, not a target. The longest source (Enron, 439 tokens) plus
# meaning and notes comes to ~600; a cut-off reply is invalid JSON.
MAX_TOKENS = 1024


class ComposeServerError(RuntimeError):
    """The server could not be reached or returned an error."""


def _post(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # The body names the problem (bad schema, context overflow); the
        # status line alone does not.
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise ComposeServerError(f"HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ComposeServerError(f"cannot reach {url}: {exc}") from None


def complete(
    source: str,
    signals: Iterable[Mapping[str, Any]] | None,
    *,
    few_shot: bool = False,
    base_url: str = DEFAULT_URL,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """One rewrite. Returns {"meaning", "rewrite", "notes"} plus `raw` and `seconds`.

    Raises ComposeServerError if the server fails, ComposeOutputError if it
    answers with something that is not a usable rewrite.
    """
    payload = {
        "messages": cp.build_messages(source, signals, few_shot=few_shot),
        "temperature": temperature,
        "max_tokens": MAX_TOKENS,
        # Constrains decoding to the schema, so a small model cannot wander
        # off into prose. parse_response still checks, in case a server
        # build ignores it.
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "compose", "schema": cp.RESPONSE_SCHEMA},
        },
        # Also set on the server's command line; repeated here so a server
        # started without the flag cannot silently think.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    started = time.monotonic()
    body = _post(f"{base_url.rstrip('/')}/v1/chat/completions", payload, timeout)
    seconds = time.monotonic() - started
    try:
        raw = body["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise ComposeServerError(f"unexpected response shape: {str(body)[:300]}") from None
    result = cp.parse_response(raw)
    return {**result, "raw": raw, "seconds": round(seconds, 2)}


def _run_one(record: Mapping[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    out = {"id": record.get("id"), "source": record["source"],
           "prompt": cp.fingerprint(), "few_shot": args.few_shot}
    try:
        out.update(complete(record["source"], record.get("signals"), few_shot=args.few_shot,
                            base_url=args.url, temperature=args.temperature))
    except (cp.ComposeOutputError, ComposeServerError) as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("messages", nargs="*", help="messages to rewrite (no signals)")
    ap.add_argument("--input", type=Path, help="JSONL with source (+ signals), e.g. a gold file")
    ap.add_argument("--limit", type=int, default=0, help="only the first N records of --input")
    ap.add_argument("--out", type=Path, help="write results as JSONL here")
    ap.add_argument("--few-shot", action="store_true", help="include the examples (baseline)")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = ap.parse_args(argv)

    records: list[dict[str, Any]] = [{"id": f"cli_{i}", "source": m} for i, m in enumerate(args.messages, 1)]
    if args.input:
        lines = [json.loads(l) for l in args.input.read_text(encoding="utf-8").splitlines() if l.strip()]
        records += lines[: args.limit] if args.limit else lines
    if not records:
        ap.error("give messages or --input")

    results = []
    for record in records:
        r = _run_one(record, args)
        results.append(r)
        print(f"\n=== {r['id']}  ({r.get('seconds', '-')}s)")
        print(f"SOURCE : {r['source']}")
        if "error" in r:
            print(f"ERROR  : {r['error']}")
        else:
            m = r["meaning"]
            print(f"MEANING: ask={m['ask']!r} deadline={m['deadline']!r} urgency={m['urgency']}")
            print(f"REWRITE: {r['rewrite']}")
            for note in r["notes"]:
                print(f"  - {note}")

    failed = sum("error" in r for r in results)
    print(f"\n{len(results) - failed}/{len(results)} parsed; prompt {cp.fingerprint()}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results),
                            encoding="utf-8")
        print(f"wrote {args.out}")
    return 1 if failed == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())

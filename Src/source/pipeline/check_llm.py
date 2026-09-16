"""Preflight: is the key wired up and reaching the model?

    python Src/source/pipeline/check_llm.py

One tiny request. Reports where the key came from, which model answered, and
whether the response parsed - before you spend a twenty-example run finding
out something was misconfigured.

The key itself is never printed, only whether one was found and from where.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parents[2]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[2]))

from Src.source.pipeline.config import load  # noqa: E402
from Src.source.pipeline.llm import LLMError, complete  # noqa: E402


def main() -> int:
    config = load()

    from Src.source.pipeline.config import PROVIDER_DEFAULTS

    provider = config.llm.provider
    key_env = PROVIDER_DEFAULTS.get(provider, {}).get("key_env") or "?"

    # Ask config for the key it actually resolved, rather than scanning the
    # environment again here. A preflight that applies different rules to the
    # real code path reports failures that would never happen, and passes
    # ones that would - which is exactly what this script exists to prevent.
    print(f"credentials (provider: {provider})")
    resolved = config.llm.api_key
    if resolved:
        holder = next(
            (n for n in ("NVIDIA_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY",
                         "ANTHROPIC_API_KEY")
             if os.environ.get(n) == resolved),
            "(unknown variable)")
        print(f"  resolved from {holder} ({len(resolved)} chars, "
              f"starts {resolved[:7]}..., never logged)")
        if holder != key_env:
            print(f"  note: {provider} normally reads {key_env}; using {holder}")
        expected = {"nvidia": "nvapi-", "openai": "sk-", "anthropic": "sk-ant-"}
        want = expected.get(provider)
        if want and not resolved.startswith(want):
            print(f"  WARNING: {provider} keys usually start {want!r}. A key for "
                  f"one host sent to another fails as AuthenticationError,")
            print(f"           which looks like a bad key but is the wrong endpoint.")
    elif os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("  ANTHROPIC_AUTH_TOKEN found")
    else:
        print(f"  NO KEY FOUND. Expected {key_env}")
        print("  Put one in a .env file or export it:")
        print("     cp Src/source/pipeline/.env.example Src/source/pipeline/.env")
        print(f"     # then edit it, or:  export {key_env}=...")
        return 1

    for name in (".env", "backend/.env", "Src/source/pipeline/.env"):
        path = HERE.parents[2] / name
        print(f"  {'found  ' if path.is_file() else 'absent '} {name}")

    print("\nconfiguration")
    print(f"  provider  {config.llm.provider}")
    print(f"  model     {config.llm.model}")
    print(f"  endpoint  {config.llm.base_url or '(SDK default)'}")
    print(f"  effort    {config.llm.effort}")
    print(f"  spans in prompt    {config.include_extracted_spans}")
    print(f"  comments in prompt {config.include_model_comments}")

    print("\nsending one small request...")
    prompt = (
        'Reply with JSON only, matching the schema you were given. '
        'Set summary to the single word "ready", claims to an empty list, '
        'and unstated to an empty list.'
    )
    try:
        result = complete(prompt, config.llm)
    except LLMError as exc:
        print(f"  FAILED: {exc}")
        print("\n  Common causes: an invalid or revoked key, no network, or a")
        print("  PIPELINE_LLM_MODEL that your key cannot access.")
        return 1

    print(f"  OK - {result.model} via {result.provider} answered in "
          f"{result.attempts} attempt(s)")
    print(f"  parsed keys: {sorted(result.data)}")
    print("\nReady. Next:")
    print("  python Src/source/pipeline/run_examples.py --both")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

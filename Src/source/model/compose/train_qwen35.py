#!/usr/bin/env python3
"""Fine-tune Qwen3.5-4B to rewrite messages (16-bit LoRA, Unsloth) and export GGUF.

Every training example is built by Src/source/pipeline/compose_prompt.py, the
same module the baseline, eval and serving use, so the model is trained on
exactly the prompt it will be served with. Thinking is off everywhere.

Run on the GPU box, from the repo root, inside tmux:

    python Src/source/model/compose/train_qwen35.py --dry-run     # 20 examples, 5 steps, full export
    python Src/source/model/compose/train_qwen35.py               # the real run

--dry-run works before any training data exists: if data/filtered/train.jsonl
is missing it trains on the style-guide examples. Its job is to prove the
path end to end - load, format, mask, train, merge, GGUF - not to learn.

Reads exactly source, signals, rewrite and notes from each record. Refuses to
run if a training source is also a gold message (rule 2) or was generated
with a different prompt than the current one (rule 1).

Outputs go to runs/<name>/: the LoRA adapter, the GGUF, and run.json with
everything needed to reproduce the run.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from Src.source.pipeline import compose_prompt as cp  # noqa: E402

BASE_MODEL = "unsloth/Qwen3.5-4B"
TRAIN_FILE = "data/filtered/train.jsonl"
GOLD_GLOB = "data/gold/*_gold.jsonl"
REQUIRED = ("source", "signals", "rewrite", "notes")
DRY_RUN_EXAMPLES = 20
DRY_RUN_STEPS = 5

# From Unsloth's Qwen3.5 guide: all attention and MLP projections.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


# --------------------------------------------------------------------------
# Data - pure Python, so it can be checked on a laptop without a GPU
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text).lower()).strip()


def gold_sources(pattern: str = GOLD_GLOB) -> set[str]:
    out = set()
    for path in glob.glob(str(REPO_ROOT / pattern)):
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.add(_norm(json.loads(line)["source"]))
    return out


def load_records(path: Path, gold: set[str], fingerprint: str) -> list[dict[str, Any]]:
    """Training records, checked. Raises SystemExit naming the first bad row.

    The filter already does all of this; it is repeated here because this is
    the last point before the data is baked into weights.
    """
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        missing = [k for k in REQUIRED if k not in r]
        if missing:
            raise SystemExit(f"{path}:{n} is missing {missing}")
        if _norm(r["source"]) in gold:
            raise SystemExit(f"{path}:{n} ({r.get('id')}) is a gold message - never train on gold")
        version = r.get("prompt_version")
        if version and version != fingerprint:
            raise SystemExit(f"{path}:{n} ({r.get('id')}) was made with prompt {version}, "
                             f"current is {fingerprint} - regenerate or refilter")
        records.append({k: r[k] for k in ("id", *REQUIRED) if k in r})
    return records


def dry_run_records() -> list[dict[str, Any]]:
    """The style-guide examples, cycled to DRY_RUN_EXAMPLES rows."""
    ex = list(cp.examples())
    return [{**ex[i % len(ex)], "id": f"dry_{i}"} for i in range(DRY_RUN_EXAMPLES)]


def drop_signals(records: list[dict[str, Any]], rate: float, seed: int) -> tuple[list[dict[str, Any]], int]:
    """Replace ~rate of all individual signals with the production failure
    shape, so the model has seen a classifier go down before it happens live.
    Seeded, so a rerun drops the same ones."""
    rng = random.Random(seed)
    out, dropped = [], 0
    for r in records:
        signals = []
        for s in cp.clean_signals(r["signals"]):
            if s["label"] != "unknown" and rng.random() < rate:
                s, dropped = cp.failed_signal(s["model"]), dropped + 1
            signals.append(s)
        out.append({**r, "signals": signals})
    return out, dropped


def to_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    """System + user from compose_prompt, assistant = the target JSON."""
    return cp.build_messages(record["source"], record["signals"]) + [
        {"role": "assistant", "content": cp.assistant_response(record)}
    ]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# --------------------------------------------------------------------------
# Chat template - where the prompt ends and the answer starts
# --------------------------------------------------------------------------

def render(tokenizer, messages, **kw) -> str:
    return tokenizer.apply_chat_template(messages, tokenize=False, enable_thinking=False, **kw)


def response_marker(tokenizer) -> str:
    """The exact text the template puts between the last user turn and the
    assistant's answer, with thinking off - e.g. "<|im_start|>assistant\\n"
    plus an empty think block.

    Derived from the tokenizer instead of hardcoded: if the template differs
    from what we expect, masking against a hardcoded string would silently
    train on the prompt.
    """
    probe = [{"role": "user", "content": "x"}]
    with_prompt = render(tokenizer, probe, add_generation_prompt=True)
    without = render(tokenizer, probe, add_generation_prompt=False)
    if not with_prompt.startswith(without) or with_prompt == without:
        raise SystemExit("could not isolate the assistant generation prompt from the chat template")
    return with_prompt[len(without):]


def check_train_matches_serving(tokenizer, messages) -> None:
    """The training text must start with exactly what llama-server sends at
    inference (the same messages minus the answer, generation prompt on,
    thinking off). If not, the model trains on one prompt and serves on another."""
    full = render(tokenizer, messages)
    served = render(tokenizer, messages[:-1], add_generation_prompt=True)
    if not full.startswith(served):
        raise SystemExit("training text does not start with the serving prompt - "
                         "check the chat template / enable_thinking handling\n"
                         f"served tail: {served[-120:]!r}\ntrain  part: {full[len(served) - 120:len(served)]!r}")


# --------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true",
                    help=f"{DRY_RUN_EXAMPLES} examples, {DRY_RUN_STEPS} steps, full export path")
    ap.add_argument("--data", type=Path, default=REPO_ROOT / TRAIN_FILE)
    ap.add_argument("--name", default=None, help="run folder under runs/ (default: timestamp)")
    ap.add_argument("--model", default=BASE_MODEL)
    ap.add_argument("--max-seq-len", type=int, default=1024)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=4)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=16)
    ap.add_argument("--signal-dropout", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=3407)
    ap.add_argument("--quant", default="q4_k_m")
    ap.add_argument("--no-export", action="store_true", help="skip the GGUF export")
    ap.add_argument("--keep-merged", action="store_true",
                    help="keep the merged 16-bit model after the GGUF export (~8.7GB)")
    args = ap.parse_args(argv)

    started = time.time()
    fingerprint = cp.fingerprint()
    name = args.name or ("dry_run" if args.dry_run else time.strftime("run_%Y%m%d_%H%M"))
    out_dir = REPO_ROOT / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- data
    if args.data.exists():
        records = load_records(args.data, gold_sources(), fingerprint)
        data_source = str(args.data.relative_to(REPO_ROOT)) if args.data.is_relative_to(REPO_ROOT) else str(args.data)
        data_hash = file_sha256(args.data)
    elif args.dry_run:
        print(f"{args.data} not found - dry run uses the style-guide examples")
        records, data_source, data_hash = dry_run_records(), "compose_examples.json", None
    else:
        raise SystemExit(f"{args.data} not found - run the filter first, or use --dry-run")
    if args.dry_run:
        records = records[:DRY_RUN_EXAMPLES]
    records, dropped = drop_signals(records, args.signal_dropout, args.seed)
    print(f"{len(records)} records from {data_source}; {dropped} signals set to unknown; "
          f"prompt {fingerprint}")

    # ---- model (imported here so the data checks above run without a GPU stack)
    from unsloth import FastLanguageModel, is_bfloat16_supported  # noqa: E402
    from unsloth.chat_templates import train_on_responses_only  # noqa: E402
    from datasets import Dataset  # noqa: E402
    from trl import SFTConfig, SFTTrainer  # noqa: E402
    import torch  # noqa: E402

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=False,      # Unsloth: no QLoRA for Qwen3.5
        load_in_16bit=True,
        full_finetuning=False,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.r,
        lora_alpha=args.alpha,
        target_modules=TARGET_MODULES,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
        max_seq_length=args.max_seq_len,
    )
    bf16 = is_bfloat16_supported()
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"
    print(f"GPU {gpu}; {'bf16' if bf16 else 'fp16 (this GPU has no bf16)'}")

    # ---- format, and prove train == serve before spending GPU time
    tok = getattr(tokenizer, "tokenizer", tokenizer)   # VLM processors wrap the tokenizer
    conversations = [to_messages(r) for r in records]
    check_train_matches_serving(tok, conversations[0])
    marker = response_marker(tok)
    texts = [render(tok, m) for m in conversations]
    lengths = [len(tok(t)["input_ids"]) for t in texts]
    keep = [i for i, n in enumerate(lengths) if n <= args.max_seq_len]
    too_long = len(texts) - len(keep)
    if too_long:
        print(f"dropping {too_long} examples longer than {args.max_seq_len} tokens")
    texts = [texts[i] for i in keep]
    print(f"tokens per example: max {max(lengths)}, mean {sum(lengths) / len(lengths):.0f}")

    dataset = Dataset.from_dict({"text": texts})
    trainer = SFTTrainer(
        model=model,
        tokenizer=tok,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_seq_length=args.max_seq_len,
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=args.grad_accum,
            num_train_epochs=args.epochs,
            max_steps=DRY_RUN_STEPS if args.dry_run else -1,
            learning_rate=args.lr,
            warmup_ratio=0.05,
            lr_scheduler_type="linear",
            optim="adamw_8bit",
            bf16=bf16,
            fp16=not bf16,
            logging_steps=1,
            save_strategy="no",
            output_dir=str(out_dir / "trainer"),
            seed=args.seed,
            report_to="none",
            dataset_num_proc=1,
        ),
    )
    # Qwen uses ChatML. Anything else means the template is not what this
    # script was written against, and the masking strings below would be wrong.
    if not marker.startswith("<|im_start|>assistant"):
        raise SystemExit(f"unexpected chat template, assistant prompt is {marker!r}")
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part=marker,
    )

    # Show what the loss actually sees on example 0: it must be the JSON answer only.
    labels = trainer.train_dataset[0]["labels"]
    trained = tok.decode([t for t in labels if t != -100])
    print(f"response marker: {marker!r}")
    print(f"trained part of example 0: {trained!r}")
    expected = cp.assistant_response(records[keep[0]])
    if expected not in trained or len(trained) > len(expected) + 40:
        raise SystemExit("masking is wrong: the trained tokens are not just the answer")

    stats = trainer.train()
    print(f"train loss {stats.training_loss:.4f}")

    # ---- save
    adapter_dir = out_dir / "lora"
    model.save_pretrained(str(adapter_dir))
    tok.save_pretrained(str(adapter_dir))
    gguf_files: list[str] = []
    if not args.no_export:
        merged_dir = out_dir / "merged"
        model.save_pretrained_gguf(str(merged_dir), tok, quantization_method=args.quant)
        # Unsloth writes the merged 16-bit model to merged_dir and the GGUF to
        # a sibling it names itself ("merged_gguf"), so search the whole run.
        gguf_files = sorted(str(p.relative_to(out_dir)) for p in out_dir.rglob("*.gguf"))
        if not gguf_files:
            raise SystemExit(f"export finished but no .gguf file under {out_dir}")
        # The 16-bit copy is ~8.7GB and only an intermediate: the LoRA adapter
        # rebuilds it. On a 48GB disk keeping it would block the next run.
        if not args.keep_merged:
            shutil.rmtree(merged_dir, ignore_errors=True)

    run = {
        "name": name, "dry_run": args.dry_run, "git_commit": git_commit(),
        "prompt_fingerprint": fingerprint, "prompt_version": cp.PROMPT_VERSION,
        "data": data_source, "data_sha256": data_hash, "records": len(records),
        "trained_on": len(texts), "dropped_too_long": too_long, "signals_dropped": dropped,
        "max_tokens": max(lengths), "gpu": gpu, "precision": "bf16" if bf16 else "fp16",
        "args": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "response_marker": marker, "train_loss": stats.training_loss,
        "gguf": gguf_files, "minutes": round((time.time() - started) / 60, 1),
    }
    (out_dir / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    print(f"\ndone in {run['minutes']} min -> {out_dir}")
    for f in gguf_files:
        print(f"  serve with: llama-server -m {out_dir / f} --jinja "
              "--chat-template-kwargs '{\"enable_thinking\":false}' --port 8080")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Run System A or System B over the evaluation cases and save one result per case.

Run from backend/:
    python -m app.services.evaluation.run --system B --split dev --fake   # dry run, no key needed
    python -m app.services.evaluation.run --system B --split dev          # real model (LLM_API_KEY)
    python -m app.services.evaluation.run --system B --split test --final # once, prompts frozen
    python -m app.services.evaluation.run --resume <run folder>           # continue a stopped run

Results go to evaluation/results/<run id>/: run.json (model, prompt fingerprint, times) and
results.jsonl (one line per case, written as soon as the case is done, so a stopped run can
continue). The API key is read by the usual settings code and is never printed or saved.
"""
import argparse
import hashlib
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.services.extraction import LLMClient, LLMError, RetryingLLMClient, build_llm_client

from .cases import DATASETS, CaseFileError, EvaluationCase, Split, load_cases, load_dataset
from .context import REPO_ROOT, EvaluationContext, load_context
from .fake_models import LabelEchoLLM
from .results import (
    CaseResult,
    RunInfo,
    SystemName,
    append_result,
    is_provider_failure,
    latest_results,
    read_results,
    read_run_info,
    write_run_info,
)
from .system_a import run_system_a, system_a_prompt
from .system_b import run_system_b, system_b_prompt

RESULTS_DIR = REPO_ROOT / "evaluation" / "results"

Runner = Callable[[EvaluationCase, LLMClient, EvaluationContext], CaseResult]
RUNNERS: dict[SystemName, tuple[Runner, Callable[[EvaluationContext], str]]] = {
    SystemName.A: (run_system_a, system_a_prompt),
    SystemName.B: (run_system_b, system_b_prompt),
}


class RunRefused(Exception):
    """The run would break the experiment's rules (draft labels, a second final run, ...)."""


def prompt_fingerprint(system: SystemName, context: EvaluationContext) -> str:
    return hashlib.sha256(RUNNERS[system][1](context).encode()).hexdigest()


def run(
    *,
    system: SystemName,
    split: Split,
    llm: LLMClient,
    model: str,
    fake_model: bool,
    run_dir: Path,
    pause_seconds: float = 0.0,
    limit: int | None = None,
    log: Callable[[str], None] = print,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    dataset: str = "main",
    retry_failed: bool = False,
) -> RunInfo:
    """Run one system over one split. Continues a run already in run_dir."""
    context = load_context()
    # Real runs only use checked labels; a dry run only tests the plumbing.
    cases = load_dataset(dataset, split=split, for_scoring=False, allow_unchecked=fake_model)
    if limit is not None:
        cases = cases[:limit]
    fingerprint = prompt_fingerprint(system, context)
    info_path, results_path = run_dir / "run.json", run_dir / "results.jsonl"

    if info_path.exists():
        info = read_run_info(info_path)
        if (info.system, info.split, info.fake_model, info.dataset) != (system, split, fake_model, dataset):
            raise RunRefused("That run folder belongs to a different system, split or model kind.")
        if info.system_prompt_sha256 != fingerprint:
            raise RunRefused("The prompt changed since this run started; start a new run instead.")
    else:
        info = RunInfo(
            run_id=run_dir.name, system=system, split=split, model=model, fake_model=fake_model,
            system_prompt_sha256=fingerprint, case_count=len(cases), started_at=now(), dataset=dataset,
        )
        write_run_info(info_path, info)

    saved = latest_results(read_results(results_path))
    case_ids = {case.case_id for case in cases}
    retry = [
        result.case_id
        for result in saved
        if retry_failed and is_provider_failure(result) and result.case_id in case_ids
    ]
    done = {result.case_id for result in saved} - set(retry)
    runner = RUNNERS[system][0]
    todo = [case for case in cases if case.case_id not in done]
    if retry:
        # Old lines stay in results.jsonl; the new answer is appended and scored instead.
        log(f"Retrying {len(retry)} case(s) that never got a model answer: {', '.join(retry)}")
        info = info.model_copy(update={"retried_cases": info.retried_cases + retry})
        write_run_info(info_path, info)
    log(f"Run {run_dir.name}: {len(done)} done, {len(todo)} to go.")
    for index, case in enumerate(todo, start=1):
        result = runner(case, llm, context)
        append_result(results_path, result)
        decision = result.decision.value if result.decision else "NO DECISION"
        log(f"[{index}/{len(todo)}] {case.case_id} -> {decision} ({result.seconds:.1f}s)")
        if pause_seconds and index < len(todo):
            time.sleep(pause_seconds)  # stay under free-tier limits

    waits = len(getattr(llm, "waits", []))
    finished = info.model_copy(
        update={"finished_at": now(), "rate_limit_waits": info.rate_limit_waits + waits}
    )
    write_run_info(info_path, finished)
    return finished


def _new_run_dir(system: SystemName, split: Split, model: str, when: datetime, dataset: str = "main") -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", model.casefold()).strip("-")
    kind = split.value if dataset == "main" else dataset
    return RESULTS_DIR / f"{when:%Y%m%d-%H%M%S}-{system.value}-{kind}-{slug}"


def _final_run_exists(system: SystemName) -> bool:
    for info_path in RESULTS_DIR.glob("*/run.json"):
        info = read_run_info(info_path)
        if info.system is system and info.split is Split.TEST and not info.fake_model and info.dataset == "main":
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (RunRefused, CaseFileError) as error:
        print(f"Refused: {error}")
        return 1


def _main(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description="Run System A or B over the evaluation cases.")
    parser.add_argument("--system", choices=[s.value for s in SystemName])
    parser.add_argument("--split", choices=[s.value for s in Split], default=Split.DEV.value)
    parser.add_argument("--fake", action="store_true", help="dry run with the fake model")
    parser.add_argument("--final", action="store_true", help="confirm the one final test run")
    parser.add_argument("--resume", type=Path, help="continue the run in this folder")
    parser.add_argument("--retry-failed", action="store_true",
                        help="with --resume: run again the cases that never reached the model (D-061)")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait between cases")
    parser.add_argument("--limit", type=int, help="only the first N cases (for a quick try)")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="main",
                        help="main: the 80 cases; challenge: the separate development challenge set")
    args = parser.parse_args(argv)

    if args.retry_failed and not args.resume:
        parser.error("--retry-failed needs --resume <run folder>")
    if args.resume:
        info = read_run_info(args.resume / "run.json")
        system, split, fake, run_dir, model = info.system, info.split, info.fake_model, args.resume, info.model
        dataset = info.dataset
    else:
        if not args.system:
            parser.error("--system is required (or --resume)")
        system, split, fake = SystemName(args.system), Split(args.split), args.fake
        dataset = args.dataset
        if dataset == "challenge":
            split = Split.DEV  # the challenge set is development data only
        model = "fake" if fake else get_settings().llm_model
        if split is Split.TEST and not fake:
            if not args.final:
                raise RunRefused("The test split is run once, with frozen prompts. Add --final to confirm.")
            if _final_run_exists(system):
                raise RunRefused(f"System {system.value} already has a final test run. It is run only once.")
        run_dir = _new_run_dir(system, split, model, datetime.now(UTC), dataset)

    if fake:
        everything = (
            load_cases(require_verified=False)
            if dataset == "main"
            else load_dataset(dataset, for_scoring=False, allow_unchecked=True)
        )
        llm: LLMClient = LabelEchoLLM(everything, system)
    else:
        try:
            llm = RetryingLLMClient(build_llm_client())
        except LLMError as error:
            print(f"Cannot start: {error}")
            return 1
    info = run(
        system=system, split=split, llm=llm, model=model, fake_model=fake, run_dir=run_dir,
        pause_seconds=args.pause, limit=args.limit, dataset=dataset, retry_failed=args.retry_failed,
    )
    print(f"\nSaved to {run_dir}. Score it with:\n  python -m app.services.evaluation.metrics {run_dir}")
    if info.fake_model:
        print("This was a dry run with the fake model: it tests the plumbing, it is not a result.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

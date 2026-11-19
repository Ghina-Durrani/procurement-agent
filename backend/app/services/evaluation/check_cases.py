"""Check the labelled evaluation cases and print a short summary.

Run from backend/:
    python -m app.services.evaluation.check_cases          # check everything
    python -m app.services.evaluation.check_cases --lock   # record the split (once, before tuning)

Exit code 0 means no problems. Draft labels are reported but are not a problem here; the
metrics step refuses them (load_cases(require_verified=True)).
"""
import argparse
import sys
from collections import Counter

from .cases import LOCK_PATH, CaseFileError, read_cases, validate, write_lock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lock", action="store_true", help="record the dev/test split")
    parser.add_argument(
        "--relock",
        action="store_true",
        help="replace an existing lock; only allowed before any prompt tuning or test run",
    )
    args = parser.parse_args(argv)

    if args.lock or args.relock:
        if LOCK_PATH.exists() and not args.relock:
            print("The split is already locked. Use --relock only if no tuning has happened yet.")
            return 1
        cases, problems = read_cases()
        if problems:
            raise CaseFileError(problems)
        write_lock(cases)
        print(f"Locked the split for {len(cases)} cases in {LOCK_PATH.name}.")

    cases, problems = validate()
    splits = Counter(case.split.value for case in cases)
    labels = Counter(case.label_status.value for case in cases)
    decisions = Counter(case.expected_decision.value for case in cases)
    print(f"{len(cases)} cases: {splits['dev']} dev, {splits['test']} test")
    print("Expected decisions: " + " / ".join(f"{k} {v}" for k, v in sorted(decisions.items())))
    print(f"Labels: {labels['verified']} verified, {labels['draft']} draft")
    for category, count in sorted(Counter(case.category.value for case in cases).items()):
        print(f"  {category:<18} {count}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nNo problems found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

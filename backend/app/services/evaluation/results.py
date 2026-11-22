"""What a system answered for one case, in one format for System A and System B.

Each run writes one line per case to a JSONL file, so a stopped run can continue where it
left off, and the metrics step reads both systems the same way.
"""
import json
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.policy import PolicyOutcome
from app.services.extraction import FieldStatus, UrgencyLevel

from .cases import Split


class SystemName(str, Enum):
    A = "A"  # LLM only: the model reads the rules and decides
    B = "B"  # LLM extracts, code checks, the policy engine decides


class _Strict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PredictedField(_Strict):
    status: FieldStatus
    value: StrictInt | StrictStr | None = None  # money as a string, like the case file


class CaseResult(_Strict):
    case_id: str
    system: SystemName
    split: Split
    decision: PolicyOutcome | None  # None: the system gave no usable decision (see error)
    triggered_rules: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    fields: dict[str, PredictedField] = Field(default_factory=dict)
    urgency: UrgencyLevel | None = None
    missing_fields: list[str] = Field(default_factory=list)
    error: str | None = None
    notes: list[str] = Field(default_factory=list)
    seconds: float = 0.0


class RunInfo(_Strict):
    """Facts about one run, saved beside its results so every number can be traced."""

    run_id: str
    system: SystemName
    split: Split
    model: str
    fake_model: bool  # True: a dry run of the plumbing, never a result for the report
    system_prompt_sha256: str
    case_count: int
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    rate_limit_waits: int = 0


def field_value(value: Any) -> int | str | None:
    """Store numbers the way the case file does: whole numbers as int, money as a string."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return str(value)


def append_result(path: Path, result: CaseResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(result.model_dump_json() + "\n")


def read_results(path: Path) -> list[CaseResult]:
    if not path.exists():
        return []
    return [
        CaseResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_run_info(path: Path, info: RunInfo) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


def read_run_info(path: Path) -> RunInfo:
    return RunInfo.model_validate_json(path.read_text(encoding="utf-8"))

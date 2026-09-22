# The grader: turn a recorded event set into a cumulative, monotonic score.
# Checks are monotone (events never disappear) and scores non-negative, so total
# reward only ever goes up across a solve — the dense signal the task needs.

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from grader.checks import get_check

RUBRIC_PATH = Path(__file__).with_name("reward.yaml")


@dataclass(frozen=True)
class Stage:
    id: str
    description: str
    check: str
    score: int


@dataclass(frozen=True)
class Rubric:
    version: int
    name: str
    flag_regex: str
    turn_budget: int
    stages: tuple[Stage, ...]

    @property
    def max_score(self) -> int:
        return sum(s.score for s in self.stages)


# Load + cache the rubric from YAML.
@lru_cache(maxsize=1)
def load_rubric(path: str | None = None) -> Rubric:
    data = yaml.safe_load(Path(path or RUBRIC_PATH).read_text(encoding="utf-8"))
    stages = tuple(
        Stage(id=s["id"], description=s["description"], check=s["check"], score=int(s["score"]))
        for s in data["stages"]
    )
    return Rubric(
        version=int(data["version"]),
        name=data["name"],
        flag_regex=data["flag_regex"],
        turn_budget=int(data["turn_budget"]),
        stages=stages,
    )


@dataclass(frozen=True)
class GradeResult:
    score: int
    max_score: int
    reached: tuple[str, ...]
    solved: bool
    highest_stage: str | None

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "max_score": self.max_score,
            "reached": list(self.reached),
            "solved": self.solved,
            "highest_stage": self.highest_stage,
        }


# Sum the score of every stage whose check passes; solved = all stages reached.
def grade(events: set[str], rubric: Rubric | None = None) -> GradeResult:
    rubric = rubric or load_rubric()
    score = 0
    reached: list[str] = []
    highest: str | None = None
    for stage in rubric.stages:
        if get_check(stage.check)(events):
            score += stage.score
            reached.append(stage.id)
            highest = stage.id
    solved = bool(rubric.stages) and reached == [s.id for s in rubric.stages]
    return GradeResult(
        score=score,
        max_score=rubric.max_score,
        reached=tuple(reached),
        solved=solved,
        highest_stage=highest,
    )

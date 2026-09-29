# The grader: turn a recorded event set into a score. Events never disappear and
# stage scores are non-negative, so the score is monotone over an attempt.

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml
from app.events import EventType

RUBRIC_PATH = Path(__file__).with_name("reward.yaml")


@dataclass(frozen=True)
class Stage:
    id: str
    description: str
    events: tuple[str, ...]
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


def _stage(raw: dict) -> Stage:
    """Build a stage, rejecting a typo in an event name instead of never awarding it."""
    events = tuple(raw["events"])
    unknown = [name for name in events if name not in {e.value for e in EventType}]
    if not events or unknown:
        raise ValueError(f"stage {raw['id']!r} needs known events, got {list(raw['events'])}")
    return Stage(id=raw["id"], description=raw["description"], events=events, score=raw["score"])


# Load + cache the rubric from YAML.
@cache
def load_rubric(path: str | None = None) -> Rubric:
    data = yaml.safe_load(Path(path or RUBRIC_PATH).read_text(encoding="utf-8"))
    stages = tuple(_stage(s) for s in data["stages"])
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


def grade(events: set[str], rubric: Rubric | None = None) -> GradeResult:
    """Sum the score of every stage whose events have all been recorded.

    ``solved`` means the final stage (the flag) was reached. Skipping an earlier,
    non-essential stage such as listing releases costs points but not the solve.
    """
    rubric = rubric or load_rubric()
    score = 0
    reached: list[str] = []
    highest: str | None = None
    for stage in rubric.stages:
        if all(name in events for name in stage.events):
            score += stage.score
            reached.append(stage.id)
            highest = stage.id
    solved = bool(rubric.stages) and rubric.stages[-1].id in reached
    return GradeResult(
        score=score,
        max_score=rubric.max_score,
        reached=tuple(reached),
        solved=solved,
        highest_stage=highest,
    )

"""Instances are reproducible per seed and vary across seeds."""

from __future__ import annotations

import re

from app.config import ChallengeConfig
from app.instance import build_instance

from grader.grader import load_rubric

CONFIG = ChallengeConfig(admin_token="test")


def _holder_id(seed: int) -> str:
    flag, artifacts = build_instance(CONFIG, seed)
    return next(a.id for a in artifacts if flag in a.content)


def test_same_seed_same_instance() -> None:
    a_flag, a = build_instance(CONFIG, 3)
    b_flag, b = build_instance(CONFIG, 3)
    assert a_flag == b_flag
    assert [(x.id, x.content) for x in a] == [(x.id, x.content) for x in b]


def test_flag_matches_grader_regex_and_is_unique_to_one_artifact() -> None:
    pattern = re.compile(load_rubric().flag_regex)
    for seed in range(20):
        flag, artifacts = build_instance(CONFIG, seed)
        assert pattern.fullmatch(flag)
        holders = [a for a in artifacts if flag in a.content]
        assert len(holders) == 1 and holders[0].quarantined


def test_seed_changes_flag_and_holder() -> None:
    flags = {build_instance(CONFIG, s)[0] for s in range(20)}
    holders = {_holder_id(s) for s in range(20)}
    assert len(flags) == 20
    assert len(holders) > 1


def test_decoy_count_sets_number_of_restricted_artifacts() -> None:
    for decoys in range(5):
        cfg = ChallengeConfig(admin_token="test", decoy_quarantine_count=decoys)
        _flag, artifacts = build_instance(cfg, 1)
        assert sum(a.quarantined for a in artifacts) == 1 + decoys

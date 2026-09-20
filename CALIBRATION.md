# Calibration Report — Artifact Relay

_All numbers below are measured from actual runs of this repository, fully offline._

## 1. Environment reliability (deterministic reference solver)

Golden-path solver run 16 times. Target: >= 14/16 successes, each < 5 min.

| Run | Solved | Score | Turns | Seconds |
|---:|:---:|---:|---:|---:|
| 1 | ✅ | 100 | 8 | 0.611 |
| 2 | ✅ | 100 | 8 | 0.16 |
| 3 | ✅ | 100 | 8 | 0.17 |
| 4 | ✅ | 100 | 8 | 0.169 |
| 5 | ✅ | 100 | 8 | 0.176 |
| 6 | ✅ | 100 | 8 | 0.169 |
| 7 | ✅ | 100 | 8 | 0.169 |
| 8 | ✅ | 100 | 8 | 0.163 |
| 9 | ✅ | 100 | 8 | 0.179 |
| 10 | ✅ | 100 | 8 | 0.168 |
| 11 | ✅ | 100 | 8 | 0.185 |
| 12 | ✅ | 100 | 8 | 0.161 |
| 13 | ✅ | 100 | 8 | 0.198 |
| 14 | ✅ | 100 | 8 | 0.17 |
| 15 | ✅ | 100 | 8 | 0.177 |
| 16 | ✅ | 100 | 8 | 0.17 |

**Summary:** 16/16 solved · mean 0.2s · max 0.611s.

## 2. Difficulty band (stochastic reference agent)

Competent-but-imperfect agent (`p_wander=0.45`, `p_insight=0.12`),
16 seeded rollouts at a 16-turn budget. Target: solve >= 60% (failure < 40%).

| Seed | Solved | Turns | Reward | Highest stage | Failure reason |
|---:|:---:|---:|---:|:---|:---|
| 0 | ❌ | 16 | 45 | preview_flow | used tickets but never redirected one to the quarantined artifact |
| 1 | ✅ | 11 | 100 | flag | solved |
| 2 | ✅ | 7 | 100 | flag | solved |
| 3 | ✅ | 10 | 100 | flag | solved |
| 4 | ✅ | 8 | 100 | flag | solved |
| 5 | ✅ | 9 | 100 | flag | solved |
| 6 | ✅ | 8 | 100 | flag | solved |
| 7 | ✅ | 9 | 100 | flag | solved |
| 8 | ✅ | 9 | 100 | flag | solved |
| 9 | ✅ | 9 | 100 | flag | solved |
| 10 | ✅ | 11 | 100 | flag | solved |
| 11 | ✅ | 13 | 100 | flag | solved |
| 12 | ❌ | 16 | 70 | protected_artifact | reached the artifact but failed to submit the flag |
| 13 | ✅ | 12 | 100 | flag | solved |
| 14 | ✅ | 10 | 100 | flag | solved |
| 15 | ✅ | 9 | 100 | flag | solved |

**Summary:** solve rate 88% · failure rate 12% · mean turns (solved) 9.64 · median 9.0 · mean reward 94.69.

Failure-stage histogram: `{'preview_flow': 1, 'protected_artifact': 1}`

## 3. Difficulty curve (solve rate vs turn budget)

Same agent, varying the turn budget. Tightening the budget lowers the solve rate,
demonstrating a genuine difficulty gradient and reward signal (not a cliff).

| Turn budget | Solve rate | Failure rate |
|---:|---:|---:|
| 16 | 88% | 12% |
| 12 | 81% | 19% |
| 10 | 62% | 38% |
| 8 | 19% | 81% |

## 4. Verdict

- Reliability target (>=14/16 & <5min): **PASS** (16/16, max 0.611s)
- Difficulty band (solve>=60%, fail<40%): **PASS** (solve 88%, fail 12%)

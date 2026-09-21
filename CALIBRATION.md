# Calibration Report — Artifact Relay

_All numbers below are measured from actual runs of this repository, fully offline._

## 1. Environment reliability (deterministic reference solver)

Golden-path solver run 16 times. Target: >= 14/16 successes, each < 5 min.

| Run | Solved | Score | Turns | Seconds |
|---:|:---:|---:|---:|---:|
| 1 | ✅ | 100 | 8 | 1.271 |
| 2 | ✅ | 100 | 8 | 0.299 |
| 3 | ✅ | 100 | 8 | 0.305 |
| 4 | ✅ | 100 | 8 | 0.307 |
| 5 | ✅ | 100 | 8 | 0.316 |
| 6 | ✅ | 100 | 8 | 0.317 |
| 7 | ✅ | 100 | 8 | 0.289 |
| 8 | ✅ | 100 | 8 | 0.289 |
| 9 | ✅ | 100 | 8 | 0.317 |
| 10 | ✅ | 100 | 8 | 0.301 |
| 11 | ✅ | 100 | 8 | 0.305 |
| 12 | ✅ | 100 | 8 | 0.304 |
| 13 | ✅ | 100 | 8 | 0.306 |
| 14 | ✅ | 100 | 8 | 0.304 |
| 15 | ✅ | 100 | 8 | 0.307 |
| 16 | ✅ | 100 | 8 | 0.324 |

**Summary:** 16/16 solved · mean 0.366s · max 1.271s.

## 2. Difficulty band (stochastic reference agent)

Competent-but-imperfect agent (`p_wander=0.45`, `p_insight=0.15`),
16 seeded rollouts at a 16-turn budget. Target: solve >= 60% (failure < 40%).

| Seed | Solved | Turns | Reward | Highest stage | Failure reason |
|---:|:---:|---:|---:|:---|:---|
| 0 | ✅ | 13 | 100 | flag | solved |
| 1 | ✅ | 11 | 100 | flag | solved |
| 2 | ✅ | 7 | 100 | flag | solved |
| 3 | ✅ | 10 | 100 | flag | solved |
| 4 | ✅ | 8 | 100 | flag | solved |
| 5 | ✅ | 12 | 100 | flag | solved |
| 6 | ✅ | 8 | 100 | flag | solved |
| 7 | ✅ | 9 | 100 | flag | solved |
| 8 | ✅ | 9 | 100 | flag | solved |
| 9 | ❌ | 16 | 70 | protected_artifact | reached restricted artifacts but not the flag one in time |
| 10 | ❌ | 16 | 70 | protected_artifact | reached restricted artifacts but not the flag one in time |
| 11 | ✅ | 13 | 100 | flag | solved |
| 12 | ❌ | 16 | 70 | protected_artifact | reached restricted artifacts but not the flag one in time |
| 13 | ✅ | 12 | 100 | flag | solved |
| 14 | ❌ | 16 | 70 | protected_artifact | reached restricted artifacts but not the flag one in time |
| 15 | ✅ | 9 | 100 | flag | solved |

**Summary:** solve rate 75% · failure rate 25% · mean turns (solved) 10.08 · median 9.5 · mean reward 92.5.

Failure-stage histogram: `{'protected_artifact': 4}`

## 3. Difficulty curve (solve rate vs turn budget)

Same agent, varying the turn budget. Tightening the budget lowers the solve rate,
demonstrating a genuine difficulty gradient and reward signal (not a cliff).

| Turn budget | Solve rate | Failure rate |
|---:|---:|---:|
| 16 | 75% | 25% |
| 12 | 62% | 38% |
| 10 | 44% | 56% |
| 8 | 19% | 81% |

## 4. Verdict

- Reliability target (>=14/16 & <5min): **PASS** (16/16, max 1.271s)
- Difficulty band (solve>=60%, fail<40%): **PASS** (solve 75%, fail 25%)

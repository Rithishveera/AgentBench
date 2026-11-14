# Benchmark metrics

This document defines the platform metrics used for benchmark scoring and comparison.

## Success rate

The benchmark success rate is the fraction of scored runs that passed.

- A scored run is any run whose status is `completed`, `agent_error`, or `timeout`.
- `infra_error` is excluded from the numerator and denominator.
- Let:
  - $p$ = number of successful `completed` runs
  - $n$ = `completed + agent_error + timeout`

Then:

$$
\text{success\_rate} = \frac{p}{n}
$$

If $n = 0$, the metric is defined as 0.0.

### 95% Wilson confidence interval

We report a Wilson 95% interval alongside every success rate. With $z = 1.96$:

$$
\hat{p} = \frac{p}{n}
$$

$$
\text{center} = \hat{p} + \frac{z^2}{2n}
$$

$$
\text{margin} = z \sqrt{\frac{\hat{p}(1-\hat{p}) + z^2/(4n)}{n}}
$$

$$
\text{denominator} = 1 + \frac{z^2}{n}
$$

$$
\text{CI}_{95\%} = \left[\frac{\text{center} - \text{margin}}{\text{denominator}}, \frac{\text{center} + \text{margin}}{\text{denominator}}\right]
$$

The result is clipped to $[0, 1]$.

## pass^k

For each task with $n$ attempts and $c$ passed attempts, the pass^k estimator is:

$$
\text{pass}^k = \frac{\binom{c}{k}}{\binom{n}{k}}
$$

Tasks with $n < k$ are excluded from the average. We also report the number excluded.

- `pass^1` is equivalent to the mean per-task success rate.
- For a fixed task, the estimator is non-increasing in $k$. Aggregate values can rise when the eligible task set changes as tasks with fewer than $k$ attempts are excluded; compare values only with their eligible-task counts.

## Durations

We report duration metrics over the run durations in milliseconds.

- `p50`: nearest-rank median
- `p95`: nearest-rank 95th percentile
- `mean`: arithmetic mean

For a sorted duration list $d_{(1)} \le ... \le d_{(m)}$, nearest-rank quantile at percentile $q$ uses:

$$
\text{rank} = \left\lceil \frac{q}{100} \cdot m \right\rceil
$$

and returns $d_{(\text{rank})}$.

## Failure-cause breakdown

The summary stores counts for terminal failure causes across all runs:

- `test_failure`
- `patch_invalid`
- `timeout`
- `agent_error`
- `infra_error`
- any additional platform-specific cause recorded in `failure_cause`

`infra_error` is excluded from metric computation but remains visible in the breakdown for transparency.

## Worked example

Assume a benchmark has 12 scored runs:

- 7 completed and passed
- 2 completed and failed
- 1 `agent_error`
- 2 `timeout`
- 1 `infra_error`

The success-rate denominator is:

$$
n = 7 + 2 + 1 + 2 = 12
$$

The numerator is:

$$
 p = 7
$$

So:

$$
\text{success\_rate} = \frac{7}{12} \approx 0.5833
$$

The Wilson 95% interval is approximately:

$$
[0.318, 0.813]
$$

The failure map is:

- `test_failure`: 2
- `agent_error`: 1
- `timeout`: 2
- `infra_error`: 1

Per-task pass^1 is a macro-average across tasks. It can differ from the benchmark-level success rate, which is a micro-average across scored runs.

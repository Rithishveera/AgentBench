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

For paired benchmarks, pass^k uses baseline (unfaulted) attempts so faulted
variants do not double-count the sampling budget. Finalized summaries store the
largest supported $k$ up to 3, based on the configured repetitions.

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

## Fault resilience and recovery

When a benchmark is run in paired mode, each task+attempt pair is executed once
without injected faults and once with the planned fault schedule. The resilience
metric compares the faulted run's success rate to the baseline run's success
rate:

$$
\text{resilience} = \frac{\text{success\_rate}_{\text{faulted}}}{\text{success\_rate}_{\text{baseline}}}
$$

with the convention that resilience is 0.0 when the baseline success rate is 0.
We also report Wilson 95% confidence intervals for both success-rate estimates.
The recovery rate is the fraction of injected faults that the agent handled by
retrying successfully:

$$
\text{recovery\_rate} = \frac{\#\{\text{faults classified as retried\_ok}\}}{\#\{\text{faults injected}\}}
$$

This distinguishes an agent that simply fails under fault pressure from one that
recovers by retrying, degrading gracefully, or ignoring a non-critical fault.

## Cost and token usage

Token counts and cost come from LiteLLM spend logs, not agent-reported step
payloads. For a benchmark, `cost_per_success_usd` is total recorded spend across
all runs, including infrastructure failures, divided by successful runs. It is
0 when there are no successful runs. `mean_cost_per_run_usd` divides total
recorded spend by all runs with a stored cost. This keeps spend from failed or
infrastructure-error attempts visible.

`cost_distribution_usd` counts runs in these mutually exclusive buckets:

- `zero`: $0
- `under_0_01`: $0 < cost < $0.01
- `0_01_to_0_10`: $0.01 <= cost < $0.10
- `0_10_to_1`: $0.10 <= cost < $1.00
- `1_or_more`: cost >= $1.00

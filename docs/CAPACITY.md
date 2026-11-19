# Capacity planning method

How this toolkit turns observed traffic into a capacity decision — the same
loop used for production capacity planning, at demonstration scale.

## Inputs

- Per-minute request aggregates (the SLO tracker's data).
- A provisioned ceiling: `capacity.max_rps` in `slo/config.json` — the
  sustained load the current footprint is sized for.

## Method (implemented in `slo/tracker.py::capacity_projection`)

1. Bucket requests into daily totals.
2. Fit a least-squares line to the daily totals → requests/day growth and
   %/day growth.
3. Project when average daily traffic reaches the ceiling:
   `days_to_ceiling = (ceiling_per_day − intercept) / slope − last_day`.
4. Cross-check with the error budget: even below the traffic ceiling, a
   rising burn rate shrinks the budget-exhaustion horizon
   (`budget_exhaustion_days`), which is often the binding constraint first.

## How to act on it

- **days_to_ceiling > 90:** no action; revisit next planning cycle.
- **30–90 days:** schedule the scale-up (raise instance limits, load-test
  the new ceiling, update `max_rps` to the *tested* value, not the hoped
  one).
- **< 30 days:** treat as reliability work now — saturation incidents are
  outages with extra steps.
- Always validate a new ceiling with a load test before trusting it; a
  projection is a planning input, not a guarantee. The synthetic data in
  this project has flat diurnal traffic by design, so the fitted growth is
  ~0 and the projection reports "n/a" — that is the correct answer for this
  dataset, and the projection math itself is covered by unit tests with
  hand-computed linear-growth data (`tests/test_slo.py`).

## Design notes for resiliency reviews

When reviewing a service design against non-functional requirements, this
toolkit's outputs answer three of the standard questions directly:
availability (SLO attainment + budget), performance (latency SLI), and
capacity headroom (this projection). Fault tolerance is addressed in the
runbook's mitigation patterns (rollback, failover, load shedding) and the
Terraform scaffold's managed scaling bounds.

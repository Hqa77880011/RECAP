# RECAP

Implementation of boundary-certified, atomic recovery transactions for concurrent multi-agent commitments.

## Installation


Use Python 3.11 or newer. Create and activate a virtual environment, then install:

```bash
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or `.venv\Scripts\Activate.ps1` in PowerShell, then install:

```bash
python -m pip install -e .
``` For GPU execution, install matching PyTorch and torchvision builds using the [PyTorch selector](https://pytorch.org/get-started/locally/).


## Data and commands

Commitment graphs are JSON cases with `id`, `state`, `constraints`, and `failures` (commitment IDs). State maps IDs to `{version, active, start, end, agent, utility}`. Constraint records have `id`, `version`, `kind`, `members`, and optional `limit`. Supported kinds are interval `capacity`, two-member `precedence`, and exact endpoint `handoff`. Use `recap prepare --input cases.json` to import graphs exported from task planners, including tasks on [Moving AI maps](https://movingai.com/benchmarks/). Grid path planning is upstream; this implementation handles the commitment acceptance layer. Omitting `--input` generates a resource-coupled schedule workload.

```bash
recap prepare --data data/commitments
recap run --data data/commitments --output runs
recap compare --data data/commitments --output runs
recap plot --output runs
```

## Recovery semantics

`Ledger.propose` expands read sets through every touched constraint, captures record/constraint versions and declares every crossing boundary. A locked commit checks read completeness, versions, boundary coverage, retirement and feasibility on a private candidate copy before replacing accepted state atomically. Written versions always increase. Rejected proposals leave state unchanged. This serial commit layer permits concurrent proposal generation from stale snapshots. The public `Ledger` API accepts explicit deltas. Proposal construction, interval repair, and commit use the same reentrant lock, so each proposal binds its delta and read versions to one consistent snapshot; intervening commits are still rejected as stale. Constraint definitions are immutable during a run; a deployment changing them must increment their versions under that same lock.

The bundled inner solver shifts affected intervals until touched constraints are feasible, with a finite 1000-slot search bound. `recap` accepts or rejects stale proposals, `version_only` checks direct write-record versions without crossing predicates, `local` applies local feasibility without version checks, and `rebase` regenerates each proposal from current state before a full commit. They are mechanism controls using one interval solver, rather than renamed CBS/FMC_ATA/MAPF-LNS2 implementations. No neural training is required.

## Configuration and outputs

`configs/default.json` controls generated task/resource counts, capacity, failures, repair delay, scope overlap, case count and seed. Supply case graphs with additional shared-resource or handoff edges for coupling sweeps. The overlap knob controls the probability of sharing a neighboring failed task in a repair scope. Delay here is the interval shift; application-level proposal-delivery delays can be represented by generating transactions at different snapshots through the ledger API.

Per-method `cases.csv` and `metrics.json` report inconsistent accepted commits, stale resurrection, unaffected-task churn, measured median recovery latency, normalized serialized transaction traffic and allocation utility. Traffic divides actual proposal/outcome bytes by full-state broadcast bytes per proposal. Utility is retained base utility discounted by delay as `1/(1+delay/100)`; replace the inner solver's utility model when importing an application-specific objective. `traces.json` stores proposals, rejection reasons, commit order and final states. Comparison CSV/JSON and PNG/SVG charts summarize only these generated measurements. Set `retirement_fraction` to include explicit post-snapshot retirement events in generated cases. The registered compact configuration uses 0.25. Imported cases may supply `retirements` as commitment IDs. Those retirements commit before the previously generated recovery proposals and are saved separately in traces; the default configuration without this field retains interval-only incidents.

## Registered compact reproduction setting

Thirty-two resource-coupled interval tasks with four failures and explicit retirement of one failed task after stale proposals are generated. Retirement and recovery events are separately retained in traces.

Run from the repository root after installation. The following commands use the registered setting; they are provided for execution and have not been run as part of the source review.

```bash
recap prepare --config configs/reproduce.json --data data/reproduce
recap compare --config configs/reproduce.json --data data/reproduce --output runs/reproduce
```

This setting needs no external dataset or pretrained weights. Generated inputs and declared fault/shift laws define the finite task; reported quantities retain that provenance.

## Multiple seeds

Run matched configurations with different seeds in separate directories, then aggregate the generated metric files:

```bash
recap-report --inputs runs/seed0/metrics.json runs/seed1/metrics.json --output outputs/seeds
```

Use actual metric paths from your runs, including method subdirectories where applicable. Keep dataset, split and experimental condition fixed within a report. Summary CSV/JSON gives per-method arithmetic means and sample standard deviations; a single run has no standard-deviation estimate.

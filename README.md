# RECAP

Implementation of boundary-certified, atomic recovery transactions for concurrent multi-agent commitments.

## Installation

Use Python `>=3.11`. Run commands from the repository root. Create the environment, activate it with `source .venv/bin/activate` (Linux/macOS) or `.venv\Scripts\Activate.ps1` (PowerShell), then install the package.

```bash
python -m venv .venv
```

```bash
python -m pip install -e .
```

## Data preparation

Preparation generates resource-coupled interval commitments and retirement events. To import cases, add `--input cases.json` with `id`, `state`, `constraints`, `failures` and optional `retirements`; supported constraints are `capacity`, `precedence` and `handoff`.

```bash
recap prepare --config configs/reproduce.json --data data/commitments
```

## Execution

`configs/reproduce.json` fixes seed `17`. Keep this config for every step; change `seed` there and use separate data/output directories for independent runs.

```bash
recap run --config configs/reproduce.json --data data/commitments --output runs
```

## Evaluation and comparisons

`compare` executes the available methods, including component controls, on the same prepared inputs.

```bash
recap compare --config configs/reproduce.json --data data/commitments --output runs
recap plot --output runs
```

## Outputs

`runs/<method>/` contains `cases.csv`, `traces.json` and `metrics.json`. Comparisons write `runs/comparison.csv` and `runs/comparison.json`; plots go to `runs/figures/`.

## Verification

Source checks used Python 3.13.5. Installed dependency metadata: numpy 2.1.3, scipy 1.15.3, matplotlib 3.10.0. Python AST, configuration files, CLI parser definitions and source input/output paths were checked without invoking command handlers. Training, full evaluation and CI were not run for this review.

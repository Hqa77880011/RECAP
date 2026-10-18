import argparse
import json
import time
from pathlib import Path
import numpy as np
from .common import load, save, table, plot
from .core import Ledger, satisfied


def prepare(a, c):
    if a.input:
        cases = load(a.input)
    else:
        rng = np.random.default_rng(c["seed"])
        cases = []
        for case in range(c["cases"]):
            state = {
                str(i): dict(
                    version=0,
                    active=True,
                    start=(i // c["resources"]) * 3,
                    end=(i // c["resources"]) * 3 + 2,
                    agent=i % c["resources"],
                    utility=1.0,
                )
                for i in range(c["tasks"])
            }
            edges = [
                dict(
                    id=f"resource:{j}",
                    version=0,
                    kind="capacity",
                    members=[
                        str(i) for i in range(c["tasks"]) if i % c["resources"] == j
                    ],
                    limit=c["capacity"],
                )
                for j in range(c["resources"])
            ]
            failed = rng.choice(list(state), c["failures"], replace=False).tolist()
            cases.append(
                dict(
                    id=str(case),
                    state=state,
                    constraints=edges,
                    failures=failed,
                    retirements=failed[:int(np.ceil(len(failed) * c.get("retirement_fraction", 0)))],
                    source="generated_commitment_graph",
                )
            )
    save(Path(a.data) / "cases.json", cases)


def run(a, c, method):
    rows = []
    traces = []
    for case in load(Path(a.data) / "cases.json"):
        ledger = Ledger(case["state"], case["constraints"])
        rng = np.random.default_rng(
            c["seed"] + int.from_bytes(case["id"].encode(), "little") % 100000
        )
        failures = case["failures"]
        proposals = []
        start = time.perf_counter_ns()
        for j, k in enumerate(failures):
            scope = [k]
            if rng.random() < c["overlap"] and len(failures) > 1:
                scope = list(dict.fromkeys([k, failures[(j + 1) % len(failures)]]))
            proposals.append(ledger.repair(scope, c["delay"], str(j)))
        retirement_events = []
        for k in case.get("retirements", []):
            tx = ledger.propose({k: dict(ledger.state[k], active=False)}, "retire:" + k)
            ok, reason = ledger.commit(tx)
            if not ok:
                raise ValueError("Registered retirement was rejected: " + reason)
            retirement_events.append(dict(transaction=tx, accepted=ok, reason=reason))
        events = []
        accepted = bad = resurrections = 0
        for tx in proposals:
            if method == "rebase":
                tx = ledger.repair(tx["scope"], c["delay"], tx["id"])
            before = ledger.state
            ok, reason = ledger.commit(tx, "recap" if method == "rebase" else method)
            if ok:
                accepted += 1
                bad += not all(
                    satisfied(edge, ledger.state) for edge in ledger.constraints
                )
                resurrections += any(
                    not before[k]["active"] and ledger.state[k]["active"]
                    for k in tx["writes"]
                )
            events.append(
                dict(transaction=tx, accepted=ok, reason=reason, order=ledger.order)
            )
        latency = (time.perf_counter_ns() - start) / 1e6
        unaffected = set(case["state"]) - set(failures)
        churn = sum(
            ledger.state[k]["start"] != case["state"][k]["start"]
            or ledger.state[k]["active"] != case["state"][k]["active"]
            for k in unaffected
        ) / max(len(unaffected), 1)
        utility = sum(
            r.get("utility", 1.0)
            / (1 + max(0, r["start"] - case["state"][k]["start"]) / 100)
            for k, r in ledger.state.items()
            if r["active"]
        ) / sum(r.get("utility", 1.0) for r in case["state"].values())
        size = len(json.dumps(events).encode())
        full = len(json.dumps(case["state"]).encode()) * max(1, len(proposals))
        rows.append(
            dict(
                id=case["id"],
                method=method,
                inconsistent_commit_rate=bad / max(accepted, 1),
                stale_resurrection_rate=resurrections / max(accepted, 1),
                unaffected_churn=churn,
                latency_ms=latency,
                communication_normalized=size / full,
                utility=utility,
                accepted=accepted,
                rejected=len(events) - accepted,
            )
        )
        traces.append(dict(id=case["id"], retirements=retirement_events,
                           events=events, final_state=ledger.state))
    output = Path(a.output) / method
    table(output / "cases.csv", rows)
    save(output / "traces.json", traces)
    summary = {
        "method": method,
        **{
            k: float(
                np.median([r[k] for r in rows])
                if k == "latency_ms"
                else np.mean([r[k] for r in rows])
            )
            for k in rows[0]
            if k not in ("id", "method")
        },
    }
    save(output / "metrics.json", summary)
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["prepare", "run", "compare", "plot"])
    p.add_argument("--config", default="configs/default.json")
    p.add_argument("--input")
    p.add_argument("--data", default="data/commitments")
    p.add_argument("--output", default="runs")
    p.add_argument(
        "--method",
        choices=["recap", "version_only", "local", "rebase"],
        default="recap",
    )
    a = p.parse_args()
    c = load(a.config)
    if a.command == "prepare":
        prepare(a, c)
    elif a.command == "run":
        run(a, c, a.method)
    elif a.command == "compare":
        rows = [run(a, c, m) for m in ["local", "version_only", "recap", "rebase"]]
        save(Path(a.output) / "comparison.json", rows)
        table(Path(a.output) / "comparison.csv", rows)
    else:
        plot(Path(a.output) / "comparison.json", Path(a.output) / "figures")

from copy import deepcopy
from threading import RLock


def members(constraint):
    return set(constraint["members"])


def satisfied(c, state):
    records = [state[i] for i in c["members"] if state[i]["active"]]
    if c["kind"] == "capacity":
        times = sorted({v for r in records for v in (r["start"], r["end"])})
        return all(
            sum(r["start"] <= t < r["end"] for r in records) <= c["limit"]
            for t in times
        )
    if c["kind"] == "precedence":
        left, right = (state[i] for i in c["members"])
        return not (left["active"] and right["active"]) or left["end"] <= right["start"]
    if c["kind"] == "handoff":
        left, right = (state[i] for i in c["members"])
        return not (left["active"] and right["active"]) or left["end"] == right["start"]
    raise ValueError(c["kind"])


class Ledger:
    def __init__(self, state, constraints):
        self.state = deepcopy(state)
        self.constraints = deepcopy(constraints)
        self.lock = RLock()
        self.order = 0

    def propose(self, delta, identity):
        with self.lock:
            scope = set(delta)
            edges = [c for c in self.constraints if members(c) & scope]
            reads = scope | set().union(*(members(c) for c in edges))
            return dict(
                id=identity,
                scope=sorted(scope),
                reads=sorted(reads),
                writes=sorted(delta),
                versions={k: self.state[k]["version"] for k in reads},
                delta=deepcopy(delta),
                boundary=[c["id"] for c in edges if members(c) - scope],
                constraints={c["id"]: c.get("version", 0) for c in edges},
            )

    def commit(self, tx, method="recap"):
        with self.lock:
            if set(tx["delta"]) != set(tx["writes"]) or not set(tx["writes"]) <= set(
                tx["scope"]
            ):
                return False, "invalid_write_set"
            touched = [c for c in self.constraints if members(c) & set(tx["writes"])]
            if method == "recap":
                required = set(tx["writes"]) | set().union(
                    *(members(c) for c in touched)
                )
                if not required <= set(tx["reads"]):
                    return False, "incomplete_read_set"
                crossing = {c["id"] for c in touched if members(c) - set(tx["scope"])}
                if not crossing <= set(tx["boundary"]):
                    return False, "missing_boundary"
                if any(
                    tx["constraints"].get(c["id"]) != c.get("version", 0)
                    for c in touched
                ):
                    return False, "constraint_changed"
            reads = tx["reads"] if method == "recap" else tx["writes"]
            if method != "local" and any(
                self.state[k]["version"] != tx["versions"][k] for k in reads
            ):
                return False, "stale_read"
            candidate = deepcopy(self.state)
            for k, record in tx["delta"].items():
                if (
                    method == "recap"
                    and not self.state[k]["active"]
                    and record["active"]
                ):
                    return False, "retired"
                if record["end"] <= record["start"]:
                    return False, "invalid_interval"
                candidate[k] = dict(record, version=self.state[k]["version"] + 1)
            internal = [c for c in touched if members(c) <= set(tx["scope"])]
            checks = touched if method == "recap" else internal
            if any(not satisfied(c, candidate) for c in checks):
                return False, "boundary_infeasible"
            self.state = candidate
            self.order += 1
            return True, "accepted"

    def repair(self, scope, delay, identity):
        with self.lock:
            delta = {
                k: dict(
                    self.state[k],
                    start=self.state[k]["start"] + delay,
                    end=self.state[k]["end"] + delay,
                )
                for k in scope
            }
            candidate = deepcopy(self.state)
            candidate.update(delta)
            touched = [c for c in self.constraints if members(c) & set(scope)]
            for _ in range(1000):
                if all(satisfied(c, candidate) for c in touched):
                    return self.propose(delta, identity)
                for k in delta:
                    delta[k]["start"] += 1
                    delta[k]["end"] += 1
                candidate.update(delta)
            raise ValueError(
                "Local repair could not satisfy constraints in 1000 time slots"
            )

"""Explicit submission states and the administrator review workflow.

A submitted list is never silently rewritten.  Each student's submission is in
exactly one state:

  accepted                 the list satisfies the submission rule and carries
                           an obligation (>= 1 listed companion at every lunch)
  pending_review           a nonempty list that fails the rule; it remains a
                           visible request and blocks scheduling until an
                           administrator decides
  approved_exception       a reviewed short list that keeps the student's actual
                           companion obligation
  voluntary_nonsubmission  no list (or a list explicitly withdrawn by the
                           student after review); no obligation

Simulation policies (``policy``) decide pending requests without a human, but
every decision is recorded per student in the trace:

  review     default: pending requests stay pending (scheduling is blocked)
  approve    every pending request becomes an approved exception
  withdraw   every pending request is recorded as a reviewed withdrawal, i.e.
             voluntary nonsubmission after review (the historical "none"
             policy, now explicit rather than silent)
  pad        handled by the generator: names are padded before classification
"""
from __future__ import annotations

from dataclasses import dataclass, field

STATES = ("accepted", "pending_review", "approved_exception", "voluntary_nonsubmission")
POLICIES = ("review", "approve", "withdraw", "pad")
LEGACY_POLICIES = {"none": "withdraw"}


@dataclass(frozen=True)
class SubmissionRules:
    min_list: int = 4          # minimum distinct names of a rule-compliant list
    min_same_grade: int = 2    # names from the student's own grade
    max_list: int | None = 8   # public cap (None: not enforced by the rule)

    @classmethod
    def from_scenario(cls, rules):
        if rules.get("min4", True):
            return cls()
        return cls(min_list=1, min_same_grade=0)

    def to_dict(self):
        return {"minList": self.min_list, "minSameGrade": self.min_same_grade, "maxList": self.max_list}


@dataclass
class Submission:
    student: int
    names: list = field(default_factory=list)     # as submitted (deduplicated, no self)
    state: str = "voluntary_nonsubmission"
    reason: str = ""
    decision: str | None = None                   # review decision applied, if any
    note: str = ""

    @property
    def obligation(self):
        """Effective list used for scheduling; empty when there is no obligation."""
        return list(self.names) if self.state in ("accepted", "approved_exception") else []

    def to_dict(self, ids=None):
        name = (lambda i: ids[i]) if ids else (lambda i: i)
        return {"student": name(self.student), "names": [name(j) for j in self.names], "state": self.state,
                "reason": self.reason, "decision": self.decision, "note": self.note,
                "obligation": [name(j) for j in self.obligation]}


def classify(names, me, grade, rules: SubmissionRules):
    """(state, reason) of a raw submission under the rule; never rewrites names."""
    names = [j for j in dict.fromkeys(names) if j != me]
    if not names:
        return "voluntary_nonsubmission", "no list submitted"
    same = sum(1 for j in names if grade[j] == grade[me])
    problems = []
    if len(names) < rules.min_list:
        problems.append(f"{len(names)} name(s), fewer than {rules.min_list}")
    if same < rules.min_same_grade:
        problems.append(f"{same} same-grade name(s), fewer than {rules.min_same_grade}")
    if rules.max_list is not None and len(names) > rules.max_list:
        problems.append(f"{len(names)} names exceed the cap of {rules.max_list}")
    if problems:
        return "pending_review", "; ".join(problems)
    return "accepted", "satisfies the submission rule"


def build_submissions(raw_lists, grade, rules: SubmissionRules, policy="review", decisions=None):
    """Classify every raw list, then apply explicit decisions and the policy."""
    policy = LEGACY_POLICIES.get(policy, policy)
    if policy not in POLICIES:
        raise ValueError(f"unknown short-list policy {policy!r}; choose one of {POLICIES}")
    out = []
    for me, raw in enumerate(raw_lists):
        names = [j for j in dict.fromkeys(raw) if j != me]
        state, reason = classify(names, me, grade, rules)
        out.append(Submission(student=me, names=names, state=state, reason=reason))
    apply_decisions(out, grade, rules, decisions or {})
    for sub in out:
        if sub.state != "pending_review":
            continue
        if policy == "approve":
            sub.state, sub.decision = "approved_exception", "approve"
            sub.note = "simulation policy: pending request treated as an approved exception"
        elif policy == "withdraw":
            sub.state, sub.decision = "voluntary_nonsubmission", "withdraw"
            sub.note = "simulation policy: pending request recorded as a reviewed withdrawal (no obligation)"
        # "review" and "pad": pending requests stay pending
    return out


def apply_decisions(submissions, grade, rules: SubmissionRules, decisions):
    """Administrator decisions keyed by student index.

    approve            keep the actual list as an approved exception
    withdraw           the student withdrew the request (voluntary nonsubmission)
    resubmit           replace the names; the new list is classified again
    """
    for student, decision in decisions.items():
        sub = submissions[student]
        kind = decision.get("decision") if isinstance(decision, dict) else decision
        note = decision.get("note", "") if isinstance(decision, dict) else ""
        if sub.state != "pending_review" and kind != "resubmit":
            raise ValueError(f"student {student} is not pending review ({sub.state})")
        if kind == "approve":
            sub.state, sub.decision, sub.note = "approved_exception", "approve", note or "approved by an administrator"
        elif kind == "withdraw":
            sub.state, sub.decision, sub.note = "voluntary_nonsubmission", "withdraw", note or "withdrawn after review"
        elif kind == "resubmit":
            names = [j for j in dict.fromkeys(decision["names"]) if j != student]
            state, reason = classify(names, student, grade, rules)
            sub.names, sub.state, sub.reason, sub.decision = names, state, reason, "resubmit"
            sub.note = note or "resubmitted after review"
        else:
            raise ValueError(f"unknown review decision {kind!r} for student {student}")
    return submissions


def obligation_lists(submissions):
    return [sub.obligation for sub in submissions]


def summarize(submissions, ids=None):
    name = (lambda i: ids[i]) if ids else (lambda i: i)
    counts = {state: 0 for state in STATES}
    by_state = {state: [] for state in STATES}
    for sub in submissions:
        counts[sub.state] += 1
        by_state[sub.state].append(name(sub.student))
    return {"counts": counts,
            "pendingReview": by_state["pending_review"],
            "approvedExceptions": by_state["approved_exception"],
            "voluntaryNonsubmission": by_state["voluntary_nonsubmission"],
            "obligated": counts["accepted"] + counts["approved_exception"],
            "schedulable": counts["pending_review"] == 0}

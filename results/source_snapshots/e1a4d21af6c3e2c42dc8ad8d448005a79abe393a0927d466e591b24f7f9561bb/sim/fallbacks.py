"""Cache of independently validated feasible charts, keyed by hard constraints.

A chart enters the cache only after ``constraints.validate_chart`` accepts it
for the problem it was produced for; it leaves the cache only through
``forget``.  Retrieval revalidates every chart against the *current* problem
before it is handed out, so a stale entry (same key, different inputs through
some caller error) can never be released.  Meeting history is outside the key:
it changes scores, not validity.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .constraints import hard_constraint_key, validate_chart


class FeasibleChartCache:
    def __init__(self):
        self._charts = {}      # key -> list of entries
        self.events = []

    @staticmethod
    def key_for(p, present=None, staff=None):
        return hard_constraint_key(p.grade, p.lists, p.caps, p.table_grade, p.state,
                                   present=present, staff=p.staff if staff is None else staff, targets=p.targets)

    def store(self, key, p, assign, source):
        report = validate_chart(p, assign)
        if not report["valid"]:
            self.events.append({"event": "rejected", "key": key, "source": source, "problems": report["problems"][:3]})
            return False
        entries = self._charts.setdefault(key, [])
        if any(e["assign"] == list(assign) for e in entries):
            return True
        entries.append({"assign": list(assign), "source": source,
                        "validatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        self.events.append({"event": "stored", "key": key, "source": source})
        return True

    def candidates(self, key, p):
        """Charts stored under ``key`` that are valid for ``p`` right now."""
        out = []
        for entry in self._charts.get(key, []):
            report = validate_chart(p, entry["assign"])
            if report["valid"]:
                out.append(entry)
            else:
                self.events.append({"event": "stale", "key": key, "source": entry["source"],
                                    "problems": report["problems"][:3]})
        return out

    def charts(self, key, p):
        return [e["assign"] for e in self.candidates(key, p)]

    def forget(self, key):
        self._charts.pop(key, None)

    def summary(self):
        return {key: [{"source": e["source"], "validatedAt": e["validatedAt"]} for e in entries]
                for key, entries in self._charts.items()}

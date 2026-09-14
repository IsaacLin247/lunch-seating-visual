"""The one canonical objective specification used by every stage.

Default objective (the manuscript's Equation for C_r):

    C = sum_i max(0, s_i - 1)  +  lambda * sum_{co-seated pairs} (5 m_ab + 2 alpha_ab),
    lambda = 0.1,

where s_i counts eligible listed tablemates of submitter i, m_ab counts prior
incidental meetings of the pair (neither listed the other at the time) and
alpha_ab counts prior meetings while at least one listed the other.  The two
counters are mutually exclusive: every past meeting is in exactly one of them.

The penalty for additional listed companions (``extra_weight``) is
configurable; the hard at-least-one requirement is not.  Every weight is a
rational number, so the implementation can work with exact integers: the
integer cost is ``scale * C`` with ``scale`` the smallest positive integer that
makes every scaled weight an integer.  With the defaults this is the historical
scaling (10 per extra companion, 5 per incidental repeat, 2 per listed repeat,
10000 per violated obligation, annealing temperature 25 -> 0.2).

CP-SAT minimises exactly ``extra_int * extras + sum(m_int m_ab + alpha_int
alpha_ab)`` over co-seated pairs, so for feasible charts its objective is the
integer cost of the annealer; with the defaults that is
``10 * extras + sum(5 m_ab + 2 alpha_ab)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import lcm


def _rational(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, float):
        return Fraction(value).limit_denominator(10_000)
    return Fraction(value)


@dataclass(frozen=True)
class Objective:
    """Weights of the rotation objective and their exact integer scaling."""
    extra_weight: Fraction = Fraction(1)        # per listed companion beyond the first
    repeat_lambda: Fraction = Fraction(1, 10)   # multiplier of the history term
    incidental_repeat: int = 5                  # inside the history term, per incidental prior meeting
    listed_repeat: int = 2                      # inside the history term, per listed prior meeting
    violation_weight: int = 1000                # finite penalty per unmet obligation during search only
    t0: Fraction = Fraction(5, 2)               # unscaled annealing temperature, start
    t1: Fraction = Fraction(1, 50)              # unscaled annealing temperature, end

    def __post_init__(self):
        object.__setattr__(self, "extra_weight", _rational(self.extra_weight))
        object.__setattr__(self, "repeat_lambda", _rational(self.repeat_lambda))
        object.__setattr__(self, "t0", _rational(self.t0))
        object.__setattr__(self, "t1", _rational(self.t1))
        if self.extra_weight < 0 or self.repeat_lambda < 0:
            raise ValueError("objective weights must be nonnegative")
        if self.incidental_repeat < 0 or self.listed_repeat < 0 or self.violation_weight <= 0:
            raise ValueError("repeat weights must be nonnegative and the violation weight positive")

    # ----- exact integer scaling ---------------------------------------------
    @property
    def scale(self) -> int:
        """Smallest positive integer making every scaled weight integral."""
        return lcm(self.extra_weight.denominator,
                   (self.repeat_lambda * self.incidental_repeat).denominator,
                   (self.repeat_lambda * self.listed_repeat).denominator)

    @property
    def extra_int(self) -> int:
        return int(self.extra_weight * self.scale)

    @property
    def m_int(self) -> int:
        return int(self.repeat_lambda * self.incidental_repeat * self.scale)

    @property
    def alpha_int(self) -> int:
        return int(self.repeat_lambda * self.listed_repeat * self.scale)

    @property
    def violation_int(self) -> int:
        return self.violation_weight * self.scale

    @property
    def t0_int(self) -> float:
        return float(self.t0 * self.scale)

    @property
    def t1_int(self) -> float:
        return float(self.t1 * self.scale)

    # ----- scoring ------------------------------------------------------------
    def pair_weight(self, m: int, alpha: int) -> int:
        """Integer history cost of seating a pair with the given counters together."""
        return self.m_int * m + self.alpha_int * alpha

    def integer_cost(self, violations: int, extras: int, repeat: int) -> int:
        return self.violation_int * violations + self.extra_int * extras + repeat

    def unscaled(self, integer_cost: int) -> Fraction:
        return Fraction(integer_cost, self.scale)

    def describe(self) -> dict:
        """JSON-serialisable statement of the objective and its integer form."""
        return {
            "formula": "C = extra_weight * sum_i max(0, s_i - 1) + lambda * sum_pairs (m_w * m_ab + alpha_w * alpha_ab)",
            "extraWeight": float(self.extra_weight), "lambda": float(self.repeat_lambda),
            "incidentalRepeat": self.incidental_repeat, "listedRepeat": self.listed_repeat,
            "violationWeight": self.violation_weight,
            "integerScale": self.scale,
            "integerWeights": {"extra": self.extra_int, "incidentalRepeatPerMeeting": self.m_int,
                               "listedRepeatPerMeeting": self.alpha_int, "violation": self.violation_int},
            "cpsatObjective": f"{self.extra_int} * extras + sum({self.m_int} m_ab + {self.alpha_int} alpha_ab)",
            "temperature": {"T0": float(self.t0), "T1": float(self.t1),
                            "T0Integer": self.t0_int, "T1Integer": self.t1_int},
            "hardConstraint": "every obligated student shares a table with at least one present, eligible listed companion",
        }


DEFAULT_OBJECTIVE = Objective()


def objective_from_config(config=None) -> Objective:
    """Build an objective from a plain mapping (CLI/JSON friendly)."""
    if config is None:
        return DEFAULT_OBJECTIVE
    if isinstance(config, Objective):
        return config
    fields = {}
    for key, name in (("extraWeight", "extra_weight"), ("extra_weight", "extra_weight"),
                      ("lambda", "repeat_lambda"), ("repeat_lambda", "repeat_lambda"),
                      ("incidentalRepeat", "incidental_repeat"), ("incidental_repeat", "incidental_repeat"),
                      ("listedRepeat", "listed_repeat"), ("listed_repeat", "listed_repeat"),
                      ("violationWeight", "violation_weight"), ("violation_weight", "violation_weight")):
        if key in config:
            fields[name] = config[key]
    return Objective(**fields)

"""Analytic random baseline and chart-only leakage probe (audit C3, D2)."""
from sim.baseline import expected_distinct, expected_friend_coverage, pair_meet_probability
from sim.privacy import infer_forced_names, min_hitting_set, leakage_report
from sim.solver import table_layout


def test_pair_probability_and_expected_distinct_match_closed_form():
    caps_m = table_layout("mixed")[0]
    caps_s, tg = table_layout("same")
    grade = [11] * 132 + [12] * 125
    by_grade = {g: [c for c, t in zip(caps_s, tg) if t == g] for g in (11, 12)}
    assert abs(pair_meet_probability(caps_m, 257) - 1404 / (257 * 256)) < 1e-12
    alt = expected_distinct(grade, caps_m, by_grade, ["mixed", "same"] * 8)
    mixed = expected_distinct(grade, caps_m, by_grade, ["mixed"] * 16)
    assert abs(alt - 72.2891) < 0.001 and abs(mixed - 74.7202) < 0.001


def test_friend_coverage_matches_hypergeometric():
    caps_m = table_layout("mixed")[0]
    caps_s, tg = table_layout("same")
    grade = [11] * 132 + [12] * 125
    by_grade = {g: [c for c, t in zip(caps_s, tg) if t == g] for g in (11, 12)}
    lists = [[(i + d) % 257 for d in range(1, 9)] for i in range(257)]  # 8 names each
    cov = expected_friend_coverage(grade, lists, caps_m, by_grade, "mixed")
    assert abs(cov - 16.0448) < 0.01


def test_forced_name_inference_worst_case():
    # nine tablemate sets sharing only b: omitting b needs nine names, so b is forced under K <= 8
    peers = [{"b", f"x{r}"} for r in range(9)]
    forced, cover = infer_forced_names(peers, 8)
    assert forced == ["b"] and cover == ["b"]
    assert min_hitting_set({"b": 0b111, "c": 0b001}, 3) == ["b"]


def test_leakage_report_scores_against_truth():
    trace = {"students": [{"id": "A"}, {"id": "B"}, {"id": "C"}, {"id": "D"}],
             "listed": [["B"], ["A"], ["D"], ["C"]],
             "rotations": [{"tables": [["A", "B"], ["C", "D"]]} for _ in range(3)]}
    rep = leakage_report(trace, k_max=1)
    assert rep["forcedEdges"] == 4 and rep["forcedEdgesCorrect"] == 4 and len(rep["fullyDeterminedStudents"]) == 4


def _short_list_trace():
    return {"config": {"K": 2},
            "students": [{"id": name} for name in "ABCD"],
            "listed": [["B"], ["A"], ["D"], ["C"]],
            "rotations": [{"tables": [["A", "B"], ["C", "D"]]}]}


def test_short_private_list_recovery_is_not_unique_identification():
    # The observer cannot distinguish {B} from {B,C} for A under cap two.
    rep = leakage_report(_short_list_trace(), k_max=2)
    assert rep["forcedEdges"] == rep["forcedEdgesCorrect"] == 4
    assert rep["fullyDeterminedStudents"] == []
    assert rep["completeTruePositiveRecoveryStudents"] == list("ABCD")


def test_default_privacy_cap_uses_public_config_not_private_maximum():
    rep = leakage_report(_short_list_trace())
    assert rep["kMax"] == 2
    assert rep["fullyDeterminedStudents"] == []
    assert rep["inferenceAssumptions"]["usesPrivateLengthsForInference"] is False


def test_public_exact_length_can_identify_a_short_list():
    rep = leakage_report(_short_list_trace(), k_max=2, public_list_lengths={"A": 1})
    assert rep["fullyDeterminedStudents"] == ["A"]
    assert rep["completeTruePositiveRecoveryStudents"] == list("ABCD")


def test_inconsistent_cap_is_reported_without_forced_entries():
    rep = leakage_report(_short_list_trace(), k_max=0)
    assert rep["inconsistentObservationStudents"] == list("ABCD")
    assert rep["forcedEdges"] == 0
    assert rep["fullyDeterminedStudents"] == []


def test_public_exact_length_equal_to_peer_universe_forces_unobserved_names():
    trace = {"config": {"K": 2}, "students": [{"id": i} for i in "ABC"],
             "listed": [["B", "C"], ["A"], []],
             "rotations": [{"tables": [["A", "B"], ["C"]]}]}
    cap_only = leakage_report(trace)
    assert cap_only["perStudent"]["A"] == ["B"]
    assert cap_only["fullyDeterminedStudents"] == []
    exact = leakage_report(trace, public_list_lengths={"A": 2})
    assert exact["perStudent"]["A"] == ["B", "C"]
    assert exact["fullyDeterminedStudents"] == ["A"]
    assert exact["completeTruePositiveRecoveryStudents"] == ["A", "B"]
    assert exact["forcedEdges"] == exact["forcedEdgesCorrect"] == 3


def test_public_exact_length_does_not_force_whole_universe_below_saturation():
    trace = {"config": {"K": 2}, "students": [{"id": i} for i in "ABCD"],
             "listed": [["B", "C"], ["A"], [], []],
             "rotations": [{"tables": [["A", "B"], ["C", "D"]]}]}
    exact = leakage_report(trace, public_list_lengths={"A": 2})
    assert exact["perStudent"]["A"] == ["B"]
    assert exact["fullyDeterminedStudents"] == []

"""Structural cohesion bounds for coalition wirings (audit: attacker strength)."""
from sim.attacks import analyse_wiring, best_four_of_five_wiring, cohesion_bound, wiring_from_omissions


def test_omission_star_forces_mean_cluster_three_and_passes_screen():
    r = analyse_wiring([1, 0, 0, 0, 0, 0])
    assert r["minMeanCluster"] == 3.0 and r["minLargestCluster"] == 3 and r["screenFlags"] == []


def test_two_three_cycles_can_be_split_into_pairs():
    r = analyse_wiring([1, 2, 0, 4, 5, 3])
    assert r["minMeanCluster"] == 2.0 and r["minExtraPeers"] == 0


def test_no_four_of_five_wiring_beats_the_star():
    best, wirings = best_four_of_five_wiring()
    assert best == 3.0 and [1, 0, 0, 0, 0, 0] in wirings


def test_chain_cannot_be_split_at_all():
    lists = [[(i + 1) % 6] for i in range(6)]
    assert cohesion_bound(lists) == (6.0, 6, 0)
    assert wiring_from_omissions([1, 0, 0, 0, 0, 0])[0] == [2, 3, 4, 5]

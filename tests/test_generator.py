"""Spec 1: latent friend groups in the cohort generator."""

from sim.generator import make_cohort, generate_network, honest_lists


def _within_grade_frac(net):
    tot = sum(len(f) for f in net.friends)
    return sum(1 for i, f in enumerate(net.friends) for j in f if net.grade[j] == net.grade[i]) / tot


def test_default_is_plain_network_and_alias_matches():
    a = make_cohort(seed=3)
    b = generate_network(seed=3)
    assert a.friends == b.friends and a.groups == [] and a.mu == 0.0 and a.omega == 0.0


def test_in_group_fraction_tracks_mu():
    for mu in (0.3, 0.6, 0.8):
        net = make_cohort(seed=5, mu=mu, omega=0.0)
        assert abs(net.in_group_fraction() - mu) < 0.05, (mu, net.in_group_fraction())
        assert all(len(f) == 8 for f in net.friends)


def test_overlap_frequency_tracks_omega():
    for omega in (0.0, 0.3, 0.6):
        net = make_cohort(seed=5, mu=0.6, omega=omega)
        freq = sum(1 for s in net.secondary if s is not None) / net.n
        assert abs(freq - omega) < 0.05, (omega, freq)
        assert all(s is None or s != p for s, p in zip(net.secondary, net.primary))


def test_grade_bias_preserved_at_mu_zero():
    plain = make_cohort(seed=5)
    grouped = make_cohort(seed=5, mu=0.0, omega=0.3)
    assert _within_grade_frac(plain) > 0.85
    assert abs(_within_grade_frac(grouped) - _within_grade_frac(plain)) < 0.03


def test_mu_one_reproduces_isolated_cliques():
    net = make_cohort(seed=5, mu=1.0, omega=0.0)
    assert net.in_group_fraction() == 1.0
    assert all(set(f) <= net.group_pool(i) for i, f in enumerate(net.friends))
    # honest submissions from a small isolated group are legitimately insular
    lists = honest_lists(net)
    assert min(len(l) for l in lists) >= 4


def test_group_sizes_and_grade_purity():
    net = make_cohort(seed=5, mu=0.6, omega=0.3, group_size_dist=(6, 12))
    sizes = [len(g) for g in net.groups]
    assert min(sizes) >= 6 and max(sizes) <= 12 + 5      # a small remainder may be folded in
    assert sorted(m for g in net.groups for m in g) == list(range(net.n))
    assert all(len({int(net.grade[m]) for m in g}) == 1 for g in net.groups)
    mixed = make_cohort(seed=5, mu=0.6, omega=0.3, cross_grade_group_frac=1.0)
    assert any(len({int(mixed.grade[m]) for m in g}) == 2 for g in mixed.groups)


def test_cohort_is_deterministic():
    a = make_cohort(seed=9, mu=0.6, omega=0.3)
    b = make_cohort(seed=9, mu=0.6, omega=0.3)
    assert a.friends == b.friends and a.groups == b.groups and a.secondary == b.secondary
    assert a.clique == b.clique and len({a.primary[m] for m in a.clique}) == 1

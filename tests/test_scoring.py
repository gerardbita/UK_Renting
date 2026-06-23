from rentwatch.scoring import (
    ScoreInput,
    balanced_score,
    best_commute_minutes,
    price_percentiles,
)


def score(**kwargs):
    return balanced_score(ScoreInput(**kwargs)).score


def test_best_commute_takes_faster_mode():
    assert best_commute_minutes(40, 25) == 25
    assert best_commute_minutes(None, 30) == 30
    assert best_commute_minutes(None, None) is None


def test_balanced_commute_beats_lopsided_with_same_average():
    balanced = score(commutes=[40, 40])
    lopsided = score(commutes=[10, 70])  # same mean, worse bottleneck
    assert balanced > lopsided


def test_shorter_commute_scores_higher():
    assert score(commutes=[20, 25]) > score(commutes=[55, 60])


def test_let_agreed_is_penalised():
    assert score(commutes=[30, 30]) > score(commutes=[30, 30], let_agreed=True)


def test_cheaper_listing_scores_higher():
    cheap = score(commutes=[30, 30], price_percentile=0.0)
    pricey = score(commutes=[30, 30], price_percentile=1.0)
    assert cheap > pricey


def test_missing_routes_penalised_but_not_zeroed():
    full = score(commutes=[30, 30])
    partial = score(commutes=[30, None])
    none = score(commutes=[None, None])
    assert full > partial > none
    assert none > 0


def test_weighting_a_target_changes_effective_commute():
    # Weight the fast target heavily -> bottleneck softens -> higher score.
    even = score(commutes=[15, 65])
    favour_fast = score(commutes=[15, 65], weights=(3.0, 1.0))
    assert favour_fast > even


def test_amenities_and_size_add_points():
    base = score(commutes=[30, 30])
    nicer = score(commutes=[30, 30], has_garden=True, has_parking=True, size_sqft=900)
    assert nicer > base


def test_price_percentiles_rank_cheapest_lowest():
    ranks = price_percentiles([1000, 2000, 1500, None])
    assert ranks[1000] == 0.0
    assert ranks[2000] == 1.0
    assert 0.0 < ranks[1500] < 1.0

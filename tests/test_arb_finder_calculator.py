from __future__ import annotations

from arb_finder.calculator import value_bet_edge


def test_positive_edge():
    # decimal_odds=2.00, true_prob=0.525 -> 2.00*0.525-1 = +0.05
    assert round(value_bet_edge(2.00, 0.525), 6) == 0.05


def test_negative_edge():
    # decimal_odds=2.10, true_prob=0.40 -> 2.10*0.40-1 = -0.16
    assert round(value_bet_edge(2.10, 0.40), 6) == -0.16


def test_zero_edge_at_fair_odds():
    # decimal_odds exactly matching true_prob's fair price -> edge is 0
    assert round(value_bet_edge(2.0, 0.50), 6) == 0.0


def test_real_captured_data_negative_edge():
    # Real Commanders/Lions data: Paddy Power backs Commanders at 2.6,
    # Polymarket's post-move Commanders price was 0.36 -> a bad bet.
    assert round(value_bet_edge(2.6, 0.36), 6) == round(2.6 * 0.36 - 1, 6)

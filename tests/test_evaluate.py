from datetime import date

import numpy as np

from witching_hour.evaluate import auc, evaluate, plant, recall_at_fpr
from witching_hour.scanner import SeasonalBackend


def test_plant_only_touches_the_window():
    y = np.zeros(36)
    out = plant(y, 10, 4, 2.0)
    assert (out[:10] == 0).all() and (out[14:] == 0).all()
    assert (out[10:14] > 0).all() and out.max() <= 2.0
    assert (y == 0).all()  # input untouched


def test_auc_and_recall():
    assert auc(np.array([3, 4]), np.array([1, 2])) == 1.0
    assert auc(np.array([1.0]), np.array([1.0])) == 0.5
    assert recall_at_fpr(np.array([10, 0.5]), np.arange(100) / 100, 0.05) == 0.5


def test_evaluate_runs_and_prefers_planted_nights(house):
    nights = [date(2016, 1, 15), date(2016, 1, 16), date(2016, 1, 18)]
    res = evaluate(house, [SeasonalBackend()], nights, ["T1", "T2"])
    r = res[0]
    assert r.backend == "seasonal-same-hour" and r.n_cases == 6
    assert 0.5 <= r.auc <= 1.0
    assert 0.0 <= r.coverage90 <= 1.0
    assert set(r.recall_fpr5_by_strength) <= {"1.0", "2.0", "3.0"}

import pytest

from pipeline.summarize import _validate


def _base_data(**overrides):
    data = {
        "summary": "One. Two. Three.",
        "why_it_matters": "It matters.",
        "category": "coding",
        "importance": 5,
    }
    data.update(overrides)
    return data


def test_validate_accepts_importance_in_range():
    _validate(_base_data(importance=1))
    _validate(_base_data(importance=5))
    _validate(_base_data(importance=10))


def test_validate_rejects_missing_importance():
    data = _base_data()
    del data["importance"]
    with pytest.raises(ValueError):
        _validate(data)


def test_validate_rejects_importance_below_range():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=0))


def test_validate_rejects_importance_above_range():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=11))


def test_validate_rejects_non_int_importance():
    with pytest.raises(ValueError):
        _validate(_base_data(importance="7"))
    with pytest.raises(ValueError):
        _validate(_base_data(importance=7.5))


def test_validate_rejects_bool_importance():
    with pytest.raises(ValueError):
        _validate(_base_data(importance=True))

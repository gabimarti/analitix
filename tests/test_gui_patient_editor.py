from analitix.gui import _smoking_summary


def test_smoking_summary():
    assert _smoking_summary({}) == ""
    assert _smoking_summary({"smoker_current": 0, "smoker_former": 0}) == "No fumador"
    assert _smoking_summary({"smoker_current": 1}) == "Fumador"
    assert _smoking_summary({"smoker_former": 1, "smoker_former_from": 1998, "smoker_former_to": 2010}) == (
        "Exfumador (1998-2010)"
    )
    assert _smoking_summary({"smoker_former": 1, "smoker_former_period": "de joven"}) == "Exfumador (de joven)"

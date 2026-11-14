from simulation.lab_demos.dilution.run import dose_from_engagement, dilution_result


def test_dose_requires_engagement_and_is_capped():
    assert dose_from_engagement(0.0) == 0.0
    assert dose_from_engagement(0.5, enabled=False) == 0.0
    assert dose_from_engagement(0.325) == 10.0
    assert dose_from_engagement(4.0) == 20.0


def test_dilution_conserves_solute_and_lowers_concentration():
    amount, concentration = dilution_result(20.0, 1.0, 16.0)
    assert amount == 36.0
    assert concentration == 20.0 / 36.0
    assert amount * concentration == 20.0


def test_negative_control_has_no_expected_change():
    dose = dose_from_engagement(1.0, enabled=False)
    amount, concentration = dilution_result(20.0, 1.0, dose)
    assert dose == 0
    assert amount == 20
    assert concentration == 1

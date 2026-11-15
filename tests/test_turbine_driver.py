from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from turbine_driver import gas_performance, shaft_balance, steam_performance


def test_power_boundary():
    inferred = shaft_balance(1400, 0.98)
    assert inferred['driver_shaft_kW'] == pytest.approx(1400 / 0.98)
    assert inferred['independent_balance_difference_kW'] is None
    assert shaft_balance(1400, 0.98, 1450)['independent_balance_difference_kW'] is None
    measured = shaft_balance(1400, 0.98, 1450, True)
    assert measured['independent_balance_difference_kW'] == pytest.approx(21)


def test_condensing_wet_exhaust():
    result = steam_performance(60, 480, 0.1, 1.4, 1400, 'Vapour quality (%)', 90)
    assert result['internal_isentropic_efficiency_pct'] == pytest.approx(84.8, abs=0.001)
    with pytest.raises(ValueError, match='above saturation'):
        steam_performance(60, 480, 0.1, 1.4, 1400, 'Superheated temperature (°C)', 45)


def test_driver_workflow():
    app = Path(__file__).resolve().parents[1] / 'app.py'
    at = AppTest.from_file(str(app), default_timeout=30).run()
    at.checkbox(key='phase_Centrifugal').check()
    at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
    for mode, metric, expected in [
        ('Back-pressure steam', 'shaft_isentropic_efficiency_pct', 71.831),
        ('Condensing steam', 'shaft_isentropic_efficiency_pct', 82.288),
        ('Gas turbine', 'fuel_to_shaft_efficiency_pct', 28),
    ]:
        at.radio(key='turbine_type').set_value(mode).run()
        at.button(key='FormSubmitter:turbine_driver_form-Calculate driver performance').click().run()
        assert not at.exception
        assert not at.error
        report = at.session_state['turbine_driver_report'][1]
        assert report['driver_metrics'][metric] == pytest.approx(expected, abs=0.001)
        assert len(at.get('download_button')) == 4
        if mode == 'Condensing steam':
            assert report['driver_metrics']['internal_isentropic_efficiency_pct'] is None
    at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
    assert len(at.get('download_button')) == 3


def test_gas_energy_basis():
    result = gas_performance(0.1, 50_000, 'LHV', 1400)
    assert result['shaft_heat_rate_kJkWh'] == pytest.approx(3600 / 0.28)

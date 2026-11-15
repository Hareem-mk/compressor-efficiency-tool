"""Field screening for mechanical drivers of centrifugal compressors."""
from math import isfinite

from iapws import IAPWS97


def positive(value, label):
    if not isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be finite and greater than zero.')
    return value


def shaft_balance(compressor_kw, transmission_efficiency, driver_kw=None,
                  compressor_power_independent=False):
    positive(compressor_kw, 'Compressor shaft demand')
    if not 0 < transmission_efficiency <= 1:
        raise ValueError('Transmission efficiency must be greater than 0% and at most 100%.')
    inferred = driver_kw is None
    if inferred:
        driver_kw = compressor_kw / transmission_efficiency
    positive(driver_kw, 'Driver shaft output')
    delivered_kw = driver_kw * transmission_efficiency
    return {
        'driver_power_basis': 'Estimated from compressor load' if inferred else 'Measured driver shaft output',
        'driver_shaft_kW': driver_kw,
        'transmission_efficiency_pct': 100 * transmission_efficiency,
        'transmission_loss_kW': driver_kw - delivered_kw,
        'delivered_shaft_kW': delivered_kw,
        'compressor_demand_kW': compressor_kw,
        'compressor_power_independent': bool(compressor_power_independent),
        'independent_balance_difference_kW': (
            delivered_kw - compressor_kw if not inferred and compressor_power_independent else None
        ),
    }


def steam_performance(inlet_bar, inlet_c, exhaust_bar, steam_kg_s, shaft_kw,
                      exhaust_basis='Unavailable', exhaust_value=None):
    """IF97, one inlet and one outlet, negligible other flows and heat transfer."""
    positive(inlet_bar, 'Inlet absolute pressure')
    positive(exhaust_bar, 'Exhaust absolute pressure')
    positive(steam_kg_s, 'Steam flow')
    positive(shaft_kw, 'Driver shaft output')
    if exhaust_bar >= inlet_bar:
        raise ValueError('Steam exhaust pressure must be below inlet pressure.')
    if not -273.15 < inlet_c < float('inf'):
        raise ValueError('Enter a valid inlet steam temperature.')
    inlet = IAPWS97(P=inlet_bar / 10, T=inlet_c + 273.15)
    if inlet.region not in (2, 5):
        raise ValueError('This model requires superheated inlet steam in IF97 region 2 or 5.')
    pressure = exhaust_bar / 10
    ideal = IAPWS97(P=pressure, s=inlet.s)
    ideal_kw = positive(steam_kg_s * (inlet.h - ideal.h), 'Ideal steam power')
    result = {
        'inlet_enthalpy_kJkg': inlet.h,
        'ideal_exhaust_enthalpy_kJkg': ideal.h,
        'ideal_steam_power_kW': ideal_kw,
        'shaft_isentropic_efficiency_pct': 100 * shaft_kw / ideal_kw,
        'specific_steam_consumption_kgkWh': 3600 * steam_kg_s / shaft_kw,
        'actual_exhaust_enthalpy_kJkg': None,
        'internal_isentropic_efficiency_pct': None,
    }
    if exhaust_basis == 'Unavailable':
        return result
    if exhaust_value is None or not isfinite(exhaust_value):
        raise ValueError('Enter a finite exhaust property.')
    saturated_liquid = IAPWS97(P=pressure, x=0)
    saturated_vapour = IAPWS97(P=pressure, x=1)
    if exhaust_basis == 'Superheated temperature (°C)':
        if exhaust_value + 273.15 <= saturated_vapour.T + 0.05:
            raise ValueError('Exhaust temperature must be above saturation. For wet steam, use independently established quality or enthalpy.')
        exhaust_h = IAPWS97(P=pressure, T=exhaust_value + 273.15).h
    elif exhaust_basis == 'Vapour quality (%)':
        if not 0 < exhaust_value <= 100:
            raise ValueError('Vapour quality must be greater than 0% and at most 100%.')
        exhaust_h = IAPWS97(P=pressure, x=exhaust_value / 100).h
    elif exhaust_basis == 'Enthalpy (kJ/kg)':
        if exhaust_value <= saturated_liquid.h:
            raise ValueError('Exhaust enthalpy must describe steam, above saturated liquid enthalpy.')
        exhaust_h = exhaust_value
    else:
        raise ValueError('Unrecognized exhaust property basis.')
    fluid_kw = positive(steam_kg_s * (inlet.h - exhaust_h), 'Steam enthalpy-drop power')
    result.update(
        actual_exhaust_enthalpy_kJkg=exhaust_h,
        steam_enthalpy_drop_power_kW=fluid_kw,
        internal_isentropic_efficiency_pct=100 * fluid_kw / ideal_kw,
        shaft_to_steam_drop_ratio_pct=100 * shaft_kw / fluid_kw,
    )
    return result


def gas_performance(fuel_kg_s, heating_value_kj_kg, heating_value_basis, shaft_kw):
    positive(fuel_kg_s, 'Fuel flow')
    positive(heating_value_kj_kg, 'Fuel heating value')
    positive(shaft_kw, 'Driver shaft output')
    if heating_value_basis not in ('LHV', 'HHV'):
        raise ValueError('Select LHV or HHV.')
    fuel_kw = fuel_kg_s * heating_value_kj_kg
    return {
        'heating_value_basis': heating_value_basis,
        'fuel_energy_rate_kW': fuel_kw,
        'fuel_to_shaft_efficiency_pct': 100 * shaft_kw / fuel_kw,
        'shaft_heat_rate_kJkWh': 3600 * fuel_kw / shaft_kw,
    }

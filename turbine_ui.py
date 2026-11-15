"""Streamlit controls for the linked turbine driver assessment."""
import json

import streamlit as st

from turbine_driver import gas_performance, shaft_balance, steam_performance


def render_driver(compressor):
    st.subheader('Turbine Driver Performance')
    if not compressor or compressor['case']['machine'] != 'Centrifugal':
        st.info('Calculate a centrifugal compressor case to link its shaft demand here.')
        return
    compressor_kw = compressor['case']['power_kW']
    st.write(f"Linked centrifugal case · **{compressor_kw:,.2f} kW** shaft demand")
    driver = st.radio('Driver type', ['Back-pressure steam', 'Condensing steam', 'Gas turbine'],
                      horizontal=True, key='turbine_type')
    basis = st.radio('Driver shaft power source', ['Estimated from compressor load',
                     'Measured driver shaft output'], key='turbine_basis')
    steam = driver != 'Gas turbine'
    condensing = driver == 'Condensing steam'
    st.caption('Defaults are teaching examples. Enter synchronized readings from the same operating point for a field review.')
    with st.form('turbine_driver_form'):
        transmission = st.number_input('Coupling / gearbox transmission efficiency (%)',
                                       min_value=0.01, max_value=100.0, value=100.0)
        st.caption('100% represents an assumed lossless connection. Enter the applicable efficiency if transmission losses are included.')
        measured = basis == 'Measured driver shaft output'
        driver_kw = None
        independent = False
        if measured:
            driver_kw = st.number_input('Measured turbine output at driver coupling (kW)',
                                        min_value=0.01, value=float(compressor_kw))
            independent = st.checkbox('Compressor shaft demand was measured independently at the same operating point.')
        if steam:
            a, b = st.columns(2)
            inputs = {
                'inlet_bar': a.number_input('Inlet pressure (bar absolute)', min_value=0.01,
                                            value=60.0 if condensing else 40.0, key=f'inlet_p_{driver}'),
                'inlet_c': b.number_input('Inlet temperature (°C)', value=480.0 if condensing else 400.0,
                                          key=f'inlet_t_{driver}'),
                'exhaust_bar': a.number_input('Exhaust pressure (bar absolute)', min_value=0.0062,
                                              value=0.1 if condensing else 5.0, format='%.4f',
                                              key=f'exhaust_p_{driver}'),
                'steam_kg_s': b.number_input('Steam flow (kg/s)', min_value=0.001,
                                             value=1.4 if condensing else 4.0, key=f'steam_flow_{driver}'),
            }
            exhaust_basis = st.selectbox('Actual exhaust property', ['Unavailable',
                'Superheated temperature (°C)', 'Vapour quality (%)', 'Enthalpy (kJ/kg)'],
                index=0 if condensing else 1, key=f'exhaust_basis_{driver}')
            inputs['exhaust_basis'] = exhaust_basis
            inputs['exhaust_value'] = st.number_input(
                'Actual exhaust property value (in selected unit)', value=90.0 if condensing else 200.0,
                key=f'exhaust_value_{driver}',
                help='Ignore this field when Unavailable is selected. Use independently established quality or enthalpy for wet steam.')
            st.caption('Single inlet and exhaust with negligible side flows. For wet exhaust, provide quality or enthalpy from an independent measurement or an agreed heat balance.')
        else:
            inputs = {
                'fuel_kg_s': st.number_input('Fuel mass flow (kg/s)', min_value=0.001, value=0.10),
                'heating_value_kj_kg': st.number_input('Fuel heating value (kJ/kg)', min_value=1.0, value=50000.0),
                'heating_value_basis': st.selectbox('Heating value basis', ['LHV', 'HHV']),
            }
            st.caption('Use fuel flow and heating value on the same mass basis. Results are at the entered operating conditions.')
        submitted = st.form_submit_button('Calculate driver performance')
    result_key = (compressor['calculated_UTC'], driver, basis)
    if submitted:
        st.session_state.pop('turbine_driver_report', None)
        try:
            balance = shaft_balance(compressor_kw, transmission / 100, driver_kw, independent)
            method = steam_performance if steam else gas_performance
            metrics = method(**inputs, shaft_kw=balance['driver_shaft_kW'])
        except (ValueError, NotImplementedError, OverflowError) as exc:
            st.error(str(exc) or 'Steam state is outside the supported IF97 range.')
        else:
            st.session_state['turbine_driver_report'] = (result_key, {
                'driver_type': driver, 'driver_inputs': inputs, 'shaft_balance': balance,
                'driver_metrics': metrics, 'compressor': compressor,
            })
    saved = st.session_state.get('turbine_driver_report')
    if not saved or saved[0] != result_key:
        return
    report = saved[1]
    metrics = report['driver_metrics']
    balance = report['shaft_balance']
    st.write(f"**Power basis:** {balance['driver_power_basis']}")
    labels = {
        'driver_shaft_kW': 'Driver shaft output (kW)',
        'delivered_shaft_kW': 'Power delivered to compressor (kW)',
        'compressor_demand_kW': 'Compressor shaft demand (kW)',
        'transmission_loss_kW': 'Transmission loss (kW)',
        'independent_balance_difference_kW': 'Delivered power minus independent demand (kW)',
        'shaft_isentropic_efficiency_pct': 'Shaft-reference isentropic efficiency (%)',
        'internal_isentropic_efficiency_pct': 'Internal isentropic efficiency (%)',
        'specific_steam_consumption_kgkWh': 'Specific steam consumption (kg/kWh)',
        'fuel_to_shaft_efficiency_pct': 'Fuel-to-shaft efficiency (%)',
        'shaft_heat_rate_kJkWh': 'Shaft heat rate (kJ/kWh)',
    }
    values = {**balance, **metrics}
    st.table([{'Metric': label, 'Value': f'{values[key]:,.3f}'}
              for key, label in labels.items() if values.get(key) is not None])
    if balance['independent_balance_difference_kW'] is None:
        st.caption('An independent power balance requires two independently measured shaft powers.')
    if steam and metrics['internal_isentropic_efficiency_pct'] is None:
        st.caption('Internal efficiency requires independently established actual exhaust enthalpy.')
    if any(metrics.get(key, 0) is not None and metrics.get(key, 0) > 100 for key in (
        'shaft_isentropic_efficiency_pct', 'internal_isentropic_efficiency_pct',
        'shaft_to_steam_drop_ratio_pct', 'fuel_to_shaft_efficiency_pct'
    )):
        st.warning('An efficiency or power ratio exceeds 100%. Check the power basis, flow and state measurements.')
    with st.expander('Calculation details'):
        st.json(metrics)
    st.download_button('Download combined driver and compressor report (JSON)',
                       json.dumps(report, indent=2), 'compressor_driver_report.json',
                       mime='application/json', key='turbine_download')

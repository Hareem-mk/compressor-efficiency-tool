# Phase 2 · Turbine Driver Performance

Calculate the default centrifugal compressor case first. Its 1,400 kW shaft demand links to the **Turbine driver** tab. Select a driver and press **Calculate driver performance**. Recalculate the driver after recalculating the compressor.

## Three worked examples

All examples use 100% assumed transmission efficiency and driver output estimated from compressor demand.

| Driver | Inputs | Expected results |
|---|---|---|
| Back-pressure steam | 40 bar(a), 400°C inlet. 5 bar(a), 200°C exhaust. Steam flow 4 kg/s. | Shaft-reference efficiency 71.831%. Internal efficiency 73.571%. Steam consumption 10.286 kg/kWh. |
| Condensing steam | 60 bar(a), 480°C inlet. 0.1 bar(a) exhaust. Steam flow 1.4 kg/s. Actual exhaust property unavailable. | Shaft-reference efficiency 82.288%. Steam consumption 3.600 kg/kWh. Internal efficiency unavailable. |
| Gas turbine | 0.10 kg/s fuel, 50,000 kJ/kg LHV. | Fuel-to-shaft efficiency 28.000%. Heat rate 12,857.143 kJ/kWh. |

For the condensing case, select vapour quality and enter 90% as a teaching assumption. Internal efficiency should appear as 84.800%.

For an independent balance example, enter measured turbine output of 1,450 kW and transmission efficiency of 98%. Confirm the compressor demand was independently measured. The delivered power is 1,421 kW and the difference is +21 kW. This difference has no automatic pass/fail threshold.

## Methods and scope

Steam properties use IAPWS-IF97. Ideal exhaust enthalpy is evaluated at exhaust pressure and inlet entropy. Shaft-reference efficiency is driver output divided by ideal steam power. Internal efficiency uses the actual enthalpy drop, with the single-inlet and single-exhaust assumptions shown in the app. Saturation pressure and temperature alone cannot determine wet exhaust quality.

Gas turbine efficiency is shaft output divided by fuel mass flow times heating value. Heat rate is fuel energy per shaft kWh. The heating value and mass flow must use a consistent basis.

The JSON report includes the compressor snapshot, driver inputs, metrics and shaft-power basis. Field estimates exclude extraction/admission, process heat credit and OEM reference-condition corrections. For formal testing, refer to the agreed edition of ASME PTC 6 for steam, and ASME PTC 22 or ISO 2314 for gas turbines.

## Install and review

Use Python 3.12. Install from requirements.txt and run the Streamlit app from this folder. For local tests, install requirements-dev.txt and run `python -m pytest tests -q`.

For an existing GitHub deployment, upload app.py, engineering.py, turbine_driver.py, turbine_ui.py and requirements.txt together in a single commit. PHASE_2.md and tests/test_turbine_driver.py document the examples and automated checks.

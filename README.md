# Compressor Efficiency Tool — standalone Streamlit app

Version 1.0.0. All calculations run locally in Python: no AI API, key or paid
property service is required. This is a separate application, not a Conversion
Pro modification. It is intended for engineering training and field screening.

## Start locally

Python 3.12 is the tested runtime. From the extracted application folder:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On Windows, activate with `.venv\Scripts\activate` instead. Streamlit prints
the local application URL. Open that URL in your browser.

## Deploy to Streamlit Community Cloud

1. Create a new GitHub repository for this standalone project.
2. Upload this folder's contents to the repository root, preserving `.streamlit/`.
3. Create a Streamlit app using that repository and `app.py` as the entry point.
4. Select Python 3.12. No Secrets/API key is needed.
5. Run the acceptance checklist below before sharing the generated URL.

This package has not been deployed to a public site. A public deployment URL
does not exist until you deploy it.

## Files

- `app.py`: complete interface and report downloads.
- `engineering.py`: reusable real-gas calculation engine.
- `requirements.txt`: runtime dependencies.
- `.streamlit/config.toml`: theme, upload limit and usage-statistics setting.
- `tests/`: calculation and Streamlit interaction checks.
- `examples/`: clearly labelled synthetic CSV inputs and expected example results.
- `CODEX_HANDOFF.md`: instructions for subsequent work in Codex.
- `VALIDATION.md`: verification scope and results for this release.

## Supported machines and outputs

| Machine | Outputs |
|---|---|
| Centrifugal / axial | Real-gas isentropic head, internal and shaft-reference efficiency, classical Schultz head/efficiency, optional numerical polytropic cross-check |
| Reciprocating | Isentropic shaft-reference, volumetric efficiency, capacity deficit, specific energy, optional P–V card indicated power |
| Screw / rotary lobe / sliding vane | Isentropic/isothermal shaft-reference, volumetric efficiency, apparent capacity deficit and specific energy |
| Liquid ring | Limited reference-power/capacity screening, with explicit negligible-vapour-transfer assumption |

Additional features: pressure/temperature/flow-unit inputs, explicit standard
flow base, gas composition and optional PR interaction parameters, partial P/T
uncertainty, matched OEM CSV interpolation, JSON/CSV/printable HTML export and
field-test checklist.

## First run

1. Select **Centrifugal** and leave the assumed natural-gas composition.
2. Review the default measurements (30 to 60 bar absolute, 35 to 101.85°C,
   10 kg/s, 1400 kW).
3. Independently verify stable gas phase. The checkbox is an acknowledgement;
   the app does not perform a phase-stability calculation.
4. Click **Calculate performance**.
5. Expect approximately **76.02% Schultz polytropic efficiency**, **72.52%
   shaft-reference isentropic efficiency**, and **101.522 kJ/kg isentropic head**.
6. Review the input snapshot and assumptions before downloading results.

All preset measurements and compositions are synthetic teaching examples.
Default PD discharge temperatures are illustrative inputs; the reference-power
efficiency uses suction state, discharge pressure, flow and shaft power and does
not assume that the measured gas enthalpy rise equals input power.

## Units and flow bases

Pressure inputs include bar(a), kPa(a), MPa(a), psia, bar(g) and psig. Gauge
pressures use the entered local atmospheric pressure. Temperature supports °C,
K and °F. Flow supports kg/s, kg/h, actual suction m³/h, standard m³/h and MMSCFD.

**Changing an input unit reinterprets the entered number; it does not convert
the displayed number automatically. Enter the converted number before Calculate.**
All internal calculations use SI. The submitted snapshot stores both display
units and SI inputs. Standard flow defaults to dry gas at 101.325 kPa absolute
and 60°F (15.55555556°C); change it to your contractual base if needed.

Use measured compressor shaft power. Electrical input needs independently
established motor/gear efficiencies. Speed is recorded for the matched operating
point; geometric displacement is supplied by the user at that speed, not scaled
automatically. Dynamic P/T must be total conditions or have negligible velocity
corrections independently established.

## Property model and restrictions

CoolProp Peng–Robinson is used with the stated composition. All unlisted binary
interactions are explicitly zero. You may enter fitted values as
`Methane,Ethane,0.01` in the interaction box. No ideal-gas fallback exists.

The gas root is imposed. The user must independently verify stable single-phase
gas over actual and reference paths. Property roots are restricted to 180–1500 K;
errors are reported rather than replaced with assumed numbers. A successful root
is not independent evidence that the selected EOS is accurate for that service.

The app does not implement GERG/AGA8, steam properties, automatic dew points,
critical-region validation, full multistage/intercooler balances, kinetic-energy
corrections, leakage reconciliation or automatic reference-condition conversion.
It does not claim full PTC 10-2022 compliance. Classical Schultz and the optional
constant-efficiency ODE calculation are explicitly distinguished.

## Cooling and liquid-ring limits

For dynamic compressors, nonzero entered heat rejection suppresses adiabatic
internal and Schultz efficiency and reports a heat-corrected reference-work
ratio. This is not a universal code correction.

For PD machines, shaft-reference ratios remain available; gas enthalpy rise is
reported separately. Cooled cylinder, oil-injected screw/vane and liquid-ring
applications require additional heat/side-stream balances for internal analysis.

Liquid-ring mode requires negligible gas/liquid vapour transfer and an agreed
active-displacement definition. It does **not** solve water-sealed saturated-gas
evaporation/condensation. Those cases require a coupled gas/liquid model outside
this version. Apparent capacity deficit is not a measurement of leakage alone.

## P–V card CSV

Headers: `end_id,pressure_Pa,volume_m3`. Use absolute pressure, actual reconstructed
volume and time-ordered rows. Supply one complete cycle per cylinder end, including
the repeated first point. Correct TDC phasing and geometry independently. The app
assumes one cycle/revolution and sums every provided end; do not upload multiple
cycles under one end_id or multiply again for double-acting operation.

`examples/analytic_pv_rectangle_NOT_PLANT.csv` is a mathematical integration
check (200 kW at 600 rpm), **not a realistic measured compression path**. The app
does not calculate valve-event losses or uniquely assign ring leakage from the
power residual. These require additional field data and analysis.

## OEM CSV and comparison

Required headers: `suction_flow_m3h,efficiency_pct`.
Optional: `head_kJkg,shaft_power_kW`.

Upload one matched curve, select its efficiency definition and confirm matching
gas, EOS, speed, controls, pressure ratio and boundary. Head must use the selected
polytropic/isentropic basis. Duplicate flows and extrapolation are rejected.
The app reports differences and provides a separate OEM comparison JSON download.
It does not issue an acceptance verdict or correct a mismatched curve.

`examples/synthetic_curve_NOT_OEM.csv` is invented teaching data only. It is not
a manufacturer's curve or a guarantee, and it does not validate any machine.

## Uncertainty

Optional uncertainty analysis propagates independent standard (one-sigma)
uncertainties for P1,T1,P2,T2 through the Schultz calculation. The displayed k=2
value is a **partial** expanded uncertainty in percentage points. Composition,
EOS, correlations, spatial profiles, heat/leak corrections and OEM curve
uncertainty are excluded. It is not a complete PTC 19.1 assessment.

## Tests

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

Tests cover all seven machine types, known thermodynamic results, reversible
limits, independent numerical-path agreement, unit/flow conversion, invalid
inputs, heat-transfer handling, analytic card integration, OEM interpolation,
extrapolation rejection, uncertainty and UI calculation/error paths.

## Sharing acceptance checklist

- [ ] Run tests in the deployment environment.
- [ ] Check each machine with the expected results in `examples/`.
- [ ] Check pressure absolute/gauge and temperature/flow conversions.
- [ ] Verify JSON, CSV and HTML downloads and their input snapshots.
- [ ] Validate with real plant data and an actual matched OEM curve.
- [ ] Independently approve the EOS/composition and uncertainty budget.
- [ ] Confirm actual phone/tablet/desktop usability.

## References

ASME PTC 10; ISO 5389; ISO 1217; API 617/618/619/672 as applicable; ASME PTC 19.1.
Exact clauses, tolerances and permitted test departures: **verify against the
standard** and contractual edition. No universal acceptance allowance is assumed.

- https://www.asme.org/codes-standards/find-codes-standards/axial-and-centrifugal-compressors
- https://www.iso.org/standard/39665.html
- https://www.iso.org/standard/44769.html
- https://www.api.org/products-and-services/standards/digital-catalog
- https://coolprop.org/coolprop/Cubics.html
- https://ccp-centrifugal-compressor-performance.readthedocs.io/en/v0.2.1/discussions/polytropic_methods.html

## Privacy

No LLM or external property API is called. Calculations and uploaded files are
processed in the running application. There is no database or cross-session
persistence. The hosting environment has its own access/logging policies. Do not
assume a public Streamlit deployment provides private authenticated access.

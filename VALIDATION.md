# Validation record — version 1.0.0

Date: 4 November 2026.

## Completed

- Automated suite: **54 passed**, including Streamlit AppTest interaction checks.
- All seven machine-type calculation and UI paths exercised.
- Natural-gas and air reference calculations reproduced from the earlier
  property-based worked examples (same PR model, not independent OEM data).
- Reversible-limit checks: isentropic and classical Schultz efficiencies reach 100%.
- Classical Schultz and independent constant-efficiency numerical-path cross-check.
- Pressure absolute/gauge, temperature and mass/actual/standard-flow conversions.
- Composition, interaction parameter, invalid input and nonfinite input checks.
- Explicit heat rejection suppresses adiabatic dynamic efficiencies.
- Out-of-range efficiency is flagged rather than clipped to an artificial value.
- P–V integration against a known analytic area; active-end summation and closure.
- OEM interpolation, duplicate-flow rejection and no-extrapolation checks.
- Partial P/T uncertainty benchmark: approximately ±0.612 percentage point (k=2).
- Python source compilation passed.
- Local server startup and HTTP health endpoint: **200 ok**.

## Release limits

No actual OEM map was provided. No plant acceptance test, two-phase property
validation, real moisture/evaporation model, full uncertainty budget or contractual
compliance certification is claimed. AppTest checks rendered app state and widget
interaction, not visual phone/tablet/browser layout or real file-upload/download
transport. The uploader's calculation parsers are tested separately.

Sample curves and measurements are explicitly synthetic and are not guarantees.
Public deployment and engineering approval with real plant/OEM data remain pending.

## Tested environment

Python 3.12; Streamlit 1.66.0; CoolProp 8.0.0; NumPy 2.5.4; pandas 3.1.0;
SciPy 1.17.0; pytest 9.2.0.

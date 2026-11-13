"""Run: streamlit run app.py"""
from dataclasses import asdict
from datetime import datetime, timezone
import html
import io
import json
import pandas as pd
import streamlit as st
from engineering import (VERSION, MACHINES, DYNAMIC, PRESETS, COMPONENTS, Case,
    calculate, parse_composition, parse_kij, pressure_pa, temperature_k,
    pv_power, compare_curve, uncertainty_eta)

st.set_page_config(page_title='Compressor Efficiency Tool', page_icon='⚙️', layout='wide')
st.markdown('''<style>
.block-container{max-width:1250px}
[data-testid="stMetric"]{background:light-dark(#f2f6fa,#172433);padding:16px;border-radius:10px}
.eyebrow{font-size:.8rem;letter-spacing:.12em;color:#428b9c;font-weight:700}
.app-branding{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem}
.app-brand{flex-shrink:0;font-size:.9rem;font-weight:700;letter-spacing:.08em}
</style>''',unsafe_allow_html=True)
st.markdown(
    '<div class="app-branding">'
    '<span class="eyebrow">ROTATING EQUIPMENT · FIELD PERFORMANCE</span>'
    '<span class="app-brand">MKU</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.title('Compressor Efficiency Tool')
st.caption(f'Version {VERSION} · Real-gas calculations · Standalone application · No API key required')

DEFAULTS={
 'Centrifugal':(30.,35.,60.,101.85,10.,1400.,6000.,.5),
 'Axial':(1.01325,25.,2.0265,100.85,50.,4000.,6000.,50.),
 'Reciprocating':(10.,35.,30.,190.,1.,240.,600.,.19),
 'Screw':(4.,35.,12.,190.,.5,140.,3000.,.22),
 'Rotary lobe':(1.01325,25.,1.519875,90.,.5,30.,1500.,.5),
 'Sliding vane':(1.01325,25.,4.053,175.,.25,55.,1500.,.25),
 'Liquid ring':(1.01325,30.,2.0265,35.,.2,35.,1500.,.25),
}
STANDARDS={
 'Centrifugal':'ASME PTC 10 / ISO 5389; API 617. API 672 only for applicable packaged centrifugal air units.',
 'Axial':'ASME PTC 10 / ISO 5389; API 617.',
 'Reciprocating':'API 618; ISO 1217 or the agreed performance procedure.',
 'Screw':'ISO 1217 / agreed OEM test; API 619 where within scope.',
 'Rotary lobe':'ISO 1217 / agreed OEM test; verify API 619 scope.',
 'Sliding vane':'ISO 1217 / agreed OEM test; API 619 where within scope.',
 'Liquid ring':'ISO 1217 / agreed OEM procedure; verify the procurement standard scope.',
}
with st.sidebar:
    st.header('Machine & gas')
    machine=st.selectbox('Compressor type',MACHINES,key='machine')
    preset_names=list(PRESETS)+['Custom composition']
    preferred=0 if machine in {'Centrifugal','Reciprocating','Screw'} else 1
    preset=st.selectbox('Gas preset',preset_names,index=preferred,key=f'preset_{machine}')
    st.caption('Presets are assumed teaching compositions. Replace with the sampled plant gas.')
    st.info(STANDARDS[machine])
    st.caption('Engineering screening and training. Not certified acceptance-test software. Exact requirements and tolerances: verify against the contractual standard edition.')
    if st.button('Clear saved result',key='clear'):
        for k in ['result','pv_rows','last_error']: st.session_state.pop(k,None)

d=DEFAULTS[machine]
st.info('Enter one compressor stage or casing. For intercooled trains, calculate each section separately and reconcile side flows and cooler duties.')
with st.form('case_form'):
    st.subheader('1 · Gas composition')
    c1,c2=st.columns([3,2])
    with c1:
        gas_text=st.text_area('Component,mole percent (one component per line)',
            value=PRESETS.get(preset,'Methane,100'),height=140,
            key=f'composition_{machine}_{preset}')
    with c2:
        st.caption('Supported names: '+', '.join(sorted(COMPONENTS)))
        kij_text=st.text_area('Optional PR interactions: Component1,Component2,kij',
            value='',height=90,key=f'kij_{machine}',help='All unlisted binary interactions are explicitly zero. Use OEM-agreed fitted values for plant work.')
    st.subheader('2 · Measured operating point')
    a,b,c=st.columns(3)
    with a:
        pressure_unit=st.selectbox('Pressure unit',['bar(a)','kPa(a)','MPa(a)','psia','bar(g)','psig'],key=f'pu_{machine}',
            help='Changing units reinterprets the entered numbers; convert your values before Calculate.')
        p1=st.number_input('Suction pressure',value=d[0],format='%.6f',key=f'p1_{machine}')
        p2=st.number_input('Discharge pressure',value=d[2],format='%.6f',key=f'p2_{machine}')
        ambient=st.number_input('Local atmospheric pressure (kPa absolute)',min_value=.001,value=101.325,format='%.3f',key=f'ambient_{machine}')
    with b:
        temp_unit=st.selectbox('Temperature unit',['°C','K','°F'],key=f'tu_{machine}',
            help='Changing units reinterprets the entered temperatures. Enter the converted values.')
        T1=st.number_input('Suction temperature',value=d[1],format='%.3f',key=f'T1_{machine}')
        T2=st.number_input('Discharge temperature',value=d[3],format='%.3f',key=f'T2_{machine}')
        speed=st.number_input('Shaft speed (rpm)',min_value=.01,value=d[6],key=f'N_{machine}')
    with c:
        flow_unit=st.selectbox('Flow unit',['kg/s','kg/h','Actual m³/h','Standard m³/h','MMSCFD'],key=f'fu_{machine}',
            help='Actual volume is at suction. Standard volume uses the base entered below. Changing unit reinterprets the number.')
        flow=st.number_input('Net gas flow',min_value=.000001,value=d[4],format='%.6f',key=f'flow_{machine}')
        power=st.number_input('Compressor shaft input (kW)',min_value=.000001,value=d[5],key=f'power_{machine}',
            help='Enter measured compressor shaft power. Motor terminal power requires measured/agreed motor and gear efficiencies first.')
        qdisp=st.number_input('Geometric displacement (actual m³/s)',min_value=.000001,value=d[7],format='%.6f',
            disabled=machine in DYNAMIC,key=f'qd_{machine}',help='OEM geometric displacement rate at entered speed; not measured delivered flow. For liquid ring, use an agreed active-displacement definition.')
    with st.expander('Standard-flow base and heat transfer'):
        a,b,c=st.columns(3)
        std_p=a.number_input('Standard pressure (kPa absolute)',min_value=.001,value=101.325,key=f'sp_{machine}')
        std_t=b.number_input('Standard temperature (°C)',min_value=-93.,max_value=1226.,value=15.55555556,format='%.8f',key=f'st_{machine}')
        heat=c.number_input('Heat rejected from gas boundary (kW)',min_value=0.,value=0.,key=f'heat_{machine}',
            help='Dynamic: nonzero heat disables adiabatic Schultz/internal efficiency. PD: gas/oil/liquid duties require a full balance; shaft-reference metrics remain available.')
        st.caption('Standard defaults: 101.325 kPa and 60°F, dry gas. State the same base when comparing MMSCFD or specific energy.')
    phase=st.checkbox('I independently verified stable, single-phase gas over the relevant actual and reference paths.',key=f'phase_{machine}')
    st.caption('PR gas-root calculations do not establish phase stability. No two-phase, wet-gas or automatic dew-point analysis is provided. Dynamic P/T must be total states, or velocity corrections must be independently shown negligible.')
    ring=False
    if machine=='Liquid ring':
        ring=st.checkbox('Negligible gas/liquid vapour transfer is justified, and active displacement is defined by the OEM.',key='ring_confirmed')
        st.warning('Water-sealed saturated gas with evaporation/condensation requires a coupled wet-gas/liquid balance outside this version.')
    numeric=st.checkbox('Also calculate a numerical constant-efficiency polytropic cross-check',value=False,
        disabled=machine not in DYNAMIC,key=f'numeric_{machine}')
    submitted=st.form_submit_button('Calculate performance',type='primary')

if submitted:
    st.session_state.pop('result',None)
    st.session_state.pop('pv_rows',None)
    try:
        composition=parse_composition(gas_text); kij=parse_kij(kij_text,composition)
        case=Case(machine=machine,p1=pressure_pa(p1,pressure_unit,ambient),T1=temperature_k(T1,temp_unit),
            p2=pressure_pa(p2,pressure_unit,ambient),T2=temperature_k(T2,temp_unit),flow=flow,flow_unit=flow_unit,
            power_kW=power,speed_rpm=speed,displacement_m3s=qdisp,std_p=std_p*1000,std_T=std_t+273.15,
            heat_out_kW=heat,phase_confirmed=phase,ring_confirmed=ring,numerical_path=numeric)
        with st.spinner('Calculating real-gas performance…'):
            result=calculate(case,composition,kij)
        result['calculated_UTC']=datetime.now(timezone.utc).isoformat()
        result['input_display']={'pressure_unit':pressure_unit,'temperature_unit':temp_unit,
            'suction_pressure':p1,'discharge_pressure':p2,'suction_temperature':T1,
            'discharge_temperature':T2,'atmospheric_pressure_kPa':ambient}
        st.session_state['result']=result
        st.session_state.pop('last_error',None)
    except Exception as exc:
        st.session_state['last_error']=str(exc)

if 'last_error' in st.session_state: st.error(st.session_state['last_error'])

tabs=st.tabs(['Results','Calculation steps','OEM comparison','Field checklist','Methods & limits'])
r=st.session_state.get('result')
if r and r['case']['machine']!=machine: r=None

def metric_table(metrics):
    return pd.DataFrame([{'Parameter':k,'Value':v} for k,v in metrics.items()])

with tabs[0]:
    if not r:
        st.subheader('Ready for your operating point')
        st.write('Select a compressor, review the assumed inputs, confirm phase verification and calculate. Result values are never generated from an unsubmitted form.')
    else:
        m=r['metrics']; snap=r['case']; report=json.loads(json.dumps(r))
        st.caption('Saved calculation snapshot · '+r['calculated_UTC']+' · Edit inputs and press Calculate to update.')
        a,b,c,dcol=st.columns(4)
        a.metric('Isentropic / shaft reference',f"{m['eta_s_shaft_pct']:.2f}%")
        if 'eta_p_pct' in m: b.metric('Polytropic · Schultz',f"{m['eta_p_pct']:.2f}%")
        elif 'eta_v_pct' in m: b.metric('Volumetric efficiency',f"{m['eta_v_pct']:.2f}%")
        else: b.metric('Heat-corrected reference',f"{m['eta_s_heat_corrected_reference_pct']:.2f}%")
        c.metric('Isentropic head',f"{m['Hs_kJkg']:.3f} kJ/kg")
        dcol.metric('Shaft input',f"{snap['power_kW']:,.2f} kW")
        for warning in r['warnings']: st.warning(warning)
        st.dataframe(metric_table(m),hide_index=True,use_container_width=True)
        with st.expander('Submitted input snapshot and property states'):
            st.json(r)
        if machine=='Reciprocating':
            st.subheader('P–V card analysis · optional')
            st.caption('One closed cycle per revolution for each active cylinder end. Rows must be in time order; repeat the first point at closure. Absolute Pa and m³ only. Valve/ring loss attribution is not inferred from the residual.')
            card=st.file_uploader('Upload P–V CSV',type=['csv'],key='pv_upload')
            if card:
                try:
                    rows=pv_power(card.getvalue().decode('utf-8-sig'),snap['speed_rpm'])
                    indicated=sum(row['indicated_power_kW'] for row in rows)
                    st.dataframe(pd.DataFrame(rows),hide_index=True)
                    st.write(f"Indicated power: **{indicated:.3f} kW** · Indicated reference efficiency: **{100*m['isentropic_power_kW']/indicated:.2f}%** · Indicated/shaft ratio: **{100*indicated/snap['power_kW']:.2f}%**")
                    report['pv_cards']=rows
                    if indicated>snap['power_kW']: st.warning('Indicated power exceeds shaft input: check phasing, closure, units and power boundary.')
                except Exception as exc: st.error(f'P–V analysis: {exc}')
        if 'eta_p_pct' in m:
            with st.expander('Partial P/T uncertainty · optional'):
                st.caption('Enter independent one-sigma standard uncertainties. This is a partial budget; k=2 coverage must be justified. No acceptance decision is made.')
                a,b=st.columns(2)
                up1=a.number_input('u(P1), Pa',min_value=0.,value=snap['p1']*.0005,key='up1')
                up2=b.number_input('u(P2), Pa',min_value=0.,value=snap['p2']*.0005,key='up2')
                ut1=a.number_input('u(T1), K',min_value=0.,value=.15,key='ut1')
                ut2=b.number_input('u(T2), K',min_value=0.,value=.15,key='ut2')
                if st.button('Evaluate partial uncertainty'):
                    try:
                        kij={tuple(k.split(',')):v for k,v in r['kij'].items()}
                        unc=uncertainty_eta(Case(**snap),r['composition_mole_fraction'],kij,[up1,ut1,up2,ut2])
                        st.session_state['uncertainty']={'time':r['calculated_UTC'],'result':unc,
                            'standard_u_P1_T1_P2_T2':[up1,ut1,up2,ut2]}
                    except Exception as exc: st.error(str(exc))
                u=st.session_state.get('uncertainty',{})
                if u.get('time')==r['calculated_UTC']:
                    st.write(f"Expanded partial uncertainty: **±{u['result']['expanded_k2_pp']:.3f} percentage point** (k=2).")
                    st.caption(u['result']['scope']); report['uncertainty']=u
        st.subheader('Download calculation record')
        a,b,c=st.columns(3)
        a.download_button('JSON · inputs & results',json.dumps(report,indent=2,allow_nan=False),
            file_name='compressor_performance.json',mime='application/json')
        flat={**m,'machine':machine,'speed_rpm':snap['speed_rpm'],'shaft_power_kW':snap['power_kW'],
              'standard_pressure_Pa':snap['std_p'],'standard_temperature_K':snap['std_T'],
              'composition':json.dumps(r['composition_mole_fraction']),
              'property_model':r['property_model'],'calculated_UTC':r['calculated_UTC']}
        b.download_button('CSV · result summary',pd.DataFrame([flat]).to_csv(index=False),
            file_name='compressor_summary.csv',mime='text/csv')
        body='<h1>Compressor Efficiency Tool</h1><p>Calculation snapshot — '+html.escape(machine)+'</p>'
        body+='<p>Field screening/training; not a certified acceptance test.</p>'
        body+='<h2>Metrics</h2>'+metric_table(m).to_html(index=False,escape=True)
        body+='<h2>Inputs and assumptions</h2><pre>'+html.escape(json.dumps(report,indent=2))+'</pre>'
        c.download_button('HTML · printable report','<!doctype html><html><meta charset="utf-8"><title>Compressor report</title><body>'+body+'</body></html>',
            file_name='compressor_report.html',mime='text/html')

with tabs[1]:
    st.subheader('Trace the calculation')
    st.write('1. Convert pressure to Pa absolute and temperature to kelvin. 2. Evaluate PR inlet/outlet properties from the stated mole composition. 3. Solve the isentropic discharge at measured discharge pressure and inlet entropy. 4. Convert the measured flow to kg/s. 5. Calculate head, power and the applicable efficiency.')
    st.latex(r'H_s=h_{2s}-h_1,\quad s_{2s}=s_1,\quad \eta_{s,shaft}=\frac{\dot m H_s}{P_{shaft}}')
    st.latex(r'\eta_v=\frac{\dot m v_1}{Q_{disp}},\quad SEC=\frac{P_{shaft}}{3600\dot m}')
    if r:
        m=r['metrics']; a=r['inlet']; b=r['outlet']; bs=r['isentropic_outlet']
        st.write(f"Inlet h = {a['h_Jkg']/1000:.4f} kJ/kg; actual outlet h = {b['h_Jkg']/1000:.4f} kJ/kg; isentropic outlet h = {bs['h_Jkg']/1000:.4f} kJ/kg.")
        st.write(f"Isentropic power = {m['mass_flow_kgs']:.5f} × {m['Hs_kJkg']:.5f} = {m['isentropic_power_kW']:.4f} kW.")
        if 'eta_p_pct' in m:
            st.latex(r'n=\frac{\ln(p_2/p_1)}{\ln(v_1/v_2)},\quad H_p=f\frac{n}{n-1}(p_2v_2-p_1v_1),\quad \eta_p=\frac{H_p}{h_2-h_1}')
            st.write(f"n = {m['n']:.6f}; ns = {m['ns']:.6f}; Schultz f = {m['Schultz_f']:.7f}; Hp = {m['Hp_kJkg']:.4f} kJ/kg.")
        if 'eta_v_pct' in m:
            st.write(f"Suction flow = {m['suction_flow_m3h']/3600:.6f} m³/s; displacement = {r['case']['displacement_m3s']:.6f} m³/s.")

with tabs[2]:
    st.subheader('OEM comparison · matched conditions only')
    st.write('Supply a single OEM curve at the matched gas composition, property method, speed, control position, pressure ratio and power boundary. This version interpolates within the supplied flow range; it does not correct or extrapolate the map.')
    if not r: st.info('Calculate an operating point first.')
    else:
        basis=st.selectbox('OEM efficiency definition',['Polytropic · Schultz','Isentropic · internal','Isentropic · shaft reference','Volumetric'])
        match=st.checkbox('I verified this OEM curve matches the submitted operating conditions and efficiency definition.',key='oem_match')
        upload=st.file_uploader('OEM curve CSV',type=['csv'],key='oem_upload')
        st.caption('Required: suction_flow_m3h,efficiency_pct. Optional: head_kJkg,shaft_power_kW. Head must match the selected polytropic/isentropic definition. Flow is actual suction m³/h.')
        if upload and match:
            try:
                expected,rows=compare_curve(upload.getvalue().decode('utf-8-sig'),r['metrics']['suction_flow_m3h'])
                keys={'Polytropic · Schultz':'eta_p_pct','Isentropic · internal':'eta_s_internal_pct',
                      'Isentropic · shaft reference':'eta_s_shaft_pct','Volumetric':'eta_v_pct'}
                key=keys[basis]
                if key not in r['metrics']: raise ValueError('Selected efficiency definition is not available for this calculation.')
                measured=r['metrics'][key]; ref=expected['efficiency_pct']
                comp=[dict(Parameter=basis,Measured=measured,OEM=ref,Difference=measured-ref,Unit='percentage points')]
                if 'head_kJkg' in expected:
                    if basis=='Volumetric': raise ValueError('A volumetric-efficiency curve does not establish a head definition; omit head_kJkg.')
                    measured_head=r['metrics']['Hp_kJkg' if basis=='Polytropic · Schultz' else 'Hs_kJkg']
                    comp.append(dict(Parameter='Head',Measured=measured_head,OEM=expected['head_kJkg'],Difference=measured_head-expected['head_kJkg'],Unit='kJ/kg'))
                if 'shaft_power_kW' in expected:
                    p=r['case']['power_kW']; refp=expected['shaft_power_kW']
                    comp.append(dict(Parameter='Shaft input',Measured=p,OEM=refp,Difference=p-refp,Unit='kW'))
                st.dataframe(pd.DataFrame(comp),hide_index=True)
                st.line_chart(pd.DataFrame(rows).set_index('suction_flow_m3h')[['efficiency_pct']],x_label='Actual suction flow (m³/h)',y_label='OEM efficiency (%)')
                st.caption(f"Measured point: {r['metrics']['suction_flow_m3h']:.2f} m³/h at {measured:.2f}%. Differences are observations, not acceptance decisions. Combine measurement, correction and OEM curve uncertainty before assessing degradation.")
                st.download_button('Download OEM comparison',json.dumps({'basis':basis,'matched_conditions_confirmed':True,'calculation':r,'OEM_curve':rows,'comparison':comp},indent=2),file_name='OEM_comparison.json',mime='application/json')
            except Exception as exc: st.error(str(exc))
        elif upload: st.info('Confirm the matched conditions before comparing.')

with tabs[3]:
    st.subheader('Field performance checklist')
    for title,items in {
      'Before testing':['Agree code edition, boundary, properties and guarantee basis.','Obtain OEM maps and correction curves.','Calibrate P/T, flow, torque/electrical power and speed.','Confirm phase stability and identify all seal/recycle/bleed flows.'],
      'During testing':['Stabilize speed, load, controls and cooling.','Record synchronized P/T, flow, composition and shaft power.','Measure at agreed total-state planes; assess spatial profiles.','For PD machines, record unloaders, clearances, oil and seal-liquid conditions.'],
      'After testing':['Close mass and energy balances.','Calculate pre/post-test uncertainty, including EOS and composition.','Compare at matched OEM conditions and trend repeated observations.','Apply contractual tolerance separately from uncertainty.']}.items():
        st.markdown('**'+title+'**')
        for i,item in enumerate(items): st.checkbox(item,key=f'check_{title}_{i}')

with tabs[4]:
    st.subheader('Methods, scope and interpretation')
    st.markdown('''
- **Gas model:** CoolProp Peng–Robinson; specified mole fractions and explicit zero defaults for unspecified binary interactions. No automatic ideal-gas substitution.
- **Dynamic compressors:** classical endpoint Schultz correction. It is not a certified implementation of PTC 10-2022. The optional constant-efficiency numerical path is an independent cross-check, not a claim of code compliance.
- **PD compressors:** real-gas isentropic/isothermal reference power, volumetric efficiency, capacity deficit and specific energy. Displacement must correspond to the entered speed.
- **Cooling:** gas enthalpy rise alone is not shaft power for oil-injected screws, cooled cylinders or liquid-ring compressors. This tool does not solve a complete oil/liquid energy balance.
- **P–V cards:** one calibrated, closed, time-ordered cycle per active end, one cycle/revolution. Correct TDC phase and cylinder geometry independently. No automatic valve/ring loss attribution.
- **Limits:** stable single-phase dry gas; 180–1500 K property roots. No automatic dew-point, kinetic-energy, multistage/intercooler, leakage or real-gas OEM-condition correction. No fabricated acceptance tolerance.
- **Liquid ring:** reference screening for negligible vapour transfer only. Water-sealed wet-gas cases require a coupled balance outside this version.
- **Uncertainty:** optional independent P/T-only sensitivity of Schultz efficiency. Not a complete PTC 19.1 budget.
- **Privacy:** calculations run in the app process, with no LLM or paid API. Uploaded files are read for the active session; no database or cloud persistence is implemented. Hosting-provider logs and access policies are separate.
''')
    st.markdown('**Diagnostic prompts**')
    st.dataframe(pd.DataFrame([
      ['Dynamic head/efficiency down','Fouling, erosion, clearance growth; first match speed/flow/gas.'],
      ['PD capacity down at matched conditions','Valves/rings/vanes/clearances, heating, unloaders or slide position.'],
      ['Power up without corresponding useful head','Recirculation, pressure losses, oil/separator restriction or mechanical losses.'],
      ['Liquid-ring capacity down','Seal liquid too hot/low flow, changed vapour loading, scaling, wear.'],
      ['Sudden implausible efficiency','Instrument drift, gauge/absolute confusion, flow basis, composition or power boundary.']
    ],columns=['Observed trend','Investigate']),hide_index=True,use_container_width=True)
    st.markdown('**Primary references**')
    for title,url in [
      ('ASME PTC 10','https://www.asme.org/codes-standards/find-codes-standards/axial-and-centrifugal-compressors'),
      ('ISO 5389','https://www.iso.org/standard/39665.html'),
      ('ISO 1217','https://www.iso.org/standard/44769.html'),
      ('API standards','https://www.api.org/products-and-services/standards/digital-catalog'),
      ('CoolProp PR model','https://coolprop.org/coolprop/Cubics.html'),
      ('Schultz method documentation','https://ccp-centrifugal-compressor-performance.readthedocs.io/en/v0.2.1/discussions/polytropic_methods.html')]:
        st.markdown(f'[{title}]({url})')

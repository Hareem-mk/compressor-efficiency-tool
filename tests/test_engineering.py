from dataclasses import replace
import math
import pytest
from engineering import (Case,Gas,calculate,parse_composition,parse_kij,PRESETS,
    pressure_pa,temperature_k,pv_power,compare_curve,uncertainty_eta)

NG=parse_composition(PRESETS['Natural gas (assumed example)'])
AIR=parse_composition(PRESETS['Dry air (N2/O2 example)'])

def base(): return Case(phase_confirmed=True)

def test_centrifugal_reference_and_energy():
    r=calculate(base(),NG); m=r['metrics']
    assert m['Hs_kJkg']==pytest.approx(101.521835,rel=2e-6)
    assert m['eta_p_pct']==pytest.approx(76.015369,rel=2e-6)
    assert m['eta_s_shaft_pct']==pytest.approx(72.515597,rel=2e-6)
    assert m['gas_enthalpy_power_kW']+m['adiabatic_power_residual_kW']==pytest.approx(1400)

def test_reversible_limit():
    g=Gas(NG); a=g.pt(3e6,308.15); bs=g.root(6e6,'s_JkgK',a['s_JkgK'])
    c=replace(base(),T2=bs['T_K'],power_kW=10*(bs['h_Jkg']-a['h_Jkg'])/1000)
    m=calculate(c,NG)['metrics']
    assert m['eta_s_internal_pct']==pytest.approx(100,abs=1e-7)
    assert m['eta_p_pct']==pytest.approx(100,abs=1e-7)
    assert m['eta_s_shaft_pct']==pytest.approx(100,abs=1e-7)

def test_numerical_path_agreement():
    m=calculate(replace(base(),numerical_path=True),NG)['metrics']
    assert abs(m['eta_p_pct']-m['numerical_eta_p_pct'])<.1

@pytest.mark.parametrize('machine,p1,T1,p2,T2,m,P,Q,eta',[
    ('Axial',101325,298.15,202650,374,50,4000,50,82.2764286),
    ('Reciprocating',1e6,308.15,3e6,463.15,1,240,.19,73.0638876),
    ('Screw',4e5,308.15,1.2e6,463.15,.5,140,.22,63.4473367),
    ('Rotary lobe',101325,298.15,151987.5,363.15,.5,30,.5,61.5257972),
    ('Sliding vane',101325,298.15,405300,448.15,.25,55,.25,66.3638351),
    ('Liquid ring',101325,303.15,202650,308.15,.2,35,.25,38.2434507),
])
def test_machine_cases(machine,p1,T1,p2,T2,m,P,Q,eta):
    c=Case(machine=machine,p1=p1,T1=T1,p2=p2,T2=T2,flow=m,power_kW=P,
           displacement_m3s=Q,phase_confirmed=True,ring_confirmed=True)
    gas=NG if machine in {'Reciprocating','Screw'} else AIR
    r=calculate(c,gas)
    assert r['metrics']['eta_s_shaft_pct']==pytest.approx(eta,rel=2e-6)
    if machine!='Axial': assert 0<r['metrics']['eta_v_pct']<100

@pytest.mark.parametrize('unit,value,expected',[
    ('bar(a)',30,3e6),('kPa(a)',3000,3e6),('MPa(a)',3,3e6),
    ('psia',435.1132132,3e6),('bar(g)',28.98675,3e6),('psig',0,101325)])
def test_pressure_units(unit,value,expected):
    assert pressure_pa(value,unit)==pytest.approx(expected,rel=1e-8)

@pytest.mark.parametrize('unit,value',[('°C',35),('K',308.15),('°F',95)])
def test_temperature_units(unit,value): assert temperature_k(value,unit)==pytest.approx(308.15)

@pytest.mark.parametrize('unit',['kg/h','Actual m³/h','Standard m³/h','MMSCFD'])
def test_flow_conversion_round_trip(unit):
    c=base(); r=calculate(c,NG); m=r['metrics']
    amount={'kg/h':36000,'Actual m³/h':m['suction_flow_m3h'],
            'Standard m³/h':m['standard_flow_m3h'],'MMSCFD':m['standard_flow_MMSCFD']}[unit]
    other=calculate(replace(c,flow=amount,flow_unit=unit),NG)
    assert other['metrics']['mass_flow_kgs']==pytest.approx(10)

@pytest.mark.parametrize('text',['Methane,90','Methane,100\nMethane,1','Bogus,100','Methane,nan','Methane,-2\nNitrogen,102'])
def test_bad_composition(text):
    with pytest.raises(ValueError): parse_composition(text)

def test_kij_validation_and_application():
    k=parse_kij('Methane,Ethane,0.01',NG)
    assert k[('Ethane','Methane')]==.01
    assert calculate(base(),NG,k)['kij']=={'Ethane,Methane':.01}
    with pytest.raises(ValueError): parse_kij('Methane,Oxygen,0.1',NG)

@pytest.mark.parametrize('change',[
    {'p1':0},{'p2':2e6},{'T1':100},{'power_kW':0},{'flow':float('nan')},
    {'phase_confirmed':False},{'speed_rpm':0},{'T2':310},
    {'machine':'Liquid ring','ring_confirmed':False},
])
def test_invalid_inputs(change):
    with pytest.raises(ValueError): calculate(replace(base(),**change),NG)

def test_heat_rejection_suppresses_adiabatic_metrics():
    r=calculate(replace(base(),heat_out_kW=50),NG)
    assert 'eta_p_pct' not in r['metrics']
    assert 'eta_s_internal_pct' not in r['metrics']
    assert r['metrics']['heat_corrected_fluid_work_kW']==pytest.approx(1418.9191557)

def test_unphysical_efficiency_is_flagged_not_clipped():
    r=calculate(replace(base(),power_kW=500),NG)
    assert r['metrics']['eta_s_shaft_pct']>100
    assert any('outside 0–100%' in w for w in r['warnings'])

CARD='end_id,pressure_Pa,volume_m3\nA,3000000,.01\nA,1000000,.01\nA,1000000,.02\nA,3000000,.02\nA,3000000,.01\n'
def test_pv_known_closed_card():
    r=pv_power(CARD,600)
    assert r[0]['cycle_work_J']==pytest.approx(20000)
    assert r[0]['indicated_power_kW']==pytest.approx(200)

def test_pv_sums_separate_ends():
    r=pv_power(CARD+CARD.split('\n',1)[1].replace('A,','B,'),600)
    assert sum(x['indicated_power_kW'] for x in r)==pytest.approx(400)

@pytest.mark.parametrize('card',[
    'foo,bar\n1,2',CARD.replace('A,3000000,.01\n','',1),
    CARD.replace('3000000','-1'),CARD.replace('.02','nan'),
])
def test_bad_pv_card(card):
    with pytest.raises(ValueError): pv_power(card,600)

CURVE='suction_flow_m3h,efficiency_pct,head_kJkg,shaft_power_kW\n1000,80,100,1300\n2000,82,110,1500\n'
def test_oem_interpolation():
    e,rows=compare_curve(CURVE,1500)
    assert e=={'efficiency_pct':81.,'head_kJkg':105.,'shaft_power_kW':1400.}

@pytest.mark.parametrize('text,flow',[(CURVE,999),(CURVE.replace('2000','1000'),1000),
    (CURVE.replace(',82,',',182,'),1500),(CURVE.replace('2000','nan'),1500)])
def test_oem_invalid_or_extrapolation(text,flow):
    with pytest.raises(ValueError): compare_curve(text,flow)

def test_uncertainty_reference():
    r=uncertainty_eta(base(),NG,{},[1500,.15,3000,.15])
    assert r['expanded_k2_pp']==pytest.approx(.612028,rel=2e-5)

"""Compressor field-screening calculations. SI internally; not certified code software."""
from __future__ import annotations
import csv
import io
import math
from dataclasses import asdict, dataclass
import numpy as np
from scipy.integrate import quad, solve_ivp
from scipy.optimize import brentq
import CoolProp.CoolProp as CP

VERSION = '1.0.0'
MACHINES = ['Centrifugal', 'Axial', 'Reciprocating', 'Screw', 'Rotary lobe',
            'Sliding vane', 'Liquid ring']
DYNAMIC = {'Centrifugal', 'Axial'}
COMPONENTS = {'Methane', 'Ethane', 'Propane', 'Nitrogen', 'Oxygen',
              'CarbonDioxide', 'Hydrogen', 'Argon', 'n-Butane', 'IsoButane'}
PRESETS = {
    'Natural gas (assumed example)': 'Methane,90\nEthane,6\nPropane,2\nNitrogen,2',
    'Dry air (N2/O2 example)': 'Nitrogen,79\nOxygen,21',
    'Nitrogen': 'Nitrogen,100',
    'Methane': 'Methane,100',
}


def positive(value, name, allow_zero=False):
    value = float(value)
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        raise ValueError(f'{name} must be finite and {"nonnegative" if allow_zero else "positive"}.')
    return value


def pressure_pa(value, unit, ambient_kPa=101.325):
    positive(ambient_kPa, 'Atmospheric pressure')
    scales = {'bar(a)': 1e5, 'kPa(a)': 1000., 'MPa(a)': 1e6, 'psia': 6894.757293168,
              'bar(g)': 1e5, 'psig': 6894.757293168}
    if unit not in scales: raise ValueError('Unknown pressure unit.')
    p = float(value)*scales[unit]
    if unit in {'bar(g)', 'psig'}: p += ambient_kPa*1000
    return positive(p, 'Absolute pressure')


def temperature_k(value, unit):
    if unit not in {'°C', 'K', '°F'}: raise ValueError('Unknown temperature unit.')
    T = float(value)+273.15 if unit == '°C' else (
        (float(value)-32)*5/9+273.15 if unit == '°F' else float(value))
    return positive(T, 'Absolute temperature')


def parse_composition(text):
    rows = list(csv.reader(io.StringIO(text.strip())))
    comp = {}
    for row in rows:
        if not row or all(not cell.strip() for cell in row): continue
        if len(row) != 2: raise ValueError('Composition needs Component,mole_percent on every row.')
        name = row[0].strip()
        if name not in COMPONENTS: raise ValueError(f'Unsupported component: {name}.')
        if name in comp: raise ValueError(f'Duplicate component: {name}.')
        comp[name] = positive(row[1], f'{name} mole percent')
    if not comp or abs(sum(comp.values())-100) > 1e-6:
        raise ValueError('Mole percentages must total exactly 100 (within 0.000001).')
    return {k: v/100 for k,v in comp.items()}


def parse_kij(text, composition):
    pairs = {}
    for row in csv.reader(io.StringIO(text.strip())):
        if not row or all(not x.strip() for x in row): continue
        if len(row) != 3: raise ValueError('Interaction rows need Component1,Component2,kij.')
        a,b = row[0].strip(),row[1].strip()
        if a == b or a not in composition or b not in composition:
            raise ValueError('Interaction pairs need two different selected components.')
        key = tuple(sorted((a,b)))
        if key in pairs: raise ValueError('Duplicate interaction pair.')
        v = float(row[2])
        if not math.isfinite(v): raise ValueError('Interaction parameter must be finite.')
        pairs[key] = v
    return pairs


class Gas:
    def __init__(self, composition, kij=None):
        if not composition or any(k not in COMPONENTS for k in composition):
            raise ValueError('Select supported gas components.')
        if any(not math.isfinite(v) or v <= 0 for v in composition.values()) or abs(sum(composition.values())-1)>1e-8:
            raise ValueError('Gas mole fractions must be positive and total one.')
        self.composition = composition
        names = list(composition)
        self.state = CP.AbstractState('PR', '&'.join(names))
        self.state.set_mole_fractions(list(composition.values()))
        for i in range(len(names)):
            for j in range(i+1,len(names)):
                key=tuple(sorted((names[i],names[j])))
                self.state.set_binary_interaction_double(i,j,'kij',(kij or {}).get(key,0.))
        # User must independently establish stable gas phase. Never silently use ideal gas.
        self.state.specify_phase(CP.iphase_gas)

    def pt(self,p,T):
        positive(p,'Pressure'); positive(T,'Temperature')
        if not 180 <= T <= 1500: raise ValueError('Tool temperature range is 180–1500 K.')
        self.state.update(CP.PT_INPUTS,p,T)
        rho,cp = self.state.rhomass(), self.state.cpmass()
        if rho<=0 or cp<=0: raise ValueError('Nonphysical gas-root state; check phase/model.')
        d={'p_Pa':p,'T_K':T,'h_Jkg':self.state.hmass(), 's_JkgK':self.state.smass(),
           'v_m3kg':1/rho,'rho_kgm3':rho,'Z':self.state.compressibility_factor()}
        if not all(math.isfinite(v) for v in d.values()): raise ValueError('Nonfinite property result.')
        return d

    def root(self,p,key,target,lo=180.,hi=1500.):
        try:
            T=brentq(lambda t:self.pt(p,t)[key]-target,lo,hi,xtol=1e-8)
        except ValueError as exc:
            raise ValueError('No property root in 180–1500 K. Check phase, units and gas model.') from exc
        return self.pt(p,T)


@dataclass
class Case:
    machine: str = 'Centrifugal'
    p1: float = 3e6
    T1: float = 308.15
    p2: float = 6e6
    T2: float = 375.
    flow: float = 10.
    flow_unit: str = 'kg/s'
    power_kW: float = 1400.
    speed_rpm: float = 6000.
    displacement_m3s: float = .5
    std_p: float = 101325.
    std_T: float = 288.70555556
    heat_out_kW: float = 0.
    phase_confirmed: bool = False
    ring_confirmed: bool = False
    numerical_path: bool = False


def flow_mass(g,case,inlet):
    f=positive(case.flow,'Flow')
    if case.flow_unit=='kg/s': return f
    if case.flow_unit=='kg/h': return f/3600
    if case.flow_unit=='Actual m³/h': return f/3600/inlet['v_m3kg']
    vs=g.pt(case.std_p,case.std_T)['v_m3kg']
    if case.flow_unit=='Standard m³/h': return f/3600/vs
    if case.flow_unit=='MMSCFD': return f*1e6*.028316846592/86400/vs
    raise ValueError('Unknown flow unit.')


def endpoint_head(n,a,b,p2):
    """Stable limiting expression for n approaching one."""
    e=(n-1)/n
    if abs(e)<1e-7: return a['p_Pa']*a['v_m3kg']*math.log(p2/a['p_Pa'])
    return (p2*b['v_m3kg']-a['p_Pa']*a['v_m3kg'])/e


def schultz(g,p1,T1,p2,T2):
    a,b=g.pt(p1,T1),g.pt(p2,T2)
    bs=g.root(p2,'s_JkgK',a['s_JkgK'])
    lv=math.log(a['v_m3kg']/b['v_m3kg'])
    lvs=math.log(a['v_m3kg']/bs['v_m3kg'])
    if abs(lv)<1e-10 or abs(lvs)<1e-10: raise ValueError('Degenerate endpoint volume ratio.')
    n,ns=math.log(p2/p1)/lv,math.log(p2/p1)/lvs
    dh=b['h_Jkg']-a['h_Jkg']
    if dh<=0: raise ValueError('Adiabatic dynamic analysis requires positive enthalpy rise.')
    f=(bs['h_Jkg']-a['h_Jkg'])/endpoint_head(ns,a,bs,p2)
    head=f*endpoint_head(n,a,b,p2)
    return dict(n=n,ns=ns,Schultz_f=f,Hp_kJkg=head/1000,eta_p_pct=100*head/dh)


def numerical_polytropic(g,p1,T1,p2,T2):
    a,b=g.pt(p1,T1),g.pt(p2,T2)
    def final(eta):
        def rhs(p,y): return [g.root(p,'h_Jkg',float(y[0]))['v_m3kg']/eta]
        sol=solve_ivp(rhs,(p1,p2),[a['h_Jkg']],rtol=2e-7,atol=.001,max_step=(p2-p1)/40)
        if not sol.success: raise ValueError('Numerical path failed to converge.')
        return sol.y[0,-1]
    eta=brentq(lambda eta:final(eta)-b['h_Jkg'],.25,1.05,xtol=1e-7)
    return dict(numerical_eta_p_pct=eta*100,
                numerical_Hp_kJkg=eta*(b['h_Jkg']-a['h_Jkg'])/1000)


def calculate(case,composition,kij=None):
    if case.machine not in MACHINES: raise ValueError('Unknown compressor type.')
    if not case.phase_confirmed:
        raise ValueError('Confirm independent single-phase gas verification before calculating.')
    if case.machine=='Liquid ring' and not case.ring_confirmed:
        raise ValueError('Liquid-ring mode requires negligible gas/liquid mass transfer and an agreed displacement definition.')
    for name in ['p1','p2','T1','T2','power_kW','speed_rpm','std_p','std_T']:
        positive(getattr(case,name),name)
    positive(case.heat_out_kW,'Heat rejected',allow_zero=True)
    if case.p2<=case.p1: raise ValueError('Discharge absolute pressure must exceed suction pressure.')
    if case.machine not in DYNAMIC: positive(case.displacement_m3s,'Geometric displacement')
    g=Gas(composition,kij)
    a=g.pt(case.p1,case.T1); b=g.pt(case.p2,case.T2)
    bs=g.root(case.p2,'s_JkgK',a['s_JkgK'])
    m=flow_mass(g,case,a); Hs=(bs['h_Jkg']-a['h_Jkg'])/1000
    if Hs<=0: raise ValueError('Nonpositive isentropic head: check state/model.')
    q=m*a['v_m3kg']; vs=g.pt(case.std_p,case.std_T)['v_m3kg']
    qs=m*vs; dh=(b['h_Jkg']-a['h_Jkg'])/1000
    r={'version':VERSION,'case':asdict(case),'composition_mole_fraction':composition,
       'property_model':'CoolProp Peng–Robinson, gas root; unlisted kij=0',
       'kij':{','.join(k):v for k,v in (kij or {}).items()},'inlet':a,'outlet':b,
       'isentropic_outlet':bs,'metrics':{},'warnings':[],
       'scope':'Field screening/training. Not certified ASME/API/ISO acceptance-test software.'}
    out=r['metrics']
    out.update(mass_flow_kgs=m,suction_flow_m3h=q*3600,standard_flow_m3h=qs*3600,
        standard_flow_MMSCFD=qs*86400/.028316846592/1e6,
        pressure_ratio=case.p2/case.p1,Hs_kJkg=Hs,isentropic_power_kW=m*Hs,
        eta_s_shaft_pct=100*m*Hs/case.power_kW,
        gas_enthalpy_rise_kJkg=dh,gas_enthalpy_power_kW=m*dh,
        specific_energy_kWhkg=case.power_kW/(3600*m),
        specific_energy_kWh_std_m3=case.power_kW/(3600*qs),
        specific_power_kW_MMSCFD=case.power_kW/(qs*86400/.028316846592/1e6))
    if case.machine in DYNAMIC:
        if case.heat_out_kW==0:
            if dh<=0: raise ValueError('Dynamic adiabatic analysis needs positive measured enthalpy rise.')
            out['eta_s_internal_pct']=100*Hs/dh
            out.update(schultz(g,case.p1,case.T1,case.p2,case.T2))
            out['adiabatic_power_residual_kW']=case.power_kW-m*dh
            if case.numerical_path:
                try: out.update(numerical_polytropic(g,case.p1,case.T1,case.p2,case.T2))
                except (ValueError,RuntimeError) as exc:
                    r['warnings'].append(f'Numerical path cross-check unavailable: {exc}')
        else:
            work=m*dh+case.heat_out_kW
            if work<=0: raise ValueError('Heat-corrected fluid work must be positive.')
            out['heat_corrected_fluid_work_kW']=work
            out['eta_s_heat_corrected_reference_pct']=100*m*Hs/work
            r['warnings'].append('Heat rejection supplied: adiabatic enthalpy/Schultz efficiencies suppressed. The work ratio is a heat-corrected reference, not a code polytropic result.')
    else:
        out['eta_v_pct']=100*q/case.displacement_m3s
        out['apparent_capacity_deficit_m3h']=(case.displacement_m3s-q)*3600
        Hiso=quad(lambda p:g.pt(p,case.T1)['v_m3kg'],case.p1,case.p2,epsabs=.01)[0]/1000
        out['H_isothermal_kJkg']=Hiso
        out['eta_isothermal_shaft_pct']=100*m*Hiso/case.power_kW
        r['warnings'].append('Capacity deficit includes heating, timing and re-expansion; it is not a measured leakage rate. Gas enthalpy rise is not shaft power for cooled/flooded machines.')
        if case.machine=='Liquid ring':
            r['warnings'].append('Limited liquid-ring screening: negligible vapour transfer assumed. Water-sealed wet gas needs a coupled mass/energy balance outside this tool.')
    for key,val in out.items():
        if key.startswith('eta_') and not 0<val<=100:
            r['warnings'].append(f'{key} = {val:.2f}% is outside 0–100%. Check boundary, phase, cooling, flow and measurements; value has not been clipped.')
    if out.get('adiabatic_power_residual_kW',0)<0:
        r['warnings'].append('Gas enthalpy power exceeds measured shaft input. Review heat input, side streams, power boundary and instruments.')
    r['warnings'].append('No automatic phase-stability, dew-point, kinetic-energy, leakage or OEM reference-condition correction is applied.')
    return r


def pv_power(csv_text,rpm):
    positive(rpm,'Speed')
    reader=csv.DictReader(io.StringIO(csv_text))
    required={'end_id','pressure_Pa','volume_m3'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError('P–V CSV requires end_id,pressure_Pa,volume_m3.')
    groups={}
    for row in reader:
        end=row['end_id'].strip()
        if not end: raise ValueError('Cylinder end_id cannot be blank.')
        p=positive(row['pressure_Pa'],'Cylinder absolute pressure')
        v=positive(row['volume_m3'],'Cylinder volume',allow_zero=True)
        groups.setdefault(end,[]).append((p,v))
    if not groups: raise ValueError('P–V file contains no cards.')
    out=[]
    for end,pts in groups.items():
        p,v=np.array(pts).T
        if len(pts)<4 or not np.isclose(v[0],v[-1],rtol=1e-7,atol=1e-12) or not np.isclose(p[0],p[-1],rtol=1e-7):
            raise ValueError(f'{end}: supply a closed card including the repeated first point.')
        work=-float(np.sum((p[1:]+p[:-1])/2*np.diff(v)))
        if work<=0: raise ValueError(f'{end}: nonpositive work. Check time order, phase and card orientation.')
        out.append(dict(end_id=end,cycle_work_J=work,indicated_power_kW=work*rpm/60000))
    return out


def compare_curve(csv_text,flow_m3h):
    rows=list(csv.DictReader(io.StringIO(csv_text)))
    needed={'suction_flow_m3h','efficiency_pct'}
    if len(rows)<2 or not needed.issubset(rows[0]):
        raise ValueError('OEM CSV needs at least two rows: suction_flow_m3h,efficiency_pct.')
    allowed=['efficiency_pct','head_kJkg','shaft_power_kW']
    columns=[c for c in allowed if c in rows[0]]
    data=[]
    for row in rows:
        x=positive(row['suction_flow_m3h'],'OEM suction flow')
        d={'suction_flow_m3h':x}
        for c in columns:
            d[c]=positive(row[c],f'OEM {c}')
            if c=='efficiency_pct' and d[c]>100: raise ValueError('OEM efficiency cannot exceed 100%.')
        data.append(d)
    data.sort(key=lambda d:d['suction_flow_m3h'])
    xs=[d['suction_flow_m3h'] for d in data]
    if len(set(xs))!=len(xs): raise ValueError('OEM flow values must be unique; supply a single matched curve.')
    if not xs[0]<=flow_m3h<=xs[-1]: raise ValueError('Measured flow lies outside the OEM curve. Extrapolation is disabled.')
    return {c:float(np.interp(flow_m3h,xs,[d[c] for d in data])) for c in columns},data


def uncertainty_eta(case,composition,kij,standard_u):
    if case.machine not in DYNAMIC or case.heat_out_kW!=0:
        raise ValueError('This partial uncertainty calculation is for adiabatic dynamic compressors only.')
    g=Gas(composition,kij); x=np.array([case.p1,case.T1,case.p2,case.T2],float)
    u=np.array(standard_u,float)
    if len(u)!=4 or not np.all(np.isfinite(u)) or np.any(u<0): raise ValueError('Supply four nonnegative standard uncertainties.')
    def f(v): return schultz(g,*v)['eta_p_pct']
    grad=[]
    for i in range(4):
        step=max(abs(x[i])*1e-5,u[i]*.01,1e-6)
        a,b=x.copy(),x.copy(); a[i]+=step; b[i]-=step
        grad.append((f(a)-f(b))/(2*step))
    uc=float(np.sqrt(np.sum((np.array(grad)*u)**2)))
    return {'eta_p_pct':f(x),'standard_uncertainty_pp':uc,'expanded_k2_pp':2*uc,
            'scope':'Partial independent P/T propagation only; excludes composition/EOS, correlations, profiles, heat, leakage and OEM curve uncertainty.'}

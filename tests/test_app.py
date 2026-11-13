from pathlib import Path
from streamlit.testing.v1 import AppTest

APP=Path(__file__).resolve().parents[1]/'app.py'

def test_app_start_and_calculate():
    at=AppTest.from_file(str(APP),default_timeout=30).run()
    assert not at.exception
    assert len(at.metric)==0
    at.checkbox(key='phase_Centrifugal').check()
    at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
    assert not at.exception
    assert any(m.value=='76.02%' for m in at.metric)
    assert len(at.get('download_button'))==3

def test_invalid_submission_clears_old_result():
    at=AppTest.from_file(str(APP),default_timeout=30).run()
    at.checkbox(key='phase_Centrifugal').check()
    at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
    at.number_input(key='p2_Centrifugal').set_value(20)
    at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
    assert not at.exception
    assert len(at.metric)==0
    assert any('must exceed' in e.value for e in at.error)

def test_all_machine_ui_paths():
    at=AppTest.from_file(str(APP),default_timeout=30).run()
    for machine in ['Axial','Reciprocating','Screw','Rotary lobe','Sliding vane','Liquid ring']:
        at.selectbox(key='machine').set_value(machine).run()
        at.checkbox(key=f'phase_{machine}').check()
        if machine=='Liquid ring': at.checkbox(key='ring_confirmed').check()
        at.button(key='FormSubmitter:case_form-Calculate performance').click().run()
        assert not at.exception, machine
        assert not at.error, machine
        assert len(at.metric)==4, machine

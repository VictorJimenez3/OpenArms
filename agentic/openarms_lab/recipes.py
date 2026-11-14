"""Application-authored mock recipe; reuses the existing validated add_sample action."""
DILUTION_SKILL={
    'skill_id':'premeasured_dilution.v1','name':'Add one premeasured water portion','version':'1.0.0','status':'active',
    'description':'MOCK pick, pour and return one prepared water cup from A (5 mL) or C (15 mL) into dye receiver B.',
    'controller_ref':'add_sample',
    'steps':[{'action':'add_sample','args':{'source':'$source','into':'$destination','portions':1}}],
    'parameters':{'object':{'type':'string','enum':['sample']},'source':{'type':'string','enum':['A','C']},'destination':{'type':'string','enum':['B']}},
    'preconditions':['one prepared water cup at the selected source','receiver B contains 5 mL stock dye','capacity for one dose','empty gripper at HOME'],
    'expected_outcomes':['mock portion count changes','cup returned','analytical concentration computed separately'],
    'approval_scopes':{'mock':'approved','physical':'unsupported'},
    'evidence':{'type':'application_recipe','source':'existing openarms_agent.catalog.add_sample and independent validator; mock lifecycle tests'},
    'limitations':'No measured color. No calibrated real pour. Physical wet-lab receiver C mapping is separate.'}

def install_recipes(registry):
    registry.install_builtin(DILUTION_SKILL)

def test_recipe(skill):
    """Test actual add_sample bindings and capacity/source boundaries symbolically."""
    import copy,uuid
    from .skills import compute_skill_hash
    from agentic.openarms_agent.validator import validate
    if compute_skill_hash(skill)!=compute_skill_hash(DILUTION_SKILL):
        raise ValueError('Dilution artifact differs from this reviewed recipe.')
    stations={'A':{'kind':'source','portions':1},'C':{'kind':'source','portions':1},'B':{'kind':'receiver','capacity':1}}
    passed=[]
    for source in ('A','C'):
        state={'at':'HOME','holding':None,'armed':True,'portions_left':{'A':1,'C':1},'receiver_load':{'B':0},'point_holds':{}}
        bindings={'source':source,'destination':'B'}
        args={k:(bindings[v[1:]] if isinstance(v,str) and v.startswith('$') else v) for k,v in skill['steps'][0]['args'].items()}
        plan={'plan_id':'recipe-test','student_instruction':'Test bound recipe','steps':[{'action':'add_sample','args':args}]}
        result=validate(plan,state,stations)
        if not result['ok'] or result['end_state']['receiver_load']['B']!=1 or result['end_state']['portions_left'][source]!=0:
            raise ValueError('Dose validation failed.')
        passed.append(source+' dose, return cup and HOME')
        for case in ('empty_source','full_receiver','disarmed'):
            invalid=copy.deepcopy(state)
            if case=='empty_source':invalid['portions_left'][source]=0
            elif case=='full_receiver':invalid['receiver_load']['B']=1
            else:invalid['armed']=False
            if validate(plan,invalid,stations)['ok']:raise ValueError('Unsafe recipe boundary accepted.')
            passed.append('reject '+case+' '+source)
    return {'evidence_id':'ev-'+uuid.uuid4().hex,'skill_id':skill['skill_id'],'skill_hash':compute_skill_hash(skill),
            'verdict':'passed','provenance':'MOCK','test_method':'bound add_sample through independent legacy validator; no fluid physics',
            'tests_passed':passed,'approval_scopes':{'mock':'approved','physical':'unsupported'}}

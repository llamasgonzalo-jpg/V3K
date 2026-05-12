from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, Sample, LabResult, SamplingPlan, NonConformity, CAPA,
                    CUL, Batch, AuditLog)
from datetime import datetime, timezone

quality_bp = Blueprint('quality', __name__, template_folder='../templates/quality', url_prefix='/quality')

def utcnow():
    return datetime.now(timezone.utc)

# ── Plan de muestreo (TRZ-091) ──

@quality_bp.route('/sampling-plans')
@login_required
def sampling_plans():
    return render_template('sampling_plans.html', plans=SamplingPlan.query.all())

@quality_bp.route('/sampling-plans/save', methods=['POST'])
@login_required
def sampling_plan_save():
    pid = request.form.get('plan_id')
    if pid:
        p = SamplingPlan.query.get_or_404(int(pid))
    else:
        p = SamplingPlan()
        db.session.add(p)
    p.chemotype = request.form['chemotype']
    p.frequency = request.form.get('frequency', '')
    p.sample_size = int(request.form['sample_size']) if request.form.get('sample_size') else None
    p.process_points = request.form.get('process_points', '')
    p.custody_protocol = request.form.get('custody_protocol', '')
    db.session.commit()
    flash('Plan guardado.', 'success')
    return redirect(url_for('quality.sampling_plans'))

# ── Muestras (TRZ-092..093) ──

@quality_bp.route('/samples')
@login_required
def samples():
    return render_template('samples.html', samples=Sample.query.order_by(Sample.created_at.desc()).all(),
                           culs=CUL.query.all(), batches=Batch.query.all())

@quality_bp.route('/samples/create', methods=['POST'])
@login_required
def sample_create():
    import random, string
    code = f"M-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
    s = Sample(
        code=code,
        cul_id=int(request.form['cul_id']) if request.form.get('cul_id') else None,
        batch_id=int(request.form['batch_id']) if request.form.get('batch_id') else None,
        sampled_by=current_user.id,
        lab_name=request.form.get('lab_name', ''),
        notes=request.form.get('notes', '')
    )
    db.session.add(s)
    db.session.commit()
    flash(f'Muestra {code} creada.', 'success')
    return redirect(url_for('quality.samples'))

@quality_bp.route('/samples/<int:id>/send', methods=['POST'])
@login_required
def sample_send(id):
    s = Sample.query.get_or_404(id)
    s.status = 'Enviada'
    s.sent_at = utcnow()
    s.lab_name = request.form.get('lab_name', s.lab_name)
    s.shipping_doc = request.form.get('shipping_doc', '')
    db.session.commit()
    flash('Muestra enviada.', 'success')
    return redirect(url_for('quality.samples'))

# ── Resultados (TRZ-094) ──

@quality_bp.route('/samples/<int:id>/results')
@login_required
def sample_results(id):
    s = Sample.query.get_or_404(id)
    return render_template('lab_results.html', sample=s, results=s.results)

@quality_bp.route('/samples/<int:id>/add-result', methods=['POST'])
@login_required
def add_result(id):
    s = Sample.query.get_or_404(id)
    r = LabResult(
        sample_id=id,
        lab_name=request.form.get('lab_name', ''),
        lab_accredited='lab_accredited' in request.form,
        analysis_type=request.form.get('analysis_type', ''),
        method=request.form.get('method', ''),
        results=request.form.get('results', ''),
        coa_reference=request.form.get('coa_reference', ''),
        is_conforming='is_conforming' in request.form,
        uploaded_by=current_user.id
    )
    s.status = 'Con resultado'
    db.session.add(r)
    db.session.commit()
    if not r.is_conforming:
        nc = NonConformity(
            description=f'Resultado no conforme en muestra {s.code}',
            severity='mayor',
            entity_type='Sample',
            entity_id=id,
            cul_id=s.cul_id,
            created_by=current_user.id
        )
        db.session.add(nc)
        db.session.commit()
        flash('Resultado NO conforme. No conformidad generada.', 'warning')
    else:
        flash('Resultado cargado.', 'success')
    return redirect(url_for('quality.sample_results', id=id))

# ── No conformidades (TRZ-096) ──

@quality_bp.route('/non-conformities')
@login_required
def non_conformities():
    return render_template('non_conformities.html',
                           ncs=NonConformity.query.order_by(NonConformity.created_at.desc()).all())

@quality_bp.route('/non-conformities/create', methods=['POST'])
@login_required
def nc_create():
    nc = NonConformity(
        description=request.form['description'],
        severity=request.form.get('severity', 'menor'),
        entity_type=request.form.get('entity_type', ''),
        entity_id=int(request.form['entity_id']) if request.form.get('entity_id') else None,
        cul_id=int(request.form['cul_id']) if request.form.get('cul_id') else None,
        created_by=current_user.id
    )
    db.session.add(nc)
    db.session.commit()
    nc.code = f"NC-{nc.id:04d}"
    db.session.commit()
    flash(f'No conformidad {nc.code} creada.', 'success')
    return redirect(url_for('quality.non_conformities'))

@quality_bp.route('/non-conformities/<int:id>')
@login_required
def nc_detail(id):
    nc = NonConformity.query.get_or_404(id)
    return render_template('nc_detail.html', nc=nc, capas=nc.capas)

@quality_bp.route('/non-conformities/<int:id>/close', methods=['POST'])
@login_required
def nc_close(id):
    nc = NonConformity.query.get_or_404(id)
    open_capas = CAPA.query.filter_by(non_conformity_id=id, status='Pendiente').count()
    if open_capas > 0:
        flash('No se puede cerrar: hay acciones pendientes.', 'danger')
    else:
        nc.status = 'Cerrada'
        nc.closed_at = utcnow()
        db.session.commit()
        flash('No conformidad cerrada.', 'success')
    return redirect(url_for('quality.nc_detail', id=id))

# ── CAPA (TRZ-097) ──

@quality_bp.route('/capa/create', methods=['POST'])
@login_required
def capa_create():
    c = CAPA(
        non_conformity_id=int(request.form['nc_id']),
        action=request.form['action'],
        responsible_id=int(request.form['responsible_id']) if request.form.get('responsible_id') else current_user.id,
        due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form.get('due_date') else None
    )
    db.session.add(c)
    nc = NonConformity.query.get(int(request.form['nc_id']))
    if nc and nc.status == 'Abierta':
        nc.status = 'En tratamiento'
    db.session.commit()
    flash('Acción correctiva creada.', 'success')
    return redirect(url_for('quality.nc_detail', id=int(request.form['nc_id'])))

@quality_bp.route('/capa/<int:id>/complete', methods=['POST'])
@login_required
def capa_complete(id):
    c = CAPA.query.get_or_404(id)
    c.status = 'Completada'
    c.completed_at = utcnow()
    c.evidence = request.form.get('evidence', '')
    db.session.commit()
    flash('Acción completada.', 'success')
    return redirect(url_for('quality.nc_detail', id=c.non_conformity_id))

# ── Liberación (TRZ-095) ──

@quality_bp.route('/release-gate')
@login_required
def release_gate():
    batches = Batch.query.filter(Batch.status.in_(['Seco', 'Deposito', 'Curado'])).all()
    return render_template('release_gate.html', batches=batches)

@quality_bp.route('/release-gate/<int:batch_id>/decide', methods=['POST'])
@login_required
def release_decide(batch_id):
    b = Batch.query.get_or_404(batch_id)
    decision = request.form['decision']
    if decision == 'liberar':
        b.status = 'Deposito'
        flash('Batch liberado.', 'success')
    elif decision == 'retener':
        b.status = 'Retenido'
        flash('Batch retenido.', 'warning')
    db.session.add(AuditLog(user_id=current_user.id, action='RELEASE_DECISION',
                            entity_type='Batch', entity_id=batch_id,
                            details=f'Decisión: {decision}'))
    db.session.commit()
    return redirect(url_for('quality.release_gate'))

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, Batch, CUL, Sector, Container, HarvestPlan, WastageRecord, WastageReason,
                    DestructionRecord, QualityCategory, Movement, AuditLog, UnitOfMeasure)
from datetime import datetime, timezone

harvest_bp = Blueprint('harvest', __name__, template_folder='../templates/harvest', url_prefix='/harvest')

def utcnow():
    return datetime.now(timezone.utc)

# ── Plan de cosecha (TRZ-061) ──

@harvest_bp.route('/plans')
@login_required
def plans():
    return render_template('harvest_plans.html', plans=HarvestPlan.query.all(),
                           culs=CUL.query.filter_by(is_blocked=False).all(),
                           sectors=Sector.query.all())

@harvest_bp.route('/plans/save', methods=['POST'])
@login_required
def plan_save():
    pid = request.form.get('plan_id')
    if pid:
        p = HarvestPlan.query.get_or_404(int(pid))
    else:
        p = HarvestPlan()
        db.session.add(p)
    p.cul_id = int(request.form['cul_id'])
    p.planned_date = datetime.strptime(request.form['planned_date'], '%Y-%m-%d').date() if request.form.get('planned_date') else None
    p.sector_id = int(request.form['sector_id']) if request.form.get('sector_id') else None
    p.drying_sector_id = int(request.form['drying_sector_id']) if request.form.get('drying_sector_id') else None
    p.responsibles = request.form.get('responsibles', '')
    p.sampling_checklist = request.form.get('sampling_checklist', '')
    db.session.commit()
    flash('Plan de cosecha guardado.', 'success')
    return redirect(url_for('harvest.plans'))

# ── Batches / Cosecha (TRZ-062..063) ──

@harvest_bp.route('/batches')
@login_required
def batches():
    return render_template('batches.html', batches=Batch.query.order_by(Batch.created_at.desc()).all(),
                           culs=CUL.query.all(), sectors=Sector.query.all(),
                           quality_cats=QualityCategory.query.all())

@harvest_bp.route('/batches/create', methods=['POST'])
@login_required
def batch_create():
    import random, string
    code = request.form.get('code') or f"BATCH-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
    b = Batch(
        code=code,
        cul_id=int(request.form['cul_id']),
        batch_type=request.form.get('batch_type', 'cosecha'),
        wet_weight=float(request.form['wet_weight']) if request.form.get('wet_weight') else None,
        current_weight=float(request.form['wet_weight']) if request.form.get('wet_weight') else None,
        equipment_used=request.form.get('equipment_used', ''),
        harvest_date=datetime.strptime(request.form['harvest_date'], '%Y-%m-%dT%H:%M') if request.form.get('harvest_date') else utcnow(),
        sector_id=int(request.form['sector_id']) if request.form.get('sector_id') else None,
        notes=request.form.get('notes', ''),
        created_by=current_user.id
    )
    db.session.add(b)
    db.session.commit()
    flash(f'Batch {b.code} creado.', 'success')
    return redirect(url_for('harvest.batches'))

@harvest_bp.route('/batches/<int:id>')
@login_required
def batch_detail(id):
    b = Batch.query.get_or_404(id)
    sub = Batch.query.filter_by(parent_batch_id=id).all()
    wastages = WastageRecord.query.filter_by(batch_id=id).all()
    movements = Movement.query.filter_by(batch_id=id).all()
    return render_template('batch_detail.html', batch=b, sub_batches=sub, wastages=wastages,
                           movements=movements, sectors=Sector.query.all(),
                           quality_cats=QualityCategory.query.all(),
                           wastage_reasons=WastageReason.query.all(),
                           containers=Container.query.all())

# ── Secado (TRZ-065..067) ──

@harvest_bp.route('/batches/<int:id>/start-drying', methods=['POST'])
@login_required
def start_drying(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Secado'
    b.drying_start = datetime.strptime(request.form['drying_start'], '%Y-%m-%dT%H:%M') if request.form.get('drying_start') else utcnow()
    if request.form.get('sector_id'):
        b.sector_id = int(request.form['sector_id'])
    db.session.commit()
    flash('Secado iniciado.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

@harvest_bp.route('/batches/<int:id>/end-drying', methods=['POST'])
@login_required
def end_drying(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Seco'
    b.drying_end = datetime.strptime(request.form['drying_end'], '%Y-%m-%dT%H:%M') if request.form.get('drying_end') else utcnow()
    b.dry_weight = float(request.form['dry_weight']) if request.form.get('dry_weight') else None
    b.current_weight = b.dry_weight
    db.session.commit()
    flash(f'Secado finalizado. Merma: {((b.wet_weight or 0) - (b.dry_weight or 0)):.2f}', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Trimming / Sublotes (TRZ-068) ──

@harvest_bp.route('/batches/<int:id>/create-sublot', methods=['POST'])
@login_required
def create_sublot(id):
    parent = Batch.query.get_or_404(id)
    weight = float(request.form['weight'])
    if weight > (parent.current_weight or 0):
        flash('El peso excede el disponible.', 'danger')
        return redirect(url_for('harvest.batch_detail', id=id))
    import random, string
    code = f"{parent.code}-SUB{''.join(random.choices(string.digits, k=3))}"
    sub = Batch(
        code=code,
        cul_id=parent.cul_id,
        batch_type='sublote',
        current_weight=weight,
        dry_weight=weight,
        quality_category_id=int(request.form['quality_category_id']) if request.form.get('quality_category_id') else None,
        parent_batch_id=id,
        sector_id=parent.sector_id,
        notes=request.form.get('notes', ''),
        created_by=current_user.id
    )
    parent.current_weight = (parent.current_weight or 0) - weight
    db.session.add(sub)
    db.session.commit()
    flash(f'Sublote {sub.code} creado.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Clasificación (TRZ-069) ──

@harvest_bp.route('/batches/<int:id>/classify', methods=['POST'])
@login_required
def classify_batch(id):
    b = Batch.query.get_or_404(id)
    b.quality_category_id = int(request.form['quality_category_id'])
    db.session.commit()
    flash('Clasificación actualizada.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Curado (TRZ-070..071) ──

@harvest_bp.route('/batches/<int:id>/start-curing', methods=['POST'])
@login_required
def start_curing(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Curado'
    b.curing_start = utcnow()
    db.session.commit()
    flash('Curado iniciado.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

@harvest_bp.route('/batches/<int:id>/end-curing', methods=['POST'])
@login_required
def end_curing(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Deposito'
    b.curing_end = utcnow()
    db.session.commit()
    flash('Curado finalizado. Batch en depósito.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Contenedores (TRZ-072..073) ──

@harvest_bp.route('/containers')
@login_required
def containers():
    return render_template('containers.html', containers=Container.query.all(), sectors=Sector.query.all())

@harvest_bp.route('/containers/save', methods=['POST'])
@login_required
def container_save():
    cid = request.form.get('container_id')
    if cid:
        c = Container.query.get_or_404(int(cid))
    else:
        c = Container()
        db.session.add(c)
    c.code = request.form['code']
    c.container_type = request.form.get('container_type', '')
    c.sector_id = int(request.form['sector_id']) if request.form.get('sector_id') else None
    db.session.commit()
    flash('Contenedor guardado.', 'success')
    return redirect(url_for('harvest.containers'))

@harvest_bp.route('/batches/<int:id>/assign-container', methods=['POST'])
@login_required
def assign_container(id):
    b = Batch.query.get_or_404(id)
    b.container_id = int(request.form['container_id'])
    db.session.commit()
    flash('Contenedor asignado.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Mermas (TRZ-075) ──

@harvest_bp.route('/wastage/create', methods=['POST'])
@login_required
def wastage_create():
    batch_id = int(request.form['batch_id'])
    batch = Batch.query.get_or_404(batch_id)
    qty = float(request.form['quantity'])
    w = WastageRecord(
        batch_id=batch_id,
        cul_id=batch.cul_id,
        reason_id=int(request.form['reason_id']) if request.form.get('reason_id') else None,
        quantity=qty,
        recorded_by=current_user.id,
        notes=request.form.get('notes', '')
    )
    batch.current_weight = (batch.current_weight or 0) - qty
    db.session.add(w)
    db.session.commit()
    flash('Merma registrada.', 'success')
    return redirect(url_for('harvest.batch_detail', id=batch_id))

# ── Retención (TRZ-076) ──

@harvest_bp.route('/batches/<int:id>/retain', methods=['POST'])
@login_required
def retain_batch(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Retenido'
    db.session.commit()
    flash('Batch en retención.', 'warning')
    return redirect(url_for('harvest.batch_detail', id=id))

@harvest_bp.route('/batches/<int:id>/release', methods=['POST'])
@login_required
def release_batch(id):
    b = Batch.query.get_or_404(id)
    b.status = 'Deposito'
    db.session.commit()
    flash('Batch liberado.', 'success')
    return redirect(url_for('harvest.batch_detail', id=id))

# ── Eliminación de batch (solo Administrador) ──
@harvest_bp.route('/batches/<int:id>/delete', methods=['POST'])
@login_required
def batch_delete(id):
    from models import Sample, DispatchItem, DispatchOrder
    # Solo administrador
    if not current_user.role or current_user.role.name != 'Administrador':
        flash('No tenés permisos para eliminar batches.', 'danger')
        return redirect(url_for('harvest.batch_detail', id=id))
    b = Batch.query.get_or_404(id)
    code = b.code
    # Verificar que no haya despachos confirmados
    dispatched = db.session.query(DispatchItem).join(DispatchOrder).filter(
        DispatchItem.batch_id == id,
        DispatchOrder.status == 'Recibida'
    ).count()
    if dispatched > 0:
        flash(f'No se puede eliminar: el batch tiene {dispatched} despacho(s) confirmado(s).', 'danger')
        return redirect(url_for('harvest.batch_detail', id=id))
    # Eliminar registros relacionados en cascada
    WastageRecord.query.filter_by(batch_id=id).delete()
    DestructionRecord.query.filter_by(batch_id=id).delete()
    Movement.query.filter_by(batch_id=id).delete()
    Sample.query.filter_by(batch_id=id).delete()
    DispatchItem.query.filter_by(batch_id=id).delete()
    # Audit
    db.session.add(AuditLog(
        user_id=current_user.id,
        action='DELETE',
        entity_type='Batch',
        entity_id=id,
        details=f'Batch eliminado por administrador: {code}',
        ip_address=request.remote_addr
    ))
    db.session.delete(b)
    db.session.commit()
    flash(f'Batch {code} eliminado correctamente.', 'success')
    return redirect(url_for('harvest.batches'))

# ── Destrucción (TRZ-077) ──

@harvest_bp.route('/destruction/create', methods=['POST'])
@login_required
def destruction_create():
    batch_id = int(request.form['batch_id'])
    batch = Batch.query.get_or_404(batch_id)
    d = DestructionRecord(
        batch_id=batch_id,
        cul_id=batch.cul_id,
        quantity=float(request.form['quantity']),
        reason=request.form['reason'],
        act_number=request.form.get('act_number', ''),
        responsible_id=current_user.id
    )
    batch.status = 'Destruido'
    batch.current_weight = 0
    db.session.add(d)
    db.session.commit()
    flash('Destrucción registrada.', 'success')
    return redirect(url_for('harvest.batch_detail', id=batch_id))

# ── Inventario físico (TRZ-074) ──

@harvest_bp.route('/physical-inventory')
@login_required
def physical_inventory():
    batches = Batch.query.filter(Batch.status.in_(['Deposito', 'Seco', 'Curado'])).all()
    containers_list = Container.query.all()
    return render_template('physical_inventory.html', batches=batches, containers=containers_list)

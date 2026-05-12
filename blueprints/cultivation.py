from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import (db, CUL, FloweringGroup, Genetic, Site, Sector, Campaign, CulEvent,
                    EventType, Movement, MaterialReception, BatchOperation, CultivationPlan,
                    RPCCINotification, BlockRecord, SPIGRecord, AccessLog, AuditLog,
                    DeviationRecord, ToleranceConfig)
from datetime import datetime, timezone
import json

cult_bp = Blueprint('cultivation', __name__, template_folder='../templates/cultivation', url_prefix='/cultivation')

def utcnow():
    return datetime.now(timezone.utc)

def audit(action, etype, eid, details=''):
    db.session.add(AuditLog(user_id=current_user.id, action=action, entity_type=etype, entity_id=eid, details=details))

# ── CUL (TRZ-022..023) ──

@cult_bp.route('/culs')
@login_required
def culs():
    culs_list = CUL.query.order_by(CUL.created_at.desc()).all()
    return render_template('culs.html', culs=culs_list, genetics=Genetic.query.all(),
                           sites=Site.query.all(), campaigns=Campaign.query.filter_by(is_closed=False).all(),
                           groups=FloweringGroup.query.all())

@cult_bp.route('/culs/create', methods=['POST'])
@login_required
def cul_create():
    c = CUL(
        code=request.form['code'],
        year=int(request.form['year']),
        permit_project=request.form.get('permit_project', ''),
        site_id=int(request.form['site_id']) if request.form.get('site_id') else None,
        sector_id=int(request.form['sector_id']) if request.form.get('sector_id') else None,
        lot_number=int(request.form['lot_number']) if request.form.get('lot_number') else None,
        stage=request.form.get('stage', 'VG'),
        purpose=request.form['purpose'],
        chemotype=request.form.get('chemotype', ''),
        genetic_id=int(request.form['genetic_id']) if request.form.get('genetic_id') else None,
        campaign_id=int(request.form['campaign_id']) if request.form.get('campaign_id') else None,
        flowering_group_id=int(request.form['flowering_group_id']) if request.form.get('flowering_group_id') else None,
        plant_count=int(request.form['plant_count']) if request.form.get('plant_count') else 0,
        declared_area=float(request.form['declared_area']) if request.form.get('declared_area') else None,
        responsible_tech=request.form.get('responsible_tech', ''),
        created_by=current_user.id
    )
    db.session.add(c)
    db.session.commit()
    audit('CREATE', 'CUL', c.id, f'CUL creado: {c.code}')
    db.session.commit()
    flash(f'CUL {c.code} creado.', 'success')
    return redirect(url_for('cultivation.culs'))

@cult_bp.route('/culs/<int:id>')
@login_required
def cul_detail(id):
    c = CUL.query.get_or_404(id)
    events = c.events.all()
    movements = c.movements.all()
    notifications = RPCCINotification.query.filter_by(cul_id=id).all()
    blocks = BlockRecord.query.filter_by(cul_id=id).all()
    deviations = DeviationRecord.query.filter_by(cul_id=id).all()
    event_types = EventType.query.filter_by(is_active=True).all()
    sectors = Sector.query.filter_by(site_id=c.site_id, is_active=True).all() if c.site_id else []
    return render_template('cul_detail.html', cul=c, events=events, movements=movements,
                           notifications=notifications, blocks=blocks, deviations=deviations,
                           event_types=event_types, sectors=sectors)

@cult_bp.route('/culs/<int:id>/edit', methods=['POST'])
@login_required
def cul_edit(id):
    c = CUL.query.get_or_404(id)
    c.stage = request.form.get('stage', c.stage)
    c.status = request.form.get('status', c.status)
    c.plant_count = int(request.form['plant_count']) if request.form.get('plant_count') else c.plant_count
    c.responsible_tech = request.form.get('responsible_tech', c.responsible_tech)
    if request.form.get('flowering_group_id'):
        c.flowering_group_id = int(request.form['flowering_group_id'])
    db.session.commit()
    audit('UPDATE', 'CUL', c.id, f'CUL editado: {c.code}')
    db.session.commit()
    flash('CUL actualizado.', 'success')
    return redirect(url_for('cultivation.cul_detail', id=id))

@cult_bp.route('/culs/<int:id>/delete', methods=['POST'])
@login_required
def cul_delete(id):
    c = CUL.query.get_or_404(id)
    code = c.code

    # Validar que no tiene datos críticos asociados
    from models import Batch
    batches = Batch.query.filter_by(cul_id=id).count()
    if batches > 0:
        flash(f'No se puede eliminar: CUL tiene {batches} batch(es) asociado(s).', 'danger')
        return redirect(url_for('cultivation.cul_detail', id=id))

    # Eliminar datos asociados (eventos, movimientos, etc.) en cascada
    CulEvent.query.filter_by(cul_id=id).delete()
    Movement.query.filter_by(cul_id=id).delete()
    BlockRecord.query.filter_by(cul_id=id).delete()
    DeviationRecord.query.filter_by(cul_id=id).delete()
    RPCCINotification.query.filter_by(cul_id=id).delete()

    # Registrar antes de eliminar
    audit('DELETE', 'CUL', id, f'CUL eliminado: {code}')
    db.session.commit()

    # Eliminar CUL
    db.session.delete(c)
    db.session.commit()

    flash(f'CUL {code} eliminado correctamente.', 'success')
    return redirect(url_for('cultivation.culs'))

# ── Eventos de cultivo (TRZ-031..043, 045) ──

@cult_bp.route('/events/create', methods=['POST'])
@login_required
def event_create():
    cul_id = int(request.form['cul_id'])
    e = CulEvent(
        cul_id=cul_id,
        event_type_id=int(request.form['event_type_id']) if request.form.get('event_type_id') else None,
        event_category=request.form['event_category'],
        date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M') if request.form.get('date') else utcnow(),
        description=request.form.get('description', ''),
        sector_id=int(request.form['sector_id']) if request.form.get('sector_id') else None,
        operator_id=current_user.id,
        water_volume=float(request.form['water_volume']) if request.form.get('water_volume') else None,
        water_source=request.form.get('water_source', ''),
        recipe_name=request.form.get('recipe_name', ''),
        recipe_details=request.form.get('recipe_details', ''),
        product_name=request.form.get('product_name', ''),
        dose=request.form.get('dose', ''),
        severity=request.form.get('severity', ''),
        findings=request.form.get('findings', ''),
        recommendations=request.form.get('recommendations', ''),
        temperature=float(request.form['temperature']) if request.form.get('temperature') else None,
        humidity=float(request.form['humidity']) if request.form.get('humidity') else None,
        count_expected=int(request.form['count_expected']) if request.form.get('count_expected') else None,
        count_actual=int(request.form['count_actual']) if request.form.get('count_actual') else None,
        count_difference_reason=request.form.get('count_difference_reason', ''),
        notes=request.form.get('notes', '')
    )
    db.session.add(e)
    db.session.commit()
    flash('Evento registrado.', 'success')
    return redirect(url_for('cultivation.cul_detail', id=cul_id))

# ── Movimientos (TRZ-033) ──

@cult_bp.route('/movements/create', methods=['POST'])
@login_required
def movement_create():
    cul_id = int(request.form['cul_id'])
    cul = CUL.query.get_or_404(cul_id)
    if cul.is_blocked:
        flash('CUL bloqueado: no se permiten movimientos.', 'danger')
        return redirect(url_for('cultivation.cul_detail', id=cul_id))
    m = Movement(
        cul_id=cul_id,
        origin_sector_id=int(request.form['origin_sector_id']) if request.form.get('origin_sector_id') else None,
        destination_sector_id=int(request.form['destination_sector_id']) if request.form.get('destination_sector_id') else None,
        date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M') if request.form.get('date') else utcnow(),
        responsible_id=current_user.id,
        responsible_tech=request.form.get('responsible_tech', ''),
        movement_type=request.form.get('movement_type', 'interno'),
        notes=request.form.get('notes', '')
    )
    db.session.add(m)
    if request.form.get('destination_sector_id'):
        cul.sector_id = int(request.form['destination_sector_id'])
    db.session.commit()
    flash('Movimiento registrado.', 'success')
    return redirect(url_for('cultivation.cul_detail', id=cul_id))

# ── Recepción de material (TRZ-029..030) ──

@cult_bp.route('/receptions')
@login_required
def receptions():
    recs = MaterialReception.query.order_by(MaterialReception.received_at.desc()).all()
    return render_template('receptions.html', receptions=recs, genetics=Genetic.query.all(), culs=CUL.query.all())

@cult_bp.route('/receptions/create', methods=['POST'])
@login_required
def reception_create():
    r = MaterialReception(
        material_type=request.form['material_type'],
        origin=request.form.get('origin', ''),
        lot_series=request.form.get('lot_series', ''),
        genetic_id=int(request.form['genetic_id']) if request.form.get('genetic_id') else None,
        quantity=int(request.form['quantity']),
        cul_id=int(request.form['cul_id']) if request.form.get('cul_id') else None,
        quarantine='quarantine' in request.form,
        quarantine_status='en_cuarentena' if 'quarantine' in request.form else 'liberado',
        received_by=current_user.id
    )
    db.session.add(r)
    db.session.commit()
    flash('Recepción registrada.', 'success')
    return redirect(url_for('cultivation.receptions'))

@cult_bp.route('/receptions/<int:id>/release', methods=['POST'])
@login_required
def reception_release(id):
    r = MaterialReception.query.get_or_404(id)
    r.quarantine_status = request.form.get('status', 'liberado')
    r.quarantine_reason = request.form.get('reason', '')
    db.session.commit()
    flash(f'Material {r.quarantine_status}.', 'success')
    return redirect(url_for('cultivation.receptions'))

# ── Notificaciones RPCCI (TRZ-044) ──

@cult_bp.route('/rpcci-notifications')
@login_required
def rpcci_notifications():
    notifs = RPCCINotification.query.order_by(RPCCINotification.created_at.desc()).all()
    return render_template('rpcci_notifications.html', notifications=notifs, culs=CUL.query.all())

@cult_bp.route('/rpcci-notifications/create', methods=['POST'])
@login_required
def rpcci_notification_create():
    n = RPCCINotification(
        cul_id=int(request.form['cul_id']) if request.form.get('cul_id') else None,
        notification_type=request.form['notification_type'],
        ticket_number=request.form.get('ticket_number', ''),
        status=request.form.get('status', 'Pendiente'),
        details=request.form.get('details', ''),
        created_by=current_user.id,
        sent_at=utcnow() if request.form.get('status') == 'Enviada' else None
    )
    db.session.add(n)
    db.session.commit()
    flash('Notificación RPCCI registrada.', 'success')
    return redirect(url_for('cultivation.rpcci_notifications'))

@cult_bp.route('/rpcci-notifications/<int:id>/update', methods=['POST'])
@login_required
def rpcci_notification_update(id):
    n = RPCCINotification.query.get_or_404(id)
    n.status = request.form['status']
    n.ticket_number = request.form.get('ticket_number', n.ticket_number)
    if n.status == 'Enviada' and not n.sent_at:
        n.sent_at = utcnow()
    if n.status in ('Aceptada', 'Rechazada'):
        n.response_at = utcnow()
    db.session.commit()
    flash('Notificación actualizada.', 'success')
    return redirect(url_for('cultivation.rpcci_notifications'))

# ── Bloqueos (TRZ-048) ──

@cult_bp.route('/blocks/create', methods=['POST'])
@login_required
def block_create():
    cul_id = int(request.form['cul_id'])
    cul = CUL.query.get_or_404(cul_id)
    b = BlockRecord(
        cul_id=cul_id,
        flowering_group_id=cul.flowering_group_id if 'extend_to_gf' in request.form else None,
        block_type=request.form.get('block_type', 'preventivo'),
        reason=request.form['reason'],
        blocked_by=current_user.id
    )
    cul.is_blocked = True
    cul.block_reason = request.form['reason']
    cul.status = 'Bloqueado'
    db.session.add(b)
    if 'extend_to_gf' in request.form and cul.flowering_group_id:
        fg = FloweringGroup.query.get(cul.flowering_group_id)
        if fg:
            fg.is_blocked = True
            for related_cul in fg.culs:
                related_cul.is_blocked = True
                related_cul.status = 'Bloqueado'
    db.session.commit()
    audit('BLOCK', 'CUL', cul_id, f'Bloqueado: {request.form["reason"]}')
    db.session.commit()
    flash('CUL bloqueado.', 'warning')
    return redirect(url_for('cultivation.cul_detail', id=cul_id))

@cult_bp.route('/blocks/<int:id>/unblock', methods=['POST'])
@login_required
def block_unblock(id):
    b = BlockRecord.query.get_or_404(id)
    b.is_active = False
    b.unblocked_by = current_user.id
    b.unblocked_at = utcnow()
    b.unblock_docs = request.form.get('documentation', '')
    cul = CUL.query.get(b.cul_id)
    if cul:
        active_blocks = BlockRecord.query.filter_by(cul_id=cul.id, is_active=True).count()
        if active_blocks <= 1:
            cul.is_blocked = False
            cul.status = 'Activo'
            cul.block_reason = None
    db.session.commit()
    flash('Bloqueo levantado.', 'success')
    return redirect(url_for('cultivation.cul_detail', id=b.cul_id))

# ── SPIG-BCP (TRZ-049) ──

@cult_bp.route('/spig')
@login_required
def spig_list():
    return render_template('spig.html', records=SPIGRecord.query.all(), genetics=Genetic.query.all())

@cult_bp.route('/spig/save', methods=['POST'])
@login_required
def spig_save():
    sid = request.form.get('spig_id')
    if sid:
        s = SPIGRecord.query.get_or_404(int(sid))
    else:
        s = SPIGRecord()
        db.session.add(s)
    s.code = request.form['code']
    s.genetic_id = int(request.form['genetic_id']) if request.form.get('genetic_id') else None
    s.material_type = request.form.get('material_type', '')
    s.tech_endorsement = request.form.get('tech_endorsement', '')
    s.status = request.form.get('status', 'Vigente')
    if request.form.get('issued_at'):
        s.issued_at = datetime.strptime(request.form['issued_at'], '%Y-%m-%d').date()
    if request.form.get('expires_at'):
        s.expires_at = datetime.strptime(request.form['expires_at'], '%Y-%m-%d').date()
    db.session.commit()
    flash('Registro SPIG-BCP guardado.', 'success')
    return redirect(url_for('cultivation.spig_list'))

# ── Plan de cultivo (TRZ-037) ──

@cult_bp.route('/cultivation-plans')
@login_required
def cultivation_plans():
    plans = CultivationPlan.query.all()
    return render_template('cultivation_plans.html', plans=plans, sites=Site.query.all(), campaigns=Campaign.query.all())

@cult_bp.route('/cultivation-plans/save', methods=['POST'])
@login_required
def cultivation_plan_save():
    pid = request.form.get('plan_id')
    if pid:
        p = CultivationPlan.query.get_or_404(int(pid))
    else:
        p = CultivationPlan()
        db.session.add(p)
    p.site_id = int(request.form['site_id'])
    p.campaign_id = int(request.form['campaign_id']) if request.form.get('campaign_id') else None
    p.holder_name = request.form.get('holder_name', '')
    p.responsible_tech = request.form.get('responsible_tech', '')
    p.medical_director = request.form.get('medical_director', '')
    p.varieties = request.form.get('varieties', '')
    p.chemotypes = request.form.get('chemotypes', '')
    p.biosecurity_notes = request.form.get('biosecurity_notes', '')
    p.breeding_area = 'breeding_area' in request.form
    db.session.commit()
    flash('Plan de cultivo guardado.', 'success')
    return redirect(url_for('cultivation.cultivation_plans'))

# ── Bitácora de accesos (TRZ-046) ──

@cult_bp.route('/access-log')
@login_required
def access_log():
    logs = AccessLog.query.order_by(AccessLog.date.desc()).all()
    return render_template('access_log.html', logs=logs, sites=Site.query.all())

@cult_bp.route('/access-log/create', methods=['POST'])
@login_required
def access_log_create():
    a = AccessLog(
        site_id=int(request.form['site_id']) if request.form.get('site_id') else None,
        visitor_name=request.form['visitor_name'],
        reason=request.form.get('reason', ''),
        area_visited=request.form.get('area_visited', ''),
        date=datetime.strptime(request.form['date'], '%Y-%m-%dT%H:%M') if request.form.get('date') else utcnow(),
        registered_by=current_user.id,
        authorization_ref=request.form.get('authorization_ref', '')
    )
    db.session.add(a)
    db.session.commit()
    flash('Registro de acceso guardado.', 'success')
    return redirect(url_for('cultivation.access_log'))

# ── Cambio de etapa (TRZ-022 transiciones) ──

@cult_bp.route('/culs/<int:id>/change-stage', methods=['POST'])
@login_required
def change_stage(id):
    cul = CUL.query.get_or_404(id)
    new_stage = request.form.get('new_stage')

    # Validar transición válida: VG→FL, FL→PC, PC→DIM, DIM→(ninguna)
    valid_transitions = {'VG': ['FL'], 'FL': ['PC'], 'PC': ['DIM'], 'DIM': []}
    if new_stage not in valid_transitions.get(cul.stage, []):
        flash(f'No se puede pasar de {cul.stage} a {new_stage}', 'danger')
        return redirect(url_for('cultivation.cul_detail', id=id))

    old_stage = cul.stage
    cul.stage = new_stage

    # Crear evento registrador "Cambio de etapa"
    evt_type = EventType.query.filter_by(name='Cambio de etapa').first()
    if evt_type:
        event = CulEvent(
            cul_id=id,
            event_type_id=evt_type.id,
            event_category='stage_change',
            description=f'Transición de {old_stage} a {new_stage}',
            notes=f'Cambio automático de etapa',
            operator_id=current_user.id,
            date=utcnow()
        )
        db.session.add(event)

    # Audit log
    audit('STAGE_CHANGE', 'CUL', id, f'{old_stage} → {new_stage}')
    db.session.commit()

    flash(f'CUL {cul.code} pasó a etapa {new_stage}', 'success')
    return redirect(url_for('cultivation.cul_detail', id=id))

# ── API: sectores por sitio ──

@cult_bp.route('/api/sectors/<int:site_id>')
@login_required
def api_sectors(site_id):
    sectors = Sector.query.filter_by(site_id=site_id, is_active=True).all()
    return jsonify([{'id': s.id, 'name': s.name, 'type': s.sector_type} for s in sectors])

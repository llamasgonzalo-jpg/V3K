from flask import Blueprint, render_template, request, make_response
from flask_login import login_required
from models import (db, CUL, Batch, Campaign, WastageRecord, SupplyConsumption, Supply,
                    RPCCINotification, Sample, LabResult, NonConformity, DispatchOrder,
                    ScheduledReport, AuditLog, Movement, CulEvent, FloweringGroup, BlockRecord,
                    DeviationRecord, SPIGRecord, CAPA, ProcessOrder, ProcessInput, ProcessOutput,
                    MaterialReception, DestructionRecord, Genetic, DispatchItem, ReceptionConfirmation)
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
import csv, io, json

reports_bp = Blueprint('reports', __name__, template_folder='../templates/reports', url_prefix='/reports')

@reports_bp.route('/')
@login_required
def index():
    return render_template('reports_index.html')

# ── Rendimiento (TRZ-079) ──

@reports_bp.route('/yield')
@login_required
def yield_report():
    batches = Batch.query.filter(Batch.wet_weight.isnot(None), Batch.dry_weight.isnot(None)).all()
    data = []
    for b in batches:
        loss = (b.wet_weight - b.dry_weight) if b.wet_weight and b.dry_weight else 0
        pct = (loss / b.wet_weight * 100) if b.wet_weight else 0
        data.append({'batch': b.code, 'cul': b.cul.code if b.cul else '', 'wet': b.wet_weight,
                     'dry': b.dry_weight, 'loss': loss, 'pct': round(pct, 1)})
    return render_template('yield_report.html', data=data)

# ── Reporte por campaña (TRZ-080) ──

@reports_bp.route('/campaign')
@login_required
def campaign_report():
    campaigns = Campaign.query.all()
    campaign_id = request.args.get('campaign_id', type=int)
    report = None
    if campaign_id:
        culs = CUL.query.filter_by(campaign_id=campaign_id).all()
        cul_ids = [c.id for c in culs]
        batches = Batch.query.filter(Batch.cul_id.in_(cul_ids)).all() if cul_ids else []
        wastages = WastageRecord.query.filter(WastageRecord.cul_id.in_(cul_ids)).all() if cul_ids else []
        total_wet = sum(b.wet_weight or 0 for b in batches)
        total_dry = sum(b.dry_weight or 0 for b in batches)
        total_waste = sum(w.quantity or 0 for w in wastages)
        report = {
            'campaign': Campaign.query.get(campaign_id),
            'culs': culs, 'batches': batches,
            'total_wet': total_wet, 'total_dry': total_dry,
            'total_waste': total_waste,
            'total_stock': sum(b.current_weight or 0 for b in batches)
        }
    return render_template('campaign_report.html', campaigns=campaigns, report=report)

# ── Balance de masa (TRZ-088) ──

@reports_bp.route('/mass-balance')
@login_required
def mass_balance():
    from models import ProcessOrder, ProcessInput, ProcessOutput
    orders = ProcessOrder.query.all()
    data = []
    for o in orders:
        total_in = sum(i.quantity for i in o.inputs)
        total_out = sum(out.quantity for out in o.outputs)
        waste = sum(out.quantity for out in o.outputs if out.is_waste)
        diff = total_in - total_out
        data.append({'order': o.code, 'status': o.status, 'input': total_in,
                     'output': total_out, 'waste': waste, 'diff': diff,
                     'pct': round(diff / total_in * 100, 1) if total_in else 0})
    return render_template('mass_balance.html', data=data)

# ── Trazabilidad completa (TRZ-098) ──

@reports_bp.route('/traceability')
@login_required
def traceability():
    search = request.args.get('q', '')
    result = None
    if search:
        cul = CUL.query.filter((CUL.code == search) | (CUL.code.contains(search))).first()
        if cul:
            events = CulEvent.query.filter_by(cul_id=cul.id).order_by(CulEvent.date).all()
            movements = Movement.query.filter_by(cul_id=cul.id).order_by(Movement.date).all()
            batches = Batch.query.filter_by(cul_id=cul.id).all()
            samples = Sample.query.filter_by(cul_id=cul.id).all()
            notifications = RPCCINotification.query.filter_by(cul_id=cul.id).all()
            result = {'cul': cul, 'events': events, 'movements': movements,
                      'batches': batches, 'samples': samples, 'notifications': notifications}
        else:
            batch = Batch.query.filter(Batch.code.contains(search)).first()
            if batch:
                result = {'batch': batch, 'cul': batch.cul}
    return render_template('traceability.html', search=search, result=result)

# ── Reporte auditoría (TRZ-099) ──

@reports_bp.route('/audit')
@login_required
def audit_report():
    cul_id = request.args.get('cul_id', type=int)
    cul = CUL.query.get(cul_id) if cul_id else None
    data = None
    if cul:
        data = {
            'cul': cul,
            'events': CulEvent.query.filter_by(cul_id=cul_id).order_by(CulEvent.date).all(),
            'batches': Batch.query.filter_by(cul_id=cul_id).all(),
            'samples': Sample.query.filter_by(cul_id=cul_id).all(),
            'notifications': RPCCINotification.query.filter_by(cul_id=cul_id).all(),
            'audit_trail': AuditLog.query.filter_by(entity_type='CUL', entity_id=cul_id).order_by(AuditLog.created_at).all()
        }
    culs = CUL.query.all()
    return render_template('audit_report.html', culs=culs, data=data)

# ── Dashboard stock por estado (TRZ-100) ──

@reports_bp.route('/stock-dashboard')
@login_required
def stock_dashboard():
    status_counts = db.session.query(Batch.status, func.count(Batch.id), func.sum(Batch.current_weight))\
        .group_by(Batch.status).all()
    return render_template('stock_dashboard.html', status_counts=status_counts)

# ── Dashboard de Cumplimiento Normativo ──

@reports_bp.route('/compliance')
@login_required
def compliance_dashboard():
    data = calculate_compliance_metrics()
    return render_template('compliance_dashboard.html', data=data)

def calculate_compliance_metrics():
    """Calcula todos los KPIs de cumplimiento normativo"""
    now = datetime.now(timezone.utc)

    # 1. COMPLETITUD POR ETAPA
    total_culs = CUL.query.count() or 1

    stages = {
        'genetica': {
            'total': Genetic.query.count(),
            'registered': Genetic.query.filter(Genetic.spig_bcp_code.isnot(None)).count(),
        },
        'plantines': {
            'total': MaterialReception.query.filter(MaterialReception.material_type.in_(['C','T'])).count(),
            'released': MaterialReception.query.filter(MaterialReception.material_type.in_(['C','T']),
                                                      MaterialReception.quarantine_status=='liberado').count(),
        },
        'cultivo_vg': {
            'active': CUL.query.filter_by(stage='VG').count(),
            'with_events': db.session.query(func.count(CUL.id)).filter(CUL.stage=='VG', CUL.events.any()).scalar() or 0,
        },
        'floracion_fl': {
            'active': CUL.query.filter_by(stage='FL').count(),
            'with_samples': db.session.query(func.count(CUL.id)).filter(CUL.stage=='FL', CUL.id==Sample.cul_id).scalar() or 0,
        },
        'cosecha': {
            'total': Batch.query.count(),
            'classified': Batch.query.filter(Batch.quality_category_id.isnot(None)).count(),
        },
        'secado': {
            'in_progress': Batch.query.filter_by(status='Secado').count(),
            'completed': Batch.query.filter(Batch.drying_end.isnot(None)).count(),
        },
        'almacenamiento': {
            'in_storage': Batch.query.filter(Batch.status.in_(['Deposito','Seco'])).count(),
            'dispatched': db.session.query(func.count(Batch.id)).filter(Batch.status.in_(['Deposito','Seco']), Batch.id==DispatchItem.batch_id).scalar() or 0,
        },
        'transporte': {
            'total': DispatchOrder.query.count(),
            'confirmed': DispatchOrder.query.filter_by(status='Recibida').count(),
        },
    }

    # Calcular % de cada etapa
    for stage, data in stages.items():
        if 'active' in data:
            data['pct'] = int((data['with_events'] or data['with_samples'] or 0) / (data['active'] or 1) * 100) if data['active'] else 0
        elif 'in_progress' in data:
            data['pct'] = int((data['completed'] or 0) / (data['in_progress'] or 1) * 100) if data['in_progress'] else 0
        elif 'in_storage' in data:
            data['pct'] = int((data['dispatched'] or 0) / (data['in_storage'] or 1) * 100) if data['in_storage'] else 0
        elif 'total' in data:
            data['pct'] = int((data.get('registered') or data.get('released') or data.get('classified') or 0) / (data['total'] or 1) * 100) if data['total'] else 0
        else:
            data['pct'] = 0
        data['status'] = 'green' if data['pct'] >= 90 else 'yellow' if data['pct'] >= 75 else 'red'

    # Cumplimiento global
    global_pct = int(sum(s['pct'] for s in stages.values()) / len(stages))

    # 2. ALERTAS REGULATORIAS
    alerts = {
        'culs_blocked': BlockRecord.query.filter_by(is_active=True).count(),
        'samples_non_conforming': LabResult.query.filter_by(is_conforming=False).count(),
        'non_conformities_open': NonConformity.query.filter_by(status='Abierta').count(),
        'capa_overdue': CAPA.query.filter(CAPA.due_date < now.date(), CAPA.status=='Pendiente').count(),
        'spig_expired': SPIGRecord.query.filter_by(status='Vencido').count(),
        'rpcci_rejected': RPCCINotification.query.filter_by(status='Rechazada').count(),
        'deviations_unresolved': DeviationRecord.query.filter_by(resolved=False).count(),
    }
    total_alerts = sum(alerts.values())
    alert_severity = 'red' if total_alerts > 5 else 'yellow' if total_alerts > 0 else 'green'

    # 3. EVENTOS SIN REGISTRAR
    pending = {
        'events_without_notes': CulEvent.query.filter(CulEvent.notes.is_(None)).count(),
        'batches_unclassified': Batch.query.filter(Batch.quality_category_id.is_(None)).count(),
        'samples_pending': Sample.query.filter(Sample.status.notin_(['Con resultado'])).count(),
        'dispatch_pending': DispatchOrder.query.filter(DispatchOrder.status.notin_(['Recibida'])).count(),
        'process_open': ProcessOrder.query.filter(ProcessOrder.status.notin_(['Cerrada'])).count(),
    }

    # 4. INCONSISTENCIAS
    inconsistencies = {
        'culs_no_batch': CUL.query.outerjoin(Batch).filter(Batch.id.is_(None)).count(),
        'batches_no_destination': Batch.query.outerjoin(DispatchItem).filter(Batch.status.in_(['Deposito','Seco']), DispatchItem.id.is_(None)).count(),
        'samples_incomplete_chain': Sample.query.filter(Sample.cul_id.is_(None), Sample.batch_id.is_(None)).count(),
    }

    # 5. INVENTARIO VIVO
    active_culs = CUL.query.filter(CUL.stage.in_(['VG','FL']), CUL.status=='Activo').all()
    active_plants = sum(c.plant_count for c in active_culs) if active_culs else 0

    inventory = {
        'active_plants': active_plants,
        'seedlings': MaterialReception.query.filter(MaterialReception.material_type.in_(['C','T']),
                                                    MaterialReception.quarantine_status=='liberado').count(),
        'lots_cultivation': CUL.query.filter(CUL.stage.in_(['VG','FL'])).count(),
        'lots_harvested': Batch.query.filter(Batch.status.in_(['Seco','Curado','Deposito'])).count(),
        'biomass_kg': db.session.query(func.coalesce(func.sum(Batch.current_weight), 0)).filter(
            Batch.status.in_(['Deposito','Seco'])).scalar() or 0,
        'material_destroyed_kg': db.session.query(func.coalesce(func.sum(DestructionRecord.quantity), 0)).scalar() or 0,
    }

    # 6. TIMELINE RECIENTE
    timeline = []
    # Batches cosechados
    for b in Batch.query.order_by(Batch.created_at.desc()).limit(5).all():
        timeline.append({
            'type': 'harvest',
            'code': b.code,
            'cul': b.cul.code if b.cul else '',
            'weight': b.wet_weight,
            'timestamp': b.created_at.isoformat() if b.created_at else '',
            'status': 'confirmed'
        })
    # Despachos
    for d in DispatchOrder.query.order_by(DispatchOrder.created_at.desc()).limit(5).all():
        timeline.append({
            'type': 'dispatch',
            'code': d.code,
            'recipient': d.recipient,
            'timestamp': d.created_at.isoformat() if d.created_at else '',
            'status': d.status.lower() if d.status else 'pending'
        })
    # Ordenar por timestamp
    timeline = sorted(timeline, key=lambda x: x['timestamp'], reverse=True)[:15]

    # 7. AUDITORÍA - ALERTAS TÉCNICAS
    audit_alerts = []
    if CUL.query.filter(CUL.status=='Bloqueado').count() > 0:
        audit_alerts.append({
            'severity': 'red',
            'category': 'Cumplimiento',
            'issue': 'CULs bloqueados activos',
            'count': BlockRecord.query.filter_by(is_active=True).count(),
            'action': 'Revisar y resolver bloqueos'
        })
    if LabResult.query.filter_by(is_conforming=False).count() > 0:
        audit_alerts.append({
            'severity': 'red',
            'category': 'Calidad',
            'issue': 'Muestras no conformes',
            'count': LabResult.query.filter_by(is_conforming=False).count(),
            'action': 'Iniciar CAPA'
        })
    if Batch.query.filter(Batch.quality_category_id.is_(None)).count() > 0:
        audit_alerts.append({
            'severity': 'yellow',
            'category': 'Documentación',
            'issue': 'Batches sin clasificar',
            'count': Batch.query.filter(Batch.quality_category_id.is_(None)).count(),
            'action': 'Clasificar por calidad'
        })

    return {
        'timestamp': now.isoformat(),
        'compliance': {
            'global_pct': global_pct,
            'status': 'green' if global_pct >= 95 else 'yellow' if global_pct >= 80 else 'red',
        },
        'stages': stages,
        'alerts': {
            **alerts,
            'total': total_alerts,
            'severity': alert_severity,
        },
        'pending': pending,
        'inconsistencies': inconsistencies,
        'inventory': inventory,
        'timeline': timeline,
        'audit_alerts': audit_alerts,
    }

# ── Exportar CSV (TRZ-104) ──

@reports_bp.route('/export/<string:entity>')
@login_required
def export_csv(entity):
    si = io.StringIO()
    writer = csv.writer(si)
    if entity == 'culs':
        writer.writerow(['Código', 'Año', 'Etapa', 'Finalidad', 'Quimiotipo', 'Estado', 'Plantas'])
        for c in CUL.query.all():
            writer.writerow([c.code, c.year, c.stage, c.purpose, c.chemotype, c.status, c.plant_count])
    elif entity == 'batches':
        writer.writerow(['Código', 'CUL', 'Tipo', 'Estado', 'Peso húmedo', 'Peso seco', 'Peso actual'])
        for b in Batch.query.all():
            writer.writerow([b.code, b.cul.code if b.cul else '', b.batch_type, b.status,
                           b.wet_weight, b.dry_weight, b.current_weight])
    elif entity == 'audit':
        writer.writerow(['Fecha', 'Usuario', 'Acción', 'Entidad', 'Detalles'])
        for a in AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5000).all():
            writer.writerow([a.created_at, a.user.username if a.user else '', a.action, a.entity_type, a.details])
    output = make_response(si.getvalue())
    output.headers['Content-Disposition'] = f'attachment; filename={entity}_{__import__("datetime").datetime.now().strftime("%Y%m%d")}.csv'
    output.headers['Content-type'] = 'text/csv'
    return output

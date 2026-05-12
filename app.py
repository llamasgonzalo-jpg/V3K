import os
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_login import LoginManager, login_required, current_user
from config import Config
from models import db, User, Role, Notification, CUL, Batch, Campaign, AuditLog, \
    UnitOfMeasure, EventType, WastageReason, QualityCategory, MaterialStatus, ToleranceConfig

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicie sesión para continuar.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Bloqueo de escritura para rol Inspector/Auditor
    @app.before_request
    def block_inspector_writes():
        if current_user.is_authenticated and request.method == 'POST':
            if current_user.role and current_user.role.name == 'Auditor/Inspector':
                flash('El rol Inspector solo tiene acceso de lectura.', 'warning')
                return redirect(request.referrer or url_for('main.dashboard'))

    # Session timeout check (TRZ-007)
    @app.before_request
    def check_session_timeout():
        if current_user.is_authenticated:
            timeout = app.config.get('SESSION_TIMEOUT_MINUTES', 30)
            if current_user.last_activity:
                elapsed = datetime.now(timezone.utc) - current_user.last_activity.replace(tzinfo=timezone.utc) if current_user.last_activity.tzinfo is None else datetime.now(timezone.utc) - current_user.last_activity
                if elapsed > timedelta(minutes=timeout):
                    from flask_login import logout_user
                    logout_user()
                    flash('Sesión expirada por inactividad.', 'warning')
                    return redirect(url_for('auth.login'))
            current_user.last_activity = datetime.now(timezone.utc)
            db.session.commit()

    # Context processors
    @app.context_processor
    def inject_globals():
        unread = 0
        is_inspector = False
        if current_user.is_authenticated:
            unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            is_inspector = bool(current_user.role and current_user.role.name == 'Auditor/Inspector')
        return dict(unread_notifications=unread, now=datetime.now(timezone.utc), is_inspector=is_inspector)

    # Register blueprints
    from blueprints.auth import auth_bp
    from blueprints.admin import admin_bp
    from blueprints.master import master_bp
    from blueprints.cultivation import cult_bp
    from blueprints.inventory import inv_bp
    from blueprints.harvest import harvest_bp
    from blueprints.processing import proc_bp
    from blueprints.quality import quality_bp
    from blueprints.dispatch import dispatch_bp
    from blueprints.reports import reports_bp
    from blueprints.patients import patients_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(master_bp)
    app.register_blueprint(cult_bp)
    app.register_blueprint(inv_bp)
    app.register_blueprint(harvest_bp)
    app.register_blueprint(proc_bp)
    app.register_blueprint(quality_bp)
    app.register_blueprint(dispatch_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(patients_bp)

    # Main routes
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('main.dashboard'))
        return redirect(url_for('auth.login'))

    from flask import Blueprint
    main_bp = Blueprint('main', __name__)

    @main_bp.route('/dashboard')
    @login_required
    def dashboard():
        from models import (Sample, LabResult, NonConformity, DispatchOrder, ProcessOrder,
                            Genetic, MaterialReception, FloweringGroup, BlockRecord,
                            DeviationRecord, RPCCINotification, CAPA, DestructionRecord,
                            Movement, CulEvent, WastageRecord)

        stats = {
            'culs_active': CUL.query.filter_by(status='Activo').count(),
            'culs_blocked': CUL.query.filter_by(is_blocked=True).count(),
            'culs_vg': CUL.query.filter_by(stage='VG').count(),
            'culs_fl': CUL.query.filter_by(stage='FL').count(),
            'culs_pc': CUL.query.filter_by(stage='PC').count(),
            'batches_total': Batch.query.count(),
            'batches_drying': Batch.query.filter_by(status='Secado').count(),
            'batches_storage': Batch.query.filter_by(status='Deposito').count(),
            'batches_curing': Batch.query.filter(Batch.status.in_(['Curado','Curando'])).count(),
            'batches_retained': Batch.query.filter_by(status='Retenido').count(),
            'campaigns_open': Campaign.query.filter_by(is_closed=False).count(),
            'total_stock_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).scalar() or 0,
            'genetics_count': Genetic.query.count(),
            'flowering_groups': FloweringGroup.query.count(),
            'plants_active': db.session.query(db.func.coalesce(db.func.sum(CUL.plant_count), 0)).filter(
                CUL.status == 'Activo', CUL.stage.in_(['VG', 'FL'])).scalar() or 0,
            'samples_pending': Sample.query.filter(Sample.status.notin_(['Con resultado'])).count(),
            'nc_open': NonConformity.query.filter_by(status='Abierta').count(),
            'dispatch_pending': DispatchOrder.query.filter(DispatchOrder.status.notin_(['Recibida'])).count(),
            'process_open': ProcessOrder.query.filter(ProcessOrder.status.notin_(['Cerrada'])).count(),
            'blocks_active': BlockRecord.query.filter_by(is_active=True).count(),
            'material_destroyed': db.session.query(db.func.coalesce(db.func.sum(DestructionRecord.quantity), 0)).scalar() or 0,
            'rpcci_pending': RPCCINotification.query.filter_by(status='Pendiente').count(),
            # Stock real por estado (para gráfico)
            'stock_secado_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).filter(Batch.status == 'Secado').scalar() or 0,
            'stock_curado_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).filter(Batch.status.in_(['Curado','Curando'])).scalar() or 0,
            'stock_deposito_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).filter(Batch.status == 'Deposito').scalar() or 0,
            'stock_retenido_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).filter(Batch.status == 'Retenido').scalar() or 0,
            'batches_other': Batch.query.filter(~Batch.status.in_(['Secado','Deposito','Curado','Curando','Retenido'])).count(),
            'stock_other_kg': db.session.query(db.func.coalesce(db.func.sum(Batch.current_weight), 0)).filter(~Batch.status.in_(['Secado','Deposito','Curado','Curando','Retenido'])).scalar() or 0,
        }
        recent_events = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
        notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).limit(10).all()
        return render_template('dashboard.html', stats=stats, recent_events=recent_events,
                               notifications=notifications)

    @main_bp.route('/notifications')
    @login_required
    def notifications_list():
        notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
        return render_template('notifications.html', notifications=notifs)

    @main_bp.route('/notifications/<int:id>/read', methods=['POST'])
    @login_required
    def notification_read(id):
        n = Notification.query.get_or_404(id)
        n.is_read = True
        db.session.commit()
        return redirect(url_for('main.notifications_list'))

    @main_bp.route('/notifications/mark-all-read', methods=['POST'])
    @login_required
    def mark_all_read():
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
        db.session.commit()
        flash('Todas las notificaciones marcadas como leídas.', 'success')
        return redirect(url_for('main.notifications_list'))

    app.register_blueprint(main_bp)

    # Create tables and seed data
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        if not User.query.first():
            seed_data()

    return app

def seed_data():
    # Roles
    roles = [
        Role(name='Administrador', description='Acceso completo al sistema', permissions='all'),
        Role(name='Director Técnico', description='Gestión técnica, CUL, planes de cultivo', permissions='tech'),
        Role(name='Operador', description='Registro de eventos, movimientos, cosecha', permissions='operator'),
        Role(name='Laboratorio', description='Carga de resultados analíticos', permissions='lab'),
        Role(name='Auditor/Inspector', description='Solo lectura, consulta de trazabilidad', permissions='auditor'),
        Role(name='Receptor', description='Confirmación de recepciones', permissions='receptor'),
    ]
    for r in roles:
        db.session.add(r)
    db.session.flush()

    admin = User(username='admin', email='admin@trazabilidad.local', full_name='Administrador del Sistema',
                 role_id=roles[0].id, is_active=True)
    admin.set_password('admin123')
    db.session.add(admin)

    # Unidades de medida (TRZ-011)
    units = ['g|gramo', 'kg|kilogramo', 'mg|miligramo', 'L|litro', 'mL|mililitro', 'u|unidad']
    for u in units:
        abbr, name = u.split('|')
        db.session.add(UnitOfMeasure(name=name, abbreviation=abbr))

    # Tipos de evento (TRZ-013)
    events = ['Riego', 'Fertirrigación', 'Aplicación fitosanitaria', 'Aplicación biológica',
              'Poda', 'Tutorado', 'Trasplante', 'Scouting', 'Limpieza',
              'Registro ambiental', 'Incidente climático', 'Conteo de plantas', 'Propagación',
              'Cambio de etapa']
    for e in events:
        db.session.add(EventType(name=e, category=e.lower().replace(' ', '_')))

    # Motivos de merma (TRZ-014)
    reasons = ['Secado natural', 'Limpieza/trimming', 'Contaminación', 'Plagas',
               'Error de proceso', 'Deterioro', 'Otro']
    for r in reasons:
        db.session.add(WastageReason(name=r))

    # Categorías de calidad (TRZ-015)
    cats = ['Premium', 'Standard', 'Industrial', 'Biomasa']
    for c in cats:
        db.session.add(QualityCategory(name=c))

    # Estados (TRZ-012)
    statuses = [
        ('Activo', 'VG', 'Liberado'), ('Activo', 'FL', 'Liberado'), ('Activo', 'PC', 'Liberado'),
        ('Bloqueado preventivo', '', 'Bloqueado'), ('Suspendido', '', 'Bloqueado'),
        ('Retenido', '', 'Retenido'), ('Destruido', '', 'Destruido'),
    ]
    for name, stage, cat in statuses:
        db.session.add(MaterialStatus(name=name, stage=stage, category=cat))

    # Tolerancias (TRZ-047)
    tolerances = [('Q1', 5), ('Q2', 10), ('Q3', 15)]
    for chemo, pct in tolerances:
        for metric in ['plantas', 'superficie', 'rendimiento']:
            db.session.add(ToleranceConfig(chemotype=chemo, tolerance_pct=pct, applies_to=metric))

    db.session.commit()

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)

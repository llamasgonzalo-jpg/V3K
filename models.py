from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)

# ── TRZ-001..007: Autenticación y seguridad ──

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    permissions = db.Column(db.Text)  # JSON de permisos
    created_at = db.Column(db.DateTime, default=utcnow)
    users = db.relationship('User', backref='role', lazy='dynamic')

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(200))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    is_active = db.Column(db.Boolean, default=True)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime)
    password_expires = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        if self.locked_until and self.locked_until > utcnow():
            return True
        return False

# ── Auditoría (transversal) ──

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)  # CREATE, UPDATE, DELETE, LOGIN, etc.
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User', backref='audit_logs')

# ── TRZ-009: Adjuntos ──

class Attachment(db.Model):
    __tablename__ = 'attachments'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    mimetype = db.Column(db.String(100))
    size = db.Column(db.Integer)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User')

# ── TRZ-010: Notificaciones internas ──

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50))  # stock_min, vencimiento, aprobacion, etc.
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    entity_type = db.Column(db.String(80))
    entity_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=utcnow)
    user = db.relationship('User', backref='notifications')

# ── TRZ-011..017: Catálogos ──

class UnitOfMeasure(db.Model):
    __tablename__ = 'units_of_measure'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    abbreviation = db.Column(db.String(10), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

class MaterialStatus(db.Model):
    __tablename__ = 'material_statuses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    stage = db.Column(db.String(50))  # Propagacion, VG, FL, PC, DIM
    category = db.Column(db.String(50))  # Retenido, Liberado, Destruido, Bloqueado
    is_active = db.Column(db.Boolean, default=True)

class EventType(db.Model):
    __tablename__ = 'event_types'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50))  # riego, aplicacion, poda, cosecha, etc.
    requires_checklist = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

class WastageReason(db.Model):
    __tablename__ = 'wastage_reasons'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

class QualityCategory(db.Model):
    __tablename__ = 'quality_categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(80), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(20), nullable=False)  # text, number, date, select
    options = db.Column(db.Text)  # JSON para select
    is_required = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)

class FormTemplate(db.Model):
    __tablename__ = 'form_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    event_type_id = db.Column(db.Integer, db.ForeignKey('event_types.id'))
    fields = db.Column(db.Text)  # JSON
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-018: Reglas de codificación ──

class CodingRule(db.Model):
    __tablename__ = 'coding_rules'
    id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(20), nullable=False)  # CUL, GF, SPIG_BCP
    pattern = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    valid_stages = db.Column(db.String(100))  # VG,FL,PC,DIM
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-019..020: Predios y salas/sectores ──

class Site(db.Model):
    __tablename__ = 'sites'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    cadastral_code = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    total_area = db.Column(db.Float)
    effective_area = db.Column(db.Float)
    germination_area = db.Column(db.Float)
    vegetation_area = db.Column(db.Float)
    flowering_area = db.Column(db.Float)
    harvest_area = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    sectors = db.relationship('Sector', backref='site', lazy='dynamic')
    campaigns = db.relationship('Campaign', backref='site', lazy='dynamic')

class Sector(db.Model):
    __tablename__ = 'sectors'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sector_type = db.Column(db.String(50), nullable=False)  # propagacion, VG, FL, secado, curado, almacenamiento, proceso
    capacity = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

class SectorLink(db.Model):
    __tablename__ = 'sector_links'
    id = db.Column(db.Integer, primary_key=True)
    origin_id = db.Column(db.Integer, db.ForeignKey('sectors.id'), nullable=False)
    destination_id = db.Column(db.Integer, db.ForeignKey('sectors.id'), nullable=False)
    origin = db.relationship('Sector', foreign_keys=[origin_id])
    destination = db.relationship('Sector', foreign_keys=[destination_id])

# ── TRZ-021: Campañas ──

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_closed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-022..024: CUL ──

class CUL(db.Model):
    __tablename__ = 'culs'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    permit_project = db.Column(db.String(100))
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    lot_number = db.Column(db.Integer)
    stage = db.Column(db.String(20))  # VG, FL, PC, DIM
    purpose = db.Column(db.String(50))  # fitomejoramiento, produccion, I+D, biomasa
    chemotype = db.Column(db.String(20))  # Q1, Q2, Q3, Q4, Q5
    genetic_id = db.Column(db.Integer, db.ForeignKey('genetics.id'))
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    flowering_group_id = db.Column(db.Integer, db.ForeignKey('flowering_groups.id'))
    status = db.Column(db.String(30), default='Activo')  # Activo, Bloqueado, Cerrado
    rigor_mode = db.Column(db.String(20))  # alta, media, documental, basica
    is_blocked = db.Column(db.Boolean, default=False)
    block_reason = db.Column(db.Text)
    responsible_tech = db.Column(db.String(200))
    plant_count = db.Column(db.Integer, default=0)
    declared_area = db.Column(db.Float)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    closed_at = db.Column(db.DateTime)
    site = db.relationship('Site')
    sector = db.relationship('Sector')
    campaign = db.relationship('Campaign')
    genetic = db.relationship('Genetic')
    creator = db.relationship('User')
    events = db.relationship('CulEvent', backref='cul', lazy='dynamic', order_by='CulEvent.date.desc()')
    movements = db.relationship('Movement', backref='cul', lazy='dynamic')

# ── TRZ-008: Grupo de Floración ──

class FloweringGroup(db.Model):
    __tablename__ = 'flowering_groups'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200))
    purpose = db.Column(db.String(50))
    variety = db.Column(db.String(100))
    environment = db.Column(db.String(100))
    is_blocked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    culs = db.relationship('CUL', backref='flowering_group', lazy='dynamic')

# ── TRZ-027: Genéticas ──

class Genetic(db.Model):
    __tablename__ = 'genetics'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(100))
    origin = db.Column(db.String(200))
    expected_chemotype = db.Column(db.String(20))
    registry_status = db.Column(db.String(50))  # INASE, SPIG-BCP, Banco
    registry_expiry = db.Column(db.Date)
    spig_code = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

# ── TRZ-028: Plantas madre ──

class MotherPlant(db.Model):
    __tablename__ = 'mother_plants'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    genetic_id = db.Column(db.Integer, db.ForeignKey('genetics.id'))
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    status = db.Column(db.String(30), default='Activa')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    genetic = db.relationship('Genetic')
    site = db.relationship('Site')

# ── TRZ-029..030: Recepción material ──

class MaterialReception(db.Model):
    __tablename__ = 'material_receptions'
    id = db.Column(db.Integer, primary_key=True)
    material_type = db.Column(db.String(10), nullable=False)  # S, C, P, T
    origin = db.Column(db.String(200))
    lot_series = db.Column(db.String(100))
    genetic_id = db.Column(db.Integer, db.ForeignKey('genetics.id'))
    quantity = db.Column(db.Integer, nullable=False)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    quarantine = db.Column(db.Boolean, default=False)
    quarantine_status = db.Column(db.String(30))  # en_cuarentena, liberado, rechazado
    quarantine_reason = db.Column(db.Text)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_at = db.Column(db.DateTime, default=utcnow)
    genetic = db.relationship('Genetic')
    cul = db.relationship('CUL')

# ── TRZ-031..046: Eventos de cultivo ──

class CulEvent(db.Model):
    __tablename__ = 'cul_events'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'), nullable=False)
    event_type_id = db.Column(db.Integer, db.ForeignKey('event_types.id'))
    event_category = db.Column(db.String(50), nullable=False)  # propagacion, trasplante, riego, nutricion, aplicacion, manejo, scouting, ambiente, clima, acceso
    date = db.Column(db.DateTime, nullable=False, default=utcnow)
    description = db.Column(db.Text)
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    # Riego
    water_volume = db.Column(db.Float)
    water_source = db.Column(db.String(100))
    # Nutrición
    recipe_name = db.Column(db.String(100))
    recipe_details = db.Column(db.Text)
    # Aplicación
    product_name = db.Column(db.String(200))
    dose = db.Column(db.String(100))
    # Scouting
    severity = db.Column(db.String(20))
    findings = db.Column(db.Text)
    recommendations = db.Column(db.Text)
    # Ambiente
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    # Conteo (TRZ-035)
    count_expected = db.Column(db.Integer)
    count_actual = db.Column(db.Integer)
    count_difference_reason = db.Column(db.Text)
    # General
    notes = db.Column(db.Text)
    checklist_data = db.Column(db.Text)  # JSON
    created_at = db.Column(db.DateTime, default=utcnow)
    event_type = db.relationship('EventType')
    sector = db.relationship('Sector')
    operator = db.relationship('User')

# ── TRZ-033: Movimientos ──

class Movement(db.Model):
    __tablename__ = 'movements'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    container_id = db.Column(db.Integer, db.ForeignKey('containers.id'))
    origin_sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    destination_sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    date = db.Column(db.DateTime, nullable=False, default=utcnow)
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    responsible_tech = db.Column(db.String(200))
    movement_type = db.Column(db.String(30))  # interno, secado, curado, despacho
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    origin = db.relationship('Sector', foreign_keys=[origin_sector_id])
    destination = db.relationship('Sector', foreign_keys=[destination_sector_id])
    responsible = db.relationship('User')

# ── TRZ-036: Split/Merge ──

class BatchOperation(db.Model):
    __tablename__ = 'batch_operations'
    id = db.Column(db.Integer, primary_key=True)
    operation_type = db.Column(db.String(10), nullable=False)  # split, merge
    date = db.Column(db.DateTime, default=utcnow)
    notes = db.Column(db.Text)
    performed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    input_batches = db.Column(db.Text)   # JSON IDs
    output_batches = db.Column(db.Text)  # JSON IDs

# ── TRZ-037: Plan de cultivo ──

class CultivationPlan(db.Model):
    __tablename__ = 'cultivation_plans'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'), nullable=False)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    holder_name = db.Column(db.String(200))
    responsible_tech = db.Column(db.String(200))
    medical_director = db.Column(db.String(200))
    varieties = db.Column(db.Text)
    chemotypes = db.Column(db.Text)
    schedule = db.Column(db.Text)  # JSON cronograma
    biosecurity_notes = db.Column(db.Text)
    breeding_area = db.Column(db.Boolean, default=False)
    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)
    site = db.relationship('Site')
    campaign = db.relationship('Campaign')

# ── TRZ-034: Rigurosidad ──

class RigorRule(db.Model):
    __tablename__ = 'rigor_rules'
    id = db.Column(db.Integer, primary_key=True)
    activity = db.Column(db.String(20), nullable=False)  # H, Bio, A, E, K, N
    chemotype = db.Column(db.String(10))  # Q1, Q2, Q3, Q4, Q5
    rigor_level = db.Column(db.String(20), nullable=False)  # alta, media, documental, basica
    tracking_mode = db.Column(db.String(20))  # por_unidad, por_batch
    required_fields = db.Column(db.Text)  # JSON
    report_frequency = db.Column(db.String(50))

# ── TRZ-044: Notificaciones RPCCI ──

class RPCCINotification(db.Model):
    __tablename__ = 'rpcci_notifications'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    notification_type = db.Column(db.String(80), nullable=False)
    ticket_number = db.Column(db.String(100))
    status = db.Column(db.String(30), default='Pendiente')  # Pendiente, Enviada, Aceptada, Rechazada
    sent_at = db.Column(db.DateTime)
    response_at = db.Column(db.DateTime)
    details = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    cul = db.relationship('CUL')

# ── TRZ-047: Tolerancias ──

class ToleranceConfig(db.Model):
    __tablename__ = 'tolerance_configs'
    id = db.Column(db.Integer, primary_key=True)
    chemotype = db.Column(db.String(10), nullable=False)
    tolerance_pct = db.Column(db.Float, nullable=False)  # 5, 10, 15
    applies_to = db.Column(db.String(50))  # plantas, superficie, rendimiento

class DeviationRecord(db.Model):
    __tablename__ = 'deviation_records'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    metric = db.Column(db.String(50))
    declared_value = db.Column(db.Float)
    verified_value = db.Column(db.Float)
    deviation_pct = db.Column(db.Float)
    severity = db.Column(db.String(10))  # menor, mayor
    justification = db.Column(db.Text)
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-048: Bloqueos ──

class BlockRecord(db.Model):
    __tablename__ = 'block_records'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    flowering_group_id = db.Column(db.Integer, db.ForeignKey('flowering_groups.id'))
    block_type = db.Column(db.String(30))  # preventivo, temporal, definitivo
    reason = db.Column(db.Text, nullable=False)
    blocked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    blocked_at = db.Column(db.DateTime, default=utcnow)
    unblocked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    unblocked_at = db.Column(db.DateTime)
    unblock_docs = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

# ── TRZ-049: SPIG-BCP ──

class SPIGRecord(db.Model):
    __tablename__ = 'spig_records'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    genetic_id = db.Column(db.Integer, db.ForeignKey('genetics.id'))
    material_type = db.Column(db.String(10))  # S, C, P, T
    tech_endorsement = db.Column(db.String(200))
    varietal_record = db.Column(db.Text)
    parental_record = db.Column(db.Text)
    initial_analytics = db.Column(db.Text)
    issued_at = db.Column(db.Date)
    expires_at = db.Column(db.Date)
    extended = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(30), default='Vigente')  # Vigente, Vencido, Suspendido, Baja
    regularization_status = db.Column(db.String(30))  # pendiente, INASE, Banco
    created_at = db.Column(db.DateTime, default=utcnow)
    genetic = db.relationship('Genetic')

# ── TRZ-051..060: Inventario de insumos ──

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    contact = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

class Supply(db.Model):
    __tablename__ = 'supplies'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(80))  # fertilizante, fitosanitario, sustrato, etc.
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))
    min_stock = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    unit = db.relationship('UnitOfMeasure')

class Warehouse(db.Model):
    __tablename__ = 'warehouses'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    is_active = db.Column(db.Boolean, default=True)
    site = db.relationship('Site')

class SupplyReception(db.Model):
    __tablename__ = 'supply_receptions'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    batch_lot = db.Column(db.String(100))
    quantity = db.Column(db.Float, nullable=False)
    expiry_date = db.Column(db.Date)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_at = db.Column(db.DateTime, default=utcnow)
    supply = db.relationship('Supply')
    supplier = db.relationship('Supplier')
    warehouse = db.relationship('Warehouse')

class SupplyStock(db.Model):
    __tablename__ = 'supply_stock'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    quantity = db.Column(db.Float, default=0)
    supply = db.relationship('Supply')
    warehouse = db.relationship('Warehouse')

class SupplyConsumption(db.Model):
    __tablename__ = 'supply_consumptions'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    event_id = db.Column(db.Integer, db.ForeignKey('cul_events.id'))
    quantity = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=utcnow)
    consumed_by = db.Column(db.Integer, db.ForeignKey('users.id'))

class SupplyAdjustment(db.Model):
    __tablename__ = 'supply_adjustments'
    id = db.Column(db.Integer, primary_key=True)
    supply_id = db.Column(db.Integer, db.ForeignKey('supplies.id'), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    quantity = db.Column(db.Float, nullable=False)  # + o -
    reason = db.Column(db.Text, nullable=False)
    adjusted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    adjusted_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-058..059: Agua ──

class WaterSource(db.Model):
    __tablename__ = 'water_sources'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    source_type = db.Column(db.String(50))  # pozo, red, represa
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    is_active = db.Column(db.Boolean, default=True)

class WaterAnalysis(db.Model):
    __tablename__ = 'water_analyses'
    id = db.Column(db.Integer, primary_key=True)
    water_source_id = db.Column(db.Integer, db.ForeignKey('water_sources.id'))
    date = db.Column(db.Date, nullable=False)
    ph = db.Column(db.Float)
    ec = db.Column(db.Float)
    notes = db.Column(db.Text)
    analyzed_by = db.Column(db.Integer, db.ForeignKey('users.id'))

# ── TRZ-061..080: Cosecha y poscosecha ──

class HarvestPlan(db.Model):
    __tablename__ = 'harvest_plans'
    id = db.Column(db.Integer, primary_key=True)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    planned_date = db.Column(db.Date)
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    drying_sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    responsibles = db.Column(db.Text)
    sampling_checklist = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), default='Planificada')
    created_at = db.Column(db.DateTime, default=utcnow)
    cul = db.relationship('CUL')

class Batch(db.Model):
    __tablename__ = 'batches'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'), nullable=False)
    batch_type = db.Column(db.String(30))  # cosecha, sublote, proceso
    status = db.Column(db.String(30), default='Activo')  # Activo, Secado, Seco, Curado, Deposito, Retenido, Destruido
    wet_weight = db.Column(db.Float)
    dry_weight = db.Column(db.Float)
    current_weight = db.Column(db.Float)
    quality_category_id = db.Column(db.Integer, db.ForeignKey('quality_categories.id'))
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    container_id = db.Column(db.Integer, db.ForeignKey('containers.id'))
    equipment_used = db.Column(db.String(200))
    harvest_date = db.Column(db.DateTime)
    drying_start = db.Column(db.DateTime)
    drying_end = db.Column(db.DateTime)
    curing_start = db.Column(db.DateTime)
    curing_end = db.Column(db.DateTime)
    parent_batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    cul = db.relationship('CUL')
    quality_category = db.relationship('QualityCategory')
    sector = db.relationship('Sector')
    creator = db.relationship('User')
    sub_batches = db.relationship('Batch', backref=db.backref('parent_batch', remote_side=[id]))

class Container(db.Model):
    __tablename__ = 'containers'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    container_type = db.Column(db.String(50))  # bolsa, tambor, frasco
    sector_id = db.Column(db.Integer, db.ForeignKey('sectors.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    sector = db.relationship('Sector')
    batches = db.relationship('Batch', backref='container_rel', foreign_keys='Batch.container_id')

class WastageRecord(db.Model):
    __tablename__ = 'wastage_records'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    reason_id = db.Column(db.Integer, db.ForeignKey('wastage_reasons.id'))
    quantity = db.Column(db.Float, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))
    date = db.Column(db.DateTime, default=utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    reason = db.relationship('WastageReason')

class DestructionRecord(db.Model):
    __tablename__ = 'destruction_records'
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    quantity = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    act_number = db.Column(db.String(100))
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    date = db.Column(db.DateTime, default=utcnow)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-081..090: Procesamiento ──

class ProcessOrder(db.Model):
    __tablename__ = 'process_orders'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    date = db.Column(db.DateTime, default=utcnow)
    objective = db.Column(db.Text)
    facility = db.Column(db.String(200))
    facility_type = db.Column(db.String(20))  # interno, tercero
    status = db.Column(db.String(30), default='Creada')  # Creada, En proceso, Pendiente aprobacion, Cerrada
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    cleaning_checklist = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    responsible = db.relationship('User', foreign_keys=[responsible_id])
    inputs = db.relationship('ProcessInput', backref='order', lazy='dynamic')
    outputs = db.relationship('ProcessOutput', backref='order', lazy='dynamic')

class ProcessInput(db.Model):
    __tablename__ = 'process_inputs'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('process_orders.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    quantity = db.Column(db.Float, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))

class ProcessOutput(db.Model):
    __tablename__ = 'process_outputs'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('process_orders.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    quantity = db.Column(db.Float, nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))
    is_waste = db.Column(db.Boolean, default=False)
    waste_destination = db.Column(db.String(50))

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-091..097: Calidad ──

class SamplingPlan(db.Model):
    __tablename__ = 'sampling_plans'
    id = db.Column(db.Integer, primary_key=True)
    chemotype = db.Column(db.String(10), nullable=False)
    frequency = db.Column(db.String(50))  # por_cosecha, semestral, anual
    sample_size = db.Column(db.Integer)
    process_points = db.Column(db.Text)
    custody_protocol = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

class Sample(db.Model):
    __tablename__ = 'samples'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    date = db.Column(db.DateTime, default=utcnow)
    sampled_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(30), default='Tomada')  # Tomada, Enviada, Recibida, Con resultado
    lab_name = db.Column(db.String(200))
    sent_at = db.Column(db.DateTime)
    received_at = db.Column(db.DateTime)
    shipping_doc = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)
    cul = db.relationship('CUL')

class LabResult(db.Model):
    __tablename__ = 'lab_results'
    id = db.Column(db.Integer, primary_key=True)
    sample_id = db.Column(db.Integer, db.ForeignKey('samples.id'), nullable=False)
    lab_name = db.Column(db.String(200))
    lab_accredited = db.Column(db.Boolean, default=False)
    analysis_type = db.Column(db.String(50))  # cromatografia, microbiologia
    method = db.Column(db.String(200))
    results = db.Column(db.Text)  # JSON detallado
    coa_reference = db.Column(db.String(200))
    is_conforming = db.Column(db.Boolean)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=utcnow)
    version = db.Column(db.Integer, default=1)
    sample = db.relationship('Sample', backref='results')

class NonConformity(db.Model):
    __tablename__ = 'non_conformities'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50))
    description = db.Column(db.Text, nullable=False)
    severity = db.Column(db.String(20))  # menor, mayor, critica
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    status = db.Column(db.String(30), default='Abierta')  # Abierta, En tratamiento, Cerrada
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    closed_at = db.Column(db.DateTime)

class CAPA(db.Model):
    __tablename__ = 'capas'
    id = db.Column(db.Integer, primary_key=True)
    non_conformity_id = db.Column(db.Integer, db.ForeignKey('non_conformities.id'), nullable=False)
    action = db.Column(db.Text, nullable=False)
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='Pendiente')  # Pendiente, Completada
    completed_at = db.Column(db.DateTime)
    evidence = db.Column(db.Text)
    non_conformity = db.relationship('NonConformity', backref='capas')

# ── TRZ-101..104: Despacho ──

class DispatchOrder(db.Model):
    __tablename__ = 'dispatch_orders'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), unique=True, nullable=False)
    recipient = db.Column(db.String(200), nullable=False)
    recipient_address = db.Column(db.Text)
    date = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(30), default='Creada')  # Creada, Preparada, Despachada, Recibida
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=utcnow)
    creator = db.relationship('User')
    items = db.relationship('DispatchItem', backref='order', lazy='dynamic')

class DispatchItem(db.Model):
    __tablename__ = 'dispatch_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('dispatch_orders.id'), nullable=False)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    container_id = db.Column(db.Integer, db.ForeignKey('containers.id'))
    quantity = db.Column(db.Float)
    unit_id = db.Column(db.Integer, db.ForeignKey('units_of_measure.id'))
    batch = db.relationship('Batch')
    container = db.relationship('Container')

class ReceptionConfirmation(db.Model):
    __tablename__ = 'reception_confirmations'
    id = db.Column(db.Integer, primary_key=True)
    dispatch_order_id = db.Column(db.Integer, db.ForeignKey('dispatch_orders.id'))
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    received_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(30))  # total, parcial
    discrepancies = db.Column(db.Text)
    notes = db.Column(db.Text)

# ── TRZ-105..108: Etiquetas ──

class LabelTemplate(db.Model):
    __tablename__ = 'label_templates'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.Integer, default=1)
    fields = db.Column(db.Text)  # JSON
    status = db.Column(db.String(30), default='Borrador')  # Borrador, Enviada, Aprobada, Rechazada, Vencida
    rpcci_ticket = db.Column(db.String(100))
    rpcci_ticket_date = db.Column(db.Date)
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-109..110: Eventos notificables ──

class NotifiableEvent(db.Model):
    __tablename__ = 'notifiable_events'
    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(100), nullable=False)
    required_fields = db.Column(db.Text)
    required_attachments = db.Column(db.Text)
    sla_days = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

# ── TRZ-111..115: Pacientes ──

class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    internal_id = db.Column(db.String(50), unique=True, nullable=False)
    name_encrypted = db.Column(db.String(500))  # datos sensibles
    organization = db.Column(db.String(200))
    status = db.Column(db.String(20), default='Activo')
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=utcnow)

class PatientAssignment(db.Model):
    __tablename__ = 'patient_assignments'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    cul_id = db.Column(db.Integer, db.ForeignKey('culs.id'))
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'))
    plant_code = db.Column(db.String(100))
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_at = db.Column(db.DateTime, default=utcnow)
    patient = db.relationship('Patient', backref='assignments')

# ── TRZ-121..122: Excepciones ──

class AuthorizedException(db.Model):
    __tablename__ = 'authorized_exceptions'
    id = db.Column(db.Integer, primary_key=True)
    authorization_ref = db.Column(db.String(200), nullable=False)
    scope = db.Column(db.Text)
    valid_from = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    affected_culs = db.Column(db.Text)
    operation_type = db.Column(db.String(50))  # mezcla, split, reclasificacion, etc.
    applied_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    applied_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow)

# ── TRZ-123: Firma digital ──

class DigitalSignature(db.Model):
    __tablename__ = 'digital_signatures'
    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(80), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    signer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    signer_name = db.Column(db.String(200))
    significance = db.Column(db.String(50))  # revision, aprobacion
    signed_at = db.Column(db.DateTime, default=utcnow)
    signer = db.relationship('User')

# ── TRZ-046: Bitácora de accesos ──

class AccessLog(db.Model):
    __tablename__ = 'access_logs'
    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey('sites.id'))
    visitor_name = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.Text)
    area_visited = db.Column(db.String(200))
    date = db.Column(db.DateTime, default=utcnow)
    registered_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    authorization_ref = db.Column(db.String(200))
    site = db.relationship('Site')

# ── TRZ-116..117: Reportes programados ──

class ScheduledReport(db.Model):
    __tablename__ = 'scheduled_reports'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    chemotype = db.Column(db.String(10))
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'))
    frequency = db.Column(db.String(30))  # bimestral, trimestral, semestral
    next_due = db.Column(db.Date)
    last_generated = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

# ── TRZ-124: Validación del sistema ──

class ValidationRecord(db.Model):
    __tablename__ = 'validation_records'
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(10))  # IQ, OQ, PQ
    requirement = db.Column(db.Text)
    test_case = db.Column(db.Text)
    result = db.Column(db.Text)
    version = db.Column(db.String(20))
    validated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    validated_at = db.Column(db.DateTime)

# ── TRZ-127: Retención ──

class RetentionPolicy(db.Model):
    __tablename__ = 'retention_policies'
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(80), nullable=False)
    retention_years = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

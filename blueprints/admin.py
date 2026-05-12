from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, User, Role, UnitOfMeasure, MaterialStatus, EventType, WastageReason,
                    QualityCategory, CustomField, FormTemplate, CodingRule, AuditLog, Supplier,
                    RigorRule, ToleranceConfig, NotifiableEvent, RetentionPolicy, LabelTemplate)
from datetime import datetime, timezone

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin', url_prefix='/admin')

def utcnow():
    return datetime.now(timezone.utc)

def audit(action, entity_type, entity_id, details=''):
    db.session.add(AuditLog(user_id=current_user.id, action=action, entity_type=entity_type, entity_id=entity_id, details=details))

# ── Usuarios (TRZ-004) ──

@admin_bp.route('/users')
@login_required
def users():
    users_list = User.query.all()
    roles = Role.query.all()
    return render_template('users.html', users=users_list, roles=roles)

@admin_bp.route('/users/create', methods=['POST'])
@login_required
def user_create():
    u = User(
        username=request.form['username'],
        email=request.form['email'],
        full_name=request.form.get('full_name', ''),
        role_id=request.form.get('role_id') or None,
        is_active=True
    )
    u.set_password(request.form['password'])
    db.session.add(u)
    db.session.commit()
    audit('CREATE', 'User', u.id, f'Usuario creado: {u.username}')
    db.session.commit()
    flash('Usuario creado.', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:id>/edit', methods=['POST'])
@login_required
def user_edit(id):
    u = User.query.get_or_404(id)
    u.full_name = request.form.get('full_name', u.full_name)
    u.email = request.form.get('email', u.email)
    u.role_id = request.form.get('role_id') or u.role_id
    u.is_active = 'is_active' in request.form
    if request.form.get('password'):
        u.set_password(request.form['password'])
    db.session.commit()
    audit('UPDATE', 'User', u.id, 'Usuario editado')
    db.session.commit()
    flash('Usuario actualizado.', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:id>/toggle', methods=['POST'])
@login_required
def user_toggle(id):
    u = User.query.get_or_404(id)
    u.is_active = not u.is_active
    db.session.commit()
    audit('UPDATE', 'User', u.id, f'Usuario {"activado" if u.is_active else "desactivado"}')
    db.session.commit()
    flash(f'Usuario {"activado" if u.is_active else "desactivado"}.', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/users/<int:id>/unlock', methods=['POST'])
@login_required
def user_unlock(id):
    u = User.query.get_or_404(id)
    u.locked_until = None
    u.failed_attempts = 0
    db.session.commit()
    audit('UPDATE', 'User', u.id, 'Cuenta desbloqueada por admin')
    db.session.commit()
    flash('Cuenta desbloqueada.', 'success')
    return redirect(url_for('admin.users'))

# ── Roles (TRZ-005) ──

@admin_bp.route('/roles')
@login_required
def roles():
    return render_template('roles.html', roles=Role.query.all())

@admin_bp.route('/roles/save', methods=['POST'])
@login_required
def role_save():
    role_id = request.form.get('role_id')
    if role_id:
        r = Role.query.get_or_404(int(role_id))
        r.name = request.form['name']
        r.description = request.form.get('description', '')
        r.permissions = request.form.get('permissions', '')
    else:
        r = Role(name=request.form['name'], description=request.form.get('description', ''), permissions=request.form.get('permissions', ''))
        db.session.add(r)
    db.session.commit()
    flash('Rol guardado.', 'success')
    return redirect(url_for('admin.roles'))

# ── Catálogos genéricos ──

def catalog_crud(model, template, name_field='name'):
    items = model.query.all()
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            item = model.query.get_or_404(int(item_id))
            for field in request.form:
                if field not in ('item_id', 'csrf_token') and hasattr(item, field):
                    val = request.form[field]
                    if field == 'is_active':
                        val = val == 'on' or val == '1'
                    setattr(item, field, val)
        else:
            kwargs = {}
            for field in request.form:
                if field not in ('item_id', 'csrf_token') and hasattr(model, field):
                    kwargs[field] = request.form[field]
            item = model(**kwargs)
            db.session.add(item)
        db.session.commit()
        flash('Guardado.', 'success')
        return redirect(request.url)
    return render_template(template, items=items)

@admin_bp.route('/units', methods=['GET', 'POST'])
@login_required
def units():
    return catalog_crud(UnitOfMeasure, 'catalog.html')

@admin_bp.route('/statuses', methods=['GET', 'POST'])
@login_required
def statuses():
    return catalog_crud(MaterialStatus, 'catalog.html')

@admin_bp.route('/event-types', methods=['GET', 'POST'])
@login_required
def event_types():
    return catalog_crud(EventType, 'catalog.html')

@admin_bp.route('/wastage-reasons', methods=['GET', 'POST'])
@login_required
def wastage_reasons():
    return catalog_crud(WastageReason, 'catalog.html')

@admin_bp.route('/quality-categories', methods=['GET', 'POST'])
@login_required
def quality_categories():
    return catalog_crud(QualityCategory, 'catalog.html')

@admin_bp.route('/suppliers', methods=['GET', 'POST'])
@login_required
def suppliers():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            s = Supplier.query.get_or_404(int(item_id))
            s.name = request.form['name']
            s.contact = request.form.get('contact', '')
            s.phone = request.form.get('phone', '')
            s.email = request.form.get('email', '')
            s.address = request.form.get('address', '')
        else:
            s = Supplier(name=request.form['name'], contact=request.form.get('contact', ''),
                         phone=request.form.get('phone', ''), email=request.form.get('email', ''),
                         address=request.form.get('address', ''))
            db.session.add(s)
        db.session.commit()
        flash('Proveedor guardado.', 'success')
        return redirect(url_for('admin.suppliers'))
    return render_template('suppliers.html', items=Supplier.query.all())

# ── Reglas de codificación (TRZ-018) ──

@admin_bp.route('/coding-rules', methods=['GET', 'POST'])
@login_required
def coding_rules():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            r = CodingRule.query.get_or_404(int(item_id))
        else:
            r = CodingRule()
            db.session.add(r)
        r.rule_type = request.form['rule_type']
        r.pattern = request.form['pattern']
        r.description = request.form.get('description', '')
        r.valid_stages = request.form.get('valid_stages', '')
        r.updated_by = current_user.id
        r.updated_at = utcnow()
        db.session.commit()
        audit('UPDATE', 'CodingRule', r.id, f'Regla {r.rule_type} actualizada')
        db.session.commit()
        flash('Regla guardada.', 'success')
        return redirect(url_for('admin.coding_rules'))
    return render_template('coding_rules.html', rules=CodingRule.query.all())

# ── Tolerancias (TRZ-047) ──

@admin_bp.route('/tolerances', methods=['GET', 'POST'])
@login_required
def tolerances():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            t = ToleranceConfig.query.get_or_404(int(item_id))
        else:
            t = ToleranceConfig()
            db.session.add(t)
        t.chemotype = request.form['chemotype']
        t.tolerance_pct = float(request.form['tolerance_pct'])
        t.applies_to = request.form.get('applies_to', '')
        db.session.commit()
        flash('Tolerancia guardada.', 'success')
        return redirect(url_for('admin.tolerances'))
    return render_template('tolerances.html', items=ToleranceConfig.query.all())

# ── Rigurosidad (TRZ-034) ──

@admin_bp.route('/rigor-rules', methods=['GET', 'POST'])
@login_required
def rigor_rules():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            r = RigorRule.query.get_or_404(int(item_id))
        else:
            r = RigorRule()
            db.session.add(r)
        r.activity = request.form['activity']
        r.chemotype = request.form.get('chemotype', '')
        r.rigor_level = request.form['rigor_level']
        r.tracking_mode = request.form.get('tracking_mode', '')
        r.report_frequency = request.form.get('report_frequency', '')
        db.session.commit()
        flash('Regla guardada.', 'success')
        return redirect(url_for('admin.rigor_rules'))
    return render_template('rigor_rules.html', items=RigorRule.query.all())

# ── Auditoría ──

@admin_bp.route('/audit-log')
@login_required
def audit_log():
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=50)
    return render_template('audit_log.html', logs=logs)

# ── Plantillas de etiqueta (TRZ-105..108) ──

@admin_bp.route('/label-templates', methods=['GET', 'POST'])
@login_required
def label_templates():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            lt = LabelTemplate.query.get_or_404(int(item_id))
        else:
            lt = LabelTemplate()
            db.session.add(lt)
        lt.name = request.form['name']
        lt.fields = request.form.get('fields', '')
        lt.status = request.form.get('status', 'Borrador')
        lt.rpcci_ticket = request.form.get('rpcci_ticket', '')
        db.session.commit()
        flash('Plantilla guardada.', 'success')
        return redirect(url_for('admin.label_templates'))
    return render_template('label_templates.html', items=LabelTemplate.query.all())

# ── Retención (TRZ-127) ──

@admin_bp.route('/retention', methods=['GET', 'POST'])
@login_required
def retention():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        if item_id:
            r = RetentionPolicy.query.get_or_404(int(item_id))
        else:
            r = RetentionPolicy()
            db.session.add(r)
        r.record_type = request.form['record_type']
        r.retention_years = int(request.form['retention_years'])
        db.session.commit()
        flash('Política guardada.', 'success')
        return redirect(url_for('admin.retention'))
    return render_template('retention.html', items=RetentionPolicy.query.all())

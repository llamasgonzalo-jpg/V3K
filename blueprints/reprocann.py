"""
V3K Network — Blueprint REPROCANN (Fase 1)
Autoregistro, dashboard, trazabilidad personal, reporte RPCCI con georreferenciación.
"""
import os
import uuid
from datetime import datetime, timezone, timedelta, date
from functools import wraps

from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, current_app, send_from_directory, abort, jsonify, send_file)
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.utils import secure_filename

from models import (db, User, Role, ProfileType, UserProfile, Subscription,
                    VerificationDocument, ReprocannCultivo, ReprocannEvent,
                    ReprocannHarvest, AuditLog)

reprocann_bp = Blueprint('reprocann', __name__,
                         template_folder='../templates/reprocann',
                         url_prefix='/network')

def utcnow():
    return datetime.now(timezone.utc)

# ── Decoradores de acceso ─────────────────────────────────────

def reprocann_required(f):
    """Solo cultivadores REPROCANN pueden acceder a estas rutas."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('reprocann.login'))
        profile = UserProfile.query.filter_by(user_id=current_user.id).first()
        if not profile or not profile.profile_type or \
           profile.profile_type.code not in ('cultivador_reprocann', 'moderador_v3k'):
            flash('Esta sección es solo para cultivadores REPROCANN.', 'warning')
            return redirect(url_for('reprocann.home'))
        return f(*args, **kwargs)
    return decorated

def subscription_active_required(f):
    """Solo usuarios con suscripción activa pueden hacer cambios."""
    @wraps(f)
    def decorated(*args, **kwargs):
        sub = Subscription.query.filter_by(user_id=current_user.id).first()
        # Moderadores siempre pasan
        profile = UserProfile.query.filter_by(user_id=current_user.id).first()
        if profile and profile.profile_type and profile.profile_type.code == 'moderador_v3k':
            return f(*args, **kwargs)
        if not sub or sub.status != 'active':
            flash('Tu suscripción no está activa. Comunicate con el administrador.', 'warning')
            return redirect(url_for('reprocann.dashboard'))
        if sub.expires_at and sub.expires_at < datetime.now(timezone.utc):
            sub.status = 'expired'
            db.session.commit()
            flash('Tu suscripción venció. Renová para seguir operando.', 'danger')
            return redirect(url_for('reprocann.dashboard'))
        return f(*args, **kwargs)
    return decorated

def moderator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('reprocann.login'))
        profile = UserProfile.query.filter_by(user_id=current_user.id).first()
        is_mod = profile and profile.profile_type and profile.profile_type.code == 'moderador_v3k'
        is_admin = current_user.role and current_user.role.name == 'Administrador'
        if not (is_mod or is_admin):
            abort(403)
        return f(*args, **kwargs)
    return decorated

# ── Home pública / Landing ────────────────────────────────────

@reprocann_bp.route('/')
def home():
    return render_template('reprocann/landing.html')

# ── Autoregistro ──────────────────────────────────────────────

PROFILE_ROLE_MAP = {
    'cultivador_reprocann': 'Cultivador REPROCANN',
    'ong':                  'ONG',
    'fitomejorador':        'Fitomejorador',
    'empresa':              'Empresa',
    'laboratorio':          'Laboratorio',
}

@reprocann_bp.route('/registro', methods=['GET', 'POST'])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for('reprocann.post_login_redirect'))

    if request.method == 'POST':
        profile_type_code = request.form.get('profile_type', '').strip()
        email = request.form['email'].strip().lower()
        username = request.form['username'].strip()
        password = request.form['password']
        password2 = request.form['password2']
        full_name = request.form['full_name'].strip()
        dni = request.form.get('dni', '').strip()
        phone = request.form.get('phone', '').strip()
        province = request.form.get('province', '').strip()
        city = request.form.get('city', '').strip()
        accepted_terms = request.form.get('accepted_terms') == 'on'

        # Validaciones
        if profile_type_code not in PROFILE_ROLE_MAP:
            flash('Tipo de perfil inválido.', 'danger')
            return redirect(url_for('reprocann.registro'))
        if not accepted_terms:
            flash('Debés aceptar los términos y condiciones.', 'danger')
            return redirect(url_for('reprocann.registro'))
        if password != password2:
            flash('Las contraseñas no coinciden.', 'danger')
            return redirect(url_for('reprocann.registro'))
        if len(password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres.', 'danger')
            return redirect(url_for('reprocann.registro'))
        if User.query.filter_by(email=email).first():
            flash('Ya existe una cuenta con ese email.', 'danger')
            return redirect(url_for('reprocann.registro'))
        if User.query.filter_by(username=username).first():
            flash('Ese nombre de usuario ya está en uso.', 'danger')
            return redirect(url_for('reprocann.registro'))

        # Crear/obtener rol según el tipo de perfil
        role_name = PROFILE_ROLE_MAP[profile_type_code]
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name,
                        description=f'Usuario auto-registrado de V3K Network ({role_name})',
                        permissions=profile_type_code)
            db.session.add(role)
            db.session.flush()

        # Crear usuario
        u = User(username=username, email=email, full_name=full_name,
                 role_id=role.id, is_active=True)
        u.set_password(password)
        db.session.add(u)
        db.session.flush()

        pt = ProfileType.query.filter_by(code=profile_type_code).first()

        # Crear perfil con campos específicos según tipo
        extra_bio_parts = []
        if profile_type_code == 'cultivador_reprocann':
            reprocann_number = request.form.get('reprocann_number', '').strip()
            doctor_name = request.form.get('doctor_name', '').strip()
            profile_kwargs = dict(reprocann_number=reprocann_number, doctor_name=doctor_name)
        elif profile_type_code == 'ong':
            if request.form.get('ong_personeria'):
                extra_bio_parts.append(f"Personería jurídica: {request.form['ong_personeria']}")
            if request.form.get('ong_pacientes'):
                extra_bio_parts.append(f"Pacientes estimados: {request.form['ong_pacientes']}")
            profile_kwargs = {}
        elif profile_type_code == 'fitomejorador':
            if request.form.get('inase_matricula'):
                extra_bio_parts.append(f"Matrícula INASE: {request.form['inase_matricula']}")
            if request.form.get('spig_code'):
                extra_bio_parts.append(f"SPIG-BCP: {request.form['spig_code']}")
            profile_kwargs = {}
        elif profile_type_code == 'empresa':
            if request.form.get('ariccame'):
                extra_bio_parts.append(f"ARICCAME: {request.form['ariccame']}")
            if request.form.get('iname'):
                extra_bio_parts.append(f"INAME: {request.form['iname']}")
            profile_kwargs = {}
        elif profile_type_code == 'laboratorio':
            if request.form.get('lab_habilitacion'):
                extra_bio_parts.append(f"Habilitación: {request.form['lab_habilitacion']}")
            if request.form.get('lab_iso'):
                extra_bio_parts.append(f"ISO 17025: {request.form['lab_iso']}")
            profile_kwargs = {}
        else:
            profile_kwargs = {}

        profile = UserProfile(
            user_id=u.id, profile_type_id=pt.id if pt else None,
            dni=dni, phone=phone, province=province, city=city,
            bio=' | '.join(extra_bio_parts) if extra_bio_parts else None,
            verification_status='pending',
            profile_visibility='private',
            accepted_terms=True,
            accepted_terms_at=utcnow(),
            **profile_kwargs
        )
        db.session.add(profile)

        # Trial gratuito de 7 días al registrarse
        now = utcnow()
        sub = Subscription(
            user_id=u.id, profile_type_id=pt.id if pt else None,
            status='active',
            starts_at=now,
            expires_at=now + timedelta(days=7),
            payment_method='trial',
            notes='Trial gratuito de 7 días otorgado al registrarse'
        )
        db.session.add(sub)

        # Audit
        db.session.add(AuditLog(
            user_id=u.id, action='SIGNUP', entity_type='User', entity_id=u.id,
            details=f'Autoregistro V3K Network [{profile_type_code}]: {email}',
            ip_address=request.remote_addr
        ))

        db.session.commit()
        login_user(u)
        flash(f'¡Bienvenido a V3K Network! Completá tu perfil y cargá la documentación para verificar tu cuenta de {pt.name if pt else "usuario"}.', 'success')
        return redirect(url_for('reprocann.post_login_redirect'))

    return render_template('reprocann/registro.html')

# ── Post-login: enrutar al panel correcto según tipo de perfil ─

@reprocann_bp.route('/inicio')
@login_required
def post_login_redirect():
    """Decide a qué panel mandar al usuario según su perfil."""
    # Auto-activación de trial 7 días si el usuario nunca tuvo activación
    sub = Subscription.query.filter_by(user_id=current_user.id).first()
    if sub and sub.status == 'pending' and not sub.starts_at:
        now = utcnow()
        sub.status = 'active'
        sub.starts_at = now
        sub.expires_at = now + timedelta(days=7)
        sub.payment_method = 'trial'
        sub.notes = 'Trial gratuito 7 días activado automáticamente'
        db.session.commit()

    # Admin → panel de moderación (su dashboard real en V3K Network)
    if current_user.role and current_user.role.name == 'Administrador':
        return redirect(url_for('reprocann.moderacion'))
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not profile or not profile.profile_type:
        return redirect(url_for('reprocann.perfil'))
    code = profile.profile_type.code
    if code == 'cultivador_reprocann':
        return redirect(url_for('reprocann.dashboard'))
    if code == 'moderador_v3k':
        return redirect(url_for('reprocann.moderacion'))
    if code == 'empresa':
        return redirect(url_for('main.dashboard'))
    # ONG / Fitomejorador / Laboratorio → panel placeholder
    return redirect(url_for('reprocann.proximamente', tipo=code))

@reprocann_bp.route('/proximamente/<tipo>')
@login_required
def proximamente(tipo):
    pt = ProfileType.query.filter_by(code=tipo).first()
    return render_template('reprocann/proximamente.html', profile_type=pt)

# ── Login propio (puede usar el principal también) ────────────

@reprocann_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('reprocann.post_login_redirect'))
    if request.method == 'POST':
        ident = request.form['username'].strip()
        password = request.form['password']
        u = User.query.filter((User.username == ident) | (User.email == ident)).first()
        if u and u.check_password(password) and u.is_active:
            login_user(u)
            u.last_login = utcnow()
            u.last_activity = utcnow()  # evita que check_session_timeout expire la sesión recién creada
            db.session.commit()
            return redirect(url_for('reprocann.post_login_redirect'))
        flash('Credenciales inválidas.', 'danger')
    return render_template('reprocann/login.html')

# ── Dashboard del cultivador ──────────────────────────────────

@reprocann_bp.route('/dashboard')
@login_required
@reprocann_required
def dashboard():
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    sub = Subscription.query.filter_by(user_id=current_user.id).first()
    # Si por algún motivo no existe suscripción, la creamos en pending
    if not sub:
        pt = profile.profile_type if profile else None
        sub = Subscription(user_id=current_user.id,
                           profile_type_id=pt.id if pt else None,
                           status='pending')
        db.session.add(sub)
        db.session.commit()
    cultivos = ReprocannCultivo.query.filter_by(user_id=current_user.id).order_by(ReprocannCultivo.created_at.desc()).all()
    total_plants = sum(c.plant_count or 0 for c in cultivos if c.status == 'active')
    total_harvested = db.session.query(db.func.coalesce(db.func.sum(ReprocannHarvest.dry_weight_g), 0))\
                        .filter(ReprocannHarvest.user_id == current_user.id).scalar() or 0
    recent_events = ReprocannEvent.query.filter_by(user_id=current_user.id)\
                    .order_by(ReprocannEvent.event_date.desc()).limit(10).all()
    return render_template('reprocann/dashboard.html',
                           profile=profile, subscription=sub, cultivos=cultivos,
                           total_plants=total_plants, total_harvested=total_harvested,
                           recent_events=recent_events)

# ── Perfil del usuario ────────────────────────────────────────

@reprocann_bp.route('/perfil', methods=['GET', 'POST'])
@login_required
def perfil():
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        flash('Perfil no encontrado.', 'danger')
        return redirect(url_for('reprocann.home'))
    if request.method == 'POST':
        profile.dni = request.form.get('dni', '').strip()
        profile.phone = request.form.get('phone', '').strip()
        profile.address = request.form.get('address', '').strip()
        profile.city = request.form.get('city', '').strip()
        profile.province = request.form.get('province', '').strip()
        profile.postal_code = request.form.get('postal_code', '').strip()
        if request.form.get('birth_date'):
            profile.birth_date = datetime.strptime(request.form['birth_date'], '%Y-%m-%d').date()
        profile.reprocann_number = request.form.get('reprocann_number', '').strip()
        if request.form.get('reprocann_expiry'):
            profile.reprocann_expiry = datetime.strptime(request.form['reprocann_expiry'], '%Y-%m-%d').date()
        profile.doctor_name = request.form.get('doctor_name', '').strip()
        profile.doctor_matricula = request.form.get('doctor_matricula', '').strip()
        profile.pathology = request.form.get('pathology', '').strip()
        profile.bio = request.form.get('bio', '').strip()
        profile.profile_visibility = request.form.get('profile_visibility', 'private')
        if current_user.full_name != request.form.get('full_name', '').strip():
            current_user.full_name = request.form.get('full_name', '').strip()
        db.session.commit()
        flash('Perfil actualizado.', 'success')
        return redirect(url_for('reprocann.perfil'))
    docs = VerificationDocument.query.filter_by(user_id=current_user.id).all()
    return render_template('reprocann/perfil.html', profile=profile, docs=docs)

# ── Subir documentos de verificación ──────────────────────────

@reprocann_bp.route('/perfil/upload-doc', methods=['POST'])
@login_required
def upload_doc():
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        abort(404)
    doc_type = request.form.get('document_type')
    file = request.files.get('file')
    if not file or not doc_type:
        flash('Faltan datos.', 'danger')
        return redirect(url_for('reprocann.perfil'))
    # Validación básica
    allowed = {'png', 'jpg', 'jpeg', 'pdf'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        flash('Formato no permitido. Usá PNG, JPG o PDF.', 'danger')
        return redirect(url_for('reprocann.perfil'))
    # Crear carpeta del usuario si no existe
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'reprocann', str(current_user.id))
    os.makedirs(upload_dir, exist_ok=True)
    fname = f"{doc_type}_{uuid.uuid4().hex[:8]}.{ext}"
    fpath = os.path.join(upload_dir, fname)
    file.save(fpath)
    # Registrar
    rel_path = os.path.join('reprocann', str(current_user.id), fname)
    doc = VerificationDocument(
        user_id=current_user.id, document_type=doc_type,
        file_path=rel_path, original_filename=file.filename,
        file_size=os.path.getsize(fpath)
    )
    db.session.add(doc)
    # Cambiar estado a en revisión si estaba pendiente
    if profile.verification_status == 'pending':
        profile.verification_status = 'in_review'
        profile.verification_submitted_at = utcnow()
    db.session.commit()
    flash('Documento subido correctamente.', 'success')
    return redirect(url_for('reprocann.perfil'))

# ── Servir uploads protegidos ─────────────────────────────────

@reprocann_bp.route('/uploads/<path:filename>')
@login_required
def uploaded_file(filename):
    # Solo el dueño o moderadores pueden ver sus uploads
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    is_mod = profile and profile.profile_type and profile.profile_type.code == 'moderador_v3k'
    is_admin = current_user.role and current_user.role.name == 'Administrador'
    # Normalizar separadores (Windows → Linux)
    filename = filename.replace('\\', '/')
    parts = filename.split('/')
    if len(parts) >= 2 and parts[0] == 'reprocann':
        owner_id = int(parts[1]) if parts[1].isdigit() else None
        if owner_id != current_user.id and not (is_mod or is_admin):
            abort(403)
    import pathlib
    full_path = pathlib.Path(current_app.config['UPLOAD_FOLDER']) / filename
    if not full_path.exists():
        flash('El archivo no está disponible. El servidor fue actualizado y los archivos anteriores se perdieron. Pedile al usuario que vuelva a subir el documento.', 'warning')
        return redirect(request.referrer or url_for('reprocann.moderacion'))
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

# ── Cultivos: listado y creación ──────────────────────────────

@reprocann_bp.route('/cultivos')
@login_required
@reprocann_required
def cultivos():
    items = ReprocannCultivo.query.filter_by(user_id=current_user.id)\
            .order_by(ReprocannCultivo.created_at.desc()).all()
    return render_template('reprocann/cultivos.html', cultivos=items)

@reprocann_bp.route('/cultivos/nuevo', methods=['GET', 'POST'])
@login_required
@reprocann_required
@subscription_active_required
def cultivo_nuevo():
    if request.method == 'POST':
        # Validar límite REPROCANN: 9 plantas activas
        active_plants = db.session.query(db.func.coalesce(db.func.sum(ReprocannCultivo.plant_count), 0))\
            .filter(ReprocannCultivo.user_id == current_user.id,
                    ReprocannCultivo.status == 'active').scalar() or 0
        new_count = int(request.form.get('plant_count', 1))
        if active_plants + new_count > 9:
            flash(f'Excede el límite REPROCANN de 9 plantas activas (actualmente tenés {active_plants}).', 'danger')
            return redirect(url_for('reprocann.cultivo_nuevo'))

        c = ReprocannCultivo(
            user_id=current_user.id,
            name=request.form['name'].strip(),
            variety=request.form.get('variety', '').strip(),
            environment=request.form.get('environment', 'interior'),
            plant_count=new_count,
            stage=request.form.get('stage', 'vegetativo'),
            address=request.form.get('address', '').strip(),
            latitude=float(request.form['latitude']) if request.form.get('latitude') else None,
            longitude=float(request.form['longitude']) if request.form.get('longitude') else None,
            surface_m2=float(request.form['surface_m2']) if request.form.get('surface_m2') else None,
            is_public=request.form.get('is_public') == 'on',
            notes=request.form.get('notes', '').strip(),
        )
        if request.form.get('start_date'):
            c.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        if request.form.get('expected_harvest_date'):
            c.expected_harvest_date = datetime.strptime(request.form['expected_harvest_date'], '%Y-%m-%d').date()
        db.session.add(c)
        db.session.commit()
        flash(f'Cultivo "{c.name}" creado.', 'success')
        return redirect(url_for('reprocann.cultivo_detail', id=c.id))
    return render_template('reprocann/cultivo_form.html', cultivo=None)

@reprocann_bp.route('/cultivos/<int:id>')
@login_required
@reprocann_required
def cultivo_detail(id):
    c = ReprocannCultivo.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    events = c.events.order_by(ReprocannEvent.event_date.desc()).all()
    harvests = c.harvests.order_by(ReprocannHarvest.harvest_date.desc()).all()
    return render_template('reprocann/cultivo_detail.html',
                           cultivo=c, events=events, harvests=harvests)

@reprocann_bp.route('/cultivos/<int:id>/editar', methods=['GET', 'POST'])
@login_required
@reprocann_required
@subscription_active_required
def cultivo_edit(id):
    c = ReprocannCultivo.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        c.name = request.form['name'].strip()
        c.variety = request.form.get('variety', '').strip()
        c.environment = request.form.get('environment', 'interior')
        c.plant_count = int(request.form.get('plant_count', 1))
        c.stage = request.form.get('stage', 'vegetativo')
        c.address = request.form.get('address', '').strip()
        c.latitude = float(request.form['latitude']) if request.form.get('latitude') else None
        c.longitude = float(request.form['longitude']) if request.form.get('longitude') else None
        c.surface_m2 = float(request.form['surface_m2']) if request.form.get('surface_m2') else None
        c.is_public = request.form.get('is_public') == 'on'
        c.notes = request.form.get('notes', '').strip()
        if request.form.get('start_date'):
            c.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        if request.form.get('expected_harvest_date'):
            c.expected_harvest_date = datetime.strptime(request.form['expected_harvest_date'], '%Y-%m-%d').date()
        db.session.commit()
        flash('Cultivo actualizado.', 'success')
        return redirect(url_for('reprocann.cultivo_detail', id=c.id))
    return render_template('reprocann/cultivo_form.html', cultivo=c)

@reprocann_bp.route('/cultivos/<int:id>/eliminar', methods=['POST'])
@login_required
@reprocann_required
@subscription_active_required
def cultivo_delete(id):
    c = ReprocannCultivo.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    name = c.name
    db.session.delete(c)
    db.session.commit()
    flash(f'Cultivo "{name}" eliminado.', 'success')
    return redirect(url_for('reprocann.cultivos'))

# ── Eventos del cultivo ───────────────────────────────────────

@reprocann_bp.route('/cultivos/<int:id>/evento', methods=['POST'])
@login_required
@reprocann_required
@subscription_active_required
def event_create(id):
    c = ReprocannCultivo.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    ev = ReprocannEvent(
        cultivo_id=c.id, user_id=current_user.id,
        event_type=request.form.get('event_type', 'observacion'),
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip(),
    )
    if request.form.get('event_date'):
        ev.event_date = datetime.strptime(request.form['event_date'], '%Y-%m-%dT%H:%M')
    # Foto opcional
    photo = request.files.get('photo')
    if photo and photo.filename:
        ext = photo.filename.rsplit('.', 1)[-1].lower()
        if ext in {'png', 'jpg', 'jpeg', 'webp'}:
            upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'reprocann', str(current_user.id), 'fotos')
            os.makedirs(upload_dir, exist_ok=True)
            fname = f"ev_{uuid.uuid4().hex[:10]}.{ext}"
            photo.save(os.path.join(upload_dir, fname))
            ev.photo_path = os.path.join('reprocann', str(current_user.id), 'fotos', fname)
    # Cambiar etapa si corresponde
    if ev.event_type == 'cambio_etapa' and request.form.get('new_stage'):
        c.stage = request.form['new_stage']
    db.session.add(ev)
    db.session.commit()
    flash('Evento registrado.', 'success')
    return redirect(url_for('reprocann.cultivo_detail', id=c.id))

# ── Cosechas ──────────────────────────────────────────────────

@reprocann_bp.route('/cultivos/<int:id>/cosecha', methods=['POST'])
@login_required
@reprocann_required
@subscription_active_required
def harvest_create(id):
    c = ReprocannCultivo.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    h = ReprocannHarvest(
        cultivo_id=c.id, user_id=current_user.id,
        harvest_date=datetime.strptime(request.form['harvest_date'], '%Y-%m-%d').date(),
        wet_weight_g=float(request.form['wet_weight_g']) if request.form.get('wet_weight_g') else None,
        dry_weight_g=float(request.form['dry_weight_g']) if request.form.get('dry_weight_g') else None,
        purpose=request.form.get('purpose', '').strip(),
        notes=request.form.get('notes', '').strip(),
    )
    db.session.add(h)
    # Marcar cultivo como cosechado
    c.stage = 'cosecha'
    c.actual_harvest_date = h.harvest_date
    db.session.commit()
    flash('Cosecha registrada.', 'success')
    return redirect(url_for('reprocann.cultivo_detail', id=c.id))

# ── Reporte RPCCI (PDF) ───────────────────────────────────────

@reprocann_bp.route('/reporte/rpcci')
@login_required
@reprocann_required
def reporte_rpcci():
    """Vista HTML del reporte (descarga PDF aparte)."""
    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    cultivos = ReprocannCultivo.query.filter_by(user_id=current_user.id).all()
    harvests = ReprocannHarvest.query.filter_by(user_id=current_user.id)\
               .order_by(ReprocannHarvest.harvest_date.desc()).all()
    total_dry = sum(h.dry_weight_g or 0 for h in harvests)
    total_plants_active = sum(c.plant_count or 0 for c in cultivos if c.status == 'active')
    fecha_hoy_ar = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime('%d/%m/%Y')
    return render_template('reprocann/reporte_rpcci.html',
                           profile=profile, user=current_user, cultivos=cultivos,
                           harvests=harvests, total_dry=total_dry,
                           total_plants_active=total_plants_active,
                           fecha_hoy=fecha_hoy_ar)

@reprocann_bp.route('/reporte/rpcci/pdf')
@login_required
@reprocann_required
def reporte_rpcci_pdf():
    """Generación de PDF del reporte RPCCI."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle, PageBreak, Image as RLImage)
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    profile = UserProfile.query.filter_by(user_id=current_user.id).first()
    cultivos = ReprocannCultivo.query.filter_by(user_id=current_user.id).all()
    harvests = ReprocannHarvest.query.filter_by(user_id=current_user.id)\
               .order_by(ReprocannHarvest.harvest_date.desc()).all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.5*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=18,
                        textColor=colors.HexColor('#1a8fd1'), alignment=TA_CENTER, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=11,
                        textColor=colors.HexColor('#0a5fa0'), spaceAfter=4, spaceBefore=8)
    body = ParagraphStyle('body', parent=styles['Normal'], fontSize=9, leading=12)
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8,
                           textColor=colors.HexColor('#666666'), alignment=TA_CENTER)

    story = []

    # Encabezado con logo
    logo_path = os.path.join(current_app.root_path, 'static', 'img', 'v3k-network-logo.png')
    if os.path.exists(logo_path):
        story.append(RLImage(logo_path, width=4*cm, height=1.8*cm, hAlign='CENTER'))
        story.append(Spacer(1, 4))

    story.append(Paragraph('REPORTE DE TRAZABILIDAD — RPCCI', h1))
    story.append(Paragraph('Sistema V3K Network · Ley 9617 / Ley 27350', small))
    fecha_ar = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(f'Generado: {fecha_ar} (hora Argentina)', small))
    story.append(Spacer(1, 14))

    # Datos del cultivador
    story.append(Paragraph('1. DATOS DEL CULTIVADOR', h2))
    cult_data = [
        ['Nombre completo:',     current_user.full_name or '-'],
        ['Email:',               current_user.email],
        ['DNI:',                 profile.dni if profile else '-'],
        ['Teléfono:',            profile.phone if profile else '-'],
        ['Nº REPROCANN:',        profile.reprocann_number if profile else '-'],
        ['Vencimiento REPROCANN:', profile.reprocann_expiry.strftime('%d/%m/%Y') if (profile and profile.reprocann_expiry) else '-'],
        ['Médico tratante:',     profile.doctor_name if profile else '-'],
        ['Matrícula médica:',    profile.doctor_matricula if profile else '-'],
        ['Patología:',           profile.pathology if profile else '-'],
        ['Domicilio:',           f"{profile.address or ''} - {profile.city or ''}, {profile.province or ''}" if profile else '-'],
    ]
    t = Table(cult_data, colWidths=[5*cm, 11.4*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#f5f6fa'), colors.white]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#e8e8e8')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Resumen
    story.append(Paragraph('2. RESUMEN DE PRODUCCIÓN', h2))
    total_active = sum(c.plant_count or 0 for c in cultivos if c.status == 'active')
    total_dry = sum(h.dry_weight_g or 0 for h in harvests)
    res_data = [
        ['Cultivos totales:',    str(len(cultivos))],
        ['Cultivos activos:',    str(sum(1 for c in cultivos if c.status == 'active'))],
        ['Plantas activas:',     f"{total_active} (límite legal: 9)"],
        ['Cosechas registradas:', str(len(harvests))],
        ['Producción total seca:', f"{total_dry:.1f} g"],
    ]
    t = Table(res_data, colWidths=[6*cm, 10.4*cm])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#e8f4fc'), colors.white]),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#1a8fd1')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Cultivos con georreferenciación
    story.append(Paragraph('3. CULTIVOS REGISTRADOS', h2))
    if not cultivos:
        story.append(Paragraph('Sin cultivos registrados.', body))
    else:
        for i, c in enumerate(cultivos, 1):
            story.append(Paragraph(f"<b>{i}. {c.name}</b> — {c.variety or 'Sin variedad'}", body))
            geo = '-'
            if c.latitude and c.longitude:
                geo = f"Lat: {c.latitude:.6f}, Long: {c.longitude:.6f}"
            cult_data = [
                ['Variedad:',         c.variety or '-'],
                ['Ambiente:',         (c.environment or '-').capitalize()],
                ['Plantas:',          str(c.plant_count or 0)],
                ['Etapa actual:',     (c.stage or '-').capitalize()],
                ['Estado:',           (c.status or '-').capitalize()],
                ['Inicio:',           c.start_date.strftime('%d/%m/%Y') if c.start_date else '-'],
                ['Cosecha estimada:', c.expected_harvest_date.strftime('%d/%m/%Y') if c.expected_harvest_date else '-'],
                ['Cosecha real:',     c.actual_harvest_date.strftime('%d/%m/%Y') if c.actual_harvest_date else '-'],
                ['Superficie:',       f"{c.surface_m2:.1f} m²" if c.surface_m2 else '-'],
                ['Dirección:',        c.address or '-'],
                ['Georreferencia:',   geo],
            ]
            tc = Table(cult_data, colWidths=[4*cm, 12.4*cm])
            tc.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.HexColor('#fafafa'), colors.white]),
                ('BOX', (0, 0), (-1, -1), 0.4, colors.HexColor('#cccccc')),
                ('INNERGRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#eeeeee')),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(tc)
            story.append(Spacer(1, 8))

    # Cosechas
    if harvests:
        story.append(Paragraph('4. COSECHAS', h2))
        h_data = [['Fecha', 'Cultivo', 'Peso fresco (g)', 'Peso seco (g)', 'Destino']]
        for h in harvests:
            cult = ReprocannCultivo.query.get(h.cultivo_id)
            h_data.append([
                h.harvest_date.strftime('%d/%m/%Y'),
                cult.name if cult else '-',
                f"{h.wet_weight_g:.1f}" if h.wet_weight_g else '-',
                f"{h.dry_weight_g:.1f}" if h.dry_weight_g else '-',
                h.purpose or '-',
            ])
        th = Table(h_data, colWidths=[2.5*cm, 5.5*cm, 2.8*cm, 2.8*cm, 2.8*cm])
        th.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a8fd1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f5f8fc'), colors.white]),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#1a8fd1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.2, colors.HexColor('#cccccc')),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(th)
        story.append(Spacer(1, 12))

    # Pie de página: declaración jurada
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        '<i>El usuario declara bajo carácter de declaración jurada que la información '
        'aquí registrada se corresponde con la actividad de autocultivo realizada al '
        'amparo de su inscripción en el REPROCANN, conforme a la Ley 27350 y la Ley '
        'Provincial 9617 de Mendoza.</i>', body))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f'________________________________<br/>{current_user.full_name or current_user.username}<br/>DNI: {profile.dni if profile else "-"}',
                            ParagraphStyle('sig', parent=body, alignment=TA_CENTER)))

    doc.build(story)
    buffer.seek(0)
    filename = f"reporte_rpcci_{current_user.username}_{date.today().isoformat()}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)

# ═══════════════════════════════════════════════════════════════
#  MODERACIÓN — Solo moderadores y administradores
# ═══════════════════════════════════════════════════════════════

@reprocann_bp.route('/moderacion')
@login_required
@moderator_required
def moderacion():
    now = datetime.now(timezone.utc)
    seven_days = now + timedelta(days=7)

    # ── Conteos por tipo de perfil ──
    profile_types = ProfileType.query.filter(ProfileType.code != 'moderador_v3k').all()
    stats_by_type = []
    for pt in profile_types:
        count = UserProfile.query.filter_by(profile_type_id=pt.id).count()
        stats_by_type.append({
            'code':  pt.code,
            'name':  pt.name,
            'price': float(pt.monthly_price or 0),
            'icon':  pt.icon or 'bi-person',
            'color': pt.color or '#1a8fd1',
            'count': count,
        })

    # ── Conteos de verificación ──
    total_usuarios = UserProfile.query.count()
    verificados    = UserProfile.query.filter_by(verification_status='verified').count()
    pendientes_ver = UserProfile.query.filter(UserProfile.verification_status.in_(['pending', 'in_review'])).count()
    rechazados     = UserProfile.query.filter_by(verification_status='rejected').count()

    # ── Conteos de suscripción ──
    subs_activas    = Subscription.query.filter_by(status='active').count()
    subs_pendientes = Subscription.query.filter_by(status='pending').count()
    subs_vencidas   = Subscription.query.filter_by(status='expired').count()
    subs_canceladas = Subscription.query.filter_by(status='cancelled').count()

    # ── Ingresos esperados (suma del precio del ProfileType de cada suscripción activa) ──
    ingresos_mensuales = db.session.query(
        db.func.coalesce(db.func.sum(ProfileType.monthly_price), 0)
    ).select_from(Subscription).join(ProfileType, Subscription.profile_type_id == ProfileType.id)\
     .filter(Subscription.status == 'active').scalar() or 0

    # Pagos del mes corriente (cobrado real)
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ingresos_mes = db.session.query(db.func.coalesce(db.func.sum(Subscription.last_payment_amount), 0))\
        .filter(Subscription.last_payment_at >= inicio_mes).scalar() or 0

    # ── Listas urgentes ──
    pendientes = UserProfile.query.filter(UserProfile.verification_status.in_(['pending', 'in_review']))\
                 .order_by(UserProfile.created_at.desc()).limit(8).all()
    subs_a_cobrar = Subscription.query.filter_by(status='pending')\
                    .order_by(Subscription.created_at.desc()).limit(8).all()
    proximos_vencimientos = Subscription.query.filter(
        Subscription.status == 'active',
        Subscription.expires_at != None,
        Subscription.expires_at <= seven_days
    ).order_by(Subscription.expires_at.asc()).limit(8).all()

    # ── Registros recientes (últimas semanas) ──
    recent_signups = UserProfile.query.order_by(UserProfile.created_at.desc()).limit(8).all()

    return render_template('reprocann/moderacion.html',
        stats_by_type=stats_by_type,
        total_usuarios=total_usuarios,
        verificados=verificados, pendientes_ver=pendientes_ver, rechazados=rechazados,
        subs_activas=subs_activas, subs_pendientes=subs_pendientes,
        subs_vencidas=subs_vencidas, subs_canceladas=subs_canceladas,
        ingresos_mensuales=float(ingresos_mensuales),
        ingresos_mes=float(ingresos_mes),
        pendientes=pendientes, subs_a_cobrar=subs_a_cobrar,
        proximos_vencimientos=proximos_vencimientos,
        recent_signups=recent_signups,
    )

# ── Listado de usuarios con filtros ──

@reprocann_bp.route('/moderacion/usuarios')
@login_required
@moderator_required
def moderacion_usuarios():
    profile_type = request.args.get('profile_type', '')
    status       = request.args.get('status', '')  # verification status
    q            = request.args.get('q', '').strip()

    query = UserProfile.query.join(User, UserProfile.user_id == User.id)\
                             .outerjoin(ProfileType, UserProfile.profile_type_id == ProfileType.id)
    if profile_type:
        query = query.filter(ProfileType.code == profile_type)
    if status:
        query = query.filter(UserProfile.verification_status == status)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(User.username.ilike(like), User.email.ilike(like),
                                    User.full_name.ilike(like), UserProfile.dni.ilike(like)))

    usuarios = query.order_by(UserProfile.created_at.desc()).all()
    profile_types = ProfileType.query.filter(ProfileType.code != 'moderador_v3k').all()

    return render_template('reprocann/moderacion_usuarios.html',
                           usuarios=usuarios, profile_types=profile_types,
                           filtro_tipo=profile_type, filtro_estado=status, filtro_q=q)

# ── Listado de suscripciones con filtros ──

@reprocann_bp.route('/moderacion/suscripciones')
@login_required
@moderator_required
def moderacion_suscripciones():
    status = request.args.get('status', '')
    profile_type = request.args.get('profile_type', '')

    query = Subscription.query.join(User, Subscription.user_id == User.id)\
                              .outerjoin(ProfileType, Subscription.profile_type_id == ProfileType.id)
    if status:
        query = query.filter(Subscription.status == status)
    if profile_type:
        query = query.filter(ProfileType.code == profile_type)

    subs = query.order_by(Subscription.created_at.desc()).all()
    profile_types = ProfileType.query.filter(ProfileType.code != 'moderador_v3k').all()

    return render_template('reprocann/moderacion_suscripciones.html',
                           subs=subs, profile_types=profile_types,
                           filtro_estado=status, filtro_tipo=profile_type)

@reprocann_bp.route('/moderacion/usuario/<int:user_id>')
@login_required
@moderator_required
def moderacion_usuario(user_id):
    u = User.query.get_or_404(user_id)
    profile = UserProfile.query.filter_by(user_id=user_id).first()
    sub = Subscription.query.filter_by(user_id=user_id).first()
    docs = VerificationDocument.query.filter_by(user_id=user_id).all()
    return render_template('reprocann/moderacion_usuario.html',
                           u=u, profile=profile, sub=sub, docs=docs)

@reprocann_bp.route('/moderacion/usuario/<int:user_id>/verificar', methods=['POST'])
@login_required
@moderator_required
def moderacion_verificar(user_id):
    profile = UserProfile.query.filter_by(user_id=user_id).first_or_404()
    accion = request.form.get('accion')  # approve / reject
    notas = request.form.get('notes', '').strip()
    if accion == 'approve':
        profile.verification_status = 'verified'
        profile.verified_at = utcnow()
        profile.verified_by = current_user.id
        msg = 'Usuario verificado correctamente.'
    elif accion == 'reject':
        profile.verification_status = 'rejected'
        msg = 'Verificación rechazada.'
    profile.verification_notes = notas
    db.session.add(AuditLog(
        user_id=current_user.id, action=f'VERIFY_{accion.upper()}',
        entity_type='UserProfile', entity_id=profile.id,
        details=f'Verificación {accion} a user_id={user_id}: {notas}',
        ip_address=request.remote_addr
    ))
    db.session.commit()
    flash(msg, 'success')
    return redirect(url_for('reprocann.moderacion_usuario', user_id=user_id))

@reprocann_bp.route('/moderacion/usuario/<int:user_id>/activar-pago', methods=['POST'])
@login_required
@moderator_required
def moderacion_activar_pago(user_id):
    sub = Subscription.query.filter_by(user_id=user_id).first_or_404()
    months = int(request.form.get('months', 1))
    amount = float(request.form.get('amount', 5000))
    method = request.form.get('payment_method', 'manual')
    ref = request.form.get('payment_reference', '').strip()
    now = utcnow()
    sub.status = 'active'
    sub.starts_at = sub.starts_at or now
    base = sub.expires_at if (sub.expires_at and sub.expires_at > now) else now
    sub.expires_at = base + timedelta(days=30 * months)
    sub.last_payment_at = now
    sub.last_payment_amount = amount
    sub.payment_method = method
    sub.payment_reference = ref
    db.session.add(AuditLog(
        user_id=current_user.id, action='SUBSCRIPTION_ACTIVATE',
        entity_type='Subscription', entity_id=sub.id,
        details=f'Activación pago {months} mes(es), ${amount}, ref: {ref}',
        ip_address=request.remote_addr
    ))
    db.session.commit()
    flash(f'Suscripción activa hasta el {sub.expires_at.strftime("%d/%m/%Y")}.', 'success')
    return redirect(url_for('reprocann.moderacion_usuario', user_id=user_id))

@reprocann_bp.route('/moderacion/usuario/<int:user_id>/desactivar', methods=['POST'])
@login_required
@moderator_required
def moderacion_desactivar(user_id):
    sub = Subscription.query.filter_by(user_id=user_id).first_or_404()
    sub.status = 'cancelled'
    db.session.add(AuditLog(
        user_id=current_user.id, action='SUBSCRIPTION_CANCEL',
        entity_type='Subscription', entity_id=sub.id,
        details='Cancelado por moderador',
        ip_address=request.remote_addr
    ))
    db.session.commit()
    flash('Suscripción cancelada.', 'warning')
    return redirect(url_for('reprocann.moderacion_usuario', user_id=user_id))

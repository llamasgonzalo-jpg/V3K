from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, AuditLog

auth_bp = Blueprint('auth', __name__, template_folder='../templates/auth')

def utcnow():
    return datetime.now(timezone.utc)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if user and user.is_locked():
            flash('Cuenta bloqueada temporalmente. Intente más tarde.', 'danger')
            return render_template('login.html')
        if user and user.is_active and user.check_password(password):
            user.failed_attempts = 0
            user.last_login = utcnow()
            user.last_activity = utcnow()
            db.session.commit()
            login_user(user)
            db.session.add(AuditLog(user_id=user.id, action='LOGIN', details='Inicio de sesión exitoso', ip_address=request.remote_addr))
            db.session.commit()
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        if user:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            max_attempts = current_app.config.get('MAX_LOGIN_ATTEMPTS', 5)
            if user.failed_attempts >= max_attempts:
                lockout_min = current_app.config.get('LOCKOUT_MINUTES', 15)
                user.locked_until = utcnow() + timedelta(minutes=lockout_min)
                db.session.add(AuditLog(user_id=user.id, action='LOCKOUT', details=f'Cuenta bloqueada tras {max_attempts} intentos', ip_address=request.remote_addr))
            db.session.commit()
        flash('Credenciales inválidas.', 'danger')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    db.session.add(AuditLog(user_id=current_user.id, action='LOGOUT', details='Cierre de sesión', ip_address=request.remote_addr))
    db.session.commit()
    logout_user()
    flash('Sesión cerrada correctamente.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/password-reset', methods=['GET', 'POST'])
def password_reset():
    if request.method == 'POST':
        flash('Si el email existe, recibirá instrucciones para restablecer su contraseña.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('password_reset.html')

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_pw = request.form.get('current_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')
        if not current_user.check_password(current_pw):
            flash('Contraseña actual incorrecta.', 'danger')
        elif new_pw != confirm_pw:
            flash('Las contraseñas no coinciden.', 'danger')
        elif len(new_pw) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            flash('Contraseña actualizada.', 'success')
    return render_template('profile.html')

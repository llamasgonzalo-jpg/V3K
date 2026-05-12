from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import db, Patient, PatientAssignment, CUL, Batch
from datetime import datetime

patients_bp = Blueprint('patients', __name__, template_folder='../templates/patients', url_prefix='/patients')

# ── Pacientes (TRZ-111..115) ──

@patients_bp.route('/')
@login_required
def patient_list():
    return render_template('patients.html', patients=Patient.query.all())

@patients_bp.route('/save', methods=['POST'])
@login_required
def patient_save():
    pid = request.form.get('patient_id')
    if pid:
        p = Patient.query.get_or_404(int(pid))
    else:
        p = Patient()
        db.session.add(p)
    p.internal_id = request.form['internal_id']
    p.name_encrypted = request.form.get('name_encrypted', '')
    p.organization = request.form.get('organization', '')
    p.status = request.form.get('status', 'Activo')
    if request.form.get('valid_from'):
        p.valid_from = datetime.strptime(request.form['valid_from'], '%Y-%m-%d').date()
    if request.form.get('valid_until'):
        p.valid_until = datetime.strptime(request.form['valid_until'], '%Y-%m-%d').date()
    p.notes = request.form.get('notes', '')
    db.session.commit()
    flash('Paciente guardado.', 'success')
    return redirect(url_for('patients.patient_list'))

@patients_bp.route('/<int:id>')
@login_required
def patient_detail(id):
    p = Patient.query.get_or_404(id)
    return render_template('patient_detail.html', patient=p, assignments=p.assignments,
                           culs=CUL.query.all(), batches=Batch.query.all())

@patients_bp.route('/<int:id>/assign', methods=['POST'])
@login_required
def assign(id):
    a = PatientAssignment(
        patient_id=id,
        cul_id=int(request.form['cul_id']) if request.form.get('cul_id') else None,
        batch_id=int(request.form['batch_id']) if request.form.get('batch_id') else None,
        plant_code=request.form.get('plant_code', ''),
        assigned_by=current_user.id
    )
    db.session.add(a)
    db.session.commit()
    flash('Asignación creada.', 'success')
    return redirect(url_for('patients.patient_detail', id=id))

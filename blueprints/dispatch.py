from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, DispatchOrder, DispatchItem, ReceptionConfirmation, Batch, Container,
                    UnitOfMeasure, AuditLog, PatientAssignment)
from datetime import datetime, timezone
import random, string

dispatch_bp = Blueprint('dispatch', __name__, template_folder='../templates/dispatch', url_prefix='/dispatch')

# ── Órdenes de despacho (TRZ-101..102) ──

@dispatch_bp.route('/orders')
@login_required
def orders():
    return render_template('dispatch_orders.html',
                           orders=DispatchOrder.query.order_by(DispatchOrder.created_at.desc()).all())

@dispatch_bp.route('/orders/create', methods=['POST'])
@login_required
def order_create():
    code = f"DSP-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
    o = DispatchOrder(
        code=code,
        recipient=request.form['recipient'],
        recipient_address=request.form.get('recipient_address', ''),
        notes=request.form.get('notes', ''),
        created_by=current_user.id
    )
    db.session.add(o)
    db.session.commit()
    flash(f'Orden {code} creada.', 'success')
    return redirect(url_for('dispatch.order_detail', id=o.id))

@dispatch_bp.route('/orders/<int:id>')
@login_required
def order_detail(id):
    o = DispatchOrder.query.get_or_404(id)
    batches = Batch.query.filter(Batch.status.in_(['Deposito', 'Seco'])).filter(Batch.current_weight > 0).all()
    return render_template('dispatch_order_detail.html', order=o, items=o.items.all(),
                           batches=batches, containers=Container.query.all(),
                           units=UnitOfMeasure.query.all())

@dispatch_bp.route('/orders/<int:id>/add-item', methods=['POST'])
@login_required
def add_item(id):
    batch_id = int(request.form['batch_id']) if request.form.get('batch_id') else None
    # Check patient assignment conflicts (TRZ-113)
    if batch_id:
        batch = Batch.query.get(batch_id)
        if batch and batch.status == 'Retenido':
            flash('No se puede despachar un batch retenido.', 'danger')
            return redirect(url_for('dispatch.order_detail', id=id))
        if batch and batch.cul and batch.cul.is_blocked:
            flash('No se puede despachar: CUL bloqueado.', 'danger')
            return redirect(url_for('dispatch.order_detail', id=id))
    di = DispatchItem(
        order_id=id,
        batch_id=batch_id,
        container_id=int(request.form['container_id']) if request.form.get('container_id') else None,
        quantity=float(request.form['quantity']) if request.form.get('quantity') else None,
        unit_id=int(request.form['unit_id']) if request.form.get('unit_id') else None
    )
    db.session.add(di)
    db.session.commit()
    flash('Ítem agregado.', 'success')
    return redirect(url_for('dispatch.order_detail', id=id))

@dispatch_bp.route('/orders/<int:id>/dispatch', methods=['POST'])
@login_required
def do_dispatch(id):
    o = DispatchOrder.query.get_or_404(id)
    o.status = 'Despachada'
    o.date = datetime.now(timezone.utc)
    for item in o.items:
        if item.batch_id:
            batch = Batch.query.get(item.batch_id)
            if batch and item.quantity:
                batch.current_weight = (batch.current_weight or 0) - item.quantity
    db.session.add(AuditLog(user_id=current_user.id, action='DISPATCH', entity_type='DispatchOrder',
                            entity_id=id, details=f'Despacho {o.code}'))
    db.session.commit()
    flash('Despacho realizado.', 'success')
    return redirect(url_for('dispatch.order_detail', id=id))

# ── Recepción (TRZ-103) ──

@dispatch_bp.route('/orders/<int:id>/confirm-reception', methods=['POST'])
@login_required
def confirm_reception(id):
    o = DispatchOrder.query.get_or_404(id)
    rc = ReceptionConfirmation(
        dispatch_order_id=id,
        received_by=current_user.id,
        status=request.form.get('status', 'total'),
        discrepancies=request.form.get('discrepancies', ''),
        notes=request.form.get('notes', '')
    )
    o.status = 'Recibida'
    db.session.add(rc)
    db.session.commit()
    flash('Recepción confirmada.', 'success')
    return redirect(url_for('dispatch.order_detail', id=id))

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, ProcessOrder, ProcessInput, ProcessOutput, Batch, Product,
                    UnitOfMeasure, AuditLog)
from datetime import datetime, timezone
import random, string

proc_bp = Blueprint('processing', __name__, template_folder='../templates/processing', url_prefix='/processing')

# ── Órdenes de proceso (TRZ-081..090) ──

@proc_bp.route('/orders')
@login_required
def orders():
    return render_template('process_orders.html', orders=ProcessOrder.query.order_by(ProcessOrder.created_at.desc()).all())

@proc_bp.route('/orders/create', methods=['POST'])
@login_required
def order_create():
    code = f"OP-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
    o = ProcessOrder(
        code=code,
        objective=request.form.get('objective', ''),
        facility=request.form.get('facility', ''),
        facility_type=request.form.get('facility_type', 'interno'),
        responsible_id=current_user.id,
        notes=request.form.get('notes', '')
    )
    db.session.add(o)
    db.session.commit()
    flash(f'Orden {code} creada.', 'success')
    return redirect(url_for('processing.order_detail', id=o.id))

@proc_bp.route('/orders/<int:id>')
@login_required
def order_detail(id):
    o = ProcessOrder.query.get_or_404(id)
    return render_template('process_order_detail.html', order=o,
                           batches=Batch.query.filter(Batch.current_weight > 0).all(),
                           products=Product.query.all(),
                           units=UnitOfMeasure.query.all())

@proc_bp.route('/orders/<int:id>/add-input', methods=['POST'])
@login_required
def add_input(id):
    pi = ProcessInput(
        order_id=id,
        batch_id=int(request.form['batch_id']),
        quantity=float(request.form['quantity']),
        unit_id=int(request.form['unit_id']) if request.form.get('unit_id') else None
    )
    db.session.add(pi)
    o = ProcessOrder.query.get(id)
    if o.status == 'Creada':
        o.status = 'En proceso'
    db.session.commit()
    flash('Entrada agregada.', 'success')
    return redirect(url_for('processing.order_detail', id=id))

@proc_bp.route('/orders/<int:id>/add-output', methods=['POST'])
@login_required
def add_output(id):
    is_waste = 'is_waste' in request.form
    batch_id = None
    if not is_waste:
        code = f"PROC-{datetime.now().strftime('%Y%m%d')}-{''.join(random.choices(string.digits, k=4))}"
        # Get CUL from first input
        first_input = ProcessInput.query.filter_by(order_id=id).first()
        cul_id = first_input.batch_id if first_input else None
        if first_input and first_input.batch_id:
            src = Batch.query.get(first_input.batch_id)
            cul_id = src.cul_id if src else None
        b = Batch(code=code, cul_id=cul_id or 0, batch_type='proceso',
                  current_weight=float(request.form['quantity']),
                  created_by=current_user.id)
        db.session.add(b)
        db.session.flush()
        batch_id = b.id
    po = ProcessOutput(
        order_id=id,
        batch_id=batch_id,
        product_id=int(request.form['product_id']) if request.form.get('product_id') else None,
        quantity=float(request.form['quantity']),
        unit_id=int(request.form['unit_id']) if request.form.get('unit_id') else None,
        is_waste=is_waste,
        waste_destination=request.form.get('waste_destination', '')
    )
    db.session.add(po)
    db.session.commit()
    flash('Salida registrada.', 'success')
    return redirect(url_for('processing.order_detail', id=id))

@proc_bp.route('/orders/<int:id>/close', methods=['POST'])
@login_required
def order_close(id):
    o = ProcessOrder.query.get_or_404(id)
    o.status = 'Cerrada'
    o.approved_by = current_user.id
    o.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('Orden cerrada.', 'success')
    return redirect(url_for('processing.order_detail', id=id))

# ── Productos (TRZ-087) ──

@proc_bp.route('/products')
@login_required
def products():
    return render_template('products.html', products=Product.query.all(),
                           units=UnitOfMeasure.query.all())

@proc_bp.route('/products/save', methods=['POST'])
@login_required
def product_save():
    pid = request.form.get('product_id')
    if pid:
        p = Product.query.get_or_404(int(pid))
    else:
        p = Product()
        db.session.add(p)
    p.sku = request.form['sku']
    p.name = request.form['name']
    p.unit_id = int(request.form['unit_id']) if request.form.get('unit_id') else None
    db.session.commit()
    flash('Producto guardado.', 'success')
    return redirect(url_for('processing.products'))

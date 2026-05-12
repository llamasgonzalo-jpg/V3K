from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, Supply, SupplyReception, SupplyStock, SupplyConsumption, SupplyAdjustment,
                    Supplier, Warehouse, UnitOfMeasure, Notification)
from datetime import datetime, timezone

inv_bp = Blueprint('inventory', __name__, template_folder='../templates/inventory', url_prefix='/inventory')

def utcnow():
    return datetime.now(timezone.utc)

@inv_bp.route('/supplies')
@login_required
def supplies():
    return render_template('supplies.html', supplies=Supply.query.all(),
                           units=UnitOfMeasure.query.filter_by(is_active=True).all())

@inv_bp.route('/supplies/save', methods=['POST'])
@login_required
def supply_save():
    sid = request.form.get('supply_id')
    if sid:
        s = Supply.query.get_or_404(int(sid))
    else:
        s = Supply()
        db.session.add(s)
    s.name = request.form['name']
    s.category = request.form.get('category', '')
    s.unit_id = int(request.form['unit_id']) if request.form.get('unit_id') else None
    s.min_stock = float(request.form['min_stock']) if request.form.get('min_stock') else 0
    db.session.commit()
    flash('Insumo guardado.', 'success')
    return redirect(url_for('inventory.supplies'))

# ── Recepción (TRZ-051) ──

@inv_bp.route('/receptions')
@login_required
def receptions():
    recs = SupplyReception.query.order_by(SupplyReception.received_at.desc()).all()
    return render_template('supply_receptions.html', receptions=recs, supplies=Supply.query.all(),
                           suppliers=Supplier.query.all(), warehouses=Warehouse.query.all())

@inv_bp.route('/receptions/create', methods=['POST'])
@login_required
def reception_create():
    r = SupplyReception(
        supply_id=int(request.form['supply_id']),
        supplier_id=int(request.form['supplier_id']) if request.form.get('supplier_id') else None,
        warehouse_id=int(request.form['warehouse_id']) if request.form.get('warehouse_id') else None,
        batch_lot=request.form.get('batch_lot', ''),
        quantity=float(request.form['quantity']),
        expiry_date=datetime.strptime(request.form['expiry_date'], '%Y-%m-%d').date() if request.form.get('expiry_date') else None,
        received_by=current_user.id
    )
    db.session.add(r)
    # Actualizar stock
    if r.warehouse_id:
        stock = SupplyStock.query.filter_by(supply_id=r.supply_id, warehouse_id=r.warehouse_id).first()
        if stock:
            stock.quantity += r.quantity
        else:
            stock = SupplyStock(supply_id=r.supply_id, warehouse_id=r.warehouse_id, quantity=r.quantity)
            db.session.add(stock)
    db.session.commit()
    flash('Recepción registrada.', 'success')
    return redirect(url_for('inventory.receptions'))

# ── Stock (TRZ-053) ──

@inv_bp.route('/stock')
@login_required
def stock():
    stocks = db.session.query(SupplyStock, Supply, Warehouse).join(Supply).join(Warehouse).all()
    # Alertas de stock mínimo (TRZ-054)
    alerts = []
    for ss, supply, wh in stocks:
        if supply.min_stock and ss.quantity < supply.min_stock:
            alerts.append({'supply': supply.name, 'warehouse': wh.name, 'current': ss.quantity, 'min': supply.min_stock})
    # Alertas de vencimiento (TRZ-055)
    from datetime import timedelta
    soon = datetime.now().date() + timedelta(days=30)
    expiring = SupplyReception.query.filter(SupplyReception.expiry_date != None, SupplyReception.expiry_date <= soon).all()
    return render_template('stock.html', stocks=stocks, alerts=alerts, expiring=expiring)

# ── Consumo (TRZ-052) ──

@inv_bp.route('/consumption/create', methods=['POST'])
@login_required
def consumption_create():
    supply_id = int(request.form['supply_id'])
    warehouse_id = int(request.form['warehouse_id']) if request.form.get('warehouse_id') else None
    quantity = float(request.form['quantity'])
    # Verificar stock
    if warehouse_id:
        stock = SupplyStock.query.filter_by(supply_id=supply_id, warehouse_id=warehouse_id).first()
        if not stock or stock.quantity < quantity:
            flash('Stock insuficiente.', 'danger')
            return redirect(request.referrer or url_for('inventory.stock'))
        stock.quantity -= quantity
    c = SupplyConsumption(
        supply_id=supply_id,
        warehouse_id=warehouse_id,
        event_id=int(request.form['event_id']) if request.form.get('event_id') else None,
        quantity=quantity,
        consumed_by=current_user.id
    )
    db.session.add(c)
    db.session.commit()
    # Check min stock alert
    if warehouse_id:
        stock = SupplyStock.query.filter_by(supply_id=supply_id, warehouse_id=warehouse_id).first()
        supply = Supply.query.get(supply_id)
        if stock and supply and supply.min_stock and stock.quantity < supply.min_stock:
            n = Notification(user_id=current_user.id, type='stock_min',
                            title=f'Stock bajo: {supply.name}',
                            message=f'Stock actual: {stock.quantity}. Mínimo: {supply.min_stock}')
            db.session.add(n)
            db.session.commit()
    flash('Consumo registrado.', 'success')
    return redirect(request.referrer or url_for('inventory.stock'))

# ── Ajustes (TRZ-056) ──

@inv_bp.route('/adjustments')
@login_required
def adjustments():
    adjs = SupplyAdjustment.query.order_by(SupplyAdjustment.adjusted_at.desc()).all()
    return render_template('adjustments.html', adjustments=adjs, supplies=Supply.query.all(),
                           warehouses=Warehouse.query.all())

@inv_bp.route('/adjustments/create', methods=['POST'])
@login_required
def adjustment_create():
    supply_id = int(request.form['supply_id'])
    warehouse_id = int(request.form['warehouse_id']) if request.form.get('warehouse_id') else None
    quantity = float(request.form['quantity'])
    a = SupplyAdjustment(
        supply_id=supply_id,
        warehouse_id=warehouse_id,
        quantity=quantity,
        reason=request.form['reason'],
        adjusted_by=current_user.id
    )
    db.session.add(a)
    if warehouse_id:
        stock = SupplyStock.query.filter_by(supply_id=supply_id, warehouse_id=warehouse_id).first()
        if stock:
            stock.quantity += quantity
        else:
            stock = SupplyStock(supply_id=supply_id, warehouse_id=warehouse_id, quantity=quantity)
            db.session.add(stock)
    db.session.commit()
    flash('Ajuste registrado.', 'success')
    return redirect(url_for('inventory.adjustments'))

# ── Reporte consumo por lote (TRZ-060) ──

@inv_bp.route('/consumption-report')
@login_required
def consumption_report():
    consumptions = SupplyConsumption.query.order_by(SupplyConsumption.date.desc()).all()
    return render_template('consumption_report.html', consumptions=consumptions)

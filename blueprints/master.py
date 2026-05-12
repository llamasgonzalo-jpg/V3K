from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from models import (db, Site, Sector, SectorLink, Campaign, Genetic, MotherPlant,
                    FloweringGroup, WaterSource, WaterAnalysis, Warehouse, AuditLog)
from datetime import datetime, timezone

master_bp = Blueprint('master', __name__, template_folder='../templates/master', url_prefix='/master')

def audit(action, etype, eid, details=''):
    db.session.add(AuditLog(user_id=current_user.id, action=action, entity_type=etype, entity_id=eid, details=details))

# ── Predios (TRZ-019) ──

@master_bp.route('/sites')
@login_required
def sites():
    return render_template('sites.html', sites=Site.query.all())

@master_bp.route('/sites/save', methods=['POST'])
@login_required
def site_save():
    site_id = request.form.get('site_id')
    if site_id:
        s = Site.query.get_or_404(int(site_id))
    else:
        s = Site()
        db.session.add(s)
    s.name = request.form['name']
    s.address = request.form.get('address', '')
    s.cadastral_code = request.form.get('cadastral_code', '')
    s.latitude = float(request.form['latitude']) if request.form.get('latitude') else None
    s.longitude = float(request.form['longitude']) if request.form.get('longitude') else None
    s.total_area = float(request.form['total_area']) if request.form.get('total_area') else None
    s.effective_area = float(request.form['effective_area']) if request.form.get('effective_area') else None
    db.session.commit()
    audit('SAVE', 'Site', s.id, s.name)
    db.session.commit()
    flash('Predio guardado.', 'success')
    return redirect(url_for('master.sites'))

# ── Sectores (TRZ-020) ──

@master_bp.route('/sites/<int:site_id>/sectors')
@login_required
def sectors(site_id):
    site = Site.query.get_or_404(site_id)
    return render_template('sectors.html', site=site, sectors=site.sectors.all(),
                           links=SectorLink.query.join(Sector, SectorLink.origin_id == Sector.id).filter(Sector.site_id == site_id).all())

@master_bp.route('/sectors/save', methods=['POST'])
@login_required
def sector_save():
    sector_id = request.form.get('sector_id')
    if sector_id:
        s = Sector.query.get_or_404(int(sector_id))
    else:
        s = Sector()
        db.session.add(s)
    s.site_id = int(request.form['site_id'])
    s.name = request.form['name']
    s.sector_type = request.form['sector_type']
    s.capacity = int(request.form['capacity']) if request.form.get('capacity') else None
    db.session.commit()
    flash('Sector guardado.', 'success')
    return redirect(url_for('master.sectors', site_id=s.site_id))

@master_bp.route('/sector-links/save', methods=['POST'])
@login_required
def sector_link_save():
    sl = SectorLink(origin_id=int(request.form['origin_id']), destination_id=int(request.form['destination_id']))
    db.session.add(sl)
    db.session.commit()
    flash('Vínculo creado.', 'success')
    site_id = request.form.get('site_id', 1)
    return redirect(url_for('master.sectors', site_id=site_id))

# ── Campañas (TRZ-021) ──

@master_bp.route('/campaigns')
@login_required
def campaigns():
    return render_template('campaigns.html', campaigns=Campaign.query.all(), sites=Site.query.all())

@master_bp.route('/campaigns/save', methods=['POST'])
@login_required
def campaign_save():
    cid = request.form.get('campaign_id')
    if cid:
        c = Campaign.query.get_or_404(int(cid))
    else:
        c = Campaign()
        db.session.add(c)
    c.name = request.form['name']
    c.site_id = int(request.form['site_id']) if request.form.get('site_id') else None
    c.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else None
    c.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date() if request.form.get('end_date') else None
    db.session.commit()
    flash('Campaña guardada.', 'success')
    return redirect(url_for('master.campaigns'))

@master_bp.route('/campaigns/<int:id>/close', methods=['POST'])
@login_required
def campaign_close(id):
    c = Campaign.query.get_or_404(id)
    c.is_closed = True
    db.session.commit()
    flash('Campaña cerrada.', 'success')
    return redirect(url_for('master.campaigns'))

# ── Genéticas (TRZ-027) ──

@master_bp.route('/genetics')
@login_required
def genetics():
    return render_template('genetics.html', genetics=Genetic.query.all())

@master_bp.route('/genetics/save', methods=['POST'])
@login_required
def genetic_save():
    gid = request.form.get('genetic_id')
    if gid:
        g = Genetic.query.get_or_404(int(gid))
    else:
        g = Genetic()
        db.session.add(g)
    g.name = request.form['name']
    g.code = request.form.get('code', '')
    g.origin = request.form.get('origin', '')
    g.expected_chemotype = request.form.get('expected_chemotype', '')
    g.registry_status = request.form.get('registry_status', '')
    g.spig_code = request.form.get('spig_code', '')
    if request.form.get('registry_expiry'):
        g.registry_expiry = datetime.strptime(request.form['registry_expiry'], '%Y-%m-%d').date()
    db.session.commit()
    flash('Genética guardada.', 'success')
    return redirect(url_for('master.genetics'))

# ── Grupos de Floración (TRZ-008) ──

@master_bp.route('/flowering-groups')
@login_required
def flowering_groups():
    return render_template('flowering_groups.html', groups=FloweringGroup.query.all())

@master_bp.route('/flowering-groups/save', methods=['POST'])
@login_required
def flowering_group_save():
    fid = request.form.get('group_id')
    if fid:
        fg = FloweringGroup.query.get_or_404(int(fid))
    else:
        fg = FloweringGroup()
        db.session.add(fg)
    fg.code = request.form['code']
    fg.name = request.form.get('name', '')
    fg.purpose = request.form.get('purpose', '')
    fg.variety = request.form.get('variety', '')
    fg.environment = request.form.get('environment', '')
    db.session.commit()
    flash('Grupo de floración guardado.', 'success')
    return redirect(url_for('master.flowering_groups'))

# ── Plantas madre (TRZ-028) ──

@master_bp.route('/mother-plants')
@login_required
def mother_plants():
    return render_template('mother_plants.html', plants=MotherPlant.query.all(),
                           genetics=Genetic.query.all(), sites=Site.query.all())

@master_bp.route('/mother-plants/save', methods=['POST'])
@login_required
def mother_plant_save():
    pid = request.form.get('plant_id')
    if pid:
        p = MotherPlant.query.get_or_404(int(pid))
    else:
        p = MotherPlant()
        db.session.add(p)
    p.code = request.form['code']
    p.genetic_id = int(request.form['genetic_id']) if request.form.get('genetic_id') else None
    p.site_id = int(request.form['site_id']) if request.form.get('site_id') else None
    p.notes = request.form.get('notes', '')
    db.session.commit()
    flash('Planta madre guardada.', 'success')
    return redirect(url_for('master.mother_plants'))

# ── Fuentes de agua (TRZ-058..059) ──

@master_bp.route('/water-sources')
@login_required
def water_sources():
    return render_template('water_sources.html', sources=WaterSource.query.all(),
                           sites=Site.query.all(), analyses=WaterAnalysis.query.order_by(WaterAnalysis.date.desc()).all())

@master_bp.route('/water-sources/save', methods=['POST'])
@login_required
def water_source_save():
    wid = request.form.get('source_id')
    if wid:
        w = WaterSource.query.get_or_404(int(wid))
    else:
        w = WaterSource()
        db.session.add(w)
    w.name = request.form['name']
    w.source_type = request.form.get('source_type', '')
    w.site_id = int(request.form['site_id']) if request.form.get('site_id') else None
    db.session.commit()
    flash('Fuente guardada.', 'success')
    return redirect(url_for('master.water_sources'))

@master_bp.route('/water-analysis/save', methods=['POST'])
@login_required
def water_analysis_save():
    a = WaterAnalysis(
        water_source_id=int(request.form['water_source_id']),
        date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
        ph=float(request.form['ph']) if request.form.get('ph') else None,
        ec=float(request.form['ec']) if request.form.get('ec') else None,
        notes=request.form.get('notes', ''),
        analyzed_by=current_user.id
    )
    db.session.add(a)
    db.session.commit()
    flash('Análisis guardado.', 'success')
    return redirect(url_for('master.water_sources'))

# ── Depósitos (TRZ-053) ──

@master_bp.route('/warehouses')
@login_required
def warehouses():
    return render_template('warehouses.html', warehouses=Warehouse.query.all(), sites=Site.query.all())

@master_bp.route('/warehouses/save', methods=['POST'])
@login_required
def warehouse_save():
    wid = request.form.get('warehouse_id')
    if wid:
        w = Warehouse.query.get_or_404(int(wid))
    else:
        w = Warehouse()
        db.session.add(w)
    w.name = request.form['name']
    w.site_id = int(request.form['site_id']) if request.form.get('site_id') else None
    db.session.commit()
    flash('Depósito guardado.', 'success')
    return redirect(url_for('master.warehouses'))

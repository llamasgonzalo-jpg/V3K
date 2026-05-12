// Dynamic sector loading based on site selection
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('select[data-load-sectors]').forEach(function(sel) {
        sel.addEventListener('change', function() {
            var target = document.getElementById(sel.dataset.loadSectors);
            if (!target) return;
            var siteId = sel.value;
            if (!siteId) { target.innerHTML = '<option value="">-- Seleccione --</option>'; return; }
            fetch('/cultivation/api/sectors/' + siteId)
                .then(r => r.json())
                .then(data => {
                    target.innerHTML = '<option value="">-- Seleccione --</option>';
                    data.forEach(s => {
                        target.innerHTML += '<option value="'+s.id+'">'+s.name+' ('+s.type+')</option>';
                    });
                });
        });
    });

    // Auto-dismiss alerts after 5 seconds
    document.querySelectorAll('.alert-dismissible').forEach(function(alert) {
        setTimeout(function() { var btn = alert.querySelector('.btn-close'); if (btn) btn.click(); }, 5000);
    });

    // Confirm dangerous actions
    document.querySelectorAll('[data-confirm]').forEach(function(el) {
        el.addEventListener('click', function(e) {
            if (!confirm(el.dataset.confirm)) e.preventDefault();
        });
    });
});

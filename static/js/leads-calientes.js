/**
 * Leads calientes: campana en navbar para GERENTE / DIRECTOR_ADMINISTRATIVO.
 * Polling al API, dropdown con tarjetas y botón "Tomar control".
 */
(function () {
    'use strict';

    if (!window.LEADS_CALIENTES_API_LIST) return;

    var API_LIST = window.LEADS_CALIENTES_API_LIST;
    var POLL_INTERVAL_MS = 25000;

    function getCsrfToken() {
        var name = 'csrftoken';
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var c = cookies[i].trim();
            if (c.indexOf(name + '=') === 0) return c.substring(name.length + 1);
        }
        return '';
    }

    function fetchLeads() {
        return fetch(API_LIST, {
            method: 'GET',
            headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin'
        }).then(function (r) {
            if (!r.ok) throw new Error('Error ' + r.status);
            return r.json();
        });
    }

    function tomarControl(idUsuario) {
        var url = API_LIST.replace(/\/?$/, '') + '/' + encodeURIComponent(idUsuario) + '/tomar-control/';
        return fetch(url, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({})
        }).then(function (r) {
            if (!r.ok) throw new Error('Error ' + r.status);
            return r.json();
        });
    }

    function platformIcon(plataforma) {
        var p = (plataforma || '').toLowerCase();
        if (p === 'whatsapp') return 'fab fa-whatsapp text-success';
        if (p === 'instagram') return 'fab fa-instagram text-danger';
        if (p === 'facebook') return 'fab fa-facebook-messenger text-primary';
        return 'fas fa-comment';
    }

    function renderList(leads) {
        var listEl = document.getElementById('leads-calientes-list');
        var emptyEl = document.getElementById('leads-calientes-empty');
        var badge = document.getElementById('leads-calientes-badge');
        var countHeader = document.getElementById('leads-calientes-count-header');
        var icon = document.getElementById('leads-calientes-icon');

        var count = leads.length;
        if (countHeader) countHeader.textContent = count;
        if (badge) {
            badge.textContent = count;
            badge.style.display = count > 0 ? 'inline-block' : 'none';
        }
        if (icon) {
            icon.classList.remove('text-warning', 'fa-beat-fade');
            if (count > 0) {
                icon.classList.add('text-warning', 'fa-beat-fade');
            }
        }

        if (emptyEl) emptyEl.style.display = count > 0 ? 'none' : 'block';

        listEl.innerHTML = '';
        leads.forEach(function (lead) {
            var card = document.createElement('div');
            card.className = 'card mb-2 border-start border-3 border-warning';
            card.setAttribute('data-id-usuario', lead.id_usuario);
            card.innerHTML =
                '<div class="card-body py-2 px-3">' +
                '  <div class="d-flex justify-content-between align-items-start">' +
                '    <div class="flex-grow-1">' +
                '      <strong class="d-block">' + escapeHtml(lead.nombre_cliente) + '</strong>' +
                '      <span class="small text-muted"><i class="' + platformIcon(lead.plataforma) + ' me-1"></i>' + escapeHtml(lead.plataforma) + '</span>' +
                '      <p class="small mb-2 mt-1">' + escapeHtml(lead.resumen_viaje) + '</p>' +
                '    </div>' +
                '    <button type="button" class="btn btn-sm btn-outline-primary tomar-control-btn" data-id="' + escapeHtml(lead.id_usuario) + '">Tomar control</button>' +
                '  </div>' +
                '</div>';
            listEl.appendChild(card);

            card.querySelector('.tomar-control-btn').addEventListener('click', function () {
                var id = this.getAttribute('data-id');
                var btn = this;
                btn.disabled = true;
                btn.textContent = '...';
                tomarControl(id).then(function () {
                    var c = card.closest('#leads-calientes-list');
                    if (c) c.removeChild(card);
                    var remaining = listEl.querySelectorAll('[data-id-usuario]').length;
                    if (countHeader) countHeader.textContent = remaining;
                    if (badge) {
                        badge.textContent = remaining;
                        badge.style.display = remaining > 0 ? 'inline-block' : 'none';
                    }
                    if (icon && remaining === 0) icon.classList.remove('text-warning', 'fa-beat-fade');
                    if (emptyEl && remaining === 0) emptyEl.style.display = 'block';
                }).catch(function () {
                    btn.disabled = false;
                    btn.textContent = 'Tomar control';
                });
            });
        });
    }

    function escapeHtml(s) {
        if (s == null) return '';
        var div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function update() {
        fetchLeads().then(function (data) {
            renderList(data.leads || []);
        }).catch(function () {});
    }

    var pollTimer = null;
    function startPolling() {
        if (pollTimer) return;
        function tick() {
            update();
            pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
        }
        tick();
    }
    function stopPolling() {
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        update();
        startPolling();

        var toggle = document.getElementById('leadsCalientesToggle');
        if (toggle) {
            var dropdown = toggle.nextElementSibling;
            if (dropdown && dropdown.classList.contains('dropdown-menu')) {
                toggle.addEventListener('show.bs.dropdown', function () { update(); });
            }
        }

        document.addEventListener('visibilitychange', function () {
            if (document.hidden) stopPolling();
            else startPolling();
        });
    });
})();

/* Strop UI — vanilla JS, no dependencies.
 *
 * Load on the Raspberry Pi is kept low on purpose:
 *   - one /api/dashboard request builds the whole page;
 *   - while idle only the tiny /api/valves/status is polled (every 15 s) and the
 *     dashboard is reloaded only when something changed or every 5 minutes;
 *   - polling stops while the tab is hidden;
 *   - countdowns run locally in the browser.
 *
 * Texts come from i18n.js (Romanian by default, English optional).
 */
(function () {
    'use strict';

    var I18N = window.StropI18n;
    var t = I18N.t;

    var API = (typeof window.API_BASE_URL === 'string' && window.API_BASE_URL) || 'http://localhost:5000/api';
    var STATUS_POLL_MS = 15000;
    var DASHBOARD_REFRESH_MS = 5 * 60 * 1000;
    var MAX_MINUTES = 60;
    var DIAL_LENGTH = 326.73; // circumference of the dial ring (r = 52)
    var VALVES = [1, 2];
    // Display order Monday..Sunday with standard cron numbers (0 = Sunday)
    var WEEK = [1, 2, 3, 4, 5, 6, 0];

    var state = {
        dashboard: null,
        statusKey: null,
        lastDashboardAt: 0,
        timers: {},          // valve id -> {endAt, duration}
        zones: {},           // valve id -> DOM refs
        editing: {},         // valve id -> true while editor open
        busy: {},
        scrolledDays: false,
        locked: false
    };

    // ------------------------------------------------------------------ utils
    function $(sel, root) { return (root || document).querySelector(sel); }
    function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
    function pad(n) { return (n < 10 ? '0' : '') + n; }

    function localDateKey(d) {
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
    }
    function startOfDay(d) { var x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
    function addDays(d, n) { var x = new Date(d); x.setDate(x.getDate() + n); return x; }
    function dayDiff(a, b) { return Math.round((startOfDay(a) - startOfDay(b)) / 86400000); }
    function hhmm(d) { return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
    function monthShort(d) { return d.toLocaleString(I18N.locale(), { month: 'short' }).replace('.', ''); }
    function shortDate(d) { return d.getDate() + ' ' + monthShort(d); }
    function dayShort(d) { return t('days.short')[d.getDay()]; }

    // "Today", "Tomorrow", "Thursday" / "Joi", "Thu 19 Nov" / "Joi 19 nov"
    function relativeDay(d) {
        var diff = dayDiff(d, new Date());
        if (diff === 0) return t('day.today');
        if (diff === 1) return t('day.tomorrow');
        if (diff === -1) return t('day.yesterday');
        if (diff > 1 && diff < 7) return t('days.longCap')[d.getDay()];
        return dayShort(d) + ' ' + shortDate(d);
    }

    // Mid-sentence form: "today" / "azi", "on Thursday" / "joi"
    function phraseDay(d) {
        var diff = dayDiff(d, new Date());
        if (diff === 0) return t('phrase.today');
        if (diff === 1) return t('phrase.tomorrow');
        if (diff === -1) return t('phrase.yesterday');
        var name = (diff > 1 && diff < 7) ? t('days.long')[d.getDay()] : dayShort(d) + ' ' + shortDate(d);
        return t('phrase.on', { day: name });
    }

    function fmtDuration(seconds) {
        seconds = Math.max(0, Math.round(seconds || 0));
        if (seconds < 60) return seconds + ' s';
        var h = Math.floor(seconds / 3600);
        var m = Math.floor((seconds % 3600) / 60);
        var s = seconds % 60;
        if (h) return h + ' h' + (m ? ' ' + m + ' min' : '');
        return m + ' min' + (s && m < 10 ? ' ' + s + ' s' : '');
    }
    function fmtClock(seconds) {
        seconds = Math.max(0, Math.ceil(seconds));
        var m = Math.floor(seconds / 60);
        return pad(m) + ':' + pad(seconds % 60);
    }
    function minutesShort(seconds) {
        var m = Math.round(seconds / 60);
        return m >= 1 ? m + 'm' : Math.round(seconds) + 's';
    }
    function parseDate(s) {
        if (!s) return null;
        // "2026-11-06 05:35:00.10" (SQLite) -> ISO
        var d = new Date(String(s).replace(' ', 'T'));
        return isNaN(d) ? null : d;
    }
    function zoneName(id) { return t('zone.name', { n: id }); }

    // ------------------------------------------------------------------ reasons & errors (backend codes)
    function reasonText(key, args, fallback) {
        args = args || {};
        if (!key) return fallback || '';
        if (key === 'not_needed') return t('r.not_needed.' + (args.factor || 'rain'), args);
        if (key === 'reduced') {
            return (args.factors || []).map(function (f) { return t('r.f.' + f, args); }).join(', ');
        }
        var s = t('r.' + key, args);
        return s === 'r.' + key ? (fallback || '') : s;
    }
    function planReason(p) { return reasonText(p.reason_key, p.reason_args, p.reason); }
    function shortReason(p) {
        if (p.reason_key === 'not_needed') return t('r.f.' + ((p.reason_args || {}).factor || 'rain'), { rain: (p.reason_args || {}).rain })
            .replace(/ \d+ mm$/, '');
        var s = t('r.short.' + p.reason_key);
        return s === 'r.short.' + p.reason_key ? planReason(p) : s;
    }

    function errorText(err) {
        var d = err.data || {};
        switch (d.code) {
            case 'wrong_password': return t('e.wrong_password');
            case 'rate_limited': return t('e.rate_limited', { min: d.retry_minutes || 15 });
            case 'not_configured': return t('e.not_configured');
            case 'already_active': return t('e.already_active');
            case 'invalid_duration': return t('e.invalid_duration');
            case 'invalid_cron': return t('e.invalid_cron', { detail: d.message || '' });
        }
        if (err.kind === 'timeout') return t('e.timeout');
        if (err.kind === 'unreachable') return t('e.unreachable');
        return d.message || err.message || t('e.request', { status: err.status || '?' });
    }

    // ------------------------------------------------------------------ auth token
    var TOKEN_KEY = 'strop-token';
    var memoryToken = null;
    function getToken() {
        try { return localStorage.getItem(TOKEN_KEY) || memoryToken; } catch (e) { return memoryToken; }
    }
    function setToken(token) {
        memoryToken = token;
        try {
            if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY);
        } catch (e) {}
    }

    // ------------------------------------------------------------------ API
    function api(path, options) {
        options = options || {};
        var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
        var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 10000) : null;
        var init = { method: options.method || 'GET', headers: {} };
        if (ctrl) init.signal = ctrl.signal;
        var token = getToken();
        if (token) init.headers['Authorization'] = 'Bearer ' + token;
        if (options.body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(options.body);
        }
        return fetch(API + path, init).then(function (res) {
            if (timer) clearTimeout(timer);
            return res.json().catch(function () { return {}; }).then(function (data) {
                if (!res.ok) {
                    var err = new Error(data.message || data.error || ('HTTP ' + res.status));
                    err.status = res.status;
                    err.data = data;
                    if (res.status === 401 && data.auth_required) {
                        err.auth = true;
                        setToken(null);
                        showLogin();
                    }
                    throw err;
                }
                return data;
            });
        }, function (e) {
            if (timer) clearTimeout(timer);
            var err = new Error(e && e.name === 'AbortError' ? 'timeout' : 'unreachable');
            err.kind = e && e.name === 'AbortError' ? 'timeout' : 'unreachable';
            throw err;
        });
    }

    // ------------------------------------------------------------------ toast + connection
    var toastTimer = null;
    function toast(message, isError) {
        var el = $('#toast');
        el.textContent = message;
        el.className = 'toast show' + (isError ? ' error' : '');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { el.className = 'toast' + (isError ? ' error' : ''); }, isError ? 5000 : 3000);
    }

    var connState = null;
    function setConnection(ok) {
        connState = ok;
        var el = $('#conn');
        el.className = 'conn ' + (ok ? 'ok' : 'err');
        $('.conn-text', el).textContent = ok ? t('conn.online', { time: hhmm(new Date()) }) : t('conn.offline');
    }

    // ------------------------------------------------------------------ cron helpers
    function parseSchedule(expr) {
        var parts = (expr || '').trim().split(/\s+/);
        if (parts.length !== 5) return null;
        var minute = parts[0], hour = parts[1], dom = parts[2], month = parts[3], dow = parts[4];
        var simple = /^\d{1,2}$/.test(minute) && /^\d{1,2}$/.test(hour) && dom === '*' && month === '*';
        var days = null;
        if (dow === '*') {
            days = [0, 1, 2, 3, 4, 5, 6];
        } else if (/^[0-7](,[0-7])*$/.test(dow)) {
            days = dow.split(',').map(function (d) { return Number(d) % 7; });
        } else {
            simple = false;
        }
        return {
            simple: simple,
            minute: Number(minute),
            hour: Number(hour),
            days: days ? days.filter(function (d, i, a) { return a.indexOf(d) === i; }) : null,
            raw: expr.trim()
        };
    }

    function buildCron(days, time) {
        var parts = time.split(':');
        var dow = days.length === 7 ? '*' : WEEK.filter(function (d) { return days.indexOf(d) !== -1; }).join(',');
        return Number(parts[1]) + ' ' + Number(parts[0]) + ' * * ' + dow;
    }

    function describeDays(days) {
        if (!days || !days.length) return t('days.none');
        if (days.length === 7) return t('days.every');
        var sorted = days.slice().sort();
        if (sorted.join() === '1,2,3,4,5') return t('days.weekdays');
        if (sorted.join() === '0,6') return t('days.weekends');
        var names = t('days.short');
        return WEEK.filter(function (d) { return days.indexOf(d) !== -1; })
            .map(function (d) { return names[d]; }).join(', ');
    }

    function describeSchedule(schedule) {
        if (!schedule.cron_expression) return t('sched.notSet');
        var p = parseSchedule(schedule.cron_expression);
        var dur = schedule.duration ? ' · ' + fmtDuration(schedule.duration) : '';
        if (p && p.simple) return t('sched.at', { days: describeDays(p.days), time: pad(p.hour) + ':' + pad(p.minute) }) + dur;
        return t('sched.custom', { expr: schedule.cron_expression }) + dur;
    }

    // ------------------------------------------------------------------ weather helpers
    function weatherIcon(desc) {
        desc = (desc || '').toLowerCase();
        if (!desc) return 'w-none';
        if (desc.indexOf('thunder') !== -1) return 'w-storm';
        if (desc.indexOf('snow') !== -1 || desc.indexOf('sleet') !== -1) return 'w-snow';
        if (desc.indexOf('rain') !== -1 || desc.indexOf('drizzle') !== -1 || desc.indexOf('shower') !== -1) return 'w-rain';
        if (desc.indexOf('fog') !== -1 || desc.indexOf('mist') !== -1 || desc.indexOf('haze') !== -1) return 'w-fog';
        if (desc.indexOf('few clouds') !== -1 || desc.indexOf('scattered') !== -1) return 'w-partly';
        if (desc.indexOf('cloud') !== -1) return 'w-cloud';
        if (desc.indexOf('clear') !== -1) return 'w-clear';
        return 'w-partly';
    }
    function icon(id, cls) {
        return '<svg class="' + (cls || '') + '" aria-hidden="true"><use href="#' + id + '"/></svg>';
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // ------------------------------------------------------------------ zones
    function zoneColor(id) { return id === 1 ? 'var(--z1)' : 'var(--z2)'; }

    function createZone(id) {
        var node = document.importNode($('#zone-template').content, true).firstElementChild;
        node.style.setProperty('--zone-color', zoneColor(id));
        node.dataset.valve = id;
        $('#zones').appendChild(node);

        var refs = {
            id: id,
            root: node,
            name: $('.zone-name', node),
            next: $('.zone-next', node),
            pill: $('.pill', node),
            dial: $('.dial', node),
            bar: $('.dial-bar', node),
            time: $('.dial-time', node),
            label: $('.dial-label', node),
            runDetail: $('.run-detail', node),
            custom: $('.custom-min', node),
            start: $('.start-btn', node),
            stop: $('.stop-btn', node),
            scheduleText: $('.schedule-text', node),
            toggle: $('.schedule-toggle', node),
            edit: $('.edit-btn', node),
            editor: $('.editor', node),
            dayChips: $('.days-chips', node),
            edTime: $('.ed-time', node),
            edDuration: $('.ed-duration', node),
            edCron: $('.ed-cron', node),
            edAdvanced: $('.advanced', node),
            edError: $('.editor-error', node),
            history: $('.history', node),
            adjust: $('.adjust', node),
            adjSet: $('.adjust-set', node),
            adjFinal: $('.adjust-final', node),
            adjWhen: $('.adjust-when', node),
            adjPct: $('.adjust-pct', node),
            adjFill: $('.meter-fill', node),
            adjReason: $('.adjust-reason', node)
        };

        WEEK.forEach(function (d) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'chip';
            b.dataset.dow = d;
            b.setAttribute('aria-pressed', 'false');
            refs.dayChips.appendChild(b);
        });

        // Quick duration chips select a duration; Start opens the valve
        $all('.quick .chip', node).forEach(function (chip) {
            chip.addEventListener('click', function () {
                $all('.quick .chip', node).forEach(function (c) { c.setAttribute('aria-pressed', 'false'); });
                chip.setAttribute('aria-pressed', 'true');
                refs.custom.value = chip.dataset.min;
            });
        });
        refs.custom.addEventListener('input', function () {
            $all('.quick .chip', node).forEach(function (c) {
                c.setAttribute('aria-pressed', String(c.dataset.min === refs.custom.value));
            });
        });
        refs.custom.addEventListener('keydown', function (e) { if (e.key === 'Enter') startValve(id); });
        refs.start.addEventListener('click', function () { startValve(id); });
        refs.stop.addEventListener('click', function () { stopValve(id); });

        refs.toggle.addEventListener('change', function () { toggleSchedule(id, refs.toggle.checked); });
        refs.edit.addEventListener('click', function () { openEditor(id); });

        refs.dayChips.addEventListener('click', function (e) {
            var chip = e.target.closest('.chip');
            if (!chip) return;
            chip.setAttribute('aria-pressed', String(chip.getAttribute('aria-pressed') !== 'true'));
            syncCronField(id);
        });
        refs.edTime.addEventListener('input', function () { syncCronField(id); });
        refs.edCron.addEventListener('input', function () { refs.edCron.dataset.manual = '1'; });
        $('.ed-cancel', node).addEventListener('click', function () { closeEditor(id); });
        $('.ed-delete', node).addEventListener('click', function () { deleteSchedule(id); });
        refs.editor.addEventListener('submit', function (e) { e.preventDefault(); saveSchedule(id); });

        // default quick duration: 10 min
        $('.quick .chip[data-min="10"]', node).click();
        state.zones[id] = refs;
        translateZone(refs);
        return refs;
    }

    // Texts of a zone card that do not depend on data
    function translateZone(z) {
        I18N.apply(z.root);
        z.name.textContent = zoneName(z.id);
        var names = t('days.short');
        $all('.chip', z.dayChips).forEach(function (c) { c.textContent = names[Number(c.dataset.dow)]; });
        tickZone(z.id);
    }

    function renderZone(v) {
        var z = state.zones[v.id] || createZone(v.id);
        var schedule = v.schedule || {};
        z.root.classList.toggle('is-open', !!v.open);
        z.pill.textContent = v.open ? t('zone.watering') : t('zone.idle');

        // next run line (with the weather-adjusted duration)
        var plan = schedule.enabled && schedule.planned && schedule.planned.length ? schedule.planned[0] : null;
        var next = plan ? parseDate(plan.at) : null;
        if (next) {
            z.next.textContent = t('zone.next', {
                day: relativeDay(next), time: hhmm(next),
                what: plan.skip ? t('zone.skipped') : fmtDuration(plan.duration)
            });
        } else {
            z.next.textContent = schedule.cron_expression ? t('zone.scheduleOff') : t('zone.noSchedule');
        }
        renderAdjust(z, plan, next);

        // countdown state
        if (v.open && v.remaining != null) {
            state.timers[v.id] = { endAt: Date.now() + v.remaining * 1000, duration: v.duration || v.remaining };
            var started = parseDate(v.started_at);
            z.runDetail.textContent = t('zone.started', { time: started ? hhmm(started) : '—', dur: fmtDuration(v.duration) });
        } else {
            delete state.timers[v.id];
        }
        tickZone(v.id);

        // schedule summary + toggle (don't fight the user while saving)
        z.scheduleText.textContent = describeSchedule(schedule);
        z.scheduleText.classList.toggle('off', !schedule.enabled);
        if (!state.busy['toggle' + v.id]) z.toggle.checked = !!schedule.enabled;
        z.toggle.disabled = !schedule.cron_expression;
        z.root.dataset.cron = schedule.cron_expression || '';
        z.root.dataset.duration = schedule.duration || '';

        renderHistory(z, v.history || []);
    }

    function renderAdjust(z, plan, next) {
        if (!plan) { z.adjust.hidden = true; return; }
        z.adjust.hidden = false;
        z.adjust.classList.toggle('skip', !!plan.skip);
        z.adjust.classList.toggle('reduced', !plan.skip && plan.percent < 100);
        z.adjSet.textContent = fmtDuration(plan.base_duration);
        z.adjWhen.textContent = t('zone.adjusted', { day: relativeDay(next) });
        var pending = plan.reason_key === 'pending';
        z.adjust.classList.toggle('pending', pending);
        z.adjFinal.textContent = plan.skip ? t('adj.skip') : pending ? t('adj.upTo', { dur: fmtDuration(plan.duration) }) : fmtDuration(plan.duration);
        z.adjPct.textContent = pending ? '—' : plan.percent + '%';
        z.adjFill.style.width = pending ? '0%' : Math.max(0, Math.min(100, plan.percent)) + '%';
        z.adjReason.textContent = planReason(plan);
    }

    function tickZone(id) {
        var z = state.zones[id];
        if (!z) return;
        var timer = state.timers[id];
        if (timer) {
            var left = Math.max(0, (timer.endAt - Date.now()) / 1000);
            var frac = timer.duration ? left / timer.duration : 0;
            z.bar.style.strokeDashoffset = String(DIAL_LENGTH * (1 - frac));
            z.time.textContent = fmtClock(left);
            z.label.textContent = t('zone.remaining');
            z.dial.setAttribute('aria-label', t('zone.ariaRemaining', { n: id, time: fmtDuration(left) }));
            if (left <= 0 && !state.busy['expire' + id]) {
                // timer ended on the controller: confirm shortly after
                state.busy['expire' + id] = true;
                setTimeout(function () { state.busy['expire' + id] = false; loadDashboard(); }, 2500);
            }
        } else {
            z.bar.style.strokeDashoffset = String(DIAL_LENGTH);
            z.time.textContent = t('zone.off');
            z.label.textContent = t('zone.closed');
            z.dial.setAttribute('aria-label', t('zone.ariaClosed', { n: id }));
        }
    }

    function renderHistory(z, history) {
        if (!history.length) {
            z.history.innerHTML = '<li class="empty">' + escapeHtml(t('zone.noActivity')) + '</li>';
            return;
        }
        var map = {
            'Finished': ['h-finished', 'h.finished'],
            'Manually Stopped': ['h-stopped', 'h.stopped'],
            'Terminated': ['h-terminated', 'h.terminated'],
            'Watchdog Stopped': ['h-terminated', 'h.watchdog'],
            'Opened': ['h-open', 'h.running'],
            'Skipped': ['h-skipped', 'h.skipped']
        };
        z.history.innerHTML = history.slice(0, 4).map(function (h) {
            var m = map[h.status];
            var label = m ? t(m[1]) : h.status;
            var d = parseDate(h.start_time);
            var when = d ? relativeDay(d) + ', ' + hhmm(d) : '—';
            var reduced = h.base_duration && h.adjust_percent != null && h.adjust_percent < 100;
            var what;
            if (h.status === 'Skipped') {
                var r = h.adjust_reason || {};
                var why = reasonText(r.key, r.args, h.adjust_note);
                what = label + (why ? ' · ' + why : '');
            } else if (h.status === 'Opened') {
                what = label + (reduced ? ' · ' + t('h.pctOf', { pct: h.adjust_percent, base: fmtDuration(h.base_duration) }) : '');
            } else {
                var dur = h.duration != null ? fmtDuration(h.duration) : '';
                what = label + (dur ? ' · ' + (reduced ? t('h.of', { dur: dur, base: fmtDuration(h.base_duration) }) : dur) : '');
            }
            return '<li class="' + (m ? m[0] : '') + '"><span class="h-dot"></span><span class="h-when">' + escapeHtml(when) +
                '</span><span class="h-what">' + escapeHtml(what) + '</span></li>';
        }).join('');
    }

    // ------------------------------------------------------------------ actions
    function withBusy(btn, fn) {
        if (btn.disabled) return;
        btn.disabled = true;
        return fn().then(function () { btn.disabled = false; }, function () { btn.disabled = false; });
    }

    function startValve(id) {
        var z = state.zones[id];
        var minutes = parseInt(z.custom.value, 10);
        if (!(minutes >= 1 && minutes <= MAX_MINUTES)) {
            toast(t('t.minutes', { max: MAX_MINUTES }), true);
            z.custom.focus();
            return;
        }
        withBusy(z.start, function () {
            return api('/valves/' + id + '/activate', { method: 'POST', body: { duration: minutes * 60 } })
                .then(function () { toast(t('t.started', { n: id, min: minutes })); return loadDashboard(); })
                .catch(function (e) { toast(errorText(e), true); return loadDashboard(); });
        });
    }

    function stopValve(id) {
        var z = state.zones[id];
        withBusy(z.stop, function () {
            return api('/valves/' + id + '/deactivate', { method: 'POST' })
                .then(function () { toast(t('t.stopped', { n: id })); return loadDashboard(); })
                .catch(function (e) { toast(errorText(e), true); return loadDashboard(); });
        });
    }

    function postSchedule(id, expr, durationSec, enabled) {
        return api('/valves/' + id + '/cron', {
            method: 'POST',
            body: { cron_expression: expr, duration: durationSec, enabled: enabled }
        });
    }

    function toggleSchedule(id, enabled) {
        var z = state.zones[id];
        var expr = z.root.dataset.cron;
        if (!expr) { z.toggle.checked = false; openEditor(id); return; }
        state.busy['toggle' + id] = true;
        z.toggle.disabled = true;
        postSchedule(id, expr, Number(z.root.dataset.duration) || 300, enabled)
            .then(function () { toast(t(enabled ? 't.scheduleOn' : 't.scheduleOff', { n: id })); })
            .catch(function (e) { z.toggle.checked = !enabled; toast(errorText(e), true); })
            .then(function () { state.busy['toggle' + id] = false; return loadDashboard(); });
    }

    function setDayChips(z, days) {
        $all('.chip', z.dayChips).forEach(function (c) {
            c.setAttribute('aria-pressed', String(days.indexOf(Number(c.dataset.dow)) !== -1));
        });
    }
    function selectedDays(z) {
        return $all('.chip[aria-pressed="true"]', z.dayChips).map(function (c) { return Number(c.dataset.dow); });
    }
    function syncCronField(id) {
        var z = state.zones[id];
        var days = selectedDays(z);
        if (days.length && z.edTime.value) z.edCron.value = buildCron(days, z.edTime.value);
        delete z.edCron.dataset.manual;
    }

    function openEditor(id) {
        var z = state.zones[id];
        var expr = z.root.dataset.cron;
        var p = parseSchedule(expr);
        var dur = Number(z.root.dataset.duration) || 300;
        z.edError.textContent = '';
        z.edDuration.value = Math.max(1, Math.round(dur / 60));
        if (p && p.simple) {
            setDayChips(z, p.days);
            z.edTime.value = pad(p.hour) + ':' + pad(p.minute);
            z.edAdvanced.open = false;
        } else if (expr) {
            setDayChips(z, (p && p.days) || []);
            z.edTime.value = '';
            z.edAdvanced.open = true;
        } else {
            setDayChips(z, [1, 3, 5]);
            z.edTime.value = '06:30';
            z.edAdvanced.open = false;
        }
        z.edCron.value = expr || '';
        delete z.edCron.dataset.manual;
        if (!expr) syncCronField(id);
        z.editor.hidden = false;
        state.editing[id] = true;
        z.edTime.focus();
    }

    function closeEditor(id) {
        state.zones[id].editor.hidden = true;
        state.editing[id] = false;
    }

    function saveSchedule(id) {
        var z = state.zones[id];
        var minutes = parseInt(z.edDuration.value, 10);
        var manual = z.edCron.dataset.manual === '1' && z.edAdvanced.open;
        var expr;
        z.edError.textContent = '';

        if (!(minutes >= 1 && minutes <= MAX_MINUTES)) {
            z.edError.textContent = t('ed.errDuration', { max: MAX_MINUTES });
            return;
        }
        if (manual) {
            expr = z.edCron.value.trim();
        } else {
            var days = selectedDays(z);
            if (!days.length) { z.edError.textContent = t('ed.errDays'); return; }
            if (!z.edTime.value) { z.edError.textContent = t('ed.errTime'); return; }
            expr = buildCron(days, z.edTime.value);
        }
        var hadSchedule = !!z.root.dataset.cron;
        var enabled = hadSchedule ? z.toggle.checked : true;
        var btn = $('.ed-save', z.root);
        withBusy(btn, function () {
            return postSchedule(id, expr, minutes * 60, enabled)
                .then(function () {
                    closeEditor(id);
                    toast(t(enabled ? 't.saved' : 't.savedOff', { n: id }));
                    return loadDashboard();
                })
                .catch(function (e) { z.edError.textContent = errorText(e); });
        });
    }

    function deleteSchedule(id) {
        if (!window.confirm(t('ed.confirmDelete', { n: id }))) return;
        api('/valves/' + id + '/cron', { method: 'DELETE' })
            .then(function () { closeEditor(id); toast(t('t.deleted', { n: id })); return loadDashboard(); })
            .catch(function (e) { toast(errorText(e), true); });
    }

    // ------------------------------------------------------------------ overview
    function remainingText(timer) {
        return t('ov.remaining', { time: fmtDuration((timer.endAt - Date.now()) / 1000) });
    }

    function renderOverview(d) {
        var el = $('#overview');
        var open = d.valves.filter(function (v) { return v.open; });
        var title, sub = '';
        if (open.length) {
            title = t('ov.watering', { zones: open.map(function (v) { return zoneName(v.id); }).join(t('ov.and')) });
            var timer = state.timers[open[0].id];
            sub = timer ? remainingText(timer) : '';
        } else {
            // all upcoming runs of all zones, in time order
            var upcoming = [];
            d.valves.forEach(function (v) {
                if (!v.schedule.enabled) return;
                (v.schedule.planned || []).forEach(function (p) {
                    upcoming.push({ id: v.id, at: parseDate(p.at), plan: p });
                });
            });
            upcoming.sort(function (a, b) { return a.at - b.at; });
            var firstRun = upcoming.filter(function (u) { return !u.plan.skip; })[0];
            var skippedBefore = upcoming.filter(function (u) { return u.plan.skip && (!firstRun || u.at < firstRun.at); });
            var skipNote = '';
            if (skippedBefore.length) {
                var reasons = [];
                skippedBefore.forEach(function (u) {
                    var r = shortReason(u.plan);
                    if (reasons.indexOf(r) === -1) reasons.push(r);
                });
                skipNote = skippedBefore.length === 1
                    ? t('ov.skippedBeforeOne', { reasons: reasons.join(', ') })
                    : t('ov.skippedBefore', { n: skippedBefore.length, reasons: reasons.join(', ') });
            }
            if (firstRun) {
                var u = firstRun;
                title = t('ov.next', { day: phraseDay(u.at), time: hhmm(u.at) });
                sub = zoneName(u.id) + ' · ' + (u.plan.percent < 100
                    ? t('ov.of', { dur: fmtDuration(u.plan.duration), base: fmtDuration(u.plan.base_duration), pct: u.plan.percent })
                    : u.plan.reason_key === 'pending'
                        ? t('adj.upTo', { dur: fmtDuration(u.plan.duration) }) + ' · ' + t('r.short.pending')
                        : fmtDuration(u.plan.duration)) + (skipNote ? ' · ' + skipNote : '');
            } else if (upcoming.length) {
                title = t('ov.noneNeeded');
                sub = skipNote;
            } else {
                title = t('ov.allOff');
                sub = t('ov.nothing');
            }
        }
        el.classList.toggle('watering', open.length > 0);
        $('#overview-title').textContent = title;

        var todayKey = localDateKey(new Date());
        var w = d.weather.filter(function (x) { return x.date === todayKey; })[0];
        if (w) {
            sub += (sub ? ' · ' : '') + Math.round(w.temperature_minimum) + '° / ' + Math.round(w.temperature_maximum) + '° ' +
                I18N.weather(w.description);
        }
        $('#overview-sub').textContent = sub;

        // stats
        var todaySec = 0, weekSec = 0;
        VALVES.forEach(function (id) {
            var usage = d.usage[id] || {};
            Object.keys(usage).forEach(function (k) {
                weekSec += usage[k];
                if (k === todayKey) todaySec += usage[k];
            });
        });
        var rain3 = 0;
        for (var i = 0; i < 3; i++) {
            var key = localDateKey(addDays(new Date(), i));
            d.weather.forEach(function (x) { if (x.date === key) rain3 += x.total_rain || 0; });
        }
        $('#overview-stats').innerHTML =
            stat(t('stat.today'), Math.round(todaySec / 60), 'min') +
            stat(t('stat.week'), Math.round(weekSec / 60), 'min') +
            stat(t('stat.rain'), rain3 ? rain3.toFixed(1) : '0', 'mm');
    }
    function stat(label, value, unit) {
        return '<div class="stat"><div class="stat-label">' + escapeHtml(label) + '</div><div class="stat-value">' +
            value + ' <small>' + unit + '</small></div></div>';
    }

    // ------------------------------------------------------------------ days strip
    function renderDays(d) {
        var byDate = {};
        d.weather.forEach(function (w) { byDate[w.date] = w; });
        var planned = {};
        d.valves.forEach(function (v) {
            if (!v.schedule.enabled) return;
            (v.schedule.planned || []).forEach(function (p) {
                var at = parseDate(p.at);
                if (!at) return;
                var k = localDateKey(at);
                (planned[k] = planned[k] || []).push({ id: v.id, at: at, plan: p });
            });
        });

        var today = startOfDay(new Date());
        var html = '';
        for (var i = -6; i <= 5; i++) {
            var day = addDays(today, i);
            var key = localDateKey(day);
            var w = byDate[key];
            var cls = 'day' + (i < 0 ? ' past' : '') + (i === 0 ? ' today' : '');
            html += '<div class="' + cls + '"' + (i === 0 ? ' id="day-today"' : '') + '>';
            html += '<div class="day-name">' + escapeHtml(i === 0 ? t('day.today') : dayShort(day)) + '</div>';
            html += '<div class="day-date">' + escapeHtml(shortDate(day)) + '</div>';
            if (w) {
                var rain = w.total_rain || 0;
                html += '<span title="' + escapeHtml(I18N.weather(w.description)) + '">' + icon(weatherIcon(w.description), 'day-icon') + '</span>';
                html += '<div class="day-temp">' + Math.round(w.temperature_maximum) + '° <span class="lo">' +
                    Math.round(w.temperature_minimum) + '°</span></div>';
                html += '<div class="day-rain' + (rain >= 0.1 ? ' wet' : '') + '">' + icon('i-drop') +
                    (rain >= 0.1 ? rain.toFixed(1) + ' mm' : '0 mm') + '</div>';
                if (w.average_humidity) html += '<div class="day-hum">' + escapeHtml(t('w.hum', { h: w.average_humidity })) + '</div>';
            } else {
                html += icon('w-none', 'day-icon') + '<div class="day-nodata">' + escapeHtml(t('w.noData')) + '</div>';
            }
            html += '<div class="day-water">';
            VALVES.forEach(function (id) {
                var sec = (d.usage[id] || {})[key];
                if (sec) html += '<span class="tag tag-z' + id + '">Z' + id + ' ' + minutesShort(sec) + '</span>';
            });
            (planned[key] || []).forEach(function (p) {
                if (i < 0 || p.at < new Date()) return;
                var label = p.plan.skip ? t('w.skip') : minutesShort(p.plan.duration);
                var title = p.plan.reason_key === 'pending' ? planReason(p.plan)
                    : t('w.tagTitle', { base: fmtDuration(p.plan.base_duration), pct: p.plan.percent, reason: planReason(p.plan) });
                html += '<span class="tag tag-plan' + (p.plan.skip ? ' tag-skip' : '') + '" title="' + escapeHtml(title) + '">Z' +
                    p.id + ' ' + hhmm(p.at) + ' · ' + escapeHtml(label) + '</span>';
            });
            html += '</div></div>';
        }
        var box = $('#days');
        box.innerHTML = html;

        var updated = parseDate(d.weather_updated);
        $('#weather-note').textContent = updated ? t('w.updated', { day: phraseDay(updated), time: hhmm(updated) }) : '';

        if (!state.scrolledDays) {
            // show a couple of past days to the left of today
            var todayEl = $('#day-today');
            if (todayEl && box.scrollWidth > box.clientWidth) {
                box.scrollLeft = Math.max(0, todayEl.offsetLeft - box.offsetLeft - 2 * (todayEl.offsetWidth + 8));
            }
            state.scrolledDays = true;
        }
    }

    // ------------------------------------------------------------------ adjustment panel
    function signed(v) { return (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(Math.round(v)) + '%'; }

    function renderAdjustPanel(d) {
        var a = d.adjustment;
        if (!a) return;
        var s = a.settings || {};
        var runDay = parseDate(a.date + 'T12:00:00');
        var hasRun = d.valves.some(function (v) { return v.schedule.enabled && v.schedule.planned && v.schedule.planned.length; });
        $('#adjust-note').textContent = t(hasRun ? 'adj.forNext' : 'adj.ifWatering', { day: phraseDay(runDay) }) +
            (a.enabled ? '' : t('adj.disabled'));

        $('#adjust-big').textContent = a.skip ? t('adj.skip') : a.reason_key === 'pending' ? '—' : a.percent + '%';
        $('.adjust-of').textContent = a.skip ? t('adj.runSkipped') : t('adj.ofProgrammed');
        $('#adjust-panel').classList.toggle('skip', !!a.skip);
        $('#adjust-verdict').textContent = reasonText(a.reason_key, a.reason_args, a.reason);

        var inp = a.inputs || {}, terms = a.terms || {};
        function row(name, value, base, term) {
            var width = Math.min(100, Math.abs(term));
            return '<div class="factor"><div class="factor-head"><span class="factor-name">' + escapeHtml(name) +
                '</span><span class="factor-term ' + (term < 0 ? 'neg' : term > 0 ? 'pos' : '') + '">' + signed(term) +
                '</span></div><div class="factor-detail">' + escapeHtml(value) +
                (base ? ' <span class="factor-base">' + escapeHtml(t('adj.baseline', { v: base })) + '</span>' : '') +
                '</div><div class="factor-bar"><span class="' + (term < 0 ? 'neg' : 'pos') + '" style="width:' + width + '%"></span></div></div>';
        }
        $('#factors').innerHTML =
            row(t('adj.temperature'), inp.temp != null ? t('adj.avgTemp', { v: inp.temp }) : t('adj.noData'), s.base_temp + '°C', terms.temp || 0) +
            row(t('adj.humidity'), inp.humidity != null ? t('adj.avgHum', { v: inp.humidity }) : t('adj.noData'), s.base_humidity + '%', terms.humidity || 0) +
            row(t('adj.rain'), t('adj.rainWeighted', { v: inp.rain || 0 }), '', terms.rain || 0) +
            (inp.min_temp != null ? '<p class="factor-foot">' + escapeHtml(t('adj.minFoot', {
                min: inp.min_temp, freeze: s.freeze_temp, cold: s.cold_temp })) + '</p>' : '');

        $('#method-text').textContent = t('adj.method', {
            base: t('adj.methodBase', { t: s.base_temp, h: s.base_humidity }),
            temp: s.temp_pct_per_c + '%',
            hum: s.humidity_pct_per_pct + '%',
            rain: s.rain_pct_per_mm + '%',
            min: s.min_percent + '%'
        });
    }

    // ------------------------------------------------------------------ rendering
    function renderAll(d) {
        d.valves.forEach(renderZone);
        renderOverview(d);
        renderAdjustPanel(d);
        renderDays(d);
    }

    // ------------------------------------------------------------------ loading
    var loading = null;
    function loadDashboard() {
        if (loading) return loading;
        loading = api('/dashboard').then(function (d) {
            state.dashboard = d;
            state.lastDashboardAt = Date.now();
            state.statusKey = d.valves.map(function (v) { return v.id + ':' + !!v.open; }).join(',');
            renderAll(d);
            setConnection(true);
        }).catch(function (e) {
            if (e.auth) return;
            setConnection(false);
            if (!state.dashboard) {
                $('#overview-title').textContent = t('ov.unreachable');
                $('#overview-sub').textContent = t('ov.retrying', { error: errorText(e) });
            }
        }).then(function () { loading = null; });
        return loading;
    }

    function pollStatus() {
        if (document.hidden || state.locked) return;
        if (Date.now() - state.lastDashboardAt > DASHBOARD_REFRESH_MS) { loadDashboard(); return; }
        api('/valves/status').then(function (s) {
            setConnection(true);
            var key = VALVES.map(function (id) { return id + ':' + !!(s.valves && s.valves[id]); }).join(',');
            if (key !== state.statusKey) loadDashboard();
        }).catch(function () { setConnection(false); });
    }

    function tickAll() {
        if (document.hidden) return;
        var any = false;
        VALVES.forEach(function (id) { if (state.timers[id]) { any = true; tickZone(id); } });
        if (any && state.dashboard) {
            var open = state.dashboard.valves.filter(function (v) { return v.open; });
            var timer = open.length && state.timers[open[0].id];
            if (timer) {
                var sub = $('#overview-sub').textContent.split(' · ');
                sub[0] = remainingText(timer);
                $('#overview-sub').textContent = sub.join(' · ');
            }
        }
    }

    // ------------------------------------------------------------------ login
    var loginHint = false;
    function showLogin(message) {
        if (state.locked && !message) return;
        state.locked = true;
        document.body.classList.add('locked');
        var box = $('#login');
        box.hidden = false;
        $('#login-error').textContent = message || '';
        var input = $('#login-password');
        input.value = '';
        setTimeout(function () { input.focus(); }, 50);
        api('/auth/status').then(function (s) {
            loginHint = !s.configured;
            $('#login-hint').textContent = loginHint ? t('login.notSet') : '';
        }).catch(function () {});
    }

    function hideLogin() {
        state.locked = false;
        document.body.classList.remove('locked');
        $('#login').hidden = true;
    }

    $('#login-form').addEventListener('submit', function (e) {
        e.preventDefault();
        var btn = $('#login-submit');
        var password = $('#login-password').value;
        if (!password) return;
        $('#login-error').textContent = '';
        withBusy(btn, function () {
            return api('/auth/login', { method: 'POST', body: { password: password } })
                .then(function (r) {
                    setToken(r.token);
                    hideLogin();
                    return loadDashboard();
                })
                .catch(function (err) {
                    $('#login-error').textContent = errorText(err);
                    $('#login-password').select();
                });
        });
    });

    $('#logout').addEventListener('click', function () {
        setToken(null);
        state.dashboard = null;
        showLogin();
    });

    // ------------------------------------------------------------------ language
    function applyLanguage() {
        I18N.apply(document);
        // the button shows the language you switch TO
        $('#lang-label').textContent = I18N.getLang() === 'ro' ? 'EN' : 'RO';
        Object.keys(state.zones).forEach(function (id) { translateZone(state.zones[id]); });
        if (connState !== null) setConnection(connState);
        if (state.locked) $('#login-hint').textContent = loginHint ? t('login.notSet') : '';
        if (state.dashboard) renderAll(state.dashboard);
    }

    $('#lang-toggle').addEventListener('click', function () {
        I18N.setLang(I18N.getLang() === 'ro' ? 'en' : 'ro');
        applyLanguage();
    });

    // ------------------------------------------------------------------ theme
    function currentTheme() {
        var th = document.documentElement.getAttribute('data-theme');
        if (th) return th;
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    $('#theme-toggle').addEventListener('click', function () {
        var next = currentTheme() === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        try { localStorage.setItem('strop-theme', next); } catch (e) {}
    });

    // ------------------------------------------------------------------ start
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && !state.locked) loadDashboard();
    });
    VALVES.forEach(createZone);
    applyLanguage();
    if (getToken()) loadDashboard(); else showLogin();
    setInterval(pollStatus, STATUS_POLL_MS);
    setInterval(tickAll, 1000);
})();

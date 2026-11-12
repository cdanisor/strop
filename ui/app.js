/* Strop UI — vanilla JS, no dependencies.
 *
 * Load on the Raspberry Pi is kept low on purpose:
 *   - one /api/dashboard request builds the whole page;
 *   - while idle only the tiny /api/valves/status is polled (every 15 s) and the
 *     dashboard is reloaded only when something changed or every 5 minutes;
 *   - polling stops while the tab is hidden;
 *   - countdowns run locally in the browser.
 */
(function () {
    'use strict';

    var API = (typeof window.API_BASE_URL === 'string' && window.API_BASE_URL) || 'http://localhost:5000/api';
    var STATUS_POLL_MS = 15000;
    var DASHBOARD_REFRESH_MS = 5 * 60 * 1000;
    var MAX_MINUTES = 60;
    var DIAL_LENGTH = 326.73; // circumference of the dial ring (r = 52)
    var VALVES = [1, 2];
    var LOCALE = 'en-GB';
    // Display order Monday..Sunday with standard cron numbers (0 = Sunday)
    var WEEK = [[1, 'Mon'], [2, 'Tue'], [3, 'Wed'], [4, 'Thu'], [5, 'Fri'], [6, 'Sat'], [0, 'Sun']];
    var DAY_NAMES = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var DAY_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    var state = {
        dashboard: null,
        statusKey: null,
        lastDashboardAt: 0,
        timers: {},          // valve id -> {endAt, duration}
        zones: {},           // valve id -> DOM refs
        editing: {},         // valve id -> true while editor open
        busy: {},
        pollTimer: null,
        scrolledDays: false
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
    function shortDate(d) { return d.getDate() + ' ' + d.toLocaleString(LOCALE, { month: 'short' }); }

    function relativeDay(d) {
        var diff = dayDiff(d, new Date());
        if (diff === 0) return 'Today';
        if (diff === 1) return 'Tomorrow';
        if (diff === -1) return 'Yesterday';
        if (diff > 1 && diff < 7) return DAY_NAMES[d.getDay()];
        return DAY_SHORT[d.getDay()] + ' ' + shortDate(d);
    }

    // Mid-sentence form: "today", "tomorrow", "on Thursday", "on Thu 19 Nov"
    function phraseDay(d) {
        var r = relativeDay(d);
        if (r === 'Today' || r === 'Tomorrow' || r === 'Yesterday') return r.toLowerCase();
        return 'on ' + r;
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
        var t = ctrl ? setTimeout(function () { ctrl.abort(); }, 10000) : null;
        var init = { method: options.method || 'GET', headers: {} };
        if (ctrl) init.signal = ctrl.signal;
        var token = getToken();
        if (token) init.headers['Authorization'] = 'Bearer ' + token;
        if (options.body !== undefined) {
            init.headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(options.body);
        }
        return fetch(API + path, init).then(function (res) {
            if (t) clearTimeout(t);
            return res.json().catch(function () { return {}; }).then(function (data) {
                if (!res.ok) {
                    var err = new Error(data.message || data.error || ('Request failed (' + res.status + ')'));
                    err.status = res.status;
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
            if (t) clearTimeout(t);
            throw new Error(e && e.name === 'AbortError' ? 'Controller not responding' : 'Controller unreachable');
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

    function setConnection(ok) {
        var el = $('#conn');
        el.className = 'conn ' + (ok ? 'ok' : 'err');
        $('.conn-text', el).textContent = ok ? 'Online · ' + hhmm(new Date()) : 'Offline';
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
        var t = time.split(':');
        var dow = days.length === 7 ? '*' : WEEK.map(function (w) { return w[0]; })
            .filter(function (d) { return days.indexOf(d) !== -1; }).join(',');
        return Number(t[1]) + ' ' + Number(t[0]) + ' * * ' + dow;
    }

    function describeDays(days) {
        if (!days || !days.length) return 'No days';
        if (days.length === 7) return 'Every day';
        var sorted = days.slice().sort();
        if (sorted.join() === '1,2,3,4,5') return 'Weekdays';
        if (sorted.join() === '0,6') return 'Weekends';
        return WEEK.filter(function (w) { return days.indexOf(w[0]) !== -1; })
            .map(function (w) { return w[1]; }).join(', ');
    }

    function describeSchedule(schedule) {
        if (!schedule.cron_expression) return 'Not set';
        var p = parseSchedule(schedule.cron_expression);
        var dur = schedule.duration ? ' · ' + fmtDuration(schedule.duration) : '';
        if (p && p.simple) return describeDays(p.days) + ' at ' + pad(p.hour) + ':' + pad(p.minute) + dur;
        return 'Custom: ' + schedule.cron_expression + dur;
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
        $('.zone-name', node).textContent = 'Zone ' + id;
        $('#zones').appendChild(node);

        var refs = {
            root: node,
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

        WEEK.forEach(function (w) {
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'chip';
            b.dataset.dow = w[0];
            b.textContent = w[1];
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
        return refs;
    }

    function renderZone(v) {
        var z = state.zones[v.id] || createZone(v.id);
        var schedule = v.schedule || {};
        z.root.classList.toggle('is-open', !!v.open);
        z.pill.textContent = v.open ? 'Watering' : 'Idle';

        // next run line (with the weather-adjusted duration)
        var plan = schedule.enabled && schedule.planned && schedule.planned.length ? schedule.planned[0] : null;
        var next = plan ? parseDate(plan.at) : null;
        if (next) {
            z.next.textContent = 'Next: ' + relativeDay(next) + ' at ' + hhmm(next) + ' · ' +
                (plan.skip ? 'skipped' : fmtDuration(plan.duration));
        } else {
            z.next.textContent = schedule.cron_expression ? 'Schedule off' : 'No schedule';
        }
        renderAdjust(z, schedule, plan, next);

        // countdown state
        if (v.open && v.remaining != null) {
            state.timers[v.id] = { endAt: Date.now() + v.remaining * 1000, duration: v.duration || v.remaining };
            var started = parseDate(v.started_at);
            z.runDetail.textContent = (started ? 'Started ' + hhmm(started) + ' · ' : '') + fmtDuration(v.duration) + ' run';
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

    function renderAdjust(z, schedule, plan, next) {
        if (!plan) { z.adjust.hidden = true; return; }
        z.adjust.hidden = false;
        z.adjust.classList.toggle('skip', !!plan.skip);
        z.adjust.classList.toggle('reduced', !plan.skip && plan.percent < 100);
        z.adjSet.textContent = fmtDuration(plan.base_duration);
        z.adjWhen.textContent = 'Adjusted · ' + relativeDay(next);
        z.adjFinal.textContent = plan.skip ? 'Skipped' : fmtDuration(plan.duration);
        z.adjPct.textContent = plan.percent + '%';
        z.adjFill.style.width = Math.max(0, Math.min(100, plan.percent)) + '%';
        z.adjReason.textContent = plan.reason || '';
    }

    function tickZone(id) {
        var z = state.zones[id];
        if (!z) return;
        var t = state.timers[id];
        if (t) {
            var left = Math.max(0, (t.endAt - Date.now()) / 1000);
            var frac = t.duration ? left / t.duration : 0;
            z.bar.style.strokeDashoffset = String(DIAL_LENGTH * (1 - frac));
            z.time.textContent = fmtClock(left);
            z.label.textContent = 'remaining';
            z.dial.setAttribute('aria-label', 'Zone ' + id + ': ' + fmtDuration(left) + ' remaining');
            if (left <= 0 && !state.busy['expire' + id]) {
                // timer ended on the controller: confirm shortly after
                state.busy['expire' + id] = true;
                setTimeout(function () { state.busy['expire' + id] = false; loadDashboard(); }, 2500);
            }
        } else {
            z.bar.style.strokeDashoffset = String(DIAL_LENGTH);
            z.time.textContent = 'Off';
            z.label.textContent = 'valve closed';
            z.dial.setAttribute('aria-label', 'Zone ' + id + ': valve closed');
        }
    }

    function renderHistory(z, history) {
        if (!history.length) {
            z.history.innerHTML = '<li class="empty">No activity yet</li>';
            return;
        }
        var map = {
            'Finished': ['h-finished', 'Completed'],
            'Manually Stopped': ['h-stopped', 'Stopped'],
            'Terminated': ['h-terminated', 'Interrupted'],
            'Opened': ['h-open', 'Running'],
            'Skipped': ['h-skipped', 'Skipped']
        };
        z.history.innerHTML = history.slice(0, 4).map(function (h) {
            var m = map[h.status] || ['', h.status];
            var d = parseDate(h.start_time);
            var when = d ? relativeDay(d) + ', ' + hhmm(d) : '—';
            var what;
            if (h.status === 'Skipped') {
                what = m[1] + (h.adjust_note ? ' · ' + h.adjust_note : '');
            } else if (h.status === 'Opened') {
                what = m[1] + (h.base_duration && h.adjust_percent != null && h.adjust_percent < 100
                    ? ' · ' + h.adjust_percent + '% of ' + fmtDuration(h.base_duration) : '');
            } else {
                what = m[1] + (h.duration != null ? ' · ' + fmtDuration(h.duration) : '');
                if (h.base_duration && h.adjust_percent != null && h.adjust_percent < 100) {
                    what += ' of ' + fmtDuration(h.base_duration);
                }
            }
            return '<li class="' + m[0] + '"><span class="h-dot"></span><span class="h-when">' + escapeHtml(when) +
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
            toast('Choose between 1 and ' + MAX_MINUTES + ' minutes', true);
            z.custom.focus();
            return;
        }
        withBusy(z.start, function () {
            return api('/valves/' + id + '/activate', { method: 'POST', body: { duration: minutes * 60 } })
                .then(function () { toast('Zone ' + id + ' watering for ' + minutes + ' min'); return loadDashboard(); })
                .catch(function (e) { toast(e.message, true); return loadDashboard(); });
        });
    }

    function stopValve(id) {
        var z = state.zones[id];
        withBusy(z.stop, function () {
            return api('/valves/' + id + '/deactivate', { method: 'POST' })
                .then(function () { toast('Zone ' + id + ' stopped'); return loadDashboard(); })
                .catch(function (e) { toast(e.message, true); return loadDashboard(); });
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
            .then(function () { toast('Zone ' + id + ' schedule ' + (enabled ? 'on' : 'off')); })
            .catch(function (e) { z.toggle.checked = !enabled; toast(e.message, true); })
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
            z.edError.textContent = 'Duration must be between 1 and ' + MAX_MINUTES + ' minutes.';
            return;
        }
        if (manual) {
            expr = z.edCron.value.trim();
        } else {
            var days = selectedDays(z);
            if (!days.length) { z.edError.textContent = 'Pick at least one day.'; return; }
            if (!z.edTime.value) { z.edError.textContent = 'Pick a start time.'; return; }
            expr = buildCron(days, z.edTime.value);
        }
        var hadSchedule = !!z.root.dataset.cron;
        var enabled = hadSchedule ? z.toggle.checked : true;
        var btn = $('.ed-save', z.root);
        withBusy(btn, function () {
            return postSchedule(id, expr, minutes * 60, enabled)
                .then(function () {
                    closeEditor(id);
                    toast('Zone ' + id + ' schedule saved' + (enabled ? '' : ' (off)'));
                    return loadDashboard();
                })
                .catch(function (e) { z.edError.textContent = e.message; });
        });
    }

    function deleteSchedule(id) {
        if (!window.confirm('Delete the schedule for Zone ' + id + '?')) return;
        api('/valves/' + id + '/cron', { method: 'DELETE' })
            .then(function () { closeEditor(id); toast('Zone ' + id + ' schedule deleted'); return loadDashboard(); })
            .catch(function (e) { toast(e.message, true); });
    }

    // ------------------------------------------------------------------ overview
    function renderOverview(d) {
        var el = $('#overview');
        var open = d.valves.filter(function (v) { return v.open; });
        var title, sub = '';
        if (open.length) {
            title = open.map(function (v) { return 'Zone ' + v.id; }).join(' & ') + ' watering';
            var t = state.timers[open[0].id];
            sub = t ? fmtDuration((t.endAt - Date.now()) / 1000) + ' remaining' : '';
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
                    var r = u.plan.reason.replace(/^Not needed: /, '').replace(/ \(.*\)$/, '').toLowerCase();
                    if (reasons.indexOf(r) === -1) reasons.push(r);
                });
                skipNote = skippedBefore.length + ' run' + (skippedBefore.length > 1 ? 's' : '') + ' skipped before (' + reasons.join(', ') + ')';
            }
            if (firstRun) {
                var u = firstRun;
                title = 'Next watering ' + phraseDay(u.at) + ' at ' + hhmm(u.at);
                sub = 'Zone ' + u.id + ' · ' + fmtDuration(u.plan.duration) +
                    (u.plan.percent < 100 ? ' of ' + fmtDuration(u.plan.base_duration) + ' (' + u.plan.percent + '%)' : '') +
                    (skipNote ? ' · ' + skipNote : '');
            } else if (upcoming.length) {
                title = 'No watering needed in the coming days';
                sub = skipNote;
            } else {
                title = 'All schedules are off';
                sub = 'Nothing will water automatically';
            }
        }
        el.classList.toggle('watering', open.length > 0);
        $('#overview-title').textContent = title;

        var todayKey = localDateKey(new Date());
        var w = d.weather.filter(function (x) { return x.date === todayKey; })[0];
        if (w) {
            sub += (sub ? ' · ' : '') + Math.round(w.temperature_minimum) + '° / ' + Math.round(w.temperature_maximum) + '° ' + (w.description || '');
        }
        $('#overview-sub').textContent = sub;

        // stats
        var todaySec = 0, weekSec = 0;
        VALVES.forEach(function (id) {
            var u = d.usage[id] || {};
            Object.keys(u).forEach(function (k) {
                weekSec += u[k];
                if (k === todayKey) todaySec += u[k];
            });
        });
        var rain3 = 0;
        for (var i = 0; i < 3; i++) {
            var key = localDateKey(addDays(new Date(), i));
            d.weather.forEach(function (x) { if (x.date === key) rain3 += x.total_rain || 0; });
        }
        $('#overview-stats').innerHTML =
            stat('Watered today', Math.round(todaySec / 60), 'min') +
            stat('Last 7 days', Math.round(weekSec / 60), 'min') +
            stat('Rain next 3 days', rain3 ? rain3.toFixed(1) : '0', 'mm');
    }
    function stat(label, value, unit) {
        return '<div class="stat"><div class="stat-label">' + label + '</div><div class="stat-value">' +
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
            html += '<div class="day-name">' + (i === 0 ? 'Today' : DAY_SHORT[day.getDay()]) + '</div>';
            html += '<div class="day-date">' + shortDate(day) + '</div>';
            if (w) {
                var rain = w.total_rain || 0;
                html += '<span title="' + escapeHtml(w.description || '') + '">' + icon(weatherIcon(w.description), 'day-icon') + '</span>';
                html += '<div class="day-temp">' + Math.round(w.temperature_maximum) + '° <span class="lo">' +
                    Math.round(w.temperature_minimum) + '°</span></div>';
                html += '<div class="day-rain' + (rain >= 0.1 ? ' wet' : '') + '">' + icon('i-drop') +
                    (rain >= 0.1 ? rain.toFixed(1) + ' mm' : '0 mm') + '</div>';
                if (w.average_humidity) html += '<div class="day-hum">' + w.average_humidity + '% hum.</div>';
            } else {
                html += icon('w-none', 'day-icon') + '<div class="day-nodata">No data</div>';
            }
            html += '<div class="day-water">';
            VALVES.forEach(function (id) {
                var sec = (d.usage[id] || {})[key];
                if (sec) html += '<span class="tag tag-z' + id + '">Z' + id + ' ' + minutesShort(sec) + '</span>';
            });
            (planned[key] || []).forEach(function (p) {
                if (i < 0 || p.at < new Date()) return;
                var label = p.plan.skip ? 'skip' : minutesShort(p.plan.duration);
                html += '<span class="tag tag-plan' + (p.plan.skip ? ' tag-skip' : '') + '" title="' +
                    escapeHtml(fmtDuration(p.plan.base_duration) + ' set · ' + p.plan.percent + '% · ' + p.plan.reason) + '">Z' +
                    p.id + ' ' + hhmm(p.at) + ' · ' + label + '</span>';
            });
            html += '</div></div>';
        }
        var box = $('#days');
        box.innerHTML = html;

        var updated = parseDate(d.weather_updated);
        $('#weather-note').textContent = updated ? 'Forecast updated ' + phraseDay(updated) + ' at ' + hhmm(updated) : '';

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
        $('#adjust-note').textContent = (hasRun ? 'For the next run, ' : 'If watering ') + phraseDay(runDay) +
            (a.enabled ? '' : ' · adjustment disabled');

        $('#adjust-big').textContent = a.skip ? 'Skip' : a.percent + '%';
        $('.adjust-of').textContent = a.skip ? 'run skipped' : 'of programmed time';
        $('#adjust-panel').classList.toggle('skip', !!a.skip);
        $('#adjust-verdict').textContent = a.reason || '';

        var inp = a.inputs || {}, t = a.terms || {};
        function row(name, value, base, term) {
            var w = Math.min(100, Math.abs(term));
            return '<div class="factor"><div class="factor-head"><span class="factor-name">' + name +
                '</span><span class="factor-term ' + (term < 0 ? 'neg' : term > 0 ? 'pos' : '') + '">' + signed(term) +
                '</span></div><div class="factor-detail">' + value + (base ? ' <span class="factor-base">· baseline ' + base + '</span>' : '') +
                '</div><div class="factor-bar"><span class="' + (term < 0 ? 'neg' : 'pos') + '" style="width:' + w + '%"></span></div></div>';
        }
        $('#factors').innerHTML =
            row('Temperature', inp.temp != null ? inp.temp + '°C average' : 'no data', s.base_temp + '°C', t.temp || 0) +
            row('Humidity', inp.humidity != null ? inp.humidity + '% average' : 'no data', s.base_humidity + '%', t.humidity || 0) +
            row('Rain', (inp.rain || 0) + ' mm weighted (2 days before → 2 days after)', '', t.rain || 0) +
            (inp.min_temp != null ? '<p class="factor-foot">Minimum that day ' + inp.min_temp + '°C · frost skip at ≤ ' +
                s.freeze_temp + '°C · cold skip below ' + s.cold_temp + '°C average</p>' : '');

        $('#m-base').textContent = s.base_temp + '°C average, ' + s.base_humidity + '% humidity, no rain';
        $('#m-temp').textContent = s.temp_pct_per_c + '%';
        $('#m-hum').textContent = s.humidity_pct_per_pct + '%';
        $('#m-rain').textContent = s.rain_pct_per_mm + '%';
        $('#m-min').textContent = s.min_percent + '%';
    }

    // ------------------------------------------------------------------ loading
    var loading = null;
    function loadDashboard() {
        if (loading) return loading;
        loading = api('/dashboard').then(function (d) {
            state.dashboard = d;
            state.lastDashboardAt = Date.now();
            state.statusKey = d.valves.map(function (v) { return v.id + ':' + !!v.open; }).join(',');
            d.valves.forEach(renderZone);
            renderOverview(d);
            renderAdjustPanel(d);
            renderDays(d);
            setConnection(true);
        }).catch(function (e) {
            if (e.auth) return;
            setConnection(false);
            if (!state.dashboard) {
                $('#overview-title').textContent = 'Controller unreachable';
                $('#overview-sub').textContent = e.message + ' — retrying…';
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
            var t = open.length && state.timers[open[0].id];
            if (t) {
                var sub = $('#overview-sub').textContent.split(' · ');
                sub[0] = fmtDuration((t.endAt - Date.now()) / 1000) + ' remaining';
                $('#overview-sub').textContent = sub.join(' · ');
            }
        }
    }

    // ------------------------------------------------------------------ login
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
            $('#login-hint').textContent = s.configured ? ''
                : 'No password is set yet. On the Pi run: venv/bin/python3 scripts/set_password.py';
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
                    $('#login-error').textContent = err.message;
                    $('#login-password').select();
                });
        });
    });

    $('#logout').addEventListener('click', function () {
        setToken(null);
        state.dashboard = null;
        showLogin();
    });

    // ------------------------------------------------------------------ theme
    function currentTheme() {
        var t = document.documentElement.getAttribute('data-theme');
        if (t) return t;
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
    if (getToken()) loadDashboard(); else showLogin();
    setInterval(pollStatus, STATUS_POLL_MS);
    setInterval(tickAll, 1000);
})();

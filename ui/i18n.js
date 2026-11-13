/* Strop UI translations (Romanian default, English).
 * t(key, params) returns the text in the current language, replacing {name}
 * placeholders. Static markup uses data-i18n / data-i18n-attr attributes.
 * The chosen language is stored on the device (localStorage "strop-lang").
 */
(function () {
    'use strict';

    var LANGS = ['ro', 'en'];
    var DEFAULT_LANG = 'ro';

    var STRINGS = {
        ro: {
            // general
            'app.title': 'Strop · Irigații',
            'brand.sub': 'Irigarea grădinii',
            'conn.connecting': 'Se conectează…',
            'conn.online': 'Online · {time}',
            'conn.offline': 'Offline',
            'conn.title': 'Conexiunea cu controllerul',
            'theme.toggle': 'Comută modul întunecat',
            'lang.toggle': 'Schimbă limba',
            'logout': 'Deconectare',
            'today': 'Azi',
            'loading': 'Se încarcă…',
            'min': 'min',

            // days & dates
            'day.today': 'Azi', 'day.tomorrow': 'Mâine', 'day.yesterday': 'Ieri',
            'phrase.today': 'azi', 'phrase.tomorrow': 'mâine', 'phrase.yesterday': 'ieri', 'phrase.on': '{day}',
            'days.long': ['duminică', 'luni', 'marți', 'miercuri', 'joi', 'vineri', 'sâmbătă'],
            'days.longCap': ['Duminică', 'Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă'],
            'days.short': ['Dum', 'Lun', 'Mar', 'Mie', 'Joi', 'Vin', 'Sâm'],
            'days.every': 'Zilnic', 'days.weekdays': 'În zilele lucrătoare', 'days.weekends': 'În weekend',
            'days.none': 'Nicio zi',

            // overview
            'ov.watering': '{zones} udă',
            'ov.and': ' și ',
            'ov.remaining': 'încă {time}',
            'ov.next': 'Următoarea udare {day} la {time}',
            'ov.of': '{dur} din {base} ({pct}%)',
            'ov.skippedBefore': '{n} rulări sărite înainte ({reasons})',
            'ov.skippedBeforeOne': '1 rulare sărită înainte ({reasons})',
            'ov.noneNeeded': 'Nu e nevoie de udare în zilele următoare',
            'ov.allOff': 'Toate programele sunt oprite',
            'ov.nothing': 'Nimic nu va uda automat',
            'ov.unreachable': 'Controller indisponibil',
            'ov.retrying': '{error} — se reîncearcă…',
            'stat.today': 'Udat azi',
            'stat.week': 'Ultimele 7 zile',
            'stat.rain': 'Ploaie în 3 zile',

            // zone
            'zone.name': 'Zona {n}',
            'zone.rename': 'Redenumește zona',
            't.renamed': 'Zona se numește acum „{zone}”',
            'zone.watering': 'Udă',
            'zone.idle': 'Inactivă',
            'zone.next': 'Următoarea: {day} la {time} · {what}',
            'zone.skipped': 'sărită',
            'zone.scheduleOff': 'Program oprit',
            'zone.noSchedule': 'Fără program',
            'zone.waterNow': 'Udă acum',
            'zone.start': 'Pornește',
            'zone.stop': 'Oprește acum',
            'zone.started': 'Pornită la {time} · rulare de {dur}',
            'zone.remaining': 'rămas',
            'zone.off': 'Oprit',
            'zone.closed': 'supapă închisă',
            'zone.ariaRemaining': '{zone}: încă {time}',
            'zone.ariaClosed': '{zone}: supapă închisă',
            'zone.minutes': 'Minute',
            'zone.duration': 'Durată',
            'zone.schedule': 'Program',
            'zone.schedules': 'Programe',
            'zone.addSchedule': 'Adaugă',
            'sched.none': 'Niciun program. Adaugă unul ca zona să fie udată automat.',
            't.added': 'Program adăugat pentru {zone}',
            'e.overlap': 'Se suprapune cu programul „{other}” ({day} la {time}). Udările aceleiași zone nu se pot suprapune.',
            'e.overlap_self': 'Udările acestui program se suprapun între ele ({day} la {time}). Scurtează durata sau depărtează orele.',
            'e.too_many_schedules': 'Poți avea cel mult {max} programe pe zonă.',
            'zone.editSchedule': 'Editează programul',
            'zone.enableSchedule': 'Activează programul',
            'zone.set': 'Setat',
            'zone.adjusted': 'Ajustat · {day}',
            'zone.recent': 'Recent',
            'zone.noActivity': 'Nicio activitate încă',

            // schedule text
            'sched.notSet': 'Nesetat',
            'sched.at': '{days} la {time}',
            'sched.custom': 'Personalizat: {expr}',

            // editor
            'ed.days': 'Zile',
            'ed.startTime': 'Ora de start',
            'ed.duration': 'Durată (min)',
            'ed.advanced': 'Avansat (expresie cron)',
            'ed.cronHint': 'minut oră zi lună zi-săptămână · 0/7 = duminică',
            'ed.delete': 'Șterge programul',
            'ed.cancel': 'Anulează',
            'ed.save': 'Salvează',
            'ed.errDuration': 'Durata trebuie să fie între 1 și {max} minute.',
            'ed.errDays': 'Alege cel puțin o zi.',
            'ed.errTime': 'Alege ora de start.',
            'ed.confirmDelete': 'Ștergi programul „{what}” pentru {zone}?',

            // history
            'h.finished': 'Finalizat', 'h.stopped': 'Oprit manual', 'h.terminated': 'Întrerupt',
            'h.running': 'Rulează', 'h.skipped': 'Sărit', 'h.watchdog': 'Oprit de watchdog',
            'h.of': '{dur} din {base}',
            'h.pctOf': '{pct}% din {base}',

            // toasts
            't.minutes': 'Alege între 1 și {max} minute',
            't.started': '{zone} udă {min} min',
            't.stopped': '{zone} oprită',
            't.scheduleOn': 'Programul pentru {zone} e pornit',
            't.scheduleOff': 'Programul pentru {zone} e oprit',
            't.saved': 'Programul pentru {zone} a fost salvat',
            't.savedOff': 'Programul pentru {zone} a fost salvat (oprit)',
            't.deleted': 'Programul pentru {zone} a fost șters',

            // weather strip
            'w.title': 'Vreme și udare',
            'w.updated': 'Prognoză actualizată {day} la {time}',
            'w.noData': 'Fără date',
            'w.hum': '{h}% umid.',
            'w.legendZ1': 'Zona 1 udată', 'w.legendZ2': 'Zona 2 udată', 'w.legendPlan': 'Planificat',
            'w.skip': 'sărit',
            'w.tagTitle': '{base} setat · {pct}% · {reason}',
            'w.strip': 'Zilele trecute și următoare',

            // adjustment panel
            'adj.title': 'Ajustare după vreme',
            'adj.forNext': 'Pentru următoarea rulare, {day}',
            'adj.ifWatering': 'Dacă s-ar uda {day}',
            'adj.disabled': ' · ajustare dezactivată',
            'adj.skip': 'Sărit',
            'adj.ofProgrammed': 'din timpul programat',
            'adj.runSkipped': 'rulare sărită',
            'adj.temperature': 'Temperatură', 'adj.humidity': 'Umiditate', 'adj.rain': 'Ploaie',
            'adj.avgTemp': '{v}°C medie', 'adj.avgHum': '{v}% medie', 'adj.noData': 'fără date',
            'adj.rainWeighted': '{v} mm ponderat (2 zile înainte → 2 zile după)',
            'adj.baseline': '· referință {v}',
            'adj.minFoot': 'Minima zilei {min}°C · sărit la îngheț ≤ {freeze}°C · sărit la frig sub {cold}°C medie',
            'adj.how': 'Cum se calculează?',
            'adj.method': 'Pornește de la metoda Zimmerman (OpenSprinkler): timpul programat e potrivit pentru o zi tipică de vară ({base}). Fiecare grad mai rece scade {temp}, fiecare procent de umiditate peste referință scade {hum}, iar fiecare mm de ploaie scade {rain}. Ploaia contează din ultimele două zile, ziua udării și următoarele două zile (prognoza contează mai puțin). Timpul nu crește niciodată. Udarea e sărită la risc de îngheț, când e prea frig ca iarba să crească sau când ar rămâne mai puțin de {min} din timp.',
            'adj.methodBase': '{t}°C medie, {h}% umiditate, fără ploaie',

            // adjustment reasons (backend reason_key)
            'r.normal': 'Condiții normale',
            'r.disabled': 'Ajustarea după vreme e dezactivată',
            'r.no_data': 'Fără date meteo, durată completă',
            'r.pending': 'Prognoza nu ajunge încă până în ziua aceea. Ajustarea se calculează când apare prognoza (cu circa 5 zile înainte).',
            'r.short.pending': 'ajustare când apare prognoza',
            'adj.upTo': 'cel mult {dur}',
            'r.frost': 'Risc de îngheț (minima {min}°C)',
            'r.cold': 'Prea frig pentru iarbă ({temp}°C medie)',
            'r.not_needed.temp': 'Nu e necesar: vreme rece',
            'r.not_needed.humidity': 'Nu e necesar: umiditate mare',
            'r.not_needed.rain': 'Nu e necesar: ploaie ({rain} mm)',
            'r.too_short': 'Rularea ajustată ar fi prea scurtă',
            'r.f.temp': 'răcoare', 'r.f.humidity': 'umiditate', 'r.f.rain': 'ploaie {rain} mm',
            'r.short.frost': 'îngheț', 'r.short.cold': 'prea frig', 'r.short.not_needed': 'ploaie/umiditate',
            'r.short.too_short': 'prea scurt',

            // login
            'login.title': 'Conectare la Strop',
            'login.sub': 'Introdu parola controllerului.',
            'login.password': 'Parolă',
            'login.submit': 'Conectare',
            'login.notSet': 'Nu e setată nicio parolă. Pe Pi rulează: venv/bin/python3 scripts/set_password.py',

            // errors (backend codes)
            'e.wrong_password': 'Parolă greșită',
            'e.rate_limited': 'Prea multe încercări greșite. Reîncearcă peste {min} min.',
            'e.not_configured': 'Nu e setată nicio parolă pe controller.',
            'e.already_active': 'Supapa e deja deschisă',
            'e.invalid_duration': 'Durată invalidă',
            'e.invalid_cron': 'Expresie cron invalidă: {detail}',
            'e.unreachable': 'Controllerul nu poate fi contactat',
            'e.timeout': 'Controllerul nu răspunde',
            'e.request': 'Cererea a eșuat ({status})'
        },

        en: {
            'app.title': 'Strop · Irrigation',
            'brand.sub': 'Garden irrigation',
            'conn.connecting': 'Connecting…',
            'conn.online': 'Online · {time}',
            'conn.offline': 'Offline',
            'conn.title': 'Connection to controller',
            'theme.toggle': 'Toggle dark mode',
            'lang.toggle': 'Change language',
            'logout': 'Sign out',
            'today': 'Today',
            'loading': 'Loading…',
            'min': 'min',

            'day.today': 'Today', 'day.tomorrow': 'Tomorrow', 'day.yesterday': 'Yesterday',
            'phrase.today': 'today', 'phrase.tomorrow': 'tomorrow', 'phrase.yesterday': 'yesterday', 'phrase.on': 'on {day}',
            'days.long': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
            'days.longCap': ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
            'days.short': ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
            'days.every': 'Every day', 'days.weekdays': 'Weekdays', 'days.weekends': 'Weekends',
            'days.none': 'No days',

            'ov.watering': '{zones} watering',
            'ov.and': ' & ',
            'ov.remaining': '{time} remaining',
            'ov.next': 'Next watering {day} at {time}',
            'ov.of': '{dur} of {base} ({pct}%)',
            'ov.skippedBefore': '{n} runs skipped before ({reasons})',
            'ov.skippedBeforeOne': '1 run skipped before ({reasons})',
            'ov.noneNeeded': 'No watering needed in the coming days',
            'ov.allOff': 'All schedules are off',
            'ov.nothing': 'Nothing will water automatically',
            'ov.unreachable': 'Controller unreachable',
            'ov.retrying': '{error} — retrying…',
            'stat.today': 'Watered today',
            'stat.week': 'Last 7 days',
            'stat.rain': 'Rain next 3 days',

            'zone.name': 'Zone {n}',
            'zone.rename': 'Rename zone',
            't.renamed': 'Zone renamed to “{zone}”',
            'zone.watering': 'Watering',
            'zone.idle': 'Idle',
            'zone.next': 'Next: {day} at {time} · {what}',
            'zone.skipped': 'skipped',
            'zone.scheduleOff': 'Schedule off',
            'zone.noSchedule': 'No schedule',
            'zone.waterNow': 'Water now',
            'zone.start': 'Start',
            'zone.stop': 'Stop now',
            'zone.started': 'Started {time} · {dur} run',
            'zone.remaining': 'remaining',
            'zone.off': 'Off',
            'zone.closed': 'valve closed',
            'zone.ariaRemaining': '{zone}: {time} remaining',
            'zone.ariaClosed': '{zone}: valve closed',
            'zone.minutes': 'Minutes',
            'zone.duration': 'Duration',
            'zone.schedule': 'Schedule',
            'zone.schedules': 'Schedules',
            'zone.addSchedule': 'Add',
            'sched.none': 'No schedule yet. Add one to water this zone automatically.',
            't.added': 'Schedule added for {zone}',
            'e.overlap': 'Overlaps the schedule “{other}” ({day} at {time}). Runs of the same zone cannot overlap.',
            'e.overlap_self': 'Runs of this schedule overlap each other ({day} at {time}). Shorten the duration or space the times out.',
            'e.too_many_schedules': 'A zone can have at most {max} schedules.',
            'zone.editSchedule': 'Edit schedule',
            'zone.enableSchedule': 'Enable schedule',
            'zone.set': 'Set',
            'zone.adjusted': 'Adjusted · {day}',
            'zone.recent': 'Recent',
            'zone.noActivity': 'No activity yet',

            'sched.notSet': 'Not set',
            'sched.at': '{days} at {time}',
            'sched.custom': 'Custom: {expr}',

            'ed.days': 'Days',
            'ed.startTime': 'Start time',
            'ed.duration': 'Duration (min)',
            'ed.advanced': 'Advanced (cron expression)',
            'ed.cronHint': 'minute hour day month weekday · 0/7 = Sunday',
            'ed.delete': 'Delete schedule',
            'ed.cancel': 'Cancel',
            'ed.save': 'Save',
            'ed.errDuration': 'Duration must be between 1 and {max} minutes.',
            'ed.errDays': 'Pick at least one day.',
            'ed.errTime': 'Pick a start time.',
            'ed.confirmDelete': 'Delete the schedule “{what}” for {zone}?',

            'h.finished': 'Completed', 'h.stopped': 'Stopped', 'h.terminated': 'Interrupted',
            'h.running': 'Running', 'h.skipped': 'Skipped', 'h.watchdog': 'Watchdog stopped',
            'h.of': '{dur} of {base}',
            'h.pctOf': '{pct}% of {base}',

            't.minutes': 'Choose between 1 and {max} minutes',
            't.started': '{zone} watering for {min} min',
            't.stopped': '{zone} stopped',
            't.scheduleOn': '{zone} schedule on',
            't.scheduleOff': '{zone} schedule off',
            't.saved': '{zone} schedule saved',
            't.savedOff': '{zone} schedule saved (off)',
            't.deleted': '{zone} schedule deleted',

            'w.title': 'Weather & watering',
            'w.updated': 'Forecast updated {day} at {time}',
            'w.noData': 'No data',
            'w.hum': '{h}% hum.',
            'w.legendZ1': 'Zone 1 watered', 'w.legendZ2': 'Zone 2 watered', 'w.legendPlan': 'Planned',
            'w.skip': 'skip',
            'w.tagTitle': '{base} set · {pct}% · {reason}',
            'w.strip': 'Past and upcoming days',

            'adj.title': 'Weather adjustment',
            'adj.forNext': 'For the next run, {day}',
            'adj.ifWatering': 'If watering {day}',
            'adj.disabled': ' · adjustment disabled',
            'adj.skip': 'Skip',
            'adj.ofProgrammed': 'of programmed time',
            'adj.runSkipped': 'run skipped',
            'adj.temperature': 'Temperature', 'adj.humidity': 'Humidity', 'adj.rain': 'Rain',
            'adj.avgTemp': '{v}°C average', 'adj.avgHum': '{v}% average', 'adj.noData': 'no data',
            'adj.rainWeighted': '{v} mm weighted (2 days before → 2 days after)',
            'adj.baseline': '· baseline {v}',
            'adj.minFoot': 'Minimum that day {min}°C · frost skip at ≤ {freeze}°C · cold skip below {cold}°C average',
            'adj.how': 'How is this calculated?',
            'adj.method': 'Based on the Zimmerman method (OpenSprinkler): the programmed time is right for a typical summer day ({base}). Each degree colder removes {temp}, each % of humidity above the baseline removes {hum}, and each mm of rain removes {rain}. Rain counts from the two previous days, the run day and the next two days (forecasts count less). The time is never increased. Runs are skipped on frost risk, when it is too cold for grass to grow, or when less than {min} of the time would remain.',
            'adj.methodBase': '{t}°C average, {h}% humidity, no rain',

            'r.normal': 'Normal conditions',
            'r.disabled': 'Weather adjustment disabled',
            'r.no_data': 'No weather data, full duration',
            'r.pending': 'The forecast does not reach that day yet. The adjustment is computed once it does (about 5 days ahead).',
            'r.short.pending': 'adjusted once the forecast is in',
            'adj.upTo': 'up to {dur}',
            'r.frost': 'Frost risk (min {min}°C)',
            'r.cold': 'Too cold for grass ({temp}°C avg)',
            'r.not_needed.temp': 'Not needed: cool weather',
            'r.not_needed.humidity': 'Not needed: high humidity',
            'r.not_needed.rain': 'Not needed: rain ({rain} mm)',
            'r.too_short': 'Adjusted run too short',
            'r.f.temp': 'cool', 'r.f.humidity': 'humid', 'r.f.rain': 'rain {rain} mm',
            'r.short.frost': 'frost', 'r.short.cold': 'too cold', 'r.short.not_needed': 'rain/humidity',
            'r.short.too_short': 'too short',

            'login.title': 'Sign in to Strop',
            'login.sub': 'Enter the controller password.',
            'login.password': 'Password',
            'login.submit': 'Sign in',
            'login.notSet': 'No password is set yet. On the Pi run: venv/bin/python3 scripts/set_password.py',

            'e.wrong_password': 'Wrong password',
            'e.rate_limited': 'Too many failed attempts. Try again in {min} min.',
            'e.not_configured': 'No password is set on the controller.',
            'e.already_active': 'The valve is already open',
            'e.invalid_duration': 'Invalid duration',
            'e.invalid_cron': 'Invalid cron expression: {detail}',
            'e.unreachable': 'Controller unreachable',
            'e.timeout': 'Controller not responding',
            'e.request': 'Request failed ({status})'
        }
    };

    // OpenWeather descriptions (stored in English) -> Romanian
    var WEATHER_RO = {
        'clear sky': 'cer senin',
        'few clouds': 'puțini nori',
        'scattered clouds': 'nori răzleți',
        'broken clouds': 'nori fragmentați',
        'overcast clouds': 'cer acoperit',
        'light rain': 'ploaie slabă',
        'moderate rain': 'ploaie moderată',
        'heavy intensity rain': 'ploaie torențială',
        'very heavy rain': 'ploaie foarte puternică',
        'extreme rain': 'ploaie extremă',
        'freezing rain': 'ploaie înghețată',
        'light intensity shower rain': 'averse slabe',
        'shower rain': 'averse',
        'heavy intensity shower rain': 'averse puternice',
        'ragged shower rain': 'averse izolate',
        'light intensity drizzle': 'burniță slabă',
        'drizzle': 'burniță',
        'heavy intensity drizzle': 'burniță deasă',
        'light intensity drizzle rain': 'burniță cu ploaie slabă',
        'drizzle rain': 'burniță cu ploaie',
        'shower drizzle': 'averse de burniță',
        'thunderstorm': 'furtună',
        'thunderstorm with light rain': 'furtună cu ploaie slabă',
        'thunderstorm with rain': 'furtună cu ploaie',
        'thunderstorm with heavy rain': 'furtună cu ploaie torențială',
        'light thunderstorm': 'furtună slabă',
        'heavy thunderstorm': 'furtună puternică',
        'light snow': 'ninsoare slabă',
        'snow': 'ninsoare',
        'heavy snow': 'ninsoare abundentă',
        'sleet': 'lapoviță',
        'light shower sleet': 'averse slabe de lapoviță',
        'shower sleet': 'averse de lapoviță',
        'light rain and snow': 'lapoviță slabă',
        'rain and snow': 'lapoviță',
        'light shower snow': 'averse slabe de ninsoare',
        'shower snow': 'averse de ninsoare',
        'mist': 'aer cețos',
        'fog': 'ceață',
        'haze': 'pâclă',
        'smoke': 'fum',
        'dust': 'praf',
        'sand': 'nisip'
    };

    function storedLang() {
        try {
            var l = localStorage.getItem('strop-lang');
            if (LANGS.indexOf(l) !== -1) return l;
        } catch (e) {}
        return DEFAULT_LANG;
    }

    var lang = storedLang();

    function t(key, params) {
        var table = STRINGS[lang] || STRINGS[DEFAULT_LANG];
        var value = table[key];
        if (value === undefined) value = STRINGS.en[key];
        if (value === undefined) return key;
        if (typeof value !== 'string') return value;
        if (!params) return value;
        return value.replace(/\{(\w+)\}/g, function (m, name) {
            return params[name] !== undefined && params[name] !== null ? params[name] : m;
        });
    }

    function weather(desc) {
        if (!desc) return '';
        if (lang !== 'ro') return desc;
        return WEATHER_RO[String(desc).toLowerCase()] || desc;
    }

    // Apply translations to static markup inside `root`
    function apply(root) {
        root = root || document;
        Array.prototype.forEach.call(root.querySelectorAll('[data-i18n]'), function (el) {
            el.textContent = t(el.getAttribute('data-i18n'));
        });
        Array.prototype.forEach.call(root.querySelectorAll('[data-i18n-attr]'), function (el) {
            // format: "attr:key;attr2:key2"
            el.getAttribute('data-i18n-attr').split(';').forEach(function (pair) {
                var p = pair.split(':');
                if (p.length === 2) el.setAttribute(p[0].trim(), t(p[1].trim()));
            });
        });
        if (root === document) {
            document.documentElement.setAttribute('lang', lang);
            document.title = t('app.title');
        }
    }

    function setLang(next) {
        if (LANGS.indexOf(next) === -1) return;
        lang = next;
        try { localStorage.setItem('strop-lang', next); } catch (e) {}
        apply(document);
    }

    window.StropI18n = {
        t: t,
        weather: weather,
        apply: apply,
        setLang: setLang,
        getLang: function () { return lang; },
        locale: function () { return lang === 'ro' ? 'ro-RO' : 'en-GB'; },
        langs: LANGS
    };
})();

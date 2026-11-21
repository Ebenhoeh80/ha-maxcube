// German/French/Spanish/Italian locales write decimals with a comma.
const COMMA_LOCALE = /^(de|fr|es|it|pt|ru|nl|pl|tr|cs|da|sv|fi|no)/.test(
  (typeof navigator !== "undefined" && navigator.language) || "en"
);

// Translation system. Every key exists once per language; tests/test_card.py checks that every
// T.<key> used below exists in both.
const TRANSLATIONS = {
  de: {
    dayShort: { monday: "Mo", tuesday: "Di", wednesday: "Mi", thursday: "Do", friday: "Fr", saturday: "Sa", sunday: "So" },
    dayLong: { monday: "Montag", tuesday: "Dienstag", wednesday: "Mittwoch", thursday: "Donnerstag", friday: "Freitag", saturday: "Samstag", sunday: "Sonntag" },
    cardName: "MAX! Cube Wochenprogramm",
    cardDescription: "Wochenprogramm eines MAX!-Heizkörperthermostats bearbeiten und an den Cube senden.",
    noMaxThermostats: "Keine MAX!-Heizkörperthermostate mit Wochenprogramm gefunden.",
    noThermostatsFound: "keine Thermostate gefunden",
    zone: "Zone",
    temperature: "Temperatur",
    end: "Ende",
    splitZone: "Zone teilen",
    deleteZone: "Zone löschen",
    minusHalf: "−0,5 °C",
    plusHalf: "+0,5 °C",
    invalidTime: "ungültige Zeit",
    changed: "Geändert",
    revert: "Verwerfen",
    copyTo: (day) => `${day} kopieren nach`,
    copy: "Kopieren",
    targetDevices: (n) => `Zielgeräte (${n})`,
    dryRun: "Dry-Run",
    sending: "sendet…",
    send: (days) => `${days} an Cube senden`,
    sendIdle: "An Cube senden",
    resultState: { confirmed: "bestätigt", "dry-run": "geprüft", sent_not_confirmed: "gesendet, noch nicht bestätigt", failed: "fehlgeschlagen" },
    unsavedChanges: "ungespeicherte Änderungen",
    currentState: "Stand = Cube",
    discardUnsaved: "Ungespeicherte Änderungen verwerfen?",
    lastZoneCannotDelete: "Die letzte Zone kann nicht gelöscht werden.",
    maxZonesReached: (n) => `Maximal ${n} Zonen pro Tag.`,
    zoneTooShortToSplit: "Zone ist zu kurz zum Teilen.",
    changesDiscarded: "Änderungen verworfen.",
    copyNoTargets: "Keine Zieltage ausgewählt.",
    copyDone: (day) => `${day} auf die gewählten Tage kopiert.`,
    noTargetDevice: "Kein Zielgerät ausgewählt.",
    nothingToSend: "Keine Änderungen zum Senden.",
    confirmSend: (telegrams, devices, days, pct) =>
      `${telegrams} Funktelegramme an den Cube senden (${devices} Gerät(e) × ${days} Tag(e))?\nGeschätzter Funkzeit-Anteil: ca. ${pct} % (der Cube verweigert Schreiben ab 90 % Auslastung).`,
    statusDryRun: (days, count) => `Dry-Run: ${days} für ${count} Gerät(e) geprüft, nichts gesendet.`,
    statusSent: (days, count) => `${days} an ${count} Gerät(e) gesendet und vom Cube bestätigt.`,
    statusUnconfirmed: (items) => `Gesendet, aber noch nicht bestätigt: ${items}. Der Cube zeigt das neue Programm erst nach etwa zwei Minuten.`,
    statusFailed: (failed) => `Fehlgeschlagen: ${failed}`,
    statusStopped: "Weitere Telegramme wurden nicht gesendet.",
    dayError: (day, errors) => `${day}: ${errors.join(", ")}`,
    zoneError: (zone, msg) => `Zone ${zone}: ${msg}`,
    noPeriods: "kein Eintrag",
    maxPeriods: (n, actual) => `max. ${n} Zonen (${actual})`,
    timeNotInSteps: (time) => `${time} nicht in 5-Min-Schritten`,
    scheduleTimeError: (time) => `${time} liegt nicht im 5-Minuten-Raster`,
    timeNotRising: (time) => `${time} nicht aufsteigend`,
    tempError: (zone) => `Zone ${zone}: Temperatur ungültig`,
    mustEndAtMidnight: "letzte Zone muss bei 24:00 enden",
  },
  en: {
    dayShort: { monday: "Mo", tuesday: "Tu", wednesday: "We", thursday: "Th", friday: "Fr", saturday: "Sa", sunday: "Su" },
    dayLong: { monday: "Monday", tuesday: "Tuesday", wednesday: "Wednesday", thursday: "Thursday", friday: "Friday", saturday: "Saturday", sunday: "Sunday" },
    cardName: "MAX! Cube weekly programme",
    cardDescription: "Edit the weekly programme of a MAX! radiator thermostat and send it to the Cube.",
    noMaxThermostats: "No MAX! radiator thermostats with a weekly programme found.",
    noThermostatsFound: "no thermostats found",
    zone: "Zone",
    temperature: "Temperature",
    end: "End",
    splitZone: "Split zone",
    deleteZone: "Delete zone",
    minusHalf: "−0.5 °C",
    plusHalf: "+0.5 °C",
    invalidTime: "invalid time",
    changed: "Changed",
    revert: "Discard",
    copyTo: (day) => `Copy ${day} to`,
    copy: "Copy",
    targetDevices: (n) => `Target devices (${n})`,
    dryRun: "Dry run",
    sending: "sending…",
    send: (days) => `Send ${days} to Cube`,
    sendIdle: "Send to Cube",
    resultState: { confirmed: "confirmed", "dry-run": "checked", sent_not_confirmed: "sent, not confirmed yet", failed: "failed" },
    unsavedChanges: "unsaved changes",
    currentState: "State = Cube",
    discardUnsaved: "Discard unsaved changes?",
    lastZoneCannotDelete: "The last zone cannot be deleted.",
    maxZonesReached: (n) => `Maximum ${n} zones per day.`,
    zoneTooShortToSplit: "Zone is too short to split.",
    changesDiscarded: "Changes discarded.",
    copyNoTargets: "No target days selected.",
    copyDone: (day) => `${day} copied to the selected days.`,
    noTargetDevice: "No target device selected.",
    nothingToSend: "No changes to send.",
    confirmSend: (telegrams, devices, days, pct) =>
      `Send ${telegrams} radio telegrams to the Cube (${devices} device(s) × ${days} day(s))?\nEstimated radio time: about ${pct} % (the Cube refuses writes at 90 % duty cycle).`,
    statusDryRun: (days, count) => `Dry run: ${days} checked for ${count} device(s), nothing sent.`,
    statusSent: (days, count) => `${days} sent to ${count} device(s) and confirmed by the Cube.`,
    statusUnconfirmed: (items) => `Sent, but not confirmed yet: ${items}. The Cube shows the new programme only after about two minutes.`,
    statusFailed: (failed) => `Failed: ${failed}`,
    statusStopped: "No further telegrams were sent.",
    dayError: (day, errors) => `${day}: ${errors.join(", ")}`,
    zoneError: (zone, msg) => `Zone ${zone}: ${msg}`,
    noPeriods: "no entry",
    maxPeriods: (n, actual) => `max. ${n} zones (${actual})`,
    timeNotInSteps: (time) => `${time} not in 5-min steps`,
    scheduleTimeError: (time) => `${time} is not on the 5-minute grid`,
    timeNotRising: (time) => `${time} not ascending`,
    tempError: (zone) => `Zone ${zone}: temperature invalid`,
    mustEndAtMidnight: "last zone must end at 24:00",
  },
};

// Get translation object based on browser language
const LANG = ((typeof navigator !== "undefined" && navigator.language) || "en").startsWith("de") ? "de" : "en";
const T = TRANSLATIONS[LANG];

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const DAY_SHORT = T.dayShort;
const DAY_LONG = T.dayLong;

const STATE_ICON = { confirmed: "✔", "dry-run": "✔", sent_not_confirmed: "⚠", failed: "✖" };

const MAX_ZONES = 7;       // the Cube accepts at most seven setpoints per write
const MIN_TEMP = 4.5;
const MAX_TEMP = 30.5;
const END = 24 * 60;
const SNAP = 15;           // drag grid
const MIN_LEN = 15;        // shortest zone a drag may produce
// One programme write for one day is one radio telegram. Measured on a real Cube, six writes
// raised the duty cycle from 4 % to 21 %, so about 2.8 % each (docs/ENGINEERING.md, section 4).
// The service refuses to write at a duty cycle of 90 % and above.
const RADIO_PERCENT_PER_TELEGRAM = 2.8;
const CONFIRM_ABOVE_DEVICES = 1;
const CONFIRM_ABOVE_DAYS = 3;
const HOLD_AFTER_SEND_MS = 150000;  // the Cube shows a new programme only after about two minutes

const toMin = (hhmm) => {
  if (hhmm == null) return NaN;
  const s = String(hhmm).trim();
  if (s === "24:00") return END;
  const m = /^(\d{1,2}):(\d{2})$/.exec(s);
  if (!m) return NaN;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (h > 23 || mi > 59) return NaN;
  return h * 60 + mi;
};

const fmt = (mins) => {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
};

const snap = (mins, step = SNAP) => Math.round(mins / step) * step;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Everything that comes from outside (friendly names, entity ids, typed values, error texts)
// is escaped before it is written into innerHTML.
const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);

const fmtTemp = (t) => {
  const s = String(t);
  return COMMA_LOCALE ? s.replace(".", ",") : s;
};

// Accepts "17,5", "17.5", "17", 17.5
const parseTemp = (v) => {
  const n = Number(String(v).trim().replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
};

// Distinguishable bands: navy -> blue -> cyan -> green -> amber -> orange -> red.
const COLOR_STOPS = [
  [4.5, "#0d1b6e"],
  [8, "#1565c0"],
  [12, "#00bcd4"],
  [16, "#43a047"],
  [20, "#fbc02d"],
  [24, "#fb8c00"],
  [30.5, "#e53935"],
];

const _hex2rgb = (h) => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];

function tempColor(t) {
  const v = Number(t);
  if (!Number.isFinite(v)) return "#9e9e9e";
  if (v <= COLOR_STOPS[0][0]) return COLOR_STOPS[0][1];
  const last = COLOR_STOPS[COLOR_STOPS.length - 1];
  if (v >= last[0]) return last[1];
  for (let i = 0; i < COLOR_STOPS.length - 1; i++) {
    const [t0, c0] = COLOR_STOPS[i];
    const [t1, c1] = COLOR_STOPS[i + 1];
    if (v >= t0 && v <= t1) {
      const f = (v - t0) / (t1 - t0);
      const a = _hex2rgb(c0);
      const b = _hex2rgb(c1);
      const mix = a.map((x, k) => Math.round(x + (b[k] - x) * f));
      return `rgb(${mix[0]}, ${mix[1]}, ${mix[2]})`;
    }
  }
  return "#9e9e9e";
}

const LEGEND_GRADIENT = `linear-gradient(to right, ${COLOR_STOPS.map(
  ([t, c]) => `${c} ${(((t - MIN_TEMP) / (MAX_TEMP - MIN_TEMP)) * 100).toFixed(1)}%`
).join(", ")})`;

function normalize(days) {
  const out = {};
  for (const d of DAYS) {
    const src = Array.isArray(days?.[d]) ? days[d] : [];
    const list = src
      .map((p) => ({ until: String(p.until ?? ""), temp: Number(p.temp) }))
      .filter((p) => !Number.isNaN(toMin(p.until)) && !Number.isNaN(p.temp));
    out[d] = list.length ? list : [{ until: "24:00", temp: 20 }];
  }
  return out;
}

function validateDay(periods) {
  const errs = [];
  if (!periods.length) errs.push(T.noPeriods);
  if (periods.length > MAX_ZONES) errs.push(T.maxPeriods(MAX_ZONES, periods.length));
  let prev = 0;
  periods.forEach((p, i) => {
    const m = toMin(p.until);
    if (Number.isNaN(m)) {
      errs.push(T.zoneError(i + 1, T.invalidTime));
      return;
    }
    if (m % 5) errs.push(T.timeNotInSteps(p.until));
    if (m <= prev) errs.push(T.timeNotRising(p.until));
    prev = m;
    if (!(p.temp >= MIN_TEMP && p.temp <= MAX_TEMP) || (p.temp * 2) % 1) {
      errs.push(T.tempError(i + 1, p.temp));
    }
  });
  if (prev !== END) errs.push(T.mustEndAtMidnight);
  return errs;
}

class MaxCubeScheduleCard extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._config = null;
    this._entity = null;
    this._days = null;
    this._sel = { day: "monday", zone: 0 };
    this._copyTargets = new Set();
    this._targets = new Set();
    this._dry = false;
    this._status = null;
    this._busy = false;
    this._dirty = false;
    this._drag = null;
    this._suppressClick = false;
    this._changedDays = new Set();
    this._holdUntil = 0;
    this._onMove = this._onDragMove.bind(this);
    this._onUp = this._onDragEnd.bind(this);
  }

  static getStubConfig() {
    return { size: "medium" };
  }

  setConfig(config) {
    this._config = config || {};
    this._size = ["small", "medium", "large"].includes(this._config.size) ? this._config.size : "medium";
    const saved = this._loadSel();
    if (this._config.entity) this._entity = this._config.entity;
    else if (saved.entity) this._entity = saved.entity;
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._syncFromState();
    else this._refreshDaysIfStale();
    this._render();
  }

  get hass() {
    return this._hass;
  }

  // --- selection persistence (survives the card element being recreated) ----

  _storageKey() {
    const id = this._config?.id || this._config?.title || "default";
    return `maxcube-schedule-card:${id}`;
  }

  _loadSel() {
    try {
      return JSON.parse(localStorage.getItem(this._storageKey()) || "{}") || {};
    } catch {
      return {};
    }
  }

  _saveSel() {
    try {
      localStorage.setItem(
        this._storageKey(),
        JSON.stringify({ entity: this._entity, day: this._sel?.day })
      );
    } catch {
      /* storage may be unavailable */
    }
  }

  // --- data access ---------------------------------------------------------

  _scheduleEntities() {
    if (!this._hass) return [];
    return Object.keys(this._hass.states)
      .filter((id) => id.startsWith("climate."))
      .filter((id) => {
        const a = this._hass.states[id]?.attributes;
        return a && a.schedule !== undefined && this._isRadiator(id);
      })
      .sort();
  }

  // The service set_schedule only accepts radiator thermostats (schedule_radiator_only), but a
  // wall thermostat shows the programme of its room in the same attribute. Hide the wall
  // thermostats and entities of other integrations that happen to have a schedule attribute.
  _isRadiator(id) {
    const entry = this._hass.entities?.[id];
    if (entry?.platform && entry.platform !== "maxcube_local") return false;
    const model = this._hass.devices?.[entry?.device_id]?.model;
    if (model) return !/wall/i.test(model);
    // Device registry not available: only radiator thermostats report a valve position.
    return this._hass.states[id]?.attributes?.valve_position !== undefined;
  }

  _name(id) {
    const st = this._hass?.states[id];
    return st?.attributes?.friendly_name || id;
  }

  _syncFromState() {
    const ids = this._scheduleEntities();
    if (!ids.length) {
      this._entity = null;
      this._days = null;
      return;
    }
    const saved = this._loadSel();
    if (saved.entity && ids.includes(saved.entity)) this._entity = saved.entity;
    else if (!this._entity || !ids.includes(this._entity)) this._entity = ids[0];
    const st = this._hass.states[this._entity];
    this._days = normalize(st?.attributes?.schedule);
    this._targets = new Set([this._entity]);
    const day = saved.day && DAYS.includes(saved.day) ? saved.day : "monday";
    this._sel = { day, zone: 0 };
  }

  // The coordinator owns the schedule; only reload if the entity changed underneath us.
  _refreshDaysIfStale() {
    if (!this._entity) return;
    const st = this._hass.states[this._entity];
    if (!st) return;
    if (!this._days) {
      this._days = normalize(st.attributes?.schedule);
      return;
    }
    const src = st.attributes?.schedule;
    const changed =
      !src ||
      DAYS.some((d) => JSON.stringify(src[d] || []) !== JSON.stringify(this._days[d] || []));
    if (changed && !this._dirty && Date.now() >= this._holdUntil) this._days = normalize(src);
  }

  _periods(day = this._sel.day) {
    return this._days?.[day] || [];
  }

  // --- editing -------------------------------------------------------------

  _setTemp(v) {
    const p = this._periods()[this._sel.zone];
    if (!p || !Number.isFinite(v)) return;
    p.temp = v;
    this._dirty = true;
    this._changedDays.add(this._sel.day);
    this._repaint();
  }

  _setUntil(v) {
    const list = this._periods();
    const p = list[this._sel.zone];
    if (!p) return;
    p.until = String(v);
    this._dirty = true;
    this._changedDays.add(this._sel.day);
    this._repaint();
  }

  _normalizeTimeInput(el) {
    const m = toMin(el.value);
    const p = this._periods()[this._sel.zone];
    if (!p) return;
    if (!Number.isNaN(m)) {
      const oldUntil = p.until;
      p.until = fmt(m);
      el.value = fmt(m);
      this._dirty = true;
      if (oldUntil !== p.until) {
        this._changedDays.add(this._sel.day);
      }
    }
    this._render();
  }

  _normalizeTempInput(el) {
    const p = this._periods()[this._sel.zone];
    if (!p) return;
    p.temp = clamp(Math.round(p.temp * 2) / 2, MIN_TEMP, MAX_TEMP);
    el.value = fmtTemp(p.temp);
    this._repaint();
  }

  _deleteZone() {
    const list = this._periods();
    if (list.length <= 1) {
      this._status = { kind: "warn", text: T.lastZoneCannotDelete };
      this._render();
      return;
    }
    const i = this._sel.zone;
    list.splice(i, 1);
    // The day must stay contiguous: the previous zone now runs until the deleted end.
    if (i > 0) list[i - 1].until = this._periods()[Math.min(i, list.length - 1)]?.until || "24:00";
    if (i === 0) list[0].until = list[0].until || "24:00";
    this._sel.zone = Math.max(0, i - 1);
    this._dirty = true;
    this._changedDays.add(this._sel.day);
    this._render();
  }

  _addZone() {
    const list = this._periods();
    if (list.length >= MAX_ZONES) {
      this._status = { kind: "warn", text: T.maxZonesReached(MAX_ZONES) };
      this._render();
      return;
    }
    const i = this._sel.zone;
    const p = list[i];
    const start = i === 0 ? 0 : toMin(list[i - 1].until);
    const end = toMin(p.until);
    if (Number.isNaN(start) || Number.isNaN(end) || end - start < 10) {
      this._status = { kind: "warn", text: T.zoneTooShortToSplit };
      this._render();
      return;
    }
    let mid = snap(start + (end - start) / 2, 15);
    if (mid <= start || mid >= end) mid = start + 5;
    if (mid <= start || mid >= end) {
      this._status = { kind: "warn", text: T.zoneTooShortToSplit };
      this._render();
      return;
    }
    const newUntil = fmt(end);
    p.until = fmt(mid);
    list.splice(i + 1, 0, { until: newUntil, temp: p.temp });
    this._sel.zone = i + 1;
    this._dirty = true;
    this._changedDays.add(this._sel.day);
    this._render();
  }

  _copyDay() {
    if (!this._copyTargets.size) {
      this._status = { kind: "warn", text: T.copyNoTargets };
      this._render();
      return;
    }
    const src = this._periods();
    for (const d of this._copyTargets) {
      if (d === this._sel.day) continue;
      this._days[d] = src.map((p) => ({ until: p.until, temp: p.temp }));
      this._changedDays.add(d);
    }
    this._copyTargets.clear();
    this._dirty = true;
    this._status = { kind: "ok", text: T.copyDone(DAY_LONG[this._sel.day]) };
    this._render();
  }

  _toggleCopy(day) {
    if (this._copyTargets.has(day)) this._copyTargets.delete(day);
    else this._copyTargets.add(day);
    this._render();
  }

  _revert() {
    this._days = normalize(this._hass?.states[this._entity]?.attributes?.schedule);
    this._dirty = false;
    this._changedDays.clear();
    this._holdUntil = 0;
    this._status = { kind: "info", text: T.changesDiscarded };
    this._render();
  }

  // --- drag & drop ---------------------------------------------------------

  _boundaries(day) {
    const list = this._periods(day);
    const n = list.length;
    const b = [0];
    for (let k = 1; k < n; k++) b.push(toMin(list[k - 1].until));
    b.push(toMin(list[n - 1].until));
    return b;
  }

  _onDragStart(ev) {
    const zoneEl = ev.target.closest?.(".zone");
    if (!zoneEl) return;
    const day = zoneEl.dataset.day;
    const idx = Number(zoneEl.dataset.zone);
    const list = this._days?.[day];
    if (!list || !list[idx]) return;

    const rect = zoneEl.getBoundingClientRect();
    const xInZone = ev.clientX - rect.left;
    let mode = ev.target.dataset?.edge;
    if (!mode) {
      if (xInZone <= 10) mode = "start";
      else if (xInZone >= rect.width - 10) mode = "end";
      else mode = "move";
    }

    this._drag = {
      day,
      idx,
      mode,
      startX: ev.clientX,
      trackW: zoneEl.parentElement?.getBoundingClientRect().width || 1,
      // Always compute from the snapshot taken at drag start, never from the
      // already-mutated list: pointermove fires continuously and would otherwise
      // accumulate the delta on every event.
      origB: this._boundaries(day),
      moved: false,
      pointerId: ev.pointerId,
    };
    this._sel = { day, zone: idx };
    zoneEl.classList.add("dragging");

    document.addEventListener("pointermove", this._onMove);
    document.addEventListener("pointerup", this._onUp);
    document.addEventListener("pointercancel", this._onUp);

    ev.preventDefault();
    ev.stopPropagation();
  }

  _onDragMove(ev) {
    const d = this._drag;
    if (!d) return;
    const dx = ev.clientX - d.startX;
    const delta = Math.round(((dx / d.trackW) * END) / SNAP) * SNAP;
    if (delta === 0 && !d.moved) return;
    d.moved = true;
    this._applyDrag(d, delta);
    // Show live time during drag on the zone itself
    this._updateLiveDragDisplay(d);
    this._repaint();
  }

  _onDragEnd() {
    const d = this._drag;
    document.removeEventListener("pointermove", this._onMove);
    document.removeEventListener("pointerup", this._onUp);
    document.removeEventListener("pointercancel", this._onUp);
    if (!d) return;
    this._drag = null;
    // A plain click (no movement) must not re-render here: that would detach the
    // element the browser is about to send the click to, swallowing the selection.
    if (!d.moved) return;
    this._suppressClick = true;
    setTimeout(() => { this._suppressClick = false; }, 0);
    this._dirty = true;
    // Mark the day as changed
    this._changedDays.add(d.day);
    this._render();
  }

  _updateLiveDragDisplay(d) {
    // Show live time during drag by updating the zone's tooltip/label
    const day = d.day;
    const idx = d.idx;
    const list = this._days[day];
    if (!list || !list[idx]) return;

    const zoneEl = this.querySelector(`.zone[data-day="${day}"][data-zone="${idx}"]`);
    if (!zoneEl) return;

    const p = list[idx];
    const start = idx === 0 ? 0 : toMin(this._days[day][idx - 1]?.until || "00:00");
    const end = toMin(p.until);
    const label = `${fmt(start)}–${fmt(end)}: ${fmtTemp(p.temp)} °C`;

    zoneEl.title = label;
    const t = zoneEl.querySelector(".zt");
    if (t) t.textContent = `${fmtTemp(p.temp)}°`;
  }

  // Zones are contiguous ({until} model): a boundary is shared by two zones.
  // Always writes absolute values derived from the drag-start snapshot.
  _applyDrag(d, delta) {
    const { day, idx: i, mode } = d;
    const list = this._days[day];
    const n = list.length;
    if (!n) return;
    const b = d.origB;

    const resizeEnd = () => {
      if (i >= n - 1) return; // last zone always ends at 24:00
      const v = clamp(snap(b[i + 1] + delta), b[i] + MIN_LEN, b[i + 2] - MIN_LEN);
      list[i].until = fmt(v);
    };
    const resizeStart = () => {
      if (i <= 0) return; // first zone always starts at 00:00
      const v = clamp(snap(b[i] + delta), b[i - 1] + MIN_LEN, b[i + 1] - MIN_LEN);
      list[i - 1].until = fmt(v);
    };

    if (mode === "end") {
      resizeEnd();
      return;
    }
    if (mode === "start") {
      resizeStart();
      return;
    }

    // mode === "move"
    if (i === 0) {
      resizeEnd();
      return;
    }
    if (i === n - 1) {
      resizeStart();
      return;
    }

    const dur = b[i + 1] - b[i];
    const lo = b[i - 1] + MIN_LEN;
    const hi = b[i + 2] - MIN_LEN - dur;
    if (hi < lo) return;
    const newStart = clamp(snap(b[i] + delta), lo, hi);
    list[i - 1].until = fmt(newStart);
    list[i].until = fmt(newStart + dur);
  }

  // --- writing -------------------------------------------------------------

  _sendDays() {
    return DAYS.filter((d) => this._changedDays.has(d));
  }

  // Writes one day to one thermostat and returns the Cube's verdict for it.
  async _writeDay(entity, day) {
    const periods = this._periods(day).map((p) => ({ until: p.until, temperature: p.temp }));
    // callWS with return_response gives {context, response}; the response of an entity service
    // is keyed by entity id: {"climate.x": {"result": {"monday": "confirmed"}}} (a dry run
    // answers {"climate.x": {"dry_run": true, "would_write": {...}}}).
    const res = await this._hass.callWS({
      type: "call_service",
      domain: "maxcube_local",
      service: "set_schedule",
      service_data: { days: [day], periods, dry_run: this._dry },
      target: { entity_id: entity },
      return_response: true,
    });
    const body = res?.response?.[entity] ?? {};
    if (this._dry) return body.dry_run ? "dry-run" : "failed";
    return body.result?.[day] || "failed";
  }

  _confirmSend(targets, days) {
    const telegrams = targets.length * days.length;
    if (this._dry || (targets.length <= CONFIRM_ABOVE_DEVICES && days.length <= CONFIRM_ABOVE_DAYS)) {
      return true;
    }
    const pct = Math.ceil(telegrams * RADIO_PERCENT_PER_TELEGRAM);
    return confirm(T.confirmSend(telegrams, targets.length, days.length, pct));
  }

  _describe(r) {
    return `${this._name(r.entity)} (${DAY_SHORT[r.day]}${r.detail ? `: ${r.detail}` : ""})`;
  }

  _summary(results, days, targets, stopped) {
    const failed = results.filter((r) => r.state === "failed");
    const unconfirmed = results.filter((r) => r.state === "sent_not_confirmed");
    const dayNames = days.map((d) => DAY_SHORT[d]).join(", ");
    if (this._dry && !failed.length) return { kind: "ok", text: T.statusDryRun(dayNames, targets.length) };
    const parts = [];
    if (failed.length) {
      parts.push(T.statusFailed(failed.map((r) => this._describe(r)).join(", ")));
      if (stopped) parts.push(T.statusStopped);
    }
    if (unconfirmed.length) {
      parts.push(T.statusUnconfirmed(unconfirmed.map((r) => this._describe(r)).join(", ")));
    }
    if (!parts.length) return { kind: "ok", text: T.statusSent(dayNames, targets.length) };
    return { kind: failed.length ? "error" : "warn", text: parts.join(" ") };
  }

  async _send() {
    if (this._busy) return;
    const known = this._scheduleEntities();
    const targets = [...this._targets].filter((id) => known.includes(id));
    if (!targets.length) {
      this._status = { kind: "warn", text: T.noTargetDevice };
      this._render();
      return;
    }

    // Only days that were changed are sent; without a change nothing goes over the radio.
    const days = this._sendDays();
    if (!days.length) {
      this._status = { kind: "info", text: T.nothingToSend };
      this._render();
      return;
    }

    for (const d of days) {
      const errs = validateDay(this._periods(d));
      if (errs.length) {
        this._status = { kind: "error", text: T.dayError(DAY_LONG[d], errs) };
        this._render();
        return;
      }
    }
    if (!this._confirmSend(targets, days)) return;

    this._busy = true;
    this._render();

    const results = [];
    let stopped = false;
    try {
      for (const entity of targets) {
        for (const day of days) {
          try {
            results.push({ entity, day, state: await this._writeDay(entity, day) });
          } catch (err) {
            // Stop at the first error: the next telegrams would most likely fail the same way
            // (radio time used up, Cube unreachable) and only use up more radio time.
            results.push({ entity, day, state: "failed", detail: String(err?.message || err) });
            stopped = true;
            break;
          }
        }
        if (stopped) break;
      }
      this._status = { ...this._summary(results, days, targets, stopped), ts: new Date(), results };
      if (!this._dry) this._afterSend(results, days, targets);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  // Forget the days that arrived everywhere; keep the rest marked so a retry sends only those.
  _afterSend(results, days, targets) {
    for (const day of days) {
      const of = results.filter((r) => r.day === day);
      if (of.length === targets.length && of.every((r) => r.state !== "failed")) {
        this._changedDays.delete(day);
      }
    }
    this._dirty = this._changedDays.size > 0;
    if (results.some((r) => r.state === "sent_not_confirmed")) {
      this._holdUntil = Date.now() + HOLD_AFTER_SEND_MS;
    }
    const reached = [...new Set(results.filter((r) => r.state !== "failed").map((r) => r.entity))];
    // Ask HA to re-read the Cube so the card shows what was actually stored.
    setTimeout(() => {
      for (const entity of reached) {
        this._hass.callService("homeassistant", "update_entity", { entity_id: entity });
      }
    }, 1500);
  }

  // --- rendering -----------------------------------------------------------

  _renderGrid() {
    const hours = [];
    for (let h = 0; h <= 24; h += 3) hours.push(`<span class="hr" style="left:${(h / 24) * 100}%">${h}</span>`);

    const rows = DAYS.map((day) => {
      const list = this._periods(day);
      let cursor = 0;
      const segs = list
        .map((p, i) => {
          const end = Math.min(END, toMin(p.until));
          const start = cursor;
          const valid = !Number.isNaN(end);
          if (valid) cursor = end;
          const w = valid ? Math.max(0, ((cursor - start) / END) * 100) : 0;
          const sel = this._sel.day === day && this._sel.zone === i;
          const label = `${fmt(start)}–${valid ? fmt(end) : "?"}: ${fmtTemp(p.temp)} °C`;
          const changed = this._changedDays.has(day);
          return `<div class="zone${sel ? " sel" : ""}${changed ? " changed" : ""}" data-day="${day}" data-zone="${i}"
            style="width:${w}%;background:${tempColor(p.temp)}" title="${esc(label)}">
            <div class="edge l" data-edge="start"></div>
            <span class="zt">${fmtTemp(p.temp)}°</span>
            <div class="edge r" data-edge="end"></div>
            ${changed ? '<span class="changed-dot" title="${T.changed}"></span>' : ""}
          </div>`;
        })
        .join("");

      return `<div class="day${this._sel.day === day ? " active" : ""}${this._changedDays.has(day) ? " day-changed" : ""}" data-day="${day}">
        <div class="dl">${DAY_SHORT[day]}</div>
        <div class="track">${segs}</div>
        <div class="dstat">${this._dayStatus(day)}</div>
      </div>`;
    }).join("");

    return `<div class="grid">
      <div class="ruler"><div class="sp"></div><div class="hrwrap">${hours.join("")}</div><div class="sp"></div></div>
      ${rows}
    </div>`;
  }

  _dayStatus(day) {
    const errs = validateDay(this._periods(day));
    if (!errs.length) return "";
    return `<span class="bad" title="${esc(errs.join(", "))}">!</span>`;
  }

  _renderEditor() {
    const p = this._periods()[this._sel.zone];
    if (!p) return "";
    const idx = this._sel.zone;
    const list = this._periods();
    const start = idx === 0 ? 0 : toMin(list[idx - 1].until);
    const end = toMin(p.until);
    const m = toMin(p.until);
    const badTime = Number.isNaN(m);
    const offGrid = !badTime && m % 5 !== 0;

    return `<div class="editor">
      <div class="row">
        <label>${T.zone} ${idx + 1} / ${list.length}</label>
        <span class="span">${fmt(start)} – ${badTime ? "?" : fmt(end)}</span>
      </div>
      <div class="row">
        <label>${T.temperature}</label>
        <input type="text" class="tin temp" inputmode="decimal" value="${fmtTemp(p.temp)}"
          data-act="temp" spellcheck="false">
        <span class="unit">°C</span>
        <button class="btn sm" data-act="t-05" title="${T.minusHalf}">–</button>
        <button class="btn sm" data-act="t+05" title="${T.plusHalf}">+</button>
      </div>
      <div class="row">
        <label>${T.end}</label>
        <input type="text" class="tin time" value="${esc(p.until)}" data-act="until" inputmode="numeric"
          placeholder="HH:MM" spellcheck="false">
        ${offGrid ? `<span class="warn">${esc(T.scheduleTimeError(p.until))}</span>` : ""}
      </div>
      <div class="row">
        <button class="btn" data-act="add" ${list.length >= MAX_ZONES ? "disabled" : ""}>${T.splitZone}</button>
        <button class="btn danger" data-act="del" ${list.length <= 1 ? "disabled" : ""}>${T.deleteZone}</button>
        <button class="btn ghost" data-act="revert">${T.revert}</button>
      </div>
    </div>`;
  }

  _renderCopy() {
    const boxes = DAYS.map(
      (d) => `<label class="cb${this._copyTargets.has(d) ? " on" : ""}">
        <input type="checkbox" data-copy="${d}" ${this._copyTargets.has(d) ? "checked" : ""}
          ${d === this._sel.day ? "disabled" : ""}>
        ${DAY_SHORT[d]}
      </label>`
    ).join("");
    return `<div class="block">
      <div class="bh">${T.copyTo(DAY_LONG[this._sel.day])}</div>
      <div class="cbs">${boxes}</div>
      <button class="btn" data-act="copy">${T.copy}</button>
    </div>`;
  }

  _renderTargets() {
    const ids = this._scheduleEntities();
    const items = ids
      .map(
        (id) => `<label class="cb${this._targets.has(id) ? " on" : ""}">
        <input type="checkbox" data-target="${esc(id)}" ${this._targets.has(id) ? "checked" : ""}>
        ${esc(this._name(id))}
      </label>`
      )
      .join("");
    return `<div class="block">
      <div class="bh">${T.targetDevices(this._targets.size)}</div>
      <div class="cbs targets">${items || `<span class="muted">${T.noThermostatsFound}</span>`}</div>
    </div>`;
  }

  _renderStatus() {
    if (!this._status) return "";
    const s = this._status;
    const ts = s.ts
      ? new Date(s.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
      : "";
    const rows = (s.results || [])
      .map(
        (r) =>
          `<li>${STATE_ICON[r.state] || "•"} ${esc(this._name(r.entity))} — ${DAY_SHORT[r.day]} (${esc(T.resultState[r.state] || r.state)}${r.detail ? `: ${esc(r.detail)}` : ""})</li>`
      )
      .join("");
    return `<div class="status ${esc(s.kind)}">
      <div>${esc(s.text)}${ts ? ` <span class="muted">· ${ts}</span>` : ""}</div>
      ${rows ? `<ul>${rows}</ul>` : ""}
    </div>`;
  }

  _render() {
    const ids = this._scheduleEntities();

    if (!ids.length) {
      this.innerHTML = `<ha-card><div class="pad">${esc(T.noMaxThermostats)}</div></ha-card>`;
      return;
    }
    if (!this._days) this._syncFromState();
    // Never silently jump back to the first device: only correct an invalid pick.
    if (!this._entity || !ids.includes(this._entity)) {
      this._entity = ids[0];
      this._days = normalize(this._hass.states[this._entity]?.attributes?.schedule);
    }

    // Apply size class to host
    this.classList.remove("size-small", "size-medium", "size-large");
    this.classList.add(`size-${this._size}`);

    const tabs = ids
      .map(
        (id) =>
          `<button class="tab${id === this._entity ? " active" : ""}" data-ent="${esc(id)}">${esc(this._name(id))}</button>`
      )
      .join("");

    this.innerHTML = `
      <style>
        maxcube-schedule-card { display: block; }
        maxcube-schedule-card.size-small { font-size: 0.85em; }
        maxcube-schedule-card.size-medium { font-size: 1em; }
        maxcube-schedule-card.size-large { font-size: 1.15em; }
        .pad { padding: 12px; }
        ha-card { overflow: hidden; }
        .tabs { display: flex; overflow-x: auto; gap: 2px; padding: 4px 4px 0; }
        .tab {
          flex: 0 0 auto; border: none; cursor: pointer; padding: 6px 12px; font: inherit;
          font-size: 13px; background: var(--secondary-background-color, #f1f1f1);
          color: var(--primary-text-color, #212121);
        }
        .tab.active {
          background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
          font-weight: 600;
        }
        maxcube-schedule-card.size-small .wrap { padding: 4px 8px 8px; }
        maxcube-schedule-card.size-small .track { height: 20px; }
        maxcube-schedule-card.size-small .dl { width: 20px; flex: 0 0 20px; font-size: 9px; }
        maxcube-schedule-card.size-small .zt { font-size: 8px; }
        maxcube-schedule-card.size-small .legend span { font-size: 8px; }
        maxcube-schedule-card.size-small .scale { height: 6px; }
        maxcube-schedule-card.size-small .track { height: 20px; }
        maxcube-schedule-card.size-small .tin { width: 60px; font-size: 11px; }
        maxcube-schedule-card.size-small .tin.time { width: 70px; }
        maxcube-schedule-card.size-medium .wrap { padding: 8px 12px 12px; }
        maxcube-schedule-card.size-medium .track { height: 26px; }
        maxcube-schedule-card.size-medium .dl { width: 26px; flex: 0 0 26px; font-size: 11px; }
        maxcube-schedule-card.size-medium .zt { font-size: 10px; }
        maxcube-schedule-card.size-medium .legend span { font-size: 9px; }
        maxcube-schedule-card.size-medium .scale { height: 8px; }
        maxcube-schedule-card.size-medium .track { height: 26px; }
        maxcube-schedule-card.size-large .wrap { padding: 12px 16px 16px; }
        maxcube-schedule-card.size-large .track { height: 32px; }
        maxcube-schedule-card.size-large .dl { width: 32px; flex: 0 0 32px; font-size: 13px; }
        maxcube-schedule-card.size-large .zt { font-size: 12px; }
        maxcube-schedule-card.size-large .legend span { font-size: 10px; }
        maxcube-schedule-card.size-large .scale { height: 10px; }
        maxcube-schedule-card.size-large .track { height: 32px; }
        maxcube-schedule-card.size-large .tin { width: 88px; font-size: 14px; }
        maxcube-schedule-card.size-large .tin.time { width: 96px; }
        .wrap { padding: 8px 12px 12px; }
        .grid { width: 100%; }
        .ruler, .day { display: flex; align-items: center; }
        .ruler { height: 16px; }
        .sp { width: 26px; flex: 0 0 26px; }
        .hrwrap { position: relative; flex: 1; height: 14px; }
        .hr {
          position: absolute; transform: translateX(-50%); font-size: 9px;
          color: var(--secondary-text-color, #727272);
        }
        .hr:first-child { transform: none; }
        .hr:last-child { transform: translateX(-100%); }
        .day { gap: 0; margin: 2px 0; }
        .dl {
          width: 26px; flex: 0 0 26px; font-size: 11px;
          color: var(--secondary-text-color, #727272);
        }
        .day.active .dl { color: var(--primary-color, #03a9f4); font-weight: 700; }
        .track {
          flex: 1; display: flex; height: 26px; border-radius: 3px; overflow: hidden;
          background: repeating-linear-gradient(
            to right,
            var(--divider-color, #e0e0e0) 0 1px,
            transparent 1px calc(100% / 96));
          outline: 1px solid var(--divider-color, #e0e0e0);
        }
        .zone {
          display: flex; align-items: center; justify-content: center; position: relative;
          cursor: grab; color: #fff; font-size: 10px; overflow: hidden;
          touch-action: none; user-select: none;
          text-shadow: 0 1px 2px rgba(0,0,0,.55); border-right: 1px solid rgba(0,0,0,.28);
        }
        .zone:hover { filter: brightness(1.1); }
        .zone.sel { box-shadow: inset 0 0 0 2px var(--primary-text-color, #fff); }
        .zone.dragging { cursor: grabbing; filter: brightness(1.15); z-index: 3; }
        .zone.changed { box-shadow: inset 0 0 0 2px var(--primary-color, #03a9f4); }
        .zone .edge {
          position: absolute; top: 0; bottom: 0; width: 10px; z-index: 2; cursor: ew-resize;
        }
        .zone .edge.l { left: 0; }
        .zone .edge.r { right: 0; }
        .zone:hover .edge { background: rgba(255,255,255,.28); }
        .zt { white-space: nowrap; pointer-events: none; }
        .dstat { width: 16px; flex: 0 0 16px; text-align: right; }
        .bad { color: var(--error-color, #db4437); font-weight: 700; font-size: 11px; }
        .day-changed .dl { color: var(--primary-color, #03a9f4); font-weight: 700; }
        .changed-dot {
          position: absolute; top: 2px; right: 2px; width: 6px; height: 6px;
          border-radius: 50%; background: var(--primary-color, #03a9f4);
          box-shadow: 0 0 2px var(--primary-color, #03a9f4);
        }
        .dstat { width: 16px; flex: 0 0 16px; text-align: right; }
                .legend { display: flex; align-items: center; gap: 4px; margin: 8px 0 4px; font-size: 10px;
                          color: var(--secondary-text-color, #727272); }
                .legend span { font-size: 9px; white-space: nowrap; }
                .scale { flex: 1; height: 8px; border-radius: 4px; }
                .editor { margin-top: 8px; padding: 8px; border-radius: 6px;
                  background: var(--secondary-background-color, #f7f7f7); }
                .row { display: flex; align-items: center; gap: 6px; margin: 4px 0; flex-wrap: wrap; }
                .row label { font-size: 12px; color: var(--secondary-text-color, #727272); min-width: 84px; }
                .row.hint { font-size: 11px; color: var(--secondary-text-color, #727272); }
                .span { font-size: 12px; }
                .unit { font-size: 12px; color: var(--secondary-text-color, #727272); }
                .tin {
                  width: 74px; padding: 3px 6px; font: inherit; font-size: 13px;
                  border: 1px solid var(--divider-color, #ccc); border-radius: 4px;
                  background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
                }
                .tin.time { width: 84px; }
                .btn {
                  padding: 4px 10px; font: inherit; font-size: 12px; cursor: pointer;
                  border: 1px solid var(--divider-color, #ccc); border-radius: 4px;
                  background: var(--card-background-color, #fff); color: var(--primary-text-color, #212121);
                }
                .btn:hover { background: var(--secondary-background-color, #eee); }
                .btn.sm { padding: 2px 7px; }
                .btn.ghost { border-style: dashed; }
                .btn.danger { color: var(--error-color, #db4437); }
                .btn[disabled] { opacity: .45; cursor: not-allowed; }
                .warn { color: var(--warning-color, #ff9800); font-size: 11px; }
                .block { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--divider-color, #eee); }
                .bh { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
                .cbs { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
                .cb {
                  display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
                  border: 1px solid var(--divider-color, #ccc); border-radius: 12px;
                  font-size: 12px; cursor: pointer;
                }
                .cb.on { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff);
                  border-color: transparent; }
                .cb input { margin: 0; }
                .cbs.targets .cb { font-size: 11px; }
                .muted { color: var(--secondary-text-color, #727272); font-size: 11px; }
                .status { margin-top: 10px; padding: 8px; border-radius: 6px; font-size: 12px; }
                .status.ok { background: rgba(76,175,80,.14); color: var(--primary-text-color, #212121); }
                .status.warn { background: rgba(255,152,0,.16); }
                .status.error { background: rgba(219,68,55,.14); }
                .status ul { margin: 4px 0 0; padding-left: 16px; }
                .actions { display: flex; align-items: center; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
                .actions .spacer { flex: 1; }
                .chk { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; }
              </style>
              <ha-card>
                <div class="tabs">${tabs}</div>
                <div class="wrap">
                  ${this._renderGrid()}
                  <div class="legend">
                    <span>${fmtTemp(MIN_TEMP)} °C</span>
                    <div class="scale" style="background:${LEGEND_GRADIENT}"></div>
                    <span>${fmtTemp(MAX_TEMP)} °C</span>
                  </div>
                  ${this._renderEditor()}
                  ${this._renderCopy()}
                  ${this._renderTargets()}
                  <div class="actions">
                    <label class="chk"><input type="checkbox" data-act="dry" ${this._dry ? "checked" : ""}> ${T.dryRun}</label>
                    <span class="spacer"></span>
                    <span class="muted" data-dirty>${this._dirty ? T.unsavedChanges : T.currentState}</span>
                    <button class="btn" data-act="send" ${this._busy || !this._changedDays.size ? "disabled" : ""}>
                      ${this._busy ? T.sending : this._sendText()}
                    </button>
                  </div>
                  ${this._renderStatus()}
                </div>
              </ha-card>
            `;

    this._wire();
  }

  // Update zone widths/colours without rebuilding the DOM, so inputs keep focus.
  _repaint() {
    DAYS.forEach((day) => {
      const list = this._days?.[day] || [];
      let cursor = 0;
      list.forEach((p, i) => {
        const end = Math.min(END, toMin(p.until));
        const start = cursor;
        const valid = !Number.isNaN(end);
        if (valid) cursor = end;
        const w = valid ? Math.max(0, ((cursor - start) / END) * 100) : 0;
        const el = this.querySelector(`.zone[data-day="${day}"][data-zone="${i}"]`);
        if (!el) return;
        el.style.width = `${w}%`;
        el.style.background = tempColor(p.temp);
        const t = el.querySelector(".zt");
        if (t) t.textContent = `${fmtTemp(p.temp)}°`;
        el.title = `${fmt(start)}–${valid ? fmt(end) : "?"}: ${fmtTemp(p.temp)} °C`;
      });
    });

    const sendBtn = this.querySelector('[data-act="send"]');
    if (sendBtn && !this._busy) {
      sendBtn.disabled = !this._changedDays.size;
      sendBtn.textContent = this._sendText();
    }
    this.querySelectorAll(".zone").forEach((z) =>
      z.classList.toggle("changed", this._changedDays.has(z.dataset.day))
    );

    const dirtyEl = this.querySelector("[data-dirty]");
    if (dirtyEl) {
      dirtyEl.textContent = this._dirty ? T.unsavedChanges : T.currentState;
      dirtyEl.style.color = this._dirty ? "var(--warning-color, #ff9800)" : "";
    }
  }

  _wire() {
    this.querySelectorAll(".tab").forEach((b) =>
      b.addEventListener("click", () => {
        if (this._dirty && !confirm(T.discardUnsaved)) return;
        this._entity = b.dataset.ent;
        this._days = normalize(this._hass.states[this._entity]?.attributes?.schedule);
        this._dirty = false;
        this._changedDays.clear();
        this._holdUntil = 0;
        this._status = null;
        this._sel = { day: this._sel?.day || "monday", zone: 0 };
        this._saveSel();
        this._render();
      })
    );

    this.querySelectorAll(".day").forEach((d) =>
      d.addEventListener("click", () => {
        if (this._suppressClick) return;
        this._sel.day = d.dataset.day;
        this._sel.zone = 0;
        this._saveSel();
        this._render();
      })
    );

    this.querySelectorAll(".zone").forEach((z) => {
      z.addEventListener("pointerdown", (ev) => this._onDragStart(ev));
      z.addEventListener("click", (ev) => {
        if (this._suppressClick) return;
        ev.stopPropagation();
        this._sel.day = z.dataset.day;
        this._sel.zone = Number(z.dataset.zone);
        this._render();
      });
    });

    const editor = this.querySelector(".editor");
    if (editor) {
      editor.addEventListener("input", (ev) => {
        const act = ev.target.dataset.act;
        if (act === "temp") {
          const v = parseTemp(ev.target.value);
          if (Number.isFinite(v)) this._setTemp(v);
        } else if (act === "until") {
          this._setUntil(ev.target.value);
        }
      });
      editor.addEventListener("change", (ev) => {
        const act = ev.target.dataset.act;
        if (act === "temp") this._normalizeTempInput(ev.target);
        else if (act === "until") this._normalizeTimeInput(ev.target);
      });
      editor.addEventListener("click", (ev) => {
        const act = ev.target.dataset.act;
        if (!act) return;
        const p = this._periods()[this._sel.zone];
        if (act === "t-05") this._setTemp(Math.max(MIN_TEMP, (p?.temp ?? 20) - 0.5));
        else if (act === "t+05") this._setTemp(Math.min(MAX_TEMP, (p?.temp ?? 20) + 0.5));
        else if (act === "del") this._deleteZone();
        else if (act === "add") this._addZone();
        else if (act === "revert") this._revert();
      });
      // Reflect +/- changes in the visible input without a full re-render.
      editor.addEventListener("click", (ev) => {
        const act = ev.target.dataset.act;
        if (act !== "t-05" && act !== "t+05") return;
        const inp = editor.querySelector(".tin.temp");
        const p = this._periods()[this._sel.zone];
        if (inp && p) inp.value = fmtTemp(p.temp);
      });
    }

    this.querySelectorAll("[data-copy]").forEach((c) =>
      c.addEventListener("change", () => this._toggleCopy(c.dataset.copy))
    );

    this.querySelectorAll("[data-target]").forEach((c) =>
      c.addEventListener("change", () => {
        const id = c.dataset.target;
        if (c.checked) this._targets.add(id);
        else this._targets.delete(id);
        this._render();
      })
    );

    const copyBtn = this.querySelector('[data-act="copy"]');
    if (copyBtn) copyBtn.addEventListener("click", () => this._copyDay());

    const dry = this.querySelector('[data-act="dry"]');
    if (dry) dry.addEventListener("change", () => { this._dry = dry.checked; });

    const send = this.querySelector('[data-act="send"]');
    if (send) send.addEventListener("click", () => this._send());
  }

  _sendText() {
    const days = this._sendDays();
    return days.length ? T.send(days.map((d) => DAY_SHORT[d]).join(", ")) : T.sendIdle;
  }

  getCardSize() {
    return 9;
  }
}

customElements.define("maxcube-schedule-card", MaxCubeScheduleCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "maxcube-schedule-card",
  name: T.cardName,
  description: T.cardDescription,
});
// =========================================================================
// Evac-AI — single-page step-based experience
// =========================================================================

const TOTAL_STEPS = 7;
const state = {
  step: 1,
  selected: null,        // { lat, lon, display_name }
  locationCountry: null, // "us" | "ca" from Step 1 (alert feed)
  locationRegionCode: null, // e.g. CA, ON
  alertScope: "point",   // mirrors advanced alerts UI (point | region | national)
  alertCountry: "us",
  alerts: null,          // last alerts payload
  alertsText: "",        // textual summary fed to risk + watsonx
  weather: null,
  weatherText: "",
  resources: null,
  resourcesText: "",
  risk: null,
  riskText: "",
};

// =========================================================================
// Tiny helpers
// =========================================================================
function $(id) { return document.getElementById(id); }
function $$(sel, root = document) { return [...root.querySelectorAll(sel)]; }

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function setDisabled(id, disabled) {
  const el = $(id);
  if (el) el.disabled = disabled;
}

async function safeJson(res) {
  const text = await res.text();
  try { return JSON.parse(text); } catch { return { raw: text }; }
}

// =========================================================================
// Step machine
// =========================================================================
function goToStep(n) {
  n = Math.max(1, Math.min(TOTAL_STEPS, Number(n) || 1));
  state.step = n;
  $$(".step").forEach((el) => {
    const s = Number(el.getAttribute("data-step"));
    const active = s === n;
    el.classList.toggle("is-active", active);
    el.setAttribute("aria-hidden", active ? "false" : "true");
  });
  $$(".stepper__item").forEach((el) => {
    const s = Number(el.getAttribute("data-step"));
    el.classList.toggle("is-active", s === n);
    el.classList.toggle("is-done", s < n);
  });
  const bar = $("stepperBar");
  if (bar) bar.style.width = `${Math.round((n / TOTAL_STEPS) * 100)}%`;
  // Scroll to top of step content for context
  const stepEl = $(`step-${n}`);
  if (stepEl) {
    const top = stepEl.getBoundingClientRect().top + window.scrollY - 100;
    window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
  }
  refreshGuards();
  updateWeatherLocationUI();
  updateAlertsSummaryLine();

  if (n === 2 && state.selected && state.locationCountry) {
    syncAlertFormFromLocation();
    fetchAlerts({ mode: "default" });
  }
  if (n === 3 && state.selected) {
    fetchWeather();
  }
}

function syncAlertContext() {
  const scopeEl = $("alertScope");
  const countryEl = $("alertCountry");
  if (scopeEl) state.alertScope = scopeEl.value;
  if (countryEl) state.alertCountry = countryEl.value;
}

/** Point used for Open-Meteo: always the resolved Step 1 location. */
function effectiveWeatherPoint() {
  return state.selected;
}

function updateWeatherLocationUI() {
  const line = $("weatherForLine");
  if (!line) return;
  line.textContent = state.selected
    ? `Weather for: ${state.selected.display_name}`
    : "Select a location in Step 1 first.";
}

function countryLabel(code) {
  if (code === "us") return "United States";
  if (code === "ca") return "Canada";
  return code || "";
}

function updateAlertsSummaryLine() {
  const el = $("alertsSummaryLine");
  if (!el) return;
  if (!state.selected || !state.locationCountry) {
    el.textContent = "";
    return;
  }
  el.textContent = `Alerts for: ${state.selected.display_name} · ${countryLabel(state.locationCountry)} · this location (point)`;
}

/** Keep advanced alert form aligned with Step 1 when opening Alerts. */
function syncAlertFormFromLocation() {
  const c = $("alertCountry");
  const s = $("alertScope");
  if (c && state.locationCountry) c.value = state.locationCountry;
  if (s) s.value = "point";
  populateAlertRegions();
  onAlertScopeChange();
}

function selectedResourceTypes() {
  return $$(".js-resource-type:checked").map((el) => el.value);
}

function updateResourcesButtonState() {
  const loc = !!state.selected;
  const types = selectedResourceTypes();
  const ok = loc && types.length > 0;
  setDisabled("btnResources", !ok);
  const hint = $("resourceTypesHint");
  if (hint) {
    hint.hidden = !loc || types.length > 0;
  }
}

function refreshGuards() {
  syncAlertContext();
  // Step 1 next: resolved point + explicit alert country
  const next1 = $("btnStep1Next");
  if (next1) next1.disabled = !(state.selected && state.locationCountry);

  const canPointAlerts = !!(state.selected && state.locationCountry);
  setDisabled("btnAlertsRefresh", !canPointAlerts);
  updateAlertsButtonState();
  setDisabled("btnWeather", !effectiveWeatherPoint());
  updateResourcesButtonState();
  setDisabled("btnRisk", !state.selected);
  setDisabled("btnPlan", !state.selected);
}

// Wire data-next / data-prev / stepper clicks
function bindStepNav() {
  $$("[data-next]").forEach((b) => {
    b.addEventListener("click", () => goToStep(state.step + 1));
  });
  $$("[data-prev]").forEach((b) => {
    b.addEventListener("click", () => goToStep(state.step - 1));
  });
  $$(".stepper__item").forEach((el) => {
    el.addEventListener("click", () => {
      const s = Number(el.getAttribute("data-step"));
      // Allow jumping to any step that doesn't require missing prereqs.
      if ((!state.selected || !state.locationCountry) && s !== 1) {
        goToStep(1);
        return;
      }
      goToStep(s);
    });
  });
  const restart = $("btnRestart");
  if (restart) {
    restart.addEventListener("click", () => {
      state.selected = null;
      state.locationCountry = null;
      state.locationRegionCode = null;
      state.alerts = null;
      state.alertsText = "";
      state.weather = null;
      state.weatherText = "";
      state.resources = null;
      state.resourcesText = "";
      state.risk = null;
      state.riskText = "";
      hideGeoError();
      const gr = $("geoResults");
      if (gr) gr.innerHTML = "";
      const al = $("alerts");
      if (al) al.innerHTML = "";
      const wx = $("weather");
      if (wx) wx.innerHTML = "";
      const locPostal = $("locPostal");
      if (locPostal) locPostal.value = "";
      const qEl = $("q");
      if (qEl) qEl.value = "";
      populateLocRegions();
      goToStep(1);
    });
  }
}

// =========================================================================
// US states / Canadian provinces
// =========================================================================
const US_STATES = [
  ["AL","Alabama"],["AK","Alaska"],["AZ","Arizona"],["AR","Arkansas"],["CA","California"],
  ["CO","Colorado"],["CT","Connecticut"],["DE","Delaware"],["FL","Florida"],["GA","Georgia"],
  ["HI","Hawaii"],["ID","Idaho"],["IL","Illinois"],["IN","Indiana"],["IA","Iowa"],
  ["KS","Kansas"],["KY","Kentucky"],["LA","Louisiana"],["ME","Maine"],["MD","Maryland"],
  ["MA","Massachusetts"],["MI","Michigan"],["MN","Minnesota"],["MS","Mississippi"],["MO","Missouri"],
  ["MT","Montana"],["NE","Nebraska"],["NV","Nevada"],["NH","New Hampshire"],["NJ","New Jersey"],
  ["NM","New Mexico"],["NY","New York"],["NC","North Carolina"],["ND","North Dakota"],["OH","Ohio"],
  ["OK","Oklahoma"],["OR","Oregon"],["PA","Pennsylvania"],["RI","Rhode Island"],["SC","South Carolina"],
  ["SD","South Dakota"],["TN","Tennessee"],["TX","Texas"],["UT","Utah"],["VT","Vermont"],
  ["VA","Virginia"],["WA","Washington"],["WV","West Virginia"],["WI","Wisconsin"],["WY","Wyoming"],
  ["DC","District of Columbia"],
];
const CAN_PROVINCES = [
  ["AB","Alberta"],["BC","British Columbia"],["MB","Manitoba"],["NB","New Brunswick"],
  ["NL","Newfoundland and Labrador"],["NS","Nova Scotia"],["NT","Northwest Territories"],
  ["NU","Nunavut"],["ON","Ontario"],["PE","Prince Edward Island"],["QC","Quebec"],
  ["SK","Saskatchewan"],["YT","Yukon"],
];

function populateLocRegions() {
  const sel = $("locRegion");
  const country = $("locCountry")?.value;
  const label = $("locRegionLabel");
  if (!sel || !label) return;
  sel.innerHTML = '<option value="">— choose —</option>';
  const list = country === "ca" ? CAN_PROVINCES : US_STATES;
  label.textContent = country === "ca" ? "Province / territory" : "State";
  for (const [code, name] of list) {
    const o = document.createElement("option");
    o.value = code;
    o.textContent = `${code} — ${name}`;
    sel.appendChild(o);
  }
}

function populateAlertRegions() {
  const sel = $("alertRegion");
  const country = $("alertCountry").value;
  const label = $("alertRegionLabel");
  sel.innerHTML = '<option value="">— choose —</option>';
  const list = country === "ca" ? CAN_PROVINCES : US_STATES;
  label.textContent = country === "ca" ? "Province / territory" : "State";
  for (const [code, name] of list) {
    const o = document.createElement("option");
    o.value = code;
    o.textContent = `${code} — ${name}`;
    sel.appendChild(o);
  }
}

function updateAlertsButtonState() {
  const scopeEl = $("alertScope");
  const countryEl = $("alertCountry");
  if (!scopeEl) return;
  const scope = scopeEl.value;
  const country = countryEl.value;
  if (scope === "national") return setDisabled("btnAlertsApply", false);
  if (scope === "region") {
    if (country === "auto") return setDisabled("btnAlertsApply", true);
    const reg = $("alertRegion").value;
    return setDisabled("btnAlertsApply", !reg);
  }
  setDisabled("btnAlertsApply", !state.selected);
}

function onAlertCountryChange() {
  const country = $("alertCountry").value;
  if (country === "auto" && $("alertScope").value === "region") {
    $("alertScope").value = "point";
  }
  populateAlertRegions();
  onAlertScopeChange();
}

function onAlertScopeChange() {
  syncAlertContext();
  const scope = $("alertScope").value;
  const country = $("alertCountry").value;
  const showRegion = scope === "region" && country !== "auto";
  const row = $("alertRegionRow");
  if (row) row.style.display = showRegion ? "flex" : "none";
  updateAlertsButtonState();
  refreshGuards();
}

// =========================================================================
// Weather formatting helpers
// =========================================================================
function selectedTempUnit() {
  const el = document.querySelector('input[name="tempUnit"]:checked');
  return el ? el.value : "f";
}
function tempSuffix(letter) { return letter === "c" ? "°C" : "°F"; }
function windSpeedSuffixFromApi(data, tempLetter) {
  if (data && data.wind_speed_unit) return data.wind_speed_unit;
  return tempLetter === "c" ? "km/h" : "mph";
}
function formatWindSpeed(speed, unitSuffix) {
  if (speed == null || speed === "") return "?";
  const s = Number(speed);
  return `${Number.isFinite(s) ? s.toFixed(s >= 10 ? 0 : 1) : speed} ${unitSuffix}`;
}
function precipWindowLabel(intervalSec) {
  if (intervalSec === 900) return "prior 15 min";
  if (typeof intervalSec === "number" && intervalSec > 0) {
    const m = Math.round(intervalSec / 60);
    return m <= 1 ? "prior 1 min" : `prior ${m} min`;
  }
  return "prior interval (model sum)";
}
function formatPrecipitationSummary(cur) {
  const win = precipWindowLabel(cur.interval);
  const total = cur.precipitation;
  const rain = Number(cur.rain);
  const showers = Number(cur.showers);
  const rainMm = Number.isFinite(rain) ? rain : null;
  const shMm = Number.isFinite(showers) ? showers : null;
  const liquid = rainMm != null && shMm != null ? rainMm + shMm : null;
  const totalStr = total != null && total !== "" ? String(total) : "?";
  if (liquid != null) {
    const liqStr = liquid.toFixed(liquid >= 10 ? 1 : 2);
    return `${totalStr} mm total in ${win} (rain+showers+snow); liquid ${liqStr} mm`;
  }
  return `${totalStr} mm in ${win} (Open-Meteo: not instantaneous)`;
}

// =========================================================================
// STEP 1 — Structured location + optional advanced geocode
// =========================================================================
function hideGeoError() {
  const el = $("geoError");
  if (!el) return;
  el.hidden = true;
  el.textContent = "";
}

function showGeoError(msg) {
  const el = $("geoError");
  if (!el) return;
  el.hidden = false;
  el.textContent = msg;
}

function onLocInputsChanged() {
  state.selected = null;
  state.locationCountry = null;
  state.locationRegionCode = null;
  hideGeoError();
  const box = $("geoResults");
  if (box) box.innerHTML = "";
  refreshGuards();
  updateAlertsSummaryLine();
}

function buildStructuredGeocodeQuery() {
  const country = $("locCountry").value;
  const regionCode = $("locRegion").value;
  const zip = ($("locPostal")?.value || "").trim();
  const list = country === "ca" ? CAN_PROVINCES : US_STATES;
  const regionName = list.find(([c]) => c === regionCode)?.[1] || "";
  if (country === "us") {
    if (zip) return `${zip} ${regionName} USA`;
    return `${regionName}, USA`;
  }
  if (zip) return `${zip} ${regionName} Canada`;
  return `${regionName}, Canada`;
}

/** US ZIP → 5 digits (ignores ZIP+4 after dash). */
function usZipFive(zip) {
  const d = String(zip || "").replace(/\D/g, "");
  return d.length >= 5 ? d.slice(0, 5) : "";
}

function normalizeCanadianPostal(zip) {
  const s = String(zip || "").replace(/\s+/g, " ").trim().toUpperCase();
  return s;
}

async function fetchGeocodeResults(q) {
  const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
  const data = await safeJson(res);
  return { ok: res.ok, data, results: data.results || [] };
}

function renderSelectedLocationPill(r) {
  return `
    <div class="pill" style="border-color: rgba(52,211,153,0.45); background: rgba(52,211,153,0.07)">
      <div style="flex:1">
        <strong>Selected location</strong>
        <div class="meta">${esc(r.display_name)}</div>
      </div>
      <div class="meta">lat ${Number(r.lat).toFixed(4)}, lon ${Number(r.lon).toFixed(4)}</div>
    </div>
  `;
}

function finalizeGeocodeChoice(r, { structured } = { structured: false }) {
  state.selected = {
    lat: Number(r.lat),
    lon: Number(r.lon),
    display_name: r.display_name,
  };
  state.locationCountry = $("locCountry").value;
  state.locationRegionCode = structured ? $("locRegion").value : null;
  hideGeoError();
  refreshGuards();
  updateAlertsSummaryLine();
}

async function useStructuredLocation() {
  const regionCode = $("locRegion")?.value;
  if (!$("locCountry")?.value || !regionCode) {
    showGeoError("Choose a country and state or province before continuing.");
    return;
  }
  hideGeoError();
  const country = $("locCountry").value;
  const zipRaw = ($("locPostal")?.value || "").trim();
  const q = buildStructuredGeocodeQuery();
  const box = $("geoResults");
  if (box) box.innerHTML = `<div class="muted">Resolving location…</div>`;

  try {
    let { ok, results } = await fetchGeocodeResults(q);
    if (!ok) throw new Error("geocode http error");

    let usedZipFallback = false;
    if (!results.length && zipRaw) {
      if (country === "us") {
        const z5 = usZipFive(zipRaw);
        if (z5) {
          const second = await fetchGeocodeResults(`${z5} USA`);
          if (second.ok && second.results.length) {
            results = second.results;
            usedZipFallback = true;
          }
        }
      } else if (country === "ca") {
        const pc = normalizeCanadianPostal(zipRaw);
        const tries = pc.includes(" ") ? [pc, pc.replace(/ /g, "")] : [pc, `${pc.slice(0, 3)} ${pc.slice(3)}`];
        for (const t of tries) {
          if (!t || t.replace(/\s/g, "").length < 6) continue;
          const second = await fetchGeocodeResults(`${t} Canada`);
          if (second.ok && second.results.length) {
            results = second.results;
            usedZipFallback = true;
            break;
          }
        }
      }
    }

    if (!results.length) {
      showGeoError(
        "No location found. If you used a ZIP/postal code, make sure it matches the selected state or province, or try a different code. You can also use Advanced search below.",
      );
      if (box) box.innerHTML = "";
      return;
    }

    const hintHtml = usedZipFallback
      ? `<div class="geo-hint">${esc(
          "Resolved using your ZIP/postal code and country only (the code doesn’t match the state or province you picked). Alerts and weather use this postal location — update State/Province if you want them to line up.",
        )}</div>`
      : "";

    if (results.length === 1) {
      finalizeGeocodeChoice(results[0], { structured: true });
      if (box) box.innerHTML = hintHtml + renderSelectedLocationPill(state.selected);
      return;
    }
    if (box) {
      box.innerHTML = hintHtml + results.map((r, idx) => `
        <div class="pill">
          <div style="flex:1">
            <strong>${esc(r.display_name)}</strong>
            <div class="meta">lat ${Number(r.lat).toFixed(5)}, lon ${Number(r.lon).toFixed(5)}</div>
          </div>
          <button type="button" class="btn btn--primary" data-idx="${idx}">Use</button>
        </div>
      `).join("");
      box.querySelectorAll("button[data-idx]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const r = results[Number(btn.getAttribute("data-idx"))];
          finalizeGeocodeChoice(r, { structured: true });
          box.innerHTML = hintHtml + renderSelectedLocationPill(state.selected);
        });
      });
    }
  } catch {
    showGeoError("Geocoding failed. Check your connection or try again.");
    if (box) box.innerHTML = "";
  }
}

/** Append Step 1 region so short street queries (e.g. "34 mindy dr") resolve. */
function geocodeContextSuffix() {
  const country = $("locCountry")?.value;
  const regionCode = $("locRegion")?.value;
  if (!country || !regionCode) return "";
  const list = country === "ca" ? CAN_PROVINCES : US_STATES;
  const regionName = list.find(([c]) => c === regionCode)?.[1] || "";
  if (!regionName) return "";
  if (country === "us") return `, ${regionName}, USA`;
  return `, ${regionName}, Canada`;
}

/** Advanced: free-text search (alert country still follows Country dropdown). */
async function geocode() {
  const raw = $("q").value.trim();
  if (!raw) return;
  const box = $("geoResults");
  if (box) box.innerHTML = `<div class="muted">Searching…</div>`;
  hideGeoError();

  const country = $("locCountry")?.value || "";
  const zipRaw = ($("locPostal")?.value || "").trim();
  const z5 = country === "us" ? usZipFive(zipRaw) : "";

  const suffix = geocodeContextSuffix();
  const alreadyHasCountry = /\b(USA|United States|U\.S\.A\.|Canada)\b/i.test(raw);

  const tryQueries = [];
  const addQ = (s) => {
    if (s && !tryQueries.includes(s)) tryQueries.push(s);
  };
  addQ(raw);
  if (country === "us" && z5) {
    addQ(`${raw}, ${z5}, USA`);
  }
  if (suffix && !alreadyHasCountry) {
    addQ(`${raw}${suffix}`);
  }
  if (!suffix && country === "us" && !alreadyHasCountry) {
    addQ(`${raw}, USA`);
  }
  if (!suffix && country === "ca" && !alreadyHasCountry) {
    addQ(`${raw}, Canada`);
  }

  try {
    let data = {};
    let results = [];
    for (const q of tryQueries) {
      const res = await fetch(`/api/geocode?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      data = await safeJson(res);
      results = data.results || [];
      if (results.length) break;
    }
    if (!results.length) {
      const note = data.note ? `<div class="muted">${esc(data.note)}</div>` : "";
      if (box) {
        box.innerHTML = `<div class="empty">No results.</div>${note}`;
      }
      const regionCode = $("locRegion")?.value;
      const stateNotChosen = country && !regionCode;
      showGeoError(
        stateNotChosen
          ? "Choose a State or Province in the dropdown above (not “— choose —”). Short addresses like this need state + optional ZIP, or type a full address with city. On Render, also set MAPBOX_ACCESS_TOKEN in the hosting dashboard — a local .env file is not used in production."
          : "No results for that search. Add city or ZIP, spell out the street name, or pick Country + State above — we retry with your state automatically for short addresses. On Render, set MAPBOX_ACCESS_TOKEN under Environment (not only a .env file on your laptop).",
      );
      return;
    }
    if (results.length === 1) {
      finalizeGeocodeChoice(results[0], { structured: false });
      if (box) box.innerHTML = renderSelectedLocationPill(state.selected);
      return;
    }
    if (box) {
      box.innerHTML = results.map((r, idx) => `
        <div class="pill">
          <div style="flex:1">
            <strong>${esc(r.display_name)}</strong>
            <div class="meta">lat ${Number(r.lat).toFixed(5)}, lon ${Number(r.lon).toFixed(5)}</div>
          </div>
          <button type="button" class="btn btn--primary" data-idx="${idx}">Use</button>
        </div>
      `).join("");
      box.querySelectorAll("button[data-idx]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const r = results[Number(btn.getAttribute("data-idx"))];
          finalizeGeocodeChoice(r, { structured: false });
          box.innerHTML = renderSelectedLocationPill(state.selected);
        });
      });
    }
  } catch {
    showGeoError("Geocode failed. Try another query.");
    if (box) box.innerHTML = "";
  }
}

// =========================================================================
// STEP 2 — Alerts
// =========================================================================
const SEVERITY_RANK = { extreme: 4, severe: 3, moderate: 2, minor: 1 };

async function fetchAlerts(opts = {}) {
  const mode = opts.mode || "advanced";
  let country;
  let scope;
  let lat = null;
  let lon = null;
  let region = null;

  if (mode === "default") {
    country = state.locationCountry;
    scope = "point";
    if (!state.selected || !country) return;
    lat = state.selected.lat;
    lon = state.selected.lon;
  } else {
    syncAlertContext();
    scope = $("alertScope").value;
    country = $("alertCountry").value;
    if (scope === "point") {
      if (!state.selected) return;
      lat = state.selected.lat;
      lon = state.selected.lon;
    } else if (scope === "region") {
      if (country === "auto") return;
      region = $("alertRegion").value;
      if (!region) return;
    }
  }

  const box = $("alerts");
  box.innerHTML = `<div class="skeleton" style="height: 32px"></div><div class="skeleton"></div><div class="skeleton" style="width: 70%"></div>`;

  let url = `/api/alerts?country=${encodeURIComponent(country)}&scope=${encodeURIComponent(scope)}`;
  if (scope === "point" && lat != null && lon != null) {
    url += `&lat=${lat}&lon=${lon}`;
  } else if (scope === "region" && region) {
    url += `&region=${encodeURIComponent(region)}`;
  }

  try {
    const res = await fetch(url);
    const data = await safeJson(res);
    if (!res.ok) {
      const detail = data.detail != null ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : "";
      box.innerHTML = `<div class="empty">Alerts failed: ${esc(data.error || detail || data.raw || res.status)}</div>`;
      return;
    }
    const alerts = data.alerts || [];
    state.alerts = data;
    state.alertScope = data.scope || scope;
    if (!alerts.length) {
      state.alertsText = `No active alerts for scope=${data.scope || scope} (country=${data.country || country}).`;
      box.innerHTML = `<div class="empty">No active alerts found for this scope.</div>`;
      return;
    }

    let scopeNote = "";
    if (data.country === "US+CA" && data.scope === "national") {
      scopeNote = `US + Canada nationwide: showing ${alerts.length} alerts (merged sample).`;
    } else if (data.scope === "national") {
      scopeNote = `Nationwide: showing ${alerts.length} of ${data.count ?? "?"} active (capped for UI).`;
    } else if (data.scope === "region") {
      const r = data.state || data.province || "";
      scopeNote = `Region ${r}: showing ${alerts.length} of ${data.count ?? "?"} active.`;
    } else {
      const det = data.detected_country ? ` (detected ${data.detected_country})` : "";
      scopeNote = data.note || `Point alerts${det}.`;
    }
    state.alertsText = `${scopeNote}\n` + alerts.map((a) => {
      const prov = a.provider ? `${a.provider}: ` : "";
      return `${prov}${a.headline || a.event || "Alert"} (${a.severity || a.urgency || "?"})`;
    }).join("\n");

    const note = `<div class="muted" style="margin-bottom:8px">${esc(scopeNote)}</div>`;
    box.innerHTML = note + alerts.map((a) => {
      const title = a.headline || a.event || "Alert";
      const sev = a.severity || a.urgency || "?";
      const exp = a.expires != null && String(a.expires).length ? a.expires : "—";
      const meta = `${a.provider || "alert"} • ${sev} • expires ${exp}`;
      const ad = a.areaDesc ? String(a.areaDesc) : "";
      const area = ad ? ` • ${esc(ad).slice(0, 120)}${ad.length > 120 ? "…" : ""}` : "";
      const link = a.web ? `<a href="${esc(a.web)}" target="_blank" rel="noreferrer">Source</a>` : "";
      return `
        <div class="pill">
          <div class="pill__lead">!</div>
          <div style="flex:1">
            <strong>${esc(title)}</strong>
            <div class="meta">${esc(meta)}${area} ${link ? " • " : ""}${link}</div>
          </div>
        </div>
      `;
    }).join("");
  } catch {
    box.innerHTML = `<div class="empty">Alerts fetch failed (API/network). Try again.</div>`;
  }
}

function alertsSummaryForRisk() {
  if (!state.alerts || !Array.isArray(state.alerts.alerts)) {
    return { count: 0, max_severity: null };
  }
  const list = state.alerts.alerts;
  let max = 0; let maxName = null;
  for (const a of list) {
    const s = String(a.severity || a.urgency || "").toLowerCase();
    if (s in SEVERITY_RANK && SEVERITY_RANK[s] > max) { max = SEVERITY_RANK[s]; maxName = s; }
  }
  return { count: list.length, max_severity: maxName };
}

// =========================================================================
// STEP 3 — Weather
// =========================================================================
/** Align plan/Risk text with the latest weather payload and selected °F/°C (avoids stale strings). */
function buildWeatherSummaryForPlan() {
  if (!state.weather) return state.weatherText || null;
  const data = state.weather;
  const cur = data.current || {};
  const unitParam = selectedTempUnit();
  const tLetter = (data.temp_unit || unitParam || "f").toLowerCase().slice(0, 1) === "c" ? "c" : "f";
  const suf = tempSuffix(tLetter);
  const windSuf = windSpeedSuffixFromApi(data, tLetter);
  const precipLine = formatPrecipitationSummary(cur);
  const windLine = formatWindSpeed(cur.wind_speed_10m, windSuf);
  return [
    `time: ${cur.time || "?"}`,
    `temp_2m: ${cur.temperature_2m ?? "?"} ${suf}`,
    `feels: ${cur.apparent_temperature ?? "?"} ${suf}`,
    `wind: ${windLine}`,
    `precip: ${precipLine}`,
  ].join("\n");
}

async function fetchWeather() {
  const pt = effectiveWeatherPoint();
  if (!pt) return;
  const box = $("weather");
  box.innerHTML = `<div class="skeleton" style="height: 28px"></div><div class="skeleton" style="width: 80%"></div>`;
  const unitParam = selectedTempUnit();
  try {
    const res = await fetch(`/api/weather?lat=${pt.lat}&lon=${pt.lon}&temp_unit=${encodeURIComponent(unitParam)}`);
    const data = await safeJson(res);
    if (!res.ok) {
      box.innerHTML = `<div class="empty">Weather failed: ${esc(data.error || data.raw || res.status)}</div>`;
      return;
    }
    state.weather = data;
    const cur = data.current || {};
    const tLetter = data.temp_unit || unitParam;
    const suf = tempSuffix(tLetter);
    const windSuf = windSpeedSuffixFromApi(data, tLetter);
    const precipLine = formatPrecipitationSummary(cur);
    const windLine = formatWindSpeed(cur.wind_speed_10m, windSuf);
    state.weatherText = buildWeatherSummaryForPlan();
    const t = cur.temperature_2m, feels = cur.apparent_temperature;
    const srcLine =
      data.source && data.source !== "live"
        ? `<div class="meta" style="font-size:11px">Source: ${esc(data.source)}</div>`
        : "";
    box.innerHTML = `
      <div class="pill">
        <div class="pill__lead">☀</div>
        <div style="flex:1">
          <strong>Current weather</strong>
          <div class="meta">${esc(cur.time || "")} • ${esc(data.timezone || "")} (${esc(data.timezone_abbreviation || "")})</div>
          <div class="meta">Temp: ${t ?? "?"}${suf} · Feels: ${feels ?? "?"}${suf} · Wind: ${esc(windLine)}</div>
          <div class="meta">Precip: ${esc(precipLine)}</div>
          ${srcLine}
        </div>
      </div>
    `;
  } catch {
    box.innerHTML = `<div class="empty">Weather fetch failed (API/network). Try again.</div>`;
  }
}

function weatherForRisk() {
  if (!state.weather) return null;
  const cur = state.weather.current || {};
  const letter = state.weather.temp_unit || "f";
  const t = Number(cur.temperature_2m);
  const wind = Number(cur.wind_speed_10m);
  const precip = Number(cur.precipitation);
  // Convert wind to mph if API returned km/h
  let windMph = wind;
  if (state.weather.wind_speed_unit === "km/h") windMph = wind * 0.621371192237334;
  const out = {
    wind_speed: Number.isFinite(windMph) ? Number(windMph.toFixed(2)) : null,
    precip_mm: Number.isFinite(precip) ? precip : null,
  };
  if (Number.isFinite(t)) {
    if (letter === "c") out.temp_c = t; else out.temp_f = t;
  }
  return out;
}

// =========================================================================
// STEP 4 — Resources
// =========================================================================
const RESOURCE_LABEL = {
  shelter: "Shelter",
  hospital: "Hospital",
  clinic: "Clinic",
  food_bank: "Food bank",
  community_centre: "Community center",
};

function distanceMiLabel(item) {
  if (item.distance_mi != null && Number.isFinite(Number(item.distance_mi))) {
    const v = Number(item.distance_mi);
    return `${v >= 10 ? v.toFixed(1) : v.toFixed(2)} mi`;
  }
  if (item.distance_km != null && Number.isFinite(Number(item.distance_km))) {
    const mi = Number(item.distance_km) / 1.609344;
    return `${mi >= 10 ? mi.toFixed(1) : mi.toFixed(2)} mi`;
  }
  return "distance unknown";
}

async function fetchResources() {
  if (!state.selected) return;
  const types = selectedResourceTypes();
  if (!types.length) return;

  let radiusMi = Number($("radiusMi").value || 10);
  if (!Number.isFinite(radiusMi)) radiusMi = 10;
  radiusMi = Math.max(1, Math.min(50, radiusMi));
  $("radiusMi").value = String(Math.round(radiusMi));

  const box = $("resources");
  box.innerHTML = `<div class="skeleton" style="height: 28px"></div><div class="skeleton"></div><div class="skeleton" style="width: 80%"></div>`;

  const typesParam = types.map(encodeURIComponent).join(",");
  try {
    const res = await fetch(
      `/api/resources?lat=${state.selected.lat}&lon=${state.selected.lon}&radius_mi=${radiusMi}&types=${typesParam}`,
    );
    const data = await safeJson(res);
    if (!res.ok) {
      box.innerHTML = `<div class="empty">Resources failed: ${esc(data.detail || data.error || data.raw || res.status)}</div>`;
      return;
    }
    state.resources = { ...data };
    const items = data.items || [];
    const radiusLabel = data.radius_mi != null ? `${Number(data.radius_mi).toFixed(1)} mi` : `${radiusMi} mi`;
    if (!items.length) {
      const note = data.note ? `<div class="muted">${esc(data.note)}</div>` : "";
      const prov = data.provider
        ? `<div class="muted">Provider: ${esc(data.provider)}</div>`
        : "";
      box.innerHTML = `<div class="empty">No resources found within ${esc(radiusLabel)} for the types you selected. Try a larger radius or different types.</div>${note}${prov}`;
      state.resourcesText = `0 resources within ${radiusLabel} (${types.join(", ")}).`;
      return;
    }

    // Build summary text + group by category
    const grouped = {};
    for (const it of items) {
      const k = it.category || "other";
      (grouped[k] ||= []).push(it);
    }
    const counts = Object.entries(grouped).map(([k, v]) => `${k}=${v.length}`).join(", ");
    state.resourcesText = `${items.length} resources within ${radiusLabel} (${counts}).`;

    box.innerHTML = items.map((x) => {
      const addr = x.address || {};
      const addrLine = [addr.housenumber, addr.street, addr.city, addr.state, addr.postcode]
        .filter(Boolean).join(" ");
      const rawAddr = addr.raw ? String(addr.raw) : "";
      const addrDisplay = addrLine || rawAddr;
      const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${x.lat},${x.lon}`)}`;
      const website = x.website ? `<a href="${esc(x.website)}" target="_blank" rel="noreferrer">Website</a>` : "";
      const phone = x.phone ? `<span class="meta">☎ ${esc(x.phone)}</span>` : "";
      const cat = x.category || "other";
      const catLabel = RESOURCE_LABEL[cat] || cat;
      const dist = distanceMiLabel(x);
      return `
        <div class="pill">
          <div class="pill__lead"><span class="dot dot--${esc(cat)}" style="width:10px;height:10px"></span></div>
          <div style="flex:1">
            <strong>${esc(x.name)}</strong>
            <div class="meta"><span class="chip" style="margin: 0 6px 0 0; padding: 2px 8px;">${esc(catLabel)}</span>${esc(dist)} away</div>
            <div class="meta">${esc(addrDisplay)}</div>
            <div class="meta">
              <a href="${esc(maps)}" target="_blank" rel="noreferrer">Directions</a>
              ${website ? " • " + website : ""}
              ${phone ? " • " + phone : ""}
            </div>
          </div>
        </div>
      `;
    }).join("");
  } catch {
    box.innerHTML = `<div class="empty">Resource search failed (API/network). Try again.</div>`;
  }
}

function resourcesForRisk() {
  if (!state.resources) return null;
  const rKm = state.resources.radius_km;
  return {
    count: Number(state.resources.count ?? (state.resources.items || []).length) || 0,
    radius_km: Number(rKm != null ? rKm : 16.09344),
  };
}

// =========================================================================
// STEP 5 — ML Risk
// =========================================================================
const RISK_COLORS = {
  Low: "var(--ok)",
  Medium: "var(--warn)",
  High: "var(--danger)",
};
const FEATURE_LABELS = {
  alert_count: "Alerts (count)",
  alert_severity_max: "Max severity",
  wind_speed: "Wind speed (mph)",
  precip_mm: "Precip (mm)",
  temp_extremity: "Temp extremity",
  resource_count: "Nearby resources",
  resource_density: "Resource density",
  is_coastal_or_remote: "Coastal / remote",
};

async function loadRiskModelInfo() {
  const el = $("riskModelInfo");
  if (!el) return;
  try {
    const res = await fetch("/api/ml/status");
    const data = await safeJson(res);
    if (data && data.model) {
      el.innerHTML = `Model: <strong style="color:var(--text)">${esc(data.model)}</strong>${data.sklearn_available ? "" : " · sklearn fallback"}`;
    }
  } catch { /* ignore */ }
}

async function predictRisk() {
  if (!state.selected) return;
  const box = $("risk");
  box.innerHTML = `<div class="skeleton" style="height: 96px"></div><div class="skeleton"></div><div class="skeleton" style="width:60%"></div>`;

  const payload = {
    lat: state.selected.lat,
    lon: state.selected.lon,
    alerts: alertsSummaryForRisk(),
    weather: weatherForRisk(),
    resources: resourcesForRisk(),
  };

  try {
    const res = await fetch("/api/risk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await safeJson(res);
    if (!res.ok) {
      box.innerHTML = `<div class="empty">Risk prediction failed: ${esc(data.detail || data.error || data.raw || res.status)}</div>`;
      return;
    }
    state.risk = data;
    state.riskText = riskSummaryString(data);
    box.innerHTML = renderRisk(data);
  } catch {
    box.innerHTML = `<div class="empty">Risk request failed (network).</div>`;
  }
}

function riskSummaryString(d) {
  const conf = d.confidence != null ? Math.round(d.confidence * 100) : "?";
  const reasons = (d.reasons || []).slice(0, 4).map((r) => `- ${r}`).join("\n");
  return `Risk: ${d.risk_level} (score ${d.risk_score}/100, confidence ${conf}%)\nModel: ${d.model || "?"}\nReasons:\n${reasons}`;
}

function renderRisk(d) {
  const level = d.risk_level || "Low";
  const score = Math.max(0, Math.min(100, Number(d.risk_score) || 0));
  const conf = d.confidence != null ? Math.round(d.confidence * 100) : null;
  const colorVar = RISK_COLORS[level] || "var(--accent)";
  const reasons = (d.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("");
  const features = d.features || {};
  const featureCells = Object.entries(features).map(([k, v]) => {
    const display = typeof v === "number" ? (Math.abs(v) >= 10 ? v.toFixed(0) : v.toFixed(2)) : esc(v);
    return `<div class="feature"><div class="feature__name">${esc(FEATURE_LABELS[k] || k)}</div><div class="feature__val">${display}</div></div>`;
  }).join("");

  const probs = d.class_probabilities;
  const probsHtml = probs ? `<div class="meta" style="margin-top:8px">Class probabilities — ${
    Object.entries(probs).map(([k, v]) => `<strong>${esc(k)}</strong> ${(v*100).toFixed(0)}%`).join(" · ")
  }</div>` : "";

  return `
    <div class="pill" style="align-items:center">
      <div class="risk-gauge">
        <div class="risk-ring" style="--val:${score};--col:${colorVar}">
          <div style="text-align:center;position:relative">
            <div class="risk-ring__val" style="color:${colorVar}">${score}</div>
            <div class="risk-ring__sub">/ 100</div>
          </div>
        </div>
        <div class="risk-meta">
          <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
            <span class="risk-pill risk-pill--${level.toLowerCase()}">${esc(level)} risk</span>
            ${conf != null ? `<span class="muted">Confidence ${conf}%</span>` : ""}
            <span class="muted">· ${esc(d.model || "model")}</span>
          </div>
          <div class="risk-bar"><div class="risk-bar__fill" style="width:${score}%"></div></div>
          ${probsHtml}
          <ul class="reasons">${reasons}</ul>
        </div>
      </div>
    </div>
    ${featureCells ? `<div class="feature-table">${featureCells}</div>` : ""}
  `;
}

// =========================================================================
// STEP 6 — IBM watsonx Action Plan (structured)
// =========================================================================
function planDemoBannerHtml(data) {
  const ready = data.watsonx_ready === true;
  const metaKnown =
    Object.prototype.hasOwnProperty.call(data, "watsonx_ready") ||
    Object.prototype.hasOwnProperty.call(data, "plan_upstream_source");
  const upstream = data.plan_upstream_source || "";
  const ibmCode = data.ibm_error_code ? String(data.ibm_error_code) : "";
  const detail = data.plan_upstream_detail ? String(data.plan_upstream_detail) : "";
  const httpSt = data.plan_upstream_http_status;

  let headline =
    "You're viewing a built-in demo plan built from your scenario and previous steps — still useful if watsonx isn't available.";
  if (!metaKnown) {
    headline =
      "You're viewing a demo plan — live IBM watsonx wasn't used for this response. Expand “Why?” for setup tips.";
  } else if (!ready) {
    headline =
      "IBM watsonx isn't configured here (API key or project ID missing), so you're seeing a structured demo plan.";
  } else if (upstream === "error") {
    const isClient = ibmCode === "client_error";
    const looksNet =
      isClient ||
      /\b(timeout|timed out|connection|connect|network|resolve|refused|TLS|SSL|EOF)\b/i.test(detail);
    if (looksNet) {
      headline =
        "We couldn't reach IBM watsonx from this server (network or credentials). Showing a demo plan instead.";
    } else if (httpSt != null) {
      headline = `IBM watsonx returned HTTP ${httpSt}. Showing a demo plan with your context instead.`;
    } else {
      headline = "IBM watsonx reported an error. Showing a demo plan with your context instead.";
    }
  }

  const lines = [];
  lines.push(
    "Evac-AI always returns a structured plan: live Granite output when watsonx succeeds, otherwise these demo templates.",
  );
  lines.push(
    "Configure <code>IBM_CLOUD_API_KEY</code> and <code>WATSONX_PROJECT_ID</code> (linked to a watsonx runtime). See <strong>README.md</strong> in this repo.",
  );
  if (ibmCode) {
    lines.push(`Last IBM code: <code>${esc(ibmCode)}</code>`);
  }
  if (detail && upstream === "error") {
    const clipped = detail.length > 320 ? `${detail.slice(0, 319)}…` : detail;
    lines.push(`Detail: ${esc(clipped)}`);
  }

  const body = lines.map((h) => `<p style="margin:0 0 8px">${h}</p>`).join("");
  return `
    <div class="plan-demo-banner" role="status">
      <div><strong>Demo plan</strong> — ${esc(headline)}</div>
      <details class="plan-demo-banner__why">
        <summary>Why am I seeing this?</summary>
        <div class="plan-demo-banner__why-body">${body}</div>
      </details>
    </div>
  `;
}

const PLAN_SECTION_ORDER = [
  "risk_summary",
  "what_to_do_now",
  "emergency_kit",
  "evacuation_guidance",
  "nearby_support",
  "family_message",
  "official_alert_reminder",
];
const DEFAULT_PLAN_TITLES = {
  risk_summary: "Risk Summary",
  what_to_do_now: "What To Do Now",
  emergency_kit: "Emergency Kit",
  evacuation_guidance: "Evacuation Guidance",
  nearby_support: "Nearby Support",
  family_message: "Family Message",
  official_alert_reminder: "Official Alert Reminder",
};

async function fetchPlan() {
  if (!state.selected) return;
  const box = $("plan");
  box.innerHTML = `<div class="muted">Generating plan with IBM watsonx…</div><div class="skeleton" style="height:60px"></div><div class="skeleton" style="width:80%"></div><div class="skeleton" style="width:65%"></div>`;

  const scenario = $("scenario").value;
  const archive_to_cos = $("archiveCos").checked;

  try {
    const res = await fetch("/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: state.selected.lat,
        lon: state.selected.lon,
        location_display: state.selected.display_name,
        scenario,
        alerts_summary: state.alertsText || null,
        weather_summary: buildWeatherSummaryForPlan() || state.weatherText || null,
        resources_summary: state.resourcesText || null,
        risk_summary: state.riskText || null,
        archive_to_cos,
      }),
    });
    const data = await safeJson(res);
    if (!res.ok) {
      box.innerHTML = `<div class="empty">Plan failed: ${esc(data.detail || data.error || data.raw || res.status)}</div>`;
      return;
    }
    const isDemo = data.demo_fallback === true || data.source === "demo";
    const demoBanner = isDemo ? planDemoBannerHtml(data) : "";
    box.innerHTML = demoBanner + renderPlan(data, { isDemo });
  } catch {
    box.innerHTML = `<div class="empty">Plan request failed.</div>`;
  }
}

function renderPlan(data, opts = {}) {
  const isDemo = opts.isDemo === true;
  const plan = data.plan || {};
  const titles = data.section_titles || DEFAULT_PLAN_TITLES;
  const cos = data.ibm_cos;
  const cosLine = cos
    ? `<div class="meta">COS: ${esc(cos.source || "")}${cos.key ? " • " + esc(cos.key) : ""}</div>`
    : "";

  // If we have no parsed plan, fall back to raw text dump.
  const hasAny = PLAN_SECTION_ORDER.some((k) => {
    const v = plan[k];
    return v && (Array.isArray(v) ? v.length : String(v).trim());
  });
  if (!hasAny) {
    const raw = data.raw_text ? `<pre style="white-space:pre-wrap;font-size:12.5px;margin:8px 0 0;color:var(--text)">${esc(data.raw_text).slice(0, 6000)}</pre>` : "";
    return `
      <div class="pill" style="flex-direction:column;align-items:flex-start">
        <div><strong>${isDemo ? "Demo plan" : `watsonx (${esc(data.provider || "ibm")} / ${esc(data.model_id || "?")})`}</strong></div>
        ${cosLine}
        ${raw || `<div class="muted">No structured plan returned.</div>`}
      </div>
    `;
  }

  const sections = PLAN_SECTION_ORDER.map((key) => {
    const value = plan[key];
    if (!value || (Array.isArray(value) && !value.length)) return "";
    const title = titles[key] || DEFAULT_PLAN_TITLES[key] || key;
    const isList = Array.isArray(value);
    const fullClass = (key === "risk_summary" || key === "official_alert_reminder") ? " plan__section--full" : "";
    const variantClass = key === "family_message" ? " plan__section--family" : key === "official_alert_reminder" ? " plan__section--reminder" : "";
    const body = isList
      ? `<ul>${value.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>`
      : `<p>${esc(value)}</p>`;
    return `<div class="plan__section${fullClass}${variantClass}"><h4>${esc(title)}</h4>${body}</div>`;
  }).join("");

  const sources = (plan.sources || []).map((s) => `<a href="${esc(s)}" target="_blank" rel="noreferrer">${esc(s)}</a>`).join("");
  const sourcesBlock = sources ? `<div class="plan__sources"><span>Sources:</span> ${sources}</div>` : "";

  const modelChip = isDemo
    ? `<span class="chip" style="border-color: rgba(251,191,36,0.5); color: var(--warn)">Demo (offline templates)</span>`
    : `<span class="chip chip--accent">watsonx ${esc(data.model_id || "")}</span>`;
  return `
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px">
      ${modelChip}
      ${cos ? `<span class="chip">archived to IBM COS</span>` : ""}
    </div>
    <div class="plan">${sections}</div>
    ${sourcesBlock}
  `;
}

// =========================================================================
// Init
// =========================================================================
function init() {
  bindStepNav();

  // Step 1
  populateLocRegions();
  $("locCountry")?.addEventListener("change", () => {
    populateLocRegions();
    onLocInputsChanged();
  });
  $("locRegion")?.addEventListener("change", onLocInputsChanged);
  $("locPostal")?.addEventListener("input", onLocInputsChanged);
  $("locPostal")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      useStructuredLocation();
    }
  });
  $("btnUseLocation")?.addEventListener("click", useStructuredLocation);
  $("btnGeocode")?.addEventListener("click", geocode);
  $("q")?.addEventListener("keydown", (e) => { if (e.key === "Enter") geocode(); });

  // Step 2
  $("alertCountry").addEventListener("change", onAlertCountryChange);
  $("alertScope").addEventListener("change", onAlertScopeChange);
  $("alertRegion").addEventListener("change", updateAlertsButtonState);
  populateAlertRegions();
  onAlertScopeChange();
  $("btnAlertsRefresh")?.addEventListener("click", () => fetchAlerts({ mode: "default" }));
  $("btnAlertsApply")?.addEventListener("click", () => fetchAlerts({ mode: "advanced" }));
  syncAlertContext();

  // Step 3
  $("btnWeather").addEventListener("click", fetchWeather);
  $$('input[name="tempUnit"]').forEach((r) => {
    r.addEventListener("change", () => {
      if (state.step === 3 && state.selected) fetchWeather();
    });
  });

  // Step 4
  $("btnResources").addEventListener("click", fetchResources);
  $$(".js-resource-type").forEach((cb) => {
    cb.addEventListener("change", updateResourcesButtonState);
  });

  // Step 5
  $("btnRisk").addEventListener("click", predictRisk);
  loadRiskModelInfo();

  // Step 6
  $("btnPlan").addEventListener("click", fetchPlan);

  refreshGuards();
  updateWeatherLocationUI();
  loadGeocodeProviderHint();
  loadIbmPlanServerHint();
}

async function loadIbmPlanServerHint() {
  const el = $("ibmPlanServerHint");
  if (!el) return;
  try {
    const res = await fetch("/api/ibm/status");
    const data = await safeJson(res);
    if (!res.ok) return;
    el.style.display = "block";
    if (data.watsonx_ready) {
      el.innerHTML = `<span class="chip chip--accent" style="margin-right:8px">watsonx ready</span><span class="muted">Generate uses IBM Granite when the API call succeeds.</span>`;
    } else {
      el.innerHTML = `<span class="chip" style="margin-right:8px;border-color:rgba(251,191,36,0.45);color:var(--warn)">demo templates</span><span class="muted">No live watsonx credentials on this server — Generate still returns a full structured plan (demo). See README to enable Granite.</span>`;
    }
  } catch {
    /* ignore */
  }
}

async function loadGeocodeProviderHint() {
  const el = $("geocodeProviderHint");
  if (!el) return;
  try {
    const res = await fetch("/api/geocode/config");
    const data = await safeJson(res);
    if (!res.ok) return;
    const renderNote =
      " Deployed sites (e.g. Render) do not read a .env file from your project — add keys in the host’s Environment settings and redeploy.";
    if (!data.mapbox_configured && !data.google_configured) {
      el.hidden = false;
      el.innerHTML = `${esc(
        "Geocoding: no Mapbox/Google key on this server — street search uses public backups and may miss addresses.",
      )}${esc(renderNote)}`;
    } else {
      el.hidden = true;
      el.innerHTML = "";
    }
  } catch {
    /* ignore */
  }
}

document.addEventListener("DOMContentLoaded", init);

const PLATFORMS = ["sensor", "binary_sensor", "switch", "toggle_switch", "button", "number", "select"];
const TABLES = ["coil", "discrete_input", "holding_register", "input_register"];
const DATA_TYPES = ["bool", "int16", "uint16", "int32", "uint32", "float32"];
const DEVICE_CLASS_UNITS = {
  apparent_power: ["VA", "kVA"], battery: ["%"], current: ["A", "mA"],
  data_rate: ["bit/s", "kbit/s", "Mbit/s", "Gbit/s", "B/s", "kB/s", "MB/s", "GB/s"],
  data_size: ["bit", "kbit", "Mbit", "Gbit", "B", "kB", "MB", "GB", "TB"],
  distance: ["mm", "cm", "m", "km", "in", "ft", "yd", "mi"],
  duration: ["ms", "s", "min", "h", "d"], energy: ["Wh", "kWh", "MWh", "MJ", "GJ"],
  energy_distance: ["Wh/km", "kWh/100 km", "mi/kWh"], frequency: ["Hz", "kHz", "MHz", "GHz"],
  gas: ["m\u00B3", "ft\u00B3", "CCF"], humidity: ["%"], illuminance: ["lx"], irradiance: ["W/m\u00B2"],
  mass: ["\u00B5g", "mg", "g", "kg", "oz", "lb", "st"], moisture: ["%"],
  nitrogen_dioxide: ["\u00B5g/m\u00B3", "mg/m\u00B3", "ppm"], nitrogen_monoxide: ["\u00B5g/m\u00B3", "mg/m\u00B3", "ppm"],
  nitrous_oxide: ["\u00B5g/m\u00B3", "mg/m\u00B3", "ppm"], ozone: ["\u00B5g/m\u00B3", "mg/m\u00B3", "ppm"],
  pm1: ["\u00B5g/m\u00B3", "mg/m\u00B3"], pm10: ["\u00B5g/m\u00B3", "mg/m\u00B3"], pm25: ["\u00B5g/m\u00B3", "mg/m\u00B3"],
  power: ["W", "kW", "MW"], power_factor: ["%"], precipitation: ["mm", "cm", "in"],
  precipitation_intensity: ["mm/h", "in/h"], pressure: ["Pa", "hPa", "kPa", "bar", "cbar", "mbar", "inHg", "psi"],
  reactive_energy: ["varh", "kvarh"], reactive_power: ["var", "kvar"], signal_strength: ["dB", "dBm"],
  sound_pressure: ["dB", "dBA"], speed: ["mm/s", "cm/s", "m/s", "km/h", "in/d", "in/h", "ft/s", "mph", "kn"],
  sulphur_dioxide: ["\u00B5g/m\u00B3", "mg/m\u00B3", "ppm"], temperature: ["\u00B0C", "\u00B0F", "K"],
  volatile_organic_compounds: ["\u00B5g/m\u00B3", "mg/m\u00B3"], volatile_organic_compounds_parts: ["ppm", "ppb"],
  voltage: ["V", "mV"], volume: ["mL", "L", "m\u00B3", "ft\u00B3", "gal", "fl. oz."],
  volume_flow_rate: ["m\u00B3/h", "ft\u00B3/min", "L/min", "gal/min"], volume_storage: ["mL", "L", "m\u00B3", "ft\u00B3", "gal"]
};

class UniversalModbusPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._entryId = null;
    this._editingIndex = null;
    this._removeOnCancelIndex = null;
    this._regenerateKeyOnSave = false;
    this._draft = null;
    this._busy = false;
    this._refreshing = false;
    this._sortColumn = null;
    this._sortDirection = "asc";
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._data && !this._busy) this._load();
  }

  set panel(panel) { this._panel = panel; }
  set route(route) { this._route = route; }

  _t(en, de) {
    return this._hass?.language?.toLowerCase().startsWith("de") ? de : en;
  }

  async _load() {
    this._busy = true;
    this._renderLoading();
    try {
      this._data = await this._hass.connection.sendMessagePromise({
        type: "universal_modbus/editor/get",
      });
      const requested = new URLSearchParams(window.location.search).get("config_entry");
      this._entryId = this._data.entries.some((item) => item.entry_id === requested)
        ? requested
        : this._data.entries[0]?.entry_id;
      this._render();
      clearInterval(this._refreshTimer);
      this._refreshTimer = setInterval(() => this._refresh(), 1000);
    } catch (err) {
      this._renderError(err.message || String(err));
    } finally {
      this._busy = false;
    }
  }


  disconnectedCallback() {
    clearInterval(this._refreshTimer);
  }

  async _refresh() {
    if (this._refreshing || this._refreshBlocked()) return;
    this._refreshing = true;
    try {
      const data = await this._hass.connection.sendMessagePromise({ type: "universal_modbus/editor/get" });
      if (this._refreshBlocked()) return;
      this._data = data;
      if (!data.entries.some((item) => item.entry_id === this._entryId)) this._entryId = data.entries[0]?.entry_id;
      this._render();
    } catch (_err) { /* Keep the last successful view. */ }
    finally { this._refreshing = false; }
  }

  _refreshBlocked() {
    return Boolean(
      this.shadowRoot.querySelector(".modal-backdrop")
      || this.shadowRoot.activeElement?.matches("#hub, .write-number, .write-select")
    );
  }
  get _entry() {
    return this._data?.entries.find((item) => item.entry_id === this._entryId);
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;");
  }

  _renderLoading() {
    this.shadowRoot.innerHTML = `<div class="center">${this._t("Loading\u2026", "Laden\u2026")}</div>${this._styles()}`;
  }

  _renderError(message) {
    this.shadowRoot.innerHTML = `<div class="page"><div class="error">${this._escape(message)}</div></div>${this._styles()}`;
  }

  _styles() {
    return `<style>
      :host{display:block;color:var(--primary-text-color);background:var(--primary-background-color);min-height:100vh;font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
      .page{max-width:1100px;margin:0 auto;padding:24px}.center{padding:64px;text-align:center}
      .header{display:flex;gap:16px;align-items:center;justify-content:space-between;margin-bottom:20px}.brand{display:flex;align-items:center;gap:12px}.brand img{width:44px;height:44px;object-fit:contain}.input-unit{position:relative}.input-unit input{padding-right:34px}.input-unit span{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--secondary-text-color);pointer-events:none}.brand-text{display:flex;flex-direction:column;gap:3px}.brand h1{font-size:24px;margin:0}.version{font-size:12px;color:var(--secondary-text-color)}.header-actions,.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.hub-picker{display:flex;align-items:center;gap:8px}.hub-picker label{font-size:13px;color:var(--secondary-text-color)}.hub{min-width:240px}.hub-card{padding:16px;margin-bottom:16px}.hub-card span{color:var(--secondary-text-color)}.hub-main{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:16px;align-items:start}.hub-summary{display:flex;flex-direction:column;gap:8px;min-width:0}.hub-title{font-size:1.2rem;line-height:1.3}.hub-connection{color:var(--secondary-text-color)}.hub-meta{display:grid;grid-template-columns:max-content 1fr;column-gap:10px;row-gap:2px;color:var(--secondary-text-color)}.hub-meta b{font-weight:500;color:var(--primary-text-color)}.hub-health{display:flex;flex-direction:column;align-items:flex-end;gap:9px}.hub-diagnostics{display:flex;align-items:flex-start;justify-content:flex-end;gap:18px}.diagnostic{display:flex;flex-direction:column;align-items:flex-end;gap:2px;white-space:nowrap}.diagnostic-label{font-size:11px}.diagnostic-value{font-size:13px;color:var(--primary-text-color)!important}.status{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 10px;font-size:12px;line-height:1;background:var(--secondary-background-color);white-space:nowrap}.status::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--error-color)}.status.connected::before{background:var(--success-color, #43a047)}.toolbar{margin-bottom:16px}
      .hub-error{display:flex;align-items:flex-start;gap:7px;color:var(--error-color);font-size:13px;line-height:1.4;overflow-wrap:anywhere}.hub-error ha-icon{flex:0 0 auto;width:18px;height:18px}
      select,input,textarea{box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid var(--divider-color);border-radius:6px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}
      .card{background:var(--card-background-color);border-radius:12px;box-shadow:var(--ha-card-box-shadow);overflow:hidden}
      table{width:100%;border-collapse:collapse}th,td{padding:12px 16px;text-align:left;border-bottom:1px solid var(--divider-color)}th{font-weight:500;color:var(--secondary-text-color)}th.sortable{padding:0}button.sort{display:flex;align-items:center;gap:5px;width:100%;padding:12px 16px;border:0;background:transparent;color:inherit;font:inherit;text-align:left;cursor:pointer}button.sort:hover{color:var(--primary-text-color);background:var(--secondary-background-color)}button.sort ha-icon{width:16px;height:16px}td.actions{width:128px;white-space:nowrap}.entity-icon{width:38px;text-align:center}.entity-icon ha-icon{color:var(--secondary-text-color)}.empty{text-align:center;color:var(--secondary-text-color);padding:28px}
      .icon{display:inline-flex;border:0;background:transparent;color:var(--primary-color);cursor:pointer;padding:7px;border-radius:50%;text-decoration:none}.icon:hover{background:var(--secondary-background-color)}.icon.danger{color:var(--error-color)}.entity-link{border:0;padding:0;background:transparent;color:var(--primary-color);font:inherit;text-align:left;cursor:pointer}.entity-link:hover{text-decoration:underline}ha-icon{pointer-events:none}.value-control{display:flex;align-items:center;gap:8px;min-width:120px}.value-control input[type="checkbox"]{width:auto}.value-control input[type="number"],.value-control select{min-width:90px;padding:7px}.value-control button{flex:0 0 auto}.value-unit{color:var(--secondary-text-color);white-space:nowrap}
      .add-row td{height:42px}.add-row td:last-child{text-align:right}.modal-backdrop{position:fixed;inset:0;background:#0008;display:flex;align-items:center;justify-content:center;padding:20px;z-index:10}.dialog{width:min(760px,100%);max-height:90vh;overflow:auto;background:var(--card-background-color);border-radius:12px;box-shadow:0 8px 32px #0008}.dialog h2{margin:0;padding:20px 24px;border-bottom:1px solid var(--divider-color)}form{padding:20px 24px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field.full{grid-column:1/-1}.group{grid-column:1/-1;border:1px solid var(--divider-color);border-radius:8px;padding:16px}.group-title{font-size:15px;font-weight:600;margin:0 0 14px}.group-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.field label{display:block;font-size:13px;color:var(--secondary-text-color);margin-bottom:6px}.field.checkbox label{display:inline-flex;align-items:center;gap:8px;margin-bottom:0}.field.checkbox input{width:auto;margin:0}.readonly input{color:var(--secondary-text-color)}ha-icon-picker{display:block}.buttons{display:flex;justify-content:flex-end;gap:10px;margin-top:24px}.button{width:auto;border:0;border-radius:6px;padding:10px 18px;cursor:pointer;font-weight:500}.button.primary{background:var(--primary-color);color:var(--text-primary-color)}.button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color)}.error{padding:14px;background:var(--error-color);color:white;border-radius:6px;margin-bottom:16px}
      @media(max-width:700px){.page{padding:12px}.header{align-items:stretch;flex-direction:column}.header-actions{align-items:stretch}.hub-picker{align-items:stretch;flex-direction:column}.hub-main{grid-template-columns:1fr}.hub-health{align-items:flex-start}.hub-diagnostics{justify-content:flex-start;gap:14px;max-width:100%;overflow-x:auto}.diagnostic{align-items:flex-start}.grid,.group-grid{grid-template-columns:1fr}th:nth-child(4),td:nth-child(4){display:none}th,td{padding:10px}.dialog{max-height:96vh}}
    </style>`;
  }


  _header(actions = "") {
    return `<div class="header"><div class="brand"><img src="/universal_modbus_brand/icon.png" alt=""><div class="brand-text"><h1>Universal Modbus</h1><span class="version">${this._t("Version", "Version")} ${this._escape(this._data?.version || "")}</span></div></div>${actions}</div>`;
  }
  _sortHeader(column, label) {
    const active = this._sortColumn === column;
    const direction = active ? this._sortDirection : "none";
    const icon = active
      ? `<ha-icon icon="mdi:arrow-${this._sortDirection === "asc" ? "up" : "down"}"></ha-icon>`
      : `<ha-icon icon="mdi:unfold-more-horizontal"></ha-icon>`;
    return `<th class="sortable" aria-sort="${direction === "asc" ? "ascending" : direction === "desc" ? "descending" : "none"}"><button class="sort" data-sort="${column}" type="button">${label}${icon}</button></th>`;
  }

  _sortedEntities(entities) {
    const indexed = entities.map((entity, index) => ({ entity, index }));
    if (!this._sortColumn) return indexed;
    const values = {
      name: (entity) => entity.name,
      platform: (entity) => entity.platform === "toggle_switch" ? "ToggleSwitch" : entity.platform,
      table: (entity) => entity.table,
      register: (entity) => Number(entity.register),
      value: (entity) => this._entry.values?.[entity.key],
    };
    const getValue = values[this._sortColumn];
    const direction = this._sortDirection === "asc" ? 1 : -1;
    return indexed.sort((left, right) => {
      const a = getValue(left.entity);
      const b = getValue(right.entity);
      if (a == null && b == null) return left.index - right.index;
      if (a == null) return direction;
      if (b == null) return -direction;
      const comparison = typeof a === "number" && typeof b === "number"
        ? a - b
        : String(a).localeCompare(String(b), this._hass?.language, { numeric: true, sensitivity: "base" });
      return comparison === 0 ? left.index - right.index : comparison * direction;
    });
  }

  _toggleSort(column) {
    if (this._sortColumn === column) {
      this._sortDirection = this._sortDirection === "asc" ? "desc" : "asc";
    } else {
      this._sortColumn = column;
      this._sortDirection = "asc";
    }
    this._render();
  }

  _formatDateTime(value) {
    if (!value) return "\u2014";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "\u2014";
    return new Intl.DateTimeFormat(this._hass?.locale?.language || this._hass?.language, {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
  }

  _render() {
    const entries = this._data?.entries || [];
    if (!entries.length) {
      this.shadowRoot.innerHTML = `<div class="page">${this._header(`<div class="header-actions"><button class="icon import-hub" title="${this._t("Import hub", "Hub importieren")}"><ha-icon icon="mdi:upload"></ha-icon></button><button class="icon add-hub" title="${this._t("Add hub", "Hub hinzuf\u00FCgen")}"><ha-icon icon="mdi:plus"></ha-icon></button><input type="file" class="hub-file" accept="application/json,.json" hidden></div>`)}<div class="card empty">${this._t("No Universal Modbus hub configured.", "Kein Universal-Modbus-Hub konfiguriert.")}</div></div>${this._styles()}`;
      this.shadowRoot.querySelector(".add-hub").addEventListener("click", () => this._openHubEditor());
      this.shadowRoot.querySelector(".import-hub").addEventListener("click", () => this.shadowRoot.querySelector(".hub-file").click());
      this.shadowRoot.querySelector(".hub-file").addEventListener("change", (event) => this._importHub(event.target.files[0], event.target));
      return;
    }
    const entry = this._entry;
    const entities = entry.profile.entities || [];
    const hubSelector = `<div class="hub-picker"><label for="hub">${this._t("Hub", "Hub")}</label><select class="hub" id="hub">${entries.map((item) => `<option value="${item.entry_id}" ${item.entry_id === this._entryId ? "selected" : ""}>${this._escape(item.title)}</option>`).join("")}</select></div>`;
    const rows = this._sortedEntities(entities).map(({ entity, index }) => `<tr><td class="entity-icon">${entity.icon ? `<ha-icon icon="${this._escape(entity.icon)}"></ha-icon>` : ""}</td><td>${entry.entity_ids?.[entity.key] ? `<button class="entity-link" data-entity-id="${this._escape(entry.entity_ids[entity.key])}">${this._escape(entity.name)}</button>` : this._escape(entity.name)}</td><td>${this._escape(entity.platform === "toggle_switch" ? "ToggleSwitch" : entity.platform)}</td><td>${this._escape(entity.table)}</td><td>${this._escape(entity.register)}</td><td>${this._valueControl(entity)}</td><td class="actions"><button class="icon edit" data-index="${index}" title="${this._t("Edit", "Bearbeiten")}"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="icon duplicate" data-index="${index}" title="${this._t("Duplicate", "Duplizieren")}"><ha-icon icon="mdi:content-copy"></ha-icon></button><button class="icon danger delete" data-index="${index}" title="${this._t("Delete", "L\u00F6schen")}"><ha-icon icon="mdi:delete"></ha-icon></button></td></tr>`).join("");
    const h = entry.hub;
    const connected = entry.connected && entry.last_update_success;
    const metadata = [
      [this._t("Manufacturer", "Hersteller"), entry.profile.manufacturer],
      [this._t("Model", "Modell"), entry.profile.model],
      [this._t("Description", "Beschreibung"), entry.profile.description],
    ].filter((item) => item[1]);
    const hubError = entry.error ? `<div class="hub-error"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span><b>${this._t("Current error", "Aktueller Fehler")}:</b> ${this._escape(entry.error)}</span></div>` : "";
    const hubMetadata = (metadata.length ? `<div class="hub-meta">${metadata.map((item) => `<b>${this._escape(item[0])}</b><span>${this._escape(item[1])}</span>`).join("")}</div>` : "") + hubError;
    const diagnostics = [
      [this._t("Response time", "Antwortzeit"), entry.last_response_time_ms == null ? "\u2014" : `${entry.last_response_time_ms} ms`],
      [this._t("Communication errors", "Kommunikationsfehler"), entry.communication_error_count ?? 0],
      [this._t("Last successful poll", "Letzte erfolgreiche Abfrage"), this._formatDateTime(entry.last_successful_update)],
    ];
    const hubDiagnostics = `<div class="hub-diagnostics">${diagnostics.map(([label, value]) => `<div class="diagnostic"><span class="diagnostic-label">${this._escape(label)}</span><span class="diagnostic-value">${this._escape(value)}</span></div>`).join("")}</div>`;
    const deviceLink = entry.device_id ? `<a class="icon device-hub" href="/config/devices/device/${encodeURIComponent(entry.device_id)}" title="${this._t("Open device", "Ger\u00E4t \u00F6ffnen")}" aria-label="${this._t("Open device", "Ger\u00E4t \u00F6ffnen")}"><ha-icon icon="mdi:open-in-new"></ha-icon></a>` : "";
    const actions = `<div class="header-actions">${hubSelector}${deviceLink}<button class="icon import-hub" title="${this._t("Import hub", "Hub importieren")}"><ha-icon icon="mdi:upload"></ha-icon></button><button class="icon export-hub" title="${this._t("Export hub", "Hub exportieren")}"><ha-icon icon="mdi:download"></ha-icon></button><button class="icon regenerate-keys" title="${this._t("Regenerate entity keys", "Entit\u00E4ts-Keys neu generieren")}"><ha-icon icon="mdi:key-change"></ha-icon></button><button class="icon cleanup-entities" title="${this._t("Remove orphaned entities", "Entit\u00E4ts-Leichen entfernen")}"><ha-icon icon="mdi:broom"></ha-icon></button><button class="icon add-hub" title="${this._t("Add hub", "Hub hinzuf\u00FCgen")}"><ha-icon icon="mdi:plus"></ha-icon></button><button class="icon edit-hub" title="${this._t("Edit hub", "Hub bearbeiten")}"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="icon danger delete-hub" title="${this._t("Delete hub", "Hub l\u00F6schen")}"><ha-icon icon="mdi:delete"></ha-icon></button><input type="file" class="hub-file" accept="application/json,.json" hidden></div>`;
    this.shadowRoot.innerHTML = `<div class="page">${this._header(actions)}<div class="hub-card card"><div class="hub-main"><div class="hub-summary"><strong class="hub-title">${this._escape(entry.title)}</strong>${hubMetadata}<span class="hub-connection">${this._escape(h.host)}:${h.port} \u00B7 Unit ${h.slave} \u00B7 ${h.scan_interval}s</span></div><div class="hub-health"><span class="status ${connected ? "connected" : ""}">${connected ? this._t("Connected", "Verbunden") : this._t("Disconnected", "Nicht verbunden")}</span>${hubDiagnostics}</div></div></div><div class="toolbar"><button class="button secondary refresh">${this._t("Refresh values", "Werte aktualisieren")}</button></div><div class="card"><table><thead><tr><th></th>${this._sortHeader("name", this._t("Name", "Name"))}${this._sortHeader("platform", this._t("Type", "Typ"))}${this._sortHeader("table", this._t("Area", "Bereich"))}${this._sortHeader("register", this._t("Register", "Register"))}${this._sortHeader("value", this._t("Current value", "Aktueller Wert"))}<th></th></tr></thead><tbody>${rows}<tr class="add-row"><td colspan="6"></td><td><button class="icon add" title="${this._t("Add entity", "Entit\u00E4t hinzuf\u00FCgen")}"><ha-icon icon="mdi:plus"></ha-icon></button></td></tr></tbody></table></div></div>${this._styles()}`;
    this.shadowRoot.querySelector("#hub").addEventListener("change", (event) => { this._entryId = event.target.value; this._render(); });
    this.shadowRoot.querySelector(".add-hub").addEventListener("click", () => this._openHubEditor());
    this.shadowRoot.querySelector(".edit-hub").addEventListener("click", () => this._openHubEditor(this._entryId));
    this.shadowRoot.querySelector(".delete-hub").addEventListener("click", () => this._deleteHub());
    this.shadowRoot.querySelector(".export-hub").addEventListener("click", () => this._exportHub());
    this.shadowRoot.querySelector(".regenerate-keys").addEventListener("click", () => this._regenerateKeys());
    this.shadowRoot.querySelector(".cleanup-entities").addEventListener("click", () => this._cleanupEntities());
    this.shadowRoot.querySelector(".import-hub").addEventListener("click", () => this.shadowRoot.querySelector(".hub-file").click());
    this.shadowRoot.querySelector(".hub-file").addEventListener("change", (event) => this._importHub(event.target.files[0], event.target));
    this.shadowRoot.querySelector(".add").addEventListener("click", () => this._openEditor());
    this.shadowRoot.querySelector(".refresh").addEventListener("click", () => this._refresh());
    this.shadowRoot.querySelectorAll(".sort").forEach((button) => button.addEventListener("click", () => this._toggleSort(button.dataset.sort)));
    this.shadowRoot.querySelectorAll(".entity-link").forEach((button) => button.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("hass-more-info", {
        bubbles: true,
        composed: true,
        detail: { entityId: button.dataset.entityId },
      }));
    }));
    this.shadowRoot.querySelectorAll(".edit").forEach((button) => button.addEventListener("click", () => this._openEditor(Number(button.dataset.index))));
    this.shadowRoot.querySelectorAll(".duplicate").forEach((button) => button.addEventListener("click", () => this._duplicate(Number(button.dataset.index))));
    this.shadowRoot.querySelectorAll(".delete").forEach((button) => button.addEventListener("click", () => this._delete(Number(button.dataset.index))));
    this.shadowRoot.querySelectorAll(".value-switch").forEach((control) => control.addEventListener("change", () => this._writeValue(control.dataset.key, control.checked, control)));
    this.shadowRoot.querySelectorAll(".value-button").forEach((control) => control.addEventListener("click", () => this._writeValue(control.dataset.key, undefined, control)));
    this.shadowRoot.querySelectorAll(".write-number").forEach((control) => control.addEventListener("change", () => this._writeValue(control.dataset.key, control.value, control)));
    this.shadowRoot.querySelectorAll(".write-select").forEach((control) => control.addEventListener("change", () => this._writeValue(control.dataset.key, control.value, control)));
  }


  _formatValue(entity, current) {
    if (current === undefined) return "\u2014";
    if (entity.platform === "binary_sensor") return current ? this._t("On", "Ein") : this._t("Off", "Aus");
    if (entity.platform === "sensor" && entity.device_class === "enum" && entity.options && !Array.isArray(entity.options)) {
      const label = entity.options[String(current)];
      if (label !== undefined) return `${current}: ${label}`;
    }
    if (typeof current === "number" && entity.display_precision !== null && entity.display_precision !== undefined && entity.display_precision !== "") {
      return Number(current).toFixed(Number(entity.display_precision));
    }
    return typeof current === "object" ? JSON.stringify(current) : String(current);
  }

  _formatValueWithUnit(entity, current) {
    const value = this._formatValue(entity, current);
    return entity.unit && value !== "\u2014" ? `${value} ${entity.unit}` : value;
  }

  _valueControl(entity) {
    const current = this._entry.values?.[entity.key];
    const key = this._escape(entity.key);
    const disabled = entity.writable === false ? "disabled" : "";
    const unit = entity.unit ? `<span class="value-unit">${this._escape(entity.unit)}</span>` : "";
    if (["switch", "toggle_switch"].includes(entity.platform)) {
      return `<div class="value-control"><input class="value-switch" data-key="${key}" type="checkbox" ${current ? "checked" : ""} ${disabled} title="${this._t("Switch value", "Wert schalten")}"><span>${current ? this._t("On", "Ein") : this._t("Off", "Aus")}</span></div>`;
    }
    if (entity.platform === "button") {
      return `<div class="value-control"><button class="icon value-button" data-key="${key}" ${disabled} title="${this._t("Press", "Ausl\u00F6sen")}"><ha-icon icon="mdi:gesture-tap-button"></ha-icon></button></div>`;
    }
    if (entity.platform === "number") {
      return `<div class="value-control"><input class="write-number" data-key="${key}" type="number" min="${entity.minimum}" max="${entity.maximum}" step="${entity.step}" value="${current ?? ""}" ${disabled}>${unit}</div>`;
    }
    if (entity.platform === "select") {
      const options = Object.entries(entity.options || {}).map(([label, raw]) => `<option value="${this._escape(label)}" ${raw === current ? "selected" : ""}>${this._escape(label)}</option>`).join("");
      return `<div class="value-control"><select class="write-select" data-key="${key}" ${disabled}>${options}</select>${unit}</div>`;
    }
    return this._escape(this._formatValueWithUnit(entity, current));
  }

  async _writeValue(key, value, control) {
    control.disabled = true;
    try {
      await this._hass.connection.sendMessagePromise({ type: "universal_modbus/editor/write", entry_id: this._entryId, key, value });
      await this._refresh();
    } catch (err) {
      alert(err.message || String(err));
      control.disabled = false;
      await this._refresh();
    }
  }
  async _cleanupEntities() {
    if (!confirm(this._t(
      "Remove all Home Assistant entities that belong to this hub but are no longer present in its profile?",
      "Alle Home-Assistant-Entit\u00E4ten entfernen, die zu diesem Hub geh\u00F6ren, aber nicht mehr in seinem Profil vorhanden sind?"
    ))) return;
    try {
      const result = await this._hass.connection.sendMessagePromise({ type: "universal_modbus/hub/cleanup_entities", entry_id: this._entryId });
      alert(this._t(result.removed + " orphaned entities removed.", result.removed + " Entit\u00E4ts-Leichen entfernt."));
      await this._refresh();
    } catch (err) {
      alert(err.message || String(err));
    }
  }

  _openHubEditor(entryId = null) {
    const entry = entryId ? this._data.entries.find((item) => item.entry_id === entryId) : null;
    const hub = entry?.hub || { name: "", host: "", port: 502, slave: 1, scan_interval: 5, timeout: 3 };
    const profile = entry?.profile || { schema_version: 1, name: "", manufacturer: "", model: "", description: "", defaults: { byte_order: "big", word_order: "big" }, entities: [] };
    const dialog = document.createElement("div"); dialog.className = "modal-backdrop";
    const field = (name, label, value, type = "text", extra = "") => `<div class="field"><label>${label}</label><input name="${name}" type="${type}" value="${this._escape(value)}" ${extra}></div>`;
    const secondsField = (name, label, value) => `<div class="field"><label>${label}</label><div class="input-unit"><input name="${name}" type="number" value="${this._escape(value)}" min="1" inputmode="numeric"><span>s</span></div></div>`;
    const order = (name, label, value) => `<div class="field"><label>${label}</label><select name="${name}"><option value="big" ${value === "big" ? "selected" : ""}>Big-Endian</option><option value="little" ${value === "little" ? "selected" : ""}>Little-Endian</option></select></div>`;
    dialog.innerHTML = `<div class="dialog"><h2>${entry ? this._t("Edit hub", "Hub bearbeiten") : this._t("Add hub", "Hub hinzuf\u00FCgen")}</h2><form><div class="grid">${field("name", this._t("Hub name", "Hub-Name"), hub.name || entry?.title || "", "text", "required")}${field("manufacturer", this._t("Manufacturer", "Hersteller"), profile.manufacturer)}${field("model", this._t("Model", "Modell"), profile.model)}${field("description", this._t("Description", "Beschreibung"), profile.description)}<section class="group"><h3 class="group-title">${this._t("Communication", "Kommunikation")}</h3><div class="group-grid">${field("host", "Host", hub.host, "text", "required")}${field("port", "Port", hub.port, "number", 'min="1" max="65535"')}${field("slave", "Unit ID", hub.slave, "number", 'min="0" max="247"')}${secondsField("scan_interval", this._t("Scan interval", "Abfrageintervall"), hub.scan_interval)}${secondsField("timeout", this._t("Timeout", "Zeit\u00FCberschreitung"), hub.timeout)}${order("byte_order", this._t("Byte order", "Byte-Reihenfolge"), profile.defaults?.byte_order)}${order("word_order", this._t("Word order", "Wort-Reihenfolge"), profile.defaults?.word_order)}</div></section></div><div class="buttons"><button type="button" class="button secondary cancel">${this._t("Cancel", "Abbrechen")}</button><button class="button primary">${this._t("Save", "Speichern")}</button></div></form></div>`;
    this.shadowRoot.appendChild(dialog);
    dialog.querySelector(".cancel").addEventListener("click", () => dialog.remove());
    dialog.querySelector("form").addEventListener("submit", async (event) => { event.preventDefault(); const values = Object.fromEntries(new FormData(event.target)); ["port", "slave", "scan_interval", "timeout"].forEach((key) => values[key] = Number(values[key])); const nextProfile = structuredClone(profile); Object.assign(nextProfile, { name: values.name, manufacturer: values.manufacturer, model: values.model, description: values.description }); nextProfile.defaults = { ...(nextProfile.defaults || {}), byte_order: values.byte_order, word_order: values.word_order }; const nextHub = { name: values.name, host: values.host, port: values.port, slave: values.slave, scan_interval: values.scan_interval, timeout: values.timeout }; try { const result = await this._hass.connection.sendMessagePromise({ type: "universal_modbus/hub/save", entry_id: entryId || undefined, hub: nextHub, profile: nextProfile }); this._entryId = result.entry_id; dialog.remove(); await this._refresh(); } catch (err) { alert(err.message || String(err)); } });
  }

  async _deleteHub() {
    if (!confirm(this._t(`Delete hub \u201C${this._entry.title}\u201D?`, `Hub \u201E${this._entry.title}\u201C l\u00F6schen?`))) return;
    await this._hass.connection.sendMessagePromise({ type: "universal_modbus/hub/delete", entry_id: this._entryId }); this._entryId = null; await this._refresh();
  }

  _exportHub() {
    const { host: _host, ...exportedHub } = this._entry.hub;
    const payload = {
      metadata: {
        integration: "Universal Modbus",
        version: this._data?.version || "",
        created_at: new Date().toISOString(),
      },
      hub: exportedHub,
      profile: this._entry.profile,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${this._entry.title || this._entry.profile.name || "universal-modbus"}-hub.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  async _importHub(file, input = null) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (!data || typeof data !== "object" || !data.hub || !data.profile) throw new Error(this._t("Invalid hub export file", "Ung\u00FCltige Hub-Exportdatei"));
      this._openHubImportEditor(data);
    } catch (err) {
      alert(err.message || String(err));
    } finally {
      if (input) input.value = "";
    }
  }

  _openHubImportEditor(data) {
    const hub = { name: data.hub.name || data.profile.name || "", host: data.hub.host || "", port: data.hub.port || 502, slave: data.hub.slave ?? 1, scan_interval: data.hub.scan_interval || 5, timeout: data.hub.timeout || 3 };
    const profile = data.profile;
    const dialog = document.createElement("div"); dialog.className = "modal-backdrop";
    const field = (name, label, value, type = "text", extra = "") => `<div class="field"><label>${label}</label><input name="${name}" type="${type}" value="${this._escape(value)}" ${extra}></div>`;
    dialog.innerHTML = `<div class="dialog"><h2>${this._t("Import hub", "Hub importieren")}</h2><form><div class="grid">${field("host", this._t("IP address", "IP-Adresse"), hub.host, "text", "required")}${field("port", "Port", hub.port, "number", 'min="1" max="65535"')}${field("slave", "Unit ID", hub.slave, "number", 'min="0" max="247"')}</div><div class="buttons"><button type="button" class="button secondary cancel">${this._t("Cancel", "Abbrechen")}</button><button type="submit" class="button primary">${this._t("Import", "Importieren")}</button></div></form></div>`;
    this.shadowRoot.appendChild(dialog);
    dialog.querySelector(".cancel").addEventListener("click", () => dialog.remove());
    dialog.querySelector("form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.target));
      const nextHub = { ...hub, host: values.host, port: Number(values.port), slave: Number(values.slave) };
      try {
        const result = await this._hass.connection.sendMessagePromise({ type: "universal_modbus/hub/save", hub: nextHub, profile });
        this._entryId = result.entry_id;
        dialog.remove();
        await this._refresh();
      } catch (err) { alert(err.message || String(err)); }
    });
  }
  _defaults() {
    const defaults = this._entry.profile.defaults || {};
    return { name: "", key: "", platform: "sensor", table: "holding_register", register: 0, data_type: "int16", count: 1, scale: 1, offset: 0, unit: "", icon: "", device_class: "", state_class: "", display_precision: null, byte_order: defaults.byte_order || "big", word_order: defaults.word_order || "big", writable: false, feedback_table: "", feedback_register: 0, command_on: 1, command_off: 0, pulse_ms: 0, minimum: 0, maximum: 100, step: 1, options: {} };
  }

  _openEditor(index = null, removeOnCancel = false, regenerateKeyOnSave = false) {
    this._editingIndex = index;
    this._removeOnCancelIndex = removeOnCancel ? index : null;
    this._regenerateKeyOnSave = regenerateKeyOnSave;
    this._draft = { ...this._defaults(), ...(index === null ? {} : this._entry.profile.entities[index]) };
    this._renderEditor();
  }

  _field(name, label, type = "text", extra = "") {
    return `<div class="field"><label for="${name}">${label}</label><input id="${name}" name="${name}" type="${type}" value="${this._escape(this._draft[name] ?? "")}" ${extra}></div>`;
  }


  _readonlyField(name, label, value) {
    return `<div class="field readonly"><label for="${name}">${label}</label><input id="${name}" type="text" value="${this._escape(value)}" readonly></div>`;
  }
  _select(name, label, options, none = false) {
    const values = none ? [{ value: "", label: "None" }, ...options.map((value) => ({ value, label: value === "toggle_switch" ? "ToggleSwitch" : value }))] : options.map((value) => ({ value, label: value === "toggle_switch" ? "ToggleSwitch" : value }));
    return `<div class="field"><label for="${name}">${label}</label><select id="${name}" name="${name}">${values.map((item) => `<option value="${this._escape(item.value)}" ${String(this._draft[name] ?? "") === String(item.value) ? "selected" : ""}>${this._escape(item.label)}</option>`).join("")}</select></div>`;
  }


  _precisionSelect() {
    const options = [{ value: "", label: "None" }, ...[0, 1, 2, 3, 4, 5, 6].map((value) => ({ value, label: String(value) }))];
    return `<div class="field"><label for="display_precision">${this._t("Displayed decimal places", "Angezeigte Dezimalstellen")}</label><select id="display_precision" name="display_precision">${options.map((item) => `<option value="${item.value}" ${String(this._draft.display_precision ?? "") === String(item.value) ? "selected" : ""}>${item.label}</option>`).join("")}</select></div>`;
  }

  _iconField() {
    return `<div class="field"><label for="icon_picker">${this._t("Icon", "Icon")}</label><ha-icon-picker id="icon_picker"></ha-icon-picker><input id="icon" name="icon" type="hidden" value="${this._escape(this._draft.icon || "")}"></div>`;
  }

  _checkbox(name, label, checked) {
    return `<div class="field checkbox"><label><input name="${name}" type="checkbox" ${checked ? "checked" : ""}> <span>${label}</span></label></div>`;
  }

  _wireIconPicker(root) {
    const picker = root.querySelector("#icon_picker");
    const input = root.querySelector("#icon");
    if (!picker || !input) return;
    picker.hass = this._hass;
    picker.value = this._draft.icon || "";
    picker.label = this._t("Icon", "Icon");
    picker.addEventListener("value-changed", (event) => {
      input.value = event.detail?.value || "";
      this._draft.icon = input.value;
    });
  }

  _wireKeyPreview(root) {
    if (!this._regenerateKeyOnSave) return;
    const nameInput = root.querySelector("#name");
    const keyInput = root.querySelector('[name="key"]');
    const keyPreview = root.querySelector("#key_preview");
    if (!nameInput || !keyInput || !keyPreview) return;
    const update = () => {
      const key = this._uniqueEntityKey(nameInput.value, this._entry.profile.entities || [], this._editingIndex);
      keyInput.value = key;
      keyPreview.value = key;
      this._draft.key = key;
    };
    nameInput.addEventListener("input", update);
    update();
  }
  _renderEditor(error = "") {
    const d = this._draft;
    const bitArea = ["coil", "discrete_input"].includes(d.table);
    if (bitArea) d.data_type = "bool";
    const coilSensor = d.platform === "sensor" && d.table === "coil";
    if (coilSensor) {
      d.options = {};
      if (d.device_class === "enum") d.device_class = null;
    }
    const dataTypes = bitArea ? ["bool"] : DATA_TYPES;
    d.count = ["int32", "uint32", "float32"].includes(d.data_type) ? 2 : 1;
    const deviceClasses = (this._data.device_classes[d.platform] || []).filter((item) => !coilSensor || item !== "enum");
    const analog = d.data_type !== "bool";
    const feedback = Boolean(d.feedback_table);
    const switchLike = ["switch", "toggle_switch", "button"].includes(d.platform);
    const pulseLike = ["toggle_switch", "button"].includes(d.platform);
    if (d.platform === "toggle_switch" && !d.pulse_ms) d.pulse_ms = 100;
    const hasOptions = d.options && (Array.isArray(d.options) ? d.options.length : Object.keys(d.options).length);
    if (d.platform === "sensor" && hasOptions) { d.device_class = "enum"; d.state_class = null; d.unit = null; }
    const suggestedUnits = DEVICE_CLASS_UNITS[d.device_class] || [];
    const units = suggestedUnits.map((unit) => `<option value="${this._escape(unit)}"></option>`).join("");
    const unitField = analog && ["sensor", "number"].includes(d.platform) && !(d.platform === "sensor" && hasOptions)
      ? `<div class="field"><label for="unit">${this._t("Unit", "Einheit")}</label><input id="unit" name="unit" list="ha-units" value="${this._escape(d.unit || "")}" placeholder="${this._t("Select or enter a unit", "Einheit ausw\u00e4hlen oder eingeben")}"><datalist id="ha-units">${units}</datalist></div>`
      : "";
    const readOnlyPlatform = ["switch", "toggle_switch", "button", "number", "select"].includes(d.platform);
    const readOnly = readOnlyPlatform && d.writable === false;
    const readOnlyField = readOnlyPlatform ? this._checkbox("read_only", "Read Only", readOnly) : "";
    const modbusDetails = `${readOnlyField}${feedback ? `${this._field("feedback_register", this._t("Feedback register", "R\u00FCckmelderegister"), "number", 'min="0"')}${switchLike ? `${this._field("command_on", this._t("On command", "Einschaltwert"), "number")}${this._field("command_off", this._t("Off command", "Ausschaltwert"), "number")}` : ""}` : ""}`;
    const properties = `${this._select("platform", this._t("Entity type", "Entit\u00E4tstyp"), PLATFORMS)}${deviceClasses.length ? this._select("device_class", this._t("Device class", "Ger\u00E4teklasse"), deviceClasses, true) : ""}${d.platform === "sensor" && !hasOptions ? this._select("state_class", this._t("State class", "Zustandsklasse"), this._data.state_classes, true) : ""}${unitField}${this._iconField()}${analog && ["sensor", "number"].includes(d.platform) ? this._precisionSelect() : ""}${analog ? `${this._field("offset", "Offset", "number", 'step="any"')}${this._field("scale", this._t("Scale", "Skalierung"), "number", 'step="any"')}` : ""}${pulseLike ? this._field("pulse_ms", this._t("Pulse duration (ms)", "Impulsdauer (ms)"), "number", 'min="0"') : ""}${d.platform === "number" ? `${this._field("minimum", "Minimum", "number", 'step="any"')}${this._field("maximum", "Maximum", "number", 'step="any"')}${this._field("step", this._t("Step", "Schrittweite"), "number", 'step="any" min="0.000001"')}` : ""}${["sensor", "binary_sensor", "select"].includes(d.platform) && !coilSensor ? `<div class="field full"><label for="options_json">${this._t("Options as JSON", "Optionen als JSON")}</label><textarea id="options_json" name="options_json" rows="5">${this._escape(JSON.stringify(d.options || {}, null, 2))}</textarea></div>` : ""}`;
    const uniqueId = this._entryId || this._t("Generated when saved", "Wird beim Speichern erzeugt");
    const identity = `${this._field("name", this._t("Name", "Name"), "text", "required")}${this._readonlyField("key_preview", "key", d.key || this._t("Generated when saved", "Wird beim Speichern erzeugt"))}${this._readonlyField("unique_id", "unique_id", uniqueId)}<input name="key" type="hidden" value="${this._escape(d.key || "")}">`;
    const dialog = document.createElement("div"); dialog.className = "modal-backdrop";
    dialog.innerHTML = `<div class="dialog"><h2>${this._editingIndex === null ? this._t("Add entity", "Entit\u00E4t hinzuf\u00FCgen") : this._t("Edit entity", "Entit\u00E4t bearbeiten")}</h2><form>${error ? `<div class="error">${this._escape(error)}</div>` : ""}<div class="grid">${identity}<section class="group"><h3 class="group-title">Modbus</h3><div class="group-grid">${this._select("table", this._t("Register area", "Bereich"), TABLES)}${this._field("register", this._t("Register", "Register"), "number", 'min="0" required')}${this._select("data_type", this._t("Data type", "Datentyp"), dataTypes)}${this._select("feedback_table", this._t("Feedback source", "R\u00FCckmeldung"), TABLES, true)}${modbusDetails}</div></section><section class="group"><h3 class="group-title">${this._t("Properties", "Eigenschaften")}</h3><div class="group-grid">${properties}</div></section></div><div class="buttons"><button type="button" class="button secondary cancel">${this._t("Cancel", "Abbrechen")}</button><button type="submit" class="button primary">${this._t("Save", "Speichern")}</button></div></form></div>`;
    this.shadowRoot.querySelector(".modal-backdrop")?.remove(); this.shadowRoot.appendChild(dialog);
    dialog.querySelector(".cancel").addEventListener("click", () => this._cancelEditor());
    this._wireIconPicker(dialog);
    this._wireKeyPreview(dialog);
    ["platform", "table", "data_type", "feedback_table", "device_class"].forEach((name) => dialog.querySelector(`[name="${name}"]`)?.addEventListener("change", () => { const previousPlatform = this._draft.platform; this._draft = this._readForm(dialog.querySelector("form"), false); if (this._draft.platform !== previousPlatform) { this._draft.device_class = null; this._draft.state_class = null; this._draft.unit = null; } if (["coil", "discrete_input"].includes(this._draft.table)) this._draft.data_type = "bool"; this._renderEditor(); }));
    dialog.querySelector("form").addEventListener("submit", (event) => { event.preventDefault(); this._saveEntity(this._readForm(event.target, true)); });
  }
  _readForm(form, includeOptions) {
    const data = { ...this._draft };
    new FormData(form).forEach((value, key) => { data[key] = value; });
    ["register", "count", "feedback_register", "command_on", "command_off", "pulse_ms"].forEach((key) => { if (key in data) data[key] = Number.parseInt(data[key], 10) || 0; });
    data.count = ["int32", "uint32", "float32"].includes(data.data_type) ? 2 : 1;
    ["scale", "offset", "minimum", "maximum", "step"].forEach((key) => { if (key in data) data[key] = Number.parseFloat(data[key]); });
    data.key ||= null;
    data.feedback_table ||= null; data.feedback_register = data.feedback_table ? data.feedback_register : null;
    const coilSensor = data.platform === "sensor" && data.table === "coil";
    if (coilSensor) data.options = {};
    else if (includeOptions && ["sensor", "binary_sensor", "select"].includes(data.platform)) data.options = JSON.parse(data.options_json || "{}");
    if (data.platform === "sensor" && data.options && (Array.isArray(data.options) ? data.options.length : Object.keys(data.options).length)) { data.device_class = "enum"; data.state_class = null; data.unit = null; }
    if (coilSensor && data.device_class === "enum") data.device_class = null;
    data.device_class ||= null; data.state_class = data.platform === "sensor" ? (data.state_class || null) : null;
    data.unit ||= null; data.icon ||= null; data.display_precision = data.display_precision === "" || data.display_precision === null || data.display_precision === undefined ? null : Number.parseInt(data.display_precision, 10); if (!["sensor", "number"].includes(data.platform) || data.data_type === "bool") data.display_precision = null; data.pulse_ms = ["toggle_switch", "button"].includes(data.platform) ? (data.pulse_ms || null) : null;
    data.writable = ["switch", "toggle_switch", "button", "number", "select"].includes(data.platform) && data.read_only !== "on";
    delete data.read_only;
    delete data.options_json;
    return data;
  }


  async _cancelEditor() {
    const index = this._removeOnCancelIndex;
    this._removeOnCancelIndex = null;
    this.shadowRoot.querySelector(".modal-backdrop")?.remove();
    if (index === null) return;
    const profile = structuredClone(this._entry.profile);
    profile.entities.splice(index, 1);
    try { await this._saveProfile(profile); this._render(); } catch (err) { alert(err.message || String(err)); }
  }
  async _saveEntity(entity) {
    try {
      const profile = structuredClone(this._entry.profile); const entities = profile.entities || [];
      if (this._editingIndex === null) entities.push(entity); else entities[this._editingIndex] = entity;
      if (this._regenerateKeyOnSave) entity.key = this._uniqueEntityKey(entity.name, entities, this._editingIndex);
      profile.entities = entities; await this._saveProfile(profile); this._removeOnCancelIndex = null; this._regenerateKeyOnSave = false; this.shadowRoot.querySelector(".modal-backdrop")?.remove(); this._render();
    } catch (err) { this._renderEditor(err.message || String(err)); }
  }


  async _regenerateKeys() {
    const message = this._t(
      "Regenerating all entity keys changes Home Assistant unique IDs. Existing entities may be recreated and custom entity IDs, history links, dashboard references, or automations may need updates. Continue?",
      "Beim Neugenerieren aller Entit\u00E4ts-Keys \u00E4ndern sich die Home-Assistant-unique_ids. Bestehende Entit\u00E4ten k\u00F6nnen neu angelegt werden und benutzerdefinierte entity_ids, Verlaufsbez\u00FCge, Dashboard-Referenzen oder Automationen m\u00FCssen eventuell angepasst werden. Fortfahren?"
    );
    if (!confirm(message)) return;
    const profile = structuredClone(this._entry.profile);
    const used = new Set();
    profile.entities = (profile.entities || []).map((entity) => {
      const key = this._uniqueEntityKey(entity.name, [], null, used);
      used.add(key);
      return { ...entity, key };
    });
    try { await this._saveProfile(profile); this._render(); } catch (err) { alert(err.message || String(err)); }
  }
  async _delete(index) {
    const entity = this._entry.profile.entities[index];
    if (!confirm(this._t(`Delete \u201C${entity.name}\u201D?`, `\u201E${entity.name}\u201C l\u00F6schen?`))) return;
    const profile = structuredClone(this._entry.profile); profile.entities.splice(index, 1);
    try { await this._saveProfile(profile); this._render(); } catch (err) { alert(err.message || String(err)); }
  }


  async _duplicate(index) {
    const source = this._entry.profile.entities[index];
    const profile = structuredClone(this._entry.profile);
    const entities = profile.entities || [];
    const copyName = this._duplicateName(source.name, entities);
    const duplicate = { ...structuredClone(source), name: copyName, key: this._uniqueEntityKey(copyName, entities) };
    entities.splice(index + 1, 0, duplicate);
    profile.entities = entities;
    try {
      await this._saveProfile(profile);
      this._render();
      this._openEditor(index + 1, true, true);
    } catch (err) { alert(err.message || String(err)); }
  }


  _uniqueEntityKey(name, entities, excludeIndex = null, existingKeys = null) {
    const existing = existingKeys || new Set(entities.filter((_entity, index) => index !== excludeIndex).map((entity) => entity.key).filter(Boolean));
    const normalized = String(name)
      .toLocaleLowerCase()
      .replaceAll("ß", "ss")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "");
    const base = normalized || "entity";
    let candidate = base;
    let suffix = 2;
    while (existing.has(candidate)) {
      candidate = `${base}_${suffix}`;
      suffix += 1;
    }
    return candidate;
  }
  _duplicateName(name, entities) {
    const base = this._t(`${name} copy`, `${name} Kopie`);
    const names = new Set(entities.map((entity) => entity.name));
    if (!names.has(base)) return base;
    let suffix = 2;
    while (names.has(`${base} ${suffix}`)) suffix += 1;
    return `${base} ${suffix}`;
  }
  async _saveProfile(profile) {
    const result = await this._hass.connection.sendMessagePromise({ type: "universal_modbus/editor/save", entry_id: this._entryId, profile });
    this._entry.profile = result.profile;
  }
}

customElements.define("universal-modbus-panel", UniversalModbusPanel);

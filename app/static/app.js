const currency = new Intl.NumberFormat("id-ID", {
  style: "currency",
  currency: "IDR",
  maximumFractionDigits: 0,
});

const number = new Intl.NumberFormat("id-ID", {
  maximumFractionDigits: 2,
});

const state = {
  activities: [],
  activeActivityId: null,
  activeActivity: null,
  referenceData: null,
  ui: {
    selectedSubComponentId: null,
    activeStep: 1,
    showActivityComposer: true,
    newFormCode: "",
    notice: "",
  },
};

const root = document.getElementById("app");
let stepObserver = null;

const STEP_TITLES = [
  "Kegiatan & Pagu",
  "Tahapan",
  "Bentuk Kegiatan",
  "Rekomendasi Akun",
  "Detail Belanja",
  "Input Anggaran",
  "Ringkasan",
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let message = "Terjadi kesalahan saat memproses permintaan.";
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch (error) {
      // ignore non-json error body
    }
    throw new Error(message);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response;
}

function notify(message) {
  state.ui.notice = message;
  render();
  window.clearTimeout(notify.timer);
  notify.timer = window.setTimeout(() => {
    state.ui.notice = "";
    render();
  }, 3200);
}

function formatCurrency(value) {
  return currency.format(Number(value || 0));
}

function formatNumber(value) {
  return number.format(Number(value || 0));
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function selectedSubComponent() {
  return state.activeActivity?.sub_components?.find(
    (item) => item.id === state.ui.selectedSubComponentId,
  );
}

function formDefinition(formCode) {
  return (
    state.activeActivity?.reference?.forms?.find((item) => item.code === formCode) || null
  );
}

function getReferenceData() {
  return (
    state.activeActivity?.reference ||
    state.referenceData || {
      forms: [],
      accounts: [],
      locations: {
        provinces: [],
        cities: [],
        cities_by_province: {},
      },
    }
  );
}

function accountCatalog() {
  return getReferenceData().accounts || [];
}

function normalizeSelectOptions(rawOptions = [], currentValue = "") {
  const options = rawOptions.map((option) =>
    typeof option === "string"
      ? { value: option, label: option }
      : { value: option.value, label: option.label ?? option.value },
  );

  if (
    currentValue !== undefined &&
    currentValue !== null &&
    String(currentValue).trim() !== "" &&
    !options.some((option) => String(option.value) === String(currentValue))
  ) {
    options.unshift({ value: currentValue, label: currentValue });
  }

  return options;
}

function locationOptions(referenceKey, currentValue = "", province = "") {
  const locations = getReferenceData().locations || {};
  if (referenceKey === "cities_by_province") {
    const groupedCities = locations.cities_by_province || {};
    const provinceCities = groupedCities[province] || [];
    const fallbackCities = locations.cities || [];
    const options = province && provinceCities.length ? provinceCities : fallbackCities;
    return normalizeSelectOptions(options, currentValue);
  }
  return normalizeSelectOptions(locations[referenceKey] || [], currentValue);
}

function renderAttributes(attributes = {}) {
  return Object.entries(attributes)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([name, value]) => ` ${name}="${escapeHtml(value)}"`)
    .join("");
}

function renderOptionsMarkup(options, currentValue) {
  return options
    .map(
      (option) => `
        <option value="${escapeHtml(option.value)}" ${
          String(option.value) === String(currentValue) ? "selected" : ""
        }>
          ${escapeHtml(option.label)}
        </option>
      `,
    )
    .join("");
}

function wrapConditionalField(content, field) {
  if (!field?.visible_when) {
    return content;
  }
  return `
    <div class="conditional-field" data-visible-when="${escapeHtml(
      JSON.stringify(field.visible_when),
    )}">
      ${content}
    </div>
  `;
}

function renderSelectControl({
  fieldId,
  name,
  label,
  options,
  currentValue,
  className = "field",
  attributes = {},
}) {
  const normalizedOptions = normalizeSelectOptions(options, currentValue);
  if (!normalizedOptions.length) {
    return `
      <label class="${className}">
        <span>${escapeHtml(label)}</span>
        <input id="${fieldId}" name="${escapeHtml(name)}" type="text" value="${escapeHtml(currentValue ?? "")}"${renderAttributes(attributes)} />
      </label>
    `;
  }

  const optionMarkup = renderOptionsMarkup(normalizedOptions, currentValue);

  return `
    <label class="${className}">
      <span>${escapeHtml(label)}</span>
      <select id="${fieldId}" name="${escapeHtml(name)}"${renderAttributes(attributes)}>${optionMarkup}</select>
    </label>
  `;
}

function collectFormValues(formElement) {
  const values = {};
  const entries = formElement.querySelectorAll("[name]");
  entries.forEach((field) => {
    if (field.disabled) {
      return;
    }
    if (field.type === "checkbox") {
      values[field.name] = field.checked;
      return;
    }
    if (field.type === "number") {
      values[field.name] = field.value === "" ? 0 : Number(field.value);
      return;
    }
    values[field.name] = field.value;
  });
  return values;
}

function renderSchemaFields(schema, values = {}, scopeId) {
  if (!schema?.length) {
    return '<p class="helper">Form ini belum memiliki parameter tambahan.</p>';
  }

  return schema
    .map((field) => {
      const currentValue =
        values[field.name] !== undefined ? values[field.name] : field.default ?? "";
      const fieldId = `${scopeId}-${field.name}`;

      if (field.type === "checkbox") {
        return wrapConditionalField(
          `
          <label class="toggle-row" for="${fieldId}">
            <span>${escapeHtml(field.label)}</span>
            <input id="${fieldId}" name="${escapeHtml(field.name)}" type="checkbox" ${
              currentValue ? "checked" : ""
            } />
          </label>
        `,
          field,
        );
      }

      if (field.type === "select" || field.reference_key) {
        const provinceValue =
          field.province_source_field
            ? values[field.province_source_field] || ""
            : field.province_source === "activity_default_province"
              ? state.activeActivity?.activity?.default_province || ""
              : "";
        const options = field.reference_key
          ? locationOptions(field.reference_key, currentValue, provinceValue)
          : field.options || [];
        const attributes = field.reference_key
          ? {
              "data-location-reference": field.reference_key,
              "data-province-source-field": field.province_source_field,
              "data-province-source": field.province_source,
            }
          : {};
        return wrapConditionalField(
          renderSelectControl({
            fieldId,
            name: field.name,
            label: field.label,
            options,
            currentValue,
            attributes,
          }),
          field,
        );
      }

      return wrapConditionalField(
        `
        <label class="field">
          <span>${escapeHtml(field.label)}</span>
          <input
            id="${fieldId}"
            name="${escapeHtml(field.name)}"
            type="${field.type === "number" ? "number" : "text"}"
            value="${escapeHtml(currentValue)}"
          />
        </label>
      `,
        field,
      );
    })
    .join("");
}

function renderActivitySidebar() {
  const defaultProvinceField = renderSelectControl({
    fieldId: "create-default-province",
    name: "default_province",
    label: "Provinsi default",
    options: locationOptions("provinces", "DKI JAKARTA"),
    currentValue: "DKI JAKARTA",
  });
  const originCityField = renderSelectControl({
    fieldId: "create-origin-city",
    name: "origin_city",
    label: "Kota asal",
    options: locationOptions("cities_by_province", "JAKARTA", "DKI JAKARTA"),
    currentValue: "JAKARTA",
    attributes: {
      "data-location-reference": "cities_by_province",
      "data-province-source-field": "default_province",
    },
  });
  const cards = state.activities
    .map((activity) => {
      const isActive = activity.id === state.activeActivityId;
      return `
        <button class="activity-card ${isActive ? "active" : ""}" data-action="select-activity" data-activity-id="${activity.id}">
          <strong>${escapeHtml(activity.name)}</strong>
          <span>${formatCurrency(activity.budget_ceiling)}</span>
          <small>${formatCurrency(activity.summary?.grand_total || 0)} teralokasi</small>
        </button>
      `;
    })
    .join("");

  return `
    <aside class="sidebar">
      <div class="brand-card">
        <p class="eyebrow">Workflow RAB Kegiatan</p>
        <h1>Assistant penyusunan RAB kegiatan pemerintah</h1>
        <p>Mulai dari kegiatan, tahapan, bentuk kegiatan, rekomendasi akun, sampai validasi pagu.</p>
      </div>

      <section class="panel compact stepper-panel">
        <h2>Stepper</h2>
        <div class="step-list">
          ${STEP_TITLES.map(
            (title, index) => `
              <button class="step-chip ${state.ui.activeStep === index + 1 ? "active" : ""}" data-action="goto-step" data-step="${index + 1}">
                <span>${index + 1}</span>${title}
              </button>
            `,
          ).join("")}
        </div>
      </section>

      <section class="panel compact">
        <div class="panel-head">
          <h2>Daftar Kegiatan</h2>
          <button class="ghost-btn" data-action="toggle-activity-composer">
            ${state.ui.showActivityComposer ? "Sembunyikan" : "Tambah"}
          </button>
        </div>
        ${
          state.ui.showActivityComposer
            ? `
          <form id="activity-create-form" class="inline-form">
            <label class="field">
              <span>Nama kegiatan</span>
              <input name="name" type="text" value="Kegiatan Baru" />
            </label>
            <label class="field">
              <span>Tahun</span>
              <input name="fiscal_year" type="number" value="2026" />
            </label>
            <label class="field">
              <span>Pagu</span>
              <input name="budget_ceiling" type="number" value="50000000" />
            </label>
            ${defaultProvinceField}
            ${originCityField}
            <label class="field">
              <span>Deskripsi singkat</span>
              <textarea name="description">Kegiatan untuk disusun melalui workflow RAB.</textarea>
            </label>
            <button type="button" class="primary-btn" data-action="create-activity">Buat kegiatan</button>
          </form>
        `
            : ""
        }
        <div class="activity-list">${cards || '<p class="helper">Belum ada kegiatan.</p>'}</div>
      </section>
    </aside>
  `;
}

function renderSummaryHero(activity, summary) {
  const warningClass = summary.remaining_budget < 0 ? "danger" : "good";
  return `
    <section class="hero-card">
      <div class="hero-copy">
        <p class="eyebrow">RAB Berbasis Workflow</p>
        <h2>${escapeHtml(activity.name)}</h2>
        <p>${escapeHtml(activity.description || "Lengkapi langkah wizard untuk membangun RAB kegiatan.")}</p>
      </div>
      <div class="hero-metrics">
        <div class="metric-card">
          <span>Pagu</span>
          <strong>${formatCurrency(summary.budget_ceiling)}</strong>
        </div>
        <div class="metric-card">
          <span>Total RAB</span>
          <strong>${formatCurrency(summary.grand_total)}</strong>
        </div>
        <div class="metric-card ${warningClass}">
          <span>Sisa Pagu</span>
          <strong>${formatCurrency(summary.remaining_budget)}</strong>
        </div>
        <div class="metric-card">
          <span>Utilisasi</span>
          <strong>${formatNumber(summary.utilization_percent)}%</strong>
        </div>
      </div>
      <div class="hero-actions">
        <a class="ghost-btn" href="/api/activities/${activity.id}/export/xlsx" target="_blank" rel="noreferrer">Ekspor Excel</a>
        <a class="ghost-btn" href="/api/activities/${activity.id}/export/pdf" target="_blank" rel="noreferrer">Ekspor PDF</a>
      </div>
    </section>
  `;
}

function renderBudgetMonitor(summary) {
  return `
    <section class="budget-monitor ${summary.remaining_budget < 0 ? "danger" : "good"}">
      <div class="budget-monitor-item">
        <span>Pagu</span>
        <strong>${formatCurrency(summary.budget_ceiling)}</strong>
      </div>
      <div class="budget-monitor-item">
        <span>Total RAB</span>
        <strong>${formatCurrency(summary.grand_total)}</strong>
      </div>
      <div class="budget-monitor-item">
        <span>Sisa pagu</span>
        <strong>${formatCurrency(summary.remaining_budget)}</strong>
      </div>
      <div class="budget-monitor-item">
        <span>Utilisasi</span>
        <strong>${formatNumber(summary.utilization_percent)}%</strong>
      </div>
    </section>
  `;
}

function renderActivityEditor(activity) {
  const provinceField = renderSelectControl({
    fieldId: "edit-default-province",
    name: "default_province",
    label: "Provinsi default",
    options: locationOptions("provinces", activity.default_province || ""),
    currentValue: activity.default_province || "",
  });
  const originCityField = renderSelectControl({
    fieldId: "edit-origin-city",
    name: "origin_city",
    label: "Kota asal default",
    options: locationOptions(
      "cities_by_province",
      activity.origin_city || "",
      activity.default_province || "",
    ),
    currentValue: activity.origin_city || "",
    attributes: {
      "data-location-reference": "cities_by_province",
      "data-province-source-field": "default_province",
    },
  });
  return `
    <section class="panel" id="step-1">
      <div class="panel-head">
        <h2>Step 1. Form kegiatan dan pagu</h2>
        <button class="danger-link" data-action="delete-activity" data-activity-id="${activity.id}">Hapus kegiatan</button>
      </div>
      <form id="activity-editor-form" class="grid-form">
        <label class="field">
          <span>Nama kegiatan</span>
          <input name="name" type="text" value="${escapeHtml(activity.name)}" />
        </label>
        <label class="field">
          <span>Tahun anggaran</span>
          <input name="fiscal_year" type="number" value="${escapeHtml(activity.fiscal_year)}" />
        </label>
        <label class="field">
          <span>Pagu anggaran</span>
          <input name="budget_ceiling" type="number" value="${escapeHtml(activity.budget_ceiling)}" />
        </label>
        ${provinceField}
        ${originCityField}
        <label class="field span-2">
          <span>Deskripsi kegiatan</span>
          <textarea name="description">${escapeHtml(activity.description || "")}</textarea>
        </label>
        <button type="button" class="primary-btn" data-action="save-activity">Simpan informasi kegiatan</button>
      </form>
    </section>
  `;
}

function renderSubComponents(subComponents) {
  const selectedId = state.ui.selectedSubComponentId;
  return `
    <section class="panel" id="step-2">
      <div class="panel-head">
        <h2>Step 2. Tahapan kegiatan</h2>
        <p>Kode sub komponen dibangkitkan otomatis A, B, C, D, dan seterusnya.</p>
      </div>
      <div class="sub-grid">
        <div class="sub-list">
          ${subComponents
            .map(
              (item) => `
                <button class="sub-card ${item.id === selectedId ? "active" : ""}" data-action="select-sub" data-sub-component-id="${item.id}">
                  <span class="sub-code">${escapeHtml(item.code)}</span>
                  <strong>${escapeHtml(item.name)}</strong>
                  <small>${formatCurrency(item.sub_total || 0)}</small>
                </button>
              `,
            )
            .join("")}
        </div>
        <div class="sub-editor">
          <form id="sub-create-form" class="inline-form">
            <label class="field">
              <span>Nama tahapan baru</span>
              <input name="name" type="text" value="Tahapan Baru" />
            </label>
            <label class="field">
              <span>Catatan</span>
              <textarea name="notes">Tambahkan tujuan atau catatan singkat tahapan ini.</textarea>
            </label>
            <button type="button" class="primary-btn" data-action="create-sub">Tambah tahapan</button>
          </form>
        </div>
      </div>
    </section>
  `;
}

function renderSelectedSubEditor(subComponent) {
  if (!subComponent) {
    return `
      <section class="panel">
        <h2>Pilih salah satu sub komponen</h2>
        <p class="helper">Step 3 sampai 6 akan mengikuti sub komponen yang sedang dipilih.</p>
      </section>
    `;
  }

  return `
    <section class="panel accent">
      <div class="panel-head">
        <h2>Sub Komponen ${escapeHtml(subComponent.code)}</h2>
        <button class="danger-link" data-action="delete-sub" data-sub-component-id="${subComponent.id}">Hapus tahapan</button>
      </div>
      <form id="sub-editor-form" data-sub-component-id="${subComponent.id}" class="grid-form">
        <label class="field">
          <span>Kode</span>
          <input type="text" value="${escapeHtml(subComponent.code)}" disabled />
        </label>
        <label class="field span-2">
          <span>Nama tahapan</span>
          <input name="name" type="text" value="${escapeHtml(subComponent.name)}" />
        </label>
        <label class="field span-3">
          <span>Catatan</span>
          <textarea name="notes">${escapeHtml(subComponent.notes || "")}</textarea>
        </label>
        <button type="button" class="primary-btn" data-action="save-sub" data-sub-component-id="${subComponent.id}">Simpan tahapan</button>
      </form>
    </section>
  `;
}

function renderFormsSection(subComponent) {
  const referenceForms = state.activeActivity.reference.forms;
  const draftDefinition =
    formDefinition(state.ui.newFormCode) || referenceForms[0] || null;
  const draftSchema = draftDefinition?.parameter_schema || [];
  const draftValues = Object.fromEntries(
    draftSchema.map((field) => [field.name, field.default ?? ""]),
  );

  return `
    <section class="panel" id="step-3">
      <div class="panel-head">
        <h2>Step 3. Pilih bentuk kegiatan per tahapan</h2>
        <p>Setiap bentuk kegiatan akan memicu rule rekomendasi akun belanja.</p>
      </div>
      <div class="form-selection-grid">
        ${
          subComponent.forms.length
            ? subComponent.forms
                .map((selection) => {
                  const definition = formDefinition(selection.form_code);
                  return `
                    <article class="embedded-card">
                      <div class="embedded-card-head">
                        <div>
                          <p class="eyebrow">Bentuk kegiatan</p>
                          <h3>${escapeHtml(selection.form_name)}</h3>
                        </div>
                        <button class="danger-link" data-action="delete-form" data-form-selection-id="${selection.id}">Hapus</button>
                      </div>
                      <p class="helper">${escapeHtml(selection.form_description || "")}</p>
                      <form id="form-selection-${selection.id}" data-form-selection-id="${selection.id}" class="grid-form">
                        <label class="field span-3">
                          <span>Jenis bentuk kegiatan</span>
                          <select name="form_code">
                            ${referenceForms
                              .map(
                                (item) => `
                                  <option value="${item.code}" ${item.code === selection.form_code ? "selected" : ""}>
                                    ${escapeHtml(item.name)}
                                  </option>
                                `,
                              )
                              .join("")}
                          </select>
                        </label>
                        ${renderSchemaFields(
                          definition?.parameter_schema || [],
                          selection.attributes,
                          `existing-${selection.id}`,
                        )}
                        <button type="button" class="primary-btn" data-action="save-form" data-form-selection-id="${selection.id}">
                          Simpan bentuk kegiatan
                        </button>
                      </form>
                    </article>
                  `;
                })
                .join("")
            : '<p class="helper empty-slab">Belum ada bentuk kegiatan pada tahapan ini. Tambahkan satu atau lebih skenario kegiatan di bawah.</p>'
        }
      </div>

      <article class="embedded-card add-card">
        <div class="embedded-card-head">
          <div>
            <p class="eyebrow">Tambah bentuk kegiatan</p>
            <h3>Composer rule engine</h3>
          </div>
        </div>
        <form id="form-create-form" class="grid-form">
          <label class="field span-3">
            <span>Pilih bentuk kegiatan</span>
            <select id="new-form-code" name="form_code">
              ${referenceForms
                .map(
                  (item) => `
                    <option value="${item.code}" ${item.code === (state.ui.newFormCode || draftDefinition?.code) ? "selected" : ""}>
                      ${escapeHtml(item.name)}
                    </option>
                  `,
                )
                .join("")}
            </select>
          </label>
          ${renderSchemaFields(draftSchema, draftValues, "new-form")}
          <button type="button" class="primary-btn" data-action="add-form" data-sub-component-id="${subComponent.id}">
            Simpan bentuk kegiatan
          </button>
        </form>
      </article>
    </section>
  `;
}

function renderAccountsSection(subComponent) {
  const manualOptions = accountCatalog()
    .map(
      (account) => `
        <option value="${account.code}">${account.code} - ${escapeHtml(account.name)}</option>
      `,
    )
    .join("");

  return `
    <section class="panel" id="step-4">
      <div class="panel-head">
        <h2>Step 4. Rekomendasi akun belanja</h2>
        <p>Akun tidak ditampilkan semua di awal. Mereka muncul berdasarkan pilihan bentuk kegiatan di tahap sebelumnya.</p>
      </div>

      <div class="account-grid">
        ${
          subComponent.accounts.length
            ? subComponent.accounts
                .map(
                  (account) => `
                    <article class="account-card ${account.is_selected ? "selected" : ""}">
                      <div class="account-head">
                        <div>
                          <p class="eyebrow">${account.is_manual ? "Manual" : account.is_recommended ? "Direkomendasikan" : "Dipertahankan"}</p>
                          <h3>${account.account_code} - ${escapeHtml(account.account_name)}</h3>
                        </div>
                        <label class="toggle-row compact">
                          <span>Aktif</span>
                          <input
                            type="checkbox"
                            ${account.is_selected ? "checked" : ""}
                            data-action="toggle-account"
                            data-account-selection-id="${account.id}"
                          />
                        </label>
                      </div>
                      <p>${escapeHtml(account.recommendation_reason || "Akun dipilih manual pengguna.")}</p>
                      <div class="pill-row">
                        <span class="pill">${escapeHtml(account.account_category || "")}</span>
                        <span class="pill">${formatCurrency(account.account_total || 0)}</span>
                        <span class="pill">${account.lines.length} detail</span>
                      </div>
                    </article>
                  `,
                )
                .join("")
            : '<p class="helper empty-slab">Belum ada akun yang direkomendasikan. Tambahkan bentuk kegiatan dulu pada Step 3.</p>'
        }
      </div>

      <div class="manual-account-box">
        <label class="field">
          <span>Tambah akun manual jika diperlukan</span>
          <select id="manual-account-select">${manualOptions}</select>
        </label>
        <button type="button" class="ghost-btn" data-action="add-manual-account" data-sub-component-id="${subComponent.id}">Tambahkan akun manual</button>
      </div>
    </section>
  `;
}

function renderLineRow(line) {
  return `
    <tr data-line-id="${line.id}">
      <td><input class="line-input" name="item_name" type="text" value="${escapeHtml(line.item_name)}" /></td>
      <td><input class="line-input" name="specification" type="text" value="${escapeHtml(line.specification || "")}" /></td>
      <td><input class="line-input" name="volume" type="number" step="0.01" value="${escapeHtml(line.volume)}" /></td>
      <td><input class="line-input" name="unit" type="text" value="${escapeHtml(line.unit)}" /></td>
      <td><input class="line-input" name="unit_price" type="number" step="0.01" value="${escapeHtml(line.unit_price)}" /></td>
      <td class="numeric">${formatCurrency(line.amount)}</td>
      <td class="helper-cell">${escapeHtml(line.suggestion_note || "-")}</td>
      <td><button class="danger-link" data-action="delete-line" data-line-id="${line.id}">Hapus</button></td>
    </tr>
  `;
}

function renderBudgetLines(subComponent) {
  return `
    <section class="panel" id="step-5">
      <div class="panel-head">
        <h2>Step 5-6. Detail item belanja, volume, satuan, dan harga</h2>
        <p>Harga awal diisi dari referensi SBM bila tersedia. User tetap bisa menyesuaikan volume, satuan, dan harga satuan.</p>
      </div>
      <div class="line-card-stack">
        ${
          subComponent.accounts.length
            ? subComponent.accounts
                .map(
                  (account) => `
                    <article class="line-card ${account.is_selected ? "" : "muted"}">
                      <div class="line-card-head">
                        <div>
                          <p class="eyebrow">${account.account_code}</p>
                          <h3>${escapeHtml(account.account_name)}</h3>
                        </div>
                        <div class="pill-row">
                          <span class="pill">${account.is_selected ? "Aktif dihitung" : "Tidak dihitung"}</span>
                          <span class="pill">${formatCurrency(account.account_total || 0)}</span>
                        </div>
                      </div>
                      ${
                        account.lines.length
                          ? `
                            <div class="table-wrap">
                              <table>
                                <thead>
                                  <tr>
                                    <th>Detail belanja</th>
                                    <th>Spesifikasi</th>
                                    <th>Volume</th>
                                    <th>Satuan</th>
                                    <th>Harga satuan</th>
                                    <th>Subtotal</th>
                                    <th>Catatan referensi</th>
                                    <th></th>
                                  </tr>
                                </thead>
                                <tbody>${account.lines.map(renderLineRow).join("")}</tbody>
                              </table>
                            </div>
                          `
                          : '<p class="helper">Belum ada detail item pada akun ini. Aktifkan akun untuk memunculkan detail default, atau tambahkan manual.</p>'
                      }
                      <form class="inline-form line-adder" data-account-selection-id="${account.id}">
                        <label class="field">
                          <span>Detail manual baru</span>
                          <input name="item_name" type="text" value="Detail belanja tambahan" />
                        </label>
                        <label class="field">
                          <span>Volume</span>
                          <input name="volume" type="number" value="1" />
                        </label>
                        <label class="field">
                          <span>Satuan</span>
                          <input name="unit" type="text" value="Paket" />
                        </label>
                        <label class="field">
                          <span>Harga satuan</span>
                          <input name="unit_price" type="number" value="0" />
                        </label>
                        <label class="field span-2">
                          <span>Spesifikasi</span>
                          <input name="specification" type="text" value="" />
                        </label>
                        <button type="button" class="ghost-btn" data-action="add-line" data-account-selection-id="${account.id}">
                          Tambah detail manual
                        </button>
                      </form>
                    </article>
                  `,
                )
                .join("")
            : '<p class="helper empty-slab">Belum ada akun pada tahapan ini.</p>'
        }
      </div>
    </section>
  `;
}

function renderSummarySection(summary) {
  const warningItems = summary.warnings || [];
  return `
    <section class="panel" id="step-7">
      <div class="panel-head">
        <h2>Step 7. Ringkasan total dan sisa pagu</h2>
        <p>Validasi pagu dihitung otomatis dari total akun, total sub komponen, dan total kegiatan.</p>
      </div>
      <div class="budget-progress">
        <div class="budget-progress-bar">
          <span style="width: ${Math.min(summary.utilization_percent || 0, 100)}%"></span>
        </div>
        <div class="budget-progress-meta">
          <strong>${formatNumber(summary.utilization_percent || 0)}%</strong>
          <span>${formatCurrency(summary.grand_total)} dari ${formatCurrency(summary.budget_ceiling)}</span>
        </div>
      </div>
      <div class="summary-grid">
        <article class="summary-card">
          <h3>Total per sub komponen</h3>
          <ul class="summary-list">
            ${
              summary.totals_by_sub_component?.length
                ? summary.totals_by_sub_component
                    .map(
                      (item) => `
                        <li><span>${escapeHtml(item.code)}. ${escapeHtml(item.name)}</span><strong>${formatCurrency(item.total)}</strong></li>
                      `,
                    )
                    .join("")
                : `<li><span>Belum ada alokasi aktif</span><strong>${formatCurrency(0)}</strong></li>`
            }
          </ul>
        </article>
        <article class="summary-card">
          <h3>Total per akun</h3>
          <ul class="summary-list">
            ${
              summary.totals_by_account?.length
                ? summary.totals_by_account
                    .map(
                      (item) => `
                        <li><span>${escapeHtml(item.account_code)} - ${escapeHtml(item.account_name)}</span><strong>${formatCurrency(item.total)}</strong></li>
                      `,
                    )
                    .join("")
                : `<li><span>Belum ada akun aktif</span><strong>${formatCurrency(0)}</strong></li>`
            }
          </ul>
        </article>
      </div>
      ${
        warningItems.length
          ? `
            <div class="warning-box">
              <h3>Validasi bisnis proses</h3>
              <ul>
                ${warningItems.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
              </ul>
            </div>
          `
          : `
            <div class="success-box">
              <strong>Validasi dasar lulus.</strong>
              <span>Total anggaran masih dalam pagu dan tidak ada warning utama.</span>
            </div>
          `
      }
    </section>
  `;
}

function renderWorkspace() {
  if (!state.activeActivity) {
    return `
      <main class="workspace">
        <section class="empty-state panel">
          <p class="eyebrow">Mulai Dari Kegiatan</p>
          <h2>Buat kegiatan pertama untuk memulai penyusunan RAB.</h2>
          <p>Setelah kegiatan dibuat, wizard akan memandu tahapan, bentuk kegiatan, rekomendasi akun, dan perhitungan total.</p>
        </section>
      </main>
    `;
  }

  const { activity, summary, sub_components } = state.activeActivity;
  const selected = selectedSubComponent();

  return `
    <main class="workspace">
      ${renderSummaryHero(activity, summary)}
      ${renderBudgetMonitor(summary)}
      ${renderActivityEditor(activity)}
      ${renderSubComponents(sub_components)}
      ${renderSelectedSubEditor(selected)}
      ${selected ? renderFormsSection(selected) : ""}
      ${selected ? renderAccountsSection(selected) : ""}
      ${selected ? renderBudgetLines(selected) : ""}
      ${renderSummarySection(summary)}
    </main>
  `;
}

function render() {
  root.innerHTML = `
    <div class="shell">
      ${renderActivitySidebar()}
      ${renderWorkspace()}
      ${state.ui.notice ? `<div class="notice">${escapeHtml(state.ui.notice)}</div>` : ""}
    </div>
  `;
  updateConditionalFields(root);
  updateDependentLocationSelects(root);
  setupStepObserver();
  syncActiveStepWithViewport();
}

function updateConditionalFields(scope = root) {
  scope?.querySelectorAll("[data-visible-when]").forEach((wrapper) => {
    let conditions = {};
    try {
      conditions = JSON.parse(wrapper.dataset.visibleWhen || "{}");
    } catch (error) {
      conditions = {};
    }

    const form = wrapper.closest("form");
    const isVisible = Object.entries(conditions).every(([fieldName, expectedValue]) => {
      const field = form?.querySelector(`[name="${fieldName}"]`);
      if (!field) {
        return false;
      }
      const actualValue =
        field.type === "checkbox" ? String(field.checked) : String(field.value);
      return actualValue === String(expectedValue);
    });

    wrapper.classList.toggle("hidden", !isVisible);
    wrapper.querySelectorAll("[name]").forEach((field) => {
      field.disabled = !isVisible;
    });
  });
}

function resolveProvinceForDependentSelect(select) {
  if (select.dataset.provinceSourceField) {
    const form = select.closest("form");
    return form?.querySelector(`[name="${select.dataset.provinceSourceField}"]`)?.value || "";
  }
  if (select.dataset.provinceSource === "activity_default_province") {
    return state.activeActivity?.activity?.default_province || "";
  }
  return "";
}

function updateDependentLocationSelects(scope = root) {
  scope
    ?.querySelectorAll('select[data-location-reference="cities_by_province"]')
    .forEach((select) => {
      const province = resolveProvinceForDependentSelect(select);
      const options = locationOptions("cities_by_province", select.value, province);
      const nextValue = options.some(
        (option) => String(option.value) === String(select.value),
      )
        ? select.value
        : options[0]?.value || "";
      select.innerHTML = renderOptionsMarkup(options, nextValue);
      select.value = nextValue;
    });
}

function refreshStepChipState() {
  root.querySelectorAll('[data-action="goto-step"]').forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.step) === state.ui.activeStep);
  });
}

function setupStepObserver() {
  if (stepObserver) {
    stepObserver.disconnect();
    stepObserver = null;
  }

  if (!("IntersectionObserver" in window)) {
    return;
  }

  const sections = STEP_TITLES.map((_, index) =>
    document.getElementById(`step-${index + 1}`),
  ).filter(Boolean);
  if (!sections.length) {
    return;
  }

  stepObserver = new IntersectionObserver(
    (entries) => {
      const visibleEntries = entries
        .filter((entry) => entry.isIntersecting)
        .sort(
          (left, right) =>
            right.intersectionRatio - left.intersectionRatio ||
            left.boundingClientRect.top - right.boundingClientRect.top,
        );
      if (!visibleEntries.length) {
        return;
      }
      const nextStep = Number(
        visibleEntries[0].target.id.replace("step-", ""),
      );
      if (state.ui.activeStep !== nextStep) {
        state.ui.activeStep = nextStep;
        refreshStepChipState();
      }
    },
    {
      root: null,
      rootMargin: "-18% 0px -55% 0px",
      threshold: [0.12, 0.3, 0.5, 0.75],
    },
  );

  sections.forEach((section) => {
    stepObserver.observe(section);
  });
}

function syncActiveStepWithViewport() {
  const sections = STEP_TITLES.map((_, index) =>
    document.getElementById(`step-${index + 1}`),
  ).filter(Boolean);
  if (!sections.length) {
    return;
  }

  let activeStep = Number(sections[0].id.replace("step-", ""));
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const section of sections) {
    const distance = Math.abs(section.getBoundingClientRect().top - 170);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      activeStep = Number(section.id.replace("step-", ""));
    }
  }

  state.ui.activeStep = activeStep;
  refreshStepChipState();
}

async function refreshActivities(preserveActive = true) {
  state.activities = await api("/api/activities");
  if (!state.activities.length) {
    state.activeActivityId = null;
    state.activeActivity = null;
    return;
  }

  if (!preserveActive || !state.activeActivityId) {
    state.activeActivityId = state.activities[0].id;
  }

  const stillExists = state.activities.some((item) => item.id === state.activeActivityId);
  if (!stillExists) {
    state.activeActivityId = state.activities[0].id;
  }
}

async function openActivity(activityId) {
  state.activeActivityId = activityId;
  state.activeActivity = await api(`/api/activities/${activityId}`);
  state.referenceData = state.activeActivity.reference || state.referenceData;
  if (!state.ui.newFormCode) {
    state.ui.newFormCode = state.activeActivity.reference.forms?.[0]?.code || "";
  }
  const firstSub = state.activeActivity.sub_components?.[0]?.id || null;
  if (
    !state.ui.selectedSubComponentId ||
    !state.activeActivity.sub_components.some((item) => item.id === state.ui.selectedSubComponentId)
  ) {
    state.ui.selectedSubComponentId = firstSub;
  }
}

async function reloadActiveActivity() {
  if (!state.activeActivityId) {
    await refreshActivities();
    return;
  }
  await refreshActivities();
  await openActivity(state.activeActivityId);
}

async function initialize() {
  try {
    await api("/api/health");
    state.referenceData = await api("/api/reference-data");
    await refreshActivities(false);
    if (state.activities.length) {
      await openActivity(state.activities[0].id);
    }
    render();
  } catch (error) {
    root.innerHTML = `
      <div class="splash">
        <div class="splash-card">
          <p class="eyebrow">Tidak bisa memuat aplikasi</p>
          <h1>${escapeHtml(error.message)}</h1>
          <p>Pastikan backend FastAPI berjalan lalu muat ulang halaman.</p>
        </div>
      </div>
    `;
  }
}

async function handleClick(event) {
  const actionTarget = event.target.closest("[data-action]");
  if (!actionTarget) {
    return;
  }

  const action = actionTarget.dataset.action;
  try {
    if (action === "toggle-activity-composer") {
      state.ui.showActivityComposer = !state.ui.showActivityComposer;
      render();
      return;
    }

    if (action === "select-activity") {
      await openActivity(actionTarget.dataset.activityId);
      render();
      return;
    }

    if (action === "goto-step") {
      state.ui.activeStep = Number(actionTarget.dataset.step);
      refreshStepChipState();
      document.getElementById(`step-${state.ui.activeStep}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }

    if (action === "create-activity") {
      const form = document.getElementById("activity-create-form");
      const values = collectFormValues(form);
      const created = await api("/api/activities", {
        method: "POST",
        body: JSON.stringify(values),
      });
      await refreshActivities(false);
      state.activeActivityId = created.activity.id;
      await openActivity(created.activity.id);
      notify("Kegiatan baru berhasil dibuat.");
      render();
      return;
    }

    if (action === "save-activity") {
      const form = document.getElementById("activity-editor-form");
      const values = collectFormValues(form);
      state.activeActivity = await api(`/api/activities/${state.activeActivityId}`, {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      await refreshActivities();
      notify("Informasi kegiatan diperbarui.");
      render();
      return;
    }

    if (action === "delete-activity") {
      if (!window.confirm("Hapus kegiatan ini beserta semua tahapan dan detail anggarannya?")) {
        return;
      }
      await api(`/api/activities/${actionTarget.dataset.activityId}`, { method: "DELETE" });
      await refreshActivities(false);
      if (state.activities.length) {
        await openActivity(state.activities[0].id);
      } else {
        state.activeActivity = null;
        state.activeActivityId = null;
      }
      notify("Kegiatan dihapus.");
      render();
      return;
    }

    if (action === "select-sub") {
      state.ui.selectedSubComponentId = actionTarget.dataset.subComponentId;
      render();
      return;
    }

    if (action === "create-sub") {
      const form = document.getElementById("sub-create-form");
      const values = collectFormValues(form);
      state.activeActivity = await api(`/api/activities/${state.activeActivityId}/sub-components`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      state.ui.selectedSubComponentId =
        state.activeActivity.sub_components[state.activeActivity.sub_components.length - 1]?.id || null;
      await refreshActivities();
      notify("Tahapan kegiatan berhasil ditambahkan.");
      render();
      return;
    }

    if (action === "save-sub") {
      const form = document.getElementById("sub-editor-form");
      const values = collectFormValues(form);
      state.activeActivity = await api(`/api/sub-components/${actionTarget.dataset.subComponentId}`, {
        method: "PATCH",
        body: JSON.stringify(values),
      });
      await refreshActivities();
      notify("Sub komponen diperbarui.");
      render();
      return;
    }

    if (action === "delete-sub") {
      if (!window.confirm("Hapus tahapan ini? Kode tahapan lain akan disusun ulang otomatis.")) {
        return;
      }
      state.activeActivity = await api(`/api/sub-components/${actionTarget.dataset.subComponentId}`, {
        method: "DELETE",
      });
      state.ui.selectedSubComponentId = state.activeActivity.sub_components?.[0]?.id || null;
      await refreshActivities();
      notify("Tahapan dihapus dan kode disusun ulang.");
      render();
      return;
    }

    if (action === "add-form") {
      const form = document.getElementById("form-create-form");
      const values = collectFormValues(form);
      const payload = {
        form_code: values.form_code,
        attributes: Object.fromEntries(Object.entries(values).filter(([key]) => key !== "form_code")),
      };
      state.activeActivity = await api(`/api/sub-components/${actionTarget.dataset.subComponentId}/forms`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await refreshActivities();
      notify("Bentuk kegiatan ditambahkan dan rekomendasi akun diperbarui.");
      render();
      return;
    }

    if (action === "save-form") {
      const form = document.getElementById(`form-selection-${actionTarget.dataset.formSelectionId}`);
      const values = collectFormValues(form);
      const payload = {
        form_code: values.form_code,
        attributes: Object.fromEntries(Object.entries(values).filter(([key]) => key !== "form_code")),
      };
      state.activeActivity = await api(`/api/forms/${actionTarget.dataset.formSelectionId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await refreshActivities();
      notify("Bentuk kegiatan diperbarui dan rule engine dijalankan ulang.");
      render();
      return;
    }

    if (action === "delete-form") {
      if (!window.confirm("Hapus bentuk kegiatan ini?")) {
        return;
      }
      state.activeActivity = await api(`/api/forms/${actionTarget.dataset.formSelectionId}`, {
        method: "DELETE",
      });
      await refreshActivities();
      notify("Bentuk kegiatan dihapus.");
      render();
      return;
    }

    if (action === "toggle-account") {
      state.activeActivity = await api(`/api/accounts/${actionTarget.dataset.accountSelectionId}/toggle`, {
        method: "PATCH",
        body: JSON.stringify({ is_selected: actionTarget.checked }),
      });
      await refreshActivities();
      notify("Status akun diperbarui.");
      render();
      return;
    }

    if (action === "add-manual-account") {
      const select = document.getElementById("manual-account-select");
      state.activeActivity = await api(`/api/sub-components/${actionTarget.dataset.subComponentId}/manual-account`, {
        method: "POST",
        body: JSON.stringify({ account_code: select.value }),
      });
      await refreshActivities();
      notify("Akun manual ditambahkan.");
      render();
      return;
    }

    if (action === "add-line") {
      const form = actionTarget.closest("form");
      const values = collectFormValues(form);
      state.activeActivity = await api(`/api/accounts/${actionTarget.dataset.accountSelectionId}/lines`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      await refreshActivities();
      notify("Detail belanja manual ditambahkan.");
      render();
      return;
    }

    if (action === "delete-line") {
      state.activeActivity = await api(`/api/lines/${actionTarget.dataset.lineId}`, {
        method: "DELETE",
      });
      await refreshActivities();
      notify("Detail belanja dihapus.");
      render();
      return;
    }
  } catch (error) {
    notify(error.message);
  }
}

async function handleChange(event) {
  const target = event.target;

  if (target.id === "new-form-code") {
    state.ui.newFormCode = target.value;
    render();
    return;
  }

  if (target.closest("form")) {
    updateConditionalFields(target.closest("form"));
  }

  if (target.classList.contains("line-input")) {
    const row = target.closest("[data-line-id]");
    const payload = {
      item_name: row.querySelector('[name="item_name"]').value,
      specification: row.querySelector('[name="specification"]').value,
      volume: Number(row.querySelector('[name="volume"]').value || 0),
      unit: row.querySelector('[name="unit"]').value,
      unit_price: Number(row.querySelector('[name="unit_price"]').value || 0),
    };
    try {
      state.activeActivity = await api(`/api/lines/${row.dataset.lineId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await refreshActivities();
      render();
    } catch (error) {
      notify(error.message);
    }
  }

  if (target.matches('select[name="default_province"], select[name="province"]')) {
    updateDependentLocationSelects(target.closest("form"));
  }
}

root.addEventListener("click", handleClick);
root.addEventListener("change", handleChange);
window.addEventListener("scroll", syncActiveStepWithViewport, { passive: true });
window.addEventListener("resize", syncActiveStepWithViewport, { passive: true });

initialize();

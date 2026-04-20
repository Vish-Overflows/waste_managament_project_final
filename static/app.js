const state = {
  config: null,
  user: null,
  operatorCollections: [],
  wetStatus: null,
};

const elements = {
  loginView: document.getElementById("loginView"),
  appView: document.getElementById("appView"),
  loginForm: document.getElementById("loginForm"),
  loginMessage: document.getElementById("loginMessage"),
  username: document.getElementById("username"),
  password: document.getElementById("password"),
  welcomeLine: document.getElementById("welcomeLine"),
  roleLine: document.getElementById("roleLine"),
  logoutButton: document.getElementById("logoutButton"),
  staffSection: document.getElementById("staffSection"),
  operatorSection: document.getElementById("operatorSection"),
  adminSection: document.getElementById("adminSection"),
  staffForm: document.getElementById("staffForm"),
  staffHousingBlock: document.getElementById("staffHousingBlock"),
  staffRoomNumber: document.getElementById("staffRoomNumber"),
  staffCollectionDate: document.getElementById("staffCollectionDate"),
  staffMessage: document.getElementById("staffMessage"),
  operatorCollectionsBody: document.getElementById("operatorCollectionsBody"),
  operatorForm: document.getElementById("operatorForm"),
  operatorMode: document.getElementById("operatorMode"),
  segregationFields: document.getElementById("segregationFields"),
  compostFields: document.getElementById("compostFields"),
  collectionSelect: document.getElementById("collectionSelect"),
  processingCategory: document.getElementById("processingCategory"),
  processingSubtype: document.getElementById("processingSubtype"),
  processingQuantity: document.getElementById("processingQuantity"),
  compostQuantity: document.getElementById("compostQuantity"),
  wetTotalValue: document.getElementById("wetTotalValue"),
  wetCompostValue: document.getElementById("wetCompostValue"),
  wetBiogasValue: document.getElementById("wetBiogasValue"),
  operatorSubmitButton: document.getElementById("operatorSubmitButton"),
  operatorMessage: document.getElementById("operatorMessage"),
  refreshDashboardButton: document.getElementById("refreshDashboardButton"),
  metricsGrid: document.getElementById("metricsGrid"),
  breakdownList: document.getElementById("breakdownList"),
  wetProcessingPanel: document.getElementById("wetProcessingPanel"),
  blockAnalyticsPanel: document.getElementById("blockAnalyticsPanel"),
  operatorAnalyticsPanel: document.getElementById("operatorAnalyticsPanel"),
  trendAnalyticsPanel: document.getElementById("trendAnalyticsPanel"),
  recentCollectionsBody: document.getElementById("recentCollectionsBody"),
  recentProcessingBody: document.getElementById("recentProcessingBody"),
  dashboardMessage: document.getElementById("dashboardMessage"),
  credentialChips: document.querySelectorAll(".credential-chip"),
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }
  return payload;
}

function setMessage(element, message, type = "") {
  element.textContent = message;
  element.className = "status-message";
  if (type) {
    element.classList.add(type);
  }
}

function populateSelect(select, values, placeholder) {
  select.innerHTML = "";
  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  select.appendChild(placeholderOption);

  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function formatKg(value) {
  return `${Number(value || 0).toFixed(2)} kg`;
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function populateStaticOptions() {
  populateSelect(elements.staffHousingBlock, state.config.blocks, "Select housing block");
  populateSelect(elements.staffRoomNumber, [], "Select room number");
  populateSelect(elements.processingCategory, state.config.processingCategories, "Select waste category");
  populateSelect(elements.processingSubtype, [], "Select waste sub type");
  elements.staffCollectionDate.value = todayIsoDate();
}

function updateStaffRooms() {
  const block = elements.staffHousingBlock.value;
  const rooms = block ? (state.config.roomsByBlock[block] || []) : [];
  populateSelect(elements.staffRoomNumber, rooms, "Select room number");
  elements.staffRoomNumber.disabled = !block;
}

function updateProcessingSubtype() {
  const category = elements.processingCategory.value;
  let values = [];
  if (category === "Dry Waste") {
    values = state.config.dryWasteTypes;
  } else if (category === "Wet Waste") {
    values = state.config.wetWasteTypes;
  }
  populateSelect(elements.processingSubtype, values, "Select waste sub type");
}

function renderAppView() {
  const isAuthenticated = Boolean(state.user);
  elements.loginView.classList.toggle("hidden", isAuthenticated);
  elements.appView.classList.toggle("hidden", !isAuthenticated);
  if (!isAuthenticated) {
    return;
  }

  elements.welcomeLine.textContent = `Welcome, ${state.user.employee_id}`;
  elements.roleLine.textContent = `Role: ${state.user.role.charAt(0).toUpperCase()}${state.user.role.slice(1)}`;

  elements.staffSection.classList.toggle("hidden", state.user.role !== "staff");
  elements.operatorSection.classList.toggle("hidden", state.user.role !== "operator");
  elements.adminSection.classList.toggle("hidden", state.user.role !== "admin");
}

function renderOperatorCollections(collections) {
  state.operatorCollections = collections;
  elements.operatorCollectionsBody.innerHTML = "";
  populateSelect(elements.collectionSelect, [], "Select collected entry");

  if (collections.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="6" class="muted-text">No staff collections have been marked yet.</td>';
    elements.operatorCollectionsBody.appendChild(row);
    return;
  }

  collections.forEach((collection) => {
    const option = document.createElement("option");
    option.value = String(collection.id);
    option.textContent = `${collection.housingBlock} / ${collection.roomNumber} / ${collection.collectionDate}`;
    elements.collectionSelect.appendChild(option);

    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${collection.collectionDate}</td>
      <td>${collection.employeeId}</td>
      <td>${collection.housingBlock}</td>
      <td>${collection.roomNumber}</td>
      <td>${collection.processedEntriesCount}</td>
      <td>${formatKg(collection.processedWeight)}</td>
    `;
    elements.operatorCollectionsBody.appendChild(row);
  });
}

function renderWetStatus(status) {
  state.wetStatus = status;
  elements.wetTotalValue.textContent = formatKg(status.totalWetProcessed);
  elements.wetCompostValue.textContent = status.latestUpdate
    ? formatKg(status.latestUpdate.compostQuantity)
    : formatKg(0);
  updateBiogasPreview();
}

function updateBiogasPreview() {
  const totalWet = state.wetStatus ? Number(state.wetStatus.totalWetProcessed) : 0;
  const compost = Number(elements.compostQuantity.value || 0);
  const biogas = Math.max(totalWet - compost, 0);
  elements.wetBiogasValue.textContent = formatKg(biogas);
}

function updateOperatorMode() {
  const isCompost = elements.operatorMode.value === "compost";
  elements.segregationFields.classList.toggle("hidden", isCompost);
  elements.compostFields.classList.toggle("hidden", !isCompost);
  elements.collectionSelect.required = !isCompost;
  elements.processingCategory.required = !isCompost;
  elements.processingSubtype.required = !isCompost;
  elements.processingQuantity.required = !isCompost;
  elements.compostQuantity.required = isCompost;
  elements.operatorSubmitButton.textContent = isCompost ? "Save Compost Update" : "Save Segregation Entry";
}

async function bootstrap() {
  state.config = await request("/api/config", { method: "GET" });
  populateStaticOptions();

  const session = await request("/api/session", { method: "GET" });
  state.user = session.authenticated ? session.user : null;
  renderAppView();

  if (state.user?.role === "staff") {
    elements.staffCollectionDate.value = todayIsoDate();
  }
  if (state.user?.role === "operator") {
    await Promise.all([loadOperatorCollections(), loadWetProcessingStatus()]);
  }
  if (state.user?.role === "admin") {
    await loadDashboard();
  }
}

async function handleLogin(event) {
  event.preventDefault();
  setMessage(elements.loginMessage, "Signing in...");
  try {
    const payload = await request("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: elements.username.value.trim(),
        password: elements.password.value.trim(),
      }),
    });
    state.user = payload.user;
    renderAppView();
    setMessage(elements.loginMessage, "Login successful.", "success");

    if (state.user.role === "staff") {
      elements.staffForm.reset();
      elements.staffCollectionDate.value = todayIsoDate();
      updateStaffRooms();
    }
    if (state.user.role === "operator") {
      elements.operatorForm.reset();
      updateProcessingSubtype();
      updateOperatorMode();
      await Promise.all([loadOperatorCollections(), loadWetProcessingStatus()]);
    }
    if (state.user.role === "admin") {
      await loadDashboard();
    }
  } catch (error) {
    setMessage(elements.loginMessage, error.message, "error");
  }
}

async function handleLogout() {
  await request("/api/logout", { method: "POST", body: JSON.stringify({}) });
  state.user = null;
  renderAppView();
  setMessage(elements.loginMessage, "You have been logged out.", "success");
  setMessage(elements.staffMessage, "");
  setMessage(elements.operatorMessage, "");
  setMessage(elements.dashboardMessage, "");
}

async function handleStaffSubmit(event) {
  event.preventDefault();
  setMessage(elements.staffMessage, "Saving collection entry...");
  try {
    await request("/api/staff-collections", {
      method: "POST",
      body: JSON.stringify({
        housingBlock: elements.staffHousingBlock.value,
        roomNumber: elements.staffRoomNumber.value,
        collectionDate: elements.staffCollectionDate.value,
      }),
    });
    elements.staffForm.reset();
    elements.staffCollectionDate.value = todayIsoDate();
    updateStaffRooms();
    setMessage(elements.staffMessage, "Housing collection marked successfully.", "success");
  } catch (error) {
    setMessage(elements.staffMessage, error.message, "error");
  }
}

async function loadOperatorCollections() {
  const payload = await request("/api/operator/collections", { method: "GET" });
  renderOperatorCollections(payload.collections);
}

async function loadWetProcessingStatus() {
  const payload = await request("/api/wet-processing-status", { method: "GET" });
  renderWetStatus(payload);
}

async function handleOperatorSubmit(event) {
  event.preventDefault();
  setMessage(elements.operatorMessage, "Saving operator entry...");
  const isCompost = elements.operatorMode.value === "compost";
  try {
    if (isCompost) {
      await request("/api/wet-processing-updates", {
        method: "POST",
        body: JSON.stringify({
          compostQuantity: elements.compostQuantity.value,
        }),
      });
      await loadWetProcessingStatus();
      elements.compostQuantity.value = "";
      updateBiogasPreview();
      setMessage(elements.operatorMessage, "Compost update saved successfully.", "success");
    } else {
      await request("/api/processing-entries", {
        method: "POST",
        body: JSON.stringify({
          collectionId: elements.collectionSelect.value,
          wasteCategory: elements.processingCategory.value,
          wasteSubtype: elements.processingSubtype.value,
          quantity: elements.processingQuantity.value,
        }),
      });
      elements.operatorForm.reset();
      updateOperatorMode();
      updateProcessingSubtype();
      await Promise.all([loadOperatorCollections(), loadWetProcessingStatus()]);
      setMessage(elements.operatorMessage, "Segregation entry saved successfully.", "success");
    }
  } catch (error) {
    setMessage(elements.operatorMessage, error.message, "error");
  }
}

function renderDashboard(data) {
  const metrics = [
    ["Collections Today", `${data.metrics.collectionsToday}`],
    ["Processed Entries Today", `${data.metrics.processedEntriesToday}`],
    ["Total Processed Today", formatKg(data.metrics.totalProcessedToday)],
    ["Dry Waste Today", formatKg(data.metrics.dryWasteToday)],
    ["Wet Waste Today", formatKg(data.metrics.wetWasteToday)],
  ];

  elements.metricsGrid.innerHTML = "";
  metrics.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "metric-card";
    card.innerHTML = `<p class="metric-label">${label}</p><p class="metric-value">${value}</p>`;
    elements.metricsGrid.appendChild(card);
  });

  elements.breakdownList.innerHTML = "";
  if (data.breakdown.length === 0) {
    elements.breakdownList.innerHTML = '<p class="muted-text">No operator segregation entries saved yet.</p>';
  } else {
    data.breakdown.forEach((item) => {
      const block = document.createElement("article");
      block.className = "breakdown-item";
      block.innerHTML = `
        <strong>${item.wasteCategory}</strong>
        <p>${formatKg(item.totalWeight)} recorded</p>
        <p class="muted-text">${item.entriesCount} entries • ${item.sharePercent}% share</p>
      `;
      elements.breakdownList.appendChild(block);
    });
  }

  elements.wetProcessingPanel.innerHTML = "";
  const wetCards = [
    ["Total Wet Processed", formatKg(data.wetProcessing.totalWetProcessed)],
    [
      "Latest Compost",
      data.wetProcessing.latestUpdate ? formatKg(data.wetProcessing.latestUpdate.compostQuantity) : "No update",
    ],
    [
      "Latest Biogas",
      data.wetProcessing.latestUpdate ? formatKg(data.wetProcessing.latestUpdate.biogasQuantity) : "No update",
    ],
  ];
  wetCards.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "processing-card";
    card.innerHTML = `<p class="metric-label">${label}</p><p class="metric-value">${value}</p>`;
    elements.wetProcessingPanel.appendChild(card);
  });

  elements.blockAnalyticsPanel.innerHTML = "";
  if (data.blockAnalytics.length === 0) {
    elements.blockAnalyticsPanel.innerHTML = '<p class="muted-text">No block analytics available yet.</p>';
  } else {
    const maxWeight = Math.max(...data.blockAnalytics.map((item) => item.processedWeight), 1);
    data.blockAnalytics.forEach((item) => {
      const card = document.createElement("article");
      card.className = "analytics-item";
      const width = Math.max((item.processedWeight / maxWeight) * 100, 4);
      card.innerHTML = `
        <div class="analytics-head">
          <strong>${item.housingBlock}</strong>
          <span>${formatKg(item.processedWeight)}</span>
        </div>
        <div class="analytics-bar"><span style="width:${width}%"></span></div>
        <p class="muted-text">${item.collectionsCount} collections marked</p>
      `;
      elements.blockAnalyticsPanel.appendChild(card);
    });
  }

  elements.operatorAnalyticsPanel.innerHTML = "";
  if (data.operatorAnalytics.length === 0) {
    elements.operatorAnalyticsPanel.innerHTML = '<p class="muted-text">No operator analytics available yet.</p>';
  } else {
    const maxWeight = Math.max(...data.operatorAnalytics.map((item) => item.totalWeight), 1);
    data.operatorAnalytics.forEach((item) => {
      const card = document.createElement("article");
      card.className = "analytics-item";
      const width = Math.max((item.totalWeight / maxWeight) * 100, 4);
      card.innerHTML = `
        <div class="analytics-head">
          <strong>${item.employeeId}</strong>
          <span>${formatKg(item.totalWeight)}</span>
        </div>
        <div class="analytics-bar"><span style="width:${width}%"></span></div>
        <p class="muted-text">${item.entriesCount} operator entries</p>
      `;
      elements.operatorAnalyticsPanel.appendChild(card);
    });
  }

  elements.trendAnalyticsPanel.innerHTML = "";
  if (data.trendAnalytics.length === 0) {
    elements.trendAnalyticsPanel.innerHTML = '<p class="muted-text">No trend data available yet.</p>';
  } else {
    const maxTrend = Math.max(...data.trendAnalytics.map((item) => item.totalWeight), 1);
    data.trendAnalytics.forEach((item) => {
      const row = document.createElement("div");
      row.className = "trend-row";
      row.innerHTML = `
        <span class="trend-date">${item.date}</span>
        <div class="trend-bar"><span style="width:${Math.max((item.totalWeight / maxTrend) * 100, 4)}%"></span></div>
        <span class="trend-value">${formatKg(item.totalWeight)}</span>
      `;
      elements.trendAnalyticsPanel.appendChild(row);
    });
  }

  elements.recentCollectionsBody.innerHTML = "";
  if (data.recentCollections.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="5" class="muted-text">No staff collections recorded yet.</td>';
    elements.recentCollectionsBody.appendChild(row);
  } else {
    data.recentCollections.forEach((entry) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${entry.timestamp.replace("T", " ")}</td>
        <td>${entry.employeeId}</td>
        <td>${entry.housingBlock}</td>
        <td>${entry.roomNumber}</td>
        <td>${entry.collectionDate}</td>
      `;
      elements.recentCollectionsBody.appendChild(row);
    });
  }

  elements.recentProcessingBody.innerHTML = "";
  if (data.recentProcessingEntries.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="7" class="muted-text">No operator entries recorded yet.</td>';
    elements.recentProcessingBody.appendChild(row);
  } else {
    data.recentProcessingEntries.forEach((entry) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${entry.timestamp.replace("T", " ")}</td>
        <td>${entry.employeeId}</td>
        <td>${entry.wasteCategory}</td>
        <td>${entry.wasteSubtype}</td>
        <td>${entry.housingBlock}</td>
        <td>${entry.roomNumber}</td>
        <td>${formatKg(entry.quantity)}</td>
      `;
      elements.recentProcessingBody.appendChild(row);
    });
  }
}

async function loadDashboard() {
  setMessage(elements.dashboardMessage, "Loading dashboard...");
  try {
    const payload = await request("/api/dashboard", { method: "GET" });
    renderDashboard(payload);
    setMessage(elements.dashboardMessage, "Dashboard updated.", "success");
  } catch (error) {
    setMessage(elements.dashboardMessage, error.message, "error");
  }
}

elements.loginForm.addEventListener("submit", handleLogin);
elements.logoutButton.addEventListener("click", handleLogout);
elements.staffForm.addEventListener("submit", handleStaffSubmit);
elements.staffHousingBlock.addEventListener("change", updateStaffRooms);
elements.operatorForm.addEventListener("submit", handleOperatorSubmit);
elements.operatorMode.addEventListener("change", updateOperatorMode);
elements.processingCategory.addEventListener("change", updateProcessingSubtype);
elements.compostQuantity.addEventListener("input", updateBiogasPreview);
elements.refreshDashboardButton.addEventListener("click", loadDashboard);

elements.credentialChips.forEach((chip) => {
  chip.addEventListener("click", () => {
    elements.username.value = chip.dataset.username || "";
    elements.password.value = chip.dataset.password || "";
  });
});

bootstrap().catch((error) => {
  setMessage(elements.loginMessage, error.message || "Unable to load the app.", "error");
});

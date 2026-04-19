const state = {
  config: null,
  user: null,
  wetProcessingStatus: null,
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
  entryTabButton: document.getElementById("entryTabButton"),
  dashboardTabButton: document.getElementById("dashboardTabButton"),
  refreshDashboardButton: document.getElementById("refreshDashboardButton"),
  entrySection: document.getElementById("entrySection"),
  dashboardSection: document.getElementById("dashboardSection"),
  entryForm: document.getElementById("entryForm"),
  wasteCategory: document.getElementById("wasteCategory"),
  wetActionContainer: document.getElementById("wetActionContainer"),
  wetAction: document.getElementById("wetAction"),
  collectionFields: document.getElementById("collectionFields"),
  wetUpdateSection: document.getElementById("wetUpdateSection"),
  dryTypeField: document.getElementById("dryTypeField"),
  sourceLocationField: document.getElementById("sourceLocationField"),
  sourceLocationLabel: document.getElementById("sourceLocationLabel"),
  housingBlockField: document.getElementById("housingBlockField"),
  roomNumberField: document.getElementById("roomNumberField"),
  hazardousTypeField: document.getElementById("hazardousTypeField"),
  hazardousDates: document.getElementById("hazardousDates"),
  quantityField: document.getElementById("quantityField"),
  wasteSubtype: document.getElementById("wasteSubtype"),
  sourceLocation: document.getElementById("sourceLocation"),
  housingBlock: document.getElementById("housingBlock"),
  roomNumber: document.getElementById("roomNumber"),
  hazardousSubtype: document.getElementById("hazardousSubtype"),
  startDate: document.getElementById("startDate"),
  endDate: document.getElementById("endDate"),
  quantity: document.getElementById("quantity"),
  compostQuantity: document.getElementById("compostQuantity"),
  biogasQuantity: document.getElementById("biogasQuantity"),
  wetTotalValue: document.getElementById("wetTotalValue"),
  wetCompostValue: document.getElementById("wetCompostValue"),
  wetBiogasValue: document.getElementById("wetBiogasValue"),
  submitButton: document.getElementById("submitButton"),
  entryMessage: document.getElementById("entryMessage"),
  metricsGrid: document.getElementById("metricsGrid"),
  breakdownList: document.getElementById("breakdownList"),
  wetProcessingPanel: document.getElementById("wetProcessingPanel"),
  recentEntriesBody: document.getElementById("recentEntriesBody"),
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

function renderAppView() {
  const isAuthenticated = Boolean(state.user);
  elements.loginView.classList.toggle("hidden", isAuthenticated);
  elements.appView.classList.toggle("hidden", !isAuthenticated);

  if (!isAuthenticated) {
    return;
  }

  elements.welcomeLine.textContent = `Welcome, ${state.user.employee_id}`;
  elements.roleLine.textContent =
    state.user.role === "admin"
      ? "Role: Administrator"
      : "Role: Sanitation staff";

  const isAdmin = state.user.role === "admin";
  elements.dashboardTabButton.classList.toggle("hidden", !isAdmin);
  showTab("entry");
}

function showTab(tabName) {
  const showDashboard = tabName === "dashboard";
  elements.entrySection.classList.toggle("hidden", showDashboard);
  elements.dashboardSection.classList.toggle("hidden", !showDashboard);
  elements.entryTabButton.classList.toggle("active", !showDashboard);
  elements.dashboardTabButton.classList.toggle("active", showDashboard);
}

function populateStaticOptions() {
  populateSelect(elements.wasteCategory, state.config.wasteCategories, "Select waste category");
  populateSelect(elements.wasteSubtype, state.config.dryWasteTypes, "Select dry waste type");
  populateSelect(elements.sourceLocation, [], "Select location");
  populateSelect(elements.housingBlock, state.config.blocks, "Select academic block");
  populateSelect(elements.roomNumber, [], "Select room number");
  populateSelect(elements.hazardousSubtype, state.config.hazardousWasteTypes, "Select hazardous waste type");
  elements.roomNumber.disabled = true;
}

function clearCollectionInputs() {
  elements.wasteSubtype.value = "";
  elements.sourceLocation.value = "";
  elements.housingBlock.value = "";
  elements.roomNumber.value = "";
  populateSelect(elements.roomNumber, [], "Select room number");
  elements.roomNumber.disabled = true;
  elements.hazardousSubtype.value = "";
  elements.startDate.value = "";
  elements.endDate.value = "";
  elements.quantity.value = "";
}

function setRequired(element, required) {
  element.required = required;
}

function updateFormForCategory() {
  const category = elements.wasteCategory.value;
  const isWet = category === "Wet Waste";
  const isDry = category === "Dry Waste";
  const isHazardous = category === "Hazardous Waste";
  const isWetWeekly = isWet && elements.wetAction.value === "weekly_update";
  const showCollection = Boolean(category) && !isWetWeekly;

  elements.wetActionContainer.classList.toggle("hidden", !isWet);
  elements.collectionFields.classList.toggle("hidden", !showCollection);
  elements.wetUpdateSection.classList.toggle("hidden", !isWetWeekly);
  elements.submitButton.classList.toggle("hidden", !category);

  elements.dryTypeField.classList.toggle("hidden", !isDry);
  elements.sourceLocationField.classList.toggle("hidden", !(isDry || (isWet && !isWetWeekly)));
  elements.housingBlockField.classList.toggle("hidden", !showCollection);
  elements.roomNumberField.classList.toggle("hidden", !showCollection);
  elements.hazardousTypeField.classList.toggle("hidden", !isHazardous);
  elements.hazardousDates.classList.toggle("hidden", !isHazardous);
  elements.quantityField.classList.toggle("hidden", !showCollection);

  setRequired(elements.wasteSubtype, isDry);
  setRequired(elements.sourceLocation, isDry || (isWet && !isWetWeekly));
  setRequired(elements.housingBlock, showCollection);
  setRequired(elements.roomNumber, showCollection);
  setRequired(elements.hazardousSubtype, isHazardous);
  setRequired(elements.startDate, isHazardous);
  setRequired(elements.endDate, isHazardous);
  setRequired(elements.quantity, showCollection);

  if (isDry) {
    populateSelect(elements.sourceLocation, state.config.dryWasteLocations, "Select dry waste location");
    elements.sourceLocationLabel.textContent = "Dry Waste Location";
  } else if (isWet && !isWetWeekly) {
    populateSelect(elements.sourceLocation, state.config.wetWasteLocations, "Select wet waste location");
    elements.sourceLocationLabel.textContent = "Wet Waste Location";
  } else if (!isDry && !isWet) {
    populateSelect(elements.sourceLocation, [], "Select location");
  }

  elements.submitButton.textContent = isWetWeekly ? "Save Weekly Update" : "Save Entry";

  if (isWetWeekly) {
    loadWetProcessingStatus();
  }
}

function updateRooms() {
  const block = elements.housingBlock.value;
  const hasBlock = Boolean(block);
  const rooms = hasBlock ? (state.config.roomsByBlock[block] || []) : [];
  populateSelect(
    elements.roomNumber,
    rooms,
    "Select room number"
  );
  elements.roomNumber.disabled = !hasBlock;
}

function renderWetProcessingStatus(status) {
  state.wetProcessingStatus = status;
  elements.wetTotalValue.textContent = formatKg(status.totalWetCollected);
  elements.wetCompostValue.textContent = status.latestUpdate
    ? formatKg(status.latestUpdate.compostQuantity)
    : formatKg(0);
  elements.wetBiogasValue.textContent = status.latestUpdate
    ? formatKg(status.latestUpdate.biogasQuantity)
    : formatKg(0);
}

async function loadWetProcessingStatus() {
  try {
    const status = await request("/api/wet-processing-status", { method: "GET" });
    renderWetProcessingStatus(status);
  } catch (error) {
    setMessage(elements.entryMessage, error.message, "error");
  }
}

function resetEntryForm() {
  elements.entryForm.reset();
  elements.wetAction.value = "normal";
  clearCollectionInputs();
  elements.compostQuantity.value = "";
  elements.biogasQuantity.value = "";
  state.wetProcessingStatus = null;
  elements.wetTotalValue.textContent = formatKg(0);
  elements.wetCompostValue.textContent = formatKg(0);
  elements.wetBiogasValue.textContent = formatKg(0);
  updateFormForCategory();
}

async function bootstrap() {
  state.config = await request("/api/config", { method: "GET" });
  populateStaticOptions();

  const session = await request("/api/session", { method: "GET" });
  state.user = session.authenticated ? session.user : null;
  renderAppView();

  if (state.user && state.user.role === "admin") {
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
    resetEntryForm();
    setMessage(elements.loginMessage, "Login successful.", "success");
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
  setMessage(elements.entryMessage, "");
  setMessage(elements.dashboardMessage, "");
}

function buildCollectionPayload() {
  const category = elements.wasteCategory.value;
  if (category === "Dry Waste") {
    return {
      wasteCategory: category,
      housingBlock: elements.housingBlock.value,
      roomNumber: elements.roomNumber.value,
      wasteSubtype: elements.wasteSubtype.value,
      sourceLocation: elements.sourceLocation.value,
      quantity: elements.quantity.value,
    };
  }

  if (category === "Wet Waste") {
    return {
      wasteCategory: category,
      housingBlock: elements.housingBlock.value,
      roomNumber: elements.roomNumber.value,
      sourceLocation: elements.sourceLocation.value,
      quantity: elements.quantity.value,
    };
  }

  return {
    wasteCategory: category,
    wasteSubtype: elements.hazardousSubtype.value,
    housingBlock: elements.housingBlock.value,
    roomNumber: elements.roomNumber.value,
    quantity: elements.quantity.value,
    startDate: elements.startDate.value,
    endDate: elements.endDate.value,
  };
}

async function handleEntrySubmit(event) {
  event.preventDefault();
  setMessage(elements.entryMessage, "Saving...");

  const isWetWeekly = elements.wasteCategory.value === "Wet Waste" && elements.wetAction.value === "weekly_update";

  try {
    if (isWetWeekly) {
      await request("/api/wet-processing-updates", {
        method: "POST",
        body: JSON.stringify({
          compostQuantity: elements.compostQuantity.value,
          biogasQuantity: elements.biogasQuantity.value,
        }),
      });
      await loadWetProcessingStatus();
      setMessage(elements.entryMessage, "Wet waste processing update saved successfully.", "success");
    } else {
      await request("/api/entries", {
        method: "POST",
        body: JSON.stringify(buildCollectionPayload()),
      });
      setMessage(elements.entryMessage, "Waste entry saved successfully.", "success");
    }

    if (state.user.role === "admin") {
      await loadDashboard();
    }

    if (!isWetWeekly) {
      resetEntryForm();
    } else {
      elements.compostQuantity.value = "";
      elements.biogasQuantity.value = "";
    }
  } catch (error) {
    setMessage(elements.entryMessage, error.message, "error");
  }
}

function renderDashboard(data) {
  const metrics = [
    ["Total Waste Today", formatKg(data.metrics.totalWasteToday)],
    ["Wet Waste Today", formatKg(data.metrics.wetWasteToday)],
    ["Dry Waste Today", formatKg(data.metrics.dryWasteToday)],
    ["Hazardous Waste Today", formatKg(data.metrics.hazardousWasteToday)],
    ["Entries Today", `${data.metrics.entriesToday}`],
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
    elements.breakdownList.innerHTML = '<p class="muted-text">No waste entries saved yet.</p>';
  } else {
    data.breakdown.forEach((item) => {
      const block = document.createElement("article");
      block.className = "breakdown-item";
      block.innerHTML = `
        <strong>${item.wasteCategory}</strong>
        <p>${formatKg(item.totalWeight)} collected</p>
        <p class="muted-text">${item.entriesCount} entries</p>
      `;
      elements.breakdownList.appendChild(block);
    });
  }

  elements.wetProcessingPanel.innerHTML = "";
  const wetStatus = data.wetProcessing;
  const cards = [
    ["Total Wet Waste Logged", formatKg(wetStatus.totalWetCollected)],
    [
      "Latest Compost Allocation",
      wetStatus.latestUpdate ? formatKg(wetStatus.latestUpdate.compostQuantity) : "No update",
    ],
    [
      "Latest Biogas Allocation",
      wetStatus.latestUpdate ? formatKg(wetStatus.latestUpdate.biogasQuantity) : "No update",
    ],
    ["Pending Allocation", formatKg(wetStatus.pendingAllocation)],
  ];
  cards.forEach(([label, value]) => {
    const card = document.createElement("article");
    card.className = "processing-card";
    card.innerHTML = `<p class="metric-label">${label}</p><p class="metric-value">${value}</p>`;
    elements.wetProcessingPanel.appendChild(card);
  });

  if (wetStatus.latestUpdate) {
    const note = document.createElement("article");
    note.className = "processing-card";
    note.innerHTML = `
      <p class="metric-label">Latest update record</p>
      <p>${wetStatus.latestUpdate.employeeId}</p>
      <p class="muted-text">${wetStatus.latestUpdate.timestamp.replace("T", " ")}</p>
    `;
    elements.wetProcessingPanel.appendChild(note);
  }

  elements.recentEntriesBody.innerHTML = "";
  if (data.recentEntries.length === 0) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="6" class="muted-text">No recent entries available.</td>';
    elements.recentEntriesBody.appendChild(row);
    return;
  }

  data.recentEntries.forEach((entry) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${entry.timestamp.replace("T", " ")}</td>
      <td>${entry.employeeId}</td>
      <td>${entry.wasteCategory}</td>
      <td>${entry.wasteSubtype || "Normal Entry"}</td>
      <td>${entry.location}</td>
      <td>${formatKg(entry.quantity)}</td>
    `;
    elements.recentEntriesBody.appendChild(row);
  });
}

async function loadDashboard() {
  if (!state.user || state.user.role !== "admin") {
    return;
  }
  setMessage(elements.dashboardMessage, "Loading dashboard...");
  try {
    const data = await request("/api/dashboard", { method: "GET" });
    renderDashboard(data);
    setMessage(elements.dashboardMessage, "Dashboard updated.", "success");
  } catch (error) {
    setMessage(elements.dashboardMessage, error.message, "error");
  }
}

elements.loginForm.addEventListener("submit", handleLogin);
elements.logoutButton.addEventListener("click", handleLogout);
elements.entryForm.addEventListener("submit", handleEntrySubmit);
elements.housingBlock.addEventListener("change", updateRooms);
elements.wasteCategory.addEventListener("change", () => {
  clearCollectionInputs();
  elements.compostQuantity.value = "";
  elements.biogasQuantity.value = "";
  updateFormForCategory();
});
elements.wetAction.addEventListener("change", updateFormForCategory);
elements.entryTabButton.addEventListener("click", () => showTab("entry"));
elements.dashboardTabButton.addEventListener("click", async () => {
  showTab("dashboard");
  await loadDashboard();
});
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

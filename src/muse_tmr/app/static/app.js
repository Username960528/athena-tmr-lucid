const stateLabel = document.querySelector("#status-line");
const sourceLabel = document.querySelector("#source-label");
const deviceSummary = document.querySelector("#device-summary");
const errorBox = document.querySelector("#error-box");
const scanButton = document.querySelector("#scan-button");
const connectButton = document.querySelector("#connect-button");
const disconnectButton = document.querySelector("#disconnect-button");

const stateText = {
  disconnected: "Disconnected",
  scanning: "Scanning",
  connecting: "Connecting",
  connected: "Connected",
  error: "Error"
};

async function requestJson(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function renderState(state) {
  const connection = state.connection_state || "disconnected";
  stateLabel.textContent = stateText[connection] || connection;
  sourceLabel.textContent = state.source || "unknown";

  document.querySelectorAll(".status-meter span").forEach((item) => {
    item.classList.toggle("active", item.dataset.state === connection);
    item.classList.toggle("good", connection === "connected" && item.dataset.state === "connected");
  });

  const device = state.device;
  if (device && (device.name || device.address)) {
    deviceSummary.textContent = [device.name, device.address].filter(Boolean).join(" | ");
  } else if (state.devices && state.devices.length > 0) {
    deviceSummary.textContent = `${state.devices.length} headset candidate found`;
  } else {
    deviceSummary.textContent = "No headset selected";
  }

  errorBox.hidden = !state.error_message;
  errorBox.textContent = state.error_message || "";
  connectButton.classList.toggle("primary", connection !== "connected");
  connectButton.disabled = connection === "connecting";
  scanButton.disabled = connection === "scanning" || connection === "connecting";
  disconnectButton.disabled = connection === "disconnected";
}

async function refreshState() {
  renderState(await requestJson("/api/muse/state"));
}

scanButton.addEventListener("click", async () => {
  renderState({ connection_state: "scanning", source: sourceLabel.textContent });
  renderState(await requestJson("/api/muse/scan", { method: "POST" }));
});

connectButton.addEventListener("click", async () => {
  renderState({ connection_state: "connecting", source: sourceLabel.textContent });
  renderState(await requestJson("/api/muse/connect", { method: "POST" }));
});

disconnectButton.addEventListener("click", async () => {
  renderState(await requestJson("/api/muse/disconnect", { method: "POST" }));
});

refreshState();
window.setInterval(refreshState, 2000);

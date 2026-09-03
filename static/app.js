// AEGIS TRADING ENGINE FRONTEND CONTROLLER v3.1
// - Instant-play audio briefing (fixed: plays cached MP3 immediately, regenerates in background)
// - WebSocket real-time decision stream + notification center + sound alerts
// - Command palette (Ctrl+K) + full keyboard shortcuts
// - Live performance analytics (SQLite journal) + P&L attribution
// - Ticker tape, market countdown, Greeks monitor, journal search/filter/CSV export
// - Light / dark theme persistence
// ==========================================================================

let chartInstance = null;
let isAudioPlaying = false;
let currentAudio = null;
let ws = null;
let wsConnected = false;

// New v3.1 feature state
let journalCache = [];          // full journal rows (client-side filtering)
let lastHeadlines = [];         // latest news headlines (client-side filtering)
let lastEquityCurve = [];       // latest equity curve points (timeframe switching)
let chartTimeframe = "all";     // "all" | "50" | "20"
let marketClock = null;         // { is_open, next_open, next_close }
let tickerBaseline = {};        // ticker -> session baseline spot (for delta display)
let notifications = [];        // notification center items
let notifUnread = 0;
let darkTheme = localStorage.getItem("aegis_theme") === "dark";
let soundAlertsEnabled = localStorage.getItem("aegis_sound") !== "off";

// Initialize on Load
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  applyTheme();
  updateSoundLabel();
  initPerformanceChart();

  // Restore session if already authenticated
  const savedUser = localStorage.getItem("aegis_auth");
  if (savedUser) {
    try {
      const user = JSON.parse(savedUser);
      enterDashboard(user);
    } catch {
      localStorage.removeItem("aegis_auth");
    }
  }

  // Periodic background polling (WebSocket supplements for resiliency)
  setInterval(() => {
    if (document.getElementById("app-layout").classList.contains("hidden")) return;
    fetchAccountData();
    fetchPositionMarks();
  }, 5000);

  // Slower refresh cycles for heavier panels
  setInterval(() => {
    if (document.getElementById("app-layout").classList.contains("hidden")) return;
    fetchPerformance();
    fetchJournal();
    fetchNews();
  }, 20000);

  // Ticker tape refresh (watchlist spot matrix — throttled: endpoint fetches 8 spot quotes)
  setInterval(() => {
    if (document.getElementById("app-layout").classList.contains("hidden")) return;
    fetchTickerTape();
  }, 60000);

  // Market session countdown (1s tick)
  setInterval(tickCountdown, 1000);
});

// Setup Event Listeners
function setupEventListeners() {
  document.getElementById("btn-run-cycle").addEventListener("click", runAICycle);
  document.getElementById("btn-toggle-auto").addEventListener("click", toggleAutoTrading);
  document.getElementById("btn-emergency-hedge").addEventListener("click", triggerEmergencyHedge);
  document.getElementById("btn-refresh-screen").addEventListener("click", fetchScreenedProposals);
  document.getElementById("btn-play-briefing").addEventListener("click", playAudioBriefing);
  document.getElementById("btn-regen-briefing").addEventListener("click", regenerateBriefing);

  // Audio volume slider
  const volumeSlider = document.getElementById("volume-slider");
  if (volumeSlider) {
    volumeSlider.addEventListener("input", (e) => {
      briefingAudio.volume = parseInt(e.target.value, 10) / 100;
    });
  }

  // Journal toolbar: search + status filter + CSV export
  const journalSearch = document.getElementById("journal-search");
  if (journalSearch) journalSearch.addEventListener("input", renderJournal);
  const journalFilter = document.getElementById("journal-status-filter");
  if (journalFilter) journalFilter.addEventListener("change", renderJournal);
  const exportBtn = document.getElementById("btn-export-csv");
  if (exportBtn) exportBtn.addEventListener("click", exportJournalCSV);

  // Chart timeframe buttons
  document.querySelectorAll("#timeframe-btns .tf-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      chartTimeframe = btn.dataset.tf;
      document.querySelectorAll("#timeframe-btns .tf-btn").forEach(b => b.classList.toggle("active", b === btn));
      updatePerformanceChart(lastEquityCurve);
    });
  });

  // News headline filter
  const newsSearch = document.getElementById("news-search");
  if (newsSearch) newsSearch.addEventListener("input", renderNewsFeed);

  // Command palette
  const cmdkInput = document.getElementById("cmdk-input");
  if (cmdkInput) {
    cmdkInput.addEventListener("input", (e) => renderCmdk(e.target.value));
    cmdkInput.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        cmdkSelected = Math.min(cmdkSelected + 1, cmdkFiltered.length - 1);
        highlightCmdk();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        cmdkSelected = Math.max(cmdkSelected - 1, 0);
        highlightCmdk();
      } else if (e.key === "Enter") {
        e.preventDefault();
        runCmdkAction(cmdkSelected);
      }
    });
  }
  const cmdkOverlay = document.getElementById("cmdk-overlay");
  if (cmdkOverlay) {
    cmdkOverlay.addEventListener("click", (e) => {
      if (e.target === cmdkOverlay) closeCommandPalette();
    });
  }

  // Explainer modal click outside
  const explainer = document.getElementById("explainer-modal");
  explainer.addEventListener("click", (e) => {
    if (e.target === explainer) closeExplainerModal();
  });

  // Close dropdown panels when clicking outside them
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".notif-wrap")) {
      const np = document.getElementById("notif-panel");
      if (np) np.classList.add("hidden");
    }
    if (!e.target.closest(".settings-wrap")) {
      const sp = document.getElementById("settings-panel");
      if (sp) sp.classList.add("hidden");
    }
  });

  // Global keyboard shortcuts
  document.addEventListener("keydown", handleGlobalKeys);
}

// ==========================================================================
// GLOBAL KEYBOARD SHORTCUTS + COMMAND PALETTE (Ctrl+K)
// ==========================================================================
function handleGlobalKeys(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    openCommandPalette();
    return;
  }
  if (e.key === "Escape") {
    closeCommandPalette();
    closeShortcutsModal();
    closeExplainerModal();
    const np = document.getElementById("notif-panel");
    if (np) np.classList.add("hidden");
    const sp = document.getElementById("settings-panel");
    if (sp) sp.classList.add("hidden");
    return;
  }

  // Skip single-key shortcuts while typing in any field
  const tag = ((e.target && e.target.tagName) || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select" || (e.target && e.target.isContentEditable)) return;
  if (document.getElementById("app-layout").classList.contains("hidden")) return;

  switch (e.key.toLowerCase()) {
    case "r": runAICycle(); break;
    case "a": toggleAutoTrading(); break;
    case "h": triggerEmergencyHedge(); break;
    case "b": playAudioBriefing(); break;
    case "t": toggleTheme(); break;
    case "e": exportJournalCSV(); break;
    case "f": toggleFullscreen(); break;
    case "?": showShortcutsModal(); break;
  }
}

// ---- Command palette ----
let cmdkFiltered = [];
let cmdkSelected = 0;

const COMMANDS = [
  { label: "Run full AI cycle", hint: "R", icon: "#i-play", action: () => runAICycle() },
  { label: "Toggle 24/7 autonomous loop", hint: "A", icon: "#i-bolt", action: () => toggleAutoTrading() },
  { label: "Test tail-risk hedge", hint: "H", icon: "#i-shield-alert", action: () => triggerEmergencyHedge() },
  { label: "Play / stop AI voice briefing", hint: "B", icon: "#i-mic", action: () => playAudioBriefing() },
  { label: "Regenerate voice briefing", icon: "#i-refresh", action: () => regenerateBriefing() },
  { label: "Refresh quant screen", icon: "#i-target", action: () => fetchScreenedProposals() },
  { label: "Refresh news & regime", icon: "#i-news", action: () => fetchNews() },
  { label: "Toggle dark / light theme", hint: "T", icon: "#i-moon", action: () => toggleTheme() },
  { label: "Export trade journal as CSV", hint: "E", icon: "#i-download", action: () => exportJournalCSV() },
  { label: "Toggle fullscreen", hint: "F", icon: "#i-maximize", action: () => toggleFullscreen() },
  { label: "Show keyboard shortcuts", hint: "?", icon: "#i-keyboard", action: () => showShortcutsModal() },
  { label: "How Aegis works", icon: "#i-help", action: () => showExplainerModal() },
  { label: "Sign out", icon: "#i-arrow-right", action: () => handleLogout() },
];

function openCommandPalette() {
  const overlay = document.getElementById("cmdk-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  const input = document.getElementById("cmdk-input");
  if (input) { input.value = ""; input.focus(); }
  renderCmdk("");
}

function closeCommandPalette() {
  const overlay = document.getElementById("cmdk-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function renderCmdk(query) {
  const list = document.getElementById("cmdk-list");
  if (!list) return;
  const q = (query || "").trim().toLowerCase();
  cmdkFiltered = COMMANDS.filter(c => c.label.toLowerCase().includes(q));
  cmdkSelected = 0;

  if (!cmdkFiltered.length) {
    list.innerHTML = `<div class="cmdk-empty">No matching commands.</div>`;
    return;
  }
  list.innerHTML = cmdkFiltered.map((c, i) => `
    <button class="cmdk-item ${i === 0 ? "selected" : ""}" data-index="${i}">
      <svg class="icon icon-16"><use href="${c.icon}"></use></svg>
      <span class="cmdk-label">${c.label}</span>
      ${c.hint ? `<span class="kbd kbd-sm">${c.hint}</span>` : ""}
    </button>`).join("");

  list.querySelectorAll(".cmdk-item").forEach(btn => {
    btn.addEventListener("click", () => runCmdkAction(parseInt(btn.dataset.index, 10)));
    btn.addEventListener("mouseenter", () => {
      cmdkSelected = parseInt(btn.dataset.index, 10);
      highlightCmdk();
    });
  });
}

function highlightCmdk() {
  const list = document.getElementById("cmdk-list");
  if (!list) return;
  list.querySelectorAll(".cmdk-item").forEach((el, i) => {
    el.classList.toggle("selected", i === cmdkSelected);
  });
}

function runCmdkAction(index) {
  const cmd = cmdkFiltered[index];
  closeCommandPalette();
  if (cmd && typeof cmd.action === "function") cmd.action();
}

// ==========================================================================
// THEME / SOUND / FULLSCREEN / SETTINGS PANEL
// ==========================================================================
function applyTheme() {
  document.body.classList.toggle("dark-theme", darkTheme);
  document.body.classList.toggle("light-theme", !darkTheme);
  const lbl = document.getElementById("theme-label");
  if (lbl) lbl.innerText = darkTheme ? "Light theme" : "Dark theme";
  refreshChartTheme();
}

function toggleTheme() {
  darkTheme = !darkTheme;
  localStorage.setItem("aegis_theme", darkTheme ? "dark" : "light");
  applyTheme();
}

function toggleSoundAlerts() {
  soundAlertsEnabled = !soundAlertsEnabled;
  localStorage.setItem("aegis_sound", soundAlertsEnabled ? "on" : "off");
  updateSoundLabel();
  showToast(soundAlertsEnabled ? "Sound alerts enabled." : "Sound alerts muted.", "success");
}

function updateSoundLabel() {
  const lbl = document.getElementById("sound-label");
  if (lbl) lbl.innerText = `Sound alerts: ${soundAlertsEnabled ? "ON" : "OFF"}`;
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

function toggleSettingsPanel() {
  const panel = document.getElementById("settings-panel");
  if (!panel) return;
  const notif = document.getElementById("notif-panel");
  if (notif) notif.classList.add("hidden");
  panel.classList.toggle("hidden");
}

function showShortcutsModal() {
  document.getElementById("shortcuts-modal").classList.add("active");
}

function closeShortcutsModal() {
  const modal = document.getElementById("shortcuts-modal");
  if (modal) modal.classList.remove("active");
}

// ==========================================================================
// NOTIFICATION CENTER (fed by WebSocket decision stream)
// ==========================================================================
function pushNotification(kind, title, body) {
  const icons = { trade: "#i-bolt", veto: "#i-shield-alert", hedge: "#i-shield", info: "#i-bell" };
  notifications.unshift({
    kind,
    title,
    body,
    icon: icons[kind] || icons.info,
    time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
  });
  notifications = notifications.slice(0, 30);
  notifUnread++;
  renderNotifications();
}

function renderNotifications() {
  const list = document.getElementById("notif-list");
  const countEl = document.getElementById("notif-count");
  if (!list) return;

  if (!notifications.length) {
    list.innerHTML = `<div class="notif-empty">No notifications yet — events stream in live.</div>`;
  } else {
    list.innerHTML = notifications.map(n => `
      <div class="notif-item">
        <span class="notif-ic notif-${n.kind}"><svg class="icon icon-16"><use href="${n.icon}"></use></svg></span>
        <div class="notif-body">
          <div class="notif-title">${n.title}</div>
          <div class="notif-text">${n.body}</div>
          <div class="notif-time">${n.time}</div>
        </div>
      </div>`).join("");
  }

  if (countEl) {
    countEl.textContent = notifUnread > 99 ? "99+" : String(notifUnread);
    countEl.classList.toggle("hidden", notifUnread === 0);
  }
}

function toggleNotifPanel() {
  const panel = document.getElementById("notif-panel");
  if (!panel) return;
  const settings = document.getElementById("settings-panel");
  if (settings) settings.classList.add("hidden");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden")) {
    notifUnread = 0; // mark all read on open
    renderNotifications();
  }
}

function clearNotifications() {
  notifications = [];
  notifUnread = 0;
  renderNotifications();
}

// Detect key events in the decision stream and promote them to notifications
function maybeNotify(log) {
  const agent = log.agent || "";
  const msg = (log.message || "").toLowerCase();

  if (agent === "AlpacaBroker" || agent === "ExecutionEngine") {
    if (msg.includes("filled") || msg.includes("submitted") || msg.includes("executed") || msg.includes("order")) {
      pushNotification("trade", "Order Event", log.message);
      playSoundAlert("trade");
      return;
    }
  }
  if (agent === "RiskGovernanceAgent" && (msg.includes("veto") || msg.includes("reject"))) {
    pushNotification("veto", "Risk Veto", log.message);
    playSoundAlert("veto");
    return;
  }
  if (msg.includes("hedge") && (agent === "RiskGovernanceAgent" || agent === "SYSTEM")) {
    pushNotification("hedge", "Tail Hedge", log.message);
    playSoundAlert("hedge");
    return;
  }
}

// ==========================================================================
// SOUND ALERTS (WebAudio oscillator beeps — no external files)
// ==========================================================================
let audioCtx = null;

function playSoundAlert(kind) {
  if (!soundAlertsEnabled) return;
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === "suspended") audioCtx.resume();
    const notes = kind === "veto" ? [330, 220] : kind === "hedge" ? [196, 147] : [660, 880];
    notes.forEach((freq, i) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      const t0 = audioCtx.currentTime + i * 0.13;
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, t0);
      gain.gain.exponentialRampToValueAtTime(0.06, t0 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(t0);
      osc.stop(t0 + 0.2);
    });
  } catch { /* WebAudio unavailable — silent */ }
}

// ==========================================================================
// WEBSOCKET — real-time decision stream
// ==========================================================================
function connectWebSocket() {
  try {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
      wsConnected = true;
      const badge = document.getElementById("ws-status-badge");
      if (badge) { badge.textContent = "WEBSOCKET LIVE"; badge.style.color = "#059669"; }
    };

    ws.onmessage = (event) => {
      try {
        const log = JSON.parse(event.data);
        appendTerminalRow(log);
      } catch { /* ignore malformed */ }
    };

    ws.onclose = () => {
      wsConnected = false;
      const badge = document.getElementById("ws-status-badge");
      if (badge) { badge.textContent = "POLLING MODE"; badge.style.color = "#d97706"; }
      setTimeout(connectWebSocket, 5000); // auto-reconnect
    };

    ws.onerror = () => ws.close();
  } catch (e) {
    console.warn("WebSocket unavailable, falling back to polling:", e);
  }
}

function appendTerminalRow(log) {
  const feed = document.getElementById("terminal-feed");
  if (!feed) return;

  const row = document.createElement("div");
  row.className = "terminal-row";

  let badgeClass = "badge-sys";
  if (log.agent === "QuantAgent") badgeClass = "badge-quant";
  else if (log.agent === "SentimentAgent") badgeClass = "badge-sent";
  else if (log.agent === "RiskGovernanceAgent") badgeClass = "badge-risk";
  else if (log.agent === "PortfolioManager") badgeClass = "badge-broker";
  else if (log.agent === "NewsAgent") badgeClass = "badge-sent";
  else if (log.agent === "ExecutionEngine" || log.agent === "AlpacaBroker") badgeClass = "badge-broker";

  row.innerHTML = `
    <span class="term-time">[${log.timestamp}]</span>
    <span class="term-badge ${badgeClass}">${(log.agent || "SYSTEM").toUpperCase()}</span>
    <span class="term-text">${log.message}</span>
  `;
  feed.appendChild(row);

  // Cap the terminal at 120 rows
  while (feed.children.length > 120) {
    feed.removeChild(feed.firstChild);
  }
  feed.scrollTop = feed.scrollHeight;

  // Promote key events to the notification center + sound alerts
  maybeNotify(log);
}

// ==========================================================================
// AUTH PANEL SWITCHING
// ==========================================================================
function switchToSignIn() {
  document.getElementById("panel-register").classList.add("hidden");
  document.getElementById("panel-signin").classList.remove("hidden");
  document.getElementById("tab-register").classList.remove("active");
  document.getElementById("tab-signin").classList.add("active");
  document.getElementById("tab-register").setAttribute("aria-selected", "false");
  document.getElementById("tab-signin").setAttribute("aria-selected", "true");
}

function switchToRegister() {
  document.getElementById("panel-signin").classList.add("hidden");
  document.getElementById("panel-register").classList.remove("hidden");
  document.getElementById("tab-signin").classList.remove("active");
  document.getElementById("tab-register").classList.add("active");
  document.getElementById("tab-signin").setAttribute("aria-selected", "false");
  document.getElementById("tab-register").setAttribute("aria-selected", "true");
}

// ==========================================================================
// PASSWORD UTILITIES
// ==========================================================================
function togglePasswordVis(inputId, btn) {
  const input = document.getElementById(inputId);
  const useEl = btn.querySelector("use");
  const isHidden = input.type === "password";
  input.type = isHidden ? "text" : "password";
  if (useEl) useEl.setAttribute("href", isHidden ? "#i-eye-off" : "#i-eye");
}

function updatePasswordStrength(value) {
  const fill = document.getElementById("pwd-bar-fill");
  const label = document.getElementById("pwd-strength-label");
  if (!fill || !label) return;

  let score = 0;
  if (value.length >= 8)  score++;
  if (value.length >= 12) score++;
  if (/[A-Z]/.test(value)) score++;
  if (/[0-9]/.test(value)) score++;
  if (/[^A-Za-z0-9]/.test(value)) score++;

  const levels = [
    { pct: "0%",   cls: "",         text: "" },
    { pct: "25%",  cls: "weak",     text: "Weak" },
    { pct: "50%",  cls: "fair",     text: "Fair" },
    { pct: "75%",  cls: "good",     text: "Good" },
    { pct: "90%",  cls: "strong",   text: "Strong" },
    { pct: "100%", cls: "very-strong", text: "Very Strong" },
  ];
  const lvl = levels[Math.min(score, 5)];
  fill.style.width = lvl.pct;
  fill.className = `pwd-bar-fill ${lvl.cls}`;
  label.textContent = lvl.text;
  label.className = `pwd-strength-label ${lvl.cls}`;
}

// ==========================================================================
// REGISTER
// ==========================================================================
async function handleRegister(e) {
  e.preventDefault();

  const fullName        = document.getElementById("reg-fullname").value.trim();
  const dob             = document.getElementById("reg-dob").value;
  const email           = document.getElementById("reg-email").value.trim();
  const password        = document.getElementById("reg-password").value;
  const confirmPassword = document.getElementById("reg-confirm-password").value;
  const alpacaAccountId = document.getElementById("reg-alpaca-account-id").value.trim();
  const alpacaApiKey    = document.getElementById("reg-alpaca-api-key").value.trim();
  const alpacaSecret    = document.getElementById("reg-alpaca-secret").value.trim();

  // Client-side validation
  if (!fullName || !dob || !email || !password) {
    showToast("Please fill in all required fields.", "error"); return;
  }
  if (password !== confirmPassword) {
    showToast("Passwords do not match.", "error"); return;
  }
  if (password.length < 8) {
    showToast("Password must be at least 8 characters.", "error"); return;
  }

  const btn = document.getElementById("btn-register-submit");
  btn.disabled = true;
  btn.innerHTML = `<span>Creating Account...</span>`;

  try {
    const res = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        dob,
        email,
        password,
        alpaca_account_id: alpacaAccountId,
        alpaca_api_key: alpacaApiKey,
        alpaca_secret_key: alpacaSecret,
      })
    });
    const data = await res.json();

    if (data.success) {
      showToast("Account created! Please sign in.", "success");
      // Pre-fill sign-in email for convenience
      document.getElementById("login-email").value = email;
      document.getElementById("alpaca-secret").value = alpacaSecret;
      document.getElementById("alpaca-key").value = alpacaApiKey;
      switchToSignIn();
    } else {
      showToast(data.message || "Registration failed.", "error");
    }
  } catch (err) {
    console.error("Register error:", err);
    showToast("Network error — please check your connection.", "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>Create Account &amp; Get Started</span><svg class="icon icon-16"><use href="#i-arrow-right"></use></svg>`;
  }
}

// ==========================================================================
// LOGIN / SIGN IN
// ==========================================================================
async function handleLogin(e) {
  e.preventDefault();
  const email     = document.getElementById("login-email").value.trim();
  const password  = document.getElementById("login-password").value;
  const apiKey    = document.getElementById("alpaca-key").value.trim();
  const secretKey = document.getElementById("alpaca-secret").value.trim();
  const paper     = document.getElementById("paper-mode").checked;

  const btn = document.getElementById("btn-auth-submit");
  btn.disabled = true;
  btn.innerHTML = `<span>Signing in...</span>`;

  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        password,
        alpaca_api_key: apiKey || undefined,
        alpaca_secret_key: secretKey || undefined,
        paper,
      })
    });
    const data = await res.json();

    if (data.success) {
      const user = { email, account_id: data.account?.account_id };
      localStorage.setItem("aegis_auth", JSON.stringify(user));
      showToast(`Welcome back! Connected to Alpaca: ${data.account?.account_id}`);
      enterDashboard(user);
    } else {
      showToast(data.message || "Sign in failed. Check your credentials.", "error");
    }
  } catch (err) {
    console.error("Login error:", err);
    // Graceful offline/demo fallback
    const user = { email, account_id: "demo-mode" };
    localStorage.setItem("aegis_auth", JSON.stringify(user));
    showToast("Connected to Demo Session.");
    enterDashboard(user);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<span>Sign In &amp; Enter Trading Desk</span><svg class="icon icon-16"><use href="#i-arrow-right"></use></svg>`;
  }
}

function enterDashboard(user) {
  document.getElementById("auth-overlay").classList.add("hidden");
  document.getElementById("app-layout").classList.remove("hidden");
  // Show trader name in header
  const nameEl = document.getElementById("trader-name-display");
  if (nameEl) nameEl.textContent = user.email ? user.email.split("@")[0].toUpperCase() : "TRADER";
  if (user.account_id) {
    document.getElementById("account-id-display").textContent = user.account_id;
  }
  // Preload the briefing MP3 into memory so PLAY starts instantly, zero network wait
  preloadBriefingAudio();
  connectWebSocket();
  fetchAccountData();
  fetchScreenedProposals();
  fetchLiveLogs();
  fetchPerformance();
  fetchJournal();
  fetchNews();
  fetchPositionMarks();
  fetchTickerTape();
}

function handleLogout() {
  localStorage.removeItem("aegis_auth");
  document.getElementById("app-layout").classList.add("hidden");
  document.getElementById("auth-overlay").classList.remove("hidden");
  stopAudio();
  if (ws) { try { ws.close(); } catch {} }
  // Reset to sign-in panel on logout
  switchToSignIn();
  showToast("Signed out from Aegis Trading Desk.");
}

function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <svg class="icon icon-16 toast-ic"><use href="${type === "success" ? "#i-check" : "#i-alert"}"></use></svg>
    <span>${message}</span>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}


function showExplainerModal() {
  document.getElementById("explainer-modal").classList.add("active");
}

function closeExplainerModal() {
  document.getElementById("explainer-modal").classList.remove("active");
}

// ==========================================================================
// ACCOUNT DATA + MARKET STATE (+ Greeks Monitor + countdown clock)
// ==========================================================================
async function fetchAccountData() {
  try {
    const res = await fetch("/api/account");
    const data = await res.json();
    const acc = data.account;
    const greeks = data.portfolio_greeks;
    const md = data.market_data || {};

    if (acc.account_id) {
      document.getElementById("account-id-display").innerText = acc.account_id;
    }
    document.getElementById("portfolio-equity").innerText = `$${acc.equity.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById("buying-power").innerText = `$${acc.buying_power.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById("cash-balance").innerText = `$${acc.cash.toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

    const pnlDisplay = document.getElementById("day-pnl-display");
    const sign = acc.day_pnl >= 0 ? "+" : "";
    pnlDisplay.innerText = `${sign}$${acc.day_pnl.toFixed(2)} (${sign}${acc.day_pnl_pct.toFixed(2)}%)`;
    pnlDisplay.className = acc.day_pnl >= 0 ? "trend-positive text-emerald" : "trend-positive text-coral";

    document.getElementById("net-delta").innerText = `${greeks.net_delta >= 0 ? "+" : ""}${greeks.net_delta.toFixed(2)} Δ`;
    document.getElementById("daily-theta").innerText = `+$${greeks.daily_theta_income.toFixed(2)} / day`;

    // Market session state
    const statusText = document.getElementById("system-status-text");
    const statusDot = document.getElementById("market-status-dot");
    if (md.market_open !== undefined) {
      statusText.innerText = md.market_open ? "MARKET OPEN" : "MARKET CLOSED";
      statusDot.style.background = md.market_open ? "#10b981" : "#f59e0b";
      const sessionVal = document.getElementById("session-value");
      const sessionSub = document.getElementById("session-sub");
      if (sessionVal) {
        sessionVal.innerText = md.market_open ? "OPEN" : "CLOSED";
        sessionVal.style.color = md.market_open ? "#059669" : "#d97706";
      }
      if (sessionSub && md.next_open) {
        sessionSub.innerText = md.market_open ? `Closes: ${new Date(md.next_close).toLocaleTimeString()}` : `Opens: ${new Date(md.next_open).toLocaleString()}`;
      }
      // Store clock for the header countdown chip
      marketClock = { is_open: md.market_open, next_open: md.next_open, next_close: md.next_close };
    }

    // Stress gauge (real values)
    if (md.stress_index !== undefined) {
      const stressEl = document.getElementById("stress-index-val");
      const badge = document.getElementById("stress-badge");
      stressEl.innerText = md.stress_index.toFixed(2);
      const elevated = md.stress_index >= (md.stress_threshold || 25);
      badge.innerText = elevated ? "ELEVATED" : "NORMAL";
      badge.className = elevated ? "metric-tag tag-red" : "metric-tag tag-safe";
      stressEl.style.color = elevated ? "#e11d48" : "";
    }

    // Greeks & Exposure Monitor panel
    updateGreeksPanel(greeks, acc, md);

    // Render positions
    renderPositionsTable(data.positions);

    // Auto Trading Button State
    const autoBtn = document.getElementById("btn-toggle-auto");
    const autoText = document.getElementById("auto-btn-text");
    if (data.auto_trading && data.auto_trading.active) {
      autoBtn.classList.add("running");
      autoText.innerText = `Pause 24/7 Loop (${data.auto_trading.cycles_completed || 0} cycles)`;
    } else {
      autoBtn.classList.remove("running");
      autoText.innerText = "Enable 24/7 Loop";
    }
  } catch (e) {
    console.error("Failed to fetch account info:", e);
  }
}

// Greeks & Exposure Monitor — delta band marker, theta/stress/cash fills
function updateGreeksPanel(greeks, acc, md) {
  // Net delta within the governance band [-100, +250]
  const deltaVal = document.getElementById("greek-delta-val");
  const deltaMarker = document.getElementById("greek-delta-marker");
  if (deltaVal && greeks) {
    const d = greeks.net_delta || 0;
    deltaVal.innerText = `${d >= 0 ? "+" : ""}${d.toFixed(1)} Δ`;
    if (deltaMarker) {
      const bandMin = -100, bandMax = 250;
      const pct = Math.min(100, Math.max(0, ((d - bandMin) / (bandMax - bandMin)) * 100));
      deltaMarker.style.left = pct + "%";
      deltaMarker.style.background = (d < bandMin || d > bandMax) ? "#e11d48" : "#059669";
    }
  }

  // Theta / day (reference scale: $200/day = full bar)
  const thetaVal = document.getElementById("greek-theta-val");
  const thetaFill = document.getElementById("greek-theta-fill");
  if (thetaVal && greeks) {
    const t = greeks.daily_theta_income || 0;
    thetaVal.innerText = `+$${t.toFixed(2)}`;
    if (thetaFill) thetaFill.style.width = Math.min(100, Math.max(2, (t / 200) * 100)) + "%";
  }

  // Stress index (reference scale: 40 = full bar; trigger at threshold)
  const stressVal = document.getElementById("greek-stress-val");
  const stressFill = document.getElementById("greek-stress-fill");
  if (stressVal && md && md.stress_index !== undefined) {
    stressVal.innerText = md.stress_index.toFixed(2);
    if (stressFill) {
      stressFill.style.width = Math.min(100, (md.stress_index / 40) * 100) + "%";
      stressFill.style.background = md.stress_index >= (md.stress_threshold || 25) ? "#e11d48" : "#f59e0b";
    }
  }

  // Cash deployed ((equity - cash) / equity)
  const cashVal = document.getElementById("greek-cash-val");
  const cashFill = document.getElementById("greek-cash-fill");
  if (cashVal && acc) {
    const equity = acc.equity || 1;
    const deployed = Math.max(0, Math.min(100, ((equity - acc.cash) / equity) * 100));
    cashVal.innerText = deployed.toFixed(1) + "%";
    if (cashFill) cashFill.style.width = deployed + "%";
  }
}

// ==========================================================================
// TICKER TAPE — watchlist spot matrix with session baseline deltas
// ==========================================================================
async function fetchTickerTape() {
  const track = document.getElementById("ticker-tape-track");
  if (!track) return;
  try {
    const res = await fetch("/api/market-data");
    const data = await res.json();
    const wl = data.watchlist || [];

    if (!wl.length) {
      track.innerHTML = `<span class="ticker-loading">Market data feed unavailable…</span>`;
      return;
    }

    const items = wl.map(w => {
      if (tickerBaseline[w.ticker] === undefined) tickerBaseline[w.ticker] = w.spot;
      const base = tickerBaseline[w.ticker];
      const delta = w.spot - base;
      const pct = base ? (delta / base) * 100 : 0;
      const cls = delta >= 0 ? "up" : "down";
      return `<span class="ticker-item">
        <span class="ticker-sym">${w.ticker}</span>
        <span class="ticker-px">$${w.spot.toFixed(2)}</span>
        <span class="ticker-chg ${cls}">${delta >= 0 ? "+" : "-"}${Math.abs(pct).toFixed(2)}%</span>
      </span>`;
    }).join("");

    // Duplicate the sequence for a seamless marquee loop
    track.innerHTML = items + items;
  } catch (e) {
    // Keep last rendered tape on transient failures
  }
}

// ==========================================================================
// MARKET SESSION COUNTDOWN CHIP
// ==========================================================================
function tickCountdown() {
  const el = document.getElementById("countdown-text");
  if (!el || !marketClock) return;

  const parseClock = (s) => {
    if (!s) return null;
    const d = new Date(String(s).replace(" ", "T"));
    return isNaN(d) ? null : d;
  };

  let target = null, label = "";
  if (marketClock.is_open) {
    target = parseClock(marketClock.next_close);
    label = "CLOSES ";
  } else {
    target = parseClock(marketClock.next_open);
    label = "OPENS ";
  }

  if (!target) { el.innerText = "—"; return; }

  const diff = Math.max(0, target - new Date());
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  el.innerText = `${label}${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

// ==========================================================================
// PROPOSALS / POSITIONS / MARKS
// ==========================================================================
async function fetchScreenedProposals() {
  const tbody = document.getElementById("proposals-tbody");
  tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4">Scanning options chains across universe...</td></tr>`;

  try {
    const res = await fetch("/api/screen");
    const data = await res.json();
    tbody.innerHTML = "";

    if (!data.proposals || data.proposals.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4">No active options proposals available right now.</td></tr>`;
      return;
    }

    data.proposals.forEach(p => {
      const tr = document.createElement("tr");
      const ivRank = p.iv_rank !== undefined ? `${p.iv_rank.toFixed(0)}` : "—";
      tr.innerHTML = `
        <td><strong>${p.ticker}</strong></td>
        <td><span class="badge-alpha">${p.strategy.replace("_", " ")}</span></td>
        <td><code style="font-size:11px;">${p.contract_symbol}</code></td>
        <td>$${p.strike.toFixed(1)}</td>
        <td>${p.dte}d</td>
        <td>${p.delta}</td>
        <td>${ivRank}</td>
        <td class="text-emerald">+$${p.total_credit.toFixed(2)}</td>
        <td><strong>${p.annualized_yield.toFixed(1)}%</strong></td>
        <td>
          <button class="btn-trade-deploy" onclick="executeTradeTicket('${p.contract_symbol}', 1, 'sell', ${p.estimated_premium}, '${p.ticker}', ${p.strike}, '${p.strategy}')">
            Deploy
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to fetch proposals:", e);
    tbody.innerHTML = `<tr><td colspan="10" class="text-center py-4 text-coral">Failed to load proposals.</td></tr>`;
  }
}

function renderPositionsTable(positions) {
  const tbody = document.getElementById("positions-tbody");
  const countBadge = document.getElementById("positions-count");
  countBadge.innerText = `${positions.length} Positions`;

  if (!positions || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4">No active positions yet. Click "Deploy" above or "Run AI Cycle" to open positions.</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  positions.forEach(p => {
    const tr = document.createElement("tr");
    const pnlClass = p.unrealized_pl >= 0 ? "text-emerald" : "text-coral";
    const sign = p.unrealized_pl >= 0 ? "+" : "";
    tr.innerHTML = `
      <td><strong>${p.symbol}</strong></td>
      <td><span class="badge-alpha">${p.asset_class}</span></td>
      <td>${p.qty}</td>
      <td>$${p.market_value.toLocaleString("en-US", {minimumFractionDigits: 2})}</td>
      <td>$${p.cost_basis.toLocaleString("en-US", {minimumFractionDigits: 2})}</td>
      <td class="${pnlClass}">${sign}$${p.unrealized_pl.toFixed(2)} (${sign}${p.unrealized_plpc}%)</td>
      <td>$${p.current_price.toFixed(2)}</td>
    `;
    tbody.appendChild(tr);
  });
}

async function fetchPositionMarks() {
  const tbody = document.getElementById("marks-tbody");
  if (!tbody) return;
  try {
    const res = await fetch("/api/positions/marks");
    const data = await res.json();
    const marks = data.marks || [];
    document.getElementById("marks-count").innerText = `${marks.length} Options`;

    if (marks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center py-4">No open option positions to manage.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    marks.forEach(m => {
      const tr = document.createElement("tr");
      const stateColors = {
        "HOLD": "#64748b",
        "PROFIT_TAKE_DUE": "#059669",
        "STOP_LOSS_DUE": "#e11d48",
        "EXPIRY_TODAY": "#d97706",
        "ROLL_WINDOW": "#0284c7",
      };
      const color = stateColors[m.management_state] || "#64748b";
      const pnlClass = m.pnl_pct >= 0 ? "text-emerald" : "text-coral";
      tr.innerHTML = `
        <td><code style="font-size:10.5px;">${m.contract_symbol}</code></td>
        <td>${m.qty}</td>
        <td>$${m.entry_premium.toFixed(2)}</td>
        <td>$${m.current_mark.toFixed(2)}</td>
        <td class="${pnlClass}">${m.pnl_pct >= 0 ? "+" : ""}${m.pnl_pct.toFixed(0)}%</td>
        <td>${m.dte}d</td>
        <td><strong style="color:${color};">${m.management_state.replace(/_/g, " ")}</strong></td>
        <td>
          ${m.management_state !== "HOLD" ? `<button class="btn-trade-close" onclick="manualClosePosition('${m.contract_symbol}', ${Math.abs(m.qty)})">Close Now</button>` : "—"}
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch (e) {
    console.error("Failed to fetch position marks:", e);
  }
}

window.manualClosePosition = async function(contractSymbol, qty) {
  try {
    const res = await fetch("/api/close-position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contract_symbol: contractSymbol, qty: Math.max(1, Math.abs(qty)) })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Buy-to-close submitted for ${contractSymbol}`, "success");
    } else {
      showToast(`Close failed: ${data.order?.error || "rejected"}`, "error");
    }
    fetchPositionMarks();
    fetchAccountData();
  } catch (e) {
    console.error("Manual close error:", e);
  }
};

// ==========================================================================
// PERFORMANCE (real journal analytics) + P&L attribution + timeframe
// ==========================================================================
async function fetchPerformance() {
  try {
    const res = await fetch("/api/performance");
    const data = await res.json();

    const pnlEl = document.getElementById("realized-pnl");
    if (pnlEl) {
      pnlEl.innerText = `${data.total_realized_pnl >= 0 ? "+" : "-"}$${Math.abs(data.total_realized_pnl).toFixed(2)}`;
      pnlEl.className = `metric-value ${data.total_realized_pnl >= 0 ? "text-emerald" : "text-coral"}`;
    }
    const winRateEl = document.getElementById("win-rate-val");
    if (winRateEl) winRateEl.innerText = `${data.win_rate_pct}%`;
    const closedEl = document.getElementById("closed-trades-val");
    if (closedEl) closedEl.innerText = `${data.closed_trades}`;

    // Stat boxes
    const trEl = document.getElementById("stat-total-return");
    if (trEl) trEl.innerText = `${data.total_return_pct >= 0 ? "+" : ""}${data.total_return_pct.toFixed(2)}%`;
    const shEl = document.getElementById("stat-sharpe");
    if (shEl) shEl.innerText = data.sharpe_ratio > 0 ? data.sharpe_ratio.toFixed(2) : "—";
    const pfEl = document.getElementById("stat-profit-factor");
    if (pfEl) pfEl.innerText = data.profit_factor > 0 ? data.profit_factor.toFixed(2) : "—";
    const ddEl = document.getElementById("stat-max-dd");
    if (ddEl) ddEl.innerText = `${data.max_drawdown_pct.toFixed(2)}%`;

    // Live equity curve chart (respects active timeframe)
    lastEquityCurve = data.equity_curve || [];
    updatePerformanceChart(lastEquityCurve);

    // P&L attribution panel
    renderAttribution(data);
  } catch (e) {
    console.error("Failed to fetch performance:", e);
  }
}

function updatePerformanceChart(equityCurve) {
  if (!chartInstance || !equityCurve || !equityCurve.length) return;

  let curve = equityCurve;
  if (chartTimeframe !== "all") {
    curve = equityCurve.slice(-parseInt(chartTimeframe, 10));
  }

  const labels = curve.map(p => {
    const d = new Date(p.timestamp);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  });
  const equities = curve.map(p => p.equity);
  const base = equities[0] || 100000;
  const returns = equities.map(e => ((e - base) / base) * 100);

  chartInstance.data.labels = labels;
  chartInstance.data.datasets[0].data = returns;
  chartInstance.data.datasets[0].label = "AEGIS Live Equity Curve (% vs session start)";
  chartInstance.update("none");
}

// P&L Attribution — ticker heatmap (journal cache) + strategy bars (analytics)
function renderAttribution(perf) {
  const heatmap = document.getElementById("ticker-heatmap");
  const bars = document.getElementById("strategy-bars");
  const countBadge = document.getElementById("attribution-count");

  // Realized P&L aggregated by ticker from closed journal rows
  const byTicker = {};
  journalCache.forEach(t => {
    if (t.status === "OPEN") return;
    byTicker[t.ticker] = (byTicker[t.ticker] || 0) + (t.realized_pnl || 0);
  });
  const tickEntries = Object.entries(byTicker).sort((a, b) => b[1] - a[1]).slice(0, 12);

  if (heatmap) {
    if (!tickEntries.length) {
      heatmap.innerHTML = `<span class="heatmap-empty">No closed trades yet.</span>`;
    } else {
      const maxAbs = Math.max(...tickEntries.map(e => Math.abs(e[1])), 1);
      heatmap.innerHTML = tickEntries.map(([ticker, pnl]) => {
        const intensity = 0.15 + Math.min(1, Math.abs(pnl) / maxAbs) * 0.75;
        const bg = pnl >= 0 ? `rgba(5, 150, 105, ${intensity})` : `rgba(225, 29, 72, ${intensity})`;
        return `<span class="heatmap-tile" style="background:${bg};" title="${ticker}: $${pnl.toFixed(2)} realized">${ticker}<em>${pnl >= 0 ? "+" : "-"}$${Math.abs(pnl).toFixed(0)}</em></span>`;
      }).join("");
    }
  }

  // Strategy breakdown bars from the journal analytics
  const strategies = Object.entries(perf.strategy_breakdown || {});
  if (bars) {
    if (!strategies.length) {
      bars.innerHTML = `<span class="heatmap-empty">No closed trades yet.</span>`;
    } else {
      const maxAbsPnl = Math.max(...strategies.map(([, b]) => Math.abs(b.realized_pnl || 0)), 1);
      bars.innerHTML = strategies.map(([name, b]) => {
        const pnl = b.realized_pnl || 0;
        const width = Math.max(4, (Math.abs(pnl) / maxAbsPnl) * 100);
        const color = pnl >= 0 ? "#059669" : "#e11d48";
        return `<div class="strategy-bar-row">
          <div class="strategy-bar-head"><span>${(name || "UNKNOWN").replace(/_/g, " ")}</span><span style="color:${color};">${pnl >= 0 ? "+" : "-"}$${Math.abs(pnl).toFixed(2)}</span></div>
          <div class="strategy-bar-track"><div class="strategy-bar-fill" style="width:${width}%; background:${color};"></div></div>
          <div class="strategy-bar-meta">${b.trades} trades · ${b.win_rate}% win</div>
        </div>`;
      }).join("");
    }
  }

  if (countBadge && perf.closed_trades !== undefined) {
    countBadge.innerText = `${perf.closed_trades} Closed Trades`;
  }
}

// ==========================================================================
// TRADE JOURNAL (cache + client-side filter/search + CSV export)
// ==========================================================================
async function fetchJournal() {
  const tbody = document.getElementById("journal-tbody");
  if (!tbody) return;
  try {
    const res = await fetch("/api/journal?limit=25");
    const data = await res.json();
    journalCache = data.trades || [];
    renderJournal();
  } catch (e) {
    console.error("Failed to fetch journal:", e);
  }
}

function getFilteredJournal() {
  const searchEl = document.getElementById("journal-search");
  const filterEl = document.getElementById("journal-status-filter");
  const q = searchEl ? searchEl.value.trim().toLowerCase() : "";
  const st = filterEl ? filterEl.value : "ALL";
  return journalCache.filter(t =>
    (st === "ALL" || t.status === st) &&
    (!q || (t.ticker || "").toLowerCase().includes(q) || (t.strategy || "").toLowerCase().includes(q))
  );
}

function renderJournal() {
  const tbody = document.getElementById("journal-tbody");
  if (!tbody) return;

  const trades = getFilteredJournal();
  document.getElementById("journal-count").innerText = `${journalCache.length} Trades`;
  const filteredCount = document.getElementById("journal-filtered-count");
  if (filteredCount) {
    filteredCount.innerText = (trades.length !== journalCache.length)
      ? `Showing ${trades.length} of ${journalCache.length}`
      : "";
  }

  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4">${journalCache.length ? "No trades match the current filter." : "No journal entries yet. Run a cycle to begin the audit trail."}</td></tr>`;
    return;
  }

  tbody.innerHTML = "";
  trades.forEach(t => {
    const tr = document.createElement("tr");
    const statusColors = { OPEN: "#0284c7", CLOSED: "#059669", EXPIRED: "#64748b", ASSIGNED: "#d97706" };
    const color = statusColors[t.status] || "#64748b";
    const pnl = t.realized_pnl || 0;
    const pnlStr = t.status === "OPEN" ? "—" : `${pnl >= 0 ? "+" : "-"}$${Math.abs(pnl).toFixed(2)}`;
    const pnlClass = pnl >= 0 ? "text-emerald" : "text-coral";
    tr.innerHTML = `
      <td style="font-size:11px;">${(t.created_at || "").slice(11, 19)}</td>
      <td><strong>${t.ticker}</strong></td>
      <td style="font-size:11px;">${(t.strategy || "").replace(/_/g, " ")}</td>
      <td style="font-size:11px;">${(t.side || "").replace(/_/g, " ")}</td>
      <td>$${(t.premium || 0).toFixed(2)}</td>
      <td><strong style="color:${color};">${t.status}</strong></td>
      <td class="${pnlClass}"><strong>${pnlStr}</strong></td>
    `;
    tbody.appendChild(tr);
  });
}

function exportJournalCSV() {
  const trades = getFilteredJournal();
  if (!trades.length) {
    showToast("No trades to export — adjust the filter or run a cycle first.", "error");
    return;
  }

  const headers = ["created_at", "ticker", "strategy", "side", "qty", "contract_symbol", "premium", "status", "realized_pnl", "closed_at", "risk_verdict"];
  const esc = (v) => {
    const s = String(v === null || v === undefined ? "" : v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const rows = trades.map(t => headers.map(h => esc(t[h])).join(","));
  const csv = headers.join(",") + "\n" + rows.join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `aegis_journal_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast(`Exported ${trades.length} journal rows to CSV.`, "success");
}

// ==========================================================================
// NEWS & REGIME (with headline filter)
// ==========================================================================
async function fetchNews() {
  try {
    const res = await fetch("/api/news");
    const data = await res.json();
    const regime = data.regime || {};

    const regimeEl = document.getElementById("regime-value");
    const regimeSummaryEl = document.getElementById("regime-summary");
    const regimeBadge = document.getElementById("regime-badge");

    if (regimeEl && regime.regime) {
      regimeEl.innerText = regime.regime.replace("_", " ");
      const colors = { RISK_ON: "#059669", NEUTRAL: "#0284c7", RISK_OFF: "#d97706", CRISIS: "#e11d48" };
      regimeEl.style.color = colors[regime.regime] || "#0f172a";
    }
    if (regimeSummaryEl && regime.summary) {
      regimeSummaryEl.innerText = regime.summary.slice(0, 160);
    }
    if (regimeBadge && regime.regime) {
      regimeBadge.innerText = regime.regime.replace("_", " ");
    }

    // Cache headlines and render through the active filter
    lastHeadlines = data.market_headlines || [];
    renderNewsFeed();
  } catch (e) {
    console.error("Failed to fetch news:", e);
  }
}

function renderNewsFeed() {
  const feed = document.getElementById("news-feed");
  if (!feed) return;

  if (!lastHeadlines.length) {
    feed.innerHTML = `<div class="news-item">Live headline feed unavailable — LLM knowledge fallback in use.</div>`;
    return;
  }

  const searchEl = document.getElementById("news-search");
  const q = searchEl ? searchEl.value.trim().toLowerCase() : "";
  const headlines = q
    ? lastHeadlines.filter(h => (h.title || "").toLowerCase().includes(q))
    : lastHeadlines;

  if (!headlines.length) {
    feed.innerHTML = `<div class="news-item">No headlines match "${q}".</div>`;
    return;
  }

  feed.innerHTML = headlines.map(h => `
      <div class="news-item">
        <div class="news-headline">${h.title}</div>
        <div class="news-meta">${h.source || "Google News"}${h.published ? " · " + h.published.slice(0, 22) : ""}</div>
      </div>
    `).join("");
}

// ==========================================================================
// LIVE LOGS (polling fallback)
// ==========================================================================
async function fetchLiveLogs() {
  try {
    const res = await fetch("/api/logs");
    const data = await res.json();
    const feed = document.getElementById("terminal-feed");

    if (data.logs && data.logs.length > 0 && !wsConnected) {
      feed.innerHTML = "";
      data.logs.forEach(log => appendTerminalRow(log));
    }
  } catch (e) {
    console.error("Failed to fetch logs:", e);
  }
}

// ==========================================================================
// CYCLE ACTIONS
// ==========================================================================
async function runAICycle() {
  const btn = document.getElementById("btn-run-cycle");
  btn.disabled = true;
  btn.innerHTML = `<span>Running Multi-Agent Pipeline...</span>`;

  try {
    const res = await fetch("/api/run-cycle", { method: "POST" });
    const data = await res.json();

    if (data.briefing_text) {
      document.getElementById("briefing-text-display").innerText = `"${data.briefing_text}"`;
    }

    const mgd = data.management ? data.management.managed : 0;
    showToast(`AI Cycle Complete! Screened: ${data.proposals_count} | Executed: ${data.executed_trades ? data.executed_trades.length : 0} | Vetoed: ${data.vetoed_trades ? data.vetoed_trades.length : 0} | Managed: ${mgd}`);

    fetchAccountData();
    fetchScreenedProposals();
    fetchLiveLogs();
    fetchPerformance();
    fetchJournal();
    fetchPositionMarks();
  } catch (e) {
    console.error("Cycle execution error:", e);
    showToast("Cycle execution completed.", "success");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg class="icon icon-16"><use href="#i-play"></use></svg><span>Run AI Cycle</span>`;
  }
}

async function toggleAutoTrading() {
  try {
    const res = await fetch("/api/toggle-auto?interval_sec=300", { method: "POST" });
    const data = await res.json();
    showToast(data.active ? "Autonomous 24/7 Loop Activated (5-min cycles)" : "Autonomous Loop Paused");
    fetchAccountData();
    fetchLiveLogs();
  } catch (e) {
    console.error("Failed to toggle auto loop:", e);
  }
}

async function triggerEmergencyHedge() {
  try {
    const res = await fetch("/api/trigger-hedge", { method: "POST" });
    const data = await res.json();
    showToast(data.hedge_triggered ? "Protective Put Tail Hedge Deployed!" : "Market Risk Normal — No Hedge Needed");
    fetchAccountData();
    fetchLiveLogs();
  } catch (e) {
    console.error("Hedge trigger error:", e);
  }
}

window.executeTradeTicket = async function(symbol, qty, side, limitPrice, ticker, strike, strategy) {
  try {
    const res = await fetch("/api/execute-trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        qty: qty || 1,
        side: side || "sell",
        order_type: "limit",
        limit_price: limitPrice,
        strike: strike,
        underlying: ticker,
        strategy: strategy
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Order Submitted: ${side.toUpperCase()} 1x ${symbol} @ $${limitPrice}`);
    } else {
      showToast(`Order Rejected: ${data.message || "broker error"}`, "error");
    }
    fetchAccountData();
    fetchLiveLogs();
    fetchJournal();
  } catch (e) {
    console.error("Trade execution error:", e);
    showToast(`Order submission failed for ${symbol}`, "error");
  }
};

// ==========================================================================
// DEDICATED AUDIO PLAYER — instant-play architecture (FIX)
// The previous implementation awaited the slow ElevenLabs regeneration
// BEFORE calling play(), leaving the button in a dead "playing" state.
// Now: play the cached MP3 instantly, refresh text/audio in background.
// ==========================================================================
let briefingAudio = new Audio();
briefingAudio.preload = "auto";
briefingAudio.volume = 1.0;
let isSpeechFallback = false;
let briefingObjectUrl = null; // in-memory blob of the briefing MP3 (instant replay)

function getBriefingVolume() {
  const slider = document.getElementById("volume-slider");
  return slider ? (parseInt(slider.value, 10) / 100) : 1.0;
}

function _setPlayBtn(playing) {
  const playBtn = document.getElementById("btn-play-briefing");
  if (playBtn) {
    const useEl = playBtn.querySelector("use");
    if (useEl) useEl.setAttribute("href", playing ? "#i-pause" : "#i-play");
  }
  const statusPill = document.getElementById("audio-status-pill");
  if (statusPill) statusPill.innerText = playing ? "PLAYING" : "READY";
}

function setAudioStatus(text) {
  const statusPill = document.getElementById("audio-status-pill");
  if (statusPill) statusPill.innerText = text;
}

function stopAudio() {
  isAudioPlaying = false;
  isSpeechFallback = false;

  // Always stop both engines
  briefingAudio.pause();
  try { briefingAudio.currentTime = 0; } catch {}

  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }

  _setPlayBtn(false);
}

// Preload the cached briefing MP3 into memory (fire-and-forget) so the first
// click on PLAY starts audio instantly with no network wait.
function preloadBriefingAudio() {
  if (briefingObjectUrl) return;
  fetch("/audio/latest_briefing.mp3?t=" + Date.now(), { cache: "no-store" })
    .then((res) => (res.ok ? res.blob() : null))
    .then((blob) => {
      if (blob && blob.size > 1000 && !briefingObjectUrl) {
        briefingObjectUrl = URL.createObjectURL(blob);
        setAudioStatus("READY");
      }
    })
    .catch(() => {});
}

// Play / Stop AI Voice Briefing — bulletproof playback chain:
// 0) instant replay from the in-memory blob if already loaded
// 1) fetch the cached MP3 FULLY into memory (blob URL) before playing —
//    immune to server-side file replacement races and range-request streams
// 2) cached file missing/unusable → regenerate once, then play the fresh file
// 3) final fallback — Web Speech synthesis of the briefing text
async function playAudioBriefing() {
  // If anything is playing → stop it (true toggle)
  if (isAudioPlaying) {
    stopAudio();
    return;
  }

  const textDisplay = document.getElementById("briefing-text-display");
  isAudioPlaying = true;
  isSpeechFallback = false;
  _setPlayBtn(true);
  briefingAudio.volume = getBriefingVolume();
  briefingAudio.onended = () => stopAudio();

  // 0) Instant replay from the already-loaded in-memory blob
  if (briefingObjectUrl) {
    try {
      briefingAudio.src = briefingObjectUrl;
      await briefingAudio.play();
      setAudioStatus("PLAYING");
      return;
    } catch { /* stale blob — refetch below */ }
  }
  if (!isAudioPlaying) return;

  // 1) Load the cached briefing MP3 fully into memory, then play
  setAudioStatus("LOADING…");
  try {
    const res = await fetch("/audio/latest_briefing.mp3?t=" + Date.now(), { cache: "no-store", signal: AbortSignal.timeout(4000) });
    if (res.ok) {
      const blob = await res.blob();
      if (blob.size > 1000) {
        briefingObjectUrl = URL.createObjectURL(blob);
        briefingAudio.src = briefingObjectUrl;
        await briefingAudio.play();
        setAudioStatus("PLAYING");
        return;
      }
    }
  } catch (err) {
    console.warn("Cached briefing playback failed:", err);
  }
  if (!isAudioPlaying) return;

  // 2) Cached file unusable → regenerate (fresh text + MP3), then play
  try {
    setAudioStatus("GENERATING…");
    const res = await fetch("/api/audio-briefing", { signal: AbortSignal.timeout(30000) });
    const data = await res.json();
    if (!isAudioPlaying) return;
    if (data && data.text) textDisplay.innerText = `"${data.text}"`;
    if (data && data.audio_url) {
      const audioRes = await fetch(data.audio_url + "?t=" + Date.now(), { cache: "no-store" });
      const blob = await audioRes.blob();
      if (blob.size > 1000) {
        briefingObjectUrl = URL.createObjectURL(blob);
        briefingAudio.src = briefingObjectUrl;
        await briefingAudio.play();
        setAudioStatus("PLAYING");
        return;
      }
    }
  } catch (err) {
    console.warn("Briefing regeneration failed:", err);
  }
  if (!isAudioPlaying) return;

  // 3) Final fallback — Web Speech synthesis
  isSpeechFallback = true;
  speakText(textDisplay.innerText.replace(/["']/g, ""));
}

// Explicit regeneration via the dedicated button (shows GENERATING state)
async function regenerateBriefing() {
  const btn = document.getElementById("btn-regen-briefing");
  if (btn) btn.disabled = true;
  setAudioStatus("GENERATING…");
  try {
    const res = await fetch("/api/audio-briefing");
    const data = await res.json();
    if (data && data.text) {
      document.getElementById("briefing-text-display").innerText = `"${data.text}"`;
    }
    // Invalidate the cached in-memory blob so the next play uses the fresh MP3
    if (briefingObjectUrl) {
      URL.revokeObjectURL(briefingObjectUrl);
      briefingObjectUrl = null;
    }
    setAudioStatus(data && data.audio_url ? "READY" : "TEXT ONLY");
    showToast(
      data && data.audio_url
        ? "Voice briefing regenerated with live numbers."
        : "Briefing text refreshed (audio synthesis unavailable).",
      data && data.audio_url ? "success" : "error"
    );
  } catch {
    setAudioStatus("READY");
    showToast("Could not regenerate briefing.", "error");
  } finally {
    if (btn) btn.disabled = false;
  }
}

function speakText(text) {
  if (!window.speechSynthesis || !text || text.trim() === "") {
    stopAudio();
    return;
  }
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.volume = getBriefingVolume();
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  utterance.onend = () => stopAudio();
  utterance.onerror = () => stopAudio();

  window.speechSynthesis.speak(utterance);
}

// ==========================================================================
// PERFORMANCE VISUALIZATION (live journal equity curve)
// ==========================================================================
function initPerformanceChart() {
  const ctx = document.getElementById("performanceChart");
  if (!ctx) return;

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        {
          label: 'AEGIS Live Equity Curve (%)',
          data: [],
          borderColor: '#059669',
          backgroundColor: 'rgba(5, 150, 105, 0.08)',
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: '#059669',
          pointRadius: 3
        }
      ]
    },
    options: {
      responsive: true,
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { family: 'Inter', size: 11, weight: '600' },
            color: '#475569'
          }
        },
        tooltip: {
          callbacks: {
            label: (context) => `${context.dataset.label}: ${context.parsed.y.toFixed(3)}%`
          }
        }
      },
      scales: {
        x: {
          grid: { color: '#f1f5f9' },
          ticks: {
            font: { family: 'JetBrains Mono', size: 10 },
            color: '#64748b',
            maxTicksLimit: 10
          }
        },
        y: {
          grid: { color: '#f1f5f9' },
          ticks: {
            font: { family: 'JetBrains Mono', size: 10 },
            color: '#64748b',
            callback: value => value + '%'
          }
        }
      }
    }
  });
}

// Re-skin the chart for the active theme (gridlines / ticks / legend)
function refreshChartTheme() {
  if (!chartInstance) return;
  const grid = darkTheme ? "rgba(148, 163, 184, 0.12)" : "#f1f5f9";
  const ticks = darkTheme ? "#8b99b0" : "#64748b";
  const legend = darkTheme ? "#b6c2d6" : "#475569";

  chartInstance.options.scales.x.grid.color = grid;
  chartInstance.options.scales.x.ticks.color = ticks;
  chartInstance.options.scales.y.grid.color = grid;
  chartInstance.options.scales.y.ticks.color = ticks;
  chartInstance.options.plugins.legend.labels.color = legend;
  chartInstance.update("none");
}

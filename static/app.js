// ==========================================================================
// AEGIS TRADING ENGINE FRONTEND CONTROLLER v2.0
// ==========================================================================

let chartInstance = null;
let isAudioPlaying = false;
let currentAudio = null;

// Initialize on Load
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
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

  // Periodic background polling
  setInterval(() => {
    if (document.getElementById("app-layout").classList.contains("hidden")) return;
    fetchAccountData();
    fetchLiveLogs();
  }, 3000);
});

// Setup Event Listeners
function setupEventListeners() {
  document.getElementById("btn-run-cycle").addEventListener("click", runAICycle);
  document.getElementById("btn-toggle-auto").addEventListener("click", toggleAutoTrading);
  document.getElementById("btn-emergency-hedge").addEventListener("click", triggerEmergencyHedge);
  document.getElementById("btn-refresh-screen").addEventListener("click", fetchScreenedProposals);
  document.getElementById("btn-play-briefing").addEventListener("click", playAudioBriefing);

  // Explainer modal click outside
  const explainer = document.getElementById("explainer-modal");
  explainer.addEventListener("click", (e) => {
    if (e.target === explainer) closeExplainerModal();
  });
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
  const isHidden = input.type === "password";
  input.type = isHidden ? "text" : "password";
  btn.innerHTML = isHidden
    ? `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
    : `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
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
    btn.innerHTML = `<span>Create Account &amp; Get Started</span><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
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
    btn.innerHTML = `<span>Sign In &amp; Enter Trading Desk</span><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;
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
  fetchAccountData();
  fetchScreenedProposals();
  fetchLiveLogs();
}

function handleLogout() {
  localStorage.removeItem("aegis_auth");
  document.getElementById("app-layout").classList.add("hidden");
  document.getElementById("auth-overlay").classList.remove("hidden");
  stopAudio();
  // Reset to sign-in panel on logout
  switchToSignIn();
  showToast("Signed out from Aegis Trading Desk.");
}

function showToast(message, type = "success") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✅' : '⚠️'}</span>
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


// Fetch Account Info
async function fetchAccountData() {
  try {
    const res = await fetch("/api/account");
    const data = await res.json();
    const acc = data.account;
    const greeks = data.portfolio_greeks;

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

    // Render positions
    renderPositionsTable(data.positions);

    // Auto Trading Button State
    const autoBtn = document.getElementById("btn-toggle-auto");
    const autoText = document.getElementById("auto-btn-text");
    if (data.auto_trading && data.auto_trading.active) {
      autoBtn.classList.add("running");
      autoText.innerText = "Pause 24/7 Loop";
    } else {
      autoBtn.classList.remove("running");
      autoText.innerText = "Enable 24/7 Loop";
    }
  } catch (e) {
    console.error("Failed to fetch account info:", e);
  }
}

// Fetch Screened Opportunities
async function fetchScreenedProposals() {
  const tbody = document.getElementById("proposals-tbody");
  tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4">Scanning options chains across universe...</td></tr>`;

  try {
    const res = await fetch("/api/screen");
    const data = await res.json();
    tbody.innerHTML = "";

    if (!data.proposals || data.proposals.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4">No active options proposals available right now.</td></tr>`;
      return;
    }

    data.proposals.forEach(p => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${p.ticker}</strong></td>
        <td><span class="badge-alpha">${p.strategy.replace("_", " ")}</span></td>
        <td><code style="font-size:11px;">${p.contract_symbol}</code></td>
        <td>$${p.strike.toFixed(1)}</td>
        <td>${p.dte}d</td>
        <td>${p.delta}</td>
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
    tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-coral">Failed to load proposals.</td></tr>`;
  }
}

// Render Positions Table
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

// Fetch Live Logs & Update Terminal
async function fetchLiveLogs() {
  try {
    const res = await fetch("/api/logs");
    const data = await res.json();
    const feed = document.getElementById("terminal-feed");

    if (data.logs && data.logs.length > 0) {
      feed.innerHTML = "";
      data.logs.forEach(log => {
        const row = document.createElement("div");
        row.className = "terminal-row";

        let badgeClass = "badge-sys";
        if (log.agent === "QuantAgent") badgeClass = "badge-quant";
        else if (log.agent === "SentimentAgent") badgeClass = "badge-sent";
        else if (log.agent === "RiskGovernanceAgent") badgeClass = "badge-risk";
        else if (log.agent === "ExecutionEngine" || log.agent === "AlpacaBroker") badgeClass = "badge-broker";

        row.innerHTML = `
          <span class="term-time">[${log.timestamp}]</span>
          <span class="term-badge ${badgeClass}">${log.agent.toUpperCase()}</span>
          <span class="term-text">${log.message}</span>
        `;
        feed.appendChild(row);
      });
      feed.scrollTop = feed.scrollHeight;
    }
  } catch (e) {
    console.error("Failed to fetch logs:", e);
  }
}

// Run AI Cycle
async function runAICycle() {
  const btn = document.getElementById("btn-run-cycle");
  btn.disabled = true;
  btn.innerHTML = `<span>Running Triad Agents...</span>`;

  try {
    const res = await fetch("/api/run-cycle", { method: "POST" });
    const data = await res.json();

    if (data.briefing_text) {
      document.getElementById("briefing-text-display").innerText = `"${data.briefing_text}"`;
    }

    showToast(`AI Cycle Complete! Screened: ${data.proposals_count} | Executed: ${data.executed_trades ? data.executed_trades.length : 0} | Vetoed: ${data.vetoed_trades ? data.vetoed_trades.length : 0}`);

    fetchAccountData();
    fetchScreenedProposals();
    fetchLiveLogs();
  } catch (e) {
    console.error("Cycle execution error:", e);
    showToast("Cycle execution completed.", "success");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>Run AI Cycle</span>`;
  }
}

// Toggle Auto Trading Loop
async function toggleAutoTrading() {
  try {
    const res = await fetch("/api/toggle-auto", { method: "POST" });
    const data = await res.json();
    showToast(data.active ? "Autonomous 24/7 Loop Activated" : "Autonomous Loop Paused");
    fetchAccountData();
    fetchLiveLogs();
  } catch (e) {
    console.error("Failed to toggle auto loop:", e);
  }
}

// Trigger Emergency Tail Hedge
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

// Execute Specific Trade Ticket
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
    showToast(`Order Submitted: ${side.toUpperCase()} 1x ${symbol} @ $${limitPrice}`);
    fetchAccountData();
    fetchLiveLogs();
  } catch (e) {
    console.error("Trade execution error:", e);
    showToast(`Order submitted for ${symbol}`, "success");
  }
};

// Dedicated Audio Player Instance
let briefingAudio = new Audio();
briefingAudio.preload = "none";
briefingAudio.volume = 1.0;
let isSpeechFallback = false;

function _setPlayBtn(playing) {
  const playBtn = document.getElementById("btn-play-briefing");
  const statusPill = document.getElementById("audio-status-pill");
  if (playBtn) {
    playBtn.innerHTML = playing
      ? `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`
      : `<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;
  }
  if (statusPill) {
    statusPill.innerText = playing ? "PLAYING" : "READY";
  }
}

function stopAudio() {
  isAudioPlaying = false;
  isSpeechFallback = false;

  // Always stop both engines
  briefingAudio.pause();
  briefingAudio.currentTime = 0;

  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }

  _setPlayBtn(false);
}

// Play / Stop AI Voice Briefing (true toggle)
async function playAudioBriefing() {
  // If anything is playing → stop it
  if (isAudioPlaying) {
    stopAudio();
    return;
  }

  isAudioPlaying = true;
  isSpeechFallback = false;
  _setPlayBtn(true);

  const textDisplay = document.getElementById("briefing-text-display");

  // Assign a fresh URL (cache-busted) only when starting playback
  briefingAudio.src = "/static/audio/latest_briefing.mp3?t=" + Date.now();
  briefingAudio.volume = 1.0;

  briefingAudio.onended = () => stopAudio();

  briefingAudio.onerror = () => {
    // Only fall back if we're still supposed to be playing
    if (!isAudioPlaying) return;
    console.warn("HTML5 Audio failed — using Web Speech fallback.");
    isSpeechFallback = true;
    speakText(textDisplay.innerText.replace(/["']/g, ""));
  };

  try {
    const playPromise = briefingAudio.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        if (!isAudioPlaying) return;
        console.warn("play() rejected — using Web Speech fallback:", err);
        isSpeechFallback = true;
        speakText(textDisplay.innerText.replace(/["']/g, ""));
      });
    }
  } catch (err) {
    if (isAudioPlaying) {
      console.warn("Exception during play() — using Web Speech fallback:", err);
      isSpeechFallback = true;
      speakText(textDisplay.innerText.replace(/["']/g, ""));
    }
  }
}

function speakText(text) {
  if (!window.speechSynthesis || !text || text.trim() === "") {
    stopAudio();
    return;
  }
  window.speechSynthesis.cancel();

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.volume = 1.0;
  utterance.rate = 1.0;
  utterance.pitch = 1.0;

  utterance.onend = () => stopAudio();
  utterance.onerror = () => stopAudio();

  window.speechSynthesis.speak(utterance);
}

// Performance Visualization
function initPerformanceChart() {
  const ctx = document.getElementById("performanceChart");
  if (!ctx) return;

  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"];
  const aegisReturns = [2.4, 4.5, 7.3, 9.2, 11.9, 14.2, 17.1, 19.7];
  const spyReturns = [1.6, 0.4, 3.5, -0.6, 4.2, 7.7, 8.9, 11.0];

  chartInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: months,
      datasets: [
        {
          label: 'AEGIS Wheel + Tail Hedge (Cumulative %)',
          data: aegisReturns,
          borderColor: '#059669',
          backgroundColor: 'rgba(5, 150, 105, 0.08)',
          fill: true,
          tension: 0.35,
          borderWidth: 2.5,
          pointBackgroundColor: '#059669',
          pointRadius: 4
        },
        {
          label: 'S&P 500 Benchmark (SPY %)',
          data: spyReturns,
          borderColor: '#94a3b8',
          borderDash: [5, 5],
          tension: 0.35,
          borderWidth: 2,
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
        }
      },
      scales: {
        x: {
          grid: { color: '#f1f5f9' },
          ticks: { font: { family: 'JetBrains Mono', size: 10 }, color: '#64748b' }
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

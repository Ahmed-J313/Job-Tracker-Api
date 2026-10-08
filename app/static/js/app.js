(function () {
  "use strict";

  const STATUSES = ["applied", "interviewing", "offer", "rejected"];
  const STATUS_LABELS = {
    applied: "Applied",
    interviewing: "Interviewing",
    offer: "Offer",
    rejected: "Rejected",
  };

  const state = {
    token: localStorage.getItem("jt_token"),
    email: localStorage.getItem("jt_email") || "",
    statusFilter: "",
    search: "",
    editingId: null,
    gmailConnected: false,
  };

  // ---------- DOM refs ----------
  const authView = document.getElementById("auth-view");
  const appView = document.getElementById("app-view");

  const loginForm = document.getElementById("login-form");
  const registerForm = document.getElementById("register-form");
  const forgotForm = document.getElementById("forgot-form");
  const resetForm = document.getElementById("reset-form");
  const loginError = document.getElementById("login-error");
  const registerError = document.getElementById("register-error");
  const forgotError = document.getElementById("forgot-error");
  const forgotMessage = document.getElementById("forgot-message");
  const resetError = document.getElementById("reset-error");
  const resetMessage = document.getElementById("reset-message");

  const loginSubmitBtn = loginForm.querySelector('button[type="submit"]');
  const registerSubmitBtn = registerForm.querySelector('button[type="submit"]');
  const forgotSubmitBtn = forgotForm.querySelector('button[type="submit"]');
  const resetSubmitBtn = resetForm.querySelector('button[type="submit"]');

  const authTabsEl = document.querySelector(".auth-tabs");
  const authOAuthSection = document.getElementById("auth-oauth-section");
  const forgotPasswordLink = document.getElementById("forgot-password-link");
  const backToLoginFromForgot = document.getElementById("back-to-login-from-forgot");
  const backToLoginFromReset = document.getElementById("back-to-login-from-reset");

  const urlToken = new URLSearchParams(window.location.search).get("token");

  const accountEmailEl = document.getElementById("account-email");
  const accountBtn = document.getElementById("account-btn");
  const accountDropdown = document.getElementById("account-dropdown");
  const signoutBtn = document.getElementById("signout-btn");

  const connectGmailBtn = document.getElementById("connect-gmail-btn");
  const connectGmailLabel = document.getElementById("connect-gmail-label");
  const connectGmailBadge = document.getElementById("connect-gmail-badge");
  const gmailOnboardingModal = document.getElementById("gmail-onboarding-modal");
  const gmailOnboardingSkip = document.getElementById("gmail-onboarding-skip");
  const gmailOnboardingConnect = document.getElementById("gmail-onboarding-connect");
  const toastEl = document.getElementById("toast");

  const syncGmailBtn = document.getElementById("sync-gmail-btn");
  const syncGmailHint = document.getElementById("sync-gmail-hint");
  const reviewItemsList = document.getElementById("review-items-list");
  const reviewEmptyState = document.getElementById("review-empty-state");
  const reviewBadge = document.getElementById("review-badge");
  const reviewBulkBar = document.getElementById("review-bulk-bar");
  const reviewBulkCount = document.getElementById("review-bulk-count");
  const reviewBulkAddBtn = document.getElementById("review-bulk-add-btn");
  const selectedSuggestionIds = new Set();

  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");

  const statusFilterBtn = document.getElementById("status-filter-btn");
  const statusFilterMenu = document.getElementById("status-filter-menu");
  const statusFilterLabel = document.getElementById("status-filter-label");
  const statusFilterItems = document.querySelectorAll("#status-filter-menu .dropdown-item");
  const searchInput = document.getElementById("search-input");
  const tbody = document.getElementById("applications-tbody");
  const emptyState = document.getElementById("empty-state");

  const recentList = document.getElementById("recent-activity-list");
  const recentEmptyState = document.getElementById("recent-empty-state");

  const addBtn = document.getElementById("add-application-btn");
  const modal = document.getElementById("application-modal");
  const modalTitle = document.getElementById("modal-title");
  const appForm = document.getElementById("application-form");
  const appFormError = document.getElementById("application-form-error");
  const modalCancelBtn = document.getElementById("modal-cancel-btn");

  const statusPopover = document.getElementById("status-popover");

  const googleSigninContainer = document.getElementById("google-signin-container");
  const GOOGLE_CLIENT_ID = document.body.dataset.googleClientId || "";

  const EMPTY_ICON_SVG = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 7l1.5-3h15L21 7" />
    <path d="M3 7v11a1 1 0 001 1h16a1 1 0 001-1V7" />
    <path d="M3 7h18" />
    <path d="M9 11a3 3 0 006 0" />
  </svg>`;

  function buildEmptyState(container, { title, subtitle, actionLabel, onAction, variant = "primary" }) {
    container.innerHTML = "";

    const icon = document.createElement("div");
    icon.className = "empty-state-icon";
    icon.innerHTML = EMPTY_ICON_SVG;
    container.appendChild(icon);

    const titleEl = document.createElement("p");
    titleEl.className = "empty-state-title";
    titleEl.textContent = title;
    container.appendChild(titleEl);

    if (subtitle) {
      const subtitleEl = document.createElement("p");
      subtitleEl.className = "empty-state-subtitle";
      subtitleEl.textContent = subtitle;
      container.appendChild(subtitleEl);
    }

    if (actionLabel && onAction) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = variant === "secondary" ? "btn-secondary" : "btn-primary";
      btn.textContent = actionLabel;
      btn.addEventListener("click", onAction);
      container.appendChild(btn);
    }
  }

  // ---------- API helper ----------
  async function api(path, options = {}) {
    const headers = Object.assign({}, options.headers);
    if (options.body) headers["Content-Type"] = "application/json";
    if (state.token) headers["Authorization"] = "Bearer " + state.token;

    const res = await fetch("/api" + path, Object.assign({}, options, { headers }));

    if (res.status === 401 && state.token) {
      signOut();
      throw new Error("Session expired, please sign in again.");
    }

    let data = null;
    const text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (_) { data = null; }
    }

    if (!res.ok) {
      const message = (data && data.error) || "Something went wrong.";
      throw new Error(message);
    }
    return data;
  }

  // ---------- Auth view ----------
  function setLoading(btn, isLoading, loadingText) {
    if (isLoading) {
      if (!btn.dataset.originalText) btn.dataset.originalText = btn.textContent;
      btn.disabled = true;
      btn.textContent = loadingText;
    } else {
      btn.disabled = false;
      if (btn.dataset.originalText) btn.textContent = btn.dataset.originalText;
    }
  }

  function showAuthSubview(view) {
    loginForm.hidden = view !== "login";
    registerForm.hidden = view !== "register";
    forgotForm.hidden = view !== "forgot";
    resetForm.hidden = view !== "reset";
    authTabsEl.hidden = view === "forgot" || view === "reset";
    authOAuthSection.hidden = view === "forgot" || view === "reset";
    loginError.textContent = "";
    registerError.textContent = "";
    forgotError.textContent = "";
    forgotMessage.textContent = "";
    resetError.textContent = "";
    resetMessage.textContent = "";
  }

  document.querySelectorAll(".auth-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".auth-tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      showAuthSubview(btn.dataset.authTab);
    });
  });

  function setActiveAuthTab(target) {
    document.querySelectorAll(".auth-tab-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.authTab === target);
    });
  }

  forgotPasswordLink.addEventListener("click", () => showAuthSubview("forgot"));

  backToLoginFromForgot.addEventListener("click", () => {
    setActiveAuthTab("login");
    showAuthSubview("login");
  });

  function returnToLoginAfterReset() {
    setActiveAuthTab("login");
    window.history.replaceState({}, "", "/");
    showAuthSubview("login");
  }

  backToLoginFromReset.addEventListener("click", returnToLoginAfterReset);

  document.querySelectorAll(".password-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = document.getElementById(btn.dataset.target);
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Hide" : "Show";
    });
  });

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.textContent = "";
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;
    setLoading(loginSubmitBtn, true, "Signing in...");
    try {
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      signIn(data.access_token, email);
    } catch (err) {
      loginError.textContent = err.message;
    } finally {
      setLoading(loginSubmitBtn, false);
    }
  });

  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    registerError.textContent = "";
    const email = document.getElementById("register-email").value.trim();
    const password = document.getElementById("register-password").value;
    const confirmPassword = document.getElementById("register-confirm-password").value;
    if (password !== confirmPassword) {
      registerError.textContent = "Passwords do not match.";
      return;
    }
    setLoading(registerSubmitBtn, true, "Creating account...");
    try {
      await api("/auth/register", {
        method: "POST",
        body: JSON.stringify({ email, password, confirm_password: confirmPassword }),
      });
      const data = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      signIn(data.access_token, email);
    } catch (err) {
      registerError.textContent = err.message;
    } finally {
      setLoading(registerSubmitBtn, false);
    }
  });

  forgotForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    forgotError.textContent = "";
    forgotMessage.textContent = "";
    const email = document.getElementById("forgot-email").value.trim();
    setLoading(forgotSubmitBtn, true, "Sending...");
    try {
      const data = await api("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      forgotMessage.textContent = data.message;
    } catch (err) {
      forgotError.textContent = err.message;
    } finally {
      setLoading(forgotSubmitBtn, false);
    }
  });

  resetForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    resetError.textContent = "";
    resetMessage.textContent = "";
    const newPassword = document.getElementById("reset-password").value;
    const confirmPassword = document.getElementById("reset-confirm-password").value;
    if (newPassword !== confirmPassword) {
      resetError.textContent = "Passwords do not match.";
      return;
    }
    setLoading(resetSubmitBtn, true, "Updating password...");
    try {
      const data = await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token: urlToken, new_password: newPassword }),
      });
      resetMessage.textContent = data.message;
      resetForm.reset();
      setTimeout(returnToLoginAfterReset, 1500);
    } catch (err) {
      resetError.textContent = err.message;
    } finally {
      setLoading(resetSubmitBtn, false);
    }
  });

  async function handleGoogleCredentialResponse(response) {
    loginError.textContent = "";
    try {
      const data = await api("/auth/google", {
        method: "POST",
        body: JSON.stringify({ credential: response.credential }),
      });
      signIn(data.access_token, data.email, { offerGmailOnboarding: data.is_new_user });
    } catch (err) {
      loginError.textContent = err.message;
    }
  }

  function initGoogleSignIn() {
    if (!GOOGLE_CLIENT_ID || !window.google || !window.google.accounts) return;
    google.accounts.id.initialize({
      client_id: GOOGLE_CLIENT_ID,
      callback: handleGoogleCredentialResponse,
    });
    google.accounts.id.renderButton(googleSigninContainer, {
      theme: "outline",
      size: "large",
      width: 320,
    });
  }

  if (window.google && window.google.accounts && window.google.accounts.id) {
    initGoogleSignIn();
  } else {
    const gsiScript = document.getElementById("google-identity-script");
    if (gsiScript) gsiScript.addEventListener("load", initGoogleSignIn);
  }

  function signIn(token, email, { offerGmailOnboarding = false } = {}) {
    state.token = token;
    state.email = email;
    localStorage.setItem("jt_token", token);
    localStorage.setItem("jt_email", email);
    showAppView();
    if (offerGmailOnboarding) {
      gmailOnboardingModal.hidden = false;
    }
  }

  function signOut() {
    state.token = null;
    localStorage.removeItem("jt_token");
    localStorage.removeItem("jt_email");
    showAuthView();
    setActiveAuthTab("login");
    showAuthSubview("login");
  }

  signoutBtn.addEventListener("click", signOut);

  // ---------- View switching ----------
  function showAuthView() {
    authView.hidden = false;
    appView.hidden = true;
  }

  function showAppView() {
    authView.hidden = true;
    appView.hidden = false;
    accountEmailEl.textContent = state.email || "account";
    loadDashboard();
    loadApplications();
    loadGmailStatus();
    loadReviewItems();
  }

  // ---------- Account dropdown ----------
  accountBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    accountDropdown.hidden = !accountDropdown.hidden;
  });

  document.addEventListener("click", () => {
    accountDropdown.hidden = true;
    statusPopover.hidden = true;
    statusFilterMenu.hidden = true;
  });

  // ---------- Toast ----------
  let toastTimeout;
  function showToast(message, isError = false) {
    clearTimeout(toastTimeout);
    toastEl.textContent = message;
    toastEl.classList.toggle("toast-error", isError);
    toastEl.hidden = false;
    toastTimeout = setTimeout(() => {
      toastEl.hidden = true;
    }, 4000);
  }

  // ---------- Gmail connect ----------
  function setGmailConnected(connected) {
    state.gmailConnected = connected;
    connectGmailLabel.textContent = connected ? "Disconnect Gmail" : "Connect Gmail";
    connectGmailBadge.hidden = !connected;
  }

  async function loadGmailStatus() {
    try {
      const data = await api("/gmail/status");
      setGmailConnected(data.connected);
    } catch (err) {
      // non-critical, leave the button in its last known state
    }
  }

  async function startGmailConnect() {
    try {
      const data = await api("/gmail/connect");
      window.location.href = data.auth_url;
    } catch (err) {
      showToast(err.message, true);
    }
  }

  connectGmailBtn.addEventListener("click", async () => {
    accountDropdown.hidden = true;
    if (state.gmailConnected) {
      try {
        await api("/gmail/disconnect", { method: "POST" });
        setGmailConnected(false);
        showToast("Gmail disconnected.");
      } catch (err) {
        showToast(err.message, true);
      }
    } else {
      startGmailConnect();
    }
  });

  gmailOnboardingSkip.addEventListener("click", () => {
    gmailOnboardingModal.hidden = true;
  });

  gmailOnboardingConnect.addEventListener("click", () => {
    gmailOnboardingModal.hidden = true;
    startGmailConnect();
  });

  const gmailCallbackParam = new URLSearchParams(window.location.search);
  if (gmailCallbackParam.has("gmail_connected")) {
    window.history.replaceState({}, "", "/");
    showToast("Gmail connected.");
  } else if (gmailCallbackParam.has("gmail_connect_error")) {
    window.history.replaceState({}, "", "/");
    showToast("Couldn't connect Gmail. Try again from the account menu.", true);
  }

  // ---------- Tabs ----------
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      tabPanels.forEach((panel) => panel.classList.remove("active"));
      document.getElementById("tab-" + btn.dataset.tab).classList.add("active");

      if (btn.dataset.tab === "dashboard") loadDashboard();
      if (btn.dataset.tab === "applications") loadApplications();
      if (btn.dataset.tab === "review") loadReviewItems();
    });
  });

  // ---------- Review ----------
  function updateBulkBar() {
    reviewBulkBar.hidden = selectedSuggestionIds.size === 0;
    reviewBulkCount.textContent = `${selectedSuggestionIds.size} selected`;
  }

  function renderReviewItems(items) {
    reviewItemsList.innerHTML = "";
    reviewEmptyState.hidden = items.length > 0;
    reviewBadge.hidden = items.length === 0;
    reviewBadge.textContent = String(items.length);

    const liveIds = new Set(items.map((item) => item.id));
    for (const id of Array.from(selectedSuggestionIds)) {
      if (!liveIds.has(id)) selectedSuggestionIds.delete(id);
    }
    updateBulkBar();

    if (items.length === 0) {
      buildEmptyState(reviewEmptyState, {
        title: "Nothing to review",
        subtitle: "Emails Prospect isn't sure about will show up here.",
      });
      return;
    }

    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "review-item";
      if (item.kind === "new_application") li.classList.add("review-item-suggestion");

      const subject = document.createElement("div");
      subject.className = "review-item-subject";
      subject.textContent = item.subject || "(no subject)";
      li.appendChild(subject);

      const meta = document.createElement("div");
      meta.className = "review-item-meta";
      meta.textContent = item.sender || "";
      li.appendChild(meta);

      if (item.snippet) {
        const snippet = document.createElement("p");
        snippet.className = "review-item-snippet";
        snippet.textContent = item.snippet;
        li.appendChild(snippet);
      }

      const reason = document.createElement("p");
      reason.className = "review-item-reason";
      reason.textContent = item.reason;
      li.appendChild(reason);

      const actions = document.createElement("div");
      actions.className = "review-item-actions";

      const dismissBtn = document.createElement("button");
      dismissBtn.type = "button";
      dismissBtn.className = "btn-secondary";
      dismissBtn.textContent = "Dismiss";
      dismissBtn.addEventListener("click", () => resolveReviewItem(item.id, "dismiss"));

      if (item.kind === "new_application") {
        const suggestionRow = document.createElement("div");
        suggestionRow.className = "review-item-suggestion-row";

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "review-item-checkbox";
        checkbox.checked = selectedSuggestionIds.has(item.id);
        checkbox.addEventListener("change", () => {
          if (checkbox.checked) selectedSuggestionIds.add(item.id);
          else selectedSuggestionIds.delete(item.id);
          updateBulkBar();
        });
        suggestionRow.appendChild(checkbox);

        const suggestion = document.createElement("p");
        suggestion.className = "review-item-suggestion-label";
        suggestion.textContent = `Looks like a new application: ${item.suggested_company} - ${item.suggested_role}`;
        suggestionRow.appendChild(suggestion);

        li.appendChild(suggestionRow);

        const addBtn = document.createElement("button");
        addBtn.type = "button";
        addBtn.className = "btn-primary";
        addBtn.textContent = "Add as application";
        addBtn.addEventListener("click", () => resolveReviewItem(item.id, "create-application"));

        actions.appendChild(dismissBtn);
        actions.appendChild(addBtn);
      } else {
        const resolveBtn = document.createElement("button");
        resolveBtn.type = "button";
        resolveBtn.className = "btn-primary";
        resolveBtn.textContent = "Mark resolved";
        resolveBtn.addEventListener("click", () => resolveReviewItem(item.id, "resolve"));

        actions.appendChild(dismissBtn);
        actions.appendChild(resolveBtn);
      }
      li.appendChild(actions);

      reviewItemsList.appendChild(li);
    });
  }

  async function loadReviewItems() {
    try {
      const items = await api("/gmail/review-items");
      renderReviewItems(items);
    } catch (err) {
      // non-critical, leave the list as-is
    }
  }

  async function resolveReviewItem(id, action) {
    try {
      await api(`/gmail/review-items/${id}/${action}`, { method: "POST" });
      loadReviewItems();
      if (action === "create-application") {
        loadApplications();
        loadDashboard();
      }
    } catch (err) {
      showToast(err.message, true);
    }
  }

  reviewBulkAddBtn.addEventListener("click", async () => {
    const itemIds = Array.from(selectedSuggestionIds);
    if (itemIds.length === 0) return;
    setLoading(reviewBulkAddBtn, true, "Adding...");
    try {
      const data = await api("/gmail/review-items/bulk-create-applications", {
        method: "POST",
        body: JSON.stringify({ item_ids: itemIds }),
      });
      selectedSuggestionIds.clear();
      showToast(
        data.skipped_ids.length
          ? `Added ${data.created}, skipped ${data.skipped_ids.length}.`
          : `Added ${data.created} application${data.created === 1 ? "" : "s"}.`
      );
      loadReviewItems();
      loadApplications();
      loadDashboard();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      setLoading(reviewBulkAddBtn, false);
    }
  });

  syncGmailBtn.addEventListener("click", async () => {
    setLoading(syncGmailBtn, true, "Syncing...");
    syncGmailHint.textContent = "";
    try {
      const data = await api("/gmail/sync", { method: "POST" });
      syncGmailHint.textContent =
        `Scanned ${data.scanned} - ${data.updated.length} updated, ${data.needs_review} need review, ${data.skipped} skipped.`;
      loadReviewItems();
      loadDashboard();
      loadApplications();
    } catch (err) {
      syncGmailHint.textContent = err.message;
    } finally {
      setLoading(syncGmailBtn, false);
    }
  });

  // ---------- Dashboard ----------
  async function loadDashboard() {
    try {
      const stats = await api("/applications/stats");
      STATUSES.forEach((status) => {
        document.getElementById("stat-" + status).textContent = stats[status] || 0;
      });

      const apps = await api("/applications");
      renderRecentActivity(apps.slice(0, 5));
    } catch (err) {
      // stay silent on dashboard load errors beyond session expiry (handled in api())
    }
  }

  function renderRecentActivity(apps) {
    recentList.innerHTML = "";
    recentEmptyState.hidden = apps.length > 0;

    if (apps.length === 0) {
      buildEmptyState(recentEmptyState, {
        title: "Nothing yet",
        subtitle: "Add your first application and it'll show up here.",
      });
    }

    apps.forEach((app) => {
      const li = document.createElement("li");
      li.className = "recent-item";

      const left = document.createElement("span");
      left.textContent = `${app.company} · ${app.role_title}`;

      const right = document.createElement("span");
      right.className = "recent-item-meta";
      right.textContent = STATUS_LABELS[app.status] + (app.date_applied ? " · " + app.date_applied : "");

      li.appendChild(left);
      li.appendChild(right);
      recentList.appendChild(li);
    });
  }

  // ---------- Applications tab ----------
  statusFilterBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    statusFilterMenu.hidden = !statusFilterMenu.hidden;
  });

  function setStatusFilter(status) {
    state.statusFilter = status;
    statusFilterItems.forEach((item) => {
      item.classList.toggle("active", item.dataset.status === status);
    });
    statusFilterLabel.textContent = status ? STATUS_LABELS[status] : "All statuses";
  }

  statusFilterItems.forEach((item) => {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      setStatusFilter(item.dataset.status);
      statusFilterMenu.hidden = true;
      loadApplications();
    });
  });

  let searchDebounce;
  searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.search = searchInput.value.trim();
      loadApplications();
    }, 250);
  });

  async function loadApplications() {
    const params = new URLSearchParams();
    if (state.statusFilter) params.set("status", state.statusFilter);
    if (state.search) params.set("search", state.search);
    const qs = params.toString();

    try {
      const apps = await api("/applications" + (qs ? "?" + qs : ""));
      renderApplications(apps);
    } catch (err) {
      // session-expiry already redirected; otherwise just leave the table as-is
    }
  }

  function renderApplications(apps) {
    tbody.innerHTML = "";
    emptyState.hidden = apps.length > 0;

    if (apps.length === 0) {
      const noFiltersActive = !state.statusFilter && !state.search;
      if (noFiltersActive) {
        buildEmptyState(emptyState, {
          title: "Your list starts here",
          subtitle: "Add the first role you applied to. Everything else builds from there.",
        });
      } else {
        buildEmptyState(emptyState, {
          title: "No matches",
          subtitle: "Nothing fits that filter or search right now.",
          actionLabel: "Clear filters",
          variant: "secondary",
          onAction: () => {
            setStatusFilter("");
            state.search = "";
            searchInput.value = "";
            loadApplications();
          },
        });
      }
    }

    apps.forEach((app) => {
      const tr = document.createElement("tr");

      const companyTd = document.createElement("td");
      companyTd.appendChild(document.createTextNode(app.company));
      if (app.sync_updated_at) {
        const syncedBadge = document.createElement("span");
        syncedBadge.className = "synced-badge";
        syncedBadge.textContent = "synced";
        syncedBadge.title = "Last updated automatically by Gmail sync";
        companyTd.appendChild(syncedBadge);
      }
      tr.appendChild(companyTd);

      tr.appendChild(cell(app.role_title));
      tr.appendChild(cell(app.platform || "—"));

      const statusTd = document.createElement("td");
      const pillBtn = document.createElement("button");
      pillBtn.type = "button";
      pillBtn.className = "status-pill status-" + app.status;
      pillBtn.textContent = STATUS_LABELS[app.status];
      pillBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openStatusPopover(pillBtn, app);
      });
      statusTd.appendChild(pillBtn);
      tr.appendChild(statusTd);

      tr.appendChild(cell(app.date_applied || "—"));

      const actionsTd = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "row-actions";

      const editBtn = document.createElement("button");
      editBtn.type = "button";
      editBtn.className = "row-action-btn";
      editBtn.textContent = "Edit";
      editBtn.addEventListener("click", () => openModal(app));

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "row-action-btn danger";
      deleteBtn.textContent = "Delete";
      deleteBtn.addEventListener("click", () => deleteApplication(app.id));

      actions.appendChild(editBtn);
      actions.appendChild(deleteBtn);
      actionsTd.appendChild(actions);
      tr.appendChild(actionsTd);

      tbody.appendChild(tr);
    });
  }

  function cell(text) {
    const td = document.createElement("td");
    td.textContent = text;
    return td;
  }

  function openStatusPopover(anchorEl, app) {
    const rect = anchorEl.getBoundingClientRect();
    statusPopover.innerHTML = "";
    statusPopover.style.top = window.scrollY + rect.bottom + 6 + "px";
    statusPopover.style.left = window.scrollX + rect.left + "px";

    STATUSES.forEach((status) => {
      if (status === app.status) return;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = STATUS_LABELS[status];
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        statusPopover.hidden = true;
        try {
          await api("/applications/" + app.id, {
            method: "PUT",
            body: JSON.stringify({ status }),
          });
          loadApplications();
          loadDashboard();
        } catch (err) {
          alert(err.message);
        }
      });
      statusPopover.appendChild(btn);
    });

    statusPopover.hidden = false;
  }

  async function deleteApplication(id) {
    if (!confirm("Delete this application?")) return;
    try {
      await api("/applications/" + id, { method: "DELETE" });
      loadApplications();
      loadDashboard();
    } catch (err) {
      alert(err.message);
    }
  }

  // ---------- Add / edit modal ----------
  addBtn.addEventListener("click", () => openModal(null));
  modalCancelBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  function openModal(app) {
    appFormError.textContent = "";
    state.editingId = app ? app.id : null;
    modalTitle.textContent = app ? "Edit application" : "Add application";

    document.getElementById("form-company").value = app ? app.company : "";
    document.getElementById("form-role").value = app ? app.role_title : "";
    document.getElementById("form-platform").value = app ? app.platform || "" : "";
    document.getElementById("form-date").value = app ? app.date_applied || "" : "";
    document.getElementById("form-job-url").value = app ? app.job_url || "" : "";
    document.getElementById("form-notes").value = app ? app.notes || "" : "";

    modal.hidden = false;
  }

  function closeModal() {
    modal.hidden = true;
  }

  appForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    appFormError.textContent = "";

    const payload = {
      company: document.getElementById("form-company").value.trim(),
      role_title: document.getElementById("form-role").value.trim(),
      platform: document.getElementById("form-platform").value.trim() || null,
      date_applied: document.getElementById("form-date").value || null,
      job_url: document.getElementById("form-job-url").value.trim() || null,
      notes: document.getElementById("form-notes").value.trim() || null,
    };

    try {
      if (state.editingId) {
        await api("/applications/" + state.editingId, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
      } else {
        await api("/applications", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      closeModal();
      loadApplications();
      loadDashboard();
    } catch (err) {
      appFormError.textContent = err.message;
    }
  });

  // ---------- Boot ----------
  if (urlToken) {
    showAuthView();
    showAuthSubview("reset");
  } else if (state.token) {
    showAppView();
  } else {
    showAuthView();
    showAuthSubview("login");
  }
})();

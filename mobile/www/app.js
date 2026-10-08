/** 浏览器预览用 localStorage；真机用 Capacitor Preferences */
const Preferences = await (async () => {
  try {
    const mod = await import("@capacitor/preferences");
    return mod.Preferences;
  } catch {
    return {
      async get({ key }) {
        return { value: localStorage.getItem(key) };
      },
      async set({ key, value }) {
        localStorage.setItem(key, value);
      },
    };
  }
})();

const KEYS = { hubUrl: "hub_url", sessionId: "session_id", accessToken: "access_token" };
const DEFAULT_HUB = "http://127.0.0.1:8787";

const MODE_HINTS = {
  项目: "点左上角选择项目，或直接发任务标题",
  联通: "查看电脑 / Agent 是否在线",
  帮助: "查看全部 Bot 指令",
};

let hubUrl = DEFAULT_HUB;
let sessionId = "default";
let accessToken = "";
let hasChat = false;
let cachedProjects = [];
let selectedKey = "";
let updatesSinceId = 0;
let updatesTimer = null;
const seenReplyIds = new Set();

const chatEl = document.getElementById("chat");
const welcomeEl = document.getElementById("welcome");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("btnSend");
const drawer = document.getElementById("projectDrawer");
const backdrop = document.getElementById("drawerBackdrop");

async function loadSettings() {
  const h = await Preferences.get({ key: KEYS.hubUrl });
  const s = await Preferences.get({ key: KEYS.sessionId });
  const t = await Preferences.get({ key: KEYS.accessToken });
  hubUrl = h.value || DEFAULT_HUB;
  sessionId = s.value || "default";
  accessToken = t.value || "";
  document.getElementById("hubUrl").value = hubUrl;
  document.getElementById("sessionId").value = sessionId;
  const tok = document.getElementById("accessToken");
  if (tok) tok.value = accessToken;
  refreshInviteCode();
  updateDrawerMeta();
}

async function saveSettings() {
  hubUrl = document.getElementById("hubUrl").value.trim() || DEFAULT_HUB;
  sessionId = document.getElementById("sessionId").value.trim() || "default";
  accessToken = (document.getElementById("accessToken")?.value || "").trim();
  await Preferences.set({ key: KEYS.hubUrl, value: hubUrl });
  await Preferences.set({ key: KEYS.sessionId, value: sessionId });
  await Preferences.set({ key: KEYS.accessToken, value: accessToken });
  refreshInviteCode();
  updateDrawerMeta();
}

function parseConnectionPaste(text) {
  const raw = text || "";
  const url =
    (raw.match(/电脑连接地址[：:]\s*(\S+)/) || [])[1] ||
    (raw.match(/Hub[：:]\s*(\S+)/i) || [])[1] ||
    (raw.match(/https?:\/\/\S+/) || [])[0] ||
    "";
  const token =
    (raw.match(/连接密码[：:]\s*(\S+)/) || [])[1] ||
    (raw.match(/密码[：:]\s*(\S+)/) || [])[1] ||
    "";
  const sid =
    (raw.match(/会话\s*ID[：:]\s*(\S+)/i) || [])[1] ||
    (raw.match(/session[：:]\s*(\S+)/i) || [])[1] ||
    "";
  return {
    hubUrl: (url || "").replace(/[，,。.\s]+$/, ""),
    accessToken: token,
    sessionId: sid,
  };
}

function shortHub(url) {
  try {
    const u = new URL(url);
    return `${u.hostname}${u.port ? ":" + u.port : ""}`;
  } catch {
    return url;
  }
}

function setHubLabel(connected) {
  document.getElementById("hubLabel").textContent = connected
    ? `已连接 · ${shortHub(hubUrl)}`
    : `未连接 · ${shortHub(hubUrl)}`;
}

function updateDrawerMeta() {
  document.getElementById("drawerSessionHint").textContent = `会话 ${sessionId} · ${shortHub(hubUrl)}`;
}

function refreshInviteCode() {
  const note = document.getElementById("inviteName")?.value?.trim();
  const lines = [
    "【联合器 · 手机连接】",
    note ? `备注：${note}` : null,
    `电脑连接地址：${hubUrl}`,
    accessToken ? `连接密码：${accessToken}` : null,
    `会话 ID：${sessionId}`,
    "打开联合器 App → 设置 → 粘贴以上全部内容 → 保存。",
  ].filter(Boolean);
  document.getElementById("inviteCode").textContent = lines.join("\n");
}

async function api(path, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };
  if (accessToken) headers["X-Unifier-Token"] = accessToken;
  const res = await fetch(`${hubUrl.replace(/\/$/, "")}${path}`, {
    ...options,
    headers,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { text };
  }
  if (res.status === 401) {
    throw new Error(
      (data && data.message) || "连接密码不对，回电脑重新复制后再试",
    );
  }
  if (!res.ok) {
    const detail =
      (data && (data.message || data.detail)) ||
      text ||
      res.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function showChat() {
  if (hasChat) return;
  hasChat = true;
  welcomeEl.classList.add("hidden");
  chatEl.classList.remove("hidden");
}

function clearChat() {
  hasChat = false;
  chatEl.innerHTML = "";
  chatEl.classList.add("hidden");
  welcomeEl.classList.remove("hidden");
  closeDrawer();
}

function addBubble(role, text, opts = {}) {
  showChat();
  const wrap = document.createElement("article");
  wrap.className = `msg ${role}`;
  const body = document.createElement("div");
  body.className = "body";
  body.textContent = text;
  wrap.appendChild(body);
  if (opts.needsConfirm && opts.taskId) {
    const actions = document.createElement("div");
    actions.className = "msg-actions";
    const btnOk = document.createElement("button");
    btnOk.type = "button";
    btnOk.className = "chip-action primary";
    btnOk.textContent = "确认执行";
    btnOk.addEventListener("click", () => confirmExec(opts.taskId, "confirm"));
    const btnLater = document.createElement("button");
    btnLater.type = "button";
    btnLater.className = "chip-action";
    btnLater.textContent = "稍后";
    btnLater.addEventListener("click", () => confirmExec(opts.taskId, "defer"));
    actions.appendChild(btnOk);
    actions.appendChild(btnLater);
    wrap.appendChild(actions);
  }
  chatEl.appendChild(wrap);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function confirmExec(taskId, action) {
  try {
    const res = await api("/api/v1/mobile/exec-confirm", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId, task_id: taskId, action }),
    });
    addBubble(
      "system",
      action === "confirm"
        ? `✅ 已确认执行 #${taskId}`
        : `⏸ 任务 #${taskId} 已稍后`,
    );
    if (res?.status) pollUpdates();
  } catch (e) {
    addBubble("bot", `操作失败：${e.message}`);
  }
}

function openDrawer() {
  backdrop.hidden = false;
  requestAnimationFrame(() => {
    backdrop.classList.add("open");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  });
  loadProjectsIntoDrawer();
}

function closeDrawer() {
  backdrop.classList.remove("open");
  drawer.classList.remove("open");
  drawer.setAttribute("aria-hidden", "true");
  setTimeout(() => {
    if (!drawer.classList.contains("open")) backdrop.hidden = true;
  }, 240);
}

function openSettings() {
  closeDrawer();
  refreshInviteCode();
  document.getElementById("inviteCopied").classList.add("hidden");
  document.getElementById("settingsDialog").showModal();
}

function renderProjectList(projects) {
  const list = document.getElementById("projectList");
  const q = (document.getElementById("projectSearch").value || "").trim().toLowerCase();
  const filtered = projects.filter((p) => {
    if (!q) return true;
    const hay = `${p.display_name} ${p.slug} ${p.github_owner}/${p.github_repo}`.toLowerCase();
    return hay.includes(q);
  });

  document.getElementById("projectSectionLabel").textContent = q
    ? `搜索结果 ${filtered.length}`
    : `全部项目 ${filtered.length}`;

  if (!filtered.length) {
    list.innerHTML = `<li style="color:var(--muted)">暂无项目${q ? "匹配" : "，请先连接 Hub"}</li>`;
    return;
  }

  list.innerHTML = filtered
    .map((p) => {
      const key = `${p.github_owner}/${p.github_repo}`;
      const active = key === selectedKey ? "active" : "";
      return `
      <li class="${active}"
          data-owner="${escapeAttr(p.github_owner)}"
          data-repo="${escapeAttr(p.github_repo)}"
          data-name="${escapeAttr(p.display_name)}"
          data-key="${escapeAttr(key)}">
        ${escapeHtml(p.display_name)}
        <span class="slug">${escapeHtml(p.slug || key)}</span>
      </li>`;
    })
    .join("");

  list.querySelectorAll("li[data-owner]").forEach((li) => {
    li.addEventListener("click", async () => {
      selectedKey = li.dataset.key;
      closeDrawer();
      await selectProject(li.dataset.owner, li.dataset.repo, li.dataset.name);
    });
  });
}

async function loadProjectsIntoDrawer() {
  const list = document.getElementById("projectList");
  list.innerHTML = `<li style="color:var(--muted)">加载中…</li>`;
  try {
    const res = await api("/api/v1/mobile/command", {
      method: "POST",
      body: JSON.stringify({ text: "项目", session_id: sessionId }),
    });
    cachedProjects = res.projects || [];
    renderProjectList(cachedProjects);
  } catch (e) {
    list.innerHTML = `<li style="color:var(--muted)">加载失败：${escapeHtml(e.message)}</li>`;
  }
}

/** 命令返回项目列表时，改为打开侧栏而不是弹窗 */
function showProjects(projects) {
  cachedProjects = projects || [];
  openDrawer();
  renderProjectList(cachedProjects);
}

async function selectProject(owner, repo, name) {
  try {
    const res = await api("/api/v1/mobile/select-project", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        github_owner: owner,
        github_repo: repo,
        display_name: name,
      }),
    });
    selectedKey = `${owner}/${repo}`;
    addBubble("bot", res.text);
    refreshProjectBar();
  } catch (e) {
    addBubble("bot", `选择失败：${e.message}`);
  }
}

async function refreshProjectBar() {
  try {
    const res = await api(`/api/v1/mobile/session?session_id=${encodeURIComponent(sessionId)}`);
    const bar = document.getElementById("projectBar");
    const label = document.getElementById("currentProject");
    if (res.current_project && !res.current_project.includes("未选择")) {
      bar.classList.remove("hidden");
      label.textContent = res.current_project.split("\n")[0];
    } else {
      bar.classList.add("hidden");
    }
  } catch {
    document.getElementById("projectBar").classList.add("hidden");
  }
}

async function sendCommand(text) {
  const trimmed = text.trim();
  if (!trimmed) return;

  if (trimmed === "项目" || trimmed.startsWith("项目")) {
    addBubble("user", trimmed);
    inputEl.value = "";
    autoResize();
    updateSend();
    openDrawer();
    return;
  }

  addBubble("user", trimmed);
  inputEl.value = "";
  autoResize();
  updateSend();

  try {
    const res = await api("/api/v1/mobile/command", {
      method: "POST",
      body: JSON.stringify({ text: trimmed, session_id: sessionId }),
    });
    if (res.text) addBubble("bot", res.text);
    if (res.projects?.length) showProjects(res.projects);
    if (res.kind === "dispatch" || res.kind === "select_project" || res.kind === "current_project") {
      refreshProjectBar();
    }
    if (res.task_id && res.kind === "dispatch") {
      setTimeout(() => pollTask(res.task_id), 3000);
      startUpdatesPolling();
    }
  } catch (e) {
    addBubble("bot", `错误：${e.message}`);
  }
}

async function pollTask(taskId) {
  try {
    const res = await api(`/api/v1/orchestrate/tasks/${taskId}/status`);
    if (res.message) addBubble("system", `任务 #${taskId}\n${res.message}`);
  } catch {
    /* ignore */
  }
}

/** P0：任务通知流 — 与飞书三件套同源，弹进气泡 */
async function pollUpdates() {
  try {
    const res = await api(
      `/api/v1/mobile/updates?session_id=${encodeURIComponent(sessionId)}&since_id=${updatesSinceId}`,
    );
    for (const item of res.items || []) {
      if (seenReplyIds.has(item.id)) continue;
      seenReplyIds.add(item.id);
      const role = item.kind === "lifecycle" || item.kind === "status" ? "system" : "bot";
      addBubble(role, item.content, {
        needsConfirm: !!item.needs_confirm,
        taskId: item.task_id,
      });
    }
    if (typeof res.next_since_id === "number") {
      updatesSinceId = res.next_since_id;
    }
  } catch {
    /* Hub 未连时静默 */
  }
}

function startUpdatesPolling() {
  if (updatesTimer) return;
  pollUpdates();
  updatesTimer = setInterval(pollUpdates, 3000);
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, "&quot;");
}

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 120)}px`;
}

function updateSend() {
  sendBtn.disabled = !inputEl.value.trim();
}

async function init() {
  await loadSettings();
  setHubLabel(false);

  try {
    await api("/health");
    setHubLabel(true);
    refreshProjectBar();
    startUpdatesPolling();
  } catch {
    setHubLabel(false);
  }

  inputEl.addEventListener("input", () => {
    autoResize();
    updateSend();
  });
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendCommand(inputEl.value);
    }
  });
  sendBtn.addEventListener("click", () => sendCommand(inputEl.value));

  document.querySelectorAll("#modes .mode").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#modes .mode").forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", b === btn ? "true" : "false");
      });
      const cmd = btn.dataset.cmd;
      document.getElementById("modeHint").textContent = MODE_HINTS[cmd] || "";
      if (btn.dataset.action === "drawer") {
        openDrawer();
        return;
      }
      sendCommand(cmd);
    });
  });

  document.querySelectorAll(".tool-chips .chip").forEach((btn) => {
    btn.addEventListener("click", () => sendCommand(btn.dataset.cmd));
  });

  // 左上角：项目侧栏
  document.getElementById("btnSettings").addEventListener("click", openDrawer);
  backdrop.addEventListener("click", closeDrawer);
  document.getElementById("btnClearChat").addEventListener("click", clearChat);
  document.getElementById("btnDrawerMore").addEventListener("click", openSettings);
  document.getElementById("projectSearch").addEventListener("input", () => {
    renderProjectList(cachedProjects);
  });

  // 右上角：设置 + 邀请
  document.getElementById("btnNewChat").addEventListener("click", openSettings);

  document.getElementById("inviteName").addEventListener("input", refreshInviteCode);

  document.getElementById("btnCopyInvite").addEventListener("click", async () => {
    refreshInviteCode();
    const text = document.getElementById("inviteCode").textContent;
    try {
      await navigator.clipboard.writeText(text);
      document.getElementById("inviteCopied").classList.remove("hidden");
    } catch {
      document.getElementById("inviteCopied").textContent = "复制失败，请长按手动复制";
      document.getElementById("inviteCopied").classList.remove("hidden");
    }
  });

  document.getElementById("btnSaveSettings").addEventListener("click", async (e) => {
    e.preventDefault();
    await saveSettings();
    try {
      const h = await api("/health");
      // 有连接密码时再验一条需鉴权接口
      if (accessToken) {
        await api(`/api/v1/mobile/session?session_id=${encodeURIComponent(sessionId)}`);
      }
      document.getElementById("healthResult").textContent =
        "已连接" + (h && h.service ? ` · ${h.service}` : "");
      setHubLabel(true);
      addBubble("system", "已连上电脑");
      refreshProjectBar();
    } catch (err) {
      setHubLabel(false);
      document.getElementById("healthResult").textContent =
        err.message || "连不上电脑，请确认电脑上联合器已打开";
    }
  });

  const btnPaste = document.getElementById("btnParsePaste");
  if (btnPaste) {
    btnPaste.addEventListener("click", () => {
      const raw = document.getElementById("pasteBlock")?.value || "";
      const parsed = parseConnectionPaste(raw);
      if (parsed.hubUrl) document.getElementById("hubUrl").value = parsed.hubUrl;
      if (parsed.accessToken) document.getElementById("accessToken").value = parsed.accessToken;
      if (parsed.sessionId) document.getElementById("sessionId").value = parsed.sessionId;
      document.getElementById("healthResult").textContent = parsed.hubUrl
        ? "已填入，请点「保存并检测」"
        : "没有识别到地址，请检查粘贴内容";
    });
  }
}

init();

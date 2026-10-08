function paint(state) {
  const badge = document.getElementById("edition-badge");
  const isEnt = state.edition === "enterprise" && state.license && state.license.valid;
  badge.textContent = isEnt ? "企业版" : "个人版";
  badge.style.background = isEnt ? "#8957e5" : "#238636";

  const daemon = state.daemonRunning ? "运行中" : "未启动";
  document.getElementById("daemon-status").textContent = `守护进程：${daemon}`;
  document.getElementById("hub-status").textContent = state.hubHealthy
    ? "Hub：在线 ●"
    : "Hub：离线 ○（手机将连不上）";
  document.getElementById("hub-status").style.color = state.hubHealthy ? "#3fb950" : "#f85149";

  const cfg = state.config || {};
  const hubUrl = cfg.hubUrl || state.hubUrl || "http://127.0.0.1:8787";
  document.getElementById("hub-link").href = hubUrl;
  document.getElementById("hub-link").textContent = hubUrl;
  document.getElementById("device-status").textContent = `设备 ${cfg.deviceId || state.deviceId || "?"} · 收件箱 ${
    state.inboxRunning ? "在跑" : "未知/未跑"
  }`;

  if (document.getElementById("hub-url") && cfg.hubUrl) {
    document.getElementById("hub-url").value = cfg.hubUrl;
  }
  if (document.getElementById("device-id") && cfg.deviceId) {
    document.getElementById("device-id").value = cfg.deviceId;
  }
  const login = document.getElementById("open-at-login");
  if (login) login.checked = !!cfg.openAtLogin;

  document.getElementById("license-msg").textContent =
    state.license && state.license.valid ? "企业版已激活" : `配置目录：${state.userData || ""}`;
}

async function refresh() {
  const state = await window.unifier.getState();
  paint(state);
}

document.getElementById("btn-start-personal").addEventListener("click", async () => {
  await window.unifier.setConfig({
    hubUrl: document.getElementById("hub-url").value.trim() || "http://127.0.0.1:8787",
    deviceId: document.getElementById("device-id").value.trim() || "mac-a",
  });
  await window.unifier.start("personal");
  await refresh();
});

document.getElementById("btn-start-enterprise").addEventListener("click", async () => {
  await window.unifier.setConfig({
    hubUrl: document.getElementById("hub-url").value.trim(),
    deviceId: document.getElementById("device-id").value.trim(),
  });
  await window.unifier.start("enterprise");
  await refresh();
});

document.getElementById("btn-stop").addEventListener("click", async () => {
  await window.unifier.stop();
  await refresh();
});

document.getElementById("btn-activate").addEventListener("click", async () => {
  const key = document.getElementById("license-key").value.trim();
  const res = await window.unifier.activateLicense(key);
  document.getElementById("license-msg").textContent = res.valid
    ? "激活成功"
    : `激活失败：${res.reason || "invalid"}`;
  await refresh();
});

document.getElementById("open-at-login").addEventListener("change", async (e) => {
  await window.unifier.setConfig({ openAtLogin: e.target.checked });
});

document.getElementById("btn-open-hub").addEventListener("click", () => window.unifier.openHub());

async function paintRemote() {
  const st = await window.unifier.remoteStatus();
  const el = document.getElementById("remote-status");
  const card = document.getElementById("remote-card");
  const msg = document.getElementById("remote-msg");
  if (st && st.enabled && st.public_url) {
    el.textContent = "状态：已打开（手机可在外面连接）";
    el.style.color = "#3fb950";
    card.textContent = st.card || `电脑连接地址：${st.public_url}`;
  } else {
    el.textContent = "状态：未打开";
    el.style.color = "";
    card.textContent = "打开后，这里会出现要粘贴到手机上的连接信息。";
  }
  if (msg && !msg.dataset.keep) msg.textContent = "";
}

document.getElementById("btn-remote-on").addEventListener("click", async () => {
  const msg = document.getElementById("remote-msg");
  msg.dataset.keep = "1";
  msg.textContent = "正在打开，请稍候（首次可能需要一点时间）…";
  try {
    const res = await window.unifier.remoteEnable();
    if (!res.ok) throw new Error(res.error || "失败");
    msg.textContent = "已打开。点「复制给手机」，在 App 设置里粘贴。";
    await paintRemote();
  } catch (e) {
    msg.textContent = e.message || "打开失败，请检查网络后重试";
  }
});

document.getElementById("btn-remote-off").addEventListener("click", async () => {
  await window.unifier.remoteDisable();
  const msg = document.getElementById("remote-msg");
  msg.dataset.keep = "1";
  msg.textContent = "已关闭。手机在外面将连不上（同一 Wi‑Fi 仍可用）。";
  await paintRemote();
});

document.getElementById("btn-remote-copy").addEventListener("click", async () => {
  const text = document.getElementById("remote-card").textContent || "";
  const msg = document.getElementById("remote-msg");
  msg.dataset.keep = "1";
  try {
    await navigator.clipboard.writeText(text);
    msg.textContent = "已复制。打开手机联合器 App → 设置 → 粘贴。";
  } catch {
    msg.textContent = "复制失败，请手动选中上方文字复制。";
  }
});

if (window.unifier.onStatus) {
  window.unifier.onStatus((status) => {
    paint({
      edition: document.getElementById("edition-badge").textContent.includes("企业")
        ? "enterprise"
        : "personal",
      license: {},
      config: {
        hubUrl: document.getElementById("hub-url").value,
        deviceId: document.getElementById("device-id").value,
        openAtLogin: document.getElementById("open-at-login").checked,
      },
      userData: "",
      ...status,
    });
  });
}

refresh();
paintRemote();
setInterval(refresh, 5000);
setInterval(paintRemote, 8000);

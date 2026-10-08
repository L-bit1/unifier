const { app, BrowserWindow, Tray, Menu, ipcMain, nativeImage, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const { getPaths, getUserDataDir } = require("./lib/paths");
const { validateLicense, saveLicense, loadLicense } = require("./lib/license");

let mainWindow = null;
let tray = null;
let daemonProc = null;
let statusTimer = null;
let lastStatus = {
  daemonRunning: false,
  hubHealthy: false,
  inboxRunning: false,
  deviceId: "",
  hubUrl: "http://127.0.0.1:8787",
};

function getEdition() {
  const lic = loadLicense();
  if (lic.valid && lic.edition === "enterprise") return "enterprise";
  return process.env.UNIFIER_EDITION === "enterprise" ? "enterprise" : "personal";
}

function pythonCmd() {
  return process.platform === "win32" ? "python" : "python3";
}

function ensureDefaultConfig() {
  const dir = getUserDataDir();
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, "config.json");
  let cfg = {};
  if (fs.existsSync(p)) {
    try {
      cfg = JSON.parse(fs.readFileSync(p, "utf8"));
    } catch {
      cfg = {};
    }
  }
  let changed = false;
  if (!cfg.hubUrl) {
    cfg.hubUrl = "http://127.0.0.1:8787";
    changed = true;
  }
  if (!cfg.deviceId) {
    cfg.deviceId = process.env.DEVICE_ID || "mac-a";
    changed = true;
  }
  if (cfg.openAtLogin === undefined) {
    cfg.openAtLogin = false;
    changed = true;
  }
  if (changed) fs.writeFileSync(p, JSON.stringify(cfg, null, 2));
  return cfg;
}

function readConfig() {
  const p = path.join(getUserDataDir(), "config.json");
  if (!fs.existsSync(p)) return ensureDefaultConfig();
  try {
    return { ...ensureDefaultConfig(), ...JSON.parse(fs.readFileSync(p, "utf8")) };
  } catch {
    return ensureDefaultConfig();
  }
}

function writeConfig(patch) {
  const dir = getUserDataDir();
  fs.mkdirSync(dir, { recursive: true });
  const p = path.join(dir, "config.json");
  const prev = readConfig();
  const next = { ...prev, ...patch };
  fs.writeFileSync(p, JSON.stringify(next, null, 2));
  return next;
}

function probeHub(hubUrl) {
  return new Promise((resolve) => {
    try {
      const u = new URL(hubUrl.replace(/\/$/, "") + "/health");
      const req = http.get(
        { hostname: u.hostname, port: u.port || 80, path: u.pathname, timeout: 1500 },
        (res) => {
          res.resume();
          resolve(res.statusCode >= 200 && res.statusCode < 300);
        },
      );
      req.on("error", () => resolve(false));
      req.on("timeout", () => {
        req.destroy();
        resolve(false);
      });
    } catch {
      resolve(false);
    }
  });
}

function readDaemonStatusFile() {
  const home = process.env.UNIFIER_HOME || path.join(app.getPath("home"), ".unifier");
  const p = path.join(home, "daemon-status.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return null;
  }
}

async function refreshStatus() {
  const cfg = readConfig();
  const hubUrl = cfg.hubUrl || "http://127.0.0.1:8787";
  const hubHealthy = await probeHub(hubUrl);
  const file = readDaemonStatusFile();
  const daemonRunning = daemonProc !== null && daemonProc.exitCode === null;
  const inboxRunning = !!(file && file.procs && file.procs["inbox-auto"]);
  lastStatus = {
    daemonRunning,
    hubHealthy,
    inboxRunning: daemonRunning ? inboxRunning || hubHealthy : inboxRunning,
    deviceId: cfg.deviceId || "",
    hubUrl,
  };
  if (tray) {
    const mark = hubHealthy ? "●" : "○";
    tray.setToolTip(`联合器 ${mark} Hub ${hubHealthy ? "在线" : "离线"} · ${cfg.deviceId || "?"}`);
    tray.setContextMenu(buildTrayMenu());
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("unifier:status", lastStatus);
  }
  return lastStatus;
}

function startDaemon(edition) {
  if (daemonProc) return;
  ensureDefaultConfig();
  const paths = getPaths();
  const userData = getUserDataDir();
  const daemon = path.join(__dirname, "..", "runtime", "daemon.py");
  const logDir = path.join(app.getPath("home"), ".unifier", "logs");
  fs.mkdirSync(logDir, { recursive: true });
  const out = fs.openSync(path.join(logDir, "desktop-daemon.log"), "a");
  daemonProc = spawn(pythonCmd(), [daemon, "--edition", edition, "--hub-dir", paths.hubDir, "--user-data", userData], {
    env: {
      ...process.env,
      UNIFIER_EDITION: edition,
      DEVICE_ID: readConfig().deviceId || "mac-a",
      HUB_URL: readConfig().hubUrl || "http://127.0.0.1:8787",
      UNIFIER_HOME: path.join(app.getPath("home"), ".unifier"),
    },
    stdio: ["ignore", out, out],
  });
  daemonProc.on("exit", () => {
    daemonProc = null;
    refreshStatus();
  });
  setTimeout(() => refreshStatus(), 1500);
}

function remoteScript() {
  return path.join(__dirname, "..", "runtime", "remote_access.py");
}

function runRemote(args) {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonCmd(), [remoteScript(), ...args], {
      env: {
        ...process.env,
        UNIFIER_HOME: path.join(app.getPath("home"), ".unifier"),
      },
    });
    let out = "";
    let err = "";
    proc.stdout.on("data", (d) => {
      out += d.toString();
    });
    proc.stderr.on("data", (d) => {
      err += d.toString();
    });
    proc.on("close", (code) => {
      if (code === 0) resolve(out);
      else reject(new Error((err || out || "失败").trim()));
    });
  });
}

function readRemoteState() {
  const p = path.join(app.getPath("home"), ".unifier", "remote-access.json");
  if (!fs.existsSync(p)) return { enabled: false };
  try {
    return JSON.parse(fs.readFileSync(p, "utf8"));
  } catch {
    return { enabled: false };
  }
}

function stopDaemon() {
  if (!daemonProc) {
    setTimeout(() => refreshStatus(), 400);
    return;
  }
  const proc = daemonProc;
  daemonProc = null;
  try {
    proc.kill("SIGTERM");
  } catch {
    /* ignore */
  }
  const started = Date.now();
  const waitKill = setInterval(() => {
    if (proc.exitCode !== null || Date.now() - started > 4000) {
      clearInterval(waitKill);
      if (proc.exitCode === null) {
        try {
          proc.kill("SIGKILL");
        } catch {
          /* ignore */
        }
      }
      refreshStatus();
    }
  }, 200);
}

function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    return;
  }
  mainWindow = new BrowserWindow({
    width: 520,
    height: 680,
    title: "Unifier 联合器",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, "..", "renderer", "index.html"));
  mainWindow.on("close", (e) => {
    // 关窗常驻托盘，不退出
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function buildTrayMenu() {
  const edition = getEdition();
  const cfg = readConfig();
  const hubLabel = lastStatus.hubHealthy ? "Hub 在线" : "Hub 离线";
  const daemonLabel = lastStatus.daemonRunning ? "守护运行中" : "守护未启动";
  return Menu.buildFromTemplate([
    {
      label: `联合器 · ${edition === "enterprise" ? "企业版" : "个人版"}`,
      enabled: false,
    },
    { label: `${hubLabel} · ${daemonLabel}`, enabled: false },
    { label: `设备 ${cfg.deviceId || "?"} · ${cfg.hubUrl || ""}`, enabled: false },
    { type: "separator" },
    { label: "打开控制面板", click: () => createWindow() },
    {
      label: "打开 Hub 控制台",
      click: () => shell.openExternal(cfg.hubUrl || "http://127.0.0.1:8787"),
    },
    { type: "separator" },
    {
      label: lastStatus.daemonRunning ? "重启服务" : "启动服务（Hub+收件箱+心跳）",
      click: () => {
        const was = lastStatus.daemonRunning;
        if (was) stopDaemon();
        setTimeout(() => startDaemon(edition), was ? 1200 : 0);
      },
    },
    { label: "停止服务", enabled: lastStatus.daemonRunning, click: () => stopDaemon() },
    {
      label: `收件箱 ${lastStatus.inboxRunning ? "在跑" : "未跑"}`,
      enabled: false,
    },
    { type: "separator" },
    {
      label: readRemoteState().enabled ? "关闭：外面也能用" : "打开：让手机在外面也能用",
      click: async () => {
        try {
          if (readRemoteState().enabled) {
            await runRemote(["stop"]);
          } else {
            if (!lastStatus.daemonRunning) startDaemon(edition);
            await runRemote(["start", "--hub", "http://127.0.0.1:8787"]);
            createWindow();
          }
        } catch (e) {
          /* ignore — UI 会显示 */
        }
        refreshStatus();
      },
    },
    { type: "separator" },
    {
      label: "开机自启",
      type: "checkbox",
      checked: !!cfg.openAtLogin,
      click: (item) => {
        writeConfig({ openAtLogin: item.checked });
        app.setLoginItemSettings({ openAtLogin: item.checked, openAsHidden: true });
      },
    },
    { type: "separator" },
    {
      label: "退出",
      click: () => {
        app.isQuitting = true;
        runRemote(["stop"]).catch(() => {});
        stopDaemon();
        app.quit();
      },
    },
  ]);
}

function createTray() {
  const iconPath = path.join(__dirname, "..", "assets", "icon.png");
  const icon = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty();
  tray = new Tray(
    icon.isEmpty()
      ? nativeImage.createFromDataURL(
          "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAMUlEQVQ4T2NkYGD4z0ABYBzVMKoBBgYGRvL8DwNGYwP+k4wGRgaG/yQbQKoB0wwY0QAAi7wHAfG0bQ0AAAAASUVORK5CYII=",
        )
      : icon,
  );
  tray.setToolTip("Unifier 联合器");
  tray.setContextMenu(buildTrayMenu());
  tray.on("click", () => createWindow());
  tray.on("right-click", () => tray.popUpContextMenu());
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    createWindow();
  });
}

app.whenReady().then(() => {
  if (!gotLock) return;

  const cfg = ensureDefaultConfig();
  app.setLoginItemSettings({ openAtLogin: !!cfg.openAtLogin, openAsHidden: true });
  if (process.platform === "darwin" && app.dock) {
    // 菜单栏托盘为主；Dock 可隐藏，避免误以为关窗即退出
    try {
      app.dock.hide();
    } catch {
      /* ignore */
    }
  }
  createTray();
  createWindow();
  const edition = getEdition();
  // 个人版默认拉起；若 Hub 已在跑，daemon 会复用端口
  if (edition === "personal") startDaemon("personal");
  statusTimer = setInterval(() => refreshStatus(), 5000);
  refreshStatus();
});

app.on("before-quit", () => {
  app.isQuitting = true;
  if (statusTimer) clearInterval(statusTimer);
  runRemote(["stop"]).catch(() => {});
  stopDaemon();
});

app.on("window-all-closed", (e) => {
  // 托盘常驻：不因关窗退出
  e.preventDefault();
});

ipcMain.handle("unifier:get-state", async () => {
  const paths = getPaths();
  const lic = loadLicense();
  const status = await refreshStatus();
  return {
    edition: getEdition(),
    license: lic,
    paths,
    userData: getUserDataDir(),
    config: readConfig(),
    ...status,
  };
});

ipcMain.handle("unifier:activate-license", (_e, key) => {
  const result = validateLicense(key);
  if (result.valid) saveLicense(key, "enterprise");
  return result;
});

ipcMain.handle("unifier:set-config", (_e, cfg) => {
  const next = writeConfig(cfg || {});
  if (cfg && cfg.openAtLogin !== undefined) {
    app.setLoginItemSettings({ openAtLogin: !!cfg.openAtLogin, openAsHidden: true });
  }
  return { ok: true, config: next };
});

ipcMain.handle("unifier:start", (_e, edition) => {
  startDaemon(edition || getEdition());
  return { ok: true };
});

ipcMain.handle("unifier:stop", () => {
  stopDaemon();
  return { ok: true };
});

ipcMain.handle("unifier:open-hub", () => {
  shell.openExternal(readConfig().hubUrl || "http://127.0.0.1:8787");
  return { ok: true };
});

ipcMain.handle("unifier:remote-enable", async () => {
  try {
    if (!daemonProc) startDaemon(getEdition());
    // 等 Hub 起来
    for (let i = 0; i < 20; i++) {
      const ok = await probeHub("http://127.0.0.1:8787");
      if (ok) break;
      await new Promise((r) => setTimeout(r, 400));
    }
    await runRemote(["start", "--hub", "http://127.0.0.1:8787"]);
    return { ok: true, ...readRemoteState() };
  } catch (e) {
    return { ok: false, error: e.message || String(e) };
  }
});

ipcMain.handle("unifier:remote-disable", async () => {
  try {
    await runRemote(["stop"]);
    return { ok: true, ...readRemoteState() };
  } catch (e) {
    return { ok: false, error: e.message || String(e) };
  }
});

ipcMain.handle("unifier:remote-status", () => readRemoteState());

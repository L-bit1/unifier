const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("unifier", {
  getState: () => ipcRenderer.invoke("unifier:get-state"),
  activateLicense: (key) => ipcRenderer.invoke("unifier:activate-license", key),
  setConfig: (cfg) => ipcRenderer.invoke("unifier:set-config", cfg),
  start: (edition) => ipcRenderer.invoke("unifier:start", edition),
  stop: () => ipcRenderer.invoke("unifier:stop"),
  openHub: () => ipcRenderer.invoke("unifier:open-hub"),
  remoteEnable: () => ipcRenderer.invoke("unifier:remote-enable"),
  remoteDisable: () => ipcRenderer.invoke("unifier:remote-disable"),
  remoteStatus: () => ipcRenderer.invoke("unifier:remote-status"),
  onStatus: (cb) => {
    const handler = (_e, status) => cb(status);
    ipcRenderer.on("unifier:status", handler);
    return () => ipcRenderer.removeListener("unifier:status", handler);
  },
});

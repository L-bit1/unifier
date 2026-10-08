const { app } = require("electron");
const path = require("path");
const fs = require("fs");

function getUserDataDir() {
  return path.join(app.getPath("userData"));
}

function getPaths() {
  const isPackaged = app.isPackaged;
  let repoRoot;
  let hubDir;

  if (isPackaged) {
    hubDir = path.join(process.resourcesPath, "unifier-hub");
    repoRoot = path.dirname(hubDir);
  } else {
    // desktop/electron/lib → 联合器/
    repoRoot = path.resolve(__dirname, "..", "..", "..");
    hubDir = path.join(repoRoot, "hub");
    // 兜底：若路径含空格仍解析得到 hub
    if (!fs.existsSync(hubDir)) {
      const alt = path.resolve(__dirname, "..", "..", "..", "hub");
      if (fs.existsSync(alt)) hubDir = alt;
    }
  }

  const configDir = isPackaged
    ? path.join(process.resourcesPath, "unifier-config")
    : path.join(repoRoot, "config");

  return { repoRoot, hubDir, configDir, isPackaged };
}

module.exports = { getPaths, getUserDataDir };

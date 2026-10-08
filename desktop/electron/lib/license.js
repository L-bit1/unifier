const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { app } = require("electron");

const SALT = "unifier-enterprise-v1";

function licensePath() {
  return path.join(app.getPath("userData"), "license.json");
}

function loadLicense() {
  const p = licensePath();
  if (!fs.existsSync(p)) return { valid: false, edition: "personal" };
  try {
    const data = JSON.parse(fs.readFileSync(p, "utf8"));
    const ok = validateLicense(data.key || "").valid;
    return { valid: ok, edition: ok ? "enterprise" : "personal", key: data.key };
  } catch {
    return { valid: false, edition: "personal" };
  }
}

function saveLicense(key, edition) {
  fs.mkdirSync(app.getPath("userData"), { recursive: true });
  fs.writeFileSync(licensePath(), JSON.stringify({ key, edition, activatedAt: new Date().toISOString() }, null, 2));
}

function validateLicense(key) {
  if (!key || typeof key !== "string") return { valid: false, reason: "empty" };
  const trimmed = key.trim().toUpperCase();
  if (!trimmed.startsWith("UNIFIER-ENT-")) return { valid: false, reason: "format" };
  const body = trimmed.slice("UNIFIER-ENT-".length);
  if (!/^[0-9A-F]{16}$/.test(body)) return { valid: false, reason: "format" };
  const expect = crypto.createHash("sha256").update(SALT + body.slice(0, 8)).digest("hex").slice(0, 8).toUpperCase();
  const got = body.slice(8);
  if (expect !== got) return { valid: false, reason: "checksum" };
  return { valid: true, edition: "enterprise" };
}

module.exports = { validateLicense, saveLicense, loadLicense };

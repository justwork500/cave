import { probe } from "/static/screen.js";
const labels = {
  isSecureContext: "Page counts as a secure context",
  subtleCrypto: "Web Crypto available",
  indexedDB: "Storage (IndexedDB) available",
  keyCreatedOrLoaded: "Key made or loaded",
  keyStored: "Key stored",
  keyKeptAfterReload: "Key kept after reload",
  notExtractable: "Key marked not exportable",
  privateExportRefused: "Browser refuses to export the key",
  signs: "Key can sign",
  publicKey: "Public key readable",
  error: "Error",
  userAgent: "Browser",
};
const r = await probe();
const out = document.getElementById("out");
out.innerHTML = "";
for (const [k, v] of Object.entries(r)) {
  const tr = out.insertRow();
  tr.insertCell().textContent = labels[k] || k;
  const cell = tr.insertCell();
  cell.className = "v " + (v === true ? "pass" : v === false || k === "error" ? "fail" : "info");
  cell.textContent = v === true ? "Pass" : v === false ? "Fail" : String(v);
}
document.getElementById("again").onclick = () => location.reload();

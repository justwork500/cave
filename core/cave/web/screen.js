// CAVE screen identity: a P-256 key the browser makes and can never export.
// Shared by the enrollment page and the tablet browser spike.

const DB_NAME = "cave";
const STORE = "keys";
const KEY_ID = "screen";
const ALGORITHM = { name: "ECDSA", namedCurve: "P-256" };

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idb(mode, fn) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const req = fn(tx.objectStore(STORE));
    tx.oncomplete = () => resolve(req.result);
    tx.onerror = () => reject(tx.error);
  });
}

export async function loadKey() {
  return (await idb("readonly", (s) => s.get(KEY_ID))) || null;
}

export async function getOrCreateKey() {
  const existing = await loadKey();
  if (existing) return existing;
  const pair = await crypto.subtle.generateKey(ALGORITHM, false, ["sign", "verify"]);
  await idb("readwrite", (s) => s.put(pair, KEY_ID));
  return pair;
}

function b64(buffer) {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)));
}

export async function publicKeySpki(pair) {
  return b64(await crypto.subtle.exportKey("spki", pair.publicKey));
}

export async function signChallenge(pair, screenId, nonce) {
  const message = new TextEncoder().encode("cave-screen-auth:" + screenId + ":" + nonce);
  return b64(await crypto.subtle.sign({ name: "ECDSA", hash: "SHA-256" }, pair.privateKey, message));
}

// Spike only: what this browser actually supports.
export async function probe() {
  const r = { userAgent: navigator.userAgent, isSecureContext: window.isSecureContext };
  r.subtleCrypto = !!(window.crypto && crypto.subtle);
  r.indexedDB = !!window.indexedDB;
  if (!r.subtleCrypto || !r.indexedDB) return r;
  const reloaded = sessionStorage.getItem("cave-spike-made") === "1";
  try {
    const before = await loadKey();
    const pair = await getOrCreateKey();
    sessionStorage.setItem("cave-spike-made", "1");
    r.keyCreatedOrLoaded = true;
    r.keyStored = !!(await loadKey());
    r.keyKeptAfterReload = reloaded ? !!before : "reload to check";
    r.notExtractable = pair.privateKey.extractable === false;
    try {
      await crypto.subtle.exportKey("pkcs8", pair.privateKey);
      r.privateExportRefused = false;
    } catch {
      r.privateExportRefused = true;
    }
    r.signs = (await signChallenge(pair, "spike", "nonce")).length > 0;
    r.publicKey = (await publicKeySpki(pair)).length > 0;
  } catch (e) {
    r.error = String(e);
  }
  return r;
}

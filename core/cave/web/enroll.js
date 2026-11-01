import { getOrCreateKey, publicKeySpki, signChallenge } from "/static/screen.js";
const $ = (id) => document.getElementById(id);
const say = (title, msg, isError) => { $("title").textContent = title; $("msg").textContent = msg; $("msg").className = isError ? "err" : ""; };

async function post(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), credentials: "same-origin" });
  const data = r.status === 204 ? {} : await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || "Something went wrong. Try again.");
  return data;
}

async function signIn(pair, screenId) {
  const { nonce } = await post("/api/v1/screen-auth/challenge", { screen_id: screenId });
  await post("/api/v1/screen-auth/verify", { screen_id: screenId, nonce, signature: await signChallenge(pair, screenId, nonce) });
}

async function waitForApproval(pair, screenId) {
  for (;;) {
    try { await signIn(pair, screenId); location.replace("/"); return; }
    catch { await new Promise((r) => setTimeout(r, 5000)); }
  }
}

try {
  const pair = await getOrCreateKey();
  const code = location.hash.slice(1);
  let screenId = localStorage.getItem("cave-screen-id");
  if (code) {
    const res = await post("/api/v1/enroll", { code, public_key: await publicKeySpki(pair) });
    screenId = res.screen_id;
    localStorage.setItem("cave-screen-id", screenId);
    history.replaceState(null, "", "/enroll");
    $("fp").textContent = "Screen fingerprint: " + res.fingerprint;
    $("fp").hidden = false;
  }
  if (!screenId) {
    say("No setup link", "Ask an Admin to add this screen and open the link they give you.", true);
  } else {
    say("Waiting for an Admin to approve this screen", "Check that the fingerprint matches the one in Users and permissions › Screens. This page continues by itself once it's approved.");
    await waitForApproval(pair, screenId);
  }
} catch (e) {
  say("This screen couldn't be set up", e.message, true);
}

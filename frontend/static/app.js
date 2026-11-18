// ParkWise frontend: plain JS, hash routing. All business rules live in MySQL; this only calls /api.
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let me = null, timer = null, charts = [];

async function api(path, method = "GET", body) {
  let r;
  try { r = await fetch("/api" + path, {method, headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined}); }
  catch { throw new Error("Cannot reach the server. Check that the app is running, then try again."); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.error || "Request failed"); e.status = r.status; throw e; }
  return data;
}
function toast(msg, err) { const d = document.createElement("div"); d.className = "t" + (err ? " err" : ""); d.textContent = msg; $("#toast").append(d); setTimeout(() => d.remove(), err ? 7000 : 4500); }
// Runs one request for a button click: the button shows a spinner and is disabled meanwhile,
// success gives a toast, an error gives a toast AND a message that stays inside the form's card.
async function act(fn, ok) {
  const ev = window.event, btn = ev && ev.currentTarget instanceof HTMLButtonElement ? ev.currentTarget : null;
  const card = btn ? btn.closest(".card") : null;
  if (card) card.querySelectorAll(":scope > p.err[data-form]").forEach(p => p.remove());
  if (btn) { btn.disabled = true; btn.classList.add("busy"); }
  try { const r = await fn(); if (ok) toast(typeof ok === "function" ? ok(r) : ok); return r; }
  catch (e) {
    toast(e.message, true);
    if (card) card.insertAdjacentHTML("beforeend", `<p class="err" role="alert" data-form>${esc(e.message)}</p>`);
  } finally { if (btn) { btn.disabled = false; btn.classList.remove("busy"); } }
}
const money = v => "₹" + Number(v ?? 0).toFixed(2);
const chip = v => `<span class="chip ${esc(String(v))}">${esc(String(v).replace(/_/g, " "))}</span>`;
const sumOpen = xs => xs.filter(x => x.status === "OPEN").reduce((a, x) => a + Number(x.fine_amount), 0);
const fineTable = (rows, empty) => table([["#", v => v.violation_id], ["Vehicle", v => v.reg_number], ["Type", v => v.violation_type.replace(/_/g, " ")], ["Fine", v => money(v.fine_amount)],
  ["Status", v => chip(v.status), 1], ["When", v => v.detected_at], ["Notes", v => v.notes || ""]], rows, empty);
const dtl = d => { const p = n => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
function table(cols, data, empty = "Nothing to show.") {
  if (!data.length) return `<div class="empty">${empty}</div>`;
  return `<table><tr>${cols.map(c => `<th scope="col">${esc(c[0])}</th>`).join("")}</tr>` +
    data.map(r => `<tr>${cols.map(c => `<td>${c[2] ? c[1](r) : esc(c[1](r))}</td>`).join("")}</tr>`).join("") + `</table>`;
}

const SHORT = {AVAILABLE: "free", OCCUPIED: "occupied", RESERVED: "booked"};
const routes = {
  "": {t: "Live board", f: board}, board: {t: "Live board", f: board},
  find: {t: "Find a slot", f: find, auth: 1}, vehicles: {t: "My vehicles", f: vehicles, auth: 1},
  reservations: {t: "Reservations", f: reservations, auth: 1}, gate: {t: "Gate (demo)", f: gate, auth: 1}, payment: {t: "Payment", f: payment, auth: 1}, parking: {t: "Payment", f: payment, auth: 1},
  admin: {t: "Admin", f: admin, admin: 1}, analytics: {t: "Analytics", f: analytics, admin: 1},
  login: {t: "Login", f: login}, register: {t: "Register", f: register},
};

async function boot() {
  try { me = await api("/me"); } catch { me = null; }
  window.addEventListener("hashchange", render); render();
}
async function render() {
  clearInterval(timer); charts.forEach(c => c.destroy()); charts = [];
  const key = location.hash.slice(1) || "board", r = routes[key] || routes.board;
  const links = [["board","Live board"]];
  if (me) links.push(["find","Find a slot"],["vehicles","Vehicles"],["reservations","Reservations"],["gate","Gate (demo)"],["payment","Payment"]);
  if (me?.role === "ADMIN") links.push(["admin","Admin"],["analytics","Analytics"]);
  links.push(me ? ["logout","Logout"] : ["login","Login"]);
  if (!me) links.push(["register","Register"]);
  $("#nav").innerHTML = links.map(([k, t]) => `<a href="#${k}" class="${k === key ? "on" : ""}">${t}</a>`).join("");
  $("#who").textContent = me ? `${me.full_name} (${me.role})` : "";
  if (key === "logout") { await act(() => api("/auth/logout", "POST")); me = null; location.hash = "board"; return render(); }
  const v = $("#view");
  if ((r.auth || r.admin) && !me) { location.hash = "login"; return; }
  if (r.admin && me.role !== "ADMIN") { document.title = "Admin only · ParkWise"; v.innerHTML = "<p>Admin only.</p>"; return; }
  document.title = r.t + " · ParkWise";
  v.innerHTML = `<h2 tabindex="-1">${r.t}</h2><div id="page" aria-busy="true"><p class="mut" role="status"><span class="spin"></span>Loading…</p></div>`;
  $("h2", v).focus({preventScroll: true});
  try { await r.f($("#page")); }
  catch (e) {
    if (e.status === 401 && me) { me = null; toast("Your session ended. Please log in again.", true); location.hash = "login"; return; }
    $("#page").innerHTML = `<p class="err" role="alert">${esc(e.message)}</p><p><button class="sec" id="retry">Try again</button></p>`;
    $("#retry").onclick = render;
  }
  const pg = $("#page"); if (pg) pg.removeAttribute("aria-busy");
}

// ---------- public ----------
async function board(el) {
  const draw = async () => {
    const [zones, allSlots] = await Promise.all([api("/zones/occupancy"), api("/slots")]);
    const slots = allSlots.filter(s => s.live_status !== "MAINTENANCE");
    const cnt = k => slots.filter(s => s.live_status === k).length;
    const strip = `<div class="strip"><span class="chip AVAILABLE"><b>${cnt("AVAILABLE")}</b> free</span><span class="chip OCCUPIED"><b>${cnt("OCCUPIED")}</b> occupied</span><span class="chip RESERVED"><b>${cnt("RESERVED")}</b> booked</span></div>`;
    el.innerHTML = `${strip}<div class="tiles">${zones.map(z => `<div class="tile"><span>Zone ${esc(z.zone_code)} · ${esc(z.zone_name)}</span><b>${z.available}/${z.total_slots - z.maintenance} free</b><span>${z.occupied} occupied · ${z.reserved} reserved</span></div>`).join("")}</div>
    <p>${["AVAILABLE","OCCUPIED","RESERVED"].map(s => `<span class="pill ${s}">${s}</span>`).join(" ")} <span class="mut">⚡ EV charger · ♿ accessible · ★ premium · refreshes every 10 s · </span><span id="upd" class="mut">updated ${new Date().toLocaleTimeString()}</span></p>` +
    (slots.length ? "" : `<div class="empty">No parking slots are set up yet.</div>`) +
    [...new Set(slots.map(s => s.zone_code))].map(z => `<h3>Zone ${esc(z)}</h3><div class="grid">${slots.filter(s => s.zone_code === z).map(s =>
      `<div class="slot ${s.live_status}" title="${esc(s.slot_type)} · ${s.distance_to_entrance_m} m from entrance"><b>${esc(s.slot_code)}</b>${s.slot_type === "CAR" ? "Car" : "Bike"} ${s.is_ev_charger ? "⚡" : ""}${s.is_accessible ? "♿" : ""}${s.is_premium ? "★" : ""}<small>${SHORT[s.live_status] || ""}</small></div>`).join("")}</div>`).join("");
  };
  await draw(); timer = setInterval(() => draw().catch(() => { const u = $("#upd"); if (u) { u.textContent = "connection problem, retrying…"; u.className = "warn"; } }), 10000);
}
function login(el) {
  el.innerHTML = `<div class="card narrow"><h3>Login</h3><form class="row" id="f"><label>Email<input id="e" type="email" maxlength="120" autocomplete="username"></label><label>Password<input id="p" type="password" maxlength="128" autocomplete="current-password"></label><button id="go">Login</button></form>
  <p class="mut">Demo: admin@parkwise.test / Admin@123 · aarav@parkwise.test / Student@123</p></div>`;
  $("#f").onsubmit = e => e.preventDefault(); $("#e").focus();
  $("#go").onclick = async () => { const r = await act(() => api("/auth/login", "POST", {email: $("#e").value, password: $("#p").value})); if (r) { me = r; location.hash = "board"; render(); } };
}
function register(el) {
  el.innerHTML = `<div class="card narrow"><h3>Create an account</h3><form class="row" id="f"><label>Full name<input id="n" maxlength="100" autocomplete="name"></label><label>Email<input id="e" type="email" maxlength="120" autocomplete="email"></label><label>Phone<input id="ph" maxlength="15" inputmode="numeric" autocomplete="tel"></label><label>Password (6+ characters)<input id="p" type="password" maxlength="128" autocomplete="new-password"></label><button id="go">Register</button></form></div>`;
  $("#f").onsubmit = e => e.preventDefault(); $("#n").focus();
  $("#go").onclick = async () => { const r = await act(() => api("/auth/register", "POST", {full_name: $("#n").value, email: $("#e").value, phone: $("#ph").value, password: $("#p").value}), "Registered. Please log in."); if (r) location.hash = "login"; };
}

// ---------- user ----------
const vehLabels = vs => { const tot = {}, seen = {};
  vs.forEach(v => tot[v.vehicle_type] = (tot[v.vehicle_type] || 0) + 1);
  return vs.map(v => { seen[v.vehicle_type] = (seen[v.vehicle_type] || 0) + 1;
    const name = (v.vehicle_type === "CAR" ? "Car" : "Bike") + (tot[v.vehicle_type] > 1 ? " " + seen[v.vehicle_type] : "") + (v.is_ev ? " (EV)" : "") + (v.has_accessible_permit ? " ♿" : "");
    return `<option value="${v.vehicle_id}">${esc(name)}</option>`; }).join(""); };
const vehOptions = vs => vs.map(v => `<option value="${v.vehicle_id}">${esc(v.reg_number)} (${v.vehicle_type === "CAR" ? "Car" : "Bike"}${v.is_ev ? ", EV" : ""})</option>`).join("");
async function vehicles(el) {
  const [vs, inside, slots] = await Promise.all([api("/vehicles"), api("/sessions/active"), api("/slots")]);
  const zoneOf = Object.fromEntries(slots.map(x => [x.slot_code, x.zone_name]));
  const parked = Object.fromEntries(inside.map(x => [x.reg_number, `${zoneOf[x.slot_code] || "Zone"} · slot ${x.slot_code} (since ${String(x.entry_time).slice(11, 16)})`]));
  el.innerHTML = `<div class="card">${table([["Reg. number", v => v.reg_number], ["Type", v => v.vehicle_type === "CAR" ? "Car" : "Bike"], ["EV", v => v.is_ev ? "Yes" : "No"],
    ["Disability permit", v => v.has_accessible_permit ? "Yes" : "No"], ["Parked at", v => parked[v.reg_number] || "Not parked"]], vs, "No vehicles yet. Add your first one below.")}</div>
  <div class="card"><h3>Add a vehicle</h3><form class="row" id="f"><label>Registration no.<input id="r" maxlength="15" placeholder="MH12AB1234"></label>
  <label>Type<select id="t"><option value="CAR">Car</option><option value="TWO_WHEELER">Two-wheeler</option></select></label>
  <label><span>EV</span><input id="ev" type="checkbox"></label><label><span>Disability parking permit</span><input id="ac" type="checkbox"></label>
  <button id="go">Add</button></form></div>`;
  $("#f").onsubmit = e => e.preventDefault();
  $("#go").onclick = async () => {
    const body = {reg_number: $("#r").value, vehicle_type: $("#t").value, is_ev: $("#ev").checked, has_accessible_permit: $("#ac").checked};
    if (await act(() => api("/vehicles", "POST", body), "Vehicle added.")) vehicles(el);
  };
}
async function find(el) {
  const vs = await api("/vehicles"); const n = new Date();
  el.innerHTML = vs.length ? `<div class="card"><form class="row" id="f"><label>Vehicle<select id="v">${vehLabels(vs)}</select></label>
  <label>From<input id="s" type="datetime-local" value="${dtl(new Date(n.getTime() + 36e5))}"></label>
  <label>To<input id="e" type="datetime-local" value="${dtl(new Date(n.getTime() + 3 * 36e5))}"></label><label><span>Need accessible bay (disability)</span><input id="acc" type="checkbox"></label><button id="go">Find best slots</button></form><p class="err" id="accmsg" role="status"></p></div><div id="res"></div>` : `<div class="empty">Add a vehicle first on the <a href="#vehicles">Vehicles</a> page, then come back.</div>`;
  if (!vs.length) return;
  $("#f").onsubmit = e => e.preventDefault();
  const accCheck = () => { const v = vs.find(x => x.vehicle_id == $("#v").value), no = $("#acc").checked && v && !v.has_accessible_permit;
    $("#accmsg").textContent = no ? "This vehicle has no accessibility permit, so it cannot use accessible bays." : ""; $("#go").disabled = !!no; };
  $("#v").onchange = $("#acc").onchange = accCheck;
  $("#go").onclick = async () => {
    let rec = await act(() => api(`/recommend?vehicle_id=${$("#v").value}&start=${$("#s").value}&end=${$("#e").value}`));
    if (!rec) return;
    const accIds = new Set((await api("/slots")).filter(s => s.is_accessible).map(s => s.slot_id)), need = $("#acc").checked;
    if (need) rec = rec.filter(s => accIds.has(s.slot_id));
    $("#res").innerHTML = `<div class="card">${table([["Slot", s => esc(s.slot_code) + (accIds.has(s.slot_id) ? " ♿" : ""), 1], ["Zone", s => s.zone_name], ["Score", s => Number(s.score).toFixed(3)], ["Why this slot", s => s.reason],
      ["", s => `<button data-id="${s.slot_id}">Reserve</button>`, 1]], rec, need ? "No accessible bay is free for this time." : "No slot fits this vehicle and time.")}</div>`;
    el.querySelectorAll("#res button").forEach(b => b.onclick = async () => {
      const r = await act(() => api("/reservations", "POST", {vehicle_id: +$("#v").value, slot_id: +b.dataset.id, start: $("#s").value, end: $("#e").value}), "Reserved!");
      if (r) location.hash = "reservations";
    });
  };
}
async function reservations(el) {
  const rs = await api("/reservations");
  el.innerHTML = `<div class="card">${table([["#", r => r.reservation_id], ["Vehicle", r => r.reg_number], ["Slot", r => r.slot_code], ["From", r => r.start_time], ["To", r => r.end_time], ["Status", r => chip(r.status), 1],
    ["Why", r => r.alloc_reason || ""], ["", r => r.status === "PENDING" ? `<button class="red" data-id="${r.reservation_id}">Cancel</button>` : "", 1]], rs, "No reservations yet. Use Find a slot to book one.")}</div>`;
  el.querySelectorAll("button[data-id]").forEach(b => b.onclick = async () => { if (await act(() => api("/reservations/" + b.dataset.id, "DELETE"), "Cancelled.")) reservations(el); });
}
async function gate(el) {
  const [vs, slots, act_] = await Promise.all([api("/vehicles"), api("/slots"), api("/sessions/active")]);
  el.innerHTML = `<div class="card"><h3>Vehicle entry <span class="mut">(simulates the gate)</span></h3><div class="row"><label>Vehicle<select id="v">${vehOptions(vs)}</select></label>
  <label>Slot<select id="sl"></select></label><button id="in">Enter</button></div>${vs.length ? "" : `<p class="mut">Add a vehicle first on the <a href="#vehicles">Vehicles</a> page.</p>`}</div>
  <div class="card"><h3>Vehicles inside now</h3>${table([["Session", s => s.session_id], ["Vehicle", s => s.reg_number], ["Slot", s => s.slot_code], ["Entered", s => s.entry_time], ["Minutes", s => s.elapsed_minutes], ["Amount so far", s => money(s.running_amount)],
    ["", s => `<button data-exit="${s.session_id}">Exit</button>`, 1]], act_, "No active sessions.")}</div>
  <div id="done"></div>`;
  const fill = () => { const v = vs.find(x => x.vehicle_id == $("#v").value);
    $("#sl").innerHTML = slots.filter(s => v && s.slot_type === v.vehicle_type && ["AVAILABLE", "RESERVED"].includes(s.live_status) && (!s.is_accessible || v.has_accessible_permit) && (!s.is_ev_charger || v.is_ev))
      .map(s => `<option value="${s.slot_id}">${esc(s.slot_code)}${s.is_ev_charger ? " ⚡" : ""}${s.is_accessible ? " ♿" : ""} (${s.live_status.toLowerCase()})</option>`).join("");
    if (!$("#sl").options.length) $("#sl").innerHTML = `<option value="">No slot available</option>`;
    $("#in").disabled = !v || !$("#sl").value; };
  $("#v").onchange = fill; fill();
  $("#in").onclick = async () => { if (await act(() => api("/sessions/entry", "POST", {vehicle_id: +$("#v").value, slot_id: +$("#sl").value}), r => "Entry recorded, session " + r.session_id)) gate(el); };
  el.querySelectorAll("[data-exit]").forEach(b => b.onclick = async () => {
    const r = await act(() => api(`/sessions/${b.dataset.exit}/exit`, "POST"), r => "Exit done. Amount " + money(r.amount_due));
    if (r) { await gate(el); $("#done").innerHTML = `<div class="card"><h3>Exit done</h3><p>Amount due: <b>${money(r.amount_due)}</b>. <a href="#payment">Go to Payment</a> to pay the bill.</p></div>`; }
  });
}

async function payment(el, receipt = "") {
  const [unpaid, pens] = await Promise.all([api("/bills/unpaid"), api("/penalties")]);
  const over = pens.filter(x => x.violation_type === "OVERSTAY"), pen = pens.filter(x => x.violation_type !== "OVERSTAY");
  el.innerHTML = `<div class="card"><h3>Unpaid bills</h3>${table([["Session", b => b.session_id], ["Vehicle", b => b.reg_number], ["Slot", b => b.slot_code], ["Exit", b => b.exit_time], ["Fee", b => money(b.parking_fee)],
    ["Status", b => chip(b.payment_status), 1], ["", b => `<button data-bill="${b.session_id}">Pay</button>`, 1]], unpaid, "No unpaid bills.")}</div><div id="bill">${receipt}</div>
  <div class="card"><h3>Penalties <span class="mut">(open: ${money(sumOpen(pen))})</span></h3>${fineTable(pen.slice(0, 10), "No penalties.")}${pen.length > 10 ? `<p class="mut">Showing the latest 10 of ${pen.length}.</p>` : ""}</div>
  <div class="card"><h3>Overcharge <span class="mut">(overstay fines, open: ${money(sumOpen(over))})</span></h3>${fineTable(over.slice(0, 10), "No overcharge.")}${over.length > 10 ? `<p class="mut">Showing the latest 10 of ${over.length}.</p>` : ""}</div>`;
  el.querySelectorAll("[data-bill]").forEach(b => b.onclick = async () => showBill(await act(() => api("/bills/" + b.dataset.bill))));
  const gwCheck = () => {
    if ($("#m").value === "UPI") return /^[\w.\-]{2,}@[A-Za-z]{2,}$/.test($("#upi").value.trim()) ? "" : "Enter a valid UPI ID, for example name@bank.";
    if (!/^\d{16}$/.test($("#cn").value.replace(/\s/g, ""))) return "Card number must be 16 digits.";
    const m = /^(\d{2})\/(\d{2})$/.exec($("#ex").value.trim()); if (!m || +m[1] < 1 || +m[1] > 12) return "Expiry must look like 08/28.";
    const n = new Date(), y = 2000 + +m[2]; if (y < n.getFullYear() || (y === n.getFullYear() && +m[1] < n.getMonth() + 1)) return "This card has expired.";
    return /^\d{3}$/.test($("#cv").value) ? "" : "CVV must be 3 digits.";
  };
  function showBill(b) {
    if (!b) return;
    const open = ["PENDING", "FAILED"].includes(b.payment_status);
    $("#bill").innerHTML = `<div class="card"><h3>Bill — session ${b.session_id} · ${esc(b.reg_number)} · ${esc(b.slot_code)}</h3>
    <table><tr><td>Parked</td><td>${esc(b.entry_time)} → ${esc(b.exit_time)} (${b.duration_minutes} min)</td></tr>
    <tr><td>Free grace</td><td>${b.grace_minutes} min → ${b.billable_minutes} billable min = ${b.hourly_blocks} × ${money(b.hourly_rate)}</td></tr>
    <tr><td>Minimum / daily cap</td><td>${money(b.min_charge)} / ${b.daily_cap == null ? "none" : money(b.daily_cap)}</td></tr>
    <tr><td><b>Parking fee</b></td><td><b>${money(b.parking_fee)}</b></td></tr><tr><td>Fines (separate)</td><td>${money(b.fines)}</td></tr>
    <tr><td>Payment</td><td>${chip(b.payment_status || "PENDING")} ${b.payment_method ? "via " + esc(b.payment_method) : ""}</td></tr></table></div>` + (open ? `<div class="card gw"><h3>Sample payment gateway <span class="mut">(demo only, no real payment)</span></h3>
    <form class="row" id="gf" autocomplete="off"><label>Method<select id="m"><option value="UPI">UPI</option><option value="CARD">Card</option></select></label>
    <label class="gu">UPI ID<input id="upi" maxlength="40" placeholder="name@bank"></label>
    <label class="gc" hidden>Card number<input id="cn" maxlength="19" inputmode="numeric" placeholder="1234 5678 9012 3456"></label>
    <label class="gc" hidden>Expiry<input id="ex" maxlength="5" placeholder="MM/YY" size="6"></label>
    <label class="gc" hidden>CVV<input id="cv" type="password" maxlength="3" inputmode="numeric" placeholder="123" size="4"></label>
    <label><span>Simulate failure</span><input id="f" type="checkbox"></label><button id="pay">Pay ${money(b.parking_fee)}</button></form>
    <p class="mut">The card or UPI details stay in this page. Only the method is sent to the server.</p><p class="err" id="gwerr" role="alert"></p></div>` : "");
    if (!open) return;
    const sync = () => { const card = $("#m").value === "CARD"; el.querySelectorAll(".gc").forEach(x => x.hidden = !card); el.querySelector(".gu").hidden = card; };
    $("#m").onchange = sync; $("#gf").onsubmit = e => e.preventDefault();
    $("#pay").onclick = async () => {
      const msg = gwCheck(); $("#gwerr").textContent = msg; if (msg) return;
      const r = await act(async () => { await new Promise(res => setTimeout(res, 900)); return api("/payments", "POST", {session_id: b.session_id, method: $("#m").value, simulate_failure: $("#f").checked}); });
      if (!r) return;
      toast(r.message, r.bill.payment_status !== "PAID");
      if (r.bill.payment_status !== "PAID") return showBill(r.bill);
      const x = r.bill;
      await payment(el, `<div class="card"><h3>Payment receipt</h3><table><tr><td>Session</td><td>${x.session_id}</td></tr><tr><td>Vehicle</td><td>${esc(x.reg_number)}</td></tr><tr><td>Slot</td><td>${esc(x.slot_code)}</td></tr>
        <tr><td>Amount paid</td><td><b>${money(x.parking_fee)}</b></td></tr><tr><td>Method</td><td>${esc(x.payment_method || $("#m")?.value || "")}</td></tr><tr><td>Status</td><td>${chip("PAID")}</td></tr><tr><td>Time</td><td>${esc(new Date().toLocaleString())}</td></tr></table>
        <p class="mut">Sample gateway: nothing was charged.</p></div>`);
    };
  }
}

// ---------- admin ----------
const TLAB = {hourly_rate: "rupees per hour", grace_minutes: "grace minutes", min_charge: "minimum charge", daily_cap: "daily cap", overstay_fine_per_hour: "overstay fine per hour"};
async function admin(el) {
  const [tf, sl, vi, au, us] = await Promise.all([api("/admin/tariffs"), api("/slots"), api("/admin/violations"), api("/admin/audit"), api("/admin/users")]);
  const tile = (name, rows) => `<div class="tile"><span>${name}</span><b>${money(sumOpen(rows))} open</b><span>${rows.length} logged · ${rows.filter(x => x.status === "OPEN").length} open</span></div>`;
  const tiles = `<div class="tiles" style="margin-bottom:14px">${tile("Overcharge (overstay fines)", vi.filter(x => x.violation_type === "OVERSTAY"))}${tile("Penalties (other violations)", vi.filter(x => x.violation_type !== "OVERSTAY"))}</div>`;
  const vSorted = vi.slice().sort((a, b) => (a.status === "OPEN" ? 0 : 1) - (b.status === "OPEN" ? 0 : 1));
  el.innerHTML = `<div class="card"><h3>Tariffs</h3><table><tr><th>Type</th><th>Premium</th><th>₹/hour</th><th>Grace min</th><th>Min charge</th><th>Daily cap</th><th>Fine/hour</th><th></th></tr>${tf.map(t => `<tr data-t="${t.tariff_id}">
    <td>${t.vehicle_type}</td><td>${t.is_premium ? "Yes" : "No"}</td>${["hourly_rate", "grace_minutes", "min_charge", "daily_cap", "overstay_fine_per_hour"].map(k => `<td><input size="5" maxlength="8" inputmode="decimal" data-k="${k}" aria-label="${t.vehicle_type}${t.is_premium ? " premium" : ""}: ${TLAB[k]}" value="${t[k] ?? ""}"></td>`).join("")}<td><button>Save</button></td></tr>`).join("")}</table></div>
  <div class="card"><h3>Slot maintenance</h3><div class="row"><label>Slot<select id="sid">${sl.map(s => `<option value="${s.slot_id}">${esc(s.slot_code)} (${s.live_status})</option>`).join("")}</select></label>
  <button id="mt">Set maintenance</button><button id="av" class="sec">Set available</button><button id="jobs" class="sec">Run no-show / overstay / snapshot jobs now</button></div></div>
  ${tiles}<div class="card"><h3>Violations <span class="mut">(open ones first)</span></h3><div class="row"><label>Session no.<input id="vs" size="6" inputmode="numeric"></label><label>Type<select id="vt"><option>OVERSTAY</option><option>WRONG_SLOT</option><option>UNAUTHORIZED_BAY</option></select></label>
  <label>Fine<input id="vf" size="5" value="0"></label><label>Notes<input id="vn" maxlength="255"></label><button id="vb">Log violation</button></div>
  ${table([["#", v => v.violation_id], ["Vehicle", v => v.reg_number], ["Type", v => v.violation_type], ["Fine", v => money(v.fine_amount)], ["Status", v => chip(v.status), 1], ["When", v => v.detected_at], ["Notes", v => v.notes || ""],
    ["", v => v.status === "OPEN" ? `<button data-vs="${v.violation_id}" data-to="PAID">Mark paid</button> <button class="sec" data-vs="${v.violation_id}" data-to="WAIVED">Waive</button>` : "", 1]], vSorted.slice(0, 20), "No violations logged yet.")}</div>
  <div class="card"><h3>Users <span class="mut">(${us.length})</span></h3><div class="scroll">${table([["#", u => u.user_id], ["Name", u => u.full_name], ["Email", u => u.email], ["Phone", u => u.phone || ""], ["Role", u => u.role], ["Vehicles", u => u.vehicles], ["Joined", u => u.created_at]], us)}</div></div>
  <div class="card"><h3>Audit log (latest)</h3>${table([["When", a => a.created_at], ["Who", a => a.actor || "system"], ["Action", a => a.action], ["Entity", a => a.entity + " #" + a.entity_id], ["Old", a => a.old_value || ""], ["New", a => a.new_value || ""]], au.slice(0, 15), "No audit entries yet.")}</div>`;
  el.querySelectorAll("tr[data-t] button").forEach(b => b.onclick = async () => {
    const tr = b.closest("tr"), body = {tariff_id: +tr.dataset.t}; tr.querySelectorAll("input").forEach(i => body[i.dataset.k] = i.value);
    if (await act(() => api("/admin/tariffs", "PUT", body), r => r.message)) admin(el);
  });
  const setSlot = st => async () => { if (await act(() => api(`/admin/slots/${$("#sid").value}/status`, "PUT", {status: st}), "Slot updated.")) admin(el); };
  $("#mt").onclick = setSlot("MAINTENANCE"); $("#av").onclick = setSlot("AVAILABLE");
  el.querySelectorAll("[data-vs]").forEach(b => b.onclick = async () => {
    if (b.dataset.to === "WAIVED" && !confirm("Waive this fine? This cannot be undone.")) return;
    if (await act(() => api(`/admin/violations/${b.dataset.vs}/status`, "PUT", {status: b.dataset.to}), r => r.message)) admin(el);
  });
  $("#jobs").onclick = () => act(() => api("/admin/run-jobs", "POST"), r => r.message);
  $("#vb").onclick = async () => { if (await act(() => api("/admin/violations", "POST", {session_id: $("#vs").value, violation_type: $("#vt").value, fine_amount: $("#vf").value, notes: $("#vn").value}), "Violation logged.")) admin(el); };
}
async function analytics(el) {
  const [sm, rev, hr, fc, co] = await Promise.all(["summary", "revenue", "hourly-demand", "forecast", "carbon"].map(p => api("/analytics/" + p)));
  const T = (l, v) => `<div class="tile"><span>${l}</span><b>${v}</b></div>`;
  el.innerHTML = `<div class="tiles">${T("Inside now", sm.active_sessions)}${T("Occupancy", sm.occupancy_pct + "%")}${T("Revenue today", money(sm.revenue_today))}${T("Total revenue", money(sm.revenue_total))}${T("Unpaid bills", sm.unpaid_bills)}${T("Open violations", sm.open_violations)}</div>
  <div class="card"><h3>Daily revenue (last 30 days)</h3><canvas id="c1" height="90"></canvas></div>
  <div class="card"><h3>Entries by hour of day</h3><canvas id="c2" height="90"></canvas></div>
  <div class="card"><h3>Expected busyness by weekday and hour <span class="mut">(rule-based average of past data, not AI)</span></h3><div id="heat"></div></div>
  <div class="card"><h3>Carbon-savings estimate</h3><p>${co.sessions} sessions · ${co.metres_saved} m of driving saved · about <b>${co.co2_saved_g} g CO₂</b>.</p><p class="mut">${esc(co.note)} Small by design — shown as a minor widget.</p></div>`;
  if (window.Chart) {
    const css = getComputedStyle(document.documentElement);
    Chart.defaults.color = css.getPropertyValue("--ink").trim(); Chart.defaults.borderColor = css.getPropertyValue("--line").trim();
    if (!rev.length) $("#c1").replaceWith(Object.assign(document.createElement("div"), {className: "empty", textContent: "No revenue yet."}));
    else charts.push(new Chart($("#c1"), {type: "line", data: {labels: rev.map(r => r.revenue_date), datasets: [{label: "₹", data: rev.map(r => r.revenue), borderColor: "#1565c0", tension: .25}]}, options: {plugins: {legend: {display: false}}}}));
    if (!hr.length) $("#c2").replaceWith(Object.assign(document.createElement("div"), {className: "empty", textContent: "No entries yet."}));
    else charts.push(new Chart($("#c2"), {type: "bar", data: {labels: hr.map(h => h.hour_of_day + ":00"), datasets: [{label: "Entries", data: hr.map(h => h.entries), backgroundColor: "#1565c0"}]}, options: {plugins: {legend: {display: false}}}}));
  } else el.insertAdjacentHTML("beforeend", "<p class='err'>The charts could not load. Check that frontend/static/chart.umd.js exists, then reload the page.</p>");
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], m = {};
  fc.forEach(f => m[f.day_of_week + "-" + f.hour_of_day] = f.avg_occupancy_pct);
  const col = p => p == null ? "transparent" : `hsl(${120 - Math.min(p, 100) * 1.2},65%,${p == null ? 50 : 55}%)`;
  $("#heat").innerHTML = `<table class="heat"><tr><th></th>${[...Array(24).keys()].map(h => `<th>${h}</th>`).join("")}</tr>` + days.map((d, i) =>
    `<tr><th>${d}</th>${[...Array(24).keys()].map(h => { const p = m[(i + 1) + "-" + h]; return `<td style="background:${col(p)}" title="${p ?? "no data"}%">${p == null ? "" : Math.round(p)}</td>`; }).join("")}</tr>`).join("") + "</table>";
}
boot();

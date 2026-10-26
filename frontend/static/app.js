// ParkWise frontend: plain JS, hash routing. All business rules live in MySQL; this only calls /api.
const $ = (s, r = document) => r.querySelector(s);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let me = null, timer = null, charts = [];

async function api(path, method = "GET", body) {
  const r = await fetch("/api" + path, {method, headers: body ? {"Content-Type": "application/json"} : {}, body: body ? JSON.stringify(body) : undefined});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.error || "Request failed"); e.status = r.status; throw e; }
  return data;
}
function toast(msg, err) { const d = document.createElement("div"); d.className = "t" + (err ? " err" : ""); d.textContent = msg; $("#toast").append(d); setTimeout(() => d.remove(), 4500); }
async function act(fn, ok) { try { const r = await fn(); if (ok) toast(typeof ok === "function" ? ok(r) : ok); return r; } catch (e) { toast(e.message, true); } }
const money = v => "₹" + Number(v ?? 0).toFixed(2);
const dtl = d => { const p = n => String(n).padStart(2, "0"); return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`; };
function table(cols, data, empty = "Nothing to show.") {
  if (!data.length) return `<p class="mut">${empty}</p>`;
  return `<table><tr>${cols.map(c => `<th>${esc(c[0])}</th>`).join("")}</tr>` +
    data.map(r => `<tr>${cols.map(c => `<td>${c[2] ? c[1](r) : esc(c[1](r))}</td>`).join("")}</tr>`).join("") + `</table>`;
}

const routes = {
  "": {t: "Live board", f: board}, board: {t: "Live board", f: board},
  find: {t: "Find a slot", f: find, auth: 1}, vehicles: {t: "My vehicles", f: vehicles, auth: 1},
  reservations: {t: "Reservations", f: reservations, auth: 1}, parking: {t: "Entry / Exit / Pay", f: parking, auth: 1},
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
  if (me) links.push(["find","Find a slot"],["vehicles","Vehicles"],["reservations","Reservations"],["parking","Entry/Exit/Pay"]);
  if (me?.role === "ADMIN") links.push(["admin","Admin"],["analytics","Analytics"]);
  links.push(me ? ["logout","Logout"] : ["login","Login"]);
  if (!me) links.push(["register","Register"]);
  $("#nav").innerHTML = links.map(([k, t]) => `<a href="#${k}" class="${k === key ? "on" : ""}">${t}</a>`).join("");
  $("#who").textContent = me ? `${me.full_name} (${me.role})` : "";
  if (key === "logout") { await act(() => api("/auth/logout", "POST")); me = null; location.hash = "board"; return render(); }
  const v = $("#view");
  if ((r.auth || r.admin) && !me) { location.hash = "login"; return; }
  if (r.admin && me.role !== "ADMIN") { v.innerHTML = "<p>Admin only.</p>"; return; }
  v.innerHTML = `<h2>${r.t}</h2><div id="page">Loading…</div>`;
  try { await r.f($("#page")); } catch (e) { $("#page").innerHTML = `<p class="err">${esc(e.message)}</p>`; }
}

// ---------- public ----------
async function board(el) {
  const draw = async () => {
    const [zones, slots] = await Promise.all([api("/zones/occupancy"), api("/slots")]);
    el.innerHTML = `<div class="tiles">${zones.map(z => `<div class="tile"><span>Zone ${esc(z.zone_code)} · ${esc(z.zone_name)}</span><b>${z.available}/${z.total_slots} free</b><span>${z.occupied} occupied · ${z.reserved} reserved · ${z.maintenance} maint.</span></div>`).join("")}</div>
    <p>${["AVAILABLE","OCCUPIED","RESERVED","MAINTENANCE"].map(s => `<span class="pill ${s}" style="color:#fff">${s}</span>`).join(" ")} <span class="mut">⚡ EV charger · ♿ accessible · ★ premium · refreshes every 10 s</span></p>` +
    [...new Set(slots.map(s => s.zone_code))].map(z => `<h3>Zone ${esc(z)}</h3><div class="grid">${slots.filter(s => s.zone_code === z).map(s =>
      `<div class="slot ${s.live_status}" title="${esc(s.slot_type)} · ${s.distance_to_entrance_m} m from entrance"><b>${esc(s.slot_code)}</b>${s.slot_type === "CAR" ? "Car" : "Bike"} ${s.is_ev_charger ? "⚡" : ""}${s.is_accessible ? "♿" : ""}${s.is_premium ? "★" : ""}</div>`).join("")}</div>`).join("");
  };
  await draw(); timer = setInterval(() => draw().catch(() => {}), 10000);
}
function login(el) {
  el.innerHTML = `<div class="card"><div class="row"><label>Email<input id="e" type="email"></label><label>Password<input id="p" type="password"></label><button id="go">Login</button></div>
  <p class="mut">Demo: admin@parkwise.test / Admin@123 · aarav@parkwise.test / Student@123</p></div>`;
  $("#go").onclick = async () => { const r = await act(() => api("/auth/login", "POST", {email: $("#e").value, password: $("#p").value})); if (r) { me = r; location.hash = "board"; render(); } };
}
function register(el) {
  el.innerHTML = `<div class="card"><div class="row"><label>Full name<input id="n"></label><label>Email<input id="e" type="email"></label><label>Phone<input id="ph"></label><label>Password<input id="p" type="password"></label><button id="go">Register</button></div></div>`;
  $("#go").onclick = async () => { const r = await act(() => api("/auth/register", "POST", {full_name: $("#n").value, email: $("#e").value, phone: $("#ph").value, password: $("#p").value}), "Registered. Please log in."); if (r) location.hash = "login"; };
}

// ---------- user ----------
const vehOptions = vs => vs.map(v => `<option value="${v.vehicle_id}">${esc(v.reg_number)} (${v.vehicle_type === "CAR" ? "Car" : "Bike"}${v.is_ev ? ", EV" : ""})</option>`).join("");
async function vehicles(el) {
  const vs = await api("/vehicles");
  el.innerHTML = `<div class="card">${table([["Reg. number", v => v.reg_number], ["Type", v => v.vehicle_type], ["EV", v => v.is_ev ? "Yes" : "No"], ["Accessible permit", v => v.has_accessible_permit ? "Yes" : "No"]], vs, "No vehicles yet.")}</div>
  <div class="card"><h3>Add a vehicle</h3><div class="row"><label>Registration no.<input id="r" placeholder="MH12AB1234"></label>
  <label>Type<select id="t"><option value="CAR">Car</option><option value="TWO_WHEELER">Two-wheeler</option></select></label>
  <label><span>EV</span><input id="ev" type="checkbox"></label><label><span>Accessible permit</span><input id="ac" type="checkbox"></label><button id="go">Add</button></div></div>`;
  $("#go").onclick = async () => { if (await act(() => api("/vehicles", "POST", {reg_number: $("#r").value, vehicle_type: $("#t").value, is_ev: $("#ev").checked, has_accessible_permit: $("#ac").checked}), "Vehicle added.")) vehicles(el); };
}
async function find(el) {
  const vs = await api("/vehicles"); const n = new Date();
  el.innerHTML = vs.length ? `<div class="card"><div class="row"><label>Vehicle<select id="v">${vehOptions(vs)}</select></label>
  <label>From<input id="s" type="datetime-local" value="${dtl(new Date(n.getTime() + 36e5))}"></label>
  <label>To<input id="e" type="datetime-local" value="${dtl(new Date(n.getTime() + 3 * 36e5))}"></label><button id="go">Find best slots</button></div></div><div id="res"></div>` : `<p>Add a vehicle first.</p>`;
  if (!vs.length) return;
  $("#go").onclick = async () => {
    const rec = await act(() => api(`/recommend?vehicle_id=${$("#v").value}&start=${$("#s").value}&end=${$("#e").value}`));
    if (!rec) return;
    $("#res").innerHTML = `<div class="card">${table([["Slot", s => s.slot_code], ["Zone", s => s.zone_name], ["Score", s => Number(s.score).toFixed(3)], ["Why this slot", s => s.reason],
      ["", s => `<button data-id="${s.slot_id}" data-sc="${s.score}" data-re="${esc(s.reason)}">Reserve</button>`, 1]], rec, "No slot fits this vehicle and time.")}</div>`;
    el.querySelectorAll("#res button").forEach(b => b.onclick = async () => {
      const r = await act(() => api("/reservations", "POST", {vehicle_id: +$("#v").value, slot_id: +b.dataset.id, start: $("#s").value, end: $("#e").value, alloc_score: +b.dataset.sc, alloc_reason: b.dataset.re}), "Reserved!");
      if (r) location.hash = "reservations";
    });
  };
}
async function reservations(el) {
  const rs = await api("/reservations");
  el.innerHTML = `<div class="card">${table([["#", r => r.reservation_id], ["Vehicle", r => r.reg_number], ["Slot", r => r.slot_code], ["From", r => r.start_time], ["To", r => r.end_time], ["Status", r => r.status],
    ["Why", r => r.alloc_reason || ""], ["", r => r.status === "PENDING" ? `<button class="red" data-id="${r.reservation_id}">Cancel</button>` : "", 1]], rs, "No reservations yet.")}</div>`;
  el.querySelectorAll("button[data-id]").forEach(b => b.onclick = async () => { if (await act(() => api("/reservations/" + b.dataset.id, "DELETE"), "Cancelled.")) reservations(el); });
}
async function parking(el) {
  const [vs, slots, act_, unpaid] = await Promise.all([api("/vehicles"), api("/slots"), api("/sessions/active"), api("/bills/unpaid")]);
  el.innerHTML = `<div class="card"><h3>Vehicle entry <span class="mut">(simulates the gate)</span></h3><div class="row"><label>Vehicle<select id="v">${vehOptions(vs)}</select></label>
  <label>Slot<select id="sl"></select></label><button id="in">Enter</button></div></div>
  <div class="card"><h3>Vehicles inside now</h3>${table([["Session", s => s.session_id], ["Vehicle", s => s.reg_number], ["Slot", s => s.slot_code], ["Entered", s => s.entry_time], ["Minutes", s => s.elapsed_minutes], ["Amount so far", s => money(s.running_amount)],
    ["", s => `<button data-exit="${s.session_id}">Exit</button>`, 1]], act_, "No active sessions.")}</div>
  <div class="card"><h3>Unpaid bills</h3>${table([["Session", b => b.session_id], ["Vehicle", b => b.reg_number], ["Slot", b => b.slot_code], ["Exit", b => b.exit_time], ["Fee", b => money(b.parking_fee)], ["Status", b => b.payment_status],
    ["", b => `<button data-bill="${b.session_id}">Pay</button>`, 1]], unpaid, "No unpaid bills.")}</div><div id="bill"></div>`;
  const fill = () => { const v = vs.find(x => x.vehicle_id == $("#v").value);
    $("#sl").innerHTML = slots.filter(s => v && s.slot_type === v.vehicle_type && ["AVAILABLE", "RESERVED"].includes(s.live_status) && (!s.is_accessible || v.has_accessible_permit) && (!s.is_ev_charger || v.is_ev))
      .map(s => `<option value="${s.slot_id}">${esc(s.slot_code)}${s.is_ev_charger ? " ⚡" : ""}${s.is_accessible ? " ♿" : ""} (${s.live_status.toLowerCase()})</option>`).join(""); };
  if (vs.length) { $("#v").onchange = fill; fill(); }
  $("#in").onclick = async () => { if (await act(() => api("/sessions/entry", "POST", {vehicle_id: +$("#v").value, slot_id: +$("#sl").value}), r => "Entry recorded, session " + r.session_id)) parking(el); };
  el.querySelectorAll("[data-exit]").forEach(b => b.onclick = async () => { const r = await act(() => api(`/sessions/${b.dataset.exit}/exit`, "POST"), r => "Exit done. Amount " + money(r.amount_due)); if (r) { await parking(el); showBill(r.bill); } });
  el.querySelectorAll("[data-bill]").forEach(b => b.onclick = async () => showBill(await act(() => api("/bills/" + b.dataset.bill))));
  function showBill(b) {
    if (!b) return;
    $("#bill").innerHTML = `<div class="card"><h3>Bill — session ${b.session_id} · ${esc(b.reg_number)} · ${esc(b.slot_code)}</h3>
    <table><tr><td>Parked</td><td>${esc(b.entry_time)} → ${esc(b.exit_time)} (${b.duration_minutes} min)</td></tr>
    <tr><td>Free grace</td><td>${b.grace_minutes} min → ${b.billable_minutes} billable min = ${b.hourly_blocks} × ${money(b.hourly_rate)}</td></tr>
    <tr><td>Minimum / daily cap</td><td>${money(b.min_charge)} / ${b.daily_cap == null ? "none" : money(b.daily_cap)}</td></tr>
    <tr><td><b>Parking fee</b></td><td><b>${money(b.parking_fee)}</b></td></tr><tr><td>Fines (separate)</td><td>${money(b.fines)}</td></tr>
    <tr><td>Payment</td><td>${esc(b.payment_status || "—")} ${b.payment_method ? "via " + esc(b.payment_method) : ""}</td></tr></table>
    ${["PENDING", "FAILED"].includes(b.payment_status) ? `<div class="row" style="margin-top:10px"><label>Method<select id="m"><option>UPI</option><option>CARD</option><option>CASH</option></select></label>
    <label><span>Simulate failure</span><input id="f" type="checkbox"></label><button id="pay">Pay ${money(b.parking_fee)}</button></div>` : ""}</div>`;
    const p = $("#pay"); if (p) p.onclick = async () => {
      const r = await act(() => api("/payments", "POST", {session_id: b.session_id, method: $("#m").value, simulate_failure: $("#f").checked}));
      if (r) { toast(r.message, r.bill.payment_status !== "PAID"); showBill(r.bill); }
    };
  }
}

// ---------- admin ----------
async function admin(el) {
  const [tf, sl, vi, au] = await Promise.all([api("/admin/tariffs"), api("/slots"), api("/admin/violations"), api("/admin/audit")]);
  el.innerHTML = `<div class="card"><h3>Tariffs</h3><table><tr><th>Type</th><th>Premium</th><th>₹/hour</th><th>Grace min</th><th>Min charge</th><th>Daily cap</th><th>Fine/hour</th><th></th></tr>${tf.map(t => `<tr data-t="${t.tariff_id}">
    <td>${t.vehicle_type}</td><td>${t.is_premium ? "Yes" : "No"}</td>${["hourly_rate", "grace_minutes", "min_charge", "daily_cap", "overstay_fine_per_hour"].map(k => `<td><input size="5" data-k="${k}" value="${t[k] ?? ""}"></td>`).join("")}<td><button>Save</button></td></tr>`).join("")}</table></div>
  <div class="card"><h3>Slot maintenance</h3><div class="row"><label>Slot<select id="sid">${sl.map(s => `<option value="${s.slot_id}">${esc(s.slot_code)} (${s.live_status})</option>`).join("")}</select></label>
  <button id="mt">Set maintenance</button><button id="av" class="sec">Set available</button><button id="jobs" class="sec">Run no-show / overstay / snapshot jobs now</button></div></div>
  <div class="card"><h3>Violations</h3><div class="row"><label>Session no.<input id="vs" size="6"></label><label>Type<select id="vt"><option>OVERSTAY</option><option>WRONG_SLOT</option><option>UNAUTHORIZED_BAY</option></select></label>
  <label>Fine<input id="vf" size="5" value="0"></label><label>Notes<input id="vn"></label><button id="vb">Log violation</button></div>
  ${table([["#", v => v.violation_id], ["Vehicle", v => v.reg_number], ["Type", v => v.violation_type], ["Fine", v => money(v.fine_amount)], ["Status", v => v.status], ["When", v => v.detected_at], ["Notes", v => v.notes || ""]], vi.slice(0, 15))}</div>
  <div class="card"><h3>Audit log (latest)</h3>${table([["When", a => a.created_at], ["Who", a => a.actor || "system"], ["Action", a => a.action], ["Entity", a => a.entity + " #" + a.entity_id], ["Old", a => a.old_value || ""], ["New", a => a.new_value || ""]], au.slice(0, 15))}</div>`;
  el.querySelectorAll("tr[data-t] button").forEach(b => b.onclick = async () => {
    const tr = b.closest("tr"), body = {tariff_id: +tr.dataset.t}; tr.querySelectorAll("input").forEach(i => body[i.dataset.k] = i.value);
    if (await act(() => api("/admin/tariffs", "PUT", body), "Tariff saved.")) admin(el);
  });
  const setSlot = st => async () => { if (await act(() => api(`/admin/slots/${$("#sid").value}/status`, "PUT", {status: st}), "Slot updated.")) admin(el); };
  $("#mt").onclick = setSlot("MAINTENANCE"); $("#av").onclick = setSlot("AVAILABLE");
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
    charts.push(new Chart($("#c1"), {type: "line", data: {labels: rev.map(r => r.revenue_date), datasets: [{label: "₹", data: rev.map(r => r.revenue), borderColor: "#1565c0", tension: .25}]}, options: {plugins: {legend: {display: false}}}}));
    charts.push(new Chart($("#c2"), {type: "bar", data: {labels: hr.map(h => h.hour_of_day + ":00"), datasets: [{label: "Entries", data: hr.map(h => h.entries), backgroundColor: "#1565c0"}]}, options: {plugins: {legend: {display: false}}}}));
  } else el.insertAdjacentHTML("beforeend", "<p class='mut'>Charts need internet access for Chart.js.</p>");
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"], m = {};
  fc.forEach(f => m[f.day_of_week + "-" + f.hour_of_day] = f.avg_occupancy_pct);
  const col = p => p == null ? "transparent" : `hsl(${120 - Math.min(p, 100) * 1.2},65%,${p == null ? 50 : 55}%)`;
  $("#heat").innerHTML = `<table class="heat"><tr><th></th>${[...Array(24).keys()].map(h => `<th>${h}</th>`).join("")}</tr>` + days.map((d, i) =>
    `<tr><th>${d}</th>${[...Array(24).keys()].map(h => { const p = m[(i + 1) + "-" + h]; return `<td style="background:${col(p)}" title="${p ?? "no data"}%">${p == null ? "" : Math.round(p)}</td>`; }).join("")}</tr>`).join("") + "</table>";
}
boot();

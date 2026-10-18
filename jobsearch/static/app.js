"use strict";
const $ = (s) => document.querySelector(s);
let lastUnderstood = null;

function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "text") n.textContent = v;
    else if (k === "class") n.className = v;
    else n.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) n.append(k.nodeType ? k : document.createTextNode(String(k)));
  return n;
}

function safeUrl(u) {
  try { const p = new URL(u); return p.protocol === "https:" || p.protocol === "http:" ? p.href : "#"; } catch { return "#"; }
}

// ---- CV picker ----
const cv = $("#cv"), drop = $("#drop");
function showFile() {
  const f = cv.files[0];
  $("#cv-name").textContent = f ? `${f.name} (${Math.max(1, Math.round(f.size / 1024))} KB)` : "Upload PDF, Word or text";
  $("#cv-clear").hidden = !f;
}
cv.addEventListener("change", showFile);
$("#cv-clear").addEventListener("click", (e) => { e.preventDefault(); cv.value = ""; showFile(); });
["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => { if (e.dataTransfer.files.length) { cv.files = e.dataTransfer.files; showFile(); } });

// ---- search ----
$("#form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("#req").value.trim(), loc = $("#loc").value.trim(), file = cv.files[0];
  if (!text && !file) { status("Write what you are looking for, or upload your CV.", true); $("#req").focus(); return; }
  if (file && file.size > 5 * 1024 * 1024) { status("The CV must be smaller than 5 MB.", true); return; }
  $("#go").disabled = true;
  status(file ? "Reading your CV and searching…" : "Searching company career pages, job boards and the web…");
  $("#results").replaceChildren(...Array.from({ length: 3 }, () => el("div", { class: "skeleton" })));
  $("#understood").hidden = true; $("#sources").hidden = true;
  try {
    let res;
    if (file) {
      const fd = new FormData();
      fd.append("cv", file); fd.append("requirements", text); fd.append("location", loc); fd.append("limit", "30");
      res = await fetch("/v1/search/cv", { method: "POST", body: fd });
    } else {
      res = await fetch("/v1/search", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requirements: text, location: loc, limit: 30 }) });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.");
    render(data);
    status("");
  } catch (err) {
    $("#results").replaceChildren(el("div", { class: "card empty err", text: err.message }));
    status("");
  } finally {
    $("#go").disabled = false;
  }
});

function status(msg, isErr) { const s = $("#status"); s.textContent = msg; s.className = isErr ? "err" : "muted"; }

function chip(label, value, cls) { return el("span", { class: "chip" + (cls ? " " + cls : "") }, el("b", { text: label + ": " }), value); }

function render(data) {
  const r = data.requirements;
  lastUnderstood = r;
  const nice = (list) => list.map((x) => (data.display && data.display[x]) || x);
  const chips = [];
  if (r.titles.length) chips.push(chip("Role", r.titles.map((t) => t[0].toUpperCase() + t.slice(1)).join(", ")));
  if (r.skills.length) chips.push(chip("Skills", nice(r.skills.slice(0, 10)).join(", ")));
  if (r.nice_skills.length) chips.push(chip("Nice to have", nice(r.nice_skills).join(", ")));
  if (r.places.length) chips.push(chip("Where", r.places.map((p) => p.name).join(", ")));
  if (r.work_modes.length) chips.push(chip("Work", r.work_modes.join(" or ")));
  if (r.seniority) chips.push(chip("Level", r.seniority + (r.years_experience ? ` (${r.years_experience} yrs)` : "")));
  if (r.salary_min) chips.push(chip("Min pay", `${Math.round(r.salary_min).toLocaleString()} ${r.salary_currency || ""}/${r.salary_period}`));
  if (r.employment_types.length) chips.push(chip("Type", r.employment_types.map((t) => t.replace("_", "-")).join(", ")));
  if (r.visa_sponsorship) chips.push(chip("Visa", "sponsorship needed"));
  if (r.posted_within_days) chips.push(chip("Posted", `last ${r.posted_within_days} days`));
  if (r.keywords.length) chips.push(chip("Prefer", r.keywords.join(", ")));
  if (r.exclude.length) chips.push(chip("Avoid", r.exclude.join(", "), "no"));
  $("#chips").replaceChildren(...chips);
  $("#understood").hidden = false;

  const out = [];
  out.push(el("p", { class: "summary", text: data.results.length
    ? `${data.total_found} jobs matched. Showing the best ${data.results.length}. (${(data.elapsed_ms / 1000).toFixed(1)}s)`
    : "" }));
  if (!data.results.length) {
    out.push(el("div", { class: "card empty" }, el("p", { text: "No jobs matched every requirement right now." }),
      el("p", { class: "muted", text: "Try fewer limits (salary, posted date), a broader place, or save this search to get alerts when new jobs appear." })));
  }
  for (const m of data.results) out.push(jobCard(m));
  $("#results").replaceChildren(...out);

  $("#source-list").replaceChildren(...data.sources.map((s) => el("li", {},
    `${s.name}: `, s.skipped ? el("span", { class: "muted", text: s.skipped })
      : s.ok ? `${s.jobs} jobs` : el("span", { class: "err", text: s.error || "failed" }))));
  $("#sources").hidden = false;
}

function jobCard(m) {
  const j = m.job;
  const posted = j.posted_at ? ago(new Date(j.posted_at)) : null;
  const meta = el("div", { class: "meta" },
    el("span", { class: "co", text: j.company || "Company not listed" }),
    j.location ? el("span", { text: j.location.length > 70 ? j.location.slice(0, 70) + "…" : j.location }) : null,
    posted ? el("span", { text: posted }) : null,
    el("span", { class: "muted", text: "via " + (j.source_name || j.source) }));
  const why = el("div", { class: "why" },
    ...m.reasons.slice(0, 6).map((x) => el("span", { class: "ok", text: x })),
    ...m.warnings.slice(0, 3).map((x) => el("span", { class: "warn", text: x })));
  const score = Math.round(m.score);
  const actions = el("div", { class: "job-actions" },
    el("a", { class: "btn primary", href: safeUrl(j.url), target: "_blank", rel: "noopener noreferrer", text: "View and apply" }));
  if (j.also_on && j.also_on.length) {
    actions.append(el("span", { class: "also muted" }, "Also on ",
      ...j.also_on.slice(0, 3).flatMap((a, i) => [i ? ", " : "", el("a", { href: safeUrl(a.url), target: "_blank", rel: "noopener noreferrer", text: a.source })])));
  }
  return el("article", { class: "card job" },
    el("h3", {}, el("a", { href: safeUrl(j.url), target: "_blank", rel: "noopener noreferrer", text: j.title })),
    el("div", { class: "score", title: "How well this job fits what you asked for" },
      el("span", { class: "num", text: score }), el("span", { class: "of", text: "/100 match" }),
      el("div", { class: "bar" }, el("i", { style: null }))),
    meta, why, actions);
}

// widths without inline styles (CSP): set after insertion
const obs = new MutationObserver(() => {
  document.querySelectorAll(".job").forEach((card) => {
    const n = card.querySelector(".num"); const i = card.querySelector(".bar i");
    if (n && i && !i.dataset.set) { i.style.width = Math.max(4, Math.min(100, +n.textContent)) + "%"; i.dataset.set = "1"; }
  });
});
obs.observe($("#results"), { childList: true });

function ago(d) {
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (isNaN(days)) return null;
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months === 1 ? "a month ago" : `${months} months ago`;
}

// ---- alerts ----
const dlg = $("#dlg");
$("#save").addEventListener("click", () => { $("#dlg-out").replaceChildren(); $("#dlg-ok").hidden = false; dlg.showModal(); });
$("#dlg-ok").addEventListener("click", async (e) => {
  e.preventDefault();
  if (!lastUnderstood) return;
  $("#dlg-ok").disabled = true;
  try {
    const res = await fetch("/v1/alerts", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ understood: lastUnderstood, every_hours: +$("#every").value, webhook_url: $("#hook").value.trim() || null }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Could not create the alert.");
    $("#dlg-out").replaceChildren(el("div", { class: "out" },
      el("p", { text: "Alert created. Add this private feed to any RSS reader:" }),
      el("a", { href: safeUrl(data.feed_url), target: "_blank", rel: "noopener", text: data.feed_url }),
      el("p", { class: "muted", text: "Keep this link private. It is shown only once. To stop the alert, send DELETE to " + data.manage_url })));
    $("#dlg-ok").hidden = true;
  } catch (err) {
    $("#dlg-out").replaceChildren(el("p", { class: "err", text: err.message }));
  } finally {
    $("#dlg-ok").disabled = false;
  }
});

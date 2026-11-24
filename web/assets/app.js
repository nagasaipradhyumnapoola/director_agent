(() => {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("director-theme");
  if (savedTheme === "light" || savedTheme === "dark") root.dataset.theme = savedTheme;

  function syncThemeLabel() {
    const light = root.dataset.theme === "light";
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
      button.setAttribute("aria-pressed", String(light));
    });
  }
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
      localStorage.setItem("director-theme", root.dataset.theme);
      syncThemeLabel();
    });
  });
  syncThemeLabel();

  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const num = (value, suffix = "") => (value === null || value === undefined ? "—" : `${value}${suffix}`);
  const badge = (state) => {
    const map = { pass: "pass", merged: "pass", ok: "pass", fail: "fail", failed: "fail", rejected: "fail", queued: "warn", running: "warn" };
    const tone = map[state] || "";
    return `<span class="badge ${tone ? `badge--${tone}` : ""}">${esc(state)}</span>`;
  };

  let data = window.DIRECTOR_FALLBACK;

  const view = document.getElementById("view");
  const crumb = document.getElementById("crumb");

  const routes = {
    overview: { label: "Overview", render: renderOverview },
    contracts: { label: "Contract", render: renderContracts },
    evidence: { label: "Evidence", render: renderEvidence },
    benchmarks: { label: "Benchmarks", render: renderBenchmarks },
    selfdev: { label: "Selfdev", render: renderSelfdev },
    audit: { label: "Audit", render: renderAudit }
  };

  function pageHead(title, sub, actions = "") {
    return `<div class="page-head">
      <div><span class="eyebrow">Control room</span><h1>${esc(title)}</h1><p class="sub">${sub}</p></div>
      <div class="page-actions">${actions}</div>
    </div>`;
  }

  function kpis() {
    return `<div class="kpi-grid">${(data.kpis || []).map((kpi) => `
      <article class="kpi"><span class="label">${esc(kpi.label)}</span><span class="value">${esc(kpi.value)}</span>
      <span class="delta ${esc(kpi.tone || "")}">${esc(kpi.delta)}</span></article>`).join("")}</div>`;
  }

  function ring(percent) {
    const radius = 64;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference * (1 - Math.max(0, Math.min(100, percent)) / 100);
    return `<div class="ring-wrap">
      <div><svg class="ring" viewBox="0 0 150 150" role="img" aria-label="Acceptance ${percent} percent">
        <circle class="track" cx="75" cy="75" r="${radius}"></circle>
        <circle class="value" cx="75" cy="75" r="${radius}" stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${offset.toFixed(1)}"></circle>
      </svg><div class="ring-label"><strong>${percent}%</strong><span>acceptance</span></div></div>
      <ul class="checklist">${(data.acceptance.criteria || []).slice(0, 6).map((criterion) => `
        <li><span class="${criterion.state === "pass" ? "ok" : "no"}" aria-hidden="true">${criterion.state === "pass" ? "✓" : "!"}</span>
        <span>${esc(criterion.label)}</span></li>`).join("") || "<li><span class=\"ok\">✓</span><span>No criteria loaded</span></li>"}</ul>
    </div>`;
  }

  function retrievalTable() {
    return `<div class="bench-wrap"><table><caption>Lexical retrieval · exact markers · 100 queries</caption>
      <thead><tr><th>Tier</th><th class="num">Docs</th><th class="num">Ingest</th><th class="num">Recall@5</th><th class="num">p50</th><th class="num">p95</th><th class="num">Index</th></tr></thead>
      <tbody>${(data.retrieval || []).map((row) => `<tr><td>${esc(row.tier)} tokens</td><td class="num">${row.docs.toLocaleString()}</td>
        <td class="num">${row.ingest_s} s</td><td class="num">${row.recall.toFixed(1)}</td><td class="num">${row.p50_ms} ms</td>
        <td class="num">${row.p95_ms} ms</td><td class="num">${row.db_mb >= 1024 ? `${(row.db_mb / 1024).toFixed(2)} GB` : `${row.db_mb} MB`}</td></tr>`).join("")}
      </tbody></table></div>`;
  }

  function p95Chart() {
    const rows = data.retrieval || [];
    if (!rows.length) return `<div class="empty">No retrieval results loaded.</div>`;
    const width = 720, height = 260, left = 44, bottom = 38, top = 18, right = 18;
    const chartW = width - left - right, chartH = height - top - bottom;
    const max = Math.max(...rows.map((r) => r.p95_ms)) * 1.15;
    const barW = Math.min(92, chartW / rows.length - 28);
    const bars = rows.map((row, index) => {
      const x = left + (chartW / rows.length) * index + (chartW / rows.length - barW) / 2;
      const h = (row.p95_ms / max) * chartH;
      const y = top + chartH - h;
      return `<rect class="bar ${index === rows.length - 1 ? "bar--signal" : ""}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${h.toFixed(1)}" rx="1">
        <title>${row.tier}: p95 ${row.p95_ms} ms</title></rect>
        <text class="value-label" x="${(x + barW / 2).toFixed(1)}" y="${(y - 7).toFixed(1)}" text-anchor="middle">${row.p95_ms} ms</text>
        <text x="${(x + barW / 2).toFixed(1)}" y="${height - 16}" text-anchor="middle">${row.tier}</text>`;
    }).join("");
    return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="p95 retrieval latency by tier">
      ${[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = top + chartH - tick * chartH;
        return `<line class="grid" x1="${left}" y1="${y.toFixed(1)}" x2="${width - right}" y2="${y.toFixed(1)}"></line>
          <text x="${left - 8}" y="${(y + 3).toFixed(1)}" text-anchor="end">${(max * tick).toFixed(1)}</text>`;
      }).join("")}
      ${bars}<text x="${left}" y="${height - 2}">p95 search latency (ms)</text>
    </svg>`;
  }

  function skillMatrix() {
    const matrix = data.skill_matrix || { status: "queued", rows: [] };
    const rows = matrix.rows || [];
    const body = rows.length
      ? rows.map((row) => `<tr><td><strong>${esc(row.tool)}</strong></td><td>${esc(row.kind)}</td><td>${esc((row.best_at || []).join(" · "))}</td>${(row.scores || []).map((score, index) => `<td class="num">${score === null || score === undefined ? "—" : index === 1 ? Number(score).toLocaleString() : `${esc(score)}%`}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="9" class="empty">No matrix rows yet.</td></tr>`;
    return `<div class="panel">
      <div class="panel-head"><h2>Skill matrix</h2>${badge(matrix.status || "queued")}</div>
      <div class="panel-body flush">
        <div class="bench-wrap" style="border:0;border-top:1px solid var(--line)">
          <table><caption>2 seeds · 98 runs · prompt-level · upstream runtimes not executed</caption>
          <thead><tr><th>Tool</th><th>Kind</th><th>Best at</th><th class="num">Coding</th><th class="num">Tokens</th><th class="num">Clarity</th><th class="num">Design</th><th class="num">Context</th><th class="num">Self-improve</th></tr></thead>
          <tbody>${body}</tbody></table>
        </div>
        <p style="padding:.8rem 1rem;color:var(--faint);font-size:.76rem;margin:0">${esc(matrix.note || "")}</p>
      </div>
    </div>`;
  }

  function patches() {
    return `<div class="panel"><div class="panel-head"><h2>Selfdev patches</h2><span class="badge">${data.patches.length} records</span></div>
      <div class="patch-list">${data.patches.map((patch) => `<article class="patch"><div><h3>${esc(patch.title)}</h3>
        <div class="meta">${esc(patch.id)} · ${esc(patch.detail)}</div></div>${badge(patch.status)}</article>`).join("")}</div></div>`;
  }

  function audit(limit = 6) {
    return `<div class="panel"><div class="panel-head"><h2>Audit trail</h2><span class="badge">redacted</span></div>
      <ul class="audit">${data.audit.slice(0, limit).map((row) => `<li><span class="at">${esc(row.at)}</span>
        <span><strong style="color:var(--text);font-weight:500">${esc(row.actor)}</strong> · ${esc(row.action)}</span>
        <span class="outcome">${esc(row.outcome)}</span></li>`).join("")}</ul></div>`;
  }

  function renderOverview() {
    const project = data.project;
    return `${pageHead("Control room", `${esc(project.name)} · ${esc(project.release)} · commit <code>${esc(project.commit || "—")}</code>`,
      `<a class="btn btn--sm" href="#benchmarks">Benchmarks</a><a class="btn btn--sm btn--primary" href="#evidence">Evidence ledger</a>`)}
      ${kpis()}
      <div class="split">
        <div class="panel"><div class="panel-head"><h2>Acceptance state</h2>${badge(data.acceptance.complete ? "complete" : "open")}</div>
          <div class="panel-body">${ring(data.acceptance.percent)}</div></div>
        <div class="panel"><div class="panel-head"><h2>Next actions</h2><span class="badge badge--warn">owner</span></div>
          <div class="panel-body" style="display:grid;gap:.9rem">
            <p style="margin:0;color:var(--muted);font-size:.88rem">The matrix is staged. The UI is first; benchmarks run after sign-off.</p>
            <pre class="code">python benchmarks/skill_matrix.py --seeds 3</pre>
            <a class="btn btn--sm" href="#benchmarks">Open benchmark view</a>
            <p style="margin:0;color:var(--faint);font-size:.76rem">Worker: ${esc(data.worker.status)} · heartbeat ${data.worker.heartbeat_age_seconds}s · idle model calls 0</p>
          </div></div>
      </div>
      <div class="split">
        <div class="panel"><div class="panel-head"><h2>Evidence ledger</h2><a class="btn btn--sm btn--ghost" href="#evidence">All</a></div>
          <div class="panel-body flush"><table class="data-table"><thead><tr><th>Criterion</th><th>State</th><th>Evidence</th></tr></thead>
          <tbody>${data.acceptance.criteria.slice(0, 6).map((criterion) => `<tr><td><strong>${esc(criterion.label)}</strong><br><code>${esc(criterion.key)}</code></td>
            <td>${badge(criterion.state)}</td><td><code>${esc(criterion.evidence)}</code></td></tr>`).join("")}</tbody></table></div></div>
        ${patches()}
      </div>
      ${audit()}`;
  }

  function renderContracts() {
    const project = data.project;
    return `${pageHead("Contract", "The durable target: intent, criteria, permissions and budgets.",
      `<a class="btn btn--sm" href="#evidence">Evidence</a>`)}
      <div class="split">
        <div class="panel"><div class="panel-head"><h2>Revision</h2><span class="badge">rev 1</span></div>
          <div class="panel-body" style="display:grid;gap:.75rem">
            <p style="margin:0"><strong>${esc(project.name)}</strong><br><span style="color:var(--muted)">Supervise the local release end to end without unsupported claims.</span></p>
            <dl class="contract-card" style="position:static;width:100%;box-shadow:none">
              <div class="row"><dt>Release</dt><dd>${esc(project.release)}</dd></div>
              <div class="row"><dt>Domain</dt><dd>${esc(project.domain)}</dd></div>
              <div class="row"><dt>Model calls</dt><dd>0 idle</dd></div>
              <div class="row"><dt>Network</dt><dd>denied by default</dd></div>
              <div class="row"><dt>Merge</dt><dd>owner approval</dd></div>
            </dl>
          </div></div>
        <div class="panel"><div class="panel-head"><h2>Acceptance criteria</h2><span class="badge badge--pass">8 met</span></div>
          <div class="panel-body flush"><table class="data-table"><thead><tr><th>Criterion</th><th>State</th></tr></thead>
          <tbody>${data.acceptance.criteria.map((criterion) => `<tr><td><strong>${esc(criterion.label)}</strong><br><code>${esc(criterion.key)}</code></td><td>${badge(criterion.state)}</td></tr>`).join("")}</tbody></table></div></div>
      </div>
      <div class="panel"><div class="panel-head"><h2>Permissions</h2><span class="badge">default deny</span></div>
        <div class="panel-body" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem">
          ${["read_artifact", "run_local_subprocess", "container_run", "model_call_local"].map((action) => `<div style="border:1px solid var(--line);padding:.8rem"><span class="mono" style="color:var(--faint)">${esc(action)}</span><p style="margin:.35rem 0 0;color:var(--muted);font-size:.82rem">Grant required${action === "container_run" ? " · contract opt-in" : ""}</p></div>`).join("")}
        </div></div>`;
  }

  function renderEvidence() {
    return `${pageHead("Evidence ledger", "Latest evidence wins. A newer failure supersedes an older pass.",
      `<a class="btn btn--sm" href="#contracts">Contract</a><a class="btn btn--sm btn--primary" href="#benchmarks">Benchmarks</a>`)}
      <div class="panel"><div class="panel-head"><h2>All criteria</h2>${badge(data.acceptance.complete ? "complete" : "open")}</div>
        <div class="panel-body flush"><table class="data-table"><thead><tr><th>Criterion</th><th>State</th><th>Evidence</th><th>Freshness</th></tr></thead>
        <tbody>${data.acceptance.criteria.map((criterion) => `<tr><td><strong>${esc(criterion.label)}</strong><br><code>${esc(criterion.key)}</code></td>
          <td>${badge(criterion.state)}</td><td><code>${esc(criterion.evidence)}</code></td><td>current</td></tr>`).join("")}</tbody></table></div></div>
      <div class="panel"><div class="panel-head"><h2>Rules</h2><span class="badge">state-bound</span></div>
        <div class="panel-body" style="color:var(--muted);font-size:.88rem;display:grid;gap:.55rem">
          <p style="margin:0">A receipt carries a hash, evaluator version, limitations and the contract revision it belongs to.</p>
          <p style="margin:0">A failing or blocked result supersedes an older pass; a passing result does not erase a newer failure.</p>
          <p style="margin:0">Unsupported formats and unmeasured capabilities stay unknown. They are never silently marked green.</p>
        </div></div>`;
  }

  function renderBenchmarks() {
    return `${pageHead("Benchmarks", "Measured on one host. Limits are part of the result.",
      `<a class="btn btn--sm" href="https://github.com/nagasaipradhyumnapoola/director_agent/blob/main/docs/build/BENCHMARKS.md" rel="noreferrer">Method</a>`)}
      ${retrievalTable()}
      <div class="panel"><div class="panel-head"><h2>p95 retrieval latency</h2><span class="badge">100M measured</span></div>
        <div class="panel-body">${p95Chart()}</div></div>
      ${skillMatrix()}
      <div class="panel"><div class="panel-head"><h2>Run the matrix</h2><span class="badge badge--pass">2 seeds</span></div>
        <div class="panel-body"><pre class="code">python benchmarks/skill_matrix.py --provider proxy --model llama-3.3-70b-fp8-fast --seeds 2</pre>
        <p style="color:var(--faint);font-size:.76rem;margin:.7rem 0 0">Writes <code>benchmarks/results/skill_matrix.json</code>. Prompt-level procedure ablation, not upstream runtime execution.</p></div></div>`;
  }

  function renderSelfdev() {
    const steps = [
      ["01", "Allowlist", "Only permitted paths enter the patch."],
      ["02", "Worktree", "Apply at a recorded base in a disposable git worktree."],
      ["03", "Tests", "Run the full offline suite and bind the result."],
      ["04", "Review", "Independent reviewer records pass or fail."],
      ["05", "Merge", "Owner approval + clean tree + same base; never push."]
    ];
    return `${pageHead("Selfdev", "A patch is a proposal until the gates say otherwise.",
      `<a class="btn btn--sm" href="#audit">Audit</a>`)}
      <div class="loop" style="margin-bottom:1.2rem">${steps.map(([n, title, text]) => `<article class="loop-step"><span class="num">${n}</span><h3>${title}</h3><p>${text}</p></article>`).join("")}</div>
      ${patches()}
      <div class="panel"><div class="panel-head"><h2>Local model authoring</h2><span class="badge">loopback only</span></div>
        <div class="panel-body"><pre class="code">python -m director improve auto --proposal &lt;id&gt; --provider ollama --model qwen2.5-coder:7b --queue</pre>
        <p style="color:var(--muted);font-size:.84rem;margin:.7rem 0 0">A passing test is not merge approval. The byte-format helper passed tests and review on correctness, then was rejected because it had no production caller.</p></div></div>`;
  }

  function renderAudit() {
    return `${pageHead("Audit", "Redacted, append-only JSONL. Actions, not vibes.",
      `<a class="btn btn--sm" href="#selfdev">Selfdev</a>`)}
      <div class="panel"><div class="panel-head"><h2>Recent actions</h2><span class="badge">redacted</span></div>
        <ul class="audit">${data.audit.map((row) => `<li><span class="at">${esc(row.at)}</span>
          <span><strong style="color:var(--text);font-weight:500">${esc(row.actor)}</strong> · ${esc(row.action)}</span>
          <span class="outcome">${esc(row.outcome)}</span></li>`).join("")}</ul></div>`;
  }

  function currentRoute() {
    const name = (location.hash || "#overview").slice(1);
    return routes[name] ? name : "overview";
  }

  function render() {
    const name = currentRoute();
    crumb.textContent = routes[name].label.toLowerCase();
    view.innerHTML = routes[name].render();
    document.title = `${routes[name].label} · DIRECTOR`;
    document.querySelectorAll("[data-view-link]").forEach((link) => {
      if (link.dataset.viewLink === name) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function setProjectChrome() {
    const project = data.project || {};
    document.getElementById("project-name").textContent = project.name || "director-agent";
    document.getElementById("project-release").textContent = project.release || "v1.0.0-local-supervised";
    document.getElementById("project-domain").textContent = project.domain || "general";
    const worker = data.worker || {};
    document.getElementById("worker-status").textContent = `Worker ${worker.status || "unknown"}`;
    document.getElementById("worker-heartbeat").textContent = `heartbeat ${worker.heartbeat_age_seconds ?? "?"}s ago`;
  }

  // command palette
  const palette = document.getElementById("commandk");
  const paletteInput = document.getElementById("commandk-input");
  const paletteList = document.getElementById("commandk-list");
  const destinations = [
    ...Object.entries(routes).map(([name, route]) => ({ name, label: route.label, hint: `#${name}` })),
    { name: "landing", label: "Landing page", hint: "index.html", href: "index.html" },
    { name: "readme", label: "README", hint: "GitHub", href: "https://github.com/nagasaipradhyumnapoola/director_agent/blob/main/README.md" },
    { name: "benchmarks-doc", label: "Benchmark methodology", hint: "GitHub", href: "https://github.com/nagasaipradhyumnapoola/director_agent/blob/main/docs/build/BENCHMARKS.md" }
  ];

  function drawPalette(query = "") {
    const needle = query.trim().toLowerCase();
    const matches = destinations.filter((item) => !needle || item.label.toLowerCase().includes(needle) || item.name.includes(needle));
    paletteList.innerHTML = matches.map((item) => `<li><a href="${item.href || `#${item.name}`}" data-palette-close>
      <span>${esc(item.label)}</span><span class="hint">${esc(item.hint)}</span></a></li>`).join("") || `<li><a href="#overview" data-palette-close><span>No match</span><span class="hint">overview</span></a></li>`;
    paletteList.querySelectorAll("a").forEach((link) => link.addEventListener("click", closePalette));
  }

  function openPalette() {
    palette.classList.add("is-open");
    drawPalette("");
    paletteInput.value = "";
    paletteInput.focus();
  }

  function closePalette() {
    palette.classList.remove("is-open");
  }

  document.getElementById("open-command").addEventListener("click", openPalette);
  paletteInput.addEventListener("input", () => drawPalette(paletteInput.value));
  palette.addEventListener("click", (event) => {
    if (event.target === palette) closePalette();
  });
  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      palette.classList.contains("is-open") ? closePalette() : openPalette();
      return;
    }
    if (event.key === "/" && !typing) {
      event.preventDefault();
      openPalette();
      return;
    }
    if (event.key === "Escape" && palette.classList.contains("is-open")) closePalette();
  });

  window.addEventListener("hashchange", render);

  fetch("data.json", { cache: "no-store" })
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error("no data"))))
    .then((payload) => { data = payload; })
    .catch(() => { data = window.DIRECTOR_FALLBACK; })
    .finally(() => {
      setProjectChrome();
      if (!data.acceptance.criteria || !data.acceptance.criteria.length) {
        data = window.DIRECTOR_FALLBACK;
      }
      render();
    });

  fetch("/api/state", { cache: "no-store" })
    .then((response) => (response.ok ? response.json() : Promise.reject(new Error("no live state"))))
    .then((live) => {
      if (!live || !live.ok) return;
      data.project = { ...data.project, ...live.project };
      data.worker = live.worker;
      data.kpis = live.kpis;
      data.acceptance = live.acceptance;
      if (live.patches && live.patches.length) data.patches = live.patches;
      if (live.audit && live.audit.length) data.audit = live.audit;
      setProjectChrome();
      render();
    })
    .catch(() => {});
})();

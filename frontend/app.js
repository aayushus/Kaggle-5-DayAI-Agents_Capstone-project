const trace = document.getElementById("trace");
const result = document.getElementById("result");
const landingResult = document.getElementById("landingResult");
const boardResult = document.getElementById("boardResult");
const warResult = document.getElementById("warResult");
const traceList = document.getElementById("traceList");
const marketReadout = document.getElementById("marketReadout");
const competitorList = document.getElementById("competitorList");
const sourceList = document.getElementById("sourceList");
const hookList = document.getElementById("hookList");
const landingPreview = document.getElementById("landingPreview");
const runButton = document.getElementById("run");
const boardRunButton = document.getElementById("boardRun");
const warRunButton = document.getElementById("warRun");
const runState = document.getElementById("runState");
const competitorCount = document.getElementById("competitorCount");
const auditState = document.getElementById("auditState");
const outputPath = document.getElementById("outputPath");
const outputPdfLink = document.getElementById("outputPdfLink");
const tamValue = document.getElementById("tamValue");
const samValue = document.getElementById("samValue");
const somValue = document.getElementById("somValue");
const marketDoc = document.getElementById("marketDoc");
const geoField = document.getElementById("geoField");
const geoTrigger = document.getElementById("geoTrigger");
const geoMenu = document.getElementById("geoMenu");
const sectorField = document.getElementById("sectorField");
const sectorInput = document.getElementById("sectorInput");
const formError = document.getElementById("formError");
let latestResult = null;
let rawVisible = false;
let boardSessionId = null;
let warSessionId = null;
let boardHistory = [];
let warHistory = [];

const GEO_OPTIONS = [
  "Global",
  "United States",
  "Canada",
  "Latin America",
  "United Kingdom",
  "Europe",
  "Middle East & Africa",
  "India",
  "Southeast Asia",
  "East Asia",
  "Australia & New Zealand",
];
const geoState = new Set(["United States"]);
const sectorState = ["real estate", "dscr", "residential"];

function makeChip(labelText, onRemove) {
  const chip = document.createElement("span");
  chip.className = "chip";
  const label = document.createElement("span");
  label.textContent = labelText;
  const remove = document.createElement("button");
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove ${labelText}`);
  remove.textContent = "✕";
  remove.addEventListener("click", onRemove);
  chip.append(label, remove);
  return chip;
}

function renderGeoChips() {
  geoField.querySelectorAll(".chip").forEach((chip) => chip.remove());
  [...geoState].forEach((region) => {
    geoField.insertBefore(
      makeChip(region, () => {
        geoState.delete(region);
        renderGeoChips();
        renderGeoMenu();
      }),
      geoTrigger,
    );
  });
}

function renderGeoMenu() {
  geoMenu.innerHTML = "";
  GEO_OPTIONS.forEach((region) => {
    const option = document.createElement("button");
    option.type = "button";
    option.setAttribute("role", "option");
    const selected = geoState.has(region);
    option.className = `select-option${selected ? " selected" : ""}`;
    option.setAttribute("aria-selected", String(selected));
    option.innerHTML = `<span>${escapeHtml(region)}</span>${selected ? "<span>✓</span>" : ""}`;
    option.addEventListener("click", () => {
      if (geoState.has(region)) {
        geoState.delete(region);
      } else if (region === "Global") {
        geoState.clear();
        geoState.add("Global");
      } else {
        geoState.delete("Global");
        geoState.add(region);
      }
      renderGeoChips();
      renderGeoMenu();
    });
    geoMenu.appendChild(option);
  });
}

geoTrigger.addEventListener("click", () => {
  geoMenu.classList.toggle("hidden");
});

document.addEventListener("click", (event) => {
  if (!geoField.contains(event.target)) {
    geoMenu.classList.add("hidden");
  }
});

function renderSectorChips() {
  sectorField.querySelectorAll(".chip").forEach((chip) => chip.remove());
  sectorState.forEach((sector, index) => {
    sectorField.insertBefore(
      makeChip(sector, () => {
        sectorState.splice(index, 1);
        renderSectorChips();
      }),
      sectorInput,
    );
  });
}

function addSector(rawValue) {
  const value = String(rawValue || "").trim().replace(/,+$/, "");
  if (!value) return;
  const exists = sectorState.some((item) => item.toLowerCase() === value.toLowerCase());
  if (!exists) {
    sectorState.push(value);
    renderSectorChips();
  }
  sectorInput.value = "";
}

sectorInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === ",") {
    event.preventDefault();
    addSector(sectorInput.value);
  } else if (event.key === "Backspace" && !sectorInput.value && sectorState.length) {
    sectorState.pop();
    renderSectorChips();
  }
});

sectorInput.addEventListener("blur", () => addSector(sectorInput.value));

renderGeoChips();
renderGeoMenu();
renderSectorChips();

function validateBrief() {
  const problems = [];
  if (document.getElementById("concept").value.trim().length < 5) {
    problems.push("Describe the startup concept in at least a short sentence.");
  }
  if (!geoState.size) {
    problems.push("Add at least one geography (Global works).");
  }
  if (!sectorState.length && !sectorInput.value.trim()) {
    problems.push("Add at least one sector.");
  }
  if (document.getElementById("funding").value.trim().length < 2) {
    problems.push("Describe the funding stage or scale.");
  }
  return problems;
}

function showFormError(message) {
  formError.textContent = message;
  formError.classList.toggle("hidden", !message);
}

async function apiErrorMessage(resp) {
  try {
    const data = await resp.json();
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item) => {
          const field = (item.loc || []).slice(1).join(".") || "request";
          return `${readableLabel(field)}: ${item.msg}`;
        })
        .join(" · ");
    }
    if (typeof data.detail === "string") return data.detail;
  } catch {
    /* body was not JSON */
  }
  return `Request failed with HTTP ${resp.status}`;
}

document.querySelectorAll(".tab").forEach((button) => {
  button.addEventListener("click", () => {
    switchTab(button.dataset.tab);
  });
});

function switchTab(targetId) {
  document.querySelectorAll(".tab").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === targetId);
  });
  ["research", "board", "warroom", "landing", "about"].forEach((id) => {
    document.getElementById(id).classList.toggle("hidden", id !== targetId);
  });
}

document.getElementById("rawToggle").addEventListener("click", () => {
  rawVisible = !rawVisible;
  result.style.display = rawVisible ? "block" : "none";
  marketReadout.style.display = rawVisible ? "none" : "block";
  document.getElementById("rawToggle").textContent = rawVisible ? "Summary" : "Raw JSON";
});

async function consumeSSE(resp, onEvent) {
  if (!resp.ok || !resp.body) {
    throw new Error(`Request failed with HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
      if (!dataLine) continue;
      onEvent(JSON.parse(dataLine.slice(6)));
    }
  }
}

function getPayload() {
  addSector(sectorInput.value);
  return {
    concept: document.getElementById("concept").value.trim(),
    geography: [...geoState].join(", "),
    sector: sectorState.join(", "),
    funding_scale: document.getElementById("funding").value.trim(),
  };
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function compactMoney(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: value >= 1000000 ? 1 : 0,
  }).format(value);
}

function monthlyPrice(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Price unknown";
  return `${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)}/mo`;
}

function shortPath(path) {
  if (!path) return "No file";
  const parts = String(path).split("/");
  return parts[parts.length - 1] || path;
}

function syncArtifactActions(path) {
  outputPath.textContent = shortPath(path);
  outputPath.title = path || "";
  if (!path) {
    outputPdfLink.classList.add("hidden");
    outputPdfLink.removeAttribute("href");
    return;
  }
  outputPdfLink.href = `/api/artifacts/pdf?path=${encodeURIComponent(path)}`;
  outputPdfLink.classList.remove("hidden");
}

function isResearchReady() {
  if (!latestResult?.report || !latestResult?.market_markdown_path) return false;
  const passed = latestResult.report?.audit?.passed;
  return passed !== false;
}

function resetRunUi() {
  latestResult = null;
  boardSessionId = null;
  warSessionId = null;
  boardHistory = [];
  warHistory = [];
  trace.textContent = "";
  result.textContent = "";
  landingResult.textContent = "";
  traceList.innerHTML = "";
  marketReadout.innerHTML = loadingHtml("Research running", "Northstar is collecting live evidence and validating the report.");
  competitorList.innerHTML = loadingHtml("Building competitor field", "Validated sources will appear as soon as the run completes.");
  sourceList.innerHTML = loadingHtml("Building citations", "Research links, extracted facts, and assumptions will be separated after audit.");
  hookList.innerHTML = loadingHtml("Generating copy", "Landing hooks will appear after the research pass.");
  landingPreview.innerHTML = "<h3>Research in progress.</h3><p>Northstar is looking for the most defensible launch angle.</p>";
  boardResult.innerHTML = emptyHtml("No board session", "Research must complete before the advisory board can start.");
  warResult.innerHTML = emptyHtml("No war room session", "Research must complete before the war room can start.");
  marketDoc.innerHTML = loadingHtml("Writing artifact", "The market document will render here once Northstar finishes the run.");
  tamValue.textContent = "-";
  samValue.textContent = "-";
  somValue.textContent = "-";
  competitorCount.textContent = "0";
  auditState.textContent = "Running";
  syncArtifactActions("");
  outputPath.textContent = "Pending";
  runState.textContent = "Researching";
  setStatus(runState, "warn");
  setStatus(auditState, "warn");
  runButton.disabled = true;
  runButton.textContent = "Running Research";
  updateDependentActions();
}

function finishRunUi() {
  runButton.disabled = false;
  runButton.textContent = "Run Research";
  updateDependentActions();
}

function failRunUi(message) {
  runState.textContent = "Failed";
  auditState.textContent = "Failed";
  setStatus(runState, "bad");
  setStatus(auditState, "bad");
  syncArtifactActions("");
  outputPath.textContent = "—";
  result.textContent = message;
  marketReadout.innerHTML = emptyHtml("Run failed", message);
  competitorList.innerHTML = emptyHtml("No competitors loaded", "Fix the issue above and run research again.");
  sourceList.innerHTML = emptyHtml("No evidence yet", "Citations and assumptions are split here after audit.");
  marketDoc.innerHTML = emptyHtml("No document yet", "The markdown artifact renders here after research.");
  hookList.innerHTML = emptyHtml("No copy yet", "Run research to build the launch narrative.");
  landingPreview.innerHTML = "<h3>Run research to generate the first-page offer.</h3><p>The strongest differentiation angle will appear here.</p>";
  addTraceLine(message, true);
}

function setStatus(element, status) {
  element.classList.remove("status-good", "status-warn", "status-bad");
  if (status) element.classList.add(`status-${status}`);
}

function emptyHtml(title, body) {
  return `<div class="empty-state"><div><strong>${escapeHtml(title)}</strong>${escapeHtml(body)}</div></div>`;
}

function loadingHtml(title, body) {
  return `
    <div class="empty-state">
      <div class="loading-shell">
        <div><strong>${escapeHtml(title)}</strong>${escapeHtml(body)}</div>
        <div class="loading-bar loading-wide"></div>
        <div class="loading-bar loading-mid"></div>
        <div class="loading-bar loading-short"></div>
      </div>
    </div>
  `;
}

function addTraceLine(message, isError = false) {
  trace.textContent += `${message}\n`;
  const line = document.createElement("div");
  line.className = `trace-item${isError ? " error" : ""}`;
  line.innerHTML = `<span class="trace-dot"></span><span>${escapeHtml(message)}</span>`;
  traceList.appendChild(line);
  traceList.scrollTop = traceList.scrollHeight;
}

function renderReport(payload) {
  latestResult = payload;
  boardSessionId = null;
  warSessionId = null;
  boardHistory = [];
  warHistory = [];
  const report = payload.report || {};
  const competitors = report.competitors || [];
  const audit = report.audit || {};
  const sizing = report.market_sizing || {};
  const bottomUp = sizing.bottom_up || {};
  const assumptions = sizing.assumptions || {};
  const provenance = report.provenance || {};
  const blueprint = report.landing_page_blueprint || {};
  const topDown = sizing.top_down || {};

  result.textContent = JSON.stringify(payload, null, 2);
  landingResult.textContent = JSON.stringify(blueprint, null, 2);

  runState.textContent = "Complete";
  competitorCount.textContent = String(competitors.length);
  auditState.textContent = audit.passed ? "Passed" : "Needs revision";
  setStatus(runState, "good");
  setStatus(auditState, audit.passed ? "good" : "bad");
  setStatus(competitorCount, competitors.length ? "good" : "warn");
  syncArtifactActions(payload.market_markdown_path);
  tamValue.textContent = compactMoney(bottomUp.tam);
  samValue.textContent = compactMoney(bottomUp.sam);
  somValue.textContent = compactMoney(bottomUp.som);

  marketReadout.innerHTML = `
    <div class="metric-grid">
      <div class="metric metric-info"><span>Avg Price <button class="info-tip" type="button" data-tip="Average monthly price extracted or inferred from the competitor set.">?</button></span><strong>${monthlyPrice(assumptions.monthly_price)}</strong></div>
      <div class="metric metric-warn"><span>Capture Rate <button class="info-tip" type="button" data-tip="The assumed share of reachable market Northstar models as obtainable in the near term.">?</button></span><strong>${escapeHtml(formatPercent(assumptions.capture_rate))}</strong></div>
      <div class="metric ${audit.passed ? "metric-good" : "metric-warn"}"><span>Audit <button class="info-tip" type="button" data-tip="Validation status for required fields, numeric sanity, provenance, and URL resolution.">?</button></span><strong>${audit.passed ? "Passed" : "Failed"}</strong></div>
    </div>
    <div class="metric-grid" style="margin-top: 10px">
      <div class="metric metric-good"><span>Sector Basis</span><strong style="font-size: 1rem">${escapeHtml(assumptions.sector_profile || "Modeled profile")}</strong></div>
      <div class="metric metric-info"><span>Top-Down Basis</span><strong style="font-size: 1rem">${compactMoney(topDown.tam)}</strong></div>
      <div class="metric metric-warn"><span>Cited Sources</span><strong style="font-size: 1rem">${escapeHtml(String((provenance.source_facts || []).length))}</strong></div>
    </div>
    <div class="metric-grid" style="margin-top: 10px">
      <div class="metric ${(audit.link_summary?.failed || 0) ? "metric-warn" : "metric-good"}"><span>Links Checked</span><strong style="font-size: 1rem">${escapeHtml(String(audit.link_summary?.checked || 0))}</strong></div>
      <div class="metric ${(audit.link_summary?.failed || 0) ? "metric-bad" : "metric-good"}"><span>Link Failures</span><strong style="font-size: 1rem">${escapeHtml(String(audit.link_summary?.failed || 0))}</strong></div>
      <div class="metric ${(audit.schema_issue_count || 0) ? "metric-warn" : "metric-good"}"><span>Schema Issues</span><strong style="font-size: 1rem">${escapeHtml(String(audit.schema_issue_count || 0))}</strong></div>
    </div>
    ${renderTopDownEvidence(topDown)}
    <div class="persona-list" style="margin-top: 10px">
      ${(report.customer_personas || []).map(renderPersona).join("") || emptyHtml("No personas", "The report did not include customer personas.")}
    </div>
  `;

  competitorList.innerHTML = competitors.map(renderCompetitor).join("") || emptyHtml("No competitors found", "Research completed without usable competitor records.");
  sourceList.innerHTML = renderSources(provenance);
  renderLanding(blueprint);
  renderMarketDoc(payload.market_markdown || "");
  updateDependentActions();
}

function updateDependentActions() {
  const hasResearch = isResearchReady();
  boardRunButton.disabled = !hasResearch;
  warRunButton.disabled = !hasResearch;
  boardRunButton.textContent = !hasResearch ? "Run Research First" : boardSessionId ? "Send Board Follow-up" : "Start Advisory Board";
  warRunButton.textContent = !hasResearch ? "Run Research First" : warSessionId ? "Send War-Room Follow-up" : "Start War Room";
}

function formatPercent(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;
}

function renderPersona(persona) {
  const triggers = (persona.buying_triggers || []).slice(0, 4);
  return `
    <article class="persona-card">
      <h4>${escapeHtml(persona.name)}</h4>
      <p style="color: var(--muted); margin: 8px 0 0">${escapeHtml(persona.value_proposition || persona.demographics || "")}</p>
      <div class="feature-row">
        ${triggers.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}
      </div>
    </article>
  `;
}

function renderTopDownEvidence(topDown) {
  if (!topDown || !topDown.tam) return "";
  const reasons = (topDown.confidence_reasons || []).map((item) => `<span class="tag">${escapeHtml(readableLabel(item))}</span>`).join("");
  const sourceLabel = topDown.source_type === "external" ? "External Source" : "Benchmark Fallback";
  const detailLine = topDown.source_excerpt || topDown.benchmark_basis || topDown.source || "";
  return `
    <article class="source-card" style="margin-top: 10px">
      <h4>Top-Down TAM Source</h4>
      <div class="evidence-meta">
        <span class="evidence-label">${escapeHtml(sourceLabel)}</span>
        ${topDown.display_value ? `<span class="tag">${escapeHtml(topDown.display_value)}</span>` : ""}
        ${typeof topDown.confidence_score === "number" ? `<span class="tag">Confidence ${escapeHtml(String(Math.round(topDown.confidence_score * 100)))}%</span>` : ""}
      </div>
      <p style="color: var(--ink); margin: 10px 0 0">${escapeHtml(topDown.source || "No source recorded")}</p>
      ${topDown.source_url ? renderSourceLink(topDown.source_url) : ""}
      ${reasons ? `<div class="feature-row">${reasons}</div>` : ""}
      ${detailLine ? `<p style="color: var(--muted); margin: 10px 0 0">${escapeHtml(cleanEvidence(detailLine))}</p>` : ""}
    </article>
  `;
}

function toneClass(kind, value) {
  const normalized = String(value || "").toLowerCase();
  if (kind === "quality") {
    if (normalized.includes("high") || normalized.includes("strong")) return "tone-good";
    if (normalized.includes("medium")) return "tone-warn";
    return "tone-bad";
  }
  if (kind === "pricing") {
    if (normalized.includes("public")) return "tone-good";
    if (normalized.includes("contact") || normalized.includes("unknown")) return "tone-warn";
    return "tone-info";
  }
  if (kind === "basis") {
    if (normalized.includes("extracted") || normalized.includes("external")) return "tone-good";
    if (normalized.includes("fallback") || normalized.includes("benchmark") || normalized.includes("estimate")) return "tone-warn";
    return "tone-info";
  }
  return "tone-info";
}

function renderBadge(text, tone = "tone-info") {
  if (!text) return "";
  return `<span class="tag ${tone}">${escapeHtml(text)}</span>`;
}

function renderPricingVisibilityBadge(visibility) {
  const value = String(visibility || "").toLowerCase();
  if (value === "public-price") return renderBadge("Public pricing", "tone-good");
  if (value === "contact-sales") return renderBadge("Contact sales", "tone-warn");
  if (value === "not-listed") return renderBadge("Price not listed", "tone-neutral");
  return "";
}

function renderCompetitor(competitor) {
  const features = (competitor.features || []).filter(Boolean).slice(0, 4);
  const strengths = (competitor.strengths || []).filter(Boolean).slice(0, 2);
  const weaknesses = (competitor.weaknesses || []).filter(Boolean).slice(0, 2);
  const sourceQuality = competitor.source_quality || {};
  const sourceUrl = competitor.source_url || competitor.pricing_url || "";
  const hasPublicPrice = competitor.price_source_type === "extracted";
  const priceKnown = typeof competitor.price_monthly === "number" && Number.isFinite(competitor.price_monthly);
  const priceLabel = !priceKnown
    ? "Price N/A"
    : hasPublicPrice
      ? monthlyPrice(competitor.price_monthly)
      : `~${monthlyPrice(competitor.price_monthly)} est.`;
  return `
    <article class="competitor-card">
      <div class="competitor-top">
        <div>
          <h4>${escapeHtml(competitor.name)}</h4>
          ${sourceUrl ? renderSourceLink(sourceUrl) : ""}
        </div>
        <span class="price-pill">${escapeHtml(priceLabel)}</span>
      </div>
      <div class="evidence-meta">
        ${renderBadge(hasPublicPrice ? "Verified price" : "Modeled estimate", hasPublicPrice ? "tone-good" : "tone-warn")}
        ${renderPricingVisibilityBadge(competitor.pricing_visibility)}
        ${sourceQuality.label ? renderBadge(`Evidence ${sourceQuality.label}`, toneClass("quality", sourceQuality.label)) : ""}
      </div>
      <div class="feature-row">
        ${features.map((item) => `<span class="tag">${escapeHtml(cleanFeature(item))}</span>`).join("")}
      </div>
      ${strengths.length ? `<p class="insight-line"><strong>What they do well:</strong> ${escapeHtml(strengths.map(cleanFeature).join(" "))}</p>` : ""}
      ${weaknesses.length ? `<p style="color: var(--muted); margin: 10px 0 0">${escapeHtml(weaknesses.join(" "))}</p>` : ""}
    </article>
  `;
}

function cleanFeature(value) {
  return String(value)
    .replace(/!\[[^\]]*]\([^)]+\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^#+\s*/, "")
    .replace(/^[>*+\-]\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\\+/g, " ")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/\b(skip to main content|download pdf copy|view supplier profile|request quote|linkedin|facebook|reddit|x)\b/gi, "")
    .replace(/\[[^\]]+\]\([^)]+\)/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function renderSources(provenance) {
  const facts = provenance.source_facts || [];
  const assumptions = provenance.estimated_assumptions || [];
  const factHtml = facts.map((fact) => {
    const subject = fact.subject || "Source";
    const factBag = fact.facts || {};
    const evidence = cleanEvidence((fact.evidence || [])[0] || "");
    const features = (factBag.features || []).filter(Boolean).slice(0, 3);
    const url = factBag.source_url || factBag.pricing_url || "";
    const sourceQuality = factBag.source_quality || {};
    return `
      <article class="source-card source-card-fact">
        <h4>${escapeHtml(subject)}</h4>
        <div class="evidence-meta">
          <span class="evidence-label evidence-label-good">Primary fact</span>
          ${factBag.price_source_type === "extracted" && typeof factBag.price_monthly === "number" ? renderBadge(monthlyPrice(factBag.price_monthly), "tone-good") : ""}
          ${factBag.price_source_type ? renderBadge(factBag.price_source_type === "extracted" ? "Verified price" : "Modeled estimate", factBag.price_source_type === "extracted" ? "tone-good" : "tone-warn") : ""}
          ${renderPricingVisibilityBadge(factBag.pricing_visibility)}
          ${sourceQuality.label ? renderBadge(`Evidence ${sourceQuality.label}`, toneClass("quality", sourceQuality.label)) : ""}
          ${factBag.price_source_type !== "extracted" && typeof factBag.price_monthly === "number" ? renderBadge(`~${monthlyPrice(factBag.price_monthly)} est.`, "tone-warn") : ""}
        </div>
        ${url ? renderSourceLink(url) : ""}
        ${features.length ? `<div class="feature-row">${features.map((item) => `<span class="tag">${escapeHtml(cleanFeature(item))}</span>`).join("")}</div>` : ""}
        ${evidence ? `<p class="evidence-copy">${escapeHtml(evidence)}</p>` : ""}
      </article>
    `;
  }).join("");
  const assumptionHtml = assumptions.map((item) => `
    <article class="source-card source-card-assumption">
      <h4>${escapeHtml(readableLabel(item.type || "Assumption"))}</h4>
      <div class="evidence-meta"><span class="evidence-label evidence-label-warn">Modeled assumption</span></div>
      <p class="evidence-copy evidence-copy-warn">${escapeHtml(item.reasoning || "Estimated by Northstar.")}</p>
    </article>
  `).join("");
  if (!factHtml && !assumptionHtml) {
    return emptyHtml("No evidence", "The report did not include citations or assumptions.");
  }
  return `
    <section class="source-group">
      <div class="source-group-header">
        <span class="section-kicker">Direct evidence</span>
        <p>Facts from source pages, pricing pages, and extracted competitor records.</p>
      </div>
      <div class="source-group-grid">${factHtml || emptyHtml("No primary facts", "Northstar did not persist direct source facts for this run.")}</div>
    </section>
    <section class="source-group">
      <div class="source-group-header">
        <span class="section-kicker">Model assumptions</span>
        <p>These are Northstar inferences, modeled ranges, and copy synthesis. They are not direct citations.</p>
      </div>
      <div class="source-group-grid">${assumptionHtml || emptyHtml("No modeled assumptions", "This report did not emit modeled assumptions.")}</div>
    </section>
  `;
}

function cleanEvidence(value) {
  const normalized = cleanFeature(value)
    .replace(/^loading\.\.\.\s*/i, "")
    .replace(/\b(read report|sponsored by|reviewed by)\b/gi, "")
    .replace(/\s+/g, " ")
    .trim();
  const fragments = normalized
    .split(/(?<=[.!?])\s+/)
    .filter((part) => part.length > 24 && !/^\W*$/.test(part));
  return (fragments[0] || normalized).slice(0, 220);
}

function readableLabel(value) {
  return String(value)
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function domainLabel(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

function sourceLabel(url) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, "");
    const parts = parsed.pathname.split("/").filter(Boolean).slice(0, 3).map(decodeURIComponent);
    if (host === "github.com" && parts.length >= 2) {
      return `github.com/${parts[0]}/${parts[1]}`;
    }
    if (!parts.length) {
      return host;
    }
    const path = parts.join("/");
    return `${host}/${path}`.slice(0, 72);
  } catch {
    return url;
  }
}

function renderSourceLink(url) {
  const label = sourceLabel(url);
  return `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noreferrer" title="${escapeHtml(url)}">${escapeHtml(label)}</a>`;
}

function renderLanding(blueprint) {
  const hooks = blueprint.value_hooks || [];
  const objections = blueprint.objection_handling_copy || [];
  landingPreview.innerHTML = `
    <h3>${escapeHtml(blueprint.hero_title || "Run research to generate the first-page offer.")}</h3>
    <p>${escapeHtml(blueprint.hero_subheader || "The strongest differentiation angle will appear here.")}</p>
  `;
  hookList.innerHTML = [...hooks, ...objections]
    .map((item, index) => `
      <article class="hook-card">
        <span class="tag">${index < hooks.length ? "Hook" : "Objection"}</span>
        <p style="margin: 10px 0 0; color: var(--ink)">${escapeHtml(item)}</p>
      </article>
    `).join("") || emptyHtml("No hooks yet", "Run research to build the launch narrative.");
}

function renderMarketDoc(markdown) {
  if (!markdown) {
    marketDoc.innerHTML = emptyHtml("No market document", "Run research to generate the markdown artifact.");
    return;
  }
  marketDoc.innerHTML = markdownToHtml(markdown);
}

function markdownToHtml(markdown) {
  const lines = String(markdown).split("\n");
  let html = "";
  let inCode = false;
  let inList = false;
  let inOrderedList = false;
  let codeBuffer = [];
  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inCode) {
        html += `<pre class="doc-code"><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
        codeBuffer = [];
        inCode = false;
      } else {
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }
    if (!line.trim()) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (inOrderedList) {
        html += "</ol>";
        inOrderedList = false;
      }
      continue;
    }
    if (line.startsWith("# ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (inOrderedList) {
        html += "</ol>";
        inOrderedList = false;
      }
      html += `<h2>${escapeHtml(line.slice(2))}</h2>`;
      continue;
    }
    if (line.startsWith("## ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (inOrderedList) {
        html += "</ol>";
        inOrderedList = false;
      }
      html += `<h3>${escapeHtml(line.slice(3))}</h3>`;
      continue;
    }
    if (line.startsWith("### ")) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (inOrderedList) {
        html += "</ol>";
        inOrderedList = false;
      }
      html += `<h4>${escapeHtml(line.slice(4))}</h4>`;
      continue;
    }
    if (line.startsWith("- ")) {
      if (inOrderedList) {
        html += "</ol>";
        inOrderedList = false;
      }
      if (!inList) {
        html += "<ul>";
        inList = true;
      }
      html += `<li>${formatInline(line.slice(2))}</li>`;
      continue;
    }
    if (/^\d+\.\s/.test(line)) {
      if (inList) {
        html += "</ul>";
        inList = false;
      }
      if (!inOrderedList) {
        html += "<ol>";
        inOrderedList = true;
      }
      html += `<li>${formatInline(line.replace(/^\d+\.\s/, ""))}</li>`;
      continue;
    }
    if (inList) {
      html += "</ul>";
      inList = false;
    }
    if (inOrderedList) {
      html += "</ol>";
      inOrderedList = false;
    }
    html += `<p>${formatInline(line)}</p>`;
  }
  if (inList) html += "</ul>";
  if (inOrderedList) html += "</ol>";
  if (inCode) html += `<pre class="doc-code"><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
  return html;
}

function formatInline(text) {
  return escapeHtml(String(text)).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderConversation(kind, history, target) {
  if (!history.length) {
    target.innerHTML = emptyHtml("No session yet", "Start the simulation to build a persistent conversation.");
    return;
  }
  target.innerHTML = history.map((turn) => renderTurn(kind, turn)).join("");
  target.scrollTop = target.scrollHeight;
}

function renderTurn(kind, turn) {
  const bubbleClass = turn.role === "user" ? "chat-bubble user" : "chat-bubble assistant";
  const payload = turn.payload || {};
  return `
    <article class="${bubbleClass}">
      <div class="chat-meta">${turn.role === "user" ? "You" : kind === "board" ? "Advisory Board" : "War Room"}</div>
      <p>${escapeHtml(turn.content || "")}</p>
      ${turn.role === "assistant" && payload.generator ? `<div class="generator-line">${escapeHtml(payload.generator)}</div>` : ""}
      ${turn.role === "assistant" ? renderSimulationPayload(kind, payload) : ""}
    </article>
  `;
}

function renderSimulationPayload(kind, payload) {
  if (kind === "board") {
    const scores = payload.fit_scores || {};
    const responses = payload.responses || [];
    return `
      <div class="fit-grid">
        ${Object.entries(scores).map(([key, value]) => `<div class="fit-tile"><span>${escapeHtml(readableLabel(key))}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
      </div>
      <div class="response-stack">
        ${responses.map((item) => `
          <div class="chat-card">
            <strong>${escapeHtml(item.persona)}</strong>
            <span class="tag">${escapeHtml(item.buying_decision)}</span>
            <p>${escapeHtml(item.quote || "")}</p>
            <p class="muted-line">Friction: ${escapeHtml((item.friction_points || []).join(" "))}</p>
          </div>
        `).join("")}
      </div>
    `;
  }
  const riskMatrix = payload.risk_matrix || [];
  const responses = payload.responses || [];
  return `
    <div class="risk-grid">
      ${riskMatrix.map((item) => `
        <div class="risk-card risk-${String(item.severity || "").toLowerCase()}">
          <span>${escapeHtml(item.title)}</span>
          <strong>${escapeHtml(item.severity)}</strong>
          <p>Likelihood ${escapeHtml(item.likelihood)}/5 · Impact ${escapeHtml(item.impact)}/5</p>
          <p class="muted-line">${escapeHtml(item.counter_move)}</p>
        </div>
      `).join("")}
    </div>
    <div class="response-stack">
      ${responses.map((item) => `
        <div class="chat-card">
          <strong>${escapeHtml(item.competitor)}</strong>
          <span class="tag">${escapeHtml(item.defensive_risk)}</span>
          <p>${escapeHtml(item.pricing_reaction)}</p>
          <p class="muted-line">${escapeHtml(item.feature_reaction)}</p>
        </div>
      `).join("")}
    </div>
  `;
}

async function postJson(url, payload) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    throw new Error(await apiErrorMessage(resp));
  }
  return resp.json();
}

async function startSimulation(kind) {
  if (!isResearchReady()) return;
  const promptField = document.getElementById(kind === "board" ? "boardPrompt" : "warPrompt");
  const target = kind === "board" ? boardResult : warResult;
  const button = kind === "board" ? boardRunButton : warRunButton;
  target.innerHTML = loadingHtml("Starting session", "Northstar is opening a persistent simulation session.");
  button.disabled = true;
  try {
    const data = await postJson(`/api/sessions/${kind === "board" ? "board" : "war-room"}`, {
      report: latestResult.report,
      prompt: promptField.value,
      market_markdown_path: latestResult.market_markdown_path,
    });
    if (kind === "board") {
      boardSessionId = data.session_id;
      boardHistory = data.history || [];
      if (data.updated_report && latestResult) {
        latestResult.report = data.updated_report;
        renderLanding(latestResult.report.landing_page_blueprint || {});
        landingResult.textContent = JSON.stringify(latestResult.report.landing_page_blueprint || {}, null, 2);
      }
      if (data.updated_market_markdown && latestResult) {
        latestResult.market_markdown = data.updated_market_markdown;
        renderMarketDoc(latestResult.market_markdown);
      }
      renderConversation("board", boardHistory, boardResult);
    } else {
      warSessionId = data.session_id;
      warHistory = data.history || [];
      if (data.updated_report && latestResult) {
        latestResult.report = data.updated_report;
        renderLanding(latestResult.report.landing_page_blueprint || {});
        landingResult.textContent = JSON.stringify(latestResult.report.landing_page_blueprint || {}, null, 2);
      }
      if (data.updated_market_markdown && latestResult) {
        latestResult.market_markdown = data.updated_market_markdown;
        renderMarketDoc(latestResult.market_markdown);
      }
      renderConversation("war", warHistory, warResult);
    }
  } finally {
    button.disabled = false;
    updateDependentActions();
  }
}

async function continueSimulation(kind) {
  const promptField = document.getElementById(kind === "board" ? "boardPrompt" : "warPrompt");
  const target = kind === "board" ? boardResult : warResult;
  const button = kind === "board" ? boardRunButton : warRunButton;
  const sessionId = kind === "board" ? boardSessionId : warSessionId;
  target.insertAdjacentHTML("beforeend", `<article class="chat-bubble system"><div class="chat-meta">Northstar</div><p>Processing follow-up: ${escapeHtml(promptField.value)}</p></article>`);
  button.disabled = true;
  try {
    const basePath = `/api/sessions/${kind === "board" ? "board" : "war-room"}/${sessionId}`;
    const resp = await fetch(`${basePath}/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: promptField.value }),
    });
    try {
      await consumeSSE(resp, (event) => {
        if (event.type === "report_update" && latestResult) {
          latestResult.report = event.payload || latestResult.report;
          renderLanding(latestResult.report.landing_page_blueprint || {});
          landingResult.textContent = JSON.stringify(latestResult.report.landing_page_blueprint || {}, null, 2);
        }
      if (event.type === "artifact_update" && latestResult) {
        latestResult.market_markdown = event.payload?.market_markdown || latestResult.market_markdown;
        latestResult.market_markdown_path = event.payload?.market_markdown_path || latestResult.market_markdown_path;
        syncArtifactActions(latestResult.market_markdown_path);
        renderMarketDoc(latestResult.market_markdown || "");
      }
        if (event.type === "history") {
          if (kind === "board") {
            boardHistory = event.payload || [];
            renderConversation("board", boardHistory, boardResult);
          } else {
            warHistory = event.payload || [];
            renderConversation("war", warHistory, warResult);
          }
        }
      });
    } catch (streamError) {
      console.warn("Streaming follow-up failed; retrying with JSON fallback.", streamError);
      const data = await postJson(basePath, { message: promptField.value });
      applySimulationUpdate(kind, data);
    }
  } finally {
    button.disabled = false;
    updateDependentActions();
  }
}

function applySimulationUpdate(kind, data) {
  if (data.updated_report && latestResult) {
    latestResult.report = data.updated_report;
    renderLanding(latestResult.report.landing_page_blueprint || {});
    landingResult.textContent = JSON.stringify(latestResult.report.landing_page_blueprint || {}, null, 2);
  }
  if (data.updated_market_markdown && latestResult) {
    latestResult.market_markdown = data.updated_market_markdown;
    latestResult.market_markdown_path = data.market_markdown_path || latestResult.market_markdown_path;
    syncArtifactActions(latestResult.market_markdown_path);
    renderMarketDoc(latestResult.market_markdown || "");
  }
  if (kind === "board") {
    boardHistory = data.history || [];
    renderConversation("board", boardHistory, boardResult);
  } else {
    warHistory = data.history || [];
    renderConversation("war", warHistory, warResult);
  }
}

document.getElementById("run").addEventListener("click", async () => {
  const problems = validateBrief();
  if (problems.length) {
    showFormError(problems.join(" "));
    return;
  }
  showFormError("");
  resetRunUi();
  try {
    const resp = await fetch("/api/run/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getPayload()),
    });
    if (!resp.ok) {
      throw new Error(await apiErrorMessage(resp));
    }
    await consumeSSE(resp, (event) => {
      if (event.type === "trace") {
        addTraceLine(event.message, event.message.startsWith("ERROR:"));
      } else if (event.type === "result") {
        renderReport(event.payload);
      } else if (event.type === "error") {
        failRunUi(event.message);
      }
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    failRunUi(message);
  } finally {
    finishRunUi();
  }
});

document.getElementById("boardRun").addEventListener("click", async () => {
  try {
    if (!boardSessionId) {
      await startSimulation("board");
    } else {
      await continueSimulation("board");
    }
  } catch (error) {
    boardResult.innerHTML = emptyHtml("Board session failed", error instanceof Error ? error.message : String(error));
  }
});

document.getElementById("warRun").addEventListener("click", async () => {
  try {
    if (!warSessionId) {
      await startSimulation("war");
    } else {
      await continueSimulation("war");
    }
  } catch (error) {
    warResult.innerHTML = emptyHtml("War room failed", error instanceof Error ? error.message : String(error));
  }
});

updateDependentActions();

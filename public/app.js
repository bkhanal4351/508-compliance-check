const form = document.querySelector("#scan-form");
const jobsEl = document.querySelector("#jobs");
const formMessage = document.querySelector("#form-message");
const refreshButton = document.querySelector("#refresh");

let pollTimer;

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formMessage.textContent = "Starting scan...";
  const data = new FormData(form);
  const payload = {
    url: data.get("url"),
    filesText: data.get("filesText"),
    maxPages: Number(data.get("maxPages")),
    maxDepth: Number(data.get("maxDepth")),
    concurrency: Number(data.get("concurrency")),
    timeoutMs: Number(data.get("timeoutMs")),
    outName: data.get("outName"),
    sameOrigin: data.has("sameOrigin"),
    sameHost: data.has("sameHost"),
    downloadDocuments: data.has("downloadDocuments"),
    includeScreenshots: data.has("includeScreenshots"),
    verbose: data.has("verbose")
  };

  const response = await fetch("/api/scans", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const result = await response.json();
  if (!response.ok) {
    formMessage.textContent = result.error || "Could not start scan.";
    return;
  }
  formMessage.textContent = `Scan ${result.id} started.`;
  form.reset();
  form.maxPages.value = 5;
  form.maxDepth.value = 2;
  form.concurrency.value = 2;
  form.timeoutMs.value = 60000;
  form.sameOrigin.checked = true;
  form.sameHost.checked = true;
  form.downloadDocuments.checked = true;
  await loadJobs();
  startPolling();
});

refreshButton.addEventListener("click", loadJobs);

async function loadJobs() {
  const response = await fetch("/api/jobs");
  const jobs = await response.json();
  jobsEl.innerHTML = jobs.length ? jobs.map(renderJob).join("") : "<p>No UI scans have been started yet.</p>";
  if (jobs.some((job) => job.status === "running" || job.status === "queued")) startPolling();
}

function startPolling() {
  clearInterval(pollTimer);
  pollTimer = setInterval(loadJobs, 2500);
}

function renderJob(job) {
  const summary = job.summary
    ? `<div class="summary">
        <span>${job.summary.assets} assets</span>
        <span>${job.summary.findings} findings</span>
        <span>${job.summary.automatedIssues} automated</span>
        <span>${job.summary.manualReviewItems} manual review</span>
      </div>`
    : "";
  const links = job.status === "completed"
    ? `<div class="links">
        <a href="${job.reportUrl}">HTML report</a>
        <a href="${job.summaryUrl}">Summary JSON</a>
        <a href="${job.csvUrl}">Findings CSV</a>
        <a href="${job.manualReviewUrl}">Manual review</a>
      </div>`
    : "";
  return `<article class="job ${escapeHtml(job.status)}">
    <h3>${escapeHtml(job.target)}</h3>
    <div class="meta">
      <span class="badge">${escapeHtml(job.status)}</span>
      <span>Created ${escapeHtml(new Date(job.createdAt).toLocaleString())}</span>
      <span><code>${escapeHtml(job.outDir)}</code></span>
    </div>
    ${summary}
    ${links}
    ${job.error ? `<p class="error">${escapeHtml(job.error)}</p>` : ""}
    <pre>${escapeHtml((job.messages || []).join("\\n"))}</pre>
  </article>`;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  })[char]);
}

loadJobs();

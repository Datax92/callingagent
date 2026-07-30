(function () {
  const state = {
    direction: "inbound",
    skip: { inbound: 0, outbound: 0 },
    hasMore: { inbound: true, outbound: true },
    pendingNumbers: [], // chips waiting to be called
    searchTerm: { inbound: "", outbound: "" },
  };

  const grids = {
    inbound: document.getElementById("grid-inbound"),
    outbound: document.getElementById("grid-outbound"),
  };
  const views = {
    inbound: document.getElementById("view-inbound"),
    outbound: document.getElementById("view-outbound"),
  };
  const emptyStates = {
    inbound: document.getElementById("empty-inbound"),
    outbound: document.getElementById("empty-outbound"),
  };
  const searchInputs = {
    inbound: document.getElementById("search-inbound"),
    outbound: document.getElementById("search-outbound"),
  };
  const tabs = document.querySelectorAll(".navtab");

  const dialInput = document.getElementById("dial-input");
  const dialAddButton = document.getElementById("dial-add-button");
  const dialChips = document.getElementById("dial-chips");
  const dialStartButton = document.getElementById("dial-start-button");
  const dialCount = document.getElementById("dial-count");
  const dialCountPlural = document.getElementById("dial-count-plural");
  const dialStatus = document.getElementById("dial-status");

  const modalBackdrop = document.getElementById("call-modal-backdrop");
  const modalBody = document.getElementById("call-modal-body");
  const modalClose = document.getElementById("call-modal-close");

  // ------------------------------------------------------------- Tabs
  function switchTab(direction) {
    state.direction = direction;
    tabs.forEach((t) =>
      t.classList.toggle("active", t.dataset.tab === direction),
    );
    Object.keys(views).forEach((k) =>
      views[k].classList.toggle("active", k === direction),
    );
    if (direction === "outbound" && grids.outbound.dataset.loaded !== "true") {
      loadDeals("outbound", 0, false);
    }
  }
  tabs.forEach((t) =>
    t.addEventListener("click", () => switchTab(t.dataset.tab)),
  );

  // ------------------------------------------------------- Deal grids
  async function loadDeals(direction, skip, append) {
    try {
      const res = await fetch(
        `/api/deals?direction=${direction}&skip=${skip}&limit=50`,
      );
      const data = await res.json();
      const grid = grids[direction];
      if (append) {
        grid.insertAdjacentHTML("beforeend", data.html);
      } else {
        grid.innerHTML = data.html;
      }
      grid.dataset.loaded = "true";
      state.skip[direction] = data.skip;
      state.hasMore[direction] = data.has_more;
      applySearch(direction);
    } catch (e) {
      console.error("Failed to load calls:", e);
    }
  }

  // ---------------------------------------------------- Search / filter
  function applySearch(direction) {
    const term = state.searchTerm[direction].trim().toLowerCase();
    const grid = grids[direction];
    const rows = grid.querySelectorAll(".row");
    let visibleCount = 0;
    rows.forEach((row) => {
      const matches = !term || (row.dataset.search || "").includes(term);
      row.hidden = !matches;
      if (matches) visibleCount++;
    });
    const emptyEl = emptyStates[direction];
    if (emptyEl) {
      emptyEl.hidden = !(term && rows.length > 0 && visibleCount === 0);
    }
  }

  function setupSearch(direction) {
    const input = searchInputs[direction];
    if (!input) return;
    input.addEventListener("input", () => {
      state.searchTerm[direction] = input.value;
      applySearch(direction);
    });
  }
  setupSearch("inbound");
  setupSearch("outbound");

  function setupInfiniteScroll(direction) {
    const grid = grids[direction];
    const sentinel = document.createElement("div");
    sentinel.className = "load-more-sentinel";
    grid.parentElement.appendChild(sentinel);
    new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && state.hasMore[direction]) {
          loadDeals(direction, state.skip[direction], true);
        }
      },
      { threshold: 0.5 },
    ).observe(sentinel);
  }
  setupInfiniteScroll("inbound");
  setupInfiniteScroll("outbound");
  applySearch("inbound"); // inbound rows are already server-rendered on page load

  // ------------------------------------------------- Multi-number dial
  function renderChips() {
    dialChips.innerHTML = state.pendingNumbers
      .map(
        (num, i) => `
            <span class="chip">
                <span class="mono">${num}</span>
                <button type="button" class="chip-remove" data-index="${i}" aria-label="Remove ${num}">&times;</button>
            </span>
        `,
      )
      .join("");
    const count = state.pendingNumbers.length;
    dialCount.textContent = count;
    dialCountPlural.style.display = count === 1 ? "none" : "inline";
    dialStartButton.disabled = count === 0;
  }

  dialChips.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip-remove");
    if (!btn) return;
    state.pendingNumbers.splice(Number(btn.dataset.index), 1);
    renderChips();
  });

  function addNumbersFromText(raw) {
    // Splits on commas, whitespace, or new lines so pasting a whole list works.
    const parts = raw
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    let added = 0;
    parts.forEach((p) => {
      if (!state.pendingNumbers.includes(p)) {
        state.pendingNumbers.push(p);
        added++;
      }
    });
    if (added > 0) renderChips();
    return added;
  }

  dialAddButton.addEventListener("click", () => {
    if (addNumbersFromText(dialInput.value)) {
      dialInput.value = "";
    }
    dialInput.focus();
  });

  dialInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      if (addNumbersFromText(dialInput.value)) dialInput.value = "";
    }
  });

  dialInput.addEventListener("paste", (e) => {
    const text = (e.clipboardData || window.clipboardData).getData("text");
    if (text && /[\s,]/.test(text)) {
      e.preventDefault();
      if (addNumbersFromText(text)) dialInput.value = "";
    }
  });

  function renderBulkResults(results) {
    const rows = results
      .map((r) => {
        const ok = r.status === "dialing";
        const icon = ok
          ? "✅"
          : r.status === "invalid" || r.status === "skipped"
            ? "⚠️"
            : "❌";
        const note = ok
          ? "Calling now"
          : r.error || "Could not start this call.";
        return `
                <div class="bulk-result-item ${ok ? "ok" : "bad"}">
                    <span class="bulk-result-icon" aria-hidden="true">${icon}</span>
                    <span class="bulk-result-number mono">${r.phone_number}</span>
                    <span class="bulk-result-note">— ${note}</span>
                </div>`;
      })
      .join("");
    return `<div class="bulk-results">${rows}</div>`;
  }

  dialStartButton.addEventListener("click", async () => {
    if (state.pendingNumbers.length === 0) return;
    dialStartButton.disabled = true;
    dialStatus.className = "dial-status";
    dialStatus.textContent = "Starting calls...";
    try {
      const res = await fetch("/api/outbound-calls/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_numbers: state.pendingNumbers }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Something went wrong.");

      dialStatus.innerHTML =
        `<strong>${data.started} of ${data.requested}</strong> call${data.requested === 1 ? "" : "s"} started.` +
        renderBulkResults(data.results);
      state.pendingNumbers = [];
      renderChips();
      loadDeals("outbound", 0, false);
    } catch (err) {
      dialStatus.textContent = err.message;
    } finally {
      dialStartButton.disabled = state.pendingNumbers.length === 0;
    }
  });

  renderChips();

  // ---------------------------------------------------------- Modal
  function fieldRow(label, value) {
    if (!value) return "";
    return `<div><dt>${label}</dt><dd>${value}</dd></div>`;
  }

  function isUrdu(text) {
    return /[\u0600-\u06FF]/.test(text || "");
  }

  async function openModal(callId) {
    modalBackdrop.classList.add("visible");
    modalBody.innerHTML = '<div class="modal-loading">Loading...</div>';
    try {
      const res = await fetch(`/api/call/${callId}`);
      if (!res.ok) throw new Error("Could not load this call.");
      const doc = await res.json();
      renderModal(doc);
    } catch (e) {
      modalBody.innerHTML = `<div class="modal-error">${e.message}</div>`;
    }
  }

  // Inside renderModal function in static/js/dashboard.js
function renderModal(doc) {
    const direction = doc.call_direction === "outbound" ? "Outbound" : "Inbound";
    
    // Strip whitespace and enforce a strict fallback (also catches the
    // "<local-participant>" placeholder used in local test rooms).
    const rawCaller = (doc.caller_number || "").trim();
    const cleanCaller = rawCaller && !rawCaller.toLowerCase().includes("local-participant") ? rawCaller : "Unknown Number";
    
    const summary = doc.transcript_summary || doc.notes || "کوئی خلاصہ دستیاب نہیں ہے۔";
    const summaryClass = isUrdu(summary) ? "modal-summary urdu-text" : "modal-summary";
    const summaryDir = isUrdu(summary) ? 'dir="rtl" lang="ur"' : 'dir="ltr"';
    
    const recordingHtml = doc.recording_url
      ? `
        <div class="recording-block">
            <h4>Call Recording</h4>
            <audio controls preload="none">
                <source src="${doc.recording_url}" type="audio/wav">
            </audio>
        </div>`
      : "";

    const isReviewed = doc.status === "reviewed";
    const actionHtml =
      doc.status === "dialing" || doc.status === "failed"
        ? ""
        : `
        <div class="modal-actions">
            <button type="button" class="${isReviewed ? "unreview" : ""}" id="toggle-status-btn" data-id="${doc._id}" data-next="${isReviewed ? "new" : "reviewed"}">
                ${isReviewed ? "Mark as Not Reviewed" : "Mark as Reviewed"}
            </button>
        </div>`;

    modalBody.innerHTML = `
        <div class="modal-head">
            <h2 class="modal-title">${cleanCaller}</h2>
        </div>
        <div class="detail-grid">
            ${fieldRow("Call Direction", direction)}
            ${fieldRow("Time", doc.created_at_display)}
            ${fieldRow("Business Name", doc.business_name || "N/A")}
            ${fieldRow("Call Duration", doc.call_duration ? Math.round(doc.call_duration) + "s" : "N/A")}
        </div>
        <div style="margin-top: 15px;">
            <h4 style="margin-bottom: 5px;">AI Urdu Call Summary (اردو خلاصہ):</h4>
            <p class="${summaryClass}" ${summaryDir} style="background: #f8f9fa; padding: 12px; border-radius: 6px; border-right: 4px solid #007bff;">${summary}</p>
        </div>
        ${recordingHtml}
        ${actionHtml}
    `;

    document
      .getElementById("toggle-status-btn")
      ?.addEventListener("click", async (e) => {
        const btn = e.currentTarget;
        const id = btn.dataset.id;
        const next = btn.dataset.next;
        btn.disabled = true;
        try {
          await fetch(`/api/call/${id}/status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: next }),
          });
          closeModal();
          loadDeals(state.direction, 0, false);
        } catch (err) {
          btn.disabled = false;
        }
      });
  }

  function closeModal() {
    modalBackdrop.classList.remove("visible");
    modalBody.innerHTML = "";
  }

  modalClose.addEventListener("click", closeModal);
  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  document.body.addEventListener("click", (e) => {
    const row = e.target.closest(".row");
    if (row) openModal(row.dataset.callId);
  });
  document.body.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.classList.contains("row"))
      openModal(e.target.dataset.callId);
  });

  // ------------------------------------------------------------- SSE
  function refreshCurrent() {
    loadDeals(state.direction, 0, false);
  }

  function setupSSE() {
    let fallbackTimer = null;
    const eventSource = new EventSource("/events/deals");

    eventSource.addEventListener("new_deal", () => refreshCurrent());

    eventSource.onopen = () => {
      if (fallbackTimer) {
        clearInterval(fallbackTimer);
        fallbackTimer = null;
      }
    };

    eventSource.onerror = () => {
      if (fallbackTimer) return;
      fallbackTimer = setInterval(refreshCurrent, 10000);
    };
  }
  setupSSE();
})();
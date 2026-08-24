// ============================================================
// Verify page logic
//
// Two ways to verify a medicine before dispensing it:
//   1. Guided Verification - search, tick the item, locate it in the
//      cabinet, then scan the barcode to confirm it's the right one.
//   2. Quick Scan - just scan items one after another with a barcode
//      scanner, no searching needed.
//
// Both end the same way: a list of verified items at the bottom,
// with a Submit button (saves to the database) and a Clear All
// button (throws the list away without saving anything).
// ============================================================

// -------- switching between the two tabs --------

function showTab(tab) {
    const showingGuided = tab === "guided";
    document.getElementById("guidedSection").style.display = showingGuided ? "block" : "none";
    document.getElementById("quickSection").style.display = showingGuided ? "none" : "block";
    document.getElementById("tabGuidedBtn").classList.toggle("active", showingGuided);
    document.getElementById("tabQuickBtn").classList.toggle("active", !showingGuided);
}


// ============================================================
// GUIDED VERIFICATION
// ============================================================

// medicines the staff has ticked in the search results (step 1)
// key = medicine_id, value = { status: "idle" or "lit", data: medicine object }
let selected = {};

// medicines that have been scanned and matched against "selected" (step 3)
// key = medicine_id, value = { qty: number, data: medicine object }
let guidedReady = {};


// ---- step 1: search and select ----

async function searchMedicines(searchText) {
    const response = await fetch("/api/medicines/search?q=" + encodeURIComponent(searchText));
    const data = await response.json();
    renderMedList(data.results, data.total);
}

function renderMedList(medicines, totalMatches) {
    const listEl = document.getElementById("medList");
    listEl.innerHTML = "";
    document.getElementById("noResults").style.display = medicines.length ? "none" : "block";

    // the search only returns a handful of results at a time, so let
    // the staff know if there are more they haven't seen yet
    const moreHint = document.getElementById("moreResultsHint");
    if (totalMatches > medicines.length) {
        moreHint.style.display = "block";
        moreHint.textContent = `Showing ${medicines.length} of ${totalMatches} matches. Refine your search to see more.`;
    } else {
        moreHint.style.display = "none";
    }

    for (const med of medicines) {
        const isChecked = Boolean(selected[med.medicine_id]);

        const row = document.createElement("label");
        row.className = isChecked ? "med-row checked" : "med-row";
        row.innerHTML = `
            <input type="checkbox" ${isChecked ? "checked" : ""} data-medicine-id="${med.medicine_id}">
            <div>
                <strong>${med.name}</strong><br>
                <span class="muted">${med.dosage}</span>
            </div>
            <div class="med-loc">${med.location}<br>${med.total_qty} in stock</div>
        `;

        // storing the whole medicine object on the checkbox itself is easier
        // to read than trying to cram it into an onclick string
        const checkbox = row.querySelector("input");
        checkbox.addEventListener("change", () => toggleSelect(med));

        listEl.appendChild(row);
    }
}

function toggleSelect(medicine) {
    if (selected[medicine.medicine_id]) {
        delete selected[medicine.medicine_id];
    } else {
        selected[medicine.medicine_id] = { status: "idle", data: medicine };
    }
    searchMedicines(document.getElementById("searchInput").value);
    renderSelectedList();
}


// ---- step 2: locate in the cabinet ----

function renderSelectedList() {
    const medicineIds = Object.keys(selected);
    document.getElementById("noneSelected").style.display = medicineIds.length ? "none" : "block";

    const listEl = document.getElementById("selectedList");
    listEl.innerHTML = "";

    for (const id of medicineIds) {
        const item = selected[id];
        const isLit = item.status === "lit";

        const row = document.createElement("div");
        row.className = "list-row";
        row.innerHTML = `
            <div style="flex:1">
                <strong>${item.data.name} - ${item.data.dosage}</strong><br>
                <span class="muted">${item.data.location}</span>
            </div>
            <span class="pill ${isLit ? "pill-lit" : "pill-idle"}">${isLit ? "Light ON" : "Light off"}</span>
            <button class="btn-small">${isLit ? "Turn Off" : "Locate"}</button>
        `;

        row.querySelector("button").addEventListener("click", () => toggleLight(id));
        listEl.appendChild(row);
    }
}

// Sends an on/off request to the ESP so the correct LED lights up.
async function toggleLight(medicineId) {
    const item = selected[medicineId];
    const turningOn = item.status !== "lit";

    const response = await fetch("/api/locate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ medicine_id: medicineId, state: turningOn ? "on" : "off" })
    });
    const data = await response.json();

    if (data.success) {
        item.status = turningOn ? "lit" : "idle";
        renderSelectedList();
    }
}


// ---- step 3: scan to verify ----

async function guidedScan() {
    const input = document.getElementById("guidedBarcodeInput");
    const barcode = input.value.trim();
    if (!barcode) return;
    input.value = "";

    const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode })
    });
    const data = await response.json();
    const messageEl = document.getElementById("guidedMessage");

    if (!data.found) {
        messageEl.innerHTML = `<div class="result-box result-bad">No medicine matches this barcode: ${barcode}</div>`;
        return;
    }

    const medicine = data.medicine;

    // the scanned barcode has to match something the staff actually
    // ticked in step 1 - otherwise they may have grabbed the wrong item
    if (!selected[medicine.medicine_id]) {
        messageEl.innerHTML = `<div class="result-box result-bad">Mismatch: ${medicine.name} ${medicine.dosage} was scanned but is not on your selected list.</div>`;
        return;
    }

    // scanning the same item again just increases its quantity
    if (guidedReady[medicine.medicine_id]) {
        guidedReady[medicine.medicine_id].qty += 1;
    } else {
        guidedReady[medicine.medicine_id] = { qty: 1, data: medicine };
    }

    messageEl.innerHTML = `<div class="result-box result-ok">Verified: ${medicine.name} ${medicine.dosage}</div>`;
    renderGuidedReady();
    input.focus();
}

function renderGuidedReady() {
    renderReadyList(guidedReady, "guidedReadyList", "guidedReadyNone", "guidedSubmitBtn", "guidedClearBtn", adjustGuidedQty, removeGuidedItem);
}

function adjustGuidedQty(medicineId, change) {
    guidedReady[medicineId].qty = Math.max(1, guidedReady[medicineId].qty + change);
    renderGuidedReady();
}

function removeGuidedItem(medicineId) {
    delete guidedReady[medicineId];
    renderGuidedReady();
}

function clearGuided() {
    guidedReady = {};
    renderGuidedReady();
    document.getElementById("guidedMessage").innerHTML = "";
}

async function submitGuided() {
    await submitReadyList(guidedReady, () => {
        guidedReady = {};
        renderGuidedReady();
    });
}


// ============================================================
// QUICK SCAN
// ============================================================

// medicines scanned so far, waiting to be submitted
// key = medicine_id, value = { qty: number, data: medicine object }
let quickTally = {};

async function quickScan() {
    const input = document.getElementById("quickBarcodeInput");
    const barcode = input.value.trim();
    if (!barcode) return;
    input.value = "";

    const response = await fetch("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ barcode })
    });
    const data = await response.json();
    const messageEl = document.getElementById("quickMessage");

    if (!data.found) {
        messageEl.innerHTML = `<div class="result-box result-bad">No medicine matches barcode ${barcode}.</div>`;
        input.focus();
        return;
    }

    const medicine = data.medicine;

    // scanning the same item twice just adds up the quantity
    if (quickTally[medicine.medicine_id]) {
        quickTally[medicine.medicine_id].qty += 1;
    } else {
        quickTally[medicine.medicine_id] = { qty: 1, data: medicine };
    }

    messageEl.innerHTML = `<div class="result-box result-ok">Scanned: ${medicine.name} ${medicine.dosage}</div>`;
    renderQuickReady();
    input.focus();
}

function renderQuickReady() {
    renderReadyList(quickTally, "quickList", "quickNone", "quickSubmitBtn", "quickClearBtn", adjustQuickQty, removeQuickItem);
}

function adjustQuickQty(medicineId, change) {
    quickTally[medicineId].qty = Math.max(1, quickTally[medicineId].qty + change);
    renderQuickReady();
}

function removeQuickItem(medicineId) {
    delete quickTally[medicineId];
    renderQuickReady();
}

function clearQuick() {
    quickTally = {};
    renderQuickReady();
    document.getElementById("quickMessage").innerHTML = "";
}

async function submitQuick() {
    await submitReadyList(quickTally, () => {
        quickTally = {};
        renderQuickReady();
    });
}


// ============================================================
// Shared helpers - used by both Guided Verification and Quick Scan
// ============================================================

// Draws the "ready to submit" list: each row has +/- quantity buttons
// and a Remove button. Shows/hides the Submit and Clear All buttons
// depending on whether the list is empty.
function renderReadyList(tally, listElId, emptyMessageId, submitBtnId, clearBtnId, onAdjustQty, onRemove) {
    const medicineIds = Object.keys(tally);

    document.getElementById(emptyMessageId).style.display = medicineIds.length ? "none" : "block";
    document.getElementById(submitBtnId).style.display = medicineIds.length ? "inline-block" : "none";
    document.getElementById(clearBtnId).style.display = medicineIds.length ? "inline-block" : "none";

    const listEl = document.getElementById(listElId);
    listEl.innerHTML = "";

    for (const id of medicineIds) {
        const item = tally[id];

        const row = document.createElement("div");
        row.className = "list-row verified";
        row.innerHTML = `
            <div style="flex:1"><strong>${item.data.name} - ${item.data.dosage}</strong></div>
            <div class="qty-box">
                <button class="btn-small minus-btn">-</button>
                <span>${item.qty}</span>
                <button class="btn-small plus-btn">+</button>
            </div>
            <button class="btn-small btn-outline remove-btn">Remove</button>
        `;

        row.querySelector(".minus-btn").addEventListener("click", () => onAdjustQty(id, -1));
        row.querySelector(".plus-btn").addEventListener("click", () => onAdjustQty(id, 1));
        row.querySelector(".remove-btn").addEventListener("click", () => onRemove(id));

        listEl.appendChild(row);
    }
}

// Sends everything in the list to the server as one bulk dispense
// request, then runs onDone() (usually clears the list) once finished.
async function submitReadyList(tally, onDone) {
    const items = Object.keys(tally).map(id => ({
        medicine_id: id,
        quantity: tally[id].qty
    }));
    if (items.length === 0) return;

    const confirmed = confirm(`Submit ${items.length} item(s)? This will update the database.`);
    if (!confirmed) return;

    const response = await fetch("/api/bulk_dispense", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items })
    });
    const data = await response.json();

    const summaryLines = data.results.map(result => {
        const label = `${result.name || result.medicine_id} ${result.dosage || ""}`;
        const outcome = result.success ? "Updated" : `Failed - ${result.message}`;
        return `${label}: ${outcome}`;
    });
    alert(summaryLines.join("\n"));

    onDone();
}


// ============================================================
// Set everything up once the page loads
// ============================================================

document.getElementById("searchInput").addEventListener("input", e => searchMedicines(e.target.value));
document.getElementById("guidedBarcodeInput").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); guidedScan(); }
});
document.getElementById("quickBarcodeInput").addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); quickScan(); }
});

searchMedicines("");
renderSelectedList();
renderGuidedReady();
renderQuickReady();

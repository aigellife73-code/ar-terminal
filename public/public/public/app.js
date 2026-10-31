const screen = document.getElementById("terminal-screen");
const phoneInput = document.getElementById("phone-input");
const tabSelect = document.getElementById("tab-select");
const rangeSelect = document.getElementById("range-select");
const paySelect = document.getElementById("pay-select");

function addTerminalLine(text, type = "info") {
    const div = document.createElement("div");
    div.className = `line ${type}`;
    div.innerText = text;
    screen.appendChild(div);
    screen.scrollTop = screen.scrollHeight;
}

async function fetchLogs() {
    try {
        const res = await fetch("/api/logs");
        const data = await res.json();
        screen.innerHTML = "";
        data.logs.forEach(log => {
            let type = "info";
            if (log.includes("Error") || log.includes("closed")) type = "error";
            if (log.includes("active") || log.includes("started")) type = "success";
            addTerminalLine(log, type);
        });
    } catch (e) {}
}

document.getElementById("btn-start").addEventListener("click", async () => {
    const phone = phoneInput.value.trim();
    if (phone.length !== 10) {
        addTerminalLine("[VALIDATION] 10-digit number required.", "error");
        return;
    }

    addTerminalLine(`[CMD] START Requesting for ${phone}...`, "info");
    try {
        const res = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                phone: phone,
                tab: tabSelect.value,
                range_val: rangeSelect.value,
                payment_app: paySelect.value
            })
        });
        const data = await res.json();
        if (res.ok) {
            addTerminalLine(`[OK] Task started successfully.`, "success");
        } else {
            addTerminalLine(`[FAILED] ${data.detail || 'Error'}`, "error");
        }
    } catch (err) {
        addTerminalLine(`[NET_ERR] ${err.message}`, "error");
    }
});

document.getElementById("btn-stop").addEventListener("click", async () => {
    const phone = phoneInput.value.trim();
    if (!phone) {
        addTerminalLine("[VALIDATION] Phone number missing.", "error");
        return;
    }

    try {
        const res = await fetch(`/api/stop/${phone}`, { method: "POST" });
        const data = await res.json();
        addTerminalLine(`[STOP] Status: ${data.status}`, "info");
    } catch (err) {
        addTerminalLine(`[ERR] ${err.message}`, "error");
    }
});

document.getElementById("btn-clear").addEventListener("click", () => {
    screen.innerHTML = "";
});

setInterval(fetchLogs, 2500);

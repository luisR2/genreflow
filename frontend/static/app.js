(() => {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const browseButton = document.getElementById("browse-button");
  const clearButton = document.getElementById("clear-button");
  const analyzeButton = document.getElementById("analyze-button");
  const fileList = document.getElementById("file-list");
  const fileCounter = document.getElementById("file-counter");
  const statusEl = document.getElementById("status");
  const resultsPanel = document.getElementById("results-panel");
  const resultsBody = document.getElementById("results-body");
  const totalTime = document.getElementById("total-time");

  let files = [];

  const formatSeconds = (seconds) => `${seconds.toFixed(2)}s`;

  const setStatus = (text, level = "") => {
    statusEl.textContent = text;
    statusEl.className = `status ${level}`;
  };

  const renderList = () => {
    fileList.innerHTML = "";
    files.forEach((f, idx) => {
      const li = document.createElement("li");
      const name = document.createElement("div");
      name.textContent = f.name;

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${(f.size / 1024 / 1024).toFixed(2)} MB`;

      const remove = document.createElement("button");
      remove.className = "ghost";
      remove.type = "button";
      remove.textContent = "Remove";
      remove.onclick = () => {
        files.splice(idx, 1);
        renderList();
      };

      const left = document.createElement("div");
      left.appendChild(name);
      left.appendChild(meta);

      const right = document.createElement("div");
      right.appendChild(remove);

      li.appendChild(left);
      li.appendChild(right);
      fileList.appendChild(li);
    });

    fileCounter.textContent = files.length
      ? `${files.length} file${files.length > 1 ? "s" : ""} selected`
      : "No files selected";
  };

  const addFiles = (list) => {
    const accepted = [".wav", ".flac", ".mp3", ".aiff"];
    Array.from(list).forEach((file) => {
      if (accepted.some((ext) => file.name.toLowerCase().endsWith(ext))) {
        files.push(file);
      }
    });
    renderList();
  };

  // Mirrors MAX_FILE_SIZE_BYTES in backend/app/routes_file.py. Checked here only
  // to fail fast; the backend is the authority and enforces it again.
  const MAX_FILE_BYTES = 50 * 1024 * 1024;

  const addResultRow = ({ filename, bpm, analysisTime, error }) => {
    const row = document.createElement("tr");
    if (error) row.className = "row-error";

    const name = document.createElement("td");
    name.textContent = filename;

    const bpmCell = document.createElement("td");
    bpmCell.textContent = typeof bpm === "number" ? bpm.toFixed(1) : "–";

    const last = document.createElement("td");
    last.textContent = error ? error : formatSeconds(analysisTime);

    row.appendChild(name);
    row.appendChild(bpmCell);
    row.appendChild(last);
    resultsBody.appendChild(row);
  };

  const errorDetail = async (res) => {
    try {
      return (await res.json()).detail || "";
    } catch (_) {
      try {
        return await res.text();
      } catch (_) {
        return "";
      }
    }
  };

  const analyzeOne = async (file) => {
    const form = new FormData();
    form.append("file", file);

    const res = await fetch("/api/predict/file", { method: "POST", body: form });
    if (!res.ok) {
      const detail = await errorDetail(res);
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return res.json();
  };

  // Files are sent one request at a time rather than as a single batch. Each
  // result renders as it lands, and no single request has to carry the whole
  // selection -- which keeps every upload well inside the proxy's body-size and
  // response-timeout limits no matter how many files are queued.
  const sendFiles = async () => {
    if (!files.length) {
      setStatus("Add at least one audio file", "warn");
      return;
    }

    analyzeButton.disabled = true;
    clearButton.disabled = true;
    resultsBody.innerHTML = "";
    resultsPanel.classList.remove("hidden");
    totalTime.textContent = "Total: –";

    let elapsed = 0;
    let failures = 0;

    for (const [index, file] of files.entries()) {
      setStatus(`Analyzing ${index + 1} of ${files.length}: ${file.name}`);

      if (file.size > MAX_FILE_BYTES) {
        addResultRow({ filename: file.name, error: "Too large (max 50 MB)" });
        failures += 1;
        continue;
      }

      try {
        const item = await analyzeOne(file);
        elapsed += item.analysis_time || 0;
        addResultRow({
          filename: item.filename,
          bpm: item.bpm,
          analysisTime: item.analysis_time,
        });
        totalTime.textContent = `Total: ${formatSeconds(elapsed)}`;
      } catch (err) {
        addResultRow({ filename: file.name, error: err.message || "Failed" });
        failures += 1;
        console.error(file.name, err);
      }
    }

    const analyzed = files.length - failures;
    if (failures === 0) {
      setStatus("Done", "success");
    } else if (analyzed === 0) {
      setStatus(`All ${files.length} file${files.length > 1 ? "s" : ""} failed`, "error");
    } else {
      setStatus(`Done, ${failures} of ${files.length} failed`, "warn");
    }

    analyzeButton.disabled = false;
    clearButton.disabled = false;
  };

  // Events
  browseButton.addEventListener("click", () => fileInput.click());
  clearButton.addEventListener("click", () => {
    files = [];
    renderList();
    resultsPanel.classList.add("hidden");
    setStatus("");
  });
  analyzeButton.addEventListener("click", sendFiles);

  fileInput.addEventListener("change", (e) => addFiles(e.target.files));

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("active");
  });

  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("active"));

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("active");
    if (e.dataTransfer?.files) {
      addFiles(e.dataTransfer.files);
    }
  });
})();


// TODO: Add thinking icon when analysing songs

// TODO: Change the color of the results box
 
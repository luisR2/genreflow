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

  let apiBaseUrl = "";
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

  const fetchConfig = async () => {
    try {
      const res = await fetch("/config.json");
      const cfg = await res.json();
      apiBaseUrl = cfg.apiBaseUrl;
    } catch (err) {
      setStatus("Failed to load config", "error");
      console.error(err);
    }
  };

  const sendFiles = async () => {
    if (!files.length) {
      setStatus("Add at least one audio file", "warn");
      return;
    }

    setStatus("Analyzing...");
    analyzeButton.disabled = true;

    const form = new FormData();
    files.forEach((file) => form.append("files", file));

    try {
      const res = await fetch(`${apiBaseUrl}/predict/files`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "Request failed");
      }

      const data = await res.json();
      resultsBody.innerHTML = "";
      data.results.forEach((item) => {
        const row = document.createElement("tr");
        const name = document.createElement("td");
        name.textContent = item.filename;
        const bpm = document.createElement("td");
        bpm.textContent = item.bpm ? item.bpm.toFixed(1) : "–";
        const time = document.createElement("td");
        time.textContent = formatSeconds(item.analysis_time);
        row.appendChild(name);
        row.appendChild(bpm);
        row.appendChild(time);
        resultsBody.appendChild(row);
      });
      totalTime.textContent = `Total: ${formatSeconds(data.analysis_time)}`;
      resultsPanel.classList.remove("hidden");
      setStatus("Done", "success");
    } catch (err) {
      setStatus("Upload failed. Check backend availability.", "error");
      console.error(err);
    } finally {
      analyzeButton.disabled = false;
    }
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

  fetchConfig();
})();


// TODO: Add thinking icon when analysing songs

// TODO: Change the color of the results box
 
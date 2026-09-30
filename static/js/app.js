/**
 * StreamVault - Interactive YouTube Downloader Frontend Logic
 */

document.addEventListener("DOMContentLoaded", () => {
    // Determine API endpoint base (use current origin unless it's explicitly Live Server on 5500)
    const API_BASE = (window.location.port === "5500") ? "http://127.0.0.1:5002" : "";

    // DOM Elements
    const urlForm = document.getElementById("urlForm");
    const youtubeUrlInput = document.getElementById("youtubeUrl");
    const pasteBtn = document.getElementById("pasteBtn");
    const clearBtn = document.getElementById("clearBtn");
    const fetchBtn = document.getElementById("fetchBtn");
    const btnSpinner = fetchBtn.querySelector(".btn-spinner");
    const btnText = fetchBtn.querySelector(".btn-text");
    const btnArrow = fetchBtn.querySelector(".btn-arrow");

    // Preview Elements
    const previewSection = document.getElementById("previewSection");
    const videoThumb = document.getElementById("videoThumb");
    const videoDuration = document.getElementById("videoDuration");
    const videoTitle = document.getElementById("videoTitle");
    const videoAuthor = document.getElementById("videoAuthor");
    const videoViews = document.getElementById("videoViews");

    // Format & Quality Controls
    const tabMp4 = document.getElementById("tabMp4");
    const tabMp3 = document.getElementById("tabMp3");
    const mp4QualityGroup = document.getElementById("mp4QualityGroup");
    const mp3QualityGroup = document.getElementById("mp3QualityGroup");
    const videoQualityChips = document.getElementById("videoQualityChips");
    const audioQualityChips = document.getElementById("audioQualityChips");
    const startDownloadBtn = document.getElementById("startDownloadBtn");
    const downloadBtnText = document.getElementById("downloadBtnText");

    // Progress Elements
    const progressSection = document.getElementById("progressSection");
    const progressStatusText = document.getElementById("progressStatusText");
    const progressPercent = document.getElementById("progressPercent");
    const progressBarFill = document.getElementById("progressBarFill");
    const progressSpeed = document.getElementById("progressSpeed");
    const progressSize = document.getElementById("progressSize");
    const progressEta = document.getElementById("progressEta");
    const downloadCompletedArea = document.getElementById("downloadCompletedArea");
    const completedFilename = document.getElementById("completedFilename");
    const completedFilesize = document.getElementById("completedFilesize");
    const directSaveBtn = document.getElementById("directSaveBtn");
    const downloadErrorArea = document.getElementById("downloadErrorArea");
    const downloadErrorMsg = document.getElementById("downloadErrorMsg");

    // Reset buttons
    const resetBtn = document.getElementById("resetBtn");
    const completedResetBtn = document.getElementById("completedResetBtn");
    const errorResetBtn = document.getElementById("errorResetBtn");

    // State Variables
    let currentVideoData = null;
    let selectedFormat = "mp4";
    let selectedQuality = "1080p";
    let activePollInterval = null;

    // Reset App State
    function resetApp() {
        if (activePollInterval) {
            clearInterval(activePollInterval);
            activePollInterval = null;
        }
        currentVideoData = null;
        selectedFormat = "mp4";
        selectedQuality = "1080p";
        previewSection?.classList.add("hidden");
        progressSection?.classList.add("hidden");
        downloadCompletedArea?.classList.add("hidden");
        downloadErrorArea?.classList.add("hidden");
        youtubeUrlInput.value = "";
        clearBtn.classList.add("hidden");
        youtubeUrlInput.focus();
        startDownloadBtn.disabled = false;
        window.scrollTo({ top: 0, behavior: "smooth" });
        if (resetBtn) resetBtn.classList.remove("hidden");
        showToast("Ready for a new download!", "info");
    }

    // Wire up all reset buttons
    resetBtn?.addEventListener("click", resetApp);
    completedResetBtn?.addEventListener("click", resetApp);
    errorResetBtn?.addEventListener("click", resetApp);

    // Input handlers
    youtubeUrlInput.addEventListener("input", () => {
        if (youtubeUrlInput.value.trim().length > 0) {
            clearBtn.classList.remove("hidden");
        } else {
            clearBtn.classList.add("hidden");
        }
    });

    clearBtn.addEventListener("click", () => {
        youtubeUrlInput.value = "";
        clearBtn.classList.add("hidden");
        youtubeUrlInput.focus();
    });

    pasteBtn.addEventListener("click", async () => {
        try {
            const text = await navigator.clipboard.readText();
            if (text) {
                youtubeUrlInput.value = text.trim();
                clearBtn.classList.remove("hidden");
                showToast("Link pasted from clipboard!", "info");
                // Automatically analyze if it's a valid link
                if (text.includes("youtube.com") || text.includes("youtu.be")) {
                    analyzeUrl(text.trim());
                }
            }
        } catch (err) {
            showToast("Clipboard access denied. Please paste manually.", "error");
        }
    });

    urlForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const url = youtubeUrlInput.value.trim();
        if (url) {
            analyzeUrl(url);
        }
    });

    // Analyze URL function
    async function analyzeUrl(url) {
        setLoadingState(true);
        previewSection?.classList.add("hidden");
        progressSection?.classList.add("hidden");

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);

        try {
            const response = await fetch(`${API_BASE}/api/info`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error || "Could not fetch video information.");
            }

            currentVideoData = result;
            if (previewSection) {
                renderPreview(result);
            } else {
                // Auto download if UI was deleted
                startAutoDownload();
            }
            showToast("Video analyzed successfully!", "success");

        } catch (error) {
            clearTimeout(timeoutId);
            if (error.name === "AbortError") {
                showToast("Request timed out. Please check your internet or try another link.", "error");
            } else {
                showToast(error.message, "error");
            }
        } finally {
            setLoadingState(false);
        }
    }

    function setLoadingState(isLoading) {
        if (isLoading) {
            fetchBtn.disabled = true;
            btnSpinner.classList.remove("hidden");
            btnArrow.classList.add("hidden");
            btnText.textContent = "Submitting...";
        } else {
            fetchBtn.disabled = false;
            btnSpinner.classList.add("hidden");
            btnArrow.classList.remove("hidden");
            btnText.textContent = "Submit";
        }
    }

    // Render Preview
    function renderPreview(data) {
        if (videoThumb) videoThumb.src = data.thumbnail || "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600";
        if (videoDuration) videoDuration.textContent = data.duration;
        if (videoTitle) videoTitle.textContent = data.title;
        if (videoAuthor) videoAuthor.querySelector("span").textContent = data.uploader;
        if (videoViews) videoViews.querySelector("span").textContent = `${data.views} views`;

        // Update engine status indicator if reported
        if (data.ffmpeg_available !== undefined) {
            const statusPill = document.getElementById("statusPill");
            const statusLabel = document.getElementById("statusLabel");
            if (statusPill && statusLabel) {
                if (data.ffmpeg_available) {
                    statusPill.className = "status-pill status-active";
                    statusLabel.textContent = "FFmpeg Ready";
                } else {
                    statusPill.className = "status-pill status-warning";
                    statusLabel.textContent = "FFmpeg Not Found (Basic Mode)";
                }
            }
        }

        // Render available quality chips for video
        if (videoQualityChips && data.qualities && data.qualities.length > 0) {
            videoQualityChips.innerHTML = "";
            data.qualities.forEach((q, index) => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = `quality-chip ${index === 0 ? "active" : ""}`;
                button.setAttribute("data-quality", q);

                let label = "Standard";
                if (q.includes("2160") || q.includes("4K")) label = "4K Ultra HD";
                else if (q.includes("1440")) label = "2K Quad HD";
                else if (q.includes("1080")) label = "Full HD 1080p";
                else if (q.includes("720")) label = "High Definition";
                else if (q.includes("480")) label = "Standard Definition";
                else if (q.includes("360")) label = "Compact Size";

                button.innerHTML = `
                    <span class="chip-title">${q}</span>
                    <span class="chip-desc">${label}</span>
                `;

                button.addEventListener("click", () => {
                    videoQualityChips.querySelectorAll(".quality-chip").forEach(c => c.classList.remove("active"));
                    button.classList.add("active");
                    selectedQuality = q;
                    updateDownloadButtonLabel();
                });

                videoQualityChips.appendChild(button);
            });
            selectedQuality = data.qualities[0];
        } else if (data.qualities && data.qualities.length > 0) {
            // Default selection if UI is missing
            selectedQuality = data.qualities[0];
        }

        previewSection?.classList.remove("hidden");
        updateDownloadButtonLabel();

        // Scroll to preview smoothly
        previewSection?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    // Tab switching between MP4 and MP3
    tabMp4?.addEventListener("click", () => {
        tabMp4.classList.add("active");
        tabMp3?.classList.remove("active");
        mp4QualityGroup?.classList.remove("hidden");
        mp3QualityGroup?.classList.add("hidden");
        selectedFormat = "mp4";
        selectedQuality = currentVideoData && currentVideoData.qualities && currentVideoData.qualities.length > 0 ? currentVideoData.qualities[0] : "1080p";
        updateDownloadButtonLabel();
    });

    tabMp3?.addEventListener("click", () => {
        tabMp3.classList.add("active");
        tabMp4?.classList.remove("active");
        mp3QualityGroup?.classList.remove("hidden");
        mp4QualityGroup?.classList.add("hidden");
        selectedFormat = "mp3";
        selectedQuality = "320";
        updateDownloadButtonLabel();
    });

    // Audio Quality Chips Click
    audioQualityChips?.querySelectorAll(".quality-chip").forEach(chip => {
        chip.addEventListener("click", () => {
            audioQualityChips.querySelectorAll(".quality-chip").forEach(c => c.classList.remove("active"));
            chip.classList.add("active");
            selectedQuality = chip.getAttribute("data-quality");
            updateDownloadButtonLabel();
        });
    });

    function updateDownloadButtonLabel() {
        if (!downloadBtnText) return;
        if (selectedFormat === "mp4") {
            downloadBtnText.textContent = `Download Video (MP4 • ${selectedQuality})`;
        } else {
            downloadBtnText.textContent = `Download Audio (MP3 • ${selectedQuality} kbps)`;
        }
    }

    // Trigger Download
    startDownloadBtn?.addEventListener("click", async () => {
        startAutoDownload();
    });

    async function startAutoDownload() {
        if (!currentVideoData) return;

        if (startDownloadBtn) startDownloadBtn.disabled = true;
        if (resetBtn) resetBtn.classList.add("hidden");
        progressSection?.classList.remove("hidden");
        downloadCompletedArea?.classList.add("hidden");
        downloadErrorArea?.classList.add("hidden");

        // Reset progress UI
        if (progressStatusText) progressStatusText.textContent = "Connecting to YouTube stream...";
        if (progressPercent) progressPercent.textContent = "0%";
        if (progressBarFill) progressBarFill.style.width = "0%";
        if (progressSpeed) progressSpeed.textContent = "Connecting...";
        if (progressSize) progressSize.textContent = "0 B / Calculating...";
        if (progressEta) progressEta.textContent = "Calculating...";

        progressSection?.scrollIntoView({ behavior: "smooth", block: "nearest" });

        try {
            const response = await fetch(`${API_BASE}/api/download`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    url: currentVideoData.url,
                    format_type: selectedFormat,
                    quality: selectedQuality
                })
            });

            const result = await response.json();
            if (!result.success) {
                throw new Error(result.error || "Failed to start download.");
            }

            const taskId = result.task_id;
            pollProgress(taskId);

        } catch (err) {
            showDownloadError(err.message);
            if (startDownloadBtn) startDownloadBtn.disabled = false;
        }
    }

    // Poll Progress of Download Task
    function pollProgress(taskId) {
        if (activePollInterval) {
            clearInterval(activePollInterval);
        }

        activePollInterval = setInterval(async () => {
            try {
                const response = await fetch(`${API_BASE}/api/progress/${taskId}`);
                const data = await response.json();

                if (!data.success) {
                    clearInterval(activePollInterval);
                    showDownloadError(data.error || "Task not found");
                    startDownloadBtn.disabled = false;
                    return;
                }

                const task = data.task;
                const status = task.status;

                if (status === "downloading") {
                    if(progressStatusText) progressStatusText.textContent = `Downloading ${task.format_type.toUpperCase()} stream...`;
                    if(progressPercent) progressPercent.textContent = `${task.percent}%`;
                    if(progressBarFill) progressBarFill.style.width = `${task.percent}%`;
                    if(progressSpeed) progressSpeed.textContent = task.speed;
                    if(progressSize) progressSize.textContent = `${task.downloaded_bytes} / ${task.total_bytes}`;
                    if(progressEta) progressEta.textContent = task.eta;
                } else if (status === "processing") {
                    if(progressStatusText) progressStatusText.textContent = "Processing and converting with FFmpeg...";
                    if(progressPercent) progressPercent.textContent = "99%";
                    if(progressBarFill) progressBarFill.style.width = "99%";
                    if(progressSpeed) progressSpeed.textContent = "Encoding...";
                    if(progressEta) progressEta.textContent = "A few seconds...";
                } else if (status === "completed") {
                    clearInterval(activePollInterval);
                    if(progressBarFill) progressBarFill.style.width = "100%";
                    if(progressPercent) progressPercent.textContent = "100%";
                    if(progressStatusText) progressStatusText.textContent = "Done! Downloading to your browser...";
                    if(progressSpeed) progressSpeed.textContent = "Done";
                    if(progressEta) progressEta.textContent = "0s";
                    const finalSize = task.total_bytes || task.downloaded_bytes || "Unknown size";
                    if(progressSize) progressSize.textContent = `${finalSize} / ${finalSize}`;

                    // Show success area
                    const fileDownloadUrl = task.download_url.startsWith("http") ? task.download_url : `${API_BASE}${task.download_url}`;
                    
                    if(completedFilename) {
                        // Strip YouTube ID in brackets e.g. "Title [xyz].mp4" -> "Title.mp4"
                        let cleanName = task.filename.replace(/\s*\[.*?\](?=\.[a-zA-Z0-9]+$)/, "");
                        completedFilename.textContent = cleanName;
                    }
                    if(completedFilesize) {
                        const sizeStr = task.total_bytes || task.downloaded_bytes || "Unknown size";
                        completedFilesize.textContent = `Size: ${sizeStr} • Downloaded directly to browser`;
                    }

                    downloadCompletedArea?.classList.remove("hidden");
                    if (startDownloadBtn) startDownloadBtn.disabled = false;

                    // Automatically trigger browser file save
                    const autoLink = document.createElement("a");
                    autoLink.href = fileDownloadUrl;
                    autoLink.setAttribute("download", task.filename);
                    autoLink.style.display = "none";
                    document.body.appendChild(autoLink);
                    autoLink.click();
                    setTimeout(() => document.body.removeChild(autoLink), 1000);

                    showToast("Download complete. Saving to browser...", "success");


                } else if (status === "error") {
                    clearInterval(activePollInterval);
                    showDownloadError(task.error || "An unexpected error occurred during download.");
                    startDownloadBtn.disabled = false;
                }

            } catch (error) {
                console.error("Polling error:", error);
            }
        }, 600);
    }

    function showDownloadError(msg) {
        downloadErrorArea?.classList.remove("hidden");
        if(downloadErrorMsg) downloadErrorMsg.textContent = msg;
        if(progressStatusText) progressStatusText.textContent = "Failed";
        showToast("Download error: " + msg, "error");
    }

    // Toast Notification Utility
    function showToast(message, type = "info") {
        const toastContainer = document.getElementById("toastContainer");
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;

        let iconSvg = "";
        if (type === "success") {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
        } else if (type === "error") {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
        } else {
            iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#06b6d4" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
        }

        toast.innerHTML = `
            ${iconSvg}
            <span>${message}</span>
        `;

        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(20px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, 3500);
    }
});

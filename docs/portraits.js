// Optional, in-memory presentation layer. Trace records are never changed.
import {
    loadDirectory,
    findServedDirectory,
    loadServedDirectory,
} from "./portrait-data.js?v=20260915-served-directory-1";
import {
    avatarImg,
    anonymousAvatarUri,
    setDirectoryPortraits,
    clearDirectoryPortraits,
} from "./avatars.js?v=20260915-served-directory-1";

import {
    mapDirectoryStudents,
    setDirectoryNames,
    displayName,
    studentLabel,
} from "./names.js?v=20260915-served-directory-1";

const $ = (id) => document.getElementById(id);
// serve_local.py exposes the saved directory here; other hosts return 404.
const SERVED_DIRECTORY = new URL("student_directory/", document.baseURI);
const PROGRESS_LABELS = {
    downloading: "Loading photos",
    photos: "Preparing portraits",
};

/** Match each synthetic slot once, within its grade. Missing images stay empty. */
export function mapPortraits(simulated, directory) {
    return new Map(
        [...mapDirectoryStudents(simulated, directory)]
            .filter(
                ([, person]) =>
                    typeof person.photoUrl === "string" &&
                    person.photoUrl.startsWith("blob:"),
            )
            .map(([id, person]) => [id, person.photoUrl]),
    );
}

export function createPortraitControls({ trace, tabs, stop, hideTooltip }) {
    // Validate every view before reading any directory or changing shared photos.
    // An older cached view cannot participate in the all-tab portrait layer.
    const portraitTabs = ["room", "student", "game", "math"].map(
        (name) => tabs[name],
    );
    if (portraitTabs.some((tab) => typeof tab?.setPortraits !== "function")) {
        const error = new Error(
            "This page loaded an older version of a view. Reload the page to enable directory portraits in all four tabs.",
        );
        error.code = "STALE_PORTRAIT_MODULE";
        throw error;
    }
    const roomTab = tabs.room;
    const input = $("portrait-folder");
    const load = $("portrait-load");
    const clear = $("portrait-clear");
    const status = $("portrait-status");
    const controls = $("portrait-controls");
    const zoom = $("portrait-zoom");
    const table = $("portrait-table");
    const source = $("portrait-source");
    const tools = $("portrait-tools");
    const inspection = $("portrait-inspection");
    const seats = $("portrait-seats");
    const frames = [...document.querySelectorAll(".panel .room-frame")];
    const legend = $("room-legend-hint");
    const originalLegend = legend.textContent;
    const grades = new Map(
        trace.students.map((student) => [student.id, student.grade]),
    );
    let urls = new Map();
    let names = new Map();
    let dispose = null;
    let generation = 0;

    for (let index = 0; index < trace.config.tableCapacities.length; index++) {
        const option = document.createElement("option");
        option.value = String(index);
        option.textContent = `Table ${index + 1}`;
        table.append(option);
    }

    function setLoading(loading) {
        load.disabled = loading;
        load.textContent = loading
            ? "Loading…"
            : names.size
              ? "Change directory"
              : "Load directory";
        clear.hidden = !loading && !names.size;
        controls.setAttribute("aria-busy", String(loading));
    }

    function updateTabs(map, labels = names) {
        setDirectoryNames(labels);
        if (map.size) setDirectoryPortraits(map);
        else clearDirectoryPortraits();
        portraitTabs.forEach((tab) => tab.setPortraits(map));
    }

    function applyZoom() {
        if (!urls.size) return;
        const scale = Number(zoom.value);
        frames.forEach((frame) => {
            const height = frame.closest(".stage-layout")
                ? 350
                : frame.classList.contains("tall")
                  ? Math.max(320, Math.min(620, window.innerHeight - 330))
                  : Math.max(280, Math.min(520, window.innerHeight - 385));
            const canvas = frame.querySelector("canvas");
            frame.style.height = `${height + 16}px`;
            canvas.style.width = `${scale * 100}%`;
            canvas.style.height = `${height * scale}px`;
        });
        Object.values(tabs).forEach((tab) => tab.resize());
    }

    function inspect(info) {
        seats.replaceChildren();
        if (!info || !names.size) {
            inspection.hidden = true;
            table.value = "";
            return;
        }
        stop();
        source.value = info.key;
        table.value = String(info.table);
        const baseline =
            info.key === "tablesRandom" ? "Random baseline" : "Proposed solver";
        $("portrait-table-heading").textContent =
            `${baseline} · Table ${info.table + 1}`;
        $("portrait-table-description").textContent =
            `Rotation ${info.index + 1} · ${info.ids.length} seats`;
        for (const id of info.ids) {
            const card = document.createElement("div");
            card.className = "portrait-seat";
            card.dataset.id = id;
            const url = urls.get(id);
            const img = url ? new Image() : avatarImg(id);
            if (url) img.src = url;
            img.alt = url
                ? `Illustrative portrait for simulated student ${studentLabel(id)}`
                : `Anonymous avatar for ${studentLabel(id)}`;
            img.width = 80;
            img.height = 80;
            img.addEventListener(
                "error",
                () => {
                    const fallback = new Image();
                    fallback.src = anonymousAvatarUri(id);
                    fallback.alt = `Anonymous avatar for ${studentLabel(id)}`;
                    fallback.width = 80;
                    fallback.height = 80;
                    img.replaceWith(fallback);
                },
                { once: true },
            );
            const label = document.createElement("strong");
            label.textContent = displayName(id);
            const grade = document.createElement("span");
            grade.textContent = `${id} · Grade ${grades.get(id)}`;
            card.append(img, label, grade);
            if (!url) {
                const caption = document.createElement("small");
                caption.textContent = "No photo";
                card.append(caption);
            }
            seats.append(card);
        }
        inspection.hidden = false;
    }

    function showNotes(notes) {
        $("portrait-warnings").open = false;
        const list = $("portrait-warning-list");
        list.replaceChildren();
        for (const note of notes) {
            const item = document.createElement("li");
            item.textContent = note;
            list.append(item);
        }
        $("portrait-warnings").hidden = !notes.length;
    }

    function removePhotos() {
        generation++;
        stop();
        hideTooltip();
        urls = new Map();
        names = new Map();
        updateTabs(urls);
        inspect(null);
        dispose?.();
        dispose = null;
        document.body.classList.remove("portrait-mode");
        tools.hidden = true;
        $("portrait-zoom-control").hidden = true;
        frames.forEach((frame) => {
            frame.style.removeProperty("height");
            const canvas = frame.querySelector("canvas");
            canvas.style.removeProperty("width");
            canvas.style.removeProperty("height");
            frame.scrollTo(0, 0);
        });
        Object.values(tabs).forEach((tab) => tab.resize());
        legend.textContent = originalLegend;
        input.value = "";
        showNotes([]);
        status.textContent = "Directory removed";
        status.classList.remove("error");
        setLoading(false);
    }

    async function showDirectory(read) {
        const current = ++generation;
        stop();
        hideTooltip();
        setLoading(true);
        status.classList.remove("error");
        status.textContent = "Reading directory…";
        let result = null;
        try {
            result = await read((progress) => {
                if (current !== generation) return;
                const action =
                    PROGRESS_LABELS[progress.phase] || "Reading grade files";
                status.textContent = `${action}: ${progress.completed} / ${progress.total}`;
            });
            if (current !== generation) {
                result.dispose();
                return;
            }
            const mapped = mapPortraits(trace.students, result.students);
            const labels = new Map(
                [...mapDirectoryStudents(trace.students, result.students)].map(
                    ([id, person]) => [id, person.name],
                ),
            );
            if (!labels.size)
                throw new Error(
                    "No students matched this demo’s grades. Choose a directory folder containing grades 11 and 12.",
                );
            const previousDispose = dispose;
            try {
                updateTabs(mapped, labels);
            } catch (error) {
                updateTabs(urls);
                throw error;
            }
            urls = mapped;
            names = labels;
            inspect(null);
            dispose = result.dispose;
            previousDispose?.();
            showNotes(result.warnings);
            status.textContent = `${names.size} names · ${urls.size} photos · ${trace.students.length - urls.size} missing photos`;
            document.body.classList.add("portrait-mode");
            tools.hidden = false;
            $("portrait-zoom-control").hidden = false;
            legend.textContent = "Select a table to enlarge";
            zoom.value = "1";
            applyZoom();
        } catch (error) {
            result?.dispose();
            if (current !== generation) return;
            status.textContent = `${error.message || "The directory could not be read."}${names.size ? " Your previous directory view is still loaded." : ""}`;
            status.classList.add("error");
        } finally {
            if (current === generation) setLoading(false);
        }
    }

    // Probe quietly so hosts without a served directory keep the plain button.
    async function autoLoadDirectory() {
        const started = generation;
        const grades = [...new Set(trace.students.map((student) => student.grade))];
        const served = await findServedDirectory(SERVED_DIRECTORY, grades);
        // A folder chosen while probing wins over the served copy.
        if (served && started === generation)
            await showDirectory((onProgress) =>
                loadServedDirectory(served, { onProgress }),
            );
    }

    load.addEventListener("click", () => input.click());
    input.addEventListener("change", () => {
        const files = [...input.files];
        input.value = "";
        if (files.length)
            showDirectory((onProgress) => loadDirectory(files, { onProgress }));
    });
    clear.addEventListener("click", removePhotos);
    $("portrait-inspection-close").addEventListener("click", () =>
        inspect(null),
    );
    zoom.addEventListener("change", () => {
        stop();
        applyZoom();
    });
    table.addEventListener("change", () => {
        stop();
        if (table.value === "") inspect(null);
        else roomTab.selectTable(Number(table.value), source.value);
    });
    source.addEventListener("change", () => {
        stop();
        if (table.value !== "")
            roomTab.selectTable(Number(table.value), source.value);
    });
    window.addEventListener("resize", applyZoom);
    window.addEventListener("pagehide", removePhotos);
    setLoading(false);
    autoLoadDirectory();
    return { inspect, clear: removePhotos, resize: applyZoom };
}

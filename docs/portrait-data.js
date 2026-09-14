/* Browser-local Blackbaud portrait loading. No uploads, persistence, or remote reads. */

const MAX_FILES = 10_000;
const MAX_HTML_FILES = 24;
const MAX_HTML_BYTES = 10 * 1024 * 1024;
const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
const MAX_PHOTO_PIXELS = 12_000_000;
const MAX_STUDENTS = 2_000;
const MAX_PHOTO_EDGE = 320;
const SAFE_ID = /^[A-Za-z0-9_-]{1,80}$/;
const GRADUATION_SUFFIX = /\s+['’](\d{2})\s*$/;
const RASTER_EXTENSION = /\.(?:jpe?g|png|webp)$/i;

function cleanText(value) {
  return String(value ?? "")
    .normalize("NFC")
    .replace(/[\p{Cc}\p{Cf}]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function safeFilePath(value) {
  const path = String(value || "");
  if (!path || path.startsWith("/") || path.includes("\\") || /[\u0000-\u001f\u007f]/.test(path)) return null;
  const parts = path.split("/");
  if (parts.some((part) => part === "..")) return null;
  return parts.filter((part) => part && part !== ".").join("/") || null;
}

function gradeFromFilename(filename) {
  const stem = filename.replace(/\.html?$/i, "");
  const match = stem.match(/(?:^|\D)(1[0-2]|9)(?:st|nd|rd|th)?[\s_-]*grade/i)
    || stem.match(/grade[\s_-]*(1[0-2]|9)(?!\d)/i);
  return match ? Number(match[1]) : null;
}

function localPhotoFile(source, htmlPath, filesByPath) {
  if (!source || /^[a-z][a-z0-9+.-]*:/i.test(source) || source.startsWith("/") || source.includes("\\")) return null;
  let decoded;
  try {
    decoded = decodeURIComponent(source.split(/[?#]/, 1)[0]);
  } catch {
    return null;
  }
  if (!RASTER_EXTENSION.test(decoded)) return null;
  const relative = safeFilePath(decoded);
  if (!relative) return null;
  const parent = htmlPath.includes("/") ? htmlPath.slice(0, htmlPath.lastIndexOf("/") + 1) : "";
  // Only exact selected-file paths are usable. Traversal and network URLs never
  // reach a decoder, and no resource is fetched from the saved page itself.
  return filesByPath.get(parent + relative) || null;
}

function primaryRowNodes(row, selector) {
  return [...row.querySelectorAll(selector)].filter((node) => node.closest("tr") === row && !node.closest('[id^="additional-container"]'));
}

function parseGradeHtml(text, htmlPath, filesByPath) {
  const filename = htmlPath.split("/").at(-1);
  const grade = gradeFromFilename(filename);
  const fragment = document.createElement("template");
  // Template contents remain inert. In particular, saved <img>, <iframe>,
  // <link>, and <script> elements are never inserted into the live document.
  fragment.innerHTML = text;
  const content = fragment.content;
  const translated = /<html\b[^>]*\bclass\s*=\s*["'][^"']*\btranslated-(?:ltr|rtl)\b/i.test(text);
  for (const node of content.querySelectorAll("script,style,iframe,object,embed,link,meta,base,template")) node.remove();
  const table = content.querySelector("#directory-items-container");
  if (!table || table.tagName !== "TABLE") {
    throw new Error(`${filename}: no Blackbaud list-view student directory was found.`);
  }
  const rows = [...table.querySelectorAll(":scope > tbody > tr, :scope > tr")];
  const students = [];
  const years = [];
  const warnings = [];
  if (translated) warnings.push(`${filename} contains browser-translated text. Verify that the original grade export is the intended source.`);
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const headings = primaryRowNodes(row, "h3");
    const buttons = primaryRowNodes(row, ".user-options-button[data-userid]");
    if (!headings.length && !buttons.length && row.querySelector("th")) continue;
    if (headings.length !== 1 || buttons.length !== 1) {
      throw new Error(`${filename}: student row ${index + 1} has missing or ambiguous student details.`);
    }
    const id = String(buttons[0].getAttribute("data-userid") || "").trim();
    const heading = cleanText(headings[0].textContent);
    const name = heading.replace(GRADUATION_SUFFIX, "");
    if (!SAFE_ID.test(id) || !name || name.length > 200 || !/\p{L}/u.test(name) || /[<>@]/.test(name)) {
      throw new Error(`${filename}: student row ${index + 1} has an invalid ID or name.`);
    }
    const graduation = heading.match(GRADUATION_SUFFIX);
    if (graduation) years.push({ row: index + 1, year: graduation[1] });
    const photoCell = row.querySelector(":scope > td:first-child");
    const avatar = photoCell?.querySelector("img.bb-avatar-image");
    students.push({ id, name, grade, photoUrl: null, photoFile: localPhotoFile(avatar?.getAttribute("src"), htmlPath, filesByPath) });
  }
  if (!students.length) throw new Error(`${filename}: no student records were found.`);
  const yearCounts = new Map();
  for (const item of years) yearCounts.set(item.year, (yearCounts.get(item.year) || 0) + 1);
  if (yearCounts.size > 1) {
    const majority = [...yearCounts].sort((a, b) => b[1] - a[1])[0][0];
    const unusual = years.filter((item) => item.year !== majority).map((item) => item.row);
    warnings.push(`${filename} contains an inconsistent graduation year in student row(s) ${unusual.slice(0, 10).join(", ")}${unusual.length > 10 ? " and others" : ""}. Grades follow the export filenames.`);
  }
  return { students, warnings };
}

async function rasterSignature(file) {
  const bytes = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  if (bytes.length < 12) return false;
  const jpeg = bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff;
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((value, index) => bytes[index] === value);
  const webp = String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP";
  return jpeg || png || webp;
}

async function decodeLocalRaster(file) {
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    return { image: bitmap, width: bitmap.width, height: bitmap.height, close: () => bitmap.close() };
  }
  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = objectUrl;
    await image.decode();
    return { image, width: image.naturalWidth, height: image.naturalHeight, close: () => URL.revokeObjectURL(objectUrl) };
  } catch (error) {
    URL.revokeObjectURL(objectUrl);
    throw error;
  }
}

async function normalizedPortrait(file) {
  if (!file || file.size > MAX_PHOTO_BYTES || !await rasterSignature(file)) return null;
  let decoded;
  const canvas = document.createElement("canvas");
  try {
    decoded = await decodeLocalRaster(file);
    const { width, height } = decoded;
    if (!width || !height || width * height > MAX_PHOTO_PIXELS) return null;
    const scale = Math.min(1, MAX_PHOTO_EDGE / Math.max(width, height));
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) return null;
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(decoded.image, 0, 0, canvas.width, canvas.height);
    // Canvas produces fresh pixels; original EXIF/GPS/text metadata is omitted.
    return await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.88));
  } catch {
    return null;
  } finally {
    decoded?.close();
    canvas.width = 0;
    canvas.height = 0;
  }
}

/**
 * Load a selected saved-directory folder entirely within this browser tab.
 * onProgress receives {phase: 'reading'|'photos', completed, total}.
 * Call dispose() when replacing or clearing the returned data to revoke URLs.
 */
export async function loadDirectory(files, { onProgress } = {}) {
  const selection = Array.from(files || []);
  if (!selection.length) throw new Error("Choose the folder containing your saved grade directories and their image folders.");
  if (selection.length > MAX_FILES) throw new Error(`Choose a school directory folder with no more than ${MAX_FILES.toLocaleString()} files.`);
  const urls = new Set();
  const dispose = () => {
    for (const url of urls) URL.revokeObjectURL(url);
    urls.clear();
  };
  const notify = (phase, completed, total) => {
    if (typeof onProgress === "function") onProgress({ phase, completed, total });
  };
  try {
    const filesByPath = new Map();
    for (const file of selection) {
      if (!(file instanceof Blob) || typeof file.name !== "string") throw new Error("The selection contains an unsupported file.");
      const path = safeFilePath(file.webkitRelativePath || file.name);
      if (!path) throw new Error("The selected folder contains an invalid file path.");
      if (filesByPath.has(path)) throw new Error("The selection contains duplicate file paths. Choose one saved directory folder.");
      filesByPath.set(path, file);
    }
    const htmlFiles = [...filesByPath].filter(([path]) => /\.html?$/i.test(path) && gradeFromFilename(path.split("/").at(-1)) !== null).sort(([a], [b]) => a.localeCompare(b));
    if (!htmlFiles.length) throw new Error("No grade exports were found. Keep filenames such as 9thgrade.html or grade-11.html and include their saved image folders.");
    if (htmlFiles.length > MAX_HTML_FILES) throw new Error("Too many grade exports were selected. Choose a folder containing one current directory per grade.");
    const records = new Map();
    const warnings = [];
    let duplicateCount = 0;
    notify("reading", 0, htmlFiles.length);
    for (let index = 0; index < htmlFiles.length; index += 1) {
      const [path, file] = htmlFiles[index];
      if (file.size > MAX_HTML_BYTES) throw new Error("Each grade HTML export must be 10 MB or smaller.");
      const parsed = parseGradeHtml(await file.text(), path, filesByPath);
      warnings.push(...parsed.warnings);
      for (const record of parsed.students) {
        const previous = records.get(record.id);
        if (previous) {
          if (previous.grade !== record.grade || previous.name.toLowerCase() !== record.name.toLowerCase()) {
            throw new Error("The same student ID appears with conflicting names or grades. Check the selected exports.");
          }
          duplicateCount += 1;
          if (!previous.photoFile) previous.photoFile = record.photoFile;
        } else records.set(record.id, record);
        if (records.size > MAX_STUDENTS) throw new Error(`At most ${MAX_STUDENTS.toLocaleString()} students can be loaded at once.`);
      }
      notify("reading", index + 1, htmlFiles.length);
    }
    const students = [...records.values()].sort((a, b) => a.grade - b.grade || a.id.localeCompare(b.id));
    let next = 0;
    let completed = 0;
    notify("photos", 0, students.length);
    async function worker() {
      while (next < students.length) {
        const student = students[next++];
        const portrait = await normalizedPortrait(student.photoFile);
        delete student.photoFile;
        if (portrait) {
          student.photoUrl = URL.createObjectURL(portrait);
          urls.add(student.photoUrl);
        }
        completed += 1;
        notify("photos", completed, students.length);
      }
    }
    // Await every worker even on failure so no late worker can leak a new URL
    // after the catch block revokes the already-created portrait URLs.
    const outcomes = await Promise.allSettled(Array.from({ length: Math.min(4, students.length) }, worker));
    const rejected = outcomes.find((outcome) => outcome.status === "rejected");
    if (rejected) throw rejected.reason;
    if (duplicateCount) warnings.push(`Merged ${duplicateCount} repeated student records with matching IDs, names, and grades.`);
    const missing = students.filter((student) => !student.photoUrl).length;
    if (missing) warnings.push(`${missing} student records have no usable local portrait; those seats can keep their colored markers.`);
    return { students, warnings, dispose };
  } catch (error) {
    dispose();
    throw error;
  }
}

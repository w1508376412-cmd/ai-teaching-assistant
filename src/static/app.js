const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const MORPHOLOGIES = [
  { id: "all", label: "全部形态", short: "全部形态", terms: [] },
  { id: "maculopapular", label: "斑 / 斑丘疹", short: "斑丘疹", terms: ["斑疹", "斑丘疹", "红斑", "玫瑰疹", "丘疹"] },
  { id: "vesicle", label: "水疱 / 大疱", short: "水疱", terms: ["水疱", "大疱", "疱疹", "疱液", "疱壁"] },
  { id: "purpura", label: "紫癜 / 瘀点", short: "紫癜", terms: ["紫癜", "瘀点", "瘀斑", "出血点", "不褪色"] },
  { id: "wheal", label: "风团 / 水肿", short: "风团", terms: ["风团", "水肿", "瘙痒"] },
  { id: "mucosa", label: "黏膜受累", short: "黏膜", terms: ["黏膜", "口腔", "口唇", "舌", "结膜", "Koplik"] },
  { id: "scale", label: "结痂 / 脱屑", short: "结痂脱屑", terms: ["结痂", "脱屑", "鳞屑", "痂皮", "糠麸"] },
  { id: "pustule", label: "脓疱 / 糜烂", short: "脓疱", terms: ["脓疱", "脓液", "糜烂", "渗出"] },
  { id: "nodule", label: "结节 / 斑块", short: "结节", terms: ["结节", "斑块", "肿块", "浸润"] },
];

const VIEW_PATHS = {
  knowledge: "AI TEACHING ASSISTANT / KNOWLEDGE CONSULT",
  atlas: "AI TEACHING ASSISTANT / RASH ATLAS",
  cases: "AI TEACHING ASSISTANT / CASE DRILL",
  admin: "AI TEACHING ASSISTANT / FACULTY CONTROL",
};

const state = {
  atlas: null,
  diseases: [],
  cases: [],
  casesLoaded: false,
  currentCaseIndex: 0,
  qaMessages: [],
  stageIndex: 0,
  stageMessages: [],
  atlasQuery: "",
  atlasCategory: "all",
  atlasMorphology: "all",
  compareIds: new Set(),
  adminPassword: sessionStorage.getItem("adminPassword") || "",
};

const els = {
  sidebar: $("#sidebar"),
  sidebarAtlasTools: $("#sidebarAtlasTools"),
  sidebarScrim: $("#sidebarScrim"),
  menuButton: $("#menuButton"),
  topbarKicker: $("#topbarKicker"),
  topbarTitle: $("#topbarTitle"),
  adminNav: $("#adminNav"),
  atlasSearch: $("#atlasSearch"),
  categoryFilters: $("#categoryFilters"),
  morphologyFilters: $("#morphologyFilters"),
  diseaseGrid: $("#diseaseGrid"),
  atlasEmpty: $("#atlasEmpty"),
  compareDock: $("#compareDock"),
  compareCount: $("#compareCount"),
  compareNames: $("#compareNames"),
  clearCompare: $("#clearCompare"),
  openCompare: $("#openCompare"),
  diseaseDialog: $("#diseaseDialog"),
  diseaseDialogContent: $("#diseaseDialogContent"),
  compareDialog: $("#compareDialog"),
  compareDialogContent: $("#compareDialogContent"),
  imageDialog: $("#imageDialog"),
  lightboxImage: $("#lightboxImage"),
  lightboxCaption: $("#lightboxCaption"),
  chatFeed: $("#chatFeed"),
  chatForm: $("#chatForm"),
  chatInput: $("#chatInput"),
  clearChat: $("#clearChat"),
  caseSelect: $("#caseSelect"),
  nextCase: $("#nextCase"),
  caseEmpty: $("#caseEmpty"),
  caseWorkspace: $("#caseWorkspace"),
  caseSequence: $("#caseSequence"),
  caseTitle: $("#caseTitle"),
  caseBackground: $("#caseBackground"),
  patientGrid: $("#patientGrid"),
  decisionBoard: $("#decisionBoard"),
  decisionForm: $("#decisionForm"),
  diseaseOptions: $("#diseaseOptions"),
  measureOptions: $("#measureOptions"),
  treatmentOptions: $("#treatmentOptions"),
  decisionFeedback: $("#decisionFeedback"),
  stageBoard: $("#stageBoard"),
  stageTitle: $("#stageTitle"),
  stageTask: $("#stageTask"),
  stageData: $("#stageData"),
  stageChat: $("#stageChat"),
  stageForm: $("#stageForm"),
  stageInput: $("#stageInput"),
  nextStage: $("#nextStage"),
  adminUnlock: $("#adminUnlock"),
  adminDashboard: $("#adminDashboard"),
  adminLoginForm: $("#adminLoginForm"),
  adminPassword: $("#adminPassword"),
  caseList: $("#caseList"),
  adminCaseCount: $("#adminCaseCount"),
  toast: $("#toast"),
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function richText(value = "") {
  return escapeHtml(value)
    .replace(/^###\s+(.+)$/gm, "<strong>$1</strong>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\s*[-•]\s+(.+)$/gm, "· $1")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

function inlineAnswerText(value = "") {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function structuredAnswer(value = "") {
  const lines = String(value).replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  let listType = "";
  let listItems = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    const labeled = /^\*\*[^*]+[：:]\*\*/.test(paragraph[0]);
    blocks.push(`<p${labeled ? ' class="answer-labeled-paragraph"' : ""}>${paragraph.map(inlineAnswerText).join("<br>")}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(`<${listType}>${listItems.map((item) => `<li>${inlineAnswerText(item)}</li>`).join("")}</${listType}>`);
    listType = "";
    listItems = [];
  };

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }

    const boldHeading = trimmed.match(/^\*\*(.+[：:])\*\*$/);
    const heading = trimmed.match(/^#{2,4}\s+(.+)$/) || trimmed.match(/^([一二三四五六七八九十]+[、.]\s*.+)$/) || boldHeading;
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push(`<h3${boldHeading ? ' class="answer-section-label"' : ""}>${inlineAnswerText(heading[1])}</h3>`);
      return;
    }

    const orderedItem = trimmed.match(/^\d+[.)、]\s*(.+)$/);
    const unorderedItem = trimmed.match(/^[-•]\s+(.+)$/);
    if (orderedItem || unorderedItem) {
      flushParagraph();
      const nextListType = orderedItem ? "ol" : "ul";
      if (listType && listType !== nextListType) flushList();
      listType = nextListType;
      listItems.push((orderedItem || unorderedItem)[1]);
      return;
    }

    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();
  return blocks.join("");
}

function errorMessage(error) {
  return error?.message || "操作未完成，请稍后重试。";
}

function imageUrl(file) {
  return `/assets/rash-atlas/images/${encodeURIComponent(file)}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(data?.detail || data?.message || `请求失败（${response.status}）`);
  return data;
}

async function adminApi(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Admin-Password", state.adminPassword);
  return api(path, { ...options, headers });
}

let toastTimer;
function toast(message, isError = false) {
  clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.classList.toggle("is-error", isError);
  els.toast.classList.add("is-visible");
  toastTimer = setTimeout(() => els.toast.classList.remove("is-visible"), 3600);
}

function setBusy(button, busy, label = "处理中…") {
  if (!button) return;
  if (busy) {
    if (!button.dataset.original) button.dataset.original = button.innerHTML;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.innerHTML = button.dataset.original || button.innerHTML;
    button.disabled = false;
  }
}

function autosize(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
}

function openSidebar(open) {
  els.sidebar.classList.toggle("is-open", open);
  els.sidebarScrim.classList.toggle("is-open", open);
  els.menuButton.setAttribute("aria-expanded", String(open));
}

function switchView(viewName, updateUrl = true) {
  const target = $(`#view-${viewName}`);
  if (!target) return;
  $$(".workspace-view").forEach((view) => view.classList.toggle("is-active", view === target));
  $$(".nav-item").forEach((button) => button.classList.toggle("is-active", button.dataset.view === viewName));
  const atlasToolsVisible = viewName === "atlas";
  els.sidebar.classList.toggle("has-atlas-tools", atlasToolsVisible);
  els.sidebarAtlasTools.setAttribute("aria-hidden", String(!atlasToolsVisible));
  els.topbarKicker.textContent = VIEW_PATHS[viewName] || "AI TEACHING ASSISTANT";
  els.topbarTitle.textContent = target.dataset.title || "教学工作台";
  renderCompareDock();
  openSidebar(false);
  window.scrollTo({ top: 0, behavior: "smooth" });
  if (updateUrl) {
    const hash = viewName === "knowledge" ? "" : `#${viewName}`;
    history.replaceState(null, "", `${location.pathname}${location.search}${hash}`);
  }
  if (viewName === "atlas") {
    void ensureAtlas().catch((error) => toast(errorMessage(error), true));
  } else if (viewName === "cases") {
    void ensureCases().catch((error) => toast(errorMessage(error), true));
  }
}

function flattenAtlas(atlas) {
  return (atlas.categories || []).flatMap((category) =>
    (category.diseases || []).map((disease) => ({ ...disease, category: category.title, category_id: category.id })),
  );
}

function diseaseById(id) {
  return state.diseases.find((disease) => disease.id === id);
}

function matchesMorphology(disease, morphologyId) {
  const morphology = MORPHOLOGIES.find((item) => item.id === morphologyId);
  if (!morphology || !morphology.terms.length) return true;
  const searchable = disease.search_text.toLowerCase();
  return morphology.terms.some((term) => searchable.includes(term.toLowerCase()));
}

function filteredDiseases() {
  const query = state.atlasQuery.trim().toLowerCase();
  return state.diseases.filter((disease) => {
    const categoryMatch = state.atlasCategory === "all" || disease.category_id === state.atlasCategory;
    const morphologyMatch = matchesMorphology(disease, state.atlasMorphology);
    const queryMatch = !query || `${disease.search_text} ${disease.category}`.toLowerCase().includes(query);
    return categoryMatch && morphologyMatch && queryMatch;
  });
}

function renderAtlasFilters() {
  const allButton = `<button type="button" data-category="all" class="${state.atlasCategory === "all" ? "is-active" : ""}"><span>全部类别</span></button>`;
  const availableCategories = (state.atlas?.categories || []).filter((category) =>
    state.diseases.some((disease) => disease.category_id === category.id && matchesMorphology(disease, state.atlasMorphology)),
  );
  els.categoryFilters.innerHTML = allButton + availableCategories.map((category) =>
    `<button type="button" data-category="${escapeHtml(category.id)}" class="${state.atlasCategory === category.id ? "is-active" : ""}"><span>${escapeHtml(category.title.replace("（高发）", ""))}</span></button>`,
  ).join("");

  const availableMorphologies = MORPHOLOGIES.filter((morphology) =>
    morphology.id === "all" || state.diseases.some((disease) => {
      const categoryMatch = state.atlasCategory === "all" || disease.category_id === state.atlasCategory;
      return categoryMatch && matchesMorphology(disease, morphology.id);
    }),
  );
  els.morphologyFilters.innerHTML = availableMorphologies.map((morphology) => {
    return `<button type="button" data-morph="${morphology.id}" class="${state.atlasMorphology === morphology.id ? "is-active" : ""}"><span>${escapeHtml(morphology.label)}</span></button>`;
  }).join("");
}

function diseaseCardMarkup(disease) {
  const cover = disease.images?.[0];
  const hasTextbook = disease.images?.some((item) => item.textbook);
  const checked = state.compareIds.has(disease.id);
  return `
    <article class="disease-card" data-disease-card="${escapeHtml(disease.id)}">
      <button class="disease-cover" type="button" data-open-disease="${escapeHtml(disease.id)}" aria-label="查看${escapeHtml(disease.name)}详情">
        ${cover ? `<img src="${imageUrl(cover.file)}" alt="${escapeHtml(cover.alt || `${disease.name}皮疹`)}" loading="lazy" decoding="async">` : ""}
        <span class="image-tally">${disease.image_count} IMAGE${disease.image_count === 1 ? "" : "S"}</span>
      </button>
      <div class="disease-card-body">
        <div class="card-kicker"><span>${escapeHtml(disease.category)}</span>${hasTextbook ? '<span class="textbook-flag">含教材图</span>' : ""}</div>
        <h3>${escapeHtml(disease.name)}<small>${escapeHtml(disease.english || "—")}</small></h3>
        <p class="card-clue">${escapeHtml(disease.facts?.["鉴别要点"] || disease.facts?.["皮疹"] || "查看病种详情")}</p>
        <div class="card-actions">
          <button class="view-disease" type="button" data-open-disease="${escapeHtml(disease.id)}">查看鉴别要点</button>
          <label class="compare-toggle"><input type="checkbox" data-compare="${escapeHtml(disease.id)}" ${checked ? "checked" : ""}><span>加入比较</span></label>
        </div>
      </div>
    </article>`;
}

function renderAtlas() {
  if (!state.atlas) return;
  renderAtlasFilters();
  const diseases = filteredDiseases();
  els.diseaseGrid.innerHTML = diseases.map(diseaseCardMarkup).join("");
  els.diseaseGrid.classList.toggle("is-hidden", !diseases.length);
  els.atlasEmpty.classList.toggle("is-hidden", Boolean(diseases.length));
}

function setCompare(id, selected) {
  if (selected && !state.compareIds.has(id) && state.compareIds.size >= 3) {
    toast("最多同时比较 3 个病种。", true);
    const input = $(`[data-compare="${CSS.escape(id)}"]`);
    if (input) input.checked = false;
    return;
  }
  if (selected) state.compareIds.add(id);
  else state.compareIds.delete(id);
  renderCompareDock();
}

function renderCompareDock() {
  const selected = [...state.compareIds].map(diseaseById).filter(Boolean);
  const atlasVisible = $("#view-atlas").classList.contains("is-active");
  els.compareDock.classList.toggle("is-hidden", !selected.length || !atlasVisible);
  els.compareCount.textContent = `${selected.length} / 3`;
  els.compareNames.textContent = selected.map((item) => item.name).join(" · ") || "尚未选择病种";
  els.openCompare.disabled = selected.length < 2;
  $$('[data-compare]').forEach((input) => { input.checked = state.compareIds.has(input.dataset.compare); });
  const detailButton = $("[data-toggle-detail-compare]", els.diseaseDialogContent);
  if (detailButton) {
    const inCompare = state.compareIds.has(detailButton.dataset.toggleDetailCompare);
    detailButton.innerHTML = `${inCompare ? "移出" : "加入"}并排比较 <span>${inCompare ? "−" : "+"}</span>`;
  }
}

function openDisease(id) {
  const disease = diseaseById(id);
  if (!disease) {
    toast("病种资料仍在载入，请稍后再试。", true);
    return;
  }
  const facts = Object.entries(disease.facts || {}).map(([label, value]) => `<div class="detail-fact"><b>${escapeHtml(label)}</b><p>${escapeHtml(value)}</p></div>`).join("");
  const figures = (disease.images || []).map((item, index) => {
    const links = (item.links || []).map((link) => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.label)}</a>`).join("");
    return `
      <figure class="detail-figure">
        <button class="detail-image-button" type="button" data-lightbox-disease="${escapeHtml(disease.id)}" data-lightbox-index="${index}" aria-label="放大查看${escapeHtml(item.alt || disease.name)}"><img src="${imageUrl(item.file)}" alt="${escapeHtml(item.alt || `${disease.name}皮疹`)}" loading="lazy" decoding="async"></button>
        <figcaption><div class="figure-source"><span>${escapeHtml(item.source_label)}</span><span>${escapeHtml(item.license)}</span></div><p>${escapeHtml(item.caption || item.provider || "图像出处见来源链接。")}</p>${links ? `<div class="figure-links">${links}</div>` : ""}</figcaption>
      </figure>`;
  }).join("");
  const inCompare = state.compareIds.has(id);
  els.diseaseDialogContent.innerHTML = `
    <header class="disease-detail-head"><span class="detail-kicker">${escapeHtml(disease.category)} / DISEASE NOTE</span><h2 id="diseaseDialogTitle">${escapeHtml(disease.name)}<small>${escapeHtml(disease.english || "")}</small></h2></header>
    <div class="detail-actions"><button class="line-button" type="button" data-toggle-detail-compare="${escapeHtml(disease.id)}">${inCompare ? "移出" : "加入"}并排比较 <span>${inCompare ? "−" : "+"}</span></button></div>
    <section class="detail-facts" aria-label="${escapeHtml(disease.name)}鉴别要点">${facts}</section>
    <div class="detail-gallery-title"><h3>皮疹特征</h3></div>
    <div class="detail-gallery">${figures}</div>
`;
  els.diseaseDialog.showModal();
}

function openLightbox(diseaseId, imageIndex) {
  const disease = diseaseById(diseaseId);
  const item = disease?.images?.[imageIndex];
  if (!item) return;
  els.lightboxImage.src = imageUrl(item.file);
  els.lightboxImage.alt = item.alt || `${disease.name}皮疹`;
  els.lightboxCaption.textContent = `${disease.name} · ${item.caption || item.provider || item.source_label} · ${item.license}`;
  els.imageDialog.showModal();
}

function openComparison() {
  const selected = [...state.compareIds].map(diseaseById).filter(Boolean);
  if (selected.length < 2) return;
  const dimensions = [...new Set(selected.flatMap((disease) => Object.keys(disease.facts || {})))];
  const headers = selected.map((disease) => {
    const cover = disease.images?.[0];
    return `<th><div class="compare-disease-head">${cover ? `<img src="${imageUrl(cover.file)}" alt="${escapeHtml(disease.name)}皮疹" decoding="async">` : ""}<strong>${escapeHtml(disease.name)}</strong><small>${escapeHtml(disease.english || "")} · ${escapeHtml(disease.category)}</small></div></th>`;
  }).join("");
  const rows = dimensions.map((dimension) => `<tr><td><strong>${escapeHtml(dimension)}</strong></td>${selected.map((disease) => `<td>${escapeHtml(disease.facts?.[dimension] || "—")}</td>`).join("")}</tr>`).join("");
  els.compareDialogContent.innerHTML = `<div class="compare-table-wrap"><table class="compare-table"><thead><tr><th>观察维度</th>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`;
  els.compareDialog.showModal();
}

function initialChatMarkup() {
  return `<section class="knowledge-guide message assistant-message" id="knowledgeGuide" role="note" aria-label="知识问答说明"><div class="message-body"><div class="message-copy"><p>本AI教学工具根据权威诊疗指南和防控方案构建知识库，答案基于该权威知识库进行回答。在下方搜索框输入问题，按Enter发送，Shift+Enter换行。</p></div></div></section>`;
}

function messageAtlasGalleryMarkup(diseaseIds = []) {
  const diseases = diseaseIds.map(diseaseById).filter(Boolean);
  const figures = diseases.flatMap((disease) =>
    (disease.images || []).map((item, index) => ({ disease, item, index })),
  ).slice(0, 16);
  if (!figures.length) return "";
  const diseaseNames = diseases.map((disease) => disease.name).join("、");
  const items = figures.map(({ disease, item, index }) => `
    <figure class="message-atlas-item">
      <button type="button" data-lightbox-disease="${escapeHtml(disease.id)}" data-lightbox-index="${index}" aria-label="放大查看${escapeHtml(item.alt || `${disease.name}皮疹`)}">
        <img src="${imageUrl(item.file)}" alt="${escapeHtml(item.alt || `${disease.name}皮疹`)}" loading="lazy" decoding="async">
      </button>
      <figcaption><strong>${escapeHtml(disease.name)}</strong><span>${escapeHtml(item.caption || item.source_label || "皮疹图谱")}</span></figcaption>
    </figure>`).join("");
  return `<section class="message-atlas-gallery" aria-label="${escapeHtml(diseaseNames)}皮疹图谱"><div class="message-atlas-head"><strong>相关皮疹图谱</strong><span>${figures.length} 张 · 横向滑动查看</span></div><div class="message-atlas-track ${figures.length === 1 ? "is-single" : ""}" tabindex="0">${items}</div></section>`;
}

function appendMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  if (options.loading) article.dataset.loading = "true";
  const atlasGallery = role === "assistant" ? messageAtlasGalleryMarkup(options.atlasDiseaseIds) : "";
  const body = options.loading
    ? '<div class="message-loading"><span class="loading-dots" aria-hidden="true"><i></i><i></i><i></i></span><span>正在检索知识库并生成回答…</span></div>'
    : `<div class="message-copy">${structuredAnswer(content)}</div>${atlasGallery}`;
  article.innerHTML = `<div class="message-body">${body}</div>`;
  els.chatFeed.append(article);
  els.chatFeed.scrollTop = els.chatFeed.scrollHeight;
  return article;
}

function updateAssistantLoading(article, label) {
  if (!article.dataset.loading) return;
  const status = $(".message-loading > span:last-child", article);
  if (status) status.textContent = label;
}

function updateAssistantMessage(article, content, options = {}) {
  article.removeAttribute("data-loading");
  const body = $(".message-body", article);
  if (!body) return;
  const atlasGallery = messageAtlasGalleryMarkup(options.atlasDiseaseIds);
  body.innerHTML = `<div class="message-copy">${structuredAnswer(content)}</div>${atlasGallery}`;
  els.chatFeed.scrollTop = els.chatFeed.scrollHeight;
}

async function streamKnowledgeAnswer(messages, onEvent) {
  const response = await fetch("/api/chat/knowledge/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ messages }),
  });
  if (!response.ok) {
    const type = response.headers.get("content-type") || "";
    const data = type.includes("application/json") ? await response.json() : await response.text();
    throw new Error(data?.detail || data?.message || `请求失败（${response.status}）`);
  }
  if (!response.body) throw new Error("当前浏览器不支持流式回答。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  const dispatchBlock = (block) => {
    let event = "message";
    const dataLines = [];
    block.split(/\r?\n/).forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    });
    if (!dataLines.length) return;
    const data = JSON.parse(dataLines.join("\n"));
    if (event === "error") throw new Error(data.detail || "回答生成失败。");
    onEvent?.(event, data);
    if (event === "done") finalData = data;
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    let match = buffer.match(/\r?\n\r?\n/);
    while (match && match.index !== undefined) {
      const block = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0].length);
      if (block.trim()) dispatchBlock(block);
      match = buffer.match(/\r?\n\r?\n/);
    }
    if (done) break;
  }
  if (buffer.trim()) dispatchBlock(buffer);
  if (!finalData) throw new Error("回答流意外中断，请重试。");
  if (typeof finalData.answer !== "string" || !finalData.answer.trim()) {
    throw new Error("AI 未返回有效回答，请重试。");
  }
  return finalData;
}

let knowledgeRequestActive = false;

async function sendKnowledgeQuestion(prompt) {
  const value = prompt.trim();
  if (!value) return;
  if (knowledgeRequestActive) {
    toast("上一条回答仍在生成，请稍候。", true);
    return;
  }
  knowledgeRequestActive = true;
  els.chatForm.setAttribute("aria-busy", "true");
  els.chatInput.disabled = true;
  $("#knowledgeGuide", els.chatFeed)?.remove();
  state.qaMessages.push({ role: "user", content: value });
  appendMessage("user", value);
  els.chatInput.value = "";
  autosize(els.chatInput);
  const submit = $("button[type='submit']", els.chatForm);
  setBusy(submit, true, "正在查证…");
  const loading = appendMessage("assistant", "", { loading: true });
  let liveAnswer = "";
  let liveRenderFrame = null;
  const scheduleLiveRender = () => {
    if (liveRenderFrame !== null) return;
    liveRenderFrame = window.requestAnimationFrame(() => {
      liveRenderFrame = null;
      updateAssistantMessage(loading, liveAnswer.replace(/\s*\[K\d+\]/g, ""));
    });
  };
  try {
    const data = await streamKnowledgeAnswer(state.qaMessages, (event, payload) => {
      if (event === "meta") {
        updateAssistantLoading(loading, "已找到相关资料，正在组织回答…");
        return;
      }
      if (event !== "delta") return;
      liveAnswer += payload.text || "";
      const visibleAnswer = liveAnswer.replace(/\s*\[K\d+\]/g, "").trim();
      if (visibleAnswer) scheduleLiveRender();
    });
    if (liveRenderFrame !== null) window.cancelAnimationFrame(liveRenderFrame);
    liveRenderFrame = null;
    state.qaMessages.push({ role: "assistant", content: data.answer });
    updateAssistantMessage(loading, data.answer);
    if (data.atlas_disease_ids?.length) {
      void ensureAtlas()
        .then(() => updateAssistantMessage(loading, data.answer, { atlasDiseaseIds: data.atlas_disease_ids }))
        .catch(() => {});
    }
  } catch (error) {
    if (liveRenderFrame !== null) window.cancelAnimationFrame(liveRenderFrame);
    liveRenderFrame = null;
    const visibleAnswer = liveAnswer.replace(/\s*\[K\d+\]/g, "").trim();
    if (visibleAnswer) {
      updateAssistantMessage(loading, `${visibleAnswer}\n\n回答生成中断，请重试。`);
    } else {
      loading.remove();
      appendMessage("assistant", `无法完成回答：${errorMessage(error)}`);
    }
    if (state.qaMessages.at(-1)?.role === "user" && state.qaMessages.at(-1)?.content === value) {
      state.qaMessages.pop();
    }
    toast(errorMessage(error), true);
  } finally {
    setBusy(submit, false);
    knowledgeRequestActive = false;
    els.chatForm.setAttribute("aria-busy", "false");
    els.chatInput.disabled = false;
    els.chatInput.focus();
  }
}

function optionMarkup(items = [], group) {
  return items.map((item, index) => `<label class="option-card"><input type="checkbox" name="${group}" value="${escapeHtml(item)}" id="${group}-${index}"><span>${escapeHtml(item)}</span></label>`).join("");
}

function patientMarkup(info = {}) {
  const wideKeys = new Set(["旅行史", "症状", "接触史"]);
  return Object.entries(info).map(([key, value]) => {
    const display = Array.isArray(value) ? value.join("、") : value;
    return `<div class="patient-item ${wideKeys.has(key) ? "is-wide" : ""}"><span>${escapeHtml(key)}</span><strong>${escapeHtml(display)}</strong></div>`;
  }).join("");
}

function renderCases() {
  if (!state.cases.length) {
    els.caseWorkspace.classList.add("is-hidden");
    els.caseEmpty.classList.remove("is-hidden");
    els.caseSelect.innerHTML = "<option>暂无案例</option>";
    els.nextCase.disabled = true;
    return;
  }
  els.caseWorkspace.classList.remove("is-hidden");
  els.caseEmpty.classList.add("is-hidden");
  els.nextCase.disabled = false;
  els.caseSelect.innerHTML = state.cases.map((item, index) => `<option value="${index}">${escapeHtml(item.title)}</option>`).join("");
  els.caseSelect.value = String(state.currentCaseIndex);
  renderCurrentCase();
}

function renderCurrentCase() {
  const current = state.cases[state.currentCaseIndex];
  if (!current) return;
  state.stageIndex = 0;
  state.stageMessages = [];
  els.caseSelect.value = String(state.currentCaseIndex);
  els.caseSequence.textContent = `${String(state.currentCaseIndex + 1).padStart(2, "0")} / ${String(state.cases.length).padStart(2, "0")}`;
  els.caseTitle.textContent = current.title;
  els.caseBackground.textContent = current.background || "暂无背景信息";
  els.patientGrid.innerHTML = patientMarkup(current.patient_info || {});
  els.decisionFeedback.classList.add("is-hidden");
  els.decisionFeedback.innerHTML = "";
  if (current.format === "interactive_v2") {
    els.decisionBoard.classList.remove("is-hidden");
    els.stageBoard.classList.add("is-hidden");
    els.diseaseOptions.innerHTML = optionMarkup(current.options?.possible_diseases, "possible_diseases");
    els.measureOptions.innerHTML = optionMarkup(current.options?.measures, "measures");
    els.treatmentOptions.innerHTML = optionMarkup(current.options?.treatments, "treatments");
    els.decisionForm.reset();
  } else {
    els.decisionBoard.classList.add("is-hidden");
    els.stageBoard.classList.remove("is-hidden");
    renderStage();
  }
}

function selectedValues(name) {
  return $$(`input[name="${name}"]:checked`, els.decisionForm).map((input) => input.value);
}

async function submitDecision(event) {
  event.preventDefault();
  const current = state.cases[state.currentCaseIndex];
  if (!current) return;
  const button = $("button[type='submit']", els.decisionForm);
  setBusy(button, true, "正在分析决策…");
  els.decisionFeedback.classList.remove("is-hidden");
  els.decisionFeedback.innerHTML = '<span class="loading-dots"><i></i><i></i><i></i></span>';
  try {
    const data = await api(`/api/cases/${encodeURIComponent(current.id)}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ possible_diseases: selectedValues("possible_diseases"), measures: selectedValues("measures"), treatments: selectedValues("treatments") }),
    });
    els.decisionFeedback.innerHTML = `<h3>评估反馈</h3><p>${richText(data.feedback)}</p><div class="reference"><strong>参考依据</strong><br>${richText(data.reference_sop)}</div>`;
    els.decisionFeedback.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) {
    els.decisionFeedback.innerHTML = `<h3>反馈未生成</h3><p>${escapeHtml(errorMessage(error))}</p>`;
    toast(errorMessage(error), true);
  } finally {
    setBusy(button, false);
  }
}

function renderStage() {
  const current = state.cases[state.currentCaseIndex];
  const stages = current?.stages || [];
  const stage = stages[state.stageIndex];
  if (!stage) {
    els.stageTitle.textContent = "推演完成";
    els.stageTask.innerHTML = `<strong>参考总结</strong><br>${richText(current?.answers_summary || "本案例已完成。")}`;
    els.stageData.classList.add("is-hidden");
    els.stageForm.classList.add("is-hidden");
    els.nextStage.textContent = "重新开始";
    els.nextStage.dataset.action = "restart";
    return;
  }
  els.stageForm.classList.remove("is-hidden");
  els.nextStage.dataset.action = "next";
  els.nextStage.innerHTML = state.stageIndex === stages.length - 1 ? "完成推演 <span>→</span>" : "进入下一步 <span>→</span>";
  els.stageTitle.textContent = `第 ${stage.step || state.stageIndex + 1} 步 · ${stage.title || "现场任务"}`;
  els.stageTask.innerHTML = `<strong>当前任务</strong><br>${richText(stage.task || "")}`;
  if (stage.data) {
    els.stageData.classList.remove("is-hidden");
    els.stageData.innerHTML = `<strong>参考数据</strong><br>${richText(typeof stage.data === "string" ? stage.data : JSON.stringify(stage.data, null, 2))}`;
  } else {
    els.stageData.classList.add("is-hidden");
  }
  els.stageChat.innerHTML = "";
  state.stageMessages.forEach((message) => appendStageMessage(message.role, message.content));
}

function appendStageMessage(role, content, loading = false) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  if (loading) article.dataset.loading = "true";
  article.innerHTML = `<div class="message-marker"><span></span></div><div class="message-body"><div class="message-meta"><strong>${role === "user" ? "学员" : "案例导师"}</strong><span>${role === "user" ? "处置思路" : "引导反馈"}</span></div>${loading ? '<span class="loading-dots"><i></i><i></i><i></i></span>' : `<p>${richText(content)}</p>`}</div>`;
  els.stageChat.append(article);
  return article;
}

async function submitStageMessage(event) {
  event.preventDefault();
  const value = els.stageInput.value.trim();
  const current = state.cases[state.currentCaseIndex];
  if (!value || !current) return;
  state.stageMessages.push({ role: "user", content: value });
  appendStageMessage("user", value);
  els.stageInput.value = "";
  autosize(els.stageInput);
  const button = $("button[type='submit']", els.stageForm);
  setBusy(button, true, "导师分析中…");
  const loading = appendStageMessage("assistant", "", true);
  try {
    const data = await api(`/api/cases/${encodeURIComponent(current.id)}/coach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage_index: state.stageIndex, messages: state.stageMessages }),
    });
    loading.remove();
    state.stageMessages.push({ role: "assistant", content: data.answer });
    appendStageMessage("assistant", data.answer);
  } catch (error) {
    loading.remove();
    appendStageMessage("assistant", `反馈未生成：${errorMessage(error)}`);
    toast(errorMessage(error), true);
  } finally {
    setBusy(button, false);
  }
}

async function loadAdminContent() {
  const data = await adminApi("/api/admin/content");
  els.adminUnlock.classList.add("is-hidden");
  els.adminDashboard.classList.remove("is-hidden");
  els.adminCaseCount.textContent = `${data.cases.length} 个`;
  els.caseList.innerHTML = data.cases.length
    ? data.cases.map((item) => `<div class="content-row"><div><strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong><small>${escapeHtml(item.id || "未知 ID")}${item.error ? " · 文件损坏" : ""}</small></div><button class="delete-button" type="button" data-delete-case="${escapeHtml(item.filename)}">移除</button></div>`).join("")
    : '<div class="empty-row">案例库目前为空</div>';
}

let atlasLoadPromise = null;
let casesLoadPromise = null;

async function refreshPublicData(force = false) {
  const caseData = await api("/api/cases", force ? { cache: "reload" } : {});
  state.cases = caseData.cases || [];
  state.casesLoaded = true;
  if (state.currentCaseIndex >= state.cases.length) state.currentCaseIndex = 0;
  renderCases();
}

async function loadAtlas() {
  const atlas = await api("/api/rash-atlas");
  state.atlas = atlas;
  state.diseases = flattenAtlas(atlas);
  renderAtlas();
}

function ensureAtlas() {
  if (state.atlas) return Promise.resolve(state.atlas);
  if (!atlasLoadPromise) {
    atlasLoadPromise = loadAtlas()
      .then(() => state.atlas)
      .catch((error) => {
        atlasLoadPromise = null;
        throw error;
      });
  }
  return atlasLoadPromise;
}

function ensureCases() {
  if (state.casesLoaded) return Promise.resolve(state.cases);
  if (!casesLoadPromise) {
    casesLoadPromise = refreshPublicData()
      .then(() => state.cases)
      .catch((error) => {
        casesLoadPromise = null;
        throw error;
      });
  }
  return casesLoadPromise;
}

function bindEvents() {
  $$('[data-view]').forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
    const prefetch = () => {
      if (button.dataset.view === "atlas") void ensureAtlas().catch(() => {});
      if (button.dataset.view === "cases") void ensureCases().catch(() => {});
    };
    button.addEventListener("pointerenter", prefetch, { once: true });
    button.addEventListener("focus", prefetch, { once: true });
  });
  els.menuButton.addEventListener("click", () => openSidebar(!els.sidebar.classList.contains("is-open")));
  els.sidebarScrim.addEventListener("click", () => openSidebar(false));

  els.atlasSearch.addEventListener("input", () => {
    state.atlasQuery = els.atlasSearch.value;
    renderAtlas();
  });
  els.categoryFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-category]");
    if (!button) return;
    state.atlasCategory = button.dataset.category;
    renderAtlas();
  });
  els.morphologyFilters.addEventListener("click", (event) => {
    const button = event.target.closest("[data-morph]");
    if (!button) return;
    state.atlasMorphology = button.dataset.morph;
    renderAtlas();
  });
  els.diseaseGrid.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-open-disease]");
    if (openButton) openDisease(openButton.dataset.openDisease);
  });
  els.diseaseGrid.addEventListener("change", (event) => {
    const input = event.target.closest("[data-compare]");
    if (input) setCompare(input.dataset.compare, input.checked);
  });
  els.clearCompare.addEventListener("click", () => {
    state.compareIds.clear();
    renderCompareDock();
  });
  els.openCompare.addEventListener("click", openComparison);

  els.diseaseDialogContent.addEventListener("click", (event) => {
    const lightbox = event.target.closest("[data-lightbox-disease]");
    if (lightbox) openLightbox(lightbox.dataset.lightboxDisease, Number(lightbox.dataset.lightboxIndex));
    const toggle = event.target.closest("[data-toggle-detail-compare]");
    if (toggle) setCompare(toggle.dataset.toggleDetailCompare, !state.compareIds.has(toggle.dataset.toggleDetailCompare));
  });
  els.chatFeed.addEventListener("click", (event) => {
    const lightbox = event.target.closest("[data-lightbox-disease]");
    if (lightbox) openLightbox(lightbox.dataset.lightboxDisease, Number(lightbox.dataset.lightboxIndex));
  });
  $$('[data-close-dialog]').forEach((button) => button.addEventListener("click", () => $(`#${button.dataset.closeDialog}`)?.close()));
  [els.diseaseDialog, els.compareDialog, els.imageDialog].forEach((dialog) => dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  }));

  els.chatInput.addEventListener("input", () => autosize(els.chatInput));
  els.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendKnowledgeQuestion(els.chatInput.value);
    }
  });
  els.chatForm.addEventListener("submit", (event) => { event.preventDefault(); sendKnowledgeQuestion(els.chatInput.value); });
  $$('[data-prompt]').forEach((button) => button.addEventListener("click", () => sendKnowledgeQuestion(button.dataset.prompt)));
  els.clearChat?.addEventListener("click", () => {
    if (knowledgeRequestActive) {
      toast("请等待当前回答完成后再清空记录。", true);
      return;
    }
    state.qaMessages = [];
    els.chatFeed.innerHTML = initialChatMarkup();
    toast("问答记录已清空");
  });

  els.caseSelect.addEventListener("change", () => { state.currentCaseIndex = Number(els.caseSelect.value); renderCurrentCase(); });
  els.nextCase.addEventListener("click", () => {
    if (!state.cases.length) return;
    state.currentCaseIndex = (state.currentCaseIndex + 1) % state.cases.length;
    renderCurrentCase();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  els.decisionForm.addEventListener("submit", submitDecision);
  els.stageInput.addEventListener("input", () => autosize(els.stageInput));
  els.stageForm.addEventListener("submit", submitStageMessage);
  els.nextStage.addEventListener("click", () => {
    state.stageIndex = els.nextStage.dataset.action === "restart" ? 0 : state.stageIndex + 1;
    state.stageMessages = [];
    renderStage();
  });

  els.adminLoginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.adminPassword = els.adminPassword.value;
    sessionStorage.setItem("adminPassword", state.adminPassword);
    const button = $("button[type='submit']", els.adminLoginForm);
    setBusy(button, true, "验证中…");
    try {
      await loadAdminContent();
      toast("教师身份已验证");
    } catch (error) {
      state.adminPassword = "";
      sessionStorage.removeItem("adminPassword");
      toast(errorMessage(error), true);
    } finally {
      setBusy(button, false);
    }
  });
  els.caseList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-case]");
    if (!button || !confirm("确认移除这个案例？")) return;
    setBusy(button, true, "移除中");
    try {
      const data = await adminApi(`/api/admin/cases/${encodeURIComponent(button.dataset.deleteCase)}`, { method: "DELETE" });
      toast(data.message);
      await Promise.all([loadAdminContent(), refreshPublicData(true)]);
    } catch (error) {
      toast(errorMessage(error), true);
      setBusy(button, false);
    }
  });

  window.addEventListener("hashchange", () => {
    const view = location.hash.slice(1);
    if ($(`#view-${view}`)) switchView(view, false);
  });
}

async function init() {
  const adminRequested = new URLSearchParams(location.search).get("admin") === "true";
  if (adminRequested) els.adminNav.classList.remove("is-hidden");
  els.chatFeed.innerHTML = initialChatMarkup();
  bindEvents();

  if (adminRequested) {
    switchView("admin", false);
    if (state.adminPassword) {
      try {
        await loadAdminContent();
      } catch {
        state.adminPassword = "";
        sessionStorage.removeItem("adminPassword");
      }
    }
  } else {
    const requestedView = location.hash.slice(1);
    if ($(`#view-${requestedView}`)) switchView(requestedView, false);
  }

}

init();

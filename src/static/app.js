const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  config: null,
  cases: [],
  currentCaseIndex: 0,
  qaMessages: [],
  stageIndex: 0,
  stageMessages: [],
  adminPassword: sessionStorage.getItem("adminPassword") || "",
};

const els = {
  sidebar: $("#sidebar"),
  sidebarScrim: $("#sidebarScrim"),
  menuButton: $("#menuButton"),
  topbarTitle: $("#topbarTitle"),
  adminNav: $("#adminNav"),
  aiStatusDot: $("#aiStatusDot"),
  aiStatusText: $("#aiStatusText"),
  modelLabel: $("#modelLabel"),
  knowledgeCount: $("#knowledgeCount"),
  caseCount: $("#caseCount"),
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
  documentList: $("#documentList"),
  caseList: $("#caseList"),
  adminDocCount: $("#adminDocCount"),
  adminCaseCount: $("#adminCaseCount"),
  knowledgeUploadForm: $("#knowledgeUploadForm"),
  knowledgeFile: $("#knowledgeFile"),
  caseGenerateForm: $("#caseGenerateForm"),
  caseSourceFile: $("#caseSourceFile"),
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
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^###\s+(.+)$/gm, "<strong>$1</strong>")
    .replace(/^[-•]\s+(.+)$/gm, "· $1")
    .replace(/\n\n/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

function errorMessage(error) {
  return error?.message || "操作未完成，请稍后重试。";
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `请求失败（${response.status}）`);
  }
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
    button.dataset.original = button.innerHTML;
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

function switchView(viewName) {
  $$(".workspace-view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `view-${viewName}`);
  });
  $$(".nav-item").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.view === viewName);
  });
  const activeView = $(`#view-${viewName}`);
  els.topbarTitle.textContent = activeView?.dataset.title || "教学工作台";
  openSidebar(false);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function initialChatMarkup() {
  return `
    <article class="message assistant-message">
      <div class="message-marker"><span></span></div>
      <div class="message-body">
        <div class="message-meta"><strong>教学助手</strong><span>知识库已就绪</span></div>
        <p>请给我一个具体问题。例如：入境旅客发热并伴有离心性皮疹，现场排查应关注哪些线索？</p>
      </div>
    </article>`;
}

function appendMessage(role, content, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : "assistant-message"}`;
  if (options.loading) article.dataset.loading = "true";
  const body = options.loading
    ? '<span class="loading-dots" aria-label="正在生成回答"><i></i><i></i><i></i></span>'
    : `<p>${richText(content)}</p>${options.showImage ? '<img class="message-image" src="/assets/mpox_rash.png" alt="猴痘皮疹典型临床特征参考图">' : ""}`;
  article.innerHTML = `
    <div class="message-marker"><span></span></div>
    <div class="message-body">
      <div class="message-meta"><strong>${role === "user" ? "学员" : "教学助手"}</strong><span>${role === "user" ? "现场提问" : "知识库反馈"}</span></div>
      ${body}
    </div>`;
  els.chatFeed.append(article);
  els.chatFeed.scrollTop = els.chatFeed.scrollHeight;
  return article;
}

async function sendKnowledgeQuestion(prompt) {
  const value = prompt.trim();
  if (!value) return;

  state.qaMessages.push({ role: "user", content: value });
  appendMessage("user", value);
  els.chatInput.value = "";
  autosize(els.chatInput);
  const submit = $("button[type='submit']", els.chatForm);
  setBusy(submit, true, "正在查证…");
  const loading = appendMessage("assistant", "", { loading: true });

  try {
    const data = await api("/api/chat/knowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.qaMessages }),
    });
    loading.remove();
    state.qaMessages.push({ role: "assistant", content: data.answer });
    appendMessage("assistant", data.answer, { showImage: data.show_mpox_image });
  } catch (error) {
    loading.remove();
    appendMessage("assistant", `无法完成回答：${errorMessage(error)}`);
    toast(errorMessage(error), true);
  } finally {
    setBusy(submit, false);
  }
}

function optionMarkup(items = [], group) {
  return items
    .map(
      (item, index) => `
      <label class="option-card">
        <input type="checkbox" name="${group}" value="${escapeHtml(item)}" id="${group}-${index}">
        <span>${escapeHtml(item)}</span>
      </label>`,
    )
    .join("");
}

function patientMarkup(info = {}) {
  const wideKeys = new Set(["旅行史", "症状", "接触史"]);
  return Object.entries(info)
    .map(([key, value]) => {
      const display = Array.isArray(value) ? value.join("、") : value;
      return `<div class="patient-item ${wideKeys.has(key) ? "is-wide" : ""}"><span>${escapeHtml(key)}</span><strong>${escapeHtml(display)}</strong></div>`;
    })
    .join("");
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
  els.caseSelect.innerHTML = state.cases
    .map((item, index) => `<option value="${index}">${escapeHtml(item.title)}</option>`)
    .join("");
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
      body: JSON.stringify({
        possible_diseases: selectedValues("possible_diseases"),
        measures: selectedValues("measures"),
        treatments: selectedValues("treatments"),
      }),
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
  article.innerHTML = `
    <div class="message-marker"><span></span></div>
    <div class="message-body">
      <div class="message-meta"><strong>${role === "user" ? "学员" : "案例导师"}</strong><span>${role === "user" ? "处置思路" : "引导反馈"}</span></div>
      ${loading ? '<span class="loading-dots"><i></i><i></i><i></i></span>' : `<p>${richText(content)}</p>`}
    </div>`;
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
  els.adminDocCount.textContent = `${data.documents.length} 份`;
  els.adminCaseCount.textContent = `${data.cases.length} 个`;
  els.documentList.innerHTML = data.documents.length
    ? data.documents.map((doc) => `
        <div class="content-row">
          <div><strong title="${escapeHtml(doc.name)}">${escapeHtml(doc.name)}.md</strong><small>${doc.characters.toLocaleString()} 字符</small></div>
          <button class="delete-button" type="button" data-delete-doc="${escapeHtml(doc.name)}">移除</button>
        </div>`).join("")
    : '<div class="empty-row">知识库目前为空</div>';
  els.caseList.innerHTML = data.cases.length
    ? data.cases.map((item) => `
        <div class="content-row">
          <div><strong title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</strong><small>${escapeHtml(item.id || "未知 ID")}${item.error ? " · 文件损坏" : ""}</small></div>
          <button class="delete-button" type="button" data-delete-case="${escapeHtml(item.filename)}">移除</button>
        </div>`).join("")
    : '<div class="empty-row">案例库目前为空</div>';
}

async function refreshPublicData() {
  const [config, caseData] = await Promise.all([api("/api/config"), api("/api/cases")]);
  state.config = config;
  state.cases = caseData.cases || [];
  if (state.currentCaseIndex >= state.cases.length) state.currentCaseIndex = 0;
  updateConfig(config);
  renderCases();
}

function updateConfig(config) {
  els.aiStatusDot.classList.toggle("is-ready", config.ai_configured);
  els.aiStatusDot.classList.toggle("is-error", !config.ai_configured);
  els.aiStatusText.textContent = config.ai_configured ? "AI 服务已连接" : "等待配置 API Key";
  els.modelLabel.textContent = config.model || "MODEL UNSET";
  els.knowledgeCount.textContent = config.knowledge_count ?? "—";
  els.caseCount.textContent = config.case_count ?? "—";
}

async function uploadAdminFile(form, input, endpoint, busyLabel) {
  const file = input.files?.[0];
  if (!file) return;
  const button = $("button[type='submit']", form);
  const formData = new FormData();
  formData.append("file", file);
  setBusy(button, true, busyLabel);
  try {
    const data = await adminApi(endpoint, { method: "POST", body: formData });
    toast(data.message);
    form.reset();
    await Promise.all([loadAdminContent(), refreshPublicData()]);
  } catch (error) {
    toast(errorMessage(error), true);
  } finally {
    setBusy(button, false);
  }
}

function bindEvents() {
  $$(".nav-item").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  els.menuButton.addEventListener("click", () => openSidebar(!els.sidebar.classList.contains("is-open")));
  els.sidebarScrim.addEventListener("click", () => openSidebar(false));

  els.chatInput.addEventListener("input", () => autosize(els.chatInput));
  els.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    sendKnowledgeQuestion(els.chatInput.value);
  });
  $$("[data-prompt]").forEach((button) => button.addEventListener("click", () => sendKnowledgeQuestion(button.dataset.prompt)));
  els.clearChat.addEventListener("click", () => {
    state.qaMessages = [];
    els.chatFeed.innerHTML = initialChatMarkup();
    toast("问答记录已清空");
  });

  els.caseSelect.addEventListener("change", () => {
    state.currentCaseIndex = Number(els.caseSelect.value);
    renderCurrentCase();
  });
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
    if (els.nextStage.dataset.action === "restart") {
      state.stageIndex = 0;
    } else {
      state.stageIndex += 1;
    }
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

  els.knowledgeUploadForm.addEventListener("submit", (event) => {
    event.preventDefault();
    uploadAdminFile(els.knowledgeUploadForm, els.knowledgeFile, "/api/admin/knowledge", "正在处理文档…");
  });
  els.caseGenerateForm.addEventListener("submit", (event) => {
    event.preventDefault();
    uploadAdminFile(els.caseGenerateForm, els.caseSourceFile, "/api/admin/cases/generate", "正在生成案例…");
  });

  els.documentList.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-doc]");
    if (!button || !confirm(`确认移除《${button.dataset.deleteDoc}》？`)) return;
    setBusy(button, true, "移除中");
    try {
      const data = await adminApi(`/api/admin/knowledge/${encodeURIComponent(button.dataset.deleteDoc)}`, { method: "DELETE" });
      toast(data.message);
      await Promise.all([loadAdminContent(), refreshPublicData()]);
    } catch (error) {
      toast(errorMessage(error), true);
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
      await Promise.all([loadAdminContent(), refreshPublicData()]);
    } catch (error) {
      toast(errorMessage(error), true);
      setBusy(button, false);
    }
  });
}

async function init() {
  const adminRequested = new URLSearchParams(location.search).get("admin") === "true";
  if (adminRequested) {
    els.adminNav.classList.remove("is-hidden");
  }
  bindEvents();
  try {
    await refreshPublicData();
  } catch (error) {
    els.aiStatusDot.classList.add("is-error");
    els.aiStatusText.textContent = "服务状态异常";
    toast(errorMessage(error), true);
  }

  if (adminRequested) {
    switchView("admin");
    if (state.adminPassword) {
      try {
        await loadAdminContent();
      } catch {
        state.adminPassword = "";
        sessionStorage.removeItem("adminPassword");
      }
    }
  }
}

init();

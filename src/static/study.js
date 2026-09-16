/* Student records and scoring live on the server. No answer keys in this bundle. */
window.Study = (() => {
  const find = s => document.querySelector(s);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const phaseName = p => p === "pre" ? "前测" : "后测";
  let hooks, session = null, paper = null, answers = {}, saved = "{}", saving = Promise.resolve(), timer, showing = false, busy = false, lastVisit = "";
  let learningTickAt = 0, learningHeartbeatBusy = false, reminderQueue = [], activeReminder = null;
  const root = () => find("#assessmentRoot");
  const message = (text, bad = false) => hooks.toast(text, bad);
  const notice = text => `<p class="study-notice">${text}</p>`;
  const button = (action, text, secondary = false) => `<button type="button" class="${secondary ? "line-button" : "solid-button"}" data-study-action="${action}">${text}</button>`;
  const sections = [
    { id: "basic", label: "基础知识", code: "BASIC KNOWLEDGE" },
    { id: "rash", label: "皮疹辨别", code: "RASH IDENTIFICATION" },
    { id: "case", label: "模拟案例", code: "CLINICAL CASES" },
  ];
  const sectionFor = q => sections.some(s => s.id === q.section) ? q.section : q.case_id ? "case" : "basic";
  const pointsOf = questions => questions.reduce((sum, q) => sum + (Number(q.points) || 0), 0);
  const paperTotal = value => value.total ?? pointsOf(value.questions);
  const resultTotal = result => result.total ?? Object.values(result.sections || result.breakdown || {}).reduce((sum, data) => sum + (Number(data.total) || 0), 0);
  const answered = q => q.options.some(option => option.id === answers[q.id]);
  function sectionStats(questions) {
    const points = [...new Set(questions.map(q => Number(q.points)))];
    return `${questions.length}小题 · ${pointsOf(questions)}分${points.length === 1 ? ` · 每小题${points[0]}分` : ""}`;
  }
  function paperSummary(value) {
    return sections.map(s => {
      const questions = value.questions.filter(q => sectionFor(q) === s.id);
      return questions.length ? `${s.label}${questions.length}小题` : "";
    }).filter(Boolean).join(" · ") + `；共${value.questions.length}小题，${paperTotal(value)}分`;
  }
  function scoreTable(results, field = "sections") {
    const keys = [...new Set(results.flatMap(r => Object.keys(r[field] || {})))];
    if (field === "sections") keys.sort((a, b) => sections.findIndex(s => s.id === a) - sections.findIndex(s => s.id === b));
    if (!keys.length) return "";
    const title = field === "sections" ? "模块得分" : "知识维度得分";
    return `<div class="study-table-wrap study-score-table"><table><caption>${title}</caption><thead><tr><th scope="col">${field === "sections" ? "测验模块" : "知识维度"}</th>${results.map(r => `<th scope="col">${phaseName(r.phase)}</th>`).join("")}</tr></thead><tbody>${keys.map(key => {
      const label = field === "sections" ? results.map(r => r[field]?.[key]?.label).find(Boolean) || sections.find(s => s.id === key)?.label || key : key;
      return `<tr><th scope="row">${esc(label)}</th>${results.map(r => {
        const data = r[field]?.[key];
        return `<td>${data ? `${esc(data.score)} / ${esc(data.total)}` : "—"}</td>`;
      }).join("")}</tr>`;
    }).join("")}</tbody></table></div>`;
  }
  function safeUrl(value) {
    if (!value) return "";
    try {
      const url = new URL(value, location.href);
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch { return ""; }
  }
  function imageSourceMarkup(source) {
    if (!source) return "";
    const metadata = [source.provider, source.source_label, source.license].filter(Boolean).map(esc).join(" · ");
    const links = (Array.isArray(source.links) ? source.links : []).map(link => {
      const url = safeUrl(link.url);
      return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(link.label || "查看来源")}</a>` : "";
    }).filter(Boolean).join(" · ");
    return `<details class="exam-image-source"><summary>图片出处与许可</summary>${metadata ? `<p>${metadata}</p>` : ""}${source.caption ? `<p>${esc(source.caption)}</p>` : ""}${links ? `<p>${links}</p>` : ""}</details>`;
  }
  function previewImagePassword(url) {
    if (!url) return "";
    const parsed = new URL(url);
    return parsed.origin === location.origin && /^\/api\/admin\/study\/papers\/[AB]\/image\/[^/]+$/.test(parsed.pathname) ? sessionStorage.getItem("adminPassword") || "" : "";
  }
  function imageMarkup(q, enlarged = false) {
    if (!q.image_url) return "";
    const url = safeUrl(q.image_url);
    const image = `<img data-exam-image-url="${esc(url)}" ${url && !previewImagePassword(url) ? `src="${esc(url)}"` : ""} alt="${esc(q.image_alt || "皮损观察图片")}" loading="eager" decoding="async">`;
    return `<figure class="exam-image" data-exam-image="loading">${enlarged ? `<div class="exam-image-large">${image}</div>` : `<button type="button" class="exam-image-button" data-exam-image-action="zoom" aria-label="放大查看皮损图片" disabled>${image}</button>`}<figcaption><span data-exam-image-status role="status">图片加载中…</span><button type="button" class="line-button" data-exam-image-action="retry" hidden>重新加载图片</button></figcaption></figure>`;
  }
  function bindImages(container) {
    container.querySelectorAll("[data-exam-image]").forEach(figure => {
      const img = figure.querySelector("img");
      if (img.dataset.examImageBound) return;
      img.dataset.examImageBound = "true";
      let blobUrl;
      const update = loaded => {
        if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
        if (!img.isConnected) return;
        figure.dataset.examImage = loaded ? "loaded" : "error";
        if (loaded) figure.closest(".exam-question")?.classList.remove("is-image-missing");
        figure.querySelector("[data-exam-image-status]").textContent = loaded ? (figure.closest("dialog") ? "可滚动查看图片细节" : "点击图片可放大观察") : "图片加载失败，请重试。";
        figure.querySelector('[data-exam-image-action="retry"]').hidden = loaded;
        const zoom = figure.querySelector('[data-exam-image-action="zoom"]');
        if (zoom) zoom.disabled = !loaded;
      };
      img.onload = () => update(img.naturalWidth > 0);
      img.onerror = () => update(false);
      const url = safeUrl(img.dataset.examImageUrl);
      if (!url) { update(false); return; }
      const password = previewImagePassword(url);
      if (password) {
        // Image elements cannot send the legacy faculty password header themselves.
        void fetch(url, { credentials: "same-origin", cache: "no-store", headers: { "X-Admin-Password": password } })
          .then(response => {
            if (!response.ok) throw new Error("图片加载失败");
            return response.blob();
          }).then(blob => {
            if (!img.isConnected) return;
            blobUrl = URL.createObjectURL(blob);
            img.src = blobUrl;
          }).catch(() => update(false));
        return;
      }
      // Eager loading and a retained success state also cover images outside the viewport.
      if (img.complete) update(img.naturalWidth > 0);
    });
  }
  function initImages() {
    const dialog = find("#examImageDialog");
    document.addEventListener("click", event => {
      const target = event.target.closest("[data-exam-image-action]");
      if (!target || target.disabled) return;
      const action = target.dataset.examImageAction;
      if (action === "close") { dialog.close(); return; }
      const figure = target.closest("[data-exam-image]");
      const img = figure.querySelector("img");
      if (action === "zoom") {
        if (figure.dataset.examImage !== "loaded") return;
        find("#examImageContent").innerHTML = imageMarkup({ image_url: img.dataset.examImageUrl, image_alt: img.alt }, true);
        dialog.showModal();
        bindImages(dialog);
      } else if (action === "retry") {
        const url = safeUrl(img.dataset.examImageUrl);
        if (!url) { message("图片地址暂不可用，请重新载入试卷。", true); return; }
        const retryUrl = new URL(url);
        retryUrl.searchParams.set("_retry", String(Date.now()));
        const next = img.cloneNode();
        delete next.dataset.examImageBound;
        next.dataset.examImageUrl = retryUrl.href;
        if (previewImagePassword(retryUrl.href)) next.removeAttribute("src");
        else next.src = retryUrl.href;
        figure.dataset.examImage = "loading";
        figure.querySelector("[data-exam-image-status]").textContent = "图片重新加载中…";
        target.hidden = true;
        img.replaceWith(next);
        bindImages(figure.parentElement);
      }
    });
    dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => { find("#examImageContent").replaceChildren(); });
  }

  async function request(path, method = "GET", body) {
    const response = await fetch(path, { method, cache: "no-store", credentials: "same-origin", headers: body ? { "Content-Type": "application/json" } : {}, ...(body ? { body: JSON.stringify(body) } : {}) });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401 && path !== "/api/session/login") loginScreen();
      const error = new Error(typeof data.detail === "string" ? data.detail : "提交内容不完整，请检查后重试。");
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function signal() { try { localStorage.setItem("study-session-change", String(Date.now())); } catch {} }
  function loginScreen() {
    session = null;
    document.body.dataset.auth = "login";
    find("#studentLoginForm button").disabled = false;
    find("#studentLoginForm button").textContent = "登录并继续";
  }
  function updateSession(data) {
    session = data;
    if (!data.authenticated) { loginScreen(); return; }
    document.body.dataset.auth = "ready";
    find("#studentProfile").classList.remove("is-hidden");
    find("#studentProfile").classList.toggle("is-faculty", isTeacher());
    find("#studentAvatar").textContent = data.student.name.slice(0, 1);
    find("#studentRoleLabel").textContent = isTeacher() ? "FACULTY ACCESS" : "STUDENT ACCESS";
    find("#studentIdentity").textContent = data.student.name;
    find("#studentNumberLabel").textContent = `NO. ${data.student.student_no}`;
    find("#studentStage").textContent = isTeacher() ? "教师身份 · 无需参加前测" : data.post_completed ? "前后测已完成" : data.pre_completed ? "前测已完成 · 学习中" : "请先完成首次前测";
    find("#adminNav").classList.toggle("is-hidden", !isTeacher());
    document.querySelectorAll('[data-view="knowledge"], [data-view="atlas"], [data-view="cases"]').forEach(el => {
      el.classList.toggle("study-locked", !canLearn());
      el.setAttribute("aria-disabled", String(!canLearn()));
    });
  }
  const isTeacher = () => session?.role === "teacher";
  const canLearn = () => !!(session?.authenticated && (isTeacher() || (session.pre_completed && session.active?.phase !== "post")));
  function showNextReminder() {
    const dialog = find("#studyReminderDialog");
    if (!dialog || dialog.open || !reminderQueue.length) return;
    activeReminder = reminderQueue.shift();
    find("#studyReminderKicker").textContent = activeReminder.kicker;
    find("#studyReminderRoute").textContent = activeReminder.route;
    find("#studyReminderTitle").textContent = activeReminder.title;
    find("#studyReminderCopy").textContent = activeReminder.copy;
    find("#studyReminderPrimary").textContent = activeReminder.primary;
    find("#studyReminderSecondary").textContent = activeReminder.secondary || "稍后";
    dialog.showModal();
    find("#studyReminderPrimary").focus();
  }
  function queueReminder(reminder) {
    reminderQueue.push(reminder);
    showNextReminder();
  }
  function navigationReminder() {
    queueReminder({
      kicker: "LEARNING GUIDE · 前测完成",
      route: "01  知识问答   ·   02  皮疹图谱   ·   03  情景演练   ·   04  知识测验",
      title: "现在可以开始学习",
      copy: "点击页面左上角的菜单按钮，即可在不同学习板块之间切换。建议结合知识问答、皮疹图谱和情景演练进行学习。",
      primary: "进入知识问答",
      secondary: "留在成绩页",
      view: "knowledge",
    });
  }
  function postReminderIfNeeded(data) {
    if (!data?.post_open || !data.pre_completed || data.post_completed || data.active?.phase === "post") return;
    const noticeId = data.post_open_notice_id || `${data.post_open_reason || "open"}:default`;
    const identity = `${data.student?.student_no || ""}:${data.student?.name || ""}`;
    const storageKey = `study-post-reminder:${identity}`;
    try {
      if (localStorage.getItem(storageKey) === noticeId) return;
      localStorage.setItem(storageKey, noticeId);
    } catch {}
    const automatic = data.post_open_reason === "time";
    queueReminder({
      kicker: automatic ? "POST-ASSESSMENT · 学习满30分钟" : "POST-ASSESSMENT · 教师已发放",
      route: "04  知识测验   →   后测",
      title: "后测已经开放",
      copy: automatic ? "你已累计完成30分钟有效学习，请前往知识测验独立完成后测。" : "教师已向完成前测的学生发放后测，请前往知识测验独立完成。",
      primary: "去完成后测",
      secondary: "稍后完成",
      view: "assessment",
    });
  }
  function activeLearningModule() {
    return ["knowledge", "atlas", "cases"].find(view => find(`#view-${view}`)?.classList.contains("is-active")) || "";
  }
  function pushPostIfOpened(previous, data) {
    if (!previous?.post_open || previous.post_open_notice_id !== data.post_open_notice_id) postReminderIfNeeded(data);
  }
  async function learningHeartbeat(reset = false) {
    const module = activeLearningModule();
    const eligible = session?.authenticated && !isTeacher() && session.pre_completed && !session.post_completed && session.active?.phase !== "post";
    if (!eligible || !module || document.hidden || !document.hasFocus()) { learningTickAt = 0; return; }
    const now = Date.now();
    const seconds = reset || !learningTickAt ? 0 : Math.min(20, Math.max(0, (now - learningTickAt) / 1000));
    learningTickAt = now;
    if (learningHeartbeatBusy) return;
    learningHeartbeatBusy = true;
    try {
      const previous = session;
      const data = await request("/api/study/heartbeat", "POST", { module, seconds });
      updateSession(data);
      pushPostIfOpened(previous, data);
    } catch (error) {
      if (error.status === 401 || error.status === 403) learningTickAt = 0;
    } finally { learningHeartbeatBusy = false; }
  }
  function guard(view) {
    if (!session?.authenticated) { loginScreen(); return null; }
    if (isTeacher()) return view === "assessment" ? "admin" : view;
    if (view === "admin") return session.pre_completed ? "knowledge" : "assessment";
    if (view !== "assessment" && !canLearn()) {
      message(session.active?.phase === "post" ? "请先完成正在进行的后测。" : "首次使用请先完成04知识测验。", true);
      return "assessment";
    }
    return view;
  }
  function visit(view) {
    if (canLearn() && !isTeacher() && ["knowledge", "atlas", "cases"].includes(view) && lastVisit !== view) {
      lastVisit = view;
      void request("/api/study/visit", "POST", { module: view }).catch(() => {});
    }
    learningTickAt = 0;
    void learningHeartbeat(true);
  }
  async function init(config) {
    hooks = config;
    initImages();
    find("#studentLoginForm").addEventListener("submit", async event => {
      event.preventDefault();
      const submit = find("#studentLoginForm button");
      submit.disabled = true;
      find("#studentLoginError").textContent = "";
      try {
        const data = await request("/api/session/login", "POST", { student_no: find("#studentNumber").value, name: find("#studentName").value });
        updateSession(data);
        signal();
        hooks.switchView(isTeacher() ? "admin" : session.pre_completed ? "knowledge" : "assessment");
        pushPostIfOpened(null, data);
      } catch (error) { find("#studentLoginError").textContent = error.message; }
      finally { submit.disabled = false; }
    });
    find("#studentLogout").addEventListener("click", async () => {
      try { await flush(); await request("/api/session/logout", "POST"); signal(); location.replace("/"); }
      catch (error) { message(error.message, true); }
    });
    const reminderDialog = find("#studyReminderDialog");
    find("#studyReminderSecondary").addEventListener("click", () => reminderDialog.close());
    find("#studyReminderPrimary").addEventListener("click", () => {
      const view = activeReminder?.view;
      reminderDialog.close();
      if (view) hooks.switchView(view);
    });
    reminderDialog.addEventListener("close", () => {
      activeReminder = null;
      setTimeout(showNextReminder, 0);
    });
    root().addEventListener("change", event => {
      if (!event.target.matches('input[data-question]') || busy) return;
      answers[event.target.dataset.question] = event.target.value;
      event.target.closest(".exam-question").classList.remove("is-missing");
      progress("正在保存…");
      clearTimeout(timer);
      timer = setTimeout(() => flush().catch(error => progress(error.message, true)), 350);
    });
    root().addEventListener("click", async event => {
      const target = event.target.closest("[data-study-action]");
      if (!target || busy) return;
      const action = target.dataset.studyAction;
      if (action === "learn") { hooks.switchView("knowledge"); return; }
      if (action === "post-confirm") { find("#postConfirmation").hidden = false; find("#postConfirmation button").focus(); return; }
      target.disabled = true;
      try {
        if (["pre", "post"].includes(action)) {
          paper = await request("/api/assessments/start", "POST", { phase: action });
          updateSession(await request("/api/session"));
          signal();
          renderPaper();
        } else if (action === "submit") await submit();
        else if (action === "retry-save") await flush();
        else if (action === "refresh") await show(true);
        else if (action === "review") await review();
      } catch (error) { message(error.message, true); progress(error.message, true); }
      finally { target.disabled = false; }
    });
    window.addEventListener("storage", event => { if (event.key === "study-session-change") location.reload(); });
    window.addEventListener("beforeunload", event => {
      if (paper && !paper.submitted && JSON.stringify(answers) !== saved) { event.preventDefault(); event.returnValue = ""; }
    });
    const sync = async () => {
      if (!session?.authenticated || document.hidden || busy) return;
      try {
        const previous = session;
        const data = await request("/api/session");
        const changed = data.active?.id !== session.active?.id || data.pre_completed !== session.pre_completed || data.post_completed !== session.post_completed || data.post_open !== session.post_open;
        updateSession(data);
        pushPostIfOpened(previous, data);
        if (!data.authenticated) return;
        if (!canLearn() && !find("#view-assessment").classList.contains("is-active")) hooks.switchView("assessment");
        else if (changed && find("#view-assessment").classList.contains("is-active")) await show();
      } catch {}
    };
    window.addEventListener("focus", () => { void sync(); void learningHeartbeat(true); });
    window.addEventListener("blur", () => { learningTickAt = 0; });
    setInterval(sync, 30000);
    setInterval(() => void learningHeartbeat(), 15000);
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) { learningTickAt = 0; if (paper) void flush().catch(() => {}); }
      else { void sync(); void learningHeartbeat(true); }
    });
    try {
      const data = await request("/api/session");
      updateSession(data);
      pushPostIfOpened(null, data);
    }
    catch (error) { loginScreen(); find("#studentLoginError").textContent = error.message || "暂时无法连接，请稍后重新登录。"; }
  }
  async function show(force = false) {
    if (showing || !session?.authenticated) return;
    showing = true;
    try {
      const data = await request("/api/session");
      const previous = session;
      updateSession(data);
      pushPostIfOpened(previous, data);
      if (!session?.authenticated) return;
      if (session.active) {
        if (!force && paper?.id === session.active.id && find("#assessmentForm")) return;
        paper = await request(`/api/assessments/${session.active.id}`);
        renderPaper();
      } else { paper = null; dashboard(); if (session.pre_completed) await review(); }
    } catch (error) { root().innerHTML = `<section class="study-card"><h2>测验暂时无法载入</h2><p>${esc(error.message)}</p>${button("refresh", "重新载入")}</section>`; }
    finally { showing = false; }
  }
  function dashboard() {
    const intro = `<div class="study-heading"><span class="section-code">04 / KNOWLEDGE ASSESSMENT</span><h1>记录起点，检验进步。</h1><p>两次测验围绕相同知识点，使用不同设问与临床情景。</p></div>`;
    const stats = `<div class="exam-specs"><div><strong>60<small>分</small></strong><span>一、基础知识 · 20小题 × 3分</span></div><div><strong>16<small>分</small></strong><span>二、皮疹辨别 · 8小题 × 2分<br>前4题文字，后4题图片</span></div><div><strong>24<small>分</small></strong><span>三、模拟案例 · 8小题 × 3分<br>2个案例，各4小题</span></div></div>`;
    let content;
    if (!session.pre_completed) content = `<span class="study-pill">首次使用 · 必须完成</span><h2>先独立完成前测</h2><p>测验分为基础知识、皮疹辨别和模拟案例三节，共36个单选小题，总分100分。请按当前掌握程度作答，不查阅资料或使用AI。</p><p>答案会自动保存，可以中断后继续；完成全部题目并提交即可进入学习，不要求达到及格分数。图片可点击放大，请确认图片加载成功后提交。</p>${notice("提交后立即显示成绩、各模块得分与逐题解析，可从解析一键进入知识问答继续提问。提交后不能重做，请核对学号和姓名。")}${button("pre", "开始前测 →")}`;
    else if (!session.post_completed) {
      const pre = session.results.find(r => r.phase === "pre");
      const targetMinutes = Math.round((session.auto_post_seconds || 1800) / 60);
      const remainingMinutes = Math.max(1, Math.ceil((session.auto_post_remaining || 0) / 60));
      const availability = session.post_open ? (session.post_open_reason === "time" ? `已累计有效学习${targetMinutes}分钟，后测现已开放，请独立作答。` : "教师已开放后测，请完成学习后独立作答。") : `知识问答、皮疹图谱和情景演练均已开放。累计有效学习${targetMinutes}分钟后将自动开放后测，目前约剩${remainingMinutes}分钟；教师也可提前统一开放。`;
      content = `<span class="study-pill">前测已完成</span><h2>你的前测成绩</h2><div class="pre-score score-specs"><strong>${pre.score}<small> / ${resultTotal(pre)}</small></strong><p>下方已展开逐题解析。每题都可以进入知识问答继续提问。</p></div>${scoreTable([pre])}${scoreTable([pre], "breakdown")}<p>${availability}</p><div class="study-actions">${button("learn", "进入知识问答", true)}${button("review", "查看逐题解析", true)}${session.post_open ? button("post-confirm", "准备开始后测") : button("refresh", "刷新开放状态", true)}</div><div id="postConfirmation" class="study-confirmation" hidden><strong>确认已完成本阶段学习？</strong><p>开始后测后，本站学习模块与前测解析将暂时锁定，提交全部答案后恢复。后测只能提交一次。</p>${button("post", "确认开始后测")}</div>${notice("成绩和作答已保存，以后使用同一姓名与学号登录可继续复习。")}`;
    }
    else {
      const pre = session.results.find(r => r.phase === "pre"), post = session.results.find(r => r.phase === "post");
      content = `<span class="study-pill">两次测验已完成</span><h2>你的学习记录</h2><div class="exam-specs score-specs"><div><strong>${pre.score}</strong><span>前测 / ${resultTotal(pre)}</span></div><div><strong>${post.score}</strong><span>后测 / ${resultTotal(post)}</span></div><div><strong>${post.score - pre.score > 0 ? "+" : ""}${post.score - pre.score}</strong><span>分数变化</span></div></div>${scoreTable([pre, post])}${scoreTable([pre, post], "breakdown")}<div class="study-actions">${button("review", "查看答案与解析", true)}${button("learn", "继续学习 →")}</div>${notice("分数变化用于帮助回顾学习，不能单凭个人前后测成绩判定AI工具的因果效果。")}`;
    }
    root().innerHTML = `${intro}${session.pre_completed ? "" : stats}<section class="study-card">${content}</section><div id="assessmentReview"></div>`;
  }
  function questionMarkup(q, index, reviewMode, value) {
    const selected = (reviewMode ? value.answers || {} : answers)[q.id];
    const correct = q.options.find(o => o.id === q.correct)?.text || "";
    const chosen = q.options.find(o => o.id === selected)?.text || "未作答";
    const scope = reviewMode ? `review-${value.id || value.form}-` : "";
    const background = (value.cases || []).find(c => c.id === q.case_id)?.background || "";
    const prompt = `我正在复习${q.disease || "传染病"}的“${q.point}”。${background ? `案例：${background}\n` : ""}题目：${q.stem}\n我的答案：${chosen}。参考答案：${correct}。请结合临床证据解释判断过程，并说明与其他选项（${q.options.filter(o => o.id !== q.correct).map(o => o.text).join("；")}）的区别。`;
    return `<fieldset class="exam-question" id="exam-${esc(scope + q.id)}" tabindex="-1"><legend><span class="question-number">${index}.</span>${esc(q.stem)} <small>${q.image_url ? "看图单选" : "单选"}</small></legend>${imageMarkup(q)}<div class="exam-options">${q.options.map((o, n) => `<label class="exam-option"><input type="radio" name="${esc(scope + q.id)}" data-question="${esc(q.id)}" value="${esc(o.id)}" ${selected === o.id ? "checked" : ""} ${reviewMode ? "disabled" : ""}><span><b>${String.fromCharCode(65 + n)}</b>${esc(o.text)}</span></label>`).join("")}</div>${reviewMode ? `<div class="exam-explanation"><strong>${selected ? selected === q.correct ? "回答正确" : "需复习" : "参考解析"} · 正确答案：${esc(correct)}</strong>${selected ? `<p>你的答案：${esc(chosen)}</p>` : ""}<p>${esc(q.explanation)}</p><small>知识点：${esc(q.point)} · ${(q.sources || []).map(s => esc(s.document)).filter((v, i, a) => a.indexOf(v) === i).join("；")}</small>${imageSourceMarkup(q.image_source)}${!isTeacher() ? `<div class="study-actions"><button type="button" class="line-button" data-knowledge-question="${esc(prompt)}">去知识问答提问</button></div>` : ""}</div>` : ""}</fieldset>`;
  }
  function paperMarkup(value, reviewMode = false) {
    return sections.map(section => ({ ...section, questions: value.questions.filter(q => sectionFor(q) === section.id) }))
      .filter(section => section.questions.length).map((section, index) => {
        const title = `<div class="exam-section-title"><span class="section-code">PART ${String(index + 1).padStart(2, "0")} / ${section.code}</span><h2>${["一", "二", "三"][index]}、${section.label}</h2><span>${sectionStats(section.questions)}</span></div>`;
        if (section.id === "case") {
          const groups = [...new Set(section.questions.map(q => q.case_id))];
          return `<section class="exam-section" data-exam-section="case">${title}${groups.map((id, i) => {
            const c = (value.cases || []).find(item => item.id === id);
            const questions = section.questions.filter(q => q.case_id === id);
            return `<section class="study-card"><div class="exam-case-stem"><span class="section-code">CLINICAL CASE ${i + 1} / ${sectionStats(questions)}</span><h3>${esc(c?.title || `案例 ${i + 1}`)}</h3>${c?.background ? `<p>${esc(c.background)}</p>` : ""}</div>${questions.map((q, j) => questionMarkup(q, j + 1, reviewMode, value)).join("")}</section>`;
          }).join("")}</section>`;
        }
        // Keep the server's order within each question type; text precedes images in the rash section.
        const questions = section.id === "rash" ? [...section.questions.filter(q => !q.image_url), ...section.questions.filter(q => q.image_url)] : section.questions;
        return `<section class="study-card" data-exam-section="${section.id}">${title}${questions.map((q, i) => {
          const subheading = section.id === "rash" && (i === 0 || !!q.image_url !== !!questions[i - 1].image_url) ? `<h3 class="exam-question-group">${q.image_url ? "图片辨别" : "文字辨别"} · ${questions.filter(item => !!item.image_url === !!q.image_url).length}小题</h3>` : "";
          return subheading + questionMarkup(q, i + 1, reviewMode, value);
        }).join("")}</section>`;
      }).join("");
  }
  function renderPaper() {
    answers = { ...paper.answers }; saved = JSON.stringify(answers);
    root().innerHTML = `<div class="study-heading"><span class="section-code">KNOWLEDGE ASSESSMENT / ${paper.phase.toUpperCase()}</span><h1>${phaseName(paper.phase)}</h1><p>${paperSummary(paper)}。<br>请独立作答。每题只有一个最佳答案，提交后不可更改。</p></div><div class="exam-progress"><label for="examProgress" id="examCount"></label><progress id="examProgress" max="${paper.questions.length}" value="0"></progress><span id="examSaveStatus" role="status"></span><button class="text-button" type="button" data-study-action="retry-save">保存进度</button></div><form id="assessmentForm" onsubmit="return false">${paperMarkup(paper)}<div class="study-card exam-submit"><div><strong>已检查全部答案？</strong><p>完成全部${paper.questions.length}个小题${paper.questions.some(q => q.image_url) ? "，确认题目图片均已成功加载" : ""}后提交。</p></div>${button("submit", `提交${phaseName(paper.phase)}`)}</div></form>`;
    bindImages(root());
    progress("进度已保存");
  }
  function progress(text, error = false) {
    const count = paper?.questions.filter(answered).length || 0;
    if (find("#examCount")) find("#examCount").textContent = `已答 ${count} / ${paper.questions.length} 小题`;
    if (find("#examProgress")) { find("#examProgress").max = paper.questions.length; find("#examProgress").value = count; }
    if (find("#examSaveStatus")) { find("#examSaveStatus").textContent = text; find("#examSaveStatus").classList.toggle("study-error", error); }
  }
  function flush() {
    clearTimeout(timer);
    saving = saving.catch(() => {}).then(async () => {
      if (!paper || paper.submitted || JSON.stringify(answers) === saved) return;
      const snapshot = JSON.stringify(answers), id = paper.id;
      const result = await request(`/api/assessments/${id}/draft`, "PUT", { answers: JSON.parse(snapshot), revision: paper.revision });
      if (paper?.id !== id) return;
      paper.revision = result.revision; saved = snapshot;
      progress(JSON.stringify(answers) === saved ? "进度已保存" : "正在保存…");
    });
    return saving;
  }
  async function submit() {
    const submittedPhase = paper.phase;
    const missing = paper.questions.filter(q => !answered(q));
    const questionElement = q => document.getElementById(`exam-${q.id}`);
    root().querySelectorAll(".exam-question").forEach(el => el.classList.remove("is-missing", "is-image-missing"));
    if (missing.length) {
      missing.forEach(q => questionElement(q).classList.add("is-missing"));
      questionElement(missing[0]).focus();
      message(`还有${missing.length}个小题未作答，请补全后提交。`, true); return;
    }
    const unloaded = paper.questions.filter(q => q.image_url && questionElement(q)?.querySelector("[data-exam-image]")?.dataset.examImage !== "loaded");
    if (unloaded.length) {
      unloaded.forEach(q => questionElement(q)?.classList.add("is-image-missing"));
      questionElement(unloaded[0])?.focus();
      message(`还有${unloaded.length}张题目图片未成功加载，请等待加载完成；如加载失败，请点击“重新加载图片”后再提交。`, true); return;
    }
    if (!confirm(`确定提交${phaseName(paper.phase)}？提交后不能修改或重新作答。`)) return;
    busy = true;
    find("#assessmentForm").querySelectorAll("input,button").forEach(el => el.disabled = true);
    try {
      await flush();
      const data = await request(`/api/assessments/${paper.id}/submit`, "POST", { answers, revision: paper.revision });
      paper.submitted = true; paper = null; updateSession(data); signal(); dashboard();
      await review();
      window.scrollTo({ top: 0, behavior: "smooth" });
      message(data.post_completed ? "后测已提交，可查看两次成绩。" : "前测已提交，成绩和逐题解析已显示。");
      if (submittedPhase === "pre") {
        navigationReminder();
        pushPostIfOpened(null, data);
      }
    } finally {
      busy = false;
      const form = find("#assessmentForm");
      if (form) { form.querySelectorAll("input,button").forEach(el => el.disabled = false); bindImages(form); }
    }
  }
  async function review() {
    const container = find("#assessmentReview");
    if (!container) return;
    try {
      const data = await request("/api/assessment-results");
      if (!data.ready || !container.isConnected) return;
      container.innerHTML = data.attempts.map(p => `<details class="study-review" open><summary>${phaseName(p.phase)} · ${p.result.score} / ${p.result.total ?? paperTotal(p)} · ${p.questions.length}小题 · 答案与解析</summary>${p.result.sections ? `<section class="study-card">${scoreTable([{ ...p.result, phase: p.phase }])}</section>` : ""}${paperMarkup(p, true)}</details>`).join("");
      bindImages(container);
    } catch (error) {
      if (container.isConnected) container.innerHTML = `<section class="study-card"><p>成绩已保存。解析加载失败：${esc(error.message)}</p>${button("review", "重新加载解析", true)}</section>`;
    }
  }
  async function loadFaculty() {
    const data = await hooks.adminApi("/api/admin/study");
    find("#facultyStudy").innerHTML = `<section class="study-card"><span class="section-code">ASSESSMENT CONTROL</span><h2>知识测验与学习评价</h2><div class="exam-specs"><div><strong>${data.registered}</strong><span>登记学生</span></div><div><strong>${data.pre_completed}</strong><span>已完成前测</span></div><div><strong>${data.post_completed}</strong><span>已完成后测</span></div></div><div class="study-release"><div><strong>${data.post_open ? "教师统一后测入口已开放" : "教师统一后测入口未开放"}</strong><p>学生累计有效学习30分钟会自动获得个人后测入口；教师也可在此提前统一开放。关闭仅影响统一入口，已自动获得资格或已开始的学生不受影响。</p></div><button type="button" class="solid-button" id="togglePost">${data.post_open ? "关闭统一入口" : "统一开放后测"}</button></div><div class="study-actions"><button type="button" class="line-button" data-study-export="summary">导出配对成绩 CSV</button><button type="button" class="line-button" data-study-export="items">导出逐题作答 CSV</button><button type="button" class="line-button" id="previewPapers">查看 A/B 试卷与答案</button><button type="button" class="text-button" id="refreshFaculty">刷新记录</button></div>${notice("配对完成学生的平均分变化：" + (data.mean_gain == null ? "暂无数据" : `${data.mean_gain > 0 ? "+" : ""}${data.mean_gain}分`) + "。两卷按知识点、分值和预设难度匹配，尚需教师审题与小样本预测试验证等值性。学号和姓名是登记信息，不等同于强身份认证。")}</section><section class="study-card"><h2>学生测验记录</h2><div class="study-table-wrap"><table><thead><tr><th>学号</th><th>姓名</th><th>顺序</th><th>有效学习</th><th>后测开放</th><th>前测</th><th>后测</th><th>变化</th></tr></thead><tbody>${data.students.map(s => `<tr><td>${esc(s.student_no)}</td><td>${esc(s.name)}</td><td>${s.sequence}</td><td>${Math.floor(s.learning_seconds / 60)}分${s.learning_seconds % 60}秒</td><td>${esc(s.post_access)}</td><td>${s.pre.score ?? esc(s.pre.status)}</td><td>${s.post.score ?? esc(s.post.status)}</td><td>${s.gain ?? "—"}</td></tr>`).join("") || '<tr><td colspan="8">还没有学生记录。学生登录后会在此显示。</td></tr>'}</tbody></table></div></section><div id="facultyPapers"></div>`;
    find("#togglePost").onclick = async event => {
      if (!confirm(data.post_open ? "关闭教师统一入口？已累计学习30分钟或已开始后测的学生不受影响。" : "确认统一开放后测？所有已完成前测的学生将可以开始后测。")) return;
      event.target.disabled = true;
      try { await hooks.adminApi("/api/admin/study/release", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ open: !data.post_open }) }); await loadFaculty(); }
      catch (error) { message(error.message, true); event.target.disabled = false; }
    };
    find("#refreshFaculty").onclick = () => loadFaculty().catch(e => message(e.message, true));
    document.querySelectorAll("[data-study-export]").forEach(el => { el.onclick = async () => {
      try {
        const response = await fetch(`/api/admin/study/export?kind=${el.dataset.studyExport}`, { cache: "no-store", headers: { "X-Admin-Password": sessionStorage.getItem("adminPassword") || "" } });
        if (!response.ok) throw new Error("导出失败，请重新验证教师身份。");
        const url = URL.createObjectURL(await response.blob()); const a = document.createElement("a"); a.href = url; a.download = `study-${el.dataset.studyExport}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (error) { message(error.message, true); }
    }; });
    find("#previewPapers").onclick = async () => {
      try {
        const result = await hooks.adminApi("/api/admin/study/papers");
        find("#facultyPapers").innerHTML = `<section class="study-card"><h2>教师专用 · 平行试卷</h2><p>A/B卷使用相同知识点，按知识点、分值和预设难度匹配。每名学生随机采用A→B或B→A顺序；试卷内容固定，选项顺序随机。各节题量与分值见下方试卷，皮疹图片可放大查看。</p>${notice("请在正式教学评价前审阅题目。下方包含答案和图片出处，不要向正在测验的学生展示。")}</section>` + result.forms.map(p => `<details class="study-review"><summary>${esc(p.form)}卷 · ${paperSummary(p)}</summary>${paperMarkup(p, true)}</details>`).join("");
        bindImages(find("#facultyPapers"));
      } catch (error) { message(error.message, true); }
    };
  }
  return { init, guard, show, canLearn, isTeacher, visit, loadFaculty };
})();

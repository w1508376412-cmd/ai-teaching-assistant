/* Student records and scoring live on the server. No answer keys in this bundle. */
window.Study = (() => {
  const find = s => document.querySelector(s);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const phaseName = p => p === "pre" ? "前测" : "后测";
  let hooks, session = null, paper = null, answers = {}, saved = "{}", saving = Promise.resolve(), timer, showing = false, busy = false, lastVisit = "";
  const root = () => find("#assessmentRoot");
  const message = (text, bad = false) => hooks.toast(text, bad);
  const notice = text => `<p class="study-notice">${text}</p>`;
  const button = (action, text, secondary = false) => `<button type="button" class="${secondary ? "line-button" : "solid-button"}" data-study-action="${action}">${text}</button>`;

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
    find("#studentIdentity").textContent = `${data.student.name} · ${data.student.student_no}`;
    find("#studentStage").textContent = isTeacher() ? "教师身份 · 无需参加前测" : data.post_completed ? "前后测已完成" : data.pre_completed ? "前测已完成 · 学习中" : "请先完成首次前测";
    find("#adminNav").classList.toggle("is-hidden", !isTeacher());
    document.querySelectorAll('[data-view="knowledge"], [data-view="atlas"], [data-view="cases"]').forEach(el => {
      el.classList.toggle("study-locked", !canLearn());
      el.setAttribute("aria-disabled", String(!canLearn()));
    });
  }
  const isTeacher = () => session?.role === "teacher";
  const canLearn = () => !!(session?.authenticated && (isTeacher() || (session.pre_completed && session.active?.phase !== "post")));
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
  }
  async function init(config) {
    hooks = config;
    find("#studentLoginForm").addEventListener("submit", async event => {
      event.preventDefault();
      const submit = find("#studentLoginForm button");
      submit.disabled = true;
      find("#studentLoginError").textContent = "";
      try {
        updateSession(await request("/api/session/login", "POST", { student_no: find("#studentNumber").value, name: find("#studentName").value }));
        signal();
        hooks.switchView(isTeacher() ? "admin" : session.pre_completed ? "knowledge" : "assessment");
      } catch (error) { find("#studentLoginError").textContent = error.message; }
      finally { submit.disabled = false; }
    });
    find("#studentLogout").addEventListener("click", async () => {
      try { await flush(); await request("/api/session/logout", "POST"); signal(); location.replace("/"); }
      catch (error) { message(error.message, true); }
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
        const data = await request("/api/session");
        const changed = data.active?.id !== session.active?.id || data.pre_completed !== session.pre_completed || data.post_completed !== session.post_completed || data.post_open !== session.post_open;
        updateSession(data);
        if (!data.authenticated) return;
        if (!canLearn() && !find("#view-assessment").classList.contains("is-active")) hooks.switchView("assessment");
        else if (changed && find("#view-assessment").classList.contains("is-active")) await show();
      } catch {}
    };
    window.addEventListener("focus", sync);
    setInterval(sync, 30000);
    document.addEventListener("visibilitychange", () => { if (document.hidden && paper) void flush().catch(() => {}); else void sync(); });
    try { updateSession(await request("/api/session")); }
    catch (error) { loginScreen(); find("#studentLoginError").textContent = error.message || "暂时无法连接，请稍后重新登录。"; }
  }
  async function show(force = false) {
    if (showing || !session?.authenticated) return;
    showing = true;
    try {
      updateSession(await request("/api/session"));
      if (!session?.authenticated) return;
      if (session.active) {
        if (!force && paper?.id === session.active.id && find("#assessmentForm")) return;
        paper = await request(`/api/assessments/${session.active.id}`);
        renderPaper();
      } else { paper = null; dashboard(); }
    } catch (error) { root().innerHTML = `<section class="study-card"><h2>测验暂时无法载入</h2><p>${esc(error.message)}</p>${button("refresh", "重新载入")}</section>`; }
    finally { showing = false; }
  }
  function dashboard() {
    const intro = `<div class="study-heading"><span class="section-code">04 / KNOWLEDGE ASSESSMENT</span><h1>记录起点，检验进步。</h1><p>两次测验围绕相同知识点，使用不同设问与临床情景。</p></div>`;
    const stats = `<div class="exam-specs"><div><strong>20</strong><span>单选题 · 每题3分</span></div><div><strong>02</strong><span>案例题 · 每题20分</span></div><div><strong>100</strong><span>总分 · 不设解锁分数线</span></div></div>`;
    let content;
    if (!session.pre_completed) content = `<span class="study-pill">首次使用 · 必须完成</span><h2>先独立完成前测</h2><p>请按当前掌握程度作答，不查阅资料或使用AI。20道单选题按基础、应用、综合递进；每道案例含4个单选小题。</p><p>答案会自动保存，可以中断后继续；完成全部题目并提交即可进入学习，不要求达到及格分数。</p>${notice("前测暂不展示成绩和解析。完成后测后可查看两次成绩及逐题解析。提交后不能重做，请核对学号和姓名。")}${button("pre", "开始前测 →")}`;
    else if (!session.post_completed) content = `<span class="study-pill">前测已完成</span><h2>${session.post_open ? "教师已开放后测" : "现在可以开始学习"}</h2><p>${session.post_open ? "请按教师要求，在完成学习后独立作答。" : "知识问答、皮疹图谱和情景演练均已开放。后测由教师统一开放，此页会自动更新。"}</p><div class="study-actions">${button("learn", "返回学习 →")}${session.post_open ? button("post-confirm", "准备开始后测", true) : button("refresh", "刷新开放状态", true)}</div><div id="postConfirmation" class="study-confirmation" hidden><strong>确认已完成教师安排的学习？</strong><p>开始后测后，本站学习模块将暂时锁定，提交全部答案后恢复。后测只能提交一次。</p>${button("post", "确认开始后测")}</div>${notice("前测作答已保存在服务器。以后使用同一学号和姓名登录，不需要重复前测。")}`;
    else {
      const pre = session.results.find(r => r.phase === "pre"), post = session.results.find(r => r.phase === "post");
      content = `<span class="study-pill">两次测验已完成</span><h2>你的学习记录</h2><div class="exam-specs score-specs"><div><strong>${pre.score}</strong><span>前测 / 100</span></div><div><strong>${post.score}</strong><span>后测 / 100</span></div><div><strong>${post.score - pre.score > 0 ? "+" : ""}${post.score - pre.score}</strong><span>分数变化</span></div></div><div class="study-table-wrap"><table><thead><tr><th>知识维度</th><th>前测</th><th>后测</th></tr></thead><tbody>${Object.entries(pre.breakdown).map(([domain, data]) => `<tr><td>${esc(domain)}</td><td>${data.score} / ${data.total}</td><td>${post.breakdown[domain]?.score ?? "—"} / ${post.breakdown[domain]?.total ?? "—"}</td></tr>`).join("")}</tbody></table></div><div class="study-actions">${button("review", "查看答案与解析", true)}${button("learn", "继续学习 →")}</div>${notice("分数变化用于帮助回顾学习，不能单凭个人前后测成绩判定AI工具的因果效果。")}`;
    }
    root().innerHTML = `${intro}${session.post_completed ? "" : stats}<section class="study-card">${content}</section><div id="assessmentReview"></div>`;
  }
  function questionMarkup(q, index, reviewMode = false) {
    const selected = answers[q.id];
    return `<fieldset class="exam-question" id="exam-${q.id}" tabindex="-1"><legend><span class="question-number">${index}</span>${esc(q.stem)} <small>单选</small></legend><div class="exam-options">${q.options.map((o, n) => `<label class="exam-option"><input type="radio" name="${q.id}" data-question="${q.id}" value="${o.id}" ${selected === o.id ? "checked" : ""} ${reviewMode ? "disabled" : ""}><span><b>${String.fromCharCode(65 + n)}</b>${esc(o.text)}</span></label>`).join("")}</div>${reviewMode ? `<div class="exam-explanation"><strong>${selected === q.correct ? "回答正确" : "需复习"} · 正确答案：${esc(q.options.find(o => o.id === q.correct)?.text)}</strong><p>${esc(q.explanation)}</p><small>知识点：${esc(q.point)} · ${q.sources.map(s => esc(s.document)).filter((v, i, a) => a.indexOf(v) === i).join("；")}</small></div>` : ""}</fieldset>`;
  }
  function paperMarkup(value, reviewMode = false) {
    return `<section class="study-card"><div class="exam-section-title"><span class="section-code">PART 01 / SINGLE CHOICE</span><h2>一、单选题</h2><span>20题 · 60分</span></div>${value.questions.filter(q => !q.case_id).map((q, i) => questionMarkup(q, i + 1, reviewMode)).join("")}</section><div class="exam-section-title"><span class="section-code">PART 02 / CLINICAL CASES</span><h2>二、案例题</h2><span>2题 · 40分，每个小题只有一个最佳答案</span></div>${value.cases.map((c, i) => `<section class="study-card"><div class="exam-case-stem"><span class="section-code">CLINICAL CASE ${i + 1}</span><h3>${esc(c.title)}</h3><p>${esc(c.background)}</p></div>${value.questions.filter(q => q.case_id === c.id).map((q, j) => questionMarkup(q, `${i + 21}.${j + 1}`, reviewMode)).join("")}</section>`).join("")}`;
  }
  function renderPaper() {
    answers = { ...paper.answers }; saved = JSON.stringify(answers);
    root().innerHTML = `<div class="study-heading"><span class="section-code">KNOWLEDGE ASSESSMENT / ${paper.phase.toUpperCase()}</span><h1>${phaseName(paper.phase)}</h1><p>请独立作答。每题只有一个最佳答案，提交后不可更改。</p></div><div class="exam-progress"><label for="examProgress" id="examCount"></label><progress id="examProgress" max="28" value="0"></progress><span id="examSaveStatus" role="status"></span><button class="text-button" type="button" data-study-action="retry-save">保存进度</button></div><form id="assessmentForm" onsubmit="return false">${paperMarkup(paper)}<div class="study-card exam-submit"><div><strong>已检查全部答案？</strong><p>完成20道单选题和2道案例题的全部小题后提交。</p></div>${button("submit", `提交${phaseName(paper.phase)}`)}</div></form>`;
    progress("进度已保存");
  }
  function progress(text, error = false) {
    const count = Object.keys(answers).length;
    if (find("#examCount")) find("#examCount").textContent = `已答 ${count} / 28 小题`;
    if (find("#examProgress")) find("#examProgress").value = count;
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
    const missing = paper.questions.filter(q => !answers[q.id]);
    document.querySelectorAll(".exam-question").forEach(el => el.classList.remove("is-missing"));
    if (missing.length) {
      missing.forEach(q => find(`#exam-${q.id}`).classList.add("is-missing"));
      find(`#exam-${missing[0].id}`).focus();
      message(`还有${missing.length}个小题未作答，请补全后提交。`, true); return;
    }
    if (!confirm(`确定提交${phaseName(paper.phase)}？提交后不能修改或重新作答。`)) return;
    busy = true;
    find("#assessmentForm").querySelectorAll("input,button").forEach(el => el.disabled = true);
    try {
      await flush();
      const data = await request(`/api/assessments/${paper.id}/submit`, "POST", { answers, revision: paper.revision });
      paper.submitted = true; paper = null; updateSession(data); signal(); dashboard();
      window.scrollTo({ top: 0, behavior: "smooth" });
      message(data.post_completed ? "后测已提交，可查看两次成绩。" : "前测已提交，学习模块已开放。");
    } finally { busy = false; find("#assessmentForm")?.querySelectorAll("input,button").forEach(el => el.disabled = false); }
  }
  async function review() {
    const data = await request("/api/assessment-results");
    if (!data.ready) return;
    find("#assessmentReview").innerHTML = data.attempts.map(p => { answers = p.answers; return `<details class="study-review"><summary>${phaseName(p.phase)} · ${p.result.score} / 100 · 答案与解析</summary>${paperMarkup(p, true)}</details>`; }).join("");
  }
  async function loadFaculty() {
    const data = await hooks.adminApi("/api/admin/study");
    find("#facultyStudy").innerHTML = `<section class="study-card"><span class="section-code">ASSESSMENT CONTROL</span><h2>知识测验与学习评价</h2><div class="exam-specs"><div><strong>${data.registered}</strong><span>登记学生</span></div><div><strong>${data.pre_completed}</strong><span>已完成前测</span></div><div><strong>${data.post_completed}</strong><span>已完成后测</span></div></div><div class="study-release"><div><strong>${data.post_open ? "后测已向学生开放" : "后测未开放"}</strong><p>教师统一控制新后测的开始。关闭后，已开始的学生仍可完成作答。</p></div><button type="button" class="solid-button" id="togglePost">${data.post_open ? "关闭后测入口" : "统一开放后测"}</button></div><div class="study-actions"><button type="button" class="line-button" data-study-export="summary">导出配对成绩 CSV</button><button type="button" class="line-button" data-study-export="items">导出逐题作答 CSV</button><button type="button" class="line-button" id="previewPapers">查看 A/B 试卷与答案</button><button type="button" class="text-button" id="refreshFaculty">刷新记录</button></div>${notice("配对完成学生的平均分变化：" + (data.mean_gain == null ? "暂无数据" : `${data.mean_gain > 0 ? "+" : ""}${data.mean_gain}分`) + "。两卷按知识点、分值和预设难度匹配，尚需教师审题与小样本预测试验证等值性。学号和姓名是登记信息，不等同于强身份认证。")}</section><section class="study-card"><h2>学生测验记录</h2><div class="study-table-wrap"><table><thead><tr><th>学号</th><th>姓名</th><th>顺序</th><th>前测</th><th>后测</th><th>变化</th></tr></thead><tbody>${data.students.map(s => `<tr><td>${esc(s.student_no)}</td><td>${esc(s.name)}</td><td>${s.sequence}</td><td>${s.pre.score ?? esc(s.pre.status)}</td><td>${s.post.score ?? esc(s.post.status)}</td><td>${s.gain ?? "—"}</td></tr>`).join("") || '<tr><td colspan="6">还没有学生记录。学生登录后会在此显示。</td></tr>'}</tbody></table></div></section><div id="facultyPapers"></div>`;
    find("#togglePost").onclick = async event => {
      if (!confirm(data.post_open ? "关闭后测入口？已开始的作答不受影响。" : "确认统一开放后测？所有已完成前测的学生将可以开始后测。")) return;
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
        find("#facultyPapers").innerHTML = `<section class="study-card"><h2>教师专用 · 平行试卷</h2><p>同一批次随机抽取8道基础、8道应用、4道综合单选题，A/B卷使用相同知识点。每名学生随机采用A→B或B→A顺序；试卷内容固定，选项顺序随机。</p>${notice("请在正式教学评价前审阅题目。下方包含答案，不要向正在测验的学生展示。")}</section>` + result.forms.map(p => { answers = {}; return `<details class="study-review"><summary>${p.form}卷 · 20道单选 + 2道案例</summary>${paperMarkup(p, true)}</details>`; }).join("");
      } catch (error) { message(error.message, true); }
    };
  }
  return { init, guard, show, canLearn, isTeacher, visit, loadFaculty };
})();

window.RashQuiz = (() => {
  let data = null, hooks, busy = false, mode = "browse";
  const root = () => document.querySelector("#rashQuizRoot");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const storeKey = "rash-quiz-progress";
  const action = (id, text, secondary = false) => `<button type="button" class="${secondary ? "line-button" : "solid-button"}" data-quiz-action="${id}">${text}</button>`;
  async function request(path, body) {
    const res = await fetch(`/api/rash-quiz${path}`, {credentials: "same-origin", cache: "no-store", method: body ? "POST" : "GET", ...(body ? {headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {})});
    const result = await res.json();
    if (!res.ok) { const error = new Error(result.detail || "小测验暂时无法加载。"); error.status = res.status; throw error; }
    return result;
  }
  function remember() { try { sessionStorage.setItem(storeKey, JSON.stringify({id: data.id, index: data.index})); } catch {} }
  function setMode(next) {
    mode = next;
    document.querySelectorAll("[data-atlas-mode]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.atlasMode === mode)));
    document.querySelector(".atlas-results").classList.toggle("is-hidden", mode === "quiz");
    root().classList.toggle("is-hidden", mode !== "quiz");
    hooks.updateChrome();
    if (mode === "quiz" && !root().innerHTML) intro();
  }
  function intro() {
    root().innerHTML = `<section class="study-card quiz-intro"><span class="section-code">IMAGE PRACTICE / 05 QUESTIONS</span><h2>看图辨病小测验</h2><p>观察皮损形态和分布，结合模拟病史选择最符合的疾病。每轮随机5题，作答后可查看解析。</p><p class="study-notice">图片取自本图谱，病史为教学模拟。实际诊断还需结合查体和必要的实验室检查。</p><div class="study-actions">${action("start", "开始小测验")}${action("resume", "继续上次练习", true)}</div></section>`;
    let exists = false;
    try { exists = !!sessionStorage.getItem(storeKey); } catch {}
    root().querySelector('[data-quiz-action="resume"]').hidden = !exists;
  }
  function sources(source) {
    return `<details class="quiz-source"><summary>图片出处</summary><p>${esc(source.provider)} · ${esc(source.source_label)} · ${esc(source.license)}</p><p>${esc(source.caption)}</p>${(Array.isArray(source.links) ? source.links : []).filter(l => /^https:\/\//.test(l.url)).map(l => `<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${esc(l.label)}</a>`).join(" · ")}</details>`;
  }
  function render() {
    const q = data.question;
    if (!q) {
      root().innerHTML = `<section class="study-card"><span class="section-code">PRACTICE COMPLETE</span><h2>本轮练习完成</h2><div class="pre-score"><strong>${data.correct_count}<small> / ${data.total} 题</small></strong><p>正确率 ${Math.round(data.correct_count / data.total * 100)}%</p></div><ol class="quiz-history">${data.history.map(h => `<li><strong>${esc(h.answer)} · ${h.correct ? "回答正确" : "需复习"}</strong><p>你的选择：${esc(h.selected)}</p><p>${esc(h.explanation)}</p></li>`).join("")}</ol><div class="study-actions">${action("start", "再练一轮")}${action("browse", "返回图谱", true)}</div></section>`;
      return;
    }
    const answered = Object.hasOwn(q, "selected");
    const prompt = answered ? `请解释${q.answer}的典型皮损、临床诊断及需要安排的检查，并与${q.options.filter(o => o !== q.answer).join("、")}鉴别。` : "";
    root().innerHTML = `<section class="study-card quiz-card"><div class="quiz-heading"><span class="section-code">IMAGE PRACTICE</span><span>${data.index + 1} / ${data.total}</span></div><div class="quiz-layout"><figure class="quiz-figure"><button type="button" class="quiz-image-button" data-quiz-action="zoom" aria-label="放大查看皮损图片"><img src="${esc(q.image_url)}" alt="${esc(q.alt)}" decoding="async"></button><figcaption>点击图片可放大观察</figcaption><p class="quiz-image-error" role="alert" hidden>图片加载失败，请重试后作答。${action("reload", "重新加载图片", true)}</p></figure><div class="quiz-answer"><p class="quiz-context">${esc(q.context)}</p><form id="rashQuizForm"><fieldset class="exam-question"><legend><span class="question-number">${data.index + 1}.</span>结合图片和病史，最符合哪种疾病？</legend><div class="exam-options">${q.options.map((o, n) => `<label class="exam-option"><input type="radio" name="rash-disease" value="${esc(o)}" ${answered ? "disabled" : ""} ${q.selected === o ? "checked" : ""}><span><b>${String.fromCharCode(65+n)}</b>${esc(o)}</span></label>`).join("")}</div></fieldset>${!answered ? '<button type="submit" class="solid-button" id="submitRashAnswer" disabled>提交答案</button>' : ""}</form>${answered ? `<div class="exam-explanation" role="status"><strong>${q.correct ? "回答正确" : "需复习"} · ${esc(q.answer)}</strong><p>${esc(q.explanation)}</p><div class="study-actions"><button type="button" class="line-button" data-knowledge-question="${esc(prompt)}">去知识问答提问</button></div></div>${sources(q.source)}<div class="study-actions">${action("next", data.index + 1 === data.total ? "查看本轮结果" : "下一题")}</div>` : ""}</div></div></section><dialog class="quiz-zoom" aria-label="皮损图片放大"><button type="button" data-quiz-action="close-zoom" aria-label="关闭图片">×</button><img src="${esc(q.image_url)}" alt="${esc(q.alt)}"></dialog>`;
    const img = root().querySelector(".quiz-image-button img");
    const form = root().querySelector("#rashQuizForm");
    const updateSubmit = () => { const submit = form.querySelector("#submitRashAnswer"); if (submit) submit.disabled = busy || !img.complete || !img.naturalWidth || !form.querySelector("input:checked"); };
    img.onload = () => { if (!img.isConnected) return; root().querySelector(".quiz-image-error").hidden = true; updateSubmit(); };
    img.onerror = () => { if (!img.isConnected) return; root().querySelector(".quiz-image-error").hidden = false; updateSubmit(); };
    if (img.complete && !img.naturalWidth) img.onerror();
    form.onchange = updateSubmit;
    form.onsubmit = async event => {
      event.preventDefault();
      const selected = form.querySelector("input:checked");
      if (busy || answered || !selected || !img.naturalWidth) return;
      busy = true; form.querySelectorAll("input,button").forEach(el => el.disabled = true);
      try { data = await request(`/${data.id}/answer`, {question_id: q.id, choice: selected.value}); remember(); render(); root().querySelector('[data-quiz-action="next"]').focus(); }
      catch (error) { hooks.toast(error.message, true); }
      finally { busy = false; if (form.isConnected) { form.querySelectorAll("input,button").forEach(el => el.disabled = false); updateSubmit(); } }
    };
  }
  function init(config) {
    hooks = config;
    document.querySelectorAll("[data-atlas-mode]").forEach(b => b.onclick = () => setMode(b.dataset.atlasMode));
    root().onclick = async event => {
      const target = event.target.closest("[data-quiz-action]");
      if (!target || busy) return;
      const type = target.dataset.quizAction;
      if (type === "browse") { setMode("browse"); return; }
      if (type === "zoom") { root().querySelector("dialog").showModal(); return; }
      if (type === "close-zoom") { root().querySelector("dialog").close(); return; }
      if (type === "reload") { render(); return; }
      busy = true; target.disabled = true;
      try {
        if (type === "start") data = await request("", {});
        else if (type === "next") data = await request(`/${data.id}?index=${data.index+1}`);
        else if (type === "resume") {
          const last = JSON.parse(sessionStorage.getItem(storeKey));
          if (!last?.id || !/^[a-f0-9]{32}$/.test(last.id) || !Number.isInteger(last.index)) throw new Error("暂无可继续的练习，请开始新一轮。");
          data = await request(`/${last.id}?index=${last.index}`);
        }
        remember(); render();
        root().scrollIntoView({behavior: "smooth", block: "start"});
      } catch (error) {
        if (error.status === 404) { try { sessionStorage.removeItem(storeKey); } catch {} intro(); }
        hooks.toast(error.message, true);
      } finally { busy = false; target.disabled = false; }
    };
  }
  return {init, isActive: () => mode === "quiz"};
})();

/* AgentHub 控制台 —— Agent 管理页签的逻辑。
 * 零依赖：只用浏览器自带 fetch，调后端 REST API。
 * 后面加知识库/对话页签时，往这个文件里加函数即可。
 */

const API = "/api";
let editingId = null; // 当前正在编辑的 Agent id，null 表示"新建"模式

/* ---------- 通用小工具 ---------- */

// 发请求：method 传 "GET"/"POST"/"PUT"/"DELETE"，body 传对象（会自动 JSON 序列化）
async function api(method, path, body) {
  const resp = await fetch(API + path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    // 后端错误统一形如 {"detail": "..."}，尽力取出来
    let detail = `HTTP ${resp.status}`;
    try {
      const data = await resp.json();
      detail = data.detail || detail;
    } catch (_) { /* 空 body 就只显示状态码 */ }
    throw new Error(detail);
  }
  if (resp.status === 204) return null; // 删除等无返回体
  return resp.json();
}

function toast(msg, type = "") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type}`;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 2600);
}

// "a,b, 1,2" → ["a","b"]；去空、去重
function parseList(text) {
  return [...new Set(text.split(",").map((s) => s.trim()).filter(Boolean))];
}

/* ---------- Agent 列表 ---------- */

async function loadAgents() {
  const q = document.getElementById("search-name").value.trim();
  const url = q ? `/agents?size=100&name=${encodeURIComponent(q)}` : "/agents?size=100";
  const tbody = document.getElementById("agent-tbody");
  try {
    const data = await api("GET", url);
    tbody.innerHTML = data.items.length
      ? data.items.map(rowHtml).join("")
      : '<tr><td colspan="8" class="empty">没有 Agent，先在上方建一个吧</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">加载失败：${e.message}</td></tr>`;
  }
}

function rowHtml(a) {
  const tools = (a.tools || []).map((t) => `<span class="chip">${t}</span>`).join("") || "—";
  const rag = a.use_rag ? '<span class="chip on">开</span>' : '<span class="chip off">关</span>';
  const status = a.status === 1 ? '<span class="chip on">启用</span>' : '<span class="chip off">停用</span>';
  return `
    <tr>
      <td>${a.id}</td>
      <td><strong>${esc(a.name)}</strong><br><span style="color:var(--muted)">${esc(a.description) || "&nbsp;"}</span></td>
      <td>${esc(a.model_name)}</td>
      <td>${a.temperature}</td>
      <td>${rag}</td>
      <td>${tools}</td>
      <td>${status}</td>
      <td>
        <button class="btn ghost op-btn" onclick="startEdit(${a.id})">编辑</button>
        <button class="btn danger op-btn" onclick="removeAgent(${a.id}, '${esc(a.name, true)}')">删除</button>
      </td>
    </tr>`;
}

// 转义用户输入，防止 XSS（name 是用户可填的）
function esc(s, forAttr = false) {
  if (s == null) return "";
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const out = String(s).replace(/[&<>"']/g, (c) => map[c]);
  return forAttr ? out : out;
}

/* ---------- 新建 / 编辑 ---------- */

function collectForm() {
  return {
    name: document.getElementById("f-name").value.trim(),
    description: document.getElementById("f-desc").value.trim(),
    prompt_template: document.getElementById("f-prompt").value,
    model_name: document.getElementById("f-model").value,
    temperature: parseFloat(document.getElementById("f-temp").value) || 0.7,
    max_tokens: parseInt(document.getElementById("f-max-tokens").value, 10) || 1024,
    use_rag: document.getElementById("f-rag").checked,
    // 工具从输入框解析（下拉菜单选中后会自动写入，逗号分隔）
    tools: parseList(document.getElementById("f-tools").value),
    knowledge_base_ids: selectedKbIds.slice(),  // 从多选菜单收集的知识库 id
    status: 1,
  };
}

async function onFormSubmit(e) {
  e.preventDefault();
  try {
    if (editingId === null) {
      await api("POST", "/agents", collectForm());
      toast("创建成功 🎉", "ok");
      resetForm(); // 创建完清空表单，方便连续创建下一个
    } else {
      await api("PUT", `/agents/${editingId}`, collectForm());
      toast("已保存修改 ✅", "ok");
      resetForm();
    }
    loadAgents();
    loadChatAgents(); // 新建/改完，对话下拉框要及时看到
  } catch (err) {
    toast("失败：" + err.message, "err");
  }
}

function startEdit(id) {
  api("GET", `/agents/${id}`).then((a) => {
    editingId = id;
    document.getElementById("f-id").value = a.id;
    document.getElementById("f-name").value = a.name;
    document.getElementById("f-desc").value = a.description || "";
    document.getElementById("f-prompt").value = a.prompt_template || "";
    document.getElementById("f-model").value = a.model_name || "qwen3.7-plus";
    document.getElementById("f-temp").value = a.temperature;
    document.getElementById("f-max-tokens").value = a.max_tokens;
    document.getElementById("f-rag").checked = !!a.use_rag;
    // 回填工具（逗号分隔格式，与下拉菜单选择一致）
    document.getElementById("f-tools").value = (a.tools || []).join(", ");
    // 回填绑定的知识库（多选菜单里标已选，输入框显示库名）
    selectedKbIds = (a.knowledge_base_ids || []).map((x) => Number(x));
    updateKbInput();
    document.getElementById("f-kbs").value = (a.knowledge_base_ids || []).join(", ");
    document.getElementById("form-title").textContent = `编辑 Agent #${a.id}`;
    document.getElementById("btn-submit").textContent = "保存修改";
    document.getElementById("btn-cancel").hidden = false;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }).catch((err) => toast("读取失败：" + err.message, "err"));
}

function resetForm() {
  editingId = null;
  document.getElementById("agent-form").reset();
  document.getElementById("f-rag").checked = false;
  selectedKbIds = [];       // 清空已选知识库（输入框会被 reset 清空，状态也要同步）
  updateKbInput();
  document.getElementById("form-title").textContent = "新建 Agent";
  document.getElementById("btn-submit").textContent = "创建";
  document.getElementById("btn-cancel").hidden = true;
}

async function removeAgent(id, name) {
  if (!confirm(`确定删除 Agent「${name}」吗？此操作不可恢复。`)) return;
  try {
    await api("DELETE", `/agents/${id}`);
    toast("已删除", "ok");
    if (editingId === id) resetForm();
    loadAgents();
    loadChatAgents(); // 删完助手，对话下拉框同步移除
  } catch (err) {
    toast("删除失败：" + err.message, "err");
  }
}

/* ---------- 知识库管理 ---------- */

let currentKbId = null; // 当前正在查看哪个知识库

// 多部分表单上传（文件不走 JSON）
async function apiMultipart(method, path, formData) {
  const resp = await fetch(API + path, { method, body: formData });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try { detail = (await resp.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return resp.status === 204 ? null : resp.json();
}

function fmtSize(bytes) {
  if (!bytes) return "—";
  return bytes > 1024 ? (bytes / 1024).toFixed(1) + " KB" : bytes + " B";
}

function fmtDate(s) {
  return s ? String(s).replace("T", " ").slice(0, 16) : "";
}

async function loadKnowledgeBases() {
  const tbody = document.getElementById("kb-tbody");
  try {
    const data = await api("GET", "/knowledge-bases?size=100");
    tbody.innerHTML = data.items.length
      ? data.items.map(kbRow).join("")
      : '<tr><td colspan="5" class="empty">还没有知识库，先在上方创建</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">加载失败：${e.message}</td></tr>`;
  }
}

function kbRow(kb) {
  return `<tr>
    <td>${kb.id}</td>
    <td><strong>${esc(kb.name)}</strong><br><span style="color:var(--muted)">${esc(kb.description) || "&nbsp;"}</span></td>
    <td>${kb.doc_count}</td>
    <td>${fmtDate(kb.created_at)}</td>
    <td><button class="btn ghost op-btn" onclick="selectKb('${kb.id}', '${esc(kb.name, true)}')">📂 文档</button></td>
  </tr>`;
}

// ---- 绑定知识库：点击输入框弹出库列表多选（与"绑定工具"一致）----
let selectedKbIds = [];   // 已选知识库的 id
let kbIdToName = {};      // id → 名称（输入框只显示名称，不暴露 id）

// 填充 Agent 表单里的"绑定知识库"下拉菜单
async function loadKbSelect() {
  const menu = document.getElementById("kb-menu");
  try {
    const data = await api("GET", "/knowledge-bases?size=100");
    kbIdToName = {};
    data.items.forEach((kb) => { kbIdToName[kb.id] = kb.name; });
    menu.innerHTML = data.items.length
      ? data.items.map((kb) =>
          `<div class="tool-option" data-kb-id="${kb.id}">` +
          `<span class="tool-name">${esc(kb.name)}</span>` +
          `<span class="muted">${kb.doc_count} 份文档</span></div>`).join("")
      : '<div class="tool-option" data-kb-id="">还没知识库，先到「知识库」页签创建</div>';
    updateKbInput();
  } catch (e) {
    menu.innerHTML = '<div class="tool-option" data-kb-id="">加载失败</div>';
  }
}

// 把已选库显示到输入框（名称，逗号分隔）
function updateKbInput() {
  document.getElementById("f-kbs").value = selectedKbIds.map((id) => kbIdToName[id] || id).join(", ");
}

// 弹出库列表，并给已选的打勾
function showKbMenu() {
  const menu = document.getElementById("kb-menu");
  menu.querySelectorAll(".tool-option").forEach((opt) => {
    opt.classList.toggle("selected", selectedKbIds.includes(Number(opt.dataset.kbId)));
  });
  menu.hidden = false;
}
document.getElementById("f-kbs").addEventListener("focus", showKbMenu);
document.getElementById("f-kbs").addEventListener("click", showKbMenu);

// 点某个库 → 选/取消，写完输入框后收起菜单（可再点输入框弹开多选）
document.getElementById("kb-menu").addEventListener("mousedown", (e) => {
  const opt = e.target.closest(".tool-option");
  if (!opt || !opt.dataset.kbId) return;
  e.preventDefault(); // 防止输入框先失焦把菜单关掉
  const id = Number(opt.dataset.kbId);
  selectedKbIds = selectedKbIds.includes(id)
    ? selectedKbIds.filter((x) => x !== id)   // 再点 = 取消
    : [...selectedKbIds, id];                 // 点 = 追加（支持多选）
  updateKbInput();
  document.getElementById("kb-menu").hidden = true;  // 选完收起，避免挡住其它控件
  document.getElementById("f-kbs").focus();
});

async function createKb() {
  const name = document.getElementById("kb-name").value.trim();
  if (!name) return toast("请填知识库名称", "err");
  const initialText = document.getElementById("kb-initial-text").value;
  try {
    await api("POST", "/knowledge-bases", {
      name,
      description: document.getElementById("kb-desc").value.trim(),
      initial_text: initialText,  // 填了就直接入库一份文档，创建后文档数=1
    });
    toast(initialText.trim() ? "创建成功，初始文档已入库 🎉" : "知识库创建成功 🎉", "ok");
    document.getElementById("kb-name").value = "";
    document.getElementById("kb-desc").value = "";
    document.getElementById("kb-initial-text").value = "";
    loadKnowledgeBases();
    loadKbSelect(); // 新库也要能立刻在 Agent 表单里被选
  } catch (e) { toast("失败：" + e.message, "err"); }
}

async function selectKb(id, name) {
  currentKbId = id;
  document.getElementById("kb-detail").hidden = false;
  document.getElementById("kb-title").textContent = `文档管理（知识库：${name}）`;
  document.getElementById("search-results").innerHTML = "";
  loadDocuments();
}

function closeKb() {
  currentKbId = null;
  document.getElementById("kb-detail").hidden = true;
  loadKnowledgeBases();
}

async function loadDocuments() {
  if (currentKbId == null) return;
  const tbody = document.getElementById("doc-tbody");
  try {
    const data = await api("GET", `/documents?kb_id=${currentKbId}&size=100`);
    tbody.innerHTML = data.items.length
      ? data.items.map(docRow).join("")
      : '<tr><td colspan="8" class="empty">还没有文档，选个 PDF/TXT/MD 上传试试</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty">加载失败：${e.message}</td></tr>`;
  }
}

const DOC_STATUS = {
  ready: '<span class="chip on">就绪</span>',
  processing: '<span class="chip">处理中</span>',
  pending: '<span class="chip">排队</span>',
  failed: '<span class="chip off" title="看看错误列">失败</span>',
};

function docRow(d) {
  return `<tr>
    <td>${d.id}</td>
    <td>${esc(d.filename)}</td>
    <td>${esc(d.file_type)}</td>
    <td>${fmtSize(d.size_bytes)}</td>
    <td>${DOC_STATUS[d.status] || esc(d.status)}</td>
    <td>${d.chunk_count}</td>
    <td style="max-width:180px;color:var(--danger)">${esc(d.error_msg)}</td>
    <td>
      <button class="btn ghost op-btn" onclick="inspectDoc(${d.id})">查看</button>
      <button class="btn danger op-btn" onclick="removeDoc(${d.id})">删除</button>
    </td>
  </tr>`;
}

// 查看文档入库后的切块内容（弹层）
async function inspectDoc(id) {
  const m = document.getElementById("doc-modal");
  const title = document.getElementById("doc-modal-title");
  const body = document.getElementById("doc-modal-body");
  title.textContent = "加载中…";
  body.innerHTML = "";
  m.hidden = false;
  try {
    const data = await api("GET", `/documents/${id}/chunks`);
    title.textContent = `「${data.filename}」内容预览（共 ${data.chunk_count} 段）`;
    body.innerHTML = data.chunks.length
    ? '<div class="hint-inline">这份文档被切成 ' + data.chunk_count + ' 段（切块）入库，每段都能被独立检索。以下按顺序罗列全部段落。</div>' +
      data.chunks.map((ch) => `
          <div class="doc-chunk">
            <div class="doc-chunk-text">${esc(ch.text)}</div>
          </div>`).join("")
    : `<div class="chat-hint">该文档没有可查看的切块（状态：${esc(data.status)}）。可能是上传失败或还在处理中。</div>`;
  } catch (e) {
    body.innerHTML = `<div class="chat-hint">加载失败：${e.message}</div>`;
  }
}

function closeDocModal() {
  document.getElementById("doc-modal").hidden = true;
}

// 点弹层背景（非内容）关闭
document.addEventListener("DOMContentLoaded", () => {
  const m = document.getElementById("doc-modal");
  if (m) m.addEventListener("click", (e) => { if (e.target.id === "doc-modal") closeDocModal(); });
});

async function uploadDoc() {
  if (currentKbId == null) return toast("先点一个知识库的「文档」按钮", "err");
  const input = document.getElementById("doc-file");
  if (!input.files || !input.files.length) return toast("请先选择文件", "err");
  const form = new FormData();
  form.append("file", input.files[0]);
  toast("上传处理中（切块+向量化需要几秒）…");
  try {
    const doc = await apiMultipart("POST", `/knowledge-bases/${currentKbId}/documents`, form);
    if (doc.status === "ready") toast(`入库成功，切成 ${doc.chunk_count} 块 ✅`, "ok");
    else toast(`处理失败：${doc.error_msg || doc.status}`, "err");
    input.value = "";
    loadDocuments();
    loadKnowledgeBases();
  } catch (e) {
    toast("上传失败：" + e.message, "err");
  }
}

async function removeDoc(id) {
  if (!confirm("确定删除该文档及其向量吗？")) return;
  try {
    await api("DELETE", `/documents/${id}`);
    toast("文档已删除，向量已清理", "ok");
    loadDocuments();
    loadKnowledgeBases();
  } catch (e) { toast("删除失败：" + e.message, "err"); }
}

async function searchKb() {
  if (currentKbId == null) return toast("先点一个知识库的「文档」按钮", "err");
  const q = document.getElementById("search-query").value.trim();
  if (!q) return toast("请输入检索词", "err");
  const box = document.getElementById("search-results");
  box.innerHTML = '<div class="hit loading">检索中…</div>';
  try {
    const data = await api("GET", `/knowledge-bases/${currentKbId}/search?query=${encodeURIComponent(q)}&top_k=5`);
    box.innerHTML = data.results.length
      ? data.results.map((r) => `
          <div class="hit">
            <div class="hit-head">
              <span>来源：${esc(r.filename) || "未知文档"}</span>
              <span class="hit-score">相关度 ${Math.max(0, 1 - r.score).toFixed(2)}</span>
            </div>
            <div class="hit-text">${esc(r.chunk_text)}</div>
          </div>`).join("")
      : '<div class="hit empty">无命中，试试换个词</div>';
  } catch (e) {
    box.innerHTML = `<div class="hit empty">检索失败：${e.message}</div>`;
  }
}

/* ---------- 绑定工具下拉菜单 ---------- */

// 当前输入框里已选中的工具列表
function currentTools() {
  return parseList(document.getElementById("f-tools").value);
}

// 点输入框 → 弹出工具列表，并标出"已选"的工具
function showToolMenu() {
  const menu = document.getElementById("tool-menu");
  const have = currentTools();
  menu.querySelectorAll(".tool-option").forEach((opt) => {
    opt.classList.toggle("selected", have.includes(opt.dataset.tool));
  });
  menu.hidden = false;
}
document.getElementById("f-tools").addEventListener("focus", showToolMenu);
document.getElementById("f-tools").addEventListener("click", showToolMenu);

// 点某个工具 → 写入输入框（已选的再点=取消，未选的点=追加），然后收起菜单
document.querySelectorAll(".tool-option").forEach((opt) => {
  opt.addEventListener("mousedown", (e) => {   // mousedown（非 click）避免输入框先失焦把菜单关掉
    e.preventDefault();
    const name = opt.dataset.tool;
    const have = currentTools();
    const next = have.includes(name) ? have.filter((t) => t !== name) : [...have, name];
    const input = document.getElementById("f-tools");
    input.value = next.join(", ");
    document.getElementById("tool-menu").hidden = true;
    input.focus();
  });
});

// 点击输入框之外任意处 → 收起所有下拉菜单（工具菜单 + 知识库菜单）
document.addEventListener("click", (e) => {
  if (!e.target.closest(".tool-field")) {
    document.querySelectorAll(".tool-menu").forEach((m) => { m.hidden = true; });
  }
});

/* ---------- 对话服务 ---------- */

let chatSessionId = null; // 当前会话号（页面上所有消息共用，发给后端）
let chatAgentId = null;   // 当前选中的 Agent id
let chatAgentName = "";   // 当前选中 Agent 的名称（只用来展示，不让用户看到内部 id）

// 下拉框加载所有 Agent，供用户挑选对话对象
async function loadChatAgents() {
  const sel = document.getElementById("chat-agent");
  try {
    const data = await api("GET", "/agents?size=100");
    // 下拉框：value 存 id（给后端），显示只用名称（不让用户看到内部 id）
    sel.innerHTML = '<option value="">—— 选择 Agent ——</option>' +
      data.items.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
    // 重建下拉后恢复之前的选中（切页签回来不丢选择）
    if (chatAgentId && [...sel.options].some((o) => o.value === String(chatAgentId))) {
      sel.value = String(chatAgentId);
      chatAgentName = sel.selectedOptions[0].text.trim();
    } else {
      chatAgentId = null;
      chatAgentName = "";
    }
  } catch (e) {
    sel.innerHTML = '<option value="">加载失败</option>';
  }
}

// 进入对话页签时：若已选过 Agent 但对话区还是初始空态，补一个欢迎提示（不重置会话）
function rememberChatAgent() {
  const sel = document.getElementById("chat-agent");
  if (chatAgentId && sel.value === String(chatAgentId)) {
    // 已有选中，仅在对话区是纯提示时补齐欢迎语，不打断历史
    const box = document.getElementById("chat-box");
    if (!box.querySelector(".msg") && box.querySelector(".chat-hint")) {
      box.innerHTML = `<div class="chat-hint">已选「${esc(chatAgentName)}」，开始聊天吧（本次会话内它有记忆）</div>`;
    }
  }
}

// 切换 Agent 时开一个新的会话（换 Agent 或点"新会话"都走这里）
function newChat() {
  const sel = document.getElementById("chat-agent");
  chatAgentId = sel.value ? Number(sel.value) : null;
  // 记住名称用于展示（不要让用户看到内部 id）
  chatAgentName = sel.selectedOptions[0] ? sel.selectedOptions[0].text.trim() : "";
  // 生成一个"不会重复"的会话号（时间 + 随机数凑的）。
  // 模块4 起：同一会话号的消息历史存 Redis，后端每次把最近几轮拼给模型 → 助手有记忆
  chatSessionId = "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  document.getElementById("chat-box").innerHTML =
    `<div class="chat-hint">${chatAgentId ? `已选「${esc(chatAgentName)}」，开始聊天吧（本次会话内它有记忆）` : "先在上方选择 Agent，然后开始聊天"}</div>`;
  document.getElementById("chat-input").value = "";
  document.getElementById("chat-input").focus();
}

// 点「新会话」按钮：彻底重置——清空已选的 Agent，要求重新选择
function resetChat() {
  const sel = document.getElementById("chat-agent");
  sel.value = "";               // 回到"选择 Agent"占位
  chatAgentId = null;
  chatAgentName = "";
  chatSessionId = "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  document.getElementById("chat-box").innerHTML =
    '<div class="chat-hint">已开启全新会话，请重新选择 Agent 后开始聊天</div>';
  document.getElementById("chat-input").value = "";
  document.getElementById("chat-input").focus();
}

// 把一条消息显示到聊天气泡区。role: "user"（自己，靠右）/ "assistant"（助手，靠左）
function appendChat(role, text) {
  const box = document.getElementById("chat-box");
  const hint = box.querySelector(".chat-hint");
  if (hint) hint.remove(); // 第一条真实消息出现时，去掉占位提示
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.innerHTML = `<span class="bubble">${esc(text)}</span>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight; // 自动滚到底部
  return div.querySelector(".bubble"); // 返回气泡元素，供流式逐字填充
}

// 发送消息：POST /api/chat，把回答加到气泡区
async function sendChat() {
  // 兜底：万一没触发 onchange（比如下拉值被程序设置过），这里补一次读取
  if (!chatAgentId) {
    const sel = document.getElementById("chat-agent");
    if (sel.value) newChat(); // 同步函数，调用后 chatAgentId 已就位
  }
  if (!chatAgentId) return toast("请先在右上角选择 Agent", "err");
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  const box = document.getElementById("chat-box");
  appendChat("user", text);
  input.value = "";
  toast("思考中…");
  const bubble = appendChat("assistant", ""); // 空白占位，流式逐字填充
  try {
    // 流式：fetch 拿 body 流，边读边渲染（打字机效果）
    const resp = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        agent_id: chatAgentId, session_id: chatSessionId, message: text, stream: true,
      }),
    });
    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try { detail = (await resp.json()).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // SSE 按空行(.split("\n\n"))分帧；最后一帧可能不完整，留到下次拼
      const frames = buffer.split("\n\n");
      buffer = frames.pop();
      for (const frame of frames) {
        let data = null;
        for (const line of frame.split("\n")) {
          if (line.startsWith("data: ")) {
            try { data = JSON.parse(line.slice(6)); } catch (_) {}
            break;
          }
        }
        if (!data) continue;
        if (data.type === "delta") {
          bubble.textContent += data.text;   // 逐字追加 = 打字机效果
          box.scrollTop = box.scrollHeight;
        } else if (data.type === "tool") {
          toast("正在调用工具：" + (data.tools || []).join(", ") + "…");
        }
      }
    }
    if (!bubble.textContent) bubble.textContent = "（无回答）";
    toast("回答完成", "ok");
  } catch (e) {
    bubble.textContent = "（出错了：" + e.message + "）";
    toast("对话失败", "err");
  }
}

/* ---------- 工具调用日志 ---------- */

async function loadToolLogs() {
  const box = document.getElementById("log-box");
  const filter = document.getElementById("log-filter").value.trim();
  const url = filter
    ? `/tool-call-logs?tool_name=${encodeURIComponent(filter)}&size=100`
    : "/tool-call-logs?size=100";
  try {
    const data = await api("GET", url);
    box.innerHTML = data.items.length
      ? data.items.map(toolLogHtml).join("")
      : '<div class="chat-hint">还没有工具调用记录。<br>去「对话」页签让绑了工具的 Agent 问一句时间或查资料，就能看到日志。</div>';
  } catch (e) {
    box.innerHTML = `<div class="chat-hint">加载失败：${e.message}</div>`;
  }
}

function toolLogHtml(l) {
  const status = l.status === "success"
    ? '<span class="chip on">成功</span>'
    : '<span class="chip off">失败</span>';
  const params = JSON.stringify(l.params || {});
  const result = JSON.stringify(l.result || {});
  return `<div class="log-item">
    <div class="log-head">
      <span class="tool-name">🔧 ${esc(l.tool_name)}</span>
      ${status}
      <span class="muted">耗时 ${l.latency_ms}ms</span>
      <span class="muted">会话 ${esc(String(l.session_id).slice(0, 12))}…</span>
    </div>
    <div class="log-code" title="调用参数">⚙️ 参数：${esc(params)}</div>
    <div class="log-code" title="返回结果">📦 结果：${esc(result.slice(0, 200))}${result.length > 200 ? "…" : ""}</div>
  </div>`;
}

/* ---------- 页签切换 ---------- */

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    // 切到指定页签时按需刷新数据
    if (btn.dataset.tab === "logs") loadToolLogs();
    if (btn.dataset.tab === "chat") { loadChatAgents(); rememberChatAgent(); }
  });
});

/* ---------- 初始化 ---------- */

document.getElementById("agent-form").addEventListener("submit", onFormSubmit);
document.getElementById("btn-cancel").addEventListener("click", resetForm);
document.getElementById("search-name").addEventListener("input", debounce(loadAgents, 300));

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

loadAgents();
loadKnowledgeBases();
loadChatAgents();
loadKbSelect();
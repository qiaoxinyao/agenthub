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
    tools: parseList(document.getElementById("f-tools").value),
    knowledge_base_ids: parseList(document.getElementById("f-kbs").value).map(Number),
    status: 1,
  };
}

async function onFormSubmit(e) {
  e.preventDefault();
  try {
    if (editingId === null) {
      await api("POST", "/agents", collectForm());
      toast("创建成功 🎉", "ok");
    } else {
      await api("PUT", `/agents/${editingId}`, collectForm());
      toast("已保存修改 ✅", "ok");
      resetForm();
    }
    loadAgents();
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
    document.getElementById("f-tools").value = (a.tools || []).join(", ");
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

async function createKb() {
  const name = document.getElementById("kb-name").value.trim();
  if (!name) return toast("请填知识库名称", "err");
  try {
    await api("POST", "/knowledge-bases", { name, description: document.getElementById("kb-desc").value.trim() });
    toast("知识库创建成功 🎉", "ok");
    document.getElementById("kb-name").value = "";
    document.getElementById("kb-desc").value = "";
    loadKnowledgeBases();
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
    <td><button class="btn danger op-btn" onclick="removeDoc(${d.id})">删除</button></td>
  </tr>`;
}

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
              <span>来自文档 #${r.document_id} ${esc(r.filename)} · 块 ${r.chunk_index}</span>
              <span class="hit-score">distance ${r.score}</span>
            </div>
            <div class="hit-text">${esc(r.chunk_text)}</div>
          </div>`).join("")
      : '<div class="hit empty">无命中，试试换个词</div>';
  } catch (e) {
    box.innerHTML = `<div class="hit empty">检索失败：${e.message}</div>`;
  }
}

/* ---------- 对话服务 ---------- */

let chatSessionId = null; // 当前会话号（页面上所有消息共用，发给后端）
let chatAgentId = null;   // 当前选中的 Agent id

// 下拉框加载所有 Agent，供用户挑选对话对象
async function loadChatAgents() {
  const sel = document.getElementById("chat-agent");
  try {
    const data = await api("GET", "/agents?size=100");
    sel.innerHTML = '<option value="">—— 选择 Agent ——</option>' +
      data.items.map((a) => `<option value="${a.id}">#${a.id} ${esc(a.name)}</option>`).join("");
  } catch (e) {
    sel.innerHTML = '<option value="">加载失败</option>';
  }
}

// 切换 Agent 时开一个新的会话（模块3 是单轮；模块4 起 session 才有历史）
function newChat() {
  const sel = document.getElementById("chat-agent");
  chatAgentId = sel.value ? Number(sel.value) : null;
  // 生成一个"不会重复"的会话号（时间 + 随机数凑的）
  chatSessionId = "s" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  document.getElementById("chat-box").innerHTML =
    `<div class="chat-hint">已选 Agent${chatAgentId ? ` #${chatAgentId}` : ""}，开始聊天吧</div>`;
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
}

// 发送消息：POST /api/chat，把回答加到气泡区
async function sendChat() {
  if (!chatAgentId) return toast("请先选择 Agent", "err");
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  appendChat("user", text);
  input.value = "";
  toast("思考中…");
  try {
    const data = await api("POST", "/chat", {
      agent_id: chatAgentId,
      session_id: chatSessionId,
      message: text,
    });
    appendChat("assistant", data.reply);
    toast("回答完成", "ok");
  } catch (e) {
    appendChat("assistant", "（出错了：" + e.message + "）");
    toast("对话失败", "err");
  }
}

/* ---------- 页签切换 ---------- */

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
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
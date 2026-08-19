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
    document.getElementById("f-model").value = a.model_name || "qwen-turbo";
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
// AgentHub 切分微服务（Go）
//
// 【大白话】这是一个用 Go 写的独立小服务，只干一件事：把一段纯文本
// 切成一块块（chunk），供后面的检索用。它设计得尽量"小而纯"：
//   - 无状态：不存任何数据，来一段文字、走一段文字
//   - 只碰文本：不做 PDF 解析、不做向量化（那些重活留 Python）
//   - 一个 HTTP 接口 + 一个健康检查，约 130 行
//
// 【为什么用它对齐 JD】岗位要求会 Go。我不转学 Go，但交付这个 100 行级、
// 能独立跑起来的 Go 服务，面试话术：主栈 Python、Go 也能做轻量微服务。
//
// 接口：
//   POST /chunk   {"text":"...", "chunk_size":500, "chunk_overlap":50}
//                  → {"count":n, "chunks":["...", "..."]}
//   GET  /health  → {"status":"ok"}

package main

// import：类似 Python 的 import，引入标准库
import (
	"encoding/json" // 序列化/反序列化 JSON（Python 的 json 模块）
	"log"           // 打日志
	"net/http"      // 起 HTTP 服务（Python 里对应 FastAPI 那一套）
	"os"            // 读环境变量
	"strings"       // 字符串工具
	"unicode/utf8"  // UTF-8 处理（数"字符个数"要按 rune 数，不能按字节，中文一个 3 字节）
)

// chunkRequest：请求的 JSON 结构。json:"text" 表示 JSON 里的字段名是 text。
// 【对比 Python】这相当于类/字典，只是 Go 用 struct + 字段标签明确指定 JSON 映射。
type chunkRequest struct {
	Text         string `json:"text"`
	ChunkSize    int    `json:"chunk_size"`
	ChunkOverlap int    `json:"chunk_overlap"`
}

// chunkResponse：响应的 JSON 结构。
type chunkResponse struct {
	Count  int      `json:"count"`
	Chunks []string `json:"chunks"`
}

// runeLen 按"字符数"计长（中文英文都数得准）。
// 【为什么用 rune】中文字符在内存里占 3 个字节，len(s) 在 Go 里数的是"字节数"，
// 会把人数的 500 字错算成 1500 字节。所以要先转成 rune（Unicode 码点）再数。
func runeLen(s string) int { return utf8.RuneCountInString(s) }

// splitBy 按分隔符拆，把空段丢弃。
// 例：splitBy("中\n\n英", "\n\n") → ["中", "英"]
func splitBy(s, sep string) []string {
	var out []string
	for _, part := range strings.Split(s, sep) {
		if strings.TrimSpace(part) != "" {
			out = append(out, part)
		}
	}
	return out
}

// splitSentences 按句末标点拆句，标点随句保留（检索时上下文更完整）。
// 支持中文的 。！？； 和英文的 . ! ? ;  遇到这些字符就把"攒到现在的字"收尾成一句。
func splitSentences(s string) []string {
	seps := "。！？!?；;"
	var out []string
	var cur []rune
	for _, r := range s {
		cur = append(cur, r)
		if strings.ContainsRune(seps, r) {
			if x := strings.TrimSpace(string(cur)); x != "" {
				out = append(out, x)
			}
			cur = cur[:0] // 清空，开始攒下一句
		}
	}
	if x := strings.TrimSpace(string(cur)); x != "" {
		out = append(out, x) // 最后可能还有没收尾的
	}
	return out
}

// hardSlice 超长文本硬切成 ≤size 的片段（实在没有自然边界时的兜底）。
func hardSlice(s string, size int) []string {
	rs := []rune(s)
	var out []string
	for i := 0; i < len(rs); i += size {
		end := i + size
		if end > len(rs) {
			end = len(rs)
		}
		if x := strings.TrimSpace(string(rs[i:end])); x != "" {
			out = append(out, x)
		}
	}
	return out
}

// chunkText 主切分算法（面试常考，见 decisions.md"切块策略"）：
//   1) 把文本切成更小的"写作单元"：优先按自然结构断——
//      段落(\n\n) → 行(\n) → 句子(句末标点) → 都没有才硬切。
//      道理：在自然的语义边界断开，比死板按字数切对检索更友好。
//   2) 贪心装块：把写作单元一个个攒进当前块，每块字符数 ≤ chunk_size。
//   3) 滑窗重叠：下一个块开头带上一个块末尾 chunk_overlap 个字符，
//      防止"一句话正好跨在两块之间"导致两边都不完整、检索时语义丢失。
func chunkText(text string, size int, overlap int) []string {
	text = strings.ReplaceAll(text, "\r\n", "\n") // Windows 换行符统一成 \n
	if overlap >= size {
		overlap = size - 1 // 重叠不能超过块大小（否则下一块几乎等于上一块）
	}
	if overlap < 0 {
		overlap = 0
	}

	// 第 1 步：切成"写作单元"（各级自然边界逐层降格）
	var units []string
	for _, para := range splitBy(text, "\n\n") { // 按段落（两个换行）
		for _, line := range splitBy(para, "\n") { // 段内按行（单个换行）
			if runeLen(line) <= size { // 行没超长，直接当一个单元
				units = append(units, line)
				continue
			}
			// 行超长：先在行内按句子切
			for _, sent := range splitSentences(line) {
				if runeLen(sent) > size {
					units = append(units, hardSlice(sent, size)...) // 句子还超长才硬切
				} else {
					units = append(units, sent)
				}
			}
		}
	}

	// 第 2 步 + 第 3 步：贪心装块 + 滑窗重叠
	var chunks []string
	var cur []rune
	// flush：把当前攒的 cur 收尾成一块，然后带上"上一块尾巴"开始新的一块（=重叠）
	flush := func(tail []rune) {
		if x := strings.TrimSpace(string(cur)); x != "" {
			chunks = append(chunks, x)
		}
		cur = append([]rune(nil), tail...)
	}
	for _, u := range units {
		ur := []rune(u)
		// 再加这个单元就超限了，且当前块不为空 → 先收尾这块
		if len(cur) > 0 && len(cur)+len(ur) > size {
			var tail []rune
			if overlap > 0 && len(cur) >= overlap {
				tail = append([]rune(nil), cur[len(cur)-overlap:]...) // 取当前块末尾 overlap 个字符
			}
			flush(tail)
		}
		cur = append(cur, ur...)
	}

	if x := strings.TrimSpace(string(cur)); x != "" {
		chunks = append(chunks, x) // 收尾最后一块
	}
	return chunks
}

// handleChunk：/chunk 接口的处理函数（相当于 FastAPI 的一个路由视图函数）。
func handleChunk(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost { // 只接受 POST
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	var req chunkRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil { // 解析请求体 JSON
		http.Error(w, `{"error":"bad request"}`, http.StatusBadRequest)
		return
	}
	size, overlap := req.ChunkSize, req.ChunkOverlap
	if size <= 0 {
		size = 500 // 默认块大小：约 500 个字符
	}
	if overlap < 0 {
		overlap = 0
	}
	w.Header().Set("Content-Type", "application/json")
	chunks := chunkText(req.Text, size, overlap)
	_ = json.NewEncoder(w).Encode(chunkResponse{Count: len(chunks), Chunks: chunks}) // 编码并写回
}

// main：Go 程序的入口（类似 Python 的 if __name__ == "__main__"）。
func main() {
	addr := os.Getenv("CHUNKER_ADDR") // 允许用环境变量改端口
	if addr == "" {
		addr = ":8080" // 默认监听 8080
	}
	http.HandleFunc("/chunk", handleChunk) // 注册路由
	http.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	log.Printf("chunker listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil { // 启动服务并阻塞
		log.Fatal(err)
	}
}
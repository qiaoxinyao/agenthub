// AgentHub 切分微服务（Go）
//
// 职责：只做一件事——把一段纯文本按"滑窗 + 重叠"切成若干块，供 RAG 检索。
// 设计约束：无状态、不碰 PDF 解析、不碰向量，纯文本进、纯文本出（约 130 行）。
// 对齐 JD 的 Go 技能点；重活（PDF 提取、Embedding）留在 Python 侧。
//
// 接口：
//   POST /chunk   {"text":"...", "chunk_size":500, "chunk_overlap":50}
//                  → {"count":n, "chunks":["...", ...]}
//   GET  /health  → {"status":"ok"}
package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"
	"unicode/utf8"
)

type chunkRequest struct {
	Text         string `json:"text"`
	ChunkSize    int    `json:"chunk_size"`
	ChunkOverlap int    `json:"chunk_overlap"`
}

type chunkResponse struct {
	Count  int      `json:"count"`
	Chunks []string `json:"chunks"`
}

// runeLen 按"字符数"计长（中文英文都数得准，因为是 Unicode 码点）。
func runeLen(s string) int { return utf8.RuneCountInString(s) }

// splitBy 按分隔符拆，丢弃空段。
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
			cur = cur[:0]
		}
	}
	if x := strings.TrimSpace(string(cur)); x != "" {
		out = append(out, x)
	}
	return out
}

// hardSlice 超长文本硬切成 ≤size 的片段。
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

// chunkText 主切分算法：
//   1) 把文本切成"写作单元"：段落(\n\n) → 行(\n) → 句子(句末标点) → 硬切，
//      逐级降格，尽量在自然边界断开；
//   2) 贪心装块：每块字符数 ≤ chunk_size；
//   3) 滑窗重叠：下一个块的开头带上一个块的末尾 chunk_overlap 个字符，
//      保证跨块语义不丢（面试可讲的 RAG 切块策略）。
func chunkText(text string, size int, overlap int) []string {
	text = strings.ReplaceAll(text, "\r\n", "\n")
	if overlap >= size {
		overlap = size - 1
	}
	if overlap < 0 {
		overlap = 0
	}

	// 1) 切成写作单元
	var units []string
	for _, para := range splitBy(text, "\n\n") {
		for _, line := range splitBy(para, "\n") {
			if runeLen(line) <= size {
				units = append(units, line)
				continue
			}
			// 行超限：先按句拆
			for _, sent := range splitSentences(line) {
				if runeLen(sent) > size {
					units = append(units, hardSlice(sent, size)...)
				} else {
					units = append(units, sent)
				}
			}
		}
	}

	// 2) 贪心装块 + 滑窗重叠
	var chunks []string
	var cur []rune
	flush := func(tail []rune) {
		if x := strings.TrimSpace(string(cur)); x != "" {
			chunks = append(chunks, x)
		}
		cur = append([]rune(nil), tail...)
	}
	for _, u := range units {
		ur := []rune(u)
		if len(cur) > 0 && len(cur)+len(ur) > size {
			var tail []rune
			if overlap > 0 && len(cur) >= overlap {
				tail = append([]rune(nil), cur[len(cur)-overlap:]...)
			}
			flush(tail)
		}
		cur = append(cur, ur...)
	}

	if x := strings.TrimSpace(string(cur)); x != "" {
		chunks = append(chunks, x)
	}
	return chunks
}

func handleChunk(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method not allowed"}`, http.StatusMethodNotAllowed)
		return
	}
	var req chunkRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
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
	_ = json.NewEncoder(w).Encode(chunkResponse{Count: len(chunks), Chunks: chunks})
}

func main() {
	addr := os.Getenv("CHUNKER_ADDR")
	if addr == "" {
		addr = ":8080"
	}
	http.HandleFunc("/chunk", handleChunk)
	http.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	log.Printf("chunker listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatal(err)
	}
}
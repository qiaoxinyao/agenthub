# Go 切分微服务 Dockerfile
FROM golang:1.21-alpine AS builder

WORKDIR /build

# 复制 Go 模块文件
COPY go.mod .
RUN go mod download

# 复制源代码
COPY . .

# 编译（静态链接，无依赖）
RUN CGO_ENABLED=0 GOOS=linux go build -o chunker .

# 最终镜像（极小）
FROM alpine:latest

WORKDIR /app

# 安装 CA 证书（访问外部 API 需要）
RUN apk --no-cache add ca-certificates

# 从 builder 复制编译好的二进制
COPY --from=builder /build/chunker .

# 暴露端口
EXPOSE 8080

# 运行
CMD ["./chunker"]

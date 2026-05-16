# 模块: server.services.minio_storage

## 职责

- 解析外部接口文档中的 `minioPath`
- 将后端代理收到的 PDF 上传到本系统部署的 MinIO
- 从本系统部署的 MinIO 下载 PDF 到本地 pipeline 输入目录

## 行为规范

- `minioPath` 必须使用 `bucket/key` 格式，也兼容 `s3://bucket/key`
- 上传时由调用方传入 bucket 与 object key，helper 会在 bucket 缺失时自动创建
- 下载目标由调用方指定，通常是 `data/pdfs/{docId}.pdf`
- MinIO 连接信息来自 `ServerConfig` 的 `MINIO_ENDPOINT`、`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`MINIO_SECURE`

## 依赖关系

- 依赖 `minio.Minio`
- 被 `server.api.v1.documents` 调用

"""QA-domain error hierarchy for graded error handling."""

from __future__ import annotations


class QAError(Exception):
    """Base for all QA-domain errors."""

    code: int = 500
    message: str = "内部错误"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.message
        super().__init__(self.detail)


class LLMUnavailableError(QAError):
    """LLM timeout or 5xx."""

    code = 502
    message = "语言模型暂时不可用，请稍后重试"


class RetrievalUnavailableError(QAError):
    """Milvus / Elasticsearch unavailable."""

    code = 502
    message = "检索服务暂时不可用，请稍后重试"


class RequestTimeoutError(QAError):
    """Entire request exceeded the wall-clock deadline."""

    code = 504
    message = "请求处理超时，请简化问题或稍后重试"


class InvalidRequestError(QAError):
    """Malformed or invalid request parameters."""

    code = 400
    message = "请求参数无效"

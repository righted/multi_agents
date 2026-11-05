FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_CACHE_DIR=/tmp/uv-cache

# uv / uvx：stdio 类 MCP（如 mcp-server-time）运行时要用
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 依赖单独一层，改代码不用重装
COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY app ./app
COPY mcp ./mcp
COPY data ./data

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

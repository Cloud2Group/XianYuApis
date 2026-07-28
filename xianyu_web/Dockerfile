# ---- 构建阶段：安装 Node.js ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 安装 Node.js 18.x
RUN apt-get update && apt-get install -y curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Build from the repository root:
# docker build -f xianyu_web/Dockerfile -t xianyuapis-web .
COPY xianyu_web/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# Web 运行代码集中在单独的 Python package 中。
COPY xianyu_web ./xianyu_web

# 默认运行主进程（接收消息 + 自动回复）
CMD ["python", "-m", "xianyu_web.goofish_live"]

# --- 构建 & 运行 ---
# docker build -f xianyu_web/Dockerfile -t xianyuapis-web .
# docker run -it --env-file xianyu_web/.env.dev xianyuapis-web

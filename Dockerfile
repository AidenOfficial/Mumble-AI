# Python 3.12（不要 3.13：audioop 被移除、pymumble 未验证）
FROM python:3.12-slim

# libopus0: pymumble 通过 ctypes 加载它来解/编码 Opus
# build-essential: 仅在 arm64 上若 soxr/numpy 无 wheel 时本地编译用（确认有 wheel 后可移到多阶段构建丢弃以瘦身）
RUN apt-get update && apt-get install -y --no-install-recommends \
        libopus0 build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mumble_bot/ ./mumble_bot/

# 非 root 运行
RUN useradd -m bot && mkdir -p /app/data && chown -R bot /app
USER bot

ENTRYPOINT ["python", "-m", "mumble_bot.main"]

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc g++ build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 直接 COPY 本地模型，不从网络下载
COPY models/ /app/.cache/huggingface/

EXPOSE 8000
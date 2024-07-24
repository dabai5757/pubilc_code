# 使用 NVIDIA CUDA 作为基础镜像
FROM nvidia/cuda:12.2.2-cudnn8-devel-ubuntu22.04

# 设置工作目录
WORKDIR /var/www/ai_server

# 更新包列表并安装必要的系统依赖
RUN apt-get update \
    && apt-get install -y \
        python3 \
        python3-pip \
        wget \
        build-essential \
        ca-certificates \
        libsndfile1-dev \
        libgl1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

# 安装 openai-whisper
# RUN pip3 install openai-whisper

# 复制应用代码到容器中
COPY . .

# 预先下载并加载模型
#RUN python3 -c 'from faster_whisper import WhisperModel; model = WhisperModel("large-v2", device="cpu", num_workers=4, cpu_threads=4)'

# 暴露 Flask 应用的端口
EXPOSE 5004

# 运行 Python 应用
CMD ["python3", "translation.py"]

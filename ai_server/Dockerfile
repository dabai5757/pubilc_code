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
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 安装额外的 Python 包
RUN pip install flask requests pymysql concurrent-log-handler numba

# 设置 Python 3.11 环境变量
ENV PATH="/usr/bin/python3.11:${PATH}"

# 复制应用代码到容器中
COPY . .

# 暴露 Flask 应用的端口
EXPOSE 5004

# 运行 Python 应用
CMD ["python3", "sleep.py"]

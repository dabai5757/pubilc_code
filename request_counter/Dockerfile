# 使用官方Python基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制Python脚本到工作目录
COPY request_counter.py .

# 运行脚本
CMD ["python", "request_counter.py"]
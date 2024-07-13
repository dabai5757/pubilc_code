# 使用带有 Python 和 Flask 的基础镜像
FROM python:3.9-slim

# 安装 Docker 客户端和 Nginx
RUN apt-get update && apt-get install -y docker.io nginx

# 设置工作目录
WORKDIR /usr/src/app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install requests

# 复制 Flask 应用和其他脚本
COPY auto_scaling.py .
COPY entrypoint.sh .
# COPY nginx.conf.template .

# 确保入口脚本可执行
RUN chmod +x entrypoint.sh

# 创建运行目录
RUN mkdir -p /run

# 指定容器启动时执行的命令
ENTRYPOINT ["./entrypoint.sh"]

#!/bin/bash

# 启动Nginx
nginx -c /app/nginx/nginx.conf

# 启动Flask应用
python auto_scaling.py

# 防止容器退出
tail -f /dev/null

# Copyright 2026 XDU Reminder Service
# Dockerfile for Synology NAS / Linux server

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置时区为中国标准时间
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 拷贝项目源码
COPY . .

# 暴露 Web 端口
EXPOSE 5800

# 数据卷挂载 (包含配置、Cookie、缓存与日志)
VOLUME ["/app/data"]

# 启动服务
CMD ["python", "main.py", "--data-dir", "/app/data", "--no-browser"]

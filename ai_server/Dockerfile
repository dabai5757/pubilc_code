FROM nvidia/cuda:12.2.2-cudnn8-devel-ubuntu22.04

WORKDIR /var/www/ai_server

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

COPY requirements.txt .
RUN pip3 install --upgrade pip && \
    pip3 install -r requirements.txt

COPY . .

EXPOSE 5004

CMD ["python3", "translation.py"]

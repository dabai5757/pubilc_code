FROM python:3.11

WORKDIR /var/www/backend

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

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install requests

RUN pip3 install numba

COPY . .

CMD ["python3", "AIBT.py"]

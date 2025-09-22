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
        ffmpeg \
    && apt-get install -y net-tools iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install requests

RUN pip install librosa soundfile

RUN pip3 install numba

COPY util_debug.py .
COPY . .

CMD ["python3", "AIBT.py"]

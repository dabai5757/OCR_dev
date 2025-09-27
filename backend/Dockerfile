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

# librosa/soundfile/numba are installed via requirements.txt, but keep explicit installs in case
RUN pip install librosa soundfile || true
RUN pip3 install numba || true

COPY . .

CMD ["sh", "-c", "uvicorn AIBT:app --host 0.0.0.0 --port ${BACKEND_CONTAINER_PORT:-5560}"]

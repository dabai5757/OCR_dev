# FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04


# タイムゾーン設定
ENV TZ=Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    build-essential \
    curl \
    wget \
    git \
    ca-certificates \
    poppler-utils \
    libopencv-dev \
    python3.10 \
    python3.10-dev \
    python3-pip \
    python3-setuptools \
    python3-distutils \
    && rm -rf /var/lib/apt/lists/*

# Pythonのシンボリックリンク作成
RUN ln -sf /usr/bin/python3.10 /usr/bin/python

# 依存関係のインストール
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# PDF処理に必要なライブラリを追加でインストール
RUN pip3 install --no-cache-dir pdf2image Pillow

# YomiToku のインストール
RUN pip3 install --no-cache-dir yomitoku

# アプリケーションディレクトリの作成
WORKDIR /app
COPY ./app/* /app/

# 清理脚本和启动脚本の追加
COPY cleanup_static.sh /app/
COPY manual_cleanup.sh /app/
COPY start.sh /app/
RUN chmod +x /app/cleanup_static.sh /app/manual_cleanup.sh /app/start.sh

# staticディレクトリの作成（マウント用）
RUN mkdir -p /static && chmod 777 /static

# cron をインストール（定期清理用）
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# 定期清理の設定（毎日午前2時に実行）
RUN echo "0 2 * * * /app/cleanup_static.sh" | crontab -

# 環境変数の設定
ENV FLASK_APP=main.py
ENV FLASK_ENV=production

# ポートの公開
EXPOSE 5550

# アプリケーションの起動
CMD ["bash", "-c", "service cron start && python main.py --server"]
import warnings
from numba.core.errors import NumbaDeprecationWarning
warnings.filterwarnings('ignore', category=NumbaDeprecationWarning)
warnings.filterwarnings("ignore", "FP16 is not supported on CPU; using FP32 instead")

from flask import Flask, request, jsonify, g, send_from_directory, make_response
import mysql.connector
import sys
import os
import io
import shutil
import traceback
import time
from threading import Lock
from datetime import datetime, timedelta
from math import floor
import locale
import logging
from flask_cors import CORS
from werkzeug.utils import secure_filename
import requests
import re
import json
import mimetypes
import subprocess
# from translation_tasks import check_translation_result
import asyncio
import uuid

app = Flask(__name__)
CORS(
    app
)

os.environ["PYTHONIOENCODING"] = "UTF-8"

ai_server_container_port = os.getenv('AI_SERVER_CONTAINER_PORT')
ai_server_container_url = f"http://ai:{ai_server_container_port}/api/aibt/ai_server"

previous_result = {}     # client_idごとの結果を保存する辞書を初期化
result_lock = Lock()     # 結果の辞書を保護するためのロックを作成
first_time = 0           # 初回呼出しされた時間を保持
transcribe_duration = 0  # transcribeの滞在時間を保存するグローバル変数を初期化
transcribe_lock = Lock() # transcribe関数を保護するためのロックを作成
duration_lock = Lock()   # 滞在時間を保護するためのロックを作成

TABLE_TRANSLATION_API="sound_files_api"
TABLE_TRANSLATION="sound_files"
DATABASE="sound_files_db"
HOST = os.getenv("DB_HOST")
PORT = os.getenv("MYSQL_CONTAINER_PORT")
PASSWORD = os.getenv("DB_PASSWORD")

count = 0
MAX_RETRIES = 3
RETRY_INTERVAL = 10
# API_WAITTIME_TIME = 30
API_WAITTIME_TIME = 60

log_path =  "app.log"
logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",filename=log_path)
os.chmod(log_path, 0o644)

try:
    logging.basicConfig(filename='log_cui_info.log', level=logging.INFO, encoding='utf-8')
    # os.chmod('log_cui_info.log', 0o644)
except Exception as e:
    # Tkinter の MainThread からは呼び出せないので messagebox は使えない
    print(traceback.format_exc())
    raise

pipe            = None
assistant_model = None
output_file = None
audio_model = None  # グローバル変数としてaudio_modelを初期化
dtime_1st = None
dtime_old = None

SERVER_ADDRESS = os.getenv("SERVER_ADDRESS", "192.168.10.9")
NGINX_PORT = int(os.getenv("NGINX_PORT", 33380))

def connect_to_database(HOST, DATABASE, PASSWORD, PORT):
    logging.info(">connect_to_database():")
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            connection = mysql.connector.connect(
                host=HOST,
                database=DATABASE,
                user='root',
                password=PASSWORD,
                port=PORT
            )
            return connection
        except mysql.connector.Error as e:
            logging.error(f"Error occurred during database connection: {str(e)}")
            print(f"再試行します...({retry_count+1}/{MAX_RETRIES})")
            logging.warning(f"再試行します...({retry_count+1}/{MAX_RETRIES})")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL)
            continue

    logging.error("データベースに接続できませんでした。リトライ回数を超えました。")
    exit

@app.before_request
def initialize():
    """
    Initialize database connection before handling request.
    """
    logging.info(">initialize():")
    try:
        g.connection = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
        if g.connection.is_connected():
            return
    except Exception as e:
        logging.error(f"Error occurred during database connection: {str(e)}")
        return

@app.teardown_request
def close_connection(exception):
    """
    Close database connection after handling request.
    """
    logging.info(">close_connection():")
    connection = getattr(g, 'connection', None)
    if connection is not None:
        connection.close()


@app.route('/api/aibt/transcribe', methods=['POST'])
def transcribe_audio():
    logging.info(">transcribe_audio():")
    cursor = None
    connection = None


@app.route('/api/aibt/get_url', methods=['POST'])
def get_url():
    logging.info(">get_url():")


@app.route('/api/estimated_completion_time', methods=['GET'])
def estimated_completion_time():
    try:
        conn = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT SUM(audio_length) as total_length
            FROM sound_files
            WHERE status IN ('pending', 'processing')
        """)
        total_length = cursor.fetchone()['total_length']
        cursor.close()
        conn.close()

        if total_length is None:
            total_length = 0

        # 目安完了時間計算
        estimated_seconds = total_length / 4
        # estimated_seconds = total_length / 8
        estimated_minutes = estimated_seconds // 60
        estimated_seconds = estimated_seconds % 60

        now = datetime.now() + timedelta(hours=9)
        completion_time = now + timedelta(minutes=int(estimated_minutes), seconds=int(estimated_seconds))
        estimated_time = completion_time.strftime("%H:%M")

        return jsonify({"estimated_time": estimated_time})
    except Exception as e:
        logging.error(f"Error calculating estimated completion time: {str(e)}")
        return jsonify({"error": "Internal Server Error"}), 500


# 翻訳結果削除関数
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
import logging

def clean_expired_result_urls():
   connection = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
   cursor = connection.cursor()

   # 現在時刻を取得
   current_time = datetime.now()

   # TABLE_TRANSLATION_APIテーブルの処理
   # result_urlとtext_contentをNULLに設定（text_contentがNULLでない場合のみ）
   cursor.execute(f"""
       UPDATE `{TABLE_TRANSLATION_API}`
       SET result_url = NULL, text_content = NULL
       WHERE translation_end_time IS NOT NULL
       AND status = 'completed'
       AND result_url IS NOT NULL
       AND text_content IS NOT NULL
       AND TIMESTAMPDIFF(HOUR, translation_end_time, %s) >= 1
   """, (current_time,))

   # TABLE_TRANSLATIONテーブルの処理
   # result_urlのみをNULLに設定
   cursor.execute(f"""
       UPDATE `{TABLE_TRANSLATION}`
       SET result_url = NULL
       WHERE translation_end_time IS NOT NULL
       AND status = 'completed'
       AND result_url IS NOT NULL
       AND TIMESTAMPDIFF(HOUR, translation_end_time, %s) >= 1
   """, (current_time,))

   connection.commit()
   cursor.close()
   connection.close()
   # logging.info(f"期限切れのresult_urlをクリアしました。(チェック時刻: {current_time})")

# スケジューラーの設定（1時間ごとに実行）
clean_expired_result_urls()
scheduler = BackgroundScheduler()
scheduler.add_job(clean_expired_result_urls, 'interval', hours=1)
# scheduler.add_job(clean_expired_result_urls, 'interval', seconds=10)  # テスト用
scheduler.start()
#--------------------------------------------------------------------------------------------------------------------------
# main
if __name__ == '__main__':
    if os.getenv('TAG', '').lower() == 'dev':
        from util_debug import attach_debugger
        debug_thread = attach_debugger(port=5674)
    app.run(host='0.0.0.0', port=port, debug=False)

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


TABLE_OCR="ocr_files"
DATABASE="ocr_files_db"
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
port = int(os.getenv("BACKEND_CONTAINER_PORT", 5000))

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

@app.route('/api/aibt/ocr', methods=['POST'])
def ocr_request():
    logging.info(">ocr_request():")
    cursor = None
    connection = None

    try:
        # 检查请求中是否包含文件
        if 'file' not in request.files:
            return jsonify({"error": "没有上传文件"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "文件名为空"}), 400

        # 获取其他参数
        file_type = request.form.get('file_type', 'unknown')
        file_size = request.form.get('file_size', '0')
        range_start = request.form.get('range_start')
        range_end = request.form.get('range_end')
        page_count = request.form.get('page_count')

        # 生成唯一的任务ID
        task_id = str(uuid.uuid4())

        # 确保input_audio_files目录存在
        upload_dir = os.path.join(os.path.dirname(__file__), 'input_audio_files')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        # 保存文件
        filename = secure_filename(file.filename)
        if not filename:
            filename = f"{task_id}_{file_type}"

        # 添加时间戳避免文件名冲突
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(upload_dir, filename)

        file.save(file_path)
        logging.info(f"文件已保存到: {file_path}")

        # 保存到数据库
        connection = g.connection
        cursor = connection.cursor()

        # 插入OCR请求记录到数据库（使用ocr_files表）
        insert_query = f"""
            INSERT INTO {TABLE_OCR}
            (file_name, original_filename, file_path, file_size, file_type,
             page_count, range_start, range_end, status, upload_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        now = datetime.now()

        cursor.execute(insert_query, (
            filename,  # 处理后的文件名
            file.filename,  # 原始文件名
            file_path,  # 文件保存路径
            int(file_size),
            file_type,
            int(page_count) if page_count else None,
            int(range_start) if range_start else None,
            int(range_end) if range_end else None,
            'pending',
            now
        ))

        # 获取插入记录的ID作为task_id
        task_id = cursor.lastrowid

        connection.commit()
        logging.info(f"OCR请求已保存到数据库，任务ID: {task_id}")

        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "OCR请求已提交，正在处理中",
            "filename": filename
        }), 200

    except mysql.connector.Error as db_error:
        logging.error(f"数据库错误: {str(db_error)}")
        if connection:
            connection.rollback()
        return jsonify({"error": f"数据库操作失败: {str(db_error)}"}), 500

    except Exception as e:
        logging.error(f"OCR请求处理错误: {str(e)}")
        logging.error(traceback.format_exc())
        if connection:
            connection.rollback()
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()


@app.route('/api/aibt/ocr/status/<task_id>', methods=['GET'])
def get_ocr_status(task_id):
    logging.info(f">get_ocr_status(): task_id={task_id}")

    try:
        connection = g.connection
        cursor = connection.cursor(dictionary=True)

        # 查询任务状态
        query = f"""
            SELECT ocr_id, file_name, original_filename, file_path, file_size, file_type,
                   page_count, range_start, range_end, status, upload_time,
                   text_content, result_url, error_message, processing_start_time, processing_end_time
            FROM {TABLE_OCR}
            WHERE ocr_id = %s
        """

        cursor.execute(query, (task_id,))
        result = cursor.fetchone()

        if not result:
            return jsonify({"error": "任务不存在"}), 404

        return jsonify({
            "success": True,
            "task_id": result['ocr_id'],
            "status": result['status'],
            "filename": result['file_name'],
            "original_filename": result['original_filename'],
            "file_path": result['file_path'],
            "file_type": result['file_type'],
            "file_size": result['file_size'],
            "page_count": result['page_count'],
            "range_start": result['range_start'],
            "range_end": result['range_end'],
            "upload_time": result['upload_time'].isoformat() if result['upload_time'] else None,
            "processing_start_time": result['processing_start_time'].isoformat() if result['processing_start_time'] else None,
            "processing_end_time": result['processing_end_time'].isoformat() if result['processing_end_time'] else None,
            "ocr_result": result['text_content'],
            "result_url": result['result_url'],
            "error_message": result['error_message']
        }), 200

    except mysql.connector.Error as db_error:
        logging.error(f"数据库错误: {str(db_error)}")
        return jsonify({"error": f"数据库查询失败: {str(db_error)}"}), 500

    except Exception as e:
        logging.error(f"查询OCR状态错误: {str(e)}")
        logging.error(traceback.format_exc())
        return jsonify({"error": f"服务器内部错误: {str(e)}"}), 500

    finally:
        if cursor:
            cursor.close()


@app.route('/api/estimated_completion_time', methods=['GET'])
def estimated_completion_time():
    try:
        conn = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"""
            SELECT SUM(file_size) as total_size
            FROM {TABLE_OCR}
            WHERE status IN ('pending', 'processing')
        """)
        total_size = cursor.fetchone()['total_size']
        cursor.close()
        conn.close()

        if total_size is None:
            total_size = 0

        # 目安完了時間計算（OCRの場合、ファイルサイズベースで推定）
        # 1MBあたり約10秒として計算
        estimated_seconds = (total_size / 1024 / 1024) * 10
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

   # OCR_FILESテーブルの処理
   # result_urlとtext_contentをNULLに設定（text_contentがNULLでない場合のみ）
   cursor.execute(f"""
       UPDATE `{TABLE_OCR}`
       SET result_url = NULL, text_content = NULL
       WHERE processing_end_time IS NOT NULL
       AND status = 'completed'
       AND result_url IS NOT NULL
       AND text_content IS NOT NULL
       AND TIMESTAMPDIFF(HOUR, processing_end_time, %s) >= 1
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

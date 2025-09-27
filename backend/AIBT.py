import warnings
from numba.core.errors import NumbaDeprecationWarning

warnings.filterwarnings('ignore', category=NumbaDeprecationWarning)
warnings.filterwarnings("ignore", "FP16 is not supported on CPU; using FP32 instead")

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import mysql.connector
import os
import shutil
import traceback
import logging
from datetime import datetime, timedelta
from threading import Lock
from math import floor
import uuid
from typing import Generator, Optional
import time

from PyPDF2 import PdfReader, PdfWriter
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler

# --------------------------------------------------------------------------------------
# Application setup
# --------------------------------------------------------------------------------------

app = FastAPI(title="AIBT OCR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.environ["PYTHONIOENCODING"] = "UTF-8"

ai_server_container_port = os.getenv('AI_SERVER_CONTAINER_PORT')
ai_server_container_url = f"http://ai:{ai_server_container_port}/api/aibt/ai_server" if ai_server_container_port else None

previous_result = {}
result_lock = Lock()
first_time = 0
transcribe_duration = 0
transcribe_lock = Lock()
duration_lock = Lock()

TABLE_OCR = "ocr_files"
DATABASE = "ocr_files_db"
HOST = os.getenv("DB_HOST")
PORT = os.getenv("MYSQL_CONTAINER_PORT")
PASSWORD = os.getenv("DB_PASSWORD")

MAX_RETRIES = 3
RETRY_INTERVAL = 10
API_WAITTIME_TIME = 60

log_path = "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",
    filename=log_path
)
os.chmod(log_path, 0o644)

try:
    logging.basicConfig(filename='log_cui_info.log', level=logging.INFO, encoding='utf-8')
except Exception:
    print(traceback.format_exc())
    raise

SERVER_ADDRESS = os.getenv("SERVER_ADDRESS", "192.168.10.9")
NGINX_PORT = int(os.getenv("NGINX_PORT", 33380))
BACKEND_PORT = int(os.getenv("BACKEND_CONTAINER_PORT", 5560))

scheduler = BackgroundScheduler()

# --------------------------------------------------------------------------------------
# Database utilities
# --------------------------------------------------------------------------------------

def connect_to_database(host: Optional[str], database: str, password: Optional[str], port: Optional[str]):
    logging.info(">connect_to_database():")
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            connection = mysql.connector.connect(
                host=host,
                database=database,
                user='root',
                password=password,
                port=port
            )
            if connection.is_connected():
                return connection
        except mysql.connector.Error as error:
            logging.error(f"Error occurred during database connection: {error}")
            logging.warning(f"Retrying... ({retry_count + 1}/{MAX_RETRIES})")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                time_to_sleep = RETRY_INTERVAL
                logging.info(f"Sleeping {time_to_sleep} seconds before retry")
                time.sleep(time_to_sleep)
    logging.error("Failed to connect to database after retries")
    raise RuntimeError("数据库连接失败")


def get_db() -> Generator[mysql.connector.MySQLConnection, None, None]:
    try:
        connection = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    try:
        yield connection
    finally:
        if connection.is_connected():
            connection.close()

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def normalize_page_range(start: Optional[str], end: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    try:
        range_start = int(start) if start else None
        range_end = int(end) if end else None
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的页码范围")

    if range_start and not range_end:
        range_end = range_start
    if range_end and not range_start:
        range_start = 1

    return range_start, range_end


def ensure_upload_dir() -> str:
    upload_dir = os.path.join(os.path.dirname(__file__), 'input_audio_files')
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def save_upload_file(upload: UploadFile, destination: str) -> None:
    upload.file.seek(0)
    with open(destination, 'wb') as buffer:
        shutil.copyfileobj(upload.file, buffer)


def trim_pdf_if_needed(file_path: str, filename: str, file_type: str,
                       range_start: Optional[int], range_end: Optional[int]) -> tuple[str, str, int]:
    stored_file_size = os.path.getsize(file_path)

    if file_type != 'pdf' or not (range_start and range_end):
        return file_path, filename, stored_file_size

    try:
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)

        if range_start < 1 or range_end > total_pages or range_start > range_end:
            os.remove(file_path)
            raise HTTPException(status_code=400, detail="页码范围超出PDF页面数量")

        writer = PdfWriter()
        for page_index in range(range_start - 1, range_end):
            writer.add_page(reader.pages[page_index])

        trimmed_filename = f"{os.path.splitext(filename)[0]}_pages_{range_start}-{range_end}.pdf"
        trimmed_path = os.path.join(os.path.dirname(file_path), trimmed_filename)

        with open(trimmed_path, 'wb') as trimmed_file:
            writer.write(trimmed_file)

        os.remove(file_path)
        stored_file_size = os.path.getsize(trimmed_path)
        logging.info(
            "PDF trimmed by range: %s (total %s -> %s pages)",
            trimmed_path,
            total_pages,
            range_end - range_start + 1
        )
        return trimmed_path, trimmed_filename, stored_file_size
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"PDF range extraction failed: {exc}")
        os.remove(file_path)
        raise HTTPException(status_code=500, detail="PDF 页码提取失败")

# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------

@app.post("/api/aibt/ocr")
async def ocr_request(
    file: UploadFile = File(...),
    file_type: str = Form("unknown"),
    file_size: str = Form("0"),
    range_start: Optional[str] = Form(None),
    range_end: Optional[str] = Form(None),
    page_count: Optional[str] = Form(None),
    connection: mysql.connector.MySQLConnection = Depends(get_db)
):
    logging.info(">ocr_request():")

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    normalized_file_type = (file_type or 'unknown').lower()
    range_start_value, range_end_value = normalize_page_range(range_start, range_end)

    try:
        task_id = str(uuid.uuid4())
        upload_dir = ensure_upload_dir()

        sanitized_name = secure_filename(file.filename) or f"{task_id}_{normalized_file_type}"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stored_filename = f"{timestamp}_{sanitized_name}"
        stored_path = os.path.join(upload_dir, stored_filename)

        save_upload_file(file, stored_path)
        logging.info(f"文件已保存到: {stored_path}")

        stored_path, stored_filename, stored_file_size = trim_pdf_if_needed(
            stored_path,
            stored_filename,
            normalized_file_type,
            range_start_value,
            range_end_value
        )

        cursor = connection.cursor()
        insert_query = f"""
            INSERT INTO {TABLE_OCR}
            (file_name, original_filename, file_path, file_size, file_type,
             page_count, range_start, range_end, status, upload_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        now = datetime.now()
        cursor.execute(insert_query, (
            stored_filename,
            file.filename,
            stored_path,
            stored_file_size,
            normalized_file_type,
            int(page_count) if page_count else None,
            range_start_value,
            range_end_value,
            'pending',
            now
        ))

        connection.commit()
        task_db_id = cursor.lastrowid
        cursor.close()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "task_id": task_db_id,
                "message": "OCR请求已提交，正在处理中",
                "filename": stored_filename
            }
        )
    except mysql.connector.Error as db_error:
        logging.error(f"数据库错误: {db_error}")
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"数据库操作失败: {db_error}")
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"OCR请求处理错误: {exc}")
        logging.error(traceback.format_exc())
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {exc}")


@app.get("/api/aibt/ocr/status/{task_id}")
async def get_ocr_status(task_id: int, connection: mysql.connector.MySQLConnection = Depends(get_db)):
    logging.info(f">get_ocr_status(): task_id={task_id}")

    try:
        cursor = connection.cursor(dictionary=True)
        query = f"""
            SELECT ocr_id, file_name, original_filename, file_path, file_size, file_type,
                   page_count, range_start, range_end, status, upload_time,
                   text_content, result_url, error_message, processing_start_time, processing_end_time
            FROM {TABLE_OCR}
            WHERE ocr_id = %s
        """
        cursor.execute(query, (task_id,))
        result = cursor.fetchone()
        cursor.close()

        if not result:
            raise HTTPException(status_code=404, detail="任务不存在")

        return JSONResponse(
            status_code=200,
            content={
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
            }
        )
    except mysql.connector.Error as db_error:
        logging.error(f"数据库错误: {db_error}")
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {db_error}")
    except HTTPException:
        raise
    except Exception as exc:
        logging.error(f"查询OCR状态错误: {exc}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {exc}")


@app.get("/api/estimated_completion_time")
async def estimated_completion_time(connection: mysql.connector.MySQLConnection = Depends(get_db)):
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(f"""
            SELECT SUM(file_size) as total_size
            FROM {TABLE_OCR}
            WHERE status IN ('pending', 'processing')
        """)
        total_size_row = cursor.fetchone()
        cursor.close()

        total_size = total_size_row['total_size'] if total_size_row else 0
        if total_size is None:
            total_size = 0

        estimated_seconds = (total_size / 1024 / 1024) * 10
        estimated_minutes = floor(estimated_seconds // 60)
        estimated_seconds = floor(estimated_seconds % 60)

        now = datetime.now() + timedelta(hours=9)
        completion_time = now + timedelta(minutes=estimated_minutes, seconds=estimated_seconds)
        estimated_time = completion_time.strftime("%H:%M")

        return JSONResponse(status_code=200, content={"estimated_time": estimated_time})
    except mysql.connector.Error as db_error:
        logging.error(f"数据库错误: {db_error}")
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {db_error}")
    except Exception as exc:
        logging.error(f"Error calculating estimated completion time: {exc}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# --------------------------------------------------------------------------------------
# Scheduled cleanup
# --------------------------------------------------------------------------------------

def clean_expired_result_urls() -> None:
    try:
        connection = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
    except RuntimeError as exc:
        logging.error(f"Clean-up aborted: {exc}")
        return

    cursor = connection.cursor(dictionary=True)

    current_time = datetime.now()

    expiration_query = f"""
        SELECT ocr_id, file_name, file_path
        FROM `{TABLE_OCR}`
        WHERE processing_end_time IS NOT NULL
          AND status = 'completed'
          AND text_content IS NOT NULL
          AND TIMESTAMPDIFF(MINUTE, processing_end_time, %s) >= 1
    """

    cursor.execute(expiration_query, (current_time,))
    expired_records = cursor.fetchall()

    for record in expired_records:
        file_path = record.get('file_path')
        file_name = record.get('file_name')

        if not file_path and file_name:
            file_path = os.path.join(os.path.dirname(__file__), 'input_audio_files', file_name)

        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logging.info(f"已删除过期OCR文件: {file_path}")
            except OSError as file_error:
                logging.error(f"删除过期OCR文件失败: {file_path} - {file_error}")

    cursor.execute(f"""
        UPDATE `{TABLE_OCR}`
        SET result_url = NULL,
            text_content = NULL
        WHERE processing_end_time IS NOT NULL
          AND status = 'completed'
          AND text_content IS NOT NULL
          AND TIMESTAMPDIFF(MINUTE, processing_end_time, %s) >= 1
    """, (current_time,))

    connection.commit()
    cursor.close()
    connection.close()


@app.on_event("startup")
def on_startup() -> None:
    clean_expired_result_urls()
    if not scheduler.get_jobs():
        scheduler.add_job(clean_expired_result_urls, 'interval', minutes=1, id="cleanup_job", replace_existing=True)
    if not scheduler.running:
        scheduler.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

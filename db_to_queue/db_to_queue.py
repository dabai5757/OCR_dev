import asyncio
import aiomysql
import aiohttp
import os
import logging
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'db': 'ocr_files_db',
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('MYSQL_CONTAINER_PORT'))
}

CONCURRENT_REQUESTS = 1
QUEUE_MAX_SIZE = 1
CHECK_INTERVAL = 5

log_path = "/logs/db_to_queue.log"

logger = logging.getLogger("db_to_queue")
logger.setLevel(logging.INFO)

if not logger.handlers:
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s - %(levelname)s:%(name)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

logger.info("Logging has been initialized successfully.")

API_URL = f"http://ocr-api:5000/ocr"
FILE_BASE_PATH = "/var/www/backend/input_audio_files"  # Docker container path


async def fetch_pending_ocr_tasks(queue: asyncio.Queue, stop_event: asyncio.Event):
    while not stop_event.is_set():
        if queue.qsize() < QUEUE_MAX_SIZE:
            conn: Optional[aiomysql.Connection] = None
            try:
                conn = await aiomysql.connect(**DB_CONFIG)
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT ocr_id, file_name, original_filename, file_path, file_type,
                               page_count, range_start, range_end, user_name
                        FROM ocr_files
                        WHERE status='pending'
                        ORDER BY upload_time ASC
                        LIMIT %s
                        """,
                        (QUEUE_MAX_SIZE - queue.qsize(),)
                    )
                    tasks = await cur.fetchall()
                    for task in tasks:
                        await cur.execute(
                            "UPDATE ocr_files SET status='processing', processing_start_time=NOW() WHERE ocr_id=%s",
                            (task[0],)
                        )
                        await conn.commit()
                        await queue.put(task)
                        logger.info(
                            "OCR Task %s added to queue with file_name %s, file_type %s. Queue size now %s",
                            task[0], task[1], task[4], queue.qsize()
                        )
            except Exception as exc:
                logger.error(f"Error fetching OCR tasks from database: {exc}")
            finally:
                if conn:
                    conn.close()
        else:
            logger.info("Queue is full, waiting for space to become available.")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=CHECK_INTERVAL)
        except asyncio.TimeoutError:
            continue

    logger.info("Fetch task loop stopped.")


async def process_ocr_task(queue: asyncio.Queue, semaphore: asyncio.Semaphore,
                           session: aiohttp.ClientSession, stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            task = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        if task is None:
            queue.task_done()
            break

        async with semaphore:
            ocr_id, file_name, original_filename, file_path, file_type, page_count, range_start, range_end, user_name = task

            logger.info(
                "Processing OCR task %s with file_name %s, file_type %s, user_name %s. Queue size before processing: %s",
                ocr_id, file_name, file_type, user_name, queue.qsize()
            )

            try:
                # 完全なファイルパスを構築
                full_file_path = os.path.join(FILE_BASE_PATH, file_name)

                # ファイルが存在するか確認
                if not os.path.exists(full_file_path):
                    logger.error(f"File not found: {full_file_path}")
                    await update_task_status(ocr_id, 'error', f"File not found: {full_file_path}")
                    queue.task_done()
                    continue

                # ファイル内容を読み込む
                with open(full_file_path, 'rb') as f:
                    file_content = f.read()

                # フォームデータを準備
                data = aiohttp.FormData()
                data.add_field('file', file_content, filename=original_filename or file_name,
                              content_type='application/pdf' if file_type == 'pdf' else 'image/*')
                data.add_field('file_type', file_type)
                data.add_field('file_size', str(os.path.getsize(full_file_path)))

                # user_nameパラメータを追加（存在する場合）
                if user_name:
                    data.add_field('user_name', user_name)

                if file_type == 'pdf' and page_count:
                    if range_start:
                        data.add_field('range_start', str(range_start))
                    if range_end:
                        data.add_field('range_end', str(range_end))
                    data.add_field('page_count', str(page_count))

                async with session.post(API_URL, data=data) as response:
                    if response.status == 200:
                        logger.info(f"OCR task {ocr_id} sent to API successfully.")
                        try:
                            response_data = await response.json()
                            logger.info(f"API Response: {response_data}")

                            # OCR処理が完了したか確認
                            if response_data.get('status') == 'success':
                                # OCR結果を抽出
                                ocr_result = ""
                                result_url = ""

                                # 異なるフィールドからOCR結果を取得しようとする
                                if 'markdown_content' in response_data:
                                    ocr_result = response_data['markdown_content']
                                elif 'content' in response_data:
                                    ocr_result = response_data['content']
                                elif 'merged_markdown' in response_data:
                                    # 返されたファイルパスからファイル内容を読み込む必要がある
                                    merged_markdown_path = response_data['merged_markdown']
                                    try:
                                        # 共有静的ファイルディレクトリから直接ファイル内容を読み込む
                                        full_file_path = merged_markdown_path  # パスは既に /static/... の形式
                                        with open(full_file_path, 'r', encoding='utf-8') as f:
                                            ocr_result = f.read()
                                        logger.info(f"Successfully read OCR result from {full_file_path}")
                                    except Exception as file_error:
                                        logger.error(f"Error reading merged markdown file {merged_markdown_path}: {file_error}")

                                if 'dl_url' in response_data:
                                    result_url = response_data['dl_url']

                                # データベースステータスをcompletedに更新し、OCR結果を保存
                                await update_task_status_with_result(ocr_id, 'completed', ocr_result, result_url)
                            else:
                                # OCR処理中、processingステータスを維持
                                logger.info(f"OCR task {ocr_id} is still processing...")

                        except Exception as json_error:
                            logger.error(f"Failed to parse JSON response: {json_error}")
                            response_text = await response.text()
                            logger.info(f"API Response (text): {response_text}")
                            # 解析に失敗しても処理完了とみなす（APIが200を返したため）
                            await update_task_status(ocr_id, 'completed')
                    else:
                        logger.error(f"Failed to send OCR task {ocr_id} to API: {response.status}")
                        error_text = await response.text()
                        logger.error(f"Response: {error_text}")
                        await update_task_status(ocr_id, 'error', f"API error: {response.status}")

            except Exception as e:
                logger.error(f"Exception occurred while processing OCR task {ocr_id}: {e}")
                await update_task_status(ocr_id, 'error', str(e))

            queue.task_done()
            logger.info(f"Finished processing OCR task {ocr_id}. Queue size after processing: {queue.qsize()}")

    logger.info("Process task loop stopped.")

async def update_task_status(ocr_id, status, error_message=None):
    """タスクステータスを更新"""
    try:
        conn = await aiomysql.connect(**DB_CONFIG)
        async with conn.cursor() as cur:
            if error_message:
                await cur.execute("""
                    UPDATE ocr_files
                    SET status=%s, error_message=%s, processing_end_time=NOW()
                    WHERE ocr_id=%s
                """, (status, error_message, ocr_id))
            else:
                await cur.execute("""
                    UPDATE ocr_files
                    SET status=%s, processing_end_time=NOW()
                    WHERE ocr_id=%s
                """, (status, ocr_id))
            await conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"Error updating task status: {exc}")

async def update_task_status_with_result(ocr_id, status, ocr_result=None, result_url=None):
    """タスクステータスを更新し、OCR結果を保存"""
    try:
        conn = await aiomysql.connect(**DB_CONFIG)
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE ocr_files
                SET status=%s, text_content=%s, result_url=%s, processing_end_time=NOW()
                WHERE ocr_id=%s
            """, (status, ocr_result, result_url, ocr_id))
            await conn.commit()
        conn.close()
        logger.info(f"Task {ocr_id} completed successfully with OCR result saved to database")
    except Exception as exc:
        logger.error(f"Error updating task status with result: {exc}")
        # 結果の保存に失敗した場合、少なくともステータスを更新
        await update_task_status(ocr_id, status)


async def process_ocr_queue(queue: asyncio.Queue, stop_event: asyncio.Event, worker_count: int):
    timeout = aiohttp.ClientTimeout(total=1200)  # 20分 = 1200秒
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [
            asyncio.create_task(process_ocr_task(queue, semaphore, session, stop_event))
            for _ in range(worker_count)
        ]
        await asyncio.gather(*tasks, return_exceptions=True)


class QueueWorker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        self.stop_event = asyncio.Event()
        self.tasks: list[asyncio.Task] = []
        self.worker_count = max(1, QUEUE_MAX_SIZE)

    async def start(self) -> None:
        if any(task for task in self.tasks if not task.done()):
            logger.info("Queue worker already running; start skipped.")
            return

        self.stop_event.clear()
        fetch_task = asyncio.create_task(fetch_pending_ocr_tasks(self.queue, self.stop_event))
        process_task = asyncio.create_task(process_ocr_queue(self.queue, self.stop_event, self.worker_count))
        self.tasks = [fetch_task, process_task]
        logger.info("Queue worker started.")

    async def stop(self) -> None:
        if not self.tasks:
            return

        self.stop_event.set()
        for _ in range(self.worker_count):
            try:
                self.queue.put_nowait(None)
            except asyncio.QueueFull:
                break

        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        logger.info("Queue worker stopped.")


worker = QueueWorker()

app = FastAPI(title="OCR Task Queue", version="1.0.0")


@app.on_event("startup")
async def startup_event() -> None:
    if os.getenv('TAG', '').lower() == 'dev':
        from util_debug import attach_debugger
        attach_debugger(port=5673)
    await worker.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await worker.stop()


@app.get("/health")
async def health_check() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "queue_size": worker.queue.qsize() if worker.queue else 0,
            "running": any(not task.done() for task in worker.tasks)
        }
    )

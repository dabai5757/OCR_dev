import asyncio
import aiomysql
import aiohttp
import ssl
import os
import logging

# logging.basicConfig(level=logging.INFO)

DB_CONFIG = {
    'user': 'root',
    'password': os.getenv('DB_PASSWORD'),
    'db': 'ocr_files_db',
    'host': os.getenv('DB_HOST'),
    'port': int(os.getenv('MYSQL_CONTAINER_PORT'))
}

SERVER_ADDRESS = os.getenv("SERVER_ADDRESS", "192.168.131.192")
NGINX_PORT = int(os.getenv("NGINX_PORT", 33380))

CONCURRENT_REQUESTS = 1
QUEUE_MAX_SIZE = 1
CHECK_INTERVAL = 5

# Log file path
log_path = "/logs/db_to_queue.log"

# Create logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create file handler which logs even debug messages
file_handler = logging.FileHandler(log_path)
file_handler.setLevel(logging.INFO)

# Create console handler with a higher log level
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter and add it to the handlers
formatter = logging.Formatter("%(asctime)s - %(levelname)s:%(name)s - %(message)s")
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

logger.info("Logging has been initialized successfully.")

# AI_SERVER_CONTAINER_PORT = int(os.getenv("AI_SERVER_CONTAINER_PORT"))
# if AI_SERVER_CONTAINER_PORT is None:
#     raise ValueError("AI_SERVER_CONTAINER_PORT environment variable is not set")

API_URL = f"http://ocr-api:5550/ocr"
FILE_BASE_PATH = "/var/www/backend/input_audio_files"  # Docker container path

async def fetch_pending_ocr_tasks(queue):
    while True:
        if queue.qsize() < QUEUE_MAX_SIZE:
            try:
                conn = await aiomysql.connect(**DB_CONFIG)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT ocr_id, file_name, original_filename, file_path, file_type,
                               page_count, range_start, range_end
                        FROM ocr_files
                        WHERE status='pending'
                        ORDER BY upload_time ASC
                        LIMIT %s
                    """, (QUEUE_MAX_SIZE - queue.qsize(),))
                    tasks = await cur.fetchall()
                    for task in tasks:
                        await cur.execute("UPDATE ocr_files SET status='processing', processing_start_time=NOW() WHERE ocr_id=%s", (task[0],))
                        await conn.commit()
                        # task结构: (ocr_id, file_name, original_filename, file_path, file_type, page_count, range_start, range_end)
                        await queue.put(task)
                        logging.info(f"OCR Task {task[0]} added to queue with file_name {task[1]}, file_type {task[4]}. Queue size is now {queue.qsize()}")
            except Exception as e:
                logging.error(f"Error fetching OCR tasks from database: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()
        else:
            logging.info("Queue is full, waiting for space to become available.")
        await asyncio.sleep(CHECK_INTERVAL)

async def process_ocr_task(queue, semaphore, session):
    while True:
        async with semaphore:
            # task结构: (ocr_id, file_name, original_filename, file_path, file_type, page_count, range_start, range_end)
            task = await queue.get()
            ocr_id, file_name, original_filename, file_path, file_type, page_count, range_start, range_end = task

            logging.info(f"Processing OCR task {ocr_id} with file_name {file_name}, file_type {file_type}. Queue size before processing: {queue.qsize()}")

            try:
                # 构建完整的文件路径
                full_file_path = os.path.join(FILE_BASE_PATH, file_name)

                # 检查文件是否存在
                if not os.path.exists(full_file_path):
                    logging.error(f"File not found: {full_file_path}")
                    await update_task_status(ocr_id, 'error', f"File not found: {full_file_path}")
                    queue.task_done()
                    continue

                # 读取文件内容
                with open(full_file_path, 'rb') as f:
                    file_content = f.read()

                # 准备form data
                data = aiohttp.FormData()
                data.add_field('file', file_content, filename=original_filename or file_name,
                              content_type='application/pdf' if file_type == 'pdf' else 'image/*')
                data.add_field('file_type', file_type)
                data.add_field('file_size', str(os.path.getsize(full_file_path)))

                if file_type == 'pdf' and page_count:
                    if range_start:
                        data.add_field('range_start', str(range_start))
                    if range_end:
                        data.add_field('range_end', str(range_end))
                    data.add_field('page_count', str(page_count))

                async with session.post(API_URL, data=data) as response:
                    if response.status == 200:
                        logging.info(f"OCR task {ocr_id} sent to API successfully.")
                        try:
                            response_data = await response.json()
                            logging.info(f"API Response: {response_data}")

                            # 检查OCR处理是否完成
                            if response_data.get('completed', False):
                                # 提取OCR结果
                                ocr_result = ""
                                result_url = ""

                                # 尝试从不同的字段获取OCR结果
                                if 'markdown_content' in response_data:
                                    ocr_result = response_data['markdown_content']
                                elif 'content' in response_data:
                                    ocr_result = response_data['content']
                                elif 'merged_markdown' in response_data:
                                    # 如果返回的是文件路径，需要读取文件内容
                                    merged_markdown_path = response_data['merged_markdown']
                                    try:
                                        # 直接从共享的静态文件目录读取文件内容
                                        full_file_path = merged_markdown_path  # 路径已经是 /static/...
                                        with open(full_file_path, 'r', encoding='utf-8') as f:
                                            ocr_result = f.read()
                                        logging.info(f"Successfully read OCR result from {full_file_path}")
                                    except Exception as file_error:
                                        logging.error(f"Error reading merged markdown file {merged_markdown_path}: {file_error}")

                                if 'download_url' in response_data:
                                    result_url = response_data['download_url']

                                # 更新数据库状态为completed，并保存OCR结果
                                await update_task_status_with_result(ocr_id, 'completed', ocr_result, result_url)
                            else:
                                # OCR处理中，保持processing状态
                                logging.info(f"OCR task {ocr_id} is still processing...")

                        except Exception as json_error:
                            logging.error(f"Failed to parse JSON response: {json_error}")
                            response_text = await response.text()
                            logging.info(f"API Response (text): {response_text}")
                            # 即使解析失败，也认为处理完成（因为API返回200）
                            await update_task_status(ocr_id, 'completed')
                    else:
                        logging.error(f"Failed to send OCR task {ocr_id} to API: {response.status}")
                        error_text = await response.text()
                        logging.error(f"Response: {error_text}")
                        await update_task_status(ocr_id, 'error', f"API error: {response.status}")

            except Exception as e:
                logging.error(f"Exception occurred while processing OCR task {ocr_id}: {e}")
                await update_task_status(ocr_id, 'error', str(e))

            queue.task_done()
            logging.info(f"Finished processing OCR task {ocr_id}. Queue size after processing: {queue.qsize()}")

async def update_task_status(ocr_id, status, error_message=None):
    """更新任务状态"""
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
    except Exception as e:
        logging.error(f"Error updating task status: {e}")

async def update_task_status_with_result(ocr_id, status, ocr_result=None, result_url=None):
    """更新任务状态并保存OCR结果"""
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
        logging.info(f"Task {ocr_id} completed successfully with OCR result saved to database")
    except Exception as e:
        logging.error(f"Error updating task status with result: {e}")
        # 如果保存结果失败，至少更新状态
        await update_task_status(ocr_id, status)

async def process_ocr_queue(queue):
    # OCR API是HTTP，不需要SSL
    timeout = aiohttp.ClientTimeout(total=300)  # 5分钟超时，OCR处理通常比较快
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = []
        for _ in range(QUEUE_MAX_SIZE):
            task = asyncio.create_task(process_ocr_task(queue, semaphore, session))
            tasks.append(task)
        await asyncio.gather(*tasks)

async def main():
    queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    fetch_task = asyncio.create_task(fetch_pending_ocr_tasks(queue))
    process_task = asyncio.create_task(process_ocr_queue(queue))

    await asyncio.gather(fetch_task, process_task)

if __name__ == "__main__":
    if os.getenv('TAG', '').lower() == 'dev':
        from util_debug import attach_debugger
        debug_thread = attach_debugger(port=5673)
    asyncio.run(main())
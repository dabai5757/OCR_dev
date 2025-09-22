import asyncio
import aiomysql
import aiohttp
import ssl
import os
import logging

# logging.basicConfig(level=logging.INFO)

DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
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

API_URL = f"https://{SERVER_ADDRESS}:{NGINX_PORT}/translation"

async def fetch_pending_tasks(queue):
    while True:
        if queue.qsize() < QUEUE_MAX_SIZE:
            try:
                conn = await aiomysql.connect(**DB_CONFIG)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT audio_id, file_name, translation_language, format
                        FROM sound_files
                        WHERE status='pending'
                        ORDER BY upload_time ASC
                        LIMIT %s
                    """, (QUEUE_MAX_SIZE - queue.qsize(),))
                    tasks = await cur.fetchall()
                    for task in tasks:
                        await cur.execute("UPDATE sound_files SET status='processing' WHERE audio_id=%s", (task[0],))
                        await conn.commit()
                        await queue.put((task[0], task[1], task[2], task[3]))
                        logging.info(f"Task {task[0]} added to queue with file_name {task[1]}, translation_language {task[2]}, and format {task[3]}. Queue size is now {queue.qsize()}")
            except Exception as e:
                logging.error(f"Error fetching tasks from database: {e}")
            finally:
                conn.close()
        else:
            logging.info("Queue is full, waiting for space to become available.")
        await asyncio.sleep(CHECK_INTERVAL)

async def process_task(queue, semaphore, session):
    while True:
        async with semaphore:
            audio_id, file_name, translation_language, format = await queue.get()
            logging.info(f"Processing task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format}. Queue size before processing: {queue.qsize()}")
            try:
                async with session.post(API_URL, json={"audio_id": audio_id, "file_name": file_name, "translation_language": translation_language, "format": format}) as response:
                    if response.status == 202:
                        logging.info(f"Task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} sent to API successfully.")
                    else:
                        logging.error(f"Failed to send task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} to API: {response.status}")
                        logging.error(f"Response: {await response.text()}")
            except Exception as e:
                logging.error(f"Exception occurred while sending task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} to API: {e}")
            queue.task_done()
            logging.info(f"Finished processing task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format}. Queue size after processing: {queue.qsize()}")

async def process_queue(queue):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    timeout = aiohttp.ClientTimeout(total=2700)  # 2700秒
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        for _ in range(QUEUE_MAX_SIZE):
            task = asyncio.create_task(process_task(queue, semaphore, session))
            tasks.append(task)
        await asyncio.gather(*tasks)

async def fetch_pending_tasks_api(queue):
    while True:
        if queue.qsize() < QUEUE_MAX_SIZE:
            try:
                conn = await aiomysql.connect(**DB_CONFIG)
                async with conn.cursor() as cur:
                    await cur.execute("""
                        SELECT audio_id, file_name, translation_language, format
                        FROM sound_files_api
                        WHERE status='pending'
                        ORDER BY upload_time ASC
                        LIMIT %s
                    """, (QUEUE_MAX_SIZE - queue.qsize(),))
                    tasks = await cur.fetchall()
                    for task in tasks:
                        await cur.execute("UPDATE sound_files_api SET status='processing' WHERE audio_id=%s", (task[0],))
                        await conn.commit()
                        await queue.put((task[0], task[1], task[2], task[3]))
                        logging.info(f"【API】API Task {task[0]} added to queue with file_name {task[1]}, translation_language {task[2]}, and format {task[3]}. Queue size is now {queue.qsize()}")
            except Exception as e:
                logging.error(f"【API】Error fetching API tasks from database: {e}")
            finally:
                conn.close()
        else:
            logging.info("【API】API Queue is full, waiting for space to become available.")
        await asyncio.sleep(CHECK_INTERVAL)

async def process_task_api(queue, semaphore, session):
    while True:
        async with semaphore:
            audio_id, file_name, translation_language, format = await queue.get()
            logging.info(f"【API】Processing API task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format}. Queue size before processing: {queue.qsize()}")
            try:
                api_url = f"https://{SERVER_ADDRESS}:{NGINX_PORT}/translation_api"
                async with session.post(api_url, json={"audio_id": audio_id, "file_name": file_name, "translation_language": translation_language, "format": format}) as response:
                    if response.status == 202:
                        logging.info(f"【API】API Task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} sent to API successfully.")
                    else:
                        logging.error(f"【API】Failed to send API task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} to API: {response.status}")
                        logging.error(f"【API】Response: {await response.text()}")
            except Exception as e:
                logging.error(f"【API】Exception occurred while sending API task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format} to API: {e}")
            queue.task_done()
            logging.info(f"【API】Finished processing API task {audio_id} with file_name {file_name}, translation_language {translation_language}, and format {format}. Queue size after processing: {queue.qsize()}")

async def process_queue_api(queue):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    timeout = aiohttp.ClientTimeout(total=1800)
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for _ in range(QUEUE_MAX_SIZE):
            task = asyncio.create_task(process_task_api(queue, semaphore, session))
            tasks.append(task)
        await asyncio.gather(*tasks)

async def main():
    queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    fetch_task = asyncio.create_task(fetch_pending_tasks(queue))
    process_task = asyncio.create_task(process_queue(queue))

    queue_api = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    fetch_task_api = asyncio.create_task(fetch_pending_tasks_api(queue_api))
    process_task_api = asyncio.create_task(process_queue_api(queue_api))

    await asyncio.gather(fetch_task, process_task, fetch_task_api, process_task_api)

if __name__ == "__main__":
    if os.getenv('TAG', '').lower() == 'dev':
        from util_debug import attach_debugger
        debug_thread = attach_debugger(port=5673)
    asyncio.run(main())
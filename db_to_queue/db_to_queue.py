import asyncio
import aiomysql
import aiohttp
import ssl
import os
import logging

logging.basicConfig(level=logging.INFO)

DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': 3306
}

SERVER_ADDRESS = os.getenv("SERVER_ADDRESS", "192.168.10.9")
NGINX_PORT = int(os.getenv("NGINX_PORT", 33380))

CONCURRENT_REQUESTS = 6
QUEUE_MAX_SIZE = 6
CHECK_INTERVAL = 5

AI_SERVER_CONTAINER_PORT = int(os.getenv("AI_SERVER_CONTAINER_PORT"))
if AI_SERVER_CONTAINER_PORT is None:
    raise ValueError("AI_SERVER_CONTAINER_PORT environment variable is not set")

API_URL = f"https://{SERVER_ADDRESS}:{NGINX_PORT}/ai_mode"

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
                        await queue.put((task[0], task[1], task[2], task[3]))  # 添加format到队列
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

    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for _ in range(QUEUE_MAX_SIZE):
            task = asyncio.create_task(process_task(queue, semaphore, session))
            tasks.append(task)
        await asyncio.gather(*tasks)

async def main():
    queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    fetch_task = asyncio.create_task(fetch_pending_tasks(queue))
    process_task = asyncio.create_task(process_queue(queue))
    await asyncio.gather(fetch_task, process_task)

if __name__ == "__main__":
    asyncio.run(main())

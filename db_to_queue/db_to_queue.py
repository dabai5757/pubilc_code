import asyncio
import aiomysql
import aiohttp
import os
import logging

logging.basicConfig(level=logging.INFO)

# MySQL数据库配置
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': 3306
}

QUEUE_MAX_SIZE = 30
CHECK_INTERVAL = 5  # in seconds

scaling_balancer_CONTAINER_PORT = int(os.getenv("scaling_balancer_CONTAINER_PORT"))
if scaling_balancer_CONTAINER_PORT is None:
    raise ValueError("scaling_balancer_CONTAINER_PORT environment variable is not set")

API_URL = f"http://scaling_balancer:{scaling_balancer_CONTAINER_PORT}/add_task"  # 使用 Docker Compose 中的服务名称

async def fetch_pending_tasks(queue):
    while True:
        if queue.qsize() < QUEUE_MAX_SIZE:
            try:
                conn = await aiomysql.connect(**DB_CONFIG)
                async with conn.cursor() as cur:
                    await cur.execute("SELECT audio_id, file_name FROM sound_files WHERE status='pending' LIMIT %s", (QUEUE_MAX_SIZE - queue.qsize(),))
                    tasks = await cur.fetchall()
                    for task in tasks:
                        await cur.execute("UPDATE sound_files SET status='processing' WHERE audio_id=%s", (task[0],))
                        await conn.commit()
                        await queue.put((task[0], task[1]))  # 将 (audio_id, file_name) 元组放入队列
                        logging.info(f"Task {task[0]} added to queue with file_name {task[1]}. Queue size is now {queue.qsize()}")
            except Exception as e:
                logging.error(f"Error fetching tasks from database: {e}")
            finally:
                conn.close()
        else:
            logging.info("Queue is full, waiting for space to become available.")
        await asyncio.sleep(CHECK_INTERVAL)

async def process_queue(queue):
    async with aiohttp.ClientSession() as session:
        while True:
            audio_id, file_name = await queue.get()  # 从队列中获取 (audio_id, file_name) 元组
            logging.info(f"Processing task {audio_id} with file_name {file_name}. Queue size before processing: {queue.qsize()}")
            try:
                async with session.post(API_URL, json={"audio_id": audio_id, "file_name": file_name}) as response:
                    if response.status == 202:
                        logging.info(f"Task {audio_id} with file_name {file_name} sent to API successfully.")
                    else:
                        logging.error(f"Failed to send task {audio_id} with file_name {file_name} to API: {response.status}")
                        logging.error(f"Response: {await response.text()}")
            except Exception as e:
                logging.error(f"Exception occurred while sending task {audio_id} with file_name {file_name} to API: {e}")
            queue.task_done()
            logging.info(f"Finished processing task {audio_id} with file_name {file_name}. Queue size after processing: {queue.qsize()}")

async def main():
    queue = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)

    # 启动任务获取器
    fetch_task = asyncio.create_task(fetch_pending_tasks(queue))

    # 启动队列处理器
    process_task = asyncio.create_task(process_queue(queue))

    await asyncio.gather(fetch_task, process_task)

if __name__ == "__main__":
    asyncio.run(main())

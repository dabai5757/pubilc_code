from flask import Flask, request, jsonify
import docker
import logging
import requests
import os
import socket
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import defaultdict
import threading

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

target_count = 0
image_name = "translation"
network_name = "aibt_network"

container_task_counts = defaultdict(int)
container_futures = defaultdict(list)
current_container_index = 0

# 创建一个线程池
executor = ThreadPoolExecutor(max_workers=10)  # 可以根据需要调整最大工作线程数

# 添加一个锁来保护共享资源
lock = threading.Lock()

def check_port(ip, port, retries=5, delay=3):
    logging.info(f"Checking port {port} on {ip}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for _ in range(retries):
        try:
            s.connect((ip, port))
            s.shutdown(socket.SHUT_RDWR)
            return True
        except:
            time.sleep(delay)
    s.close()
    return False

# 获取绝对路径
current_dir = '/Users/yin_shuai/Desktop/project/並列/ok_finsh'
ai_server_path = os.path.join(current_dir, 'ai_server')

input_audio_files_path = os.path.join(ai_server_path, 'input_audio_files')

# 输出路径到日志
logging.info(f"Current directory: {current_dir}")
logging.info(f"ai_server_path: {ai_server_path}")
logging.info(f"input_audio_files_path: {input_audio_files_path}")

def start_container(client, image_name, index, network_name):
    try:
        new_container = client.containers.run(
            image_name, 
            name=f"{image_name}_{index}", 
            detach=True, 
            ports={'5004/tcp': None}, 
            network=network_name,
            environment={
                'DB_USER': 'root',
                'DB_PASSWORD': 'root',
                'DB_NAME': 'sound_files_db',
                'DB_HOST': 'mysql',
                'DB_PORT': 3306
            },
            volumes={
                ai_server_path: {'bind': '/var/www/ai_server', 'mode': 'rw'},
                input_audio_files_path: {'bind': '/mnt/input_audio_files', 'mode': 'rw'}
            },
            tty=True,
            working_dir='/var/www/ai_server'  # 指定工作目录
        )
        new_container.reload()
        new_ip = new_container.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']
        logging.info(f"Started container {new_container.name} with IP {new_ip}")
        if check_port(new_ip, 5004):
            with lock:
                container_task_counts[new_container.name] = 0
                container_futures[new_container.name] = []
            return new_ip, new_container.name
    except Exception as e:
        logging.error(f"Failed to start container {index}: {e}")
    return None, f"{image_name}_{index}"

def start_container_concurrently(client, image_name, index, network_name, results, index_in_results):
    ip, name = start_container(client, image_name, index, network_name)
    results[index_in_results] = (ip, name)

def wait_for_tasks_completion(container_name):
    logging.info(f"Waiting for all tasks to complete on container {container_name}")
    while True:
        with lock:
            futures = container_futures[container_name]
            task_count = container_task_counts[container_name]
        
        if not futures and task_count == 0:
            logging.info(f"All tasks completed on container {container_name}")
            break
        
        if futures:
            completed, _ = wait(futures, timeout=1)
            with lock:
                container_futures[container_name] = [f for f in futures if f not in completed]
        else:
            time.sleep(1)  # 如果没有futures但仍有任务，等待一秒再检查

def manage_containers(target_count, image_name):
    logging.info(f"Managing containers to target count {target_count} for image {image_name}")
    client = docker.from_env()
    containers = client.containers.list(all=True, filters={"ancestor": image_name})
    running_containers = [c for c in containers if c.status == 'running']
    current_count = len(running_containers)
    logging.info(f"Currently running containers: {current_count}")
    difference = target_count - current_count
    container_ips = []

    if difference > 0:
        results = [None] * difference
        with ThreadPoolExecutor(max_workers=difference) as temp_executor:
            futures = [
                temp_executor.submit(start_container_concurrently, client, image_name, current_count + i + 1, network_name, results, i)
                for i in range(difference)
            ]
            for future in futures:
                future.result()
        new_containers = [(ip, name) for ip, name in results if ip]
        container_ips.extend([ip for ip, _ in new_containers])
    elif difference < 0:
        containers_to_remove = sorted(running_containers, key=lambda x: x.name, reverse=True)[:abs(difference)]
        for container in containers_to_remove:
            wait_for_tasks_completion(container.name)
            
            # 再次检查是否有新任务被添加
            with lock:
                if container_task_counts[container.name] > 0:
                    logging.info(f"New tasks added to {container.name}, skipping removal")
                    continue

            logging.info(f"Stopping container {container.name}")
            try:
                container.stop()
                container.remove()
                logging.info(f"Container {container.name} removed successfully")
            except docker.errors.APIError as e:
                logging.error(f"Error removing container {container.name}: {e}")
            
            with lock:
                container_task_counts.pop(container.name, None)
                container_futures.pop(container.name, None)

    for container in client.containers.list(filters={"ancestor": image_name, "status": "running"}):
        ip_address = container.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']
        if ip_address not in container_ips:
            container_ips.append(ip_address)

    update_nginx_conf(container_ips)
    return container_ips

def update_nginx_conf(container_ips):
    logging.info(f"Updating NGINX configuration with container IPs: {container_ips}")
    os.makedirs('/app/nginx', exist_ok=True)
    nginx_conf_path = '/app/nginx/nginx.conf'
    upstream_servers = "\n    ".join([f"server {ip}:5004;" for ip in container_ips])
    config_content = f"""
upstream backend {{
    {upstream_servers}
}}
server {{
    listen 80;
    location / {{
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_read_timeout 3600s;
        send_timeout 3600s;
    }}
}}
    """
    with open(nginx_conf_path, "w") as f:
        f.write(config_content)
    os.system("nginx -s reload")

def proxy_request(container_ip, audio_id, file_name, container_name):
    logging.info(f"Sending audio_id {audio_id} with file_name {file_name} to container {container_ip}")
    url = f"http://{container_ip}:5004/sleep"
    try:
        start_time = time.time()
        response = requests.post(url, json={"audio_id": audio_id, "file_name": file_name})
        response.raise_for_status()
        end_time = time.time()

        start_time_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
        end_time_str = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')

        with lock:
            container_task_counts[container_name] -= 1
            container_futures[container_name] = [f for f in container_futures[container_name] if not f.done()]

        logging.info(f"audio_id {audio_id} with file_name {file_name} completed on {container_ip} from {start_time_str} to {end_time_str}")
        
        return {
            # "response": response.json(),
            "start_time": start_time_str,
            "end_time": end_time_str,
            "container_ip": container_ip
        }
    except requests.exceptions.RequestException as e:
        logging.error(f"Request to {url} failed: {e}")
        with lock:
            container_task_counts[container_name] -= 1
            container_futures[container_name] = [f for f in container_futures[container_name] if not f.done()]
        return {"error": str(e), "container_ip": container_ip}

def get_next_container():
    global current_container_index
    client = docker.from_env()
    containers = client.containers.list(filters={"ancestor": image_name, "status": "running"})
    if not containers:
        return None, None

    container_names = [container.name for container in containers]
    if not container_names:
        return None, None

    if current_container_index >= len(container_names):
        current_container_index = 0

    next_container_name = container_names[current_container_index]
    container = client.containers.get(next_container_name)
    ip_address = container.attrs['NetworkSettings']['Networks'][network_name]['IPAddress']

    current_container_index = (current_container_index + 1) % len(container_names)
    return ip_address, next_container_name

@app.route('/add_task', methods=['POST'])
def add_task():
    data = request.get_json(force=True)
    audio_id = data.get('audio_id')
    file_name = data.get('file_name')
    if audio_id and file_name and isinstance(audio_id, int) and isinstance(file_name, str):
        logging.info(f"Received audio_id {audio_id} with file_name {file_name}")
        container_ips = manage_containers(target_count, image_name)
        if not container_ips:
            return jsonify({"error": "No available containers to process the task."}), 503

        container_ip, container_name = get_next_container()

        with lock:
            container_task_counts[container_name] += 1

        future = executor.submit(proxy_request, container_ip, audio_id, file_name, container_name)
        with lock:
            container_futures[container_name].append(future)
        
        return jsonify({"message": "Task accepted", "container_ip": container_ip}), 202

    else:
        logging.error("Invalid task received")
        return jsonify({"error": "Invalid task. Please provide a valid audio_id and integer file_name."}), 400

@app.route('/update_containers', methods=['POST'])
def update_containers():
    global target_count, image_name
    data = request.get_json(force=True)
    target_count = int(data.get('target_count', 1))
    image_name = data.get('image_name', '')

    if not image_name:
        logging.error("Image name is required")
        return jsonify({"error": "Image name is required."}), 400

    container_ips = manage_containers(target_count, image_name)
    return jsonify({"message": "Container count updated successfully.", "container_ips": container_ips}), 200

@app.route('/get_tasks_status', methods=['GET'])
def get_tasks_status():
    with lock:
        return jsonify({"task_counts": dict(container_task_counts)}), 200

if __name__ == "__main__":
    logging.info("Starting Flask app")
    app.run(debug=True, host='0.0.0.0', port=5003)
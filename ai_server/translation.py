from flask import Flask, request, jsonify, send_file, send_from_directory
from multiprocessing import Lock
from datetime import datetime
from flask_cors import CORS
import socket
import pymysql
import warnings
import os
import traceback
import time
import locale
import logging
from faster_whisper import WhisperModel
from numba.core.errors import NumbaDeprecationWarning
import sys
import math
import psutil
import concurrent.futures

warnings.filterwarnings('ignore', category=NumbaDeprecationWarning)
warnings.filterwarnings("ignore", "FP16 is not supported on CPU; using FP32 instead")

app = Flask(__name__)
CORS(app)

previous_result = {}
result_lock = Lock()
first_time = 0
transcribe_duration = 0
transcribe_lock = Lock()
duration_lock = Lock()

os.environ["PYTHONIOENCODING"] = "UTF-8"
count = 0

# 配置日志
logging.basicConfig(level=logging.INFO)

try:
    logging.basicConfig(filename='log_cui_info.log', level=logging.INFO, encoding='utf-8')
except Exception as e:
    print(traceback.format_exc())
    raise

pipe = None
assistant_model = None
output_file = None
audio_model = None
dtime_1st = None
dtime_old = None

NGINX_PORT = os.getenv('NGINX_PORT', '33380')
SERVER_ADDRESS = os.getenv('SERVER_ADDRESS', '192.168.10.9')
API_BASE_URL = f"https://{SERVER_ADDRESS}:{NGINX_PORT}"

# MySQL数据库配置
DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': 3306
}

def get_container_ip():
    """获取容器的IP地址"""
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    return ip_address

def update_task_status(task_id, status, out_filename):
    """更新数据库中任务的状态"""
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            sql = "UPDATE sound_files SET status=%s, result_url=%s WHERE audio_id=%s"
            cursor.execute(sql, (status, out_filename, task_id))
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to update task {task_id} status to {status}: {e}")
    finally:
        if conn:
            conn.close()

def handle_task(audio_id, file_name, container_ip, start_time_str):
    try:
        audio_path = os.path.join("/mnt/input_audio_files", file_name)

        logging.info(f"处理开始，任务ID-{audio_id}，容器IP-{container_ip}，开始时间-{start_time_str}")

        out_filename = generate_output_filename(file_name)

        transcription_path = cmd_transcribe('faster-large-v2', 'cuda', audio_path, out_filename, 'Japanese', None, None, None, None)

        end_time = time.time()
        end_time_str = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f"处理结束，任务ID-{audio_id}，容器IP-{container_ip}，结束时间-{end_time_str}")

        result_url = f"{API_BASE_URL}/output_txt_files/{out_filename}"
        update_task_status(audio_id, 'completed', result_url)
        return transcription_path, None
    except Exception as e:
        logging.error(f"Task handling error: {e}")
        return None, str(e)

@app.route('/ai_mode', methods=['POST'])
def ai_mode():
    data = request.get_json(force=True)
    audio_id = data.get('audio_id')
    file_name = data.get('file_name')

    if audio_id and file_name:
        container_ip = get_container_ip()
        start_time = time.time()
        start_time_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(handle_task, audio_id, file_name, container_ip, start_time_str)
            transcription_path, error = future.result()

        if transcription_path:
            return send_file(transcription_path, as_attachment=True)
        else:
            return {"error": error}, 500
    else:
        return {"error": "请提供一个有效的整数ID和音频文件"}, 400

# 在程序启动时加载模型
def get_audio_model():
    global audio_model
    if audio_model is None:
        audio_model = WhisperModel("large-v2", device="cuda", num_workers=4, cpu_threads=4)
    return audio_model

def cmd_transcribe(model, device, in_filepath, out_filename, language, initial_prompt, verbose, dtime, list):
    logging.debug(">cmd_transcribe")
    logging_cui(f"model:{model}, device:{device}, in_filepath:{in_filepath}, out_filename:{out_filename}, language:{language}, initial_prompt:{initial_prompt}, verbose:{verbose}, dtime:{dtime}, list:{list}", is_log=True)
    if dtime is None:
        dtime_base = datetime.now()
    else:
        dtime_base = datetime.fromisoformat(dtime)
    if in_filepath is None and list is None:
        return
    if in_filepath:
        return transcribe(model, device, in_filepath, out_filename, language, initial_prompt, verbose, dtime_base)
    files = _get_files_from_list(list)
    for file in files:
        transcribe(model, device, file, out_filename, language, initial_prompt, verbose, dtime_base)

def _get_files_from_list(list_path):
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    full_list_path = os.path.join(script_dir, list_path) if not os.path.isabs(list_path) else list_path
    directory = os.path.dirname(full_list_path)
    full_paths = []
    with open(full_list_path, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.split('#', 1)[0]
            line = line.split('//', 1)[0]
            filename = line.strip()
            if filename:
                full_path = os.path.join(directory, filename)
                full_path = os.path.join(directory, filename).replace("\\", "/")
                full_paths.append(full_path)
    return full_paths

def transcribe(model="faster-large-v2", device="cuda:0", in_filepath="./input_audio_files/sample.wav", out_filename=None, language="Japanese", initial_prompt="", verbose=False, dtime_base=None):
    logging.debug(">transcribe")
    global first_time
    global audio_model

    if not out_filename:
        out_filename = generate_output_filename(in_filepath)
    txt_filepath = os.path.join("output_txt_files", out_filename)
    txt_filefullpath = os.path.abspath(txt_filepath)
    txt_directory_path = os.path.dirname(txt_filefullpath)

    if not os.path.exists(txt_directory_path):
        os.makedirs(txt_directory_path)

    try:
        with open(txt_filefullpath, 'w', encoding='utf-8') as output_file:
            if not os.path.exists(in_filepath):
                logging_cui(f"エラー: {in_filepath}のファイルパスが誤っています。", is_print=True, is_output_file=True)
                return None
            assistant_model = None
            if first_time == 0:
                first_time = time.time()
            text = None
            if model == "faster-large-v2":
                text = _transcribe_faster_whisperlib_model(in_filepath, model, device, language=language, initial_prompt=initial_prompt, verbose=verbose, dtime_base=dtime_base)
            else:
                logging_cui(f'No such model:{model}', is_print=True)
            output_file.write(text)
    except OSError as e:
        logging_cui(f"transcribe() で OSError: {e}", is_print=True, is_log=True)
        logging_cui(f"traceback:{traceback.format_exc()}", is_print=True, is_log=True)
    except Exception as e:
        logging_cui(f"transcribe() で Error: {e}", is_print=True, is_log=True)
        logging_cui(f"traceback:{traceback.format_exc()}", is_print=True, is_log=True)

    return txt_filefullpath

def _transcribe_faster_whisperlib_model(in_filepath, model, device, language=None, initial_prompt=None, verbose=False, dtime_base=None):
    logging.debug(">_transcribe_faster_whisperlib_model")
    global transcribe_duration
    result_text = ""
    logging_cui(f'{_str_diff_time(dtime_base)}文字起こし开始:{in_filepath}:{model}', is_print=True, is_log=True)
    start_time = time.time()
    result = None
    if language == "Japanese":
        language = "ja"
    elif language == "English":
        language = "en"
    elif language == "Chinese":
        language = "cn"
    try:
        with transcribe_lock:
            logging.debug("Starting transcription")
            # audio_model = get_audio_model()
            segments, info = audio_model.transcribe(in_filepath, language=language, initial_prompt=initial_prompt)
            logging.debug("Transcription completed")
            logging.debug(f"Transcription segments: {segments}")
            logging.debug(f"Transcription info: {info}")
    except Exception as e:
        logging_cui(f"Error during transcription: {e}", is_print=True, is_log=True)
        raise e
    end_time = time.time()
    with duration_lock:
        transcribe_duration += end_time - start_time
    elapsed_time_since_load = end_time - first_time
    minutes, seconds = divmod(math.floor(transcribe_duration), 60)
    min, sec = divmod(math.floor(elapsed_time_since_load), 60)
    for segment in segments:
        start_formatted = "{:02}:{:02}.{:03d}".format(int(segment.start // 60), int(segment.start % 60), int(0))
        end_formatted = "{:02}:{:02}.{:03d}".format(int(segment.end // 60), int(segment.end % 60), int(0))
        result_text += f"[{start_formatted} --> {end_formatted}] {segment.text}\n"
    logging_cui(f'{_str_diff_time(dtime_base)}文字起こし完了', is_print=True, is_log=True)
    return result_text

def _str_diff_time(dtime_base):
    global dtime_1st
    global dtime_old

    if dtime_base is None:
        return ""

    if dtime_1st is None:
        dtime_1st = dtime_base
    if dtime_old is None:
        dtime_old = dtime_1st

    dtime_new = datetime.now()
    time_diff = dtime_new - dtime_old
    dtime_old = dtime_new

    hours, remainder = divmod(time_diff.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    new_fmt = dtime_new.strftime("%H:%M:%S")
    diff_fmt = "{:02}:{:02}:{:02}".format(hours, minutes, seconds)
    return f"[{new_fmt}(+{diff_fmt})]"

def logging_cui(message, file=sys.stdout, is_flush=True, is_print=False, is_log=False, is_output_file=False):
    logging.debug(f">logging_cui=file:{file}, is_flush:{is_flush}, is_print:{is_print}, is_log:{is_log}, is_output_file:{is_output_file}, sys.stdout:{sys.stdout}, sys.stderr:{sys.stderr}")
    global output_file
    time_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    if is_print:
        if file and not file.closed:
            pass
        else:
            file = sys.stdout
        try:
            default_encoding = locale.getpreferredencoding()
            safe_message = message.encode(default_encoding, errors="replace").decode(default_encoding)
            print(safe_message, file=file, flush=is_flush)
        except OSError as e:
            print(f"Caught an OSError: {e}")
    if is_log:
        logging.info(f"[{time_str}]{message}")
    if is_output_file:
        if output_file and not output_file.closed:
            output_file.write(f"[{time_str}]{message}")
        else:
            pass

def generate_output_filename(file_name):
    base_filename, _ = os.path.splitext(file_name)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    return f"{base_filename}_{timestamp}.txt"

# 静的ファイルを提供するエンドポイントを定義
@app.route('/output_txt_files/<path:filename>')
def serve_static(filename):
    logging.info(">serve_static():")
    try:
        return send_from_directory('output_txt_files', filename, as_attachment=True)
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    device = "cuda"  # 如果需要使用GPU，则设置为 "cuda"
    audio_model = get_audio_model()
    app.run(host='0.0.0.0', port=5004)

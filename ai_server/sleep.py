from flask import Flask, request, jsonify, send_file
from multiprocessing import Process, Queue, Lock
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
logging.basicConfig(level=logging.DEBUG)

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

task_queue = Queue()

def update_task_status(task_id, status):
    """更新数据库中任务的状态"""
    conn = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            sql = "UPDATE sound_files SET status=%s WHERE audio_id=%s"
            cursor.execute(sql, (status, task_id))
            conn.commit()
    except Exception as e:
        logging.error(f"Failed to update task {task_id} status to {status}: {e}")
    finally:
        if conn:
            conn.close()

def log_resource_usage():
    process = psutil.Process(os.getpid())
    logging.info(f"CPU usage: {process.cpu_percent()}%")
    logging.info(f"Memory usage: {process.memory_info().rss / (1024 * 1024)} MB")

def handle_task(audio_id, file_name, container_ip, start_time_str, task_queue):
    try:
        audio_path = os.path.join("/mnt/input_audio_files", file_name)

        logging.info(f"处理开始，任务ID-{audio_id}，容器IP-{container_ip}，开始时间-{start_time_str}")

        out_filename = generate_output_filename(file_name)
        
        log_resource_usage()
        
        transcription_path = cmd_transcribe('faster-large-v2', 'cpu', audio_path, out_filename, None, None, None, None, None)
        
        log_resource_usage()

        end_time = time.time()
        end_time_str = datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
        logging.info(f"处理结束，任务ID-{audio_id}，容器IP-{container_ip}，结束时间-{end_time_str}")

        update_task_status(audio_id, 'completed')
        task_queue.put((transcription_path, None))
    except Exception as e:
        logging.error(f"Task handling error: {e}")
        task_queue.put((None, str(e)))

@app.route('/sleep', methods=['POST'])
def sleep():
    data = request.get_json(force=True)
    audio_id = data.get('audio_id')
    file_name = data.get('file_name')
    
    if audio_id and file_name:
        container_ip = get_container_ip()
        start_time = time.time()
        start_time_str = datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
        
        process = Process(target=handle_task, args=(audio_id, file_name, container_ip, start_time_str, task_queue))
        process.start()
        process.join()
        transcription_path, error = task_queue.get()

        if transcription_path:
            return send_file(transcription_path, as_attachment=True)
        else:
            return {"error": error}, 500
    else:
        return {"error": "请提供一个有效的整数ID和音频文件"}, 400

# 在程序启动时加载模型
def load_model():
    global audio_model
    logging.info("Loading model...")
    
    log_resource_usage()
    
    if "cuda" in device:
        audio_model = WhisperModel("large-v2", device="cuda", compute_type="float16")
    else:
        audio_model = WhisperModel("large-v2", device="cpu")
    
    logging.info("Model loaded successfully")
    
    log_resource_usage()

def cmd_transcribe(model, device, in_filepath, out_filename, language, initial_prompt, verbose, dtime, list):
    logging.debug(">cmd_transcribe")
    logging_cui(f"model:{model}, device:{device}, in_filepath:{in_filepath}, out_filename:{out_filename}, language:{language}, initial_prompt:{initial_prompt}, verbose:{verbose}, dtime:{dtime}, list:{list}", is_log=True)
    global count
    if dtime is None : dtime_base = datetime.now()
    else             : dtime_base = datetime.fromisoformat(dtime)
    if in_filepath == None and list == None:
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
    global output_file
    global audio_model

    start_time = 0

    logging_cui(f'①精度・処理时间（faster-large-v2。指定しないと「faster-large-v2」）:{model}', is_log=True)
    logging_cui(f'②ハードウェア（cpu,cuda。指定しないと自動検出）:{device}', is_log=True)
    logging_cui(f'③詳細出力（True,False。指定しないと「True」）:{verbose}', is_log=True)
    logging_cui(f'④音声ファイルのパス（指定しないと「sample.mp3」）:{in_filepath}', is_log=True)
    logging_cui(f'⑤出力ファイルのパス（指定しないと「YYYY-MM-DD-hh-mm-ss.txt」）:{out_filename}', is_log=True)

    if not out_filename:
        only_filename = os.path.basename(in_filepath)
        base_filename, _ = os.path.splitext(only_filename)
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        out_filename = f"{base_filename}_{timestamp}.txt"
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
            logging_cui(f"\n{text}", is_output_file=True)
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

if __name__ == '__main__':
    device = "cpu"  # 如果需要使用GPU，则设置为 "cuda"
    load_model()
    app.run(host='0.0.0.0', port=5004)

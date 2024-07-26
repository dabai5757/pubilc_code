import warnings
from numba.core.errors import NumbaDeprecationWarning
warnings.filterwarnings('ignore', category=NumbaDeprecationWarning)
warnings.filterwarnings("ignore", "FP16 is not supported on CPU; using FP32 instead")

from flask import Flask, request, jsonify, g, send_from_directory
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
import json
import mimetypes

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

TABLE_TRANSLATION="sound_files"
DATABASE="sound_files_db"
HOST = os.getenv("DB_HOST")
PORT = os.getenv("MYSQL_CONTAINER_PORT")
PASSWORD = os.getenv("DB_PASSWORD")

count = 0
MAX_RETRIES = 3
RETRY_INTERVAL = 10

log_path =  "app.log"
logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",filename=log_path)

try:
    logging.basicConfig(filename='log_cui_info.log', level=logging.INFO, encoding='utf-8')
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

# POSTメソッドで音声ファイルを受け取り、指定されたモデルとデバイスを使用して音声をテキストに転写し、JSON形式で応答
@app.route('/api/aibt/transcribe', methods=['POST'])
def transcribe_audio():
    logging.info(">transcribe_audio():")
    try:
        #####################################################################################################
        # audio save
        upload_time = (datetime.now() + timedelta(hours=9)).strftime("%Y-%m-%d_%H-%M-%S")
        if 'audio_file' not in request.files:
            raise ValueError("No audio data provided in the request.")
        audio_file = request.files['audio_file']
        # logging.info(f"audio_file: {audio_file}")
        if audio_file.filename == '':
            raise ValueError("No selected audio file.")
        audio_filename = secure_filename(audio_file.filename)
        # logging.info(f"audio_filename: {audio_filename}")
        destination_path = os.path.join("/var/www/backend/input_audio_files", audio_filename)
        audio_file.save(destination_path)
        # logging.info(f"Audio file copied to: {destination_path}")
        #####################################################################################################
        # mysql
        connection = getattr(g, 'connection', None)
        cursor = connection.cursor()
        cursor.execute("""
        SELECT MAX(audio_id) FROM {}
        """.format(TABLE_TRANSLATION))
        max_audio_file_id_temp = cursor.fetchone()[0]
        audio_file_id = max_audio_file_id_temp + 1 if max_audio_file_id_temp is not None else 1
        cursor.execute(f"""
            INSERT INTO `{TABLE_TRANSLATION}` (
                `audio_id`,
                `file_name`,
                `status`,
                `audio_length`,
                `upload_time`,
                `result_url`,
                `translation_time`
            ) VALUES (
                %s, %s, 'pending', NULL, %s, NULL, NULL
            )
        """, (audio_file_id, audio_filename, upload_time))
        connection.commit()
        # return audio_file_id
        return jsonify({'audio_file_id': audio_file_id}), 200

    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
        return jsonify({'error': str(ve)}), 400  # HTTP 400 ステータスコードを返す
    except FileNotFoundError as fnfe:
        logging.error(f"FileNotFoundError: {fnfe}")
        return jsonify({'error': f"ファイルが見つかりません"}), 404  # HTTP 404 ステータスコードを返す
    except Exception as e:
        logging.error(f"Exception: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': '内部エラーが発生しました。'}), 500  # HTTP 500 ステータスコードを返す
    finally:
        cursor.close()
        connection.close()

@app.route('/api/aibt/get_url', methods=['POST'])
def get_url():
    logging.info(">get_url():")
    try:
        data = request.json
        audio_file_id = data.get('audio_id')
        if not audio_file_id:
            raise ValueError("audio_id が指定されていません。")

        connection = connect_to_database(HOST, DATABASE, PASSWORD, PORT)
        cursor = connection.cursor()
        cursor.execute(f"""
            SELECT `result_url` FROM `{TABLE_TRANSLATION}`
            WHERE `audio_id` = %s AND `status` = 'completed'
        """, (audio_file_id,))
        result = cursor.fetchone()
        if result:
            result_url = result[0]
            return jsonify({'result_url': result_url}), 200
        return jsonify({'result_url': None}), 200

    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
        return jsonify({'error': str(ve)}), 400  # HTTP 400 ステータスコードを返す
    except FileNotFoundError as fnfe:
        logging.error(f"FileNotFoundError: {fnfe}")
        return jsonify({'error': f"ファイルが見つかりません"}), 404  # HTTP 404 ステータスコードを返す
    except Exception as e:
        logging.error(f"Exception: {e}")
        logging.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({'error': '内部エラーが発生しました。'}), 500  # HTTP 500 ステータスコードを返す
    finally:
        cursor.close()
        connection.close()

port = int(os.getenv("BACKEND_CONTAINER_PORT"))
if port is None:
    raise ValueError("BACKEND_CONTAINER_PORT environment variable is not set")
# main
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=port)
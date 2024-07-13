import mysql.connector
import requests
import time
import logging
import sys
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': 3306
}

query = "SELECT COUNT(*) FROM sound_files WHERE status IN ('pending', 'processing')"
api_url = "http://scaling_balancer:5003/update_containers"

def calculate_target_count(request_count):
    return int(request_count / 5) + 1

def connect_to_database(retries=5, delay=5):
    while retries > 0:
        try:
            logging.info("Attempting to connect to MySQL...")
            conn = mysql.connector.connect(**DB_CONFIG)
            return conn
        except mysql.connector.Error as err:
            logging.error(f"MySQL Error: {err}")
            retries -= 1
            if retries > 0:
                logging.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
    raise Exception("Could not connect to MySQL after multiple retries")

loop_count = 0
while True:
    try:
        loop_count += 1
        logging.info(f"Starting loop iteration {loop_count}")

        conn = connect_to_database()
        cursor = conn.cursor()
        cursor.execute(query)
        
        result = cursor.fetchone()
        file_count = result[0]
        
        target_count = calculate_target_count(file_count)
        
        data = {
            "target_count": str(target_count),
            "image_name": "translation"
        }
        
        logging.info(f"Sending target_count={target_count} to {api_url}...")
        response = requests.post(api_url, json=data, timeout=10)
        
        logging.info(f"Sent target_count={target_count} to {api_url}, Response: {response.status_code}, {response.text}")
        
        cursor.close()
        conn.close()
        
    except mysql.connector.Error as err:
        logging.error(f"MySQL Error: {err}")
    except requests.RequestException as e:
        logging.error(f"Request Error: {e}")
    except Exception as e:
        logging.error(f"Unexpected Error: {e}", exc_info=True)
    
    logging.info(f"Completed loop iteration {loop_count}")
    logging.info("Waiting for 5 seconds before next iteration...")
    time.sleep(15)
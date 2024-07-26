import mysql.connector
from datetime import datetime
import openai
import asyncio
import logging
import os
import requests
from mysql.connector import errorcode
import time
import json
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

DB_CONFIG = {
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'db': os.getenv('DB_NAME'),
    'host': os.getenv('DB_HOST'),
    'port': 3306
}
TABLE_NAME = "document_texts"

WAITING_STATUSES_PROCESS_IN_PROGRESS = 0
WAITING_STATUSES_PROCESS_PENDING = 1
WAITING_STATUSES_PROCESS_COMPLETED = 9
AI_TYPES_INTERNAL_AI = 1
AI_TYPES_EXTERNAL_AI = 2
QUEUE_MAX_SIZE = 2
CYCLE_TIME = 1

MAX_RETRIES = 3
RETRY_INTERVAL = 10

local_llm_queue = asyncio.Queue(1)
lock = asyncio.Lock()

logging.basicConfig(level=logging.INFO,format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",filename="/logs/my_llm_logs.log")
# logging.basicConfig(level=logging.DEBUG,format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",filename="llm.log")

async def connect_to_database(HOST, DATABASE, PASSWORD, PORT):
    #logging.info(">connect_to_database():")
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
        except mysql.connector.Error as err:
            print(f"再試行します...({retry_count+1}/{MAX_RETRIES})")
            logging.warning(f"再試行します...({retry_count+1}/{MAX_RETRIES})")
            retry_count += 1
            if retry_count < MAX_RETRIES:
                await asyncio.sleep(RETRY_INTERVAL)
            continue

    logging.error("データベースに接続できませんでした。リトライ回数を超えました。")
    exit

async def poll_ai_database():
    #logging.info(">poll_ai_database():")
    poll_result = None
    connection = await connect_to_database(**DB_CONFIG)
    if connection.is_connected():
        try:
            cursor = connection.cursor(dictionary=True)
            query = (f"SELECT document_text_id, waiting_status_id, ai_type_id, sample_case_memo, sample_format, sample_generated_text, user_case_memo, user_format "
                            f"FROM {TABLE_NAME} "
                            f"WHERE waiting_status_id = {WAITING_STATUSES_PROCESS_PENDING} "
                            f"ORDER BY created_datetime ASC LIMIT 1")
            cursor.execute(query)
            poll_result = cursor.fetchone()
            if poll_result:
                update_query = (f"UPDATE {TABLE_NAME} SET waiting_status_id = {WAITING_STATUSES_PROCESS_IN_PROGRESS} "
                                "WHERE document_text_id = %s")
                cursor.execute(update_query, (poll_result['document_text_id'],))
                connection.commit()
                logging.info("document_text_id = %s : wait_stausが1になった",poll_result['document_text_id'])#★#★#★
            # else:
                # print("処理待ちレコードが存在しません。poll_ai_database関数終了。")
                #logging.info("処理待ちレコードが存在しません。poll_ai_database関数終了。")
        finally:
            cursor.close()
            connection.close()
    else:
        print("MySQL接続エラーで、poll_ai_database関数終了。")
        logging.error("MySQL接続エラーで、poll_ai_database関数終了。")
    return poll_result

def generate_local_ai_response(sample_format, sample_generated_text, user_format, thread_name):
    logging.info(f"{thread_name}>generate_local_ai_response():")
    logging.info(f"{thread_name}>generate_local_ai_response()の引数: sample_format={sample_format}, sample_generated_text={sample_generated_text}, user_format={user_format}")
    ai_response = None
    stop = ["[", "<"]
    ai_generate_start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not sample_format.strip():
        sample_format = "[令和６年４月１日の時候の挨拶を交えた書き出し]。"
    if not sample_generated_text.strip():
        sample_generated_text = "春の訪れを感じる季節となりました。貴殿におかれましては、ご清栄のことと存じます。"
    try:
        URI = "http://AISERVER:7005/v1/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": "あなたは、userが与えたFORMATの内容を変換するＡＩです。\n変換方法は次のとおりです。\n①userはあなたに、FORMATを与えます。\n②FORMATには'[『リースに関する事務作業全般』の一般的な内容を具体的に説明]である。'のような記載があります。この場合、'['と']'で囲まれた部分はあなたへの指示です。その指示に従って、例えば「新しいリース物件の登録、紹介記事作成、受注応対、修繕対応等である。」のように、指示されたとおりの「だ・である」調の文章に変換します。\n③最後に、変換したFORMATのみを出力します。それ以外は出力しません。"},
                {"role": "user", "content": f"FORMAT: {sample_format}"},
                {"role": "assistant", "content": sample_generated_text},
                {"role": "user", "content": f"FORMAT: {user_format}"},
            ],
            "stop": stop
        }
        # JSON をファイルに出力
        with open("query.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        response = requests.post(URI, headers=headers, json=data, verify=False)
        if response.status_code == 200:
            resp = response.json()
            ai_response = resp['choices'][0]['message']['content']
            ai_generate_end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"{thread_name}>generate_local_ai_response()の戻り値: ai_response={ai_response}, ai_generate_start_datetime={ai_generate_start_datetime}, ai_generate_end_datetime={ai_generate_end_datetime}")
            return ai_response, ai_generate_start_datetime, ai_generate_end_datetime
        else:
            print("Failed to get response")
    except Exception as e:
        print(f"{thread_name}>Error in generate_local_ai_response(): {e}")
        logging.error(f"{thread_name}>Error in generate_local_ai_response(): {e}")
    return None, None, None

async def write_to_ai_database(document_text_id, user_generated_text, ai_generate_start_datetime, ai_generate_end_datetime, thread_name, ai_type_id):
    logging.info(f"{thread_name}>write_to_ai_database():")
    logging.info(f"{thread_name}>write_to_ai_database()の引数: document_text_id={document_text_id}, user_generated_text={user_generated_text}, ai_generate_start_datetime={ai_generate_start_datetime}, ai_generate_end_datetime={ai_generate_end_datetime}")
    connection = await connect_to_database(**DB_CONFIG)
    if connection.is_connected():
        try:
            cursor = connection.cursor(dictionary=True)
            query = f"""
                    UPDATE {TABLE_NAME}
                    SET
                        user_generated_text = %s,
                        ai_generate_start_datetime = %s,
                        ai_generate_end_datetime = %s,
                        waiting_status_id = {WAITING_STATUSES_PROCESS_COMPLETED}
                    WHERE
                        document_text_id = %s AND ai_type_id = %s
                    """
            cursor.execute(query, (user_generated_text, ai_generate_start_datetime, ai_generate_end_datetime, document_text_id, ai_type_id))
            connection.commit()
        finally:
            cursor.close()
            connection.close()
            print(f'{thread_name}個目処理完了')
            logging.info(f'{thread_name}個目処理完了')
    else:
        print("MYSQL接続エラーで、書き込みできません。write_to_ai_database関数終了。")
        logging.error("MYSQL接続エラーで、書き込みできません。write_to_ai_database関数終了。")


async def put_main_local():
    logging.info(">put_main_local():")
    retry_count = 0
    pending_data_local = None #　QueueFullの場合のpoll_data_external情報の格納で、こうしないと、そのままpoll_data_externalを捨てられてしまう
    while retry_count < MAX_RETRIES:
        try:
            if pending_data_local != None:
                poll_data_internal = pending_data_local
            else:
                poll_data_internal = await poll_ai_database(**DB_CONFIG)
            if poll_data_internal:
                try:
                    async with lock:
                        local_llm_queue.put_nowait(poll_data_internal)
                        pending_data_local = None
                except asyncio.QueueFull:
                    # print(f"local_llm_queueがいっぱいの為、putできません。")
                    # logging.warning(f"local_llm_queueがいっぱいの為、putできません。")#★★★
                    await asyncio.sleep(CYCLE_TIME)
                    pending_data_local = poll_data_internal
                    continue
                    # print("put Queue size:", local_llm_queue.qsize())  #★
            else:
                # print("internal処理待ちレコードがないため、{}秒毎にデータベースをポーリングします。".format(CYCLE_TIME))#★★★
                # print("put_main_local()関数 : poll_ai_database戻り値がNULL。")
                #logging.info("put_main_local()関数 : poll_ai_database戻り値がNULL。")
                await asyncio.sleep(CYCLE_TIME)
                continue
        except Exception as e:
            print(f"put_main_local()にエラーが発生しました: {e}")
            logging.error(f"put_main_local()にエラーが発生しました: {e}")
            await asyncio.sleep(CYCLE_TIME)
            retry_count += 1
            if retry_count < MAX_RETRIES:
                time.sleep(RETRY_INTERVAL)
            continue

    logging.error("put_main_local()の処理中に致命的なエラーが発生しました。リトライ回数を超えました。")
    exit

async def get_poll_data_from_queue_local(name):
    logging.info(">get_poll_data_from_queue_local():")
    while True:
        try:
            async with lock:
                element = local_llm_queue.get_nowait()
        except asyncio.QueueEmpty:
            # logging.warning(f"local_llm_queueが空の為、getできません。")
            await asyncio.sleep(CYCLE_TIME)
            continue
        # print("get Queue size:", local_llm_queue.qsize())  #★
        keys = list(element.keys())
        sample_format = element[keys[4]]
        sample_generated_text = element[keys[5]]
        user_format = element[keys[7]]
        document_text_id = element[keys[0]]
        ai_type_id = element[keys[2]] #★★★
        user_generated_text, ai_generate_start_datetime, ai_generate_end_datetime = generate_local_ai_response(sample_format, sample_generated_text, user_format, name)
        if user_generated_text and ai_generate_start_datetime and ai_generate_end_datetime:
            await write_to_ai_database(document_text_id, user_generated_text, ai_generate_start_datetime, ai_generate_end_datetime, name, ai_type_id)
            await asyncio.sleep(CYCLE_TIME)
            continue
        else:
            print("write_to_ai_databaseがNULL。")
            logging.warning("generate_local_ai_response戻り値がNULL。")
            await asyncio.sleep(CYCLE_TIME)
            continue

async def get_main():
    logging.info(">get_main():")
    tasks = []
    try:
        for i in range(QUEUE_MAX_SIZE):
            task_local = asyncio.create_task(get_poll_data_from_queue_local(f'local_thr-{i}'))
            tasks.append(task_local)
        await asyncio.gather(*tasks)
    except Exception as e:
        print(f"An error occurred in get_main: {e}")
        logging.error(f"An error occurred in get_main: {e}")

async def main():
    logging.info(">main():")
    try:
        await asyncio.gather(put_main_local(), get_main())
    except Exception as e:
        print(f"エラー発生: {e}")
        logging.error(f"エラー発生: {e}")

if __name__ == "__main__":
    asyncio.run(main())
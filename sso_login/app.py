from flask import Flask, redirect, url_for, session, request, make_response
from flask_oauthlib.client import OAuth
import logging
from werkzeug.exceptions import HTTPException
from flask_cors import CORS

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# *************************************************************************************
# github sso login

app.secret_key = 'e5b0c2dfb8374e7a8f2c1c9c7a4e2b3a'  # 使用你生成的密钥
app.config['GITHUB_CONSUMER_KEY'] = 'Ov23liSvBbUEbyrHffIe'
app.config['GITHUB_CONSUMER_SECRET'] = 'b28178abe5ca58c509d2819dc623d151b2bbc044'

oauth = OAuth(app)
github = oauth.remote_app(
    'github',
    consumer_key=app.config['GITHUB_CONSUMER_KEY'],
    consumer_secret=app.config['GITHUB_CONSUMER_SECRET'],
    request_token_params={
        'scope': 'user:email',
    },
    base_url='https://api.github.com/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://github.com/login/oauth/access_token',
    authorize_url='https://github.com/login/oauth/authorize'
)

@github.tokengetter
def get_github_oauth_token():
    return session.get('github_token')

# @app.route('/')
# def index():
#     if 'github_token' in session:
#         me = github.get('user')
#         return f'Logged in as: {me.data["login"]}'
#     return redirect(url_for('login'))

@app.route('/login')
def login():
    redirect_uri = url_for('authorized', _external=True, _scheme='https')
    redirect_uri = redirect_uri.replace("https://192.168.10.9", "https://192.168.10.9:33380")
    logging.debug(f'Redirect URI: {redirect_uri}')  # 使用 logging 记录日志
    return github.authorize(callback=redirect_uri, prompt='login')

@app.route('/login/authorized')
def authorized():
    response = github.authorized_response()
    if response is None or response.get('access_token') is None:
        return 'Access denied: reason={} error={}'.format(
            request.args.get('error'), request.args.get('error_description')
        )

    # 设置 session 数据
    session['github_token'] = (response['access_token'], '')
    session['authenticated'] = True  # 确保设置认证标志

    # 获取用户信息
    me = github.get('user')
    username = me.data['login']
    session['username'] = username

    # return redirect("https://192.168.10.9:33380")
    return redirect("https://192.168.10.9:33380/github_sso/")

@app.route('/get_username')
def get_username():
    if 'authenticated' in session and session['authenticated']:
        return jsonify(username=session.get('username'))
    else:
        return jsonify({"error": "User not authenticated"}), 401

@app.route('/logout')
def logout():
    session.clear()  # 清除所有会话数据
    return redirect("https://192.168.10.9:33380/sso_ui/")

@app.route('/auth/check')
def auth_check():
    # 检查会话中是否存在认证标志
    if 'authenticated' in session and session['authenticated']:
        return '', 200  # 返回 200 状态表示已认证
    else:
        return '', 401  # 返回 401 状态表示未认证

# @app.route('/protected')
# def protected():
#     if 'github_token' not in session:
#         return redirect(url_for('login'))

# *************************************************************************************
# general login
from flask import Flask, request, jsonify, g, send_from_directory
import os
import traceback
import time
import mysql.connector

TABLE_TRANSLATION = "users"

# 数据库连接配置
db_config = {
    'host': 'mysql_host',
    'user': 'root',
    'password': 'root',
    'database': "sound_files_db"
}

def get_user_from_db(username, password):
    """
    从数据库中获取用户信息。
    """
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        query = f"SELECT username, password FROM {TABLE_TRANSLATION} WHERE username = %s AND password = %s"
        cursor.execute(query, (username, password))
        user = cursor.fetchone()
        cursor.close()
        connection.close()
        return user
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s:%(name)s - %(message)s", filename="/logs/login_log.log")

@app.route('/validate', methods=['POST'])
def validate():
    try:
        # 记录接收到的请求头和方法
        # logging.info(f"Headers: {request.headers}")
        # logging.info(f"Method: {request.method}")
        data = request.get_json(force=True)  # 强制将请求体解析为JSON，即使Content-Type错误
        username = data.get('username')
        password = data.get('password')

        logging.info(f"Received validation request for user: {username}")

        if not username or not password:
            logging.warning("Username or password not provided")
            return jsonify({"message": "Unauthorized"}), 401

        user = get_user_from_db(username, password)

        if not user:
            logging.warning(f"Invalid credentials for user: {username}")
            return jsonify({"message": "Unauthorized"}), 401

        session['authenticated'] = True  # 确保设置认证标志
        session['username'] = username

        logging.info(f"User {username} authenticated successfully")
        return jsonify({
            "message": "Login successful",
            "username": username,
            "redirect_url": f"https://192.168.10.9:33380/normal/"
        }), 200

    except Exception as e:
        logging.error(f"Error during authentication process: {traceback.format_exc()}")
        return jsonify({"message": "Internal Server Error"}), 500

def register_user(username, password):
    """
    在数据库中注册新用户。
    """
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)

        # 检查用户名是否已经存在
        check_query = "SELECT username FROM users WHERE username = %s"
        cursor.execute(check_query, (username,))
        existing_user = cursor.fetchone()

        if existing_user:
            # 如果用户已存在，返回相应消息
            cursor.close()
            connection.close()
            return {"success": False, "message": "Username already exists."}

        # 如果用户不存在，插入新用户数据
        insert_query = "INSERT INTO users (username, password) VALUES (%s, %s)"
        cursor.execute(insert_query, (username, password))
        connection.commit()

        cursor.close()
        connection.close()

        return {"success": True, "message": "User registered successfully."}
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return {"success": False, "message": f"Error: {err}"}

@app.route('/register', methods=['POST'])
def register():
    try:
        # 记录接收到的请求头和方法
        # logging.info(f"Headers: {request.headers}")
        logging.info(f"Method: {request.method}")
        data = request.get_json(force=True)
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            logging.warning("Username or password not provided")
            return jsonify({"success": False, "message": "Username and password are required."})

        logging.info(f"Attempting to register user: {username}")
        registration_result = register_user(username, password)
        if registration_result['success']:
            logging.info(f"User {username} registered successfully")
            # 模拟认证请求调用validate函数
            with app.test_request_context(json={'username': username, 'password': password}):
                # return validate()
                return jsonify({"message": "注册 successful"}), 200

        else:
            logging.warning(f"Registration failed for user {username}: {registration_result['message']}")
            return jsonify(registration_result), 400
    except Exception as e:
        logging.error(f"Error during registration process: {traceback.format_exc()}")
        return jsonify({"success": False, "message": "Internal Server Error"}), 500

# *************************************************************************************

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)

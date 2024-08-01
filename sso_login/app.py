from flask import Flask, redirect, url_for, session, request, make_response
from flask_oauthlib.client import OAuth
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


app = Flask(__name__)
app.secret_key = 'e5b0c2dfb8374e7a8f2c1c9c7a4e2b3a'  # 使用你生成的密钥
# app.config['GITHUB_CONSUMER_KEY'] = 'Ov23lifwxLDWsXCh4uAn'
# app.config['GITHUB_CONSUMER_SECRET'] = '2c1c661e91339d5535939b7fb196ed888c2b8b0f'
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

@app.route('/')
def index():
    if 'github_token' in session:
        me = github.get('user')
        return f'Logged in as: {me.data["login"]}'
    return redirect(url_for('login'))

@app.route('/login')
def login():
    redirect_uri = url_for('authorized', _external=True, _scheme='https')
    redirect_uri = redirect_uri.replace("https://192.168.10.9", "https://192.168.10.9:33380")
    logging.debug(f'Redirect URI: {redirect_uri}')  # 使用 logging 记录日志
    return github.authorize(callback=redirect_uri)

@app.route('/logout')
def logout():
    session.clear()  # 清除所有会话数据
    return redirect("https://192.168.10.9:33380/")

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
    # return redirect("https://192.168.10.9:33380")
    return redirect(f"https://192.168.10.9:33380/?username={me.data['login']}")

@app.route('/auth/check')
def auth_check():
    # 检查会话中是否存在认证标志
    if 'authenticated' in session and session['authenticated']:
        return '', 200  # 返回 200 状态表示已认证
    else:
        return '', 401  # 返回 401 状态表示未认证

@app.route('/protected')
def protected():
    if 'github_token' not in session:
        return redirect(url_for('login'))

@github.tokengetter
def get_github_oauth_token():
    return session.get('github_token')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5010, debug=True)

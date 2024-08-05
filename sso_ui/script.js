const API_BASE_URL = "https://192.168.10.9:33380";

//github
function continueWithGitHub() {
  window.location.href = `${API_BASE_URL}/sso_login`;
}

// 表单提交逻辑
document.getElementById("login-form").addEventListener("submit", function(event) {
    event.preventDefault();

    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;

    if (!username || !password) {
        document.getElementById("message").innerText = "Username and password are required.";
        return;
    }

    // 判断用户点击的是哪个按钮
    const action = document.activeElement.value;

    let url;
    if (action === "login") {
        url = `${API_BASE_URL}/normal_login`;
    } else if (action === "register") {
        url = `${API_BASE_URL}/normal_register`;
    }

    fetch(url, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ username: username, password: password })
    })
    .then(response => {
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error(' Invalid username or password.');
            }
            throw new Error(`Username ${username} already exists.`);
        }
        return response.json();
    })
    .then(data => {
        //document.getElementById("message").innerText = `${action === 'login' ? 'Login' : 'Registration'} successful!`;
        if (action === 'login') {
            // 如果是登录，则跳转到主页
            window.location.href = data.redirect_url;
        } else {
            // 如果是注册，显示注册成功的对话框
            showModal(`Registration successful!`);
        }
    })
    .catch(error => {
        showModal(`${action === 'login' ? 'Login' : 'Registration'} failed: ${error.message}`);
        console.error('Error:', error);
    });
});

// 显示模态框
function showModal(message) {
    const modal = document.getElementById("error-modal");
    const modalMessage = document.getElementById("modal-message");
    modalMessage.textContent = message;
    modal.style.display = "flex";
}

// 关闭模态框
function closeModal() {
    const modal = document.getElementById("error-modal");
    modal.style.display = "none";
}
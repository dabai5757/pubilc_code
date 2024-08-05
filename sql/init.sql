CREATE DATABASE IF NOT EXISTS sound_files_db;
USE sound_files_db;

CREATE TABLE sound_files (
    audio_id INT AUTO_INCREMENT PRIMARY KEY,
    user_name VARCHAR(255),             -- 用户名
    email VARCHAR(255),                 -- 邮箱
    password VARCHAR(255),              -- 密码（应加密存储）
    file_name VARCHAR(255) NOT NULL,
    audio_length INT,                   -- 文件时长
    file_type VARCHAR(50),              -- 文件类型（MIME类型）
    format VARCHAR(50),              -- 结果输出格式
    status ENUM('pending', 'processing', 'completed', 'canceled') NOT NULL DEFAULT 'pending',
    translation_language VARCHAR(50),   -- 目标语言
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    result_url VARCHAR(255),            -- 翻译结果的URL
    translation_start_time TIMESTAMP NULL,  -- 翻译开始时间
    translation_end_time TIMESTAMP NULL,    -- 翻译结束时间
    translation_time INT NULL,                -- 翻译持续时间（以秒为单位）
    login_method VARCHAR(50)            -- 登录方式（例如 GitHub, Google, Local）
);

-- INSERT INTO sound_files (
--     user_name, email, password, file_name, audio_length, file_type, status, translation_language, upload_time
-- ) VALUES
--     ('yinshuai5757', 'user1@example.com', 'encrypted_password1', 'audio1.mp3', 180, 'audio/mpeg', 'processing', 'English', '2024-07-31 12:00:00'),
--     ('yinshuai5757', 'user2@example.com', 'encrypted_password2', 'audio2.wav', 240, 'audio/wav', 'processing', 'Japanese', '2024-07-31 12:05:00'),
--     ('yinshuai5757', 'user3@example.com', 'encrypted_password3', 'audio3.ogg', 300, 'audio/ogg', 'completed', 'Chinese', '2024-07-31 12:10:00');

-- 创建用户认证表（无email字段）
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,  -- 用户名
    password VARCHAR(255) NOT NULL,         -- 密码（应加密存储）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 创建时间
);

-- 示例插入数据（请确保实际应用中密码是加密存储的）
INSERT INTO users (username, password) VALUES
('yin@123', '123');
-- ('johndoe', 'encrypted_password2'),
-- ('janedoe', 'encrypted_password3');
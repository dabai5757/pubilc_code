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
    translation_time INT NULL                -- 翻译持续时间（以秒为单位）
);

-- INSERT INTO sound_files (
--     user_name, email, password, file_name, audio_length, file_type, status, translation_language, upload_time
-- ) VALUES
--     ('yinshuai5757', 'user1@example.com', 'encrypted_password1', 'audio1.mp3', 180, 'audio/mpeg', 'processing', 'English', '2024-07-31 12:00:00'),
--     ('yinshuai5757', 'user2@example.com', 'encrypted_password2', 'audio2.wav', 240, 'audio/wav', 'processing', 'Japanese', '2024-07-31 12:05:00'),
--     ('yinshuai5757', 'user3@example.com', 'encrypted_password3', 'audio3.ogg', 300, 'audio/ogg', 'completed', 'Chinese', '2024-07-31 12:10:00');

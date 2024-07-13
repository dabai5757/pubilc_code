-- 创建数据库
CREATE DATABASE IF NOT EXISTS sound_files_db;

-- 选择使用数据库
USE sound_files_db;

-- 创建表
CREATE TABLE sound_files (
    audio_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    status ENUM('pending', 'processing', 'completed', 'canceled') NOT NULL DEFAULT 'pending',
    audio_length INT,
    result_url VARCHAR(255)
);

-- 插入初始数据并赋值 audio_length 和 result_url 列
-- INSERT INTO sound_files (user_id, file_name, status, audio_length, result_url) VALUES
-- (1, 'test_1.wav', 'pending', NULL, NULL);
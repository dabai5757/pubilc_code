CREATE DATABASE IF NOT EXISTS sound_files_db;
USE sound_files_db;
CREATE TABLE sound_files (
    audio_id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    status ENUM('pending', 'processing', 'completed', 'canceled') NOT NULL DEFAULT 'pending',
    audio_length INT,
    result_url VARCHAR(255),
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    translation_time TIMESTAMP NULL
);

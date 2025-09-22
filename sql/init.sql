CREATE DATABASE IF NOT EXISTS sound_files_db;
USE sound_files_db;

CREATE TABLE sound_files (
    audio_id INT AUTO_INCREMENT PRIMARY KEY,
    file_id VARCHAR(100) UNIQUE, -- ファイルIDフィールドを追加、ファイルの一意識別に使用
    user_name VARCHAR(255),
    email VARCHAR(255),
    password VARCHAR(255),
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT, -- ファイルサイズフィールドを追加（バイト単位）
    audio_length INT,
    file_type VARCHAR(50),
    format VARCHAR(50),
    number_of_channels ENUM('1ch', '2ch') NOT NULL DEFAULT '1ch',
    text_content LONGTEXT, -- 1ch & 2ch
    status ENUM('pending', 'processing', 'completed', 'canceled') NOT NULL DEFAULT 'pending',
    translation_language VARCHAR(50),
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    result_url VARCHAR(255),
    result_url_del_timestamp VARCHAR(255),
    translation_start_time TIMESTAMP NULL,
    translation_end_time TIMESTAMP NULL,
    translation_time INT NULL,
    cut_start_time TIME,
    cut_end_time TIME,
    login_method VARCHAR(50),
    timestamp_flag VARCHAR(50) DEFAULT '無'
);

CREATE TABLE sound_files_api (
    audio_id INT AUTO_INCREMENT PRIMARY KEY,
    user_name VARCHAR(255),
    audio_api_id INT,
    email VARCHAR(255),
    password VARCHAR(255),
    file_name VARCHAR(255) NOT NULL,
    audio_length INT,
    file_type VARCHAR(50),
    initial_prompt  VARCHAR(255),
    format VARCHAR(50),
    number_of_channels ENUM('1ch', '2ch') NOT NULL DEFAULT '1ch',
    text_content LONGTEXT, -- 1ch & 2ch
    channel_0_mic_content VARCHAR(255), -- 2ch-mic
    channel_1_speaker_content VARCHAR(255), -- 2ch-speaker
    status ENUM('pending', 'processing', 'completed', 'canceled') NOT NULL DEFAULT 'pending',
    translation_language VARCHAR(50),
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    result_url VARCHAR(255),
    translation_start_time TIMESTAMP NULL,
    translation_end_time TIMESTAMP NULL,
    translation_time INT NULL,
    login_method VARCHAR(50)
);

# test add
-- ALTER TABLE sound_files_api
-- ADD COLUMN test INT AFTER translation_end_time;

# test del
-- ALTER TABLE sound_files_api
-- DROP COLUMN test;
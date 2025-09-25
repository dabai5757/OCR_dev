CREATE DATABASE IF NOT EXISTS ocr_files_db;
USE ocr_files_db;

CREATE TABLE ocr_files (
    ocr_id INT AUTO_INCREMENT PRIMARY KEY,
    file_id VARCHAR(100) UNIQUE, -- ファイルIDフィールド、ファイルの一意識別に使用
    user_name VARCHAR(255),
    email VARCHAR(255),
    password VARCHAR(255),
    file_name VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255), -- 元のファイル名
    file_path VARCHAR(500), -- ファイル保存パス
    file_size BIGINT, -- ファイルサイズ（バイト単位）
    file_type ENUM('pdf', 'image') NOT NULL, -- ファイルタイプ
    image_format VARCHAR(50), -- 画像形式（jpg, png, tiff等）
    page_count INT, -- PDFの総ページ数
    range_start INT, -- OCR処理開始ページ
    range_end INT, -- OCR処理終了ページ
    text_content LONGTEXT, -- OCR結果テキスト
    status ENUM('pending', 'processing', 'completed', 'error', 'canceled') NOT NULL DEFAULT 'pending',
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processing_start_time TIMESTAMP NULL,
    processing_end_time TIMESTAMP NULL,
    processing_duration INT NULL, -- 処理時間（秒）
    result_url VARCHAR(255),
    error_message TEXT, -- エラーメッセージ
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- インデックスの作成（パフォーマンス向上のため）
CREATE INDEX idx_ocr_files_status ON ocr_files(status);
CREATE INDEX idx_ocr_files_upload_time ON ocr_files(upload_time);
CREATE INDEX idx_ocr_files_file_type ON ocr_files(file_type);
# YomiToku OCR API

日本語に特化したOCR（文字認識）APIサービスです。画像やPDFファイルから日本語テキストを抽出できます。

## 🚀 クイックスタート

### 1. 起動
```bash
docker-compose up -d
```

### 2. 使用方法
```bash
# 画像ファイルの場合
curl -X POST -F "file=@your_image.jpg" http://192.168.131.194:9552/ocr

# PDFファイルの場合
curl -X POST -F "file=@your_document.pdf" http://192.168.131.194:9552/ocr
```

### 3. 結果のダウンロード
APIレスポンスに含まれる`download_url`からMarkdown形式の結果をダウンロードできます。

## 📋 主な機能

- ✅ 日本語文字認識（7,000文字以上対応）
- ✅ 縦書きテキスト対応
- ✅ PDF・画像ファイル対応
- ✅ レイアウト解析
- ✅ 表構造認識
- ✅ 複数出力形式（JSON、Markdown、HTML、CSV）

## 🔧 必要な環境

- Docker
- Docker Compose

## 📝 API使用例

### ヘルスチェック
```bash
curl http://192.168.131.194:9552/health
```

### 基本的な使用方法
```bash
# Windows
curl -X POST -F "file=@C:\Users\username\Desktop\document.pdf" http://192.168.131.194:9552/ocr

# Linux/Mac
curl -X POST -F "file=@/path/to/document.pdf" http://192.168.131.194:9552/ocr
```

### オプションパラメータ
```bash
# 出力形式を指定
curl -X POST -F "file=@document.pdf" -F "format=html" http://192.168.131.194:9552/ocr

# GPU無効化
curl -X POST -F "file=@document.pdf" -F "use_gpu=false" http://192.168.131.194:9552/ocr
```

## 📤 APIレスポンス例

### 成功時
```json
{
  "status": "success",
  "request_id": "20250505_162345_abcd1234",
  "download_url": "http://192.168.131.194:9552/download/20250505_162345_abcd1234/document.md",
  "result": {
    "paragraphs": [...],
    "words": [...]
  },
  "completed": true
}
```

### エラー時
```json
{
  "error": "処理に失敗しました: エラーメッセージ"
}
```

## 🗂️ ファイル構成

```
yomitoku-ocr-api/
├── app/                 # アプリケーション
│   └── main.py         # メインファイル
├── static/             # 処理結果保存場所
├── docker-compose.yml  # Docker設定
└── README.md          # このファイル
```

## ❓ トラブルシューティング

### サービスが起動しない
```bash
docker-compose logs -f
```

### 処理が遅い場合
GPUが利用可能か確認：
```bash
docker-compose logs | grep "GPU"
```

### ファイルがアップロードできない
ファイルサイズが100MB以下であることを確認してください。

## 📄 ライセンス

YomiTokuはCC BY-NC-SA 4.0ライセンスです。
- 個人利用・研究目的：自由に使用可能
- 商用利用：別途ライセンスが必要

詳細：[YomiToku公式ページ](https://github.com/kotaro-kinoshita/yomitoku)
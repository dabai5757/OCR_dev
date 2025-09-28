# OCR_dev
社内向け OCR サービス（PDF / 画像から文字起こし）を管理・開発するリポジトリです。ファイルをアップロードすると、Markdown 形式で結果が得られます。

## 1. 主な機能
- PDF / 画像ファイルの OCR 処理
- PDF ページ範囲の指定
- 結果表示と Markdown / テキストでのダウンロード
- 完了通知（ブラウザ通知を有効にしている場合）
- 処理後のファイル自動削除（個人情報が残らない）

## 2. 利用方法（ユーザー）
1. https://192.168.32.232:33400/ocr-prod/ にアクセス
2. **ファイル選択** を押し、PDF または画像を選択
3. PDF の場合はページ範囲を入力
4. 緑色の **選択したファイルでOCR実行** を押す
5. 完了後、画面で結果を確認またはダウンロード

> メモ: 200MB 超のファイルはアップロード不可。未処理タスクが多い場合は一時的にアップロードが制限されます。

## 3. 開発環境セットアップ
1. リポジトリ取得
   ```bash
   git clone <REPO_URL>
   cd OCR_dev
   ```
2. `.env` を作成
   - `.env.example` を `.env` にコピー
   - 共有中の値（Notion 等）を貼り付け
3. Docker ネットワークとコンテナ起動
   ```bash
   docker network create ai-network
   docker compose -f docker-compose.yml up -d --build      # 開発環境
   docker compose -f docker-compose-stg.yml up -d --build  # STG環境
   ```
4. 動作確認
   - 開発: https://127.0.0.1:33380/ocr-dev/
   - STG: https://127.0.0.1:33392/ocr-stg/

## 4. API の概要
| メソッド | エンドポイント | 説明 |
|----------|----------------|------|
| POST     | `/api/aibt/ocr` | ファイルを送信して OCR を開始（task_id を取得） |
| GET      | `/api/aibt/ocr/status/{task_id}` | 処理状況・結果を取得 |

**例**
```bash
# OCR リクエスト
curl -k -X POST http://127.0.0.1:5560/api/aibt/ocr \
  -F "file=@\"C:\\sample.pdf\"" \
  -F "file_type=pdf" \
  -F "range_start=1" \
  -F "range_end=5"

# ステータス確認
curl -X GET http://127.0.0.1:5560/api/aibt/ocr/status/1
```
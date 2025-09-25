## OCR_dev
OCR（光学文字認識）システムの開発用リポジトリ

## Features
- 社内ローカル環境で実行できる
- 推定完了時刻表示
- 完了後ポップアップ通知（ブラウザ通知有効化必要ある）
- 対応可能ファイル（PDF、画像ファイル）
- 結果出力タイプ（Markdown形式）
- PDFページ範囲指定機能
- OCR結果自動表示・ダウンロード
- 個人情報が残らない
    - アップロードファイル削除（OCR完了後に即時削除）
    - OCR結果削除（最大2時間保持）
- Auto Monitoring（コンテナが停止した場合など、Slackへ通知）
- Auto Deploy
- 高精度OCR処理（yomitoku_ocrエンジン使用）
- 大きめなPDFファイルでも処理できる
- レイアウト保持機能

## Environment
prod
```bash
https://192.168.32.232:33400/ocr-prod/
```

stg
```bash
https://192.168.32.232:33392/ocr-stg/
```

dev
```bash
https://192.168.32.184:33380/ocr-dev/
```

## Auto Deploy
pull requestが承認され、マージされるとgithub actionsが走り、A6000(Gentoo)のマシンにデプロイされる

## Auto Monitoring
GitHub Actionsで自動デプロイ時に、指定されたDockerコンテナの監視が開始される。コンテナが停止した場合や修復後に、Slackへリアルタイムで通知が送信される。
- 停止したコンテナに関しては、一度だけエラーメッセージがSlackに送信され、修復が完了するまで再度通知は送られない。
- 自動デプロイ時にはコンテナの停止が正常な挙動であるため、この際にはSlackへの通知は送信されない。
- サービス（コンテナ）監視 → ジェンツーで監視
- サーバー（ジェンツー自体＆アデリー自体）監視 → 互いにSSH接続で監視

## サービスの使い方（ユーザー向け）
- https://192.168.32.232:33400/ocr-prod/ をアクセス
- 【ファイル選択】ボタンを押す　→　PDFまたは画像ファイル選択　→　PDFの場合はページ範囲を指定　→　【OCR実行】ボタンを押す　→　待つ　→　OCR完了（結果表示・DL可能）
- 補足：
    - 【ファイル選択】から一度に1つのファイルしかアップロードできないこと
    - 200MBを超えるファイルのアップロードできないこと
    - PDFファイルの場合、ページ範囲を指定してOCR処理可能
    - サーバーで未処理のタスクが10件以上の場合、【ファイル選択】が動的に無効化になります。10件以下になったら、まだ【ファイル選択】が動的に有効化になります。

## localでの実行方法（開発者向け）

- WSL
    - Ubuntu-22.04
    - NVIDIA cuDNN 9.0.0 [dpkg -l | grep libcudnn]
    - NVIDIA-SMI 550.54.10 [nvidia-smi]
    - Driver Version: 551.61 [nvidia-smi]
    - CUDA Version: 12.4 [nvidia-smi]

- Docker Container
    - nvidia/cuda:12.3.2-cudnn9-devel-ubuntu22.04

- リポジトリDL
    - git clone URL
    - cd OCR_dev

- ENVファイル設定
    - ".env.example" を ".env" という名前で COPY する
    - ENV内容は以下notionからコピーして、貼り付ける
    -  https://www.notion.so/ENV-106c129916b080b8be0ae8430970d3a0

- モデルDL
    - 特に設定する必要がない。
      - 補足：初回だけDLされて、その後は volumes【model_cache_volume_dev】を削除しない限り、再DLしない。

- OCR API用の使い方(簡易版)
    - OCRを行うAPIには以下の2つのエンドポイントがあります：
        - 1. **PDFまたは画像ファイルを送信して、OCR処理を開始し、task_idが返されるAPI**
        - 2. **task_idを使用してOCR処理状況と結果を取得するAPI**

    - APIの使い方

        - ⓵ PDFまたは画像ファイルを送信してOCR処理を開始するAPI

            - 以下のAPIを実行すると、ファイルがサーバーに送信され、処理に使用する `task_id` が返されます。
            - ファイルパスは必要に応じて変更してください。

            - リクエスト例
                ```bash
                curl -k -X POST http://127.0.0.1:5560/api/aibt/ocr -F "file=@\"C:\Users\user\Desktop\sample.pdf\"" -F "file_type=pdf" -F "file_size=1024000" -F "range_start=1" -F "range_end=5" -F "page_count=10"
                ```

            - レスポンス例(正常受付の場合：200)
                ```bash
                {
                    "success": true,
                    "task_id": 1,
                    "message": "OCR請求已提交，,正在処理中",
                    "filename": "sample.pdf"
                }
                ```

            - 補足：
                - task_id：MySQLにあるOCRタスクのID（MySQLのauto_increment機能）
                - PDFの場合、range_start/range_endでページ範囲を指定可能

        - ⓶ OCR処理状況と結果を取得するAPI
            - ①で返された`task_id` を使用してOCR処理状況と結果を取得するAPI

            - リクエスト例
                ```bash
                curl -X GET http://127.0.0.1:5560/api/aibt/ocr/status/1
                ```

            - レスポンス例（statusがcompletedの場合）
                ```bash
                {
                    "success": true,
                    "task_id": 1,
                    "status": "completed",
                    "ocr_result": "# 文書タイトル\n\n文書の内容...",
                    "filename": "sample.pdf",
                    "result_url": "http://example.com/download/result.md"
                }
                ```

            - レスポンス例（statusがprocessing＆pendingの場合）
                ```bash
                {
                    "success": true,
                    "task_id": 1,
                    "status": "processing",
                    "ocr_result": null
                }
                ```

            - レスポンス例（送信したtask_idが存在しない場合）
                ```bash
                {
                    "error": "任務不存在"
                }
                ```

- ネットワーク作成＆Docker Compose
    - docker network create ai-network-stg
    - STG環境の場合
    　　- docker compose -f "docker-compose-stg.yml" up -d --build
    - DEV環境の場合
    　　- docker compose -f "docker-compose.yml" up -d --build

- 確認
    - STG: https://127.0.0.1:33392/ocr-stg/
    - DEV: https://127.0.0.1:33380/ocr-dev/

- 補足
    - DEV環境での開発＆修正が完了したら、developブランチにマージし、STG環境で問題あるかどうかのを確認してください。mainブランチへのマージしないでください。 (mainブランチへのマージは毎月のメンテナンス時に行う)
    - ジェンツーでSTG環境＆PROD環境で直接修正しないでください。

## よくあるエラーと対策
エラー1：【Error response from daemon: unknown or invalid runtime name: nvidia】

対策：
- ファイルを編集
    - sudo nano /etc/docker/daemon.json

- 次の内容を追加または修正します。
```bash
{
    "default-runtime": "nvidia",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
```

- Dockerサービスの再起動
    - sudo systemctl restart docker

エラー2：
- [ERROR] [MY-012960] [InnoDB] Cannot create redo log files because data files are corrupt or the database was not shut down cleanly after creating the data files.
- [ERROR] [MY-012930] [InnoDB] Plugin initialization aborted with error Generic error.
- [ERROR] [MY-010334] [Server] Failed to initialize DD Storage Engine
- [ERROR] [MY-010020] [Server] Data Dictionary initialization failed.

対策：
- ocrすべてコンテナ&イメージを削除
- docker volume rm ocr_mysql_data_volume_stg
- docker volume create ocr_mysql_data_volume_stg
- docker compose -f docker-compose-stg.yml up -d

エラー3：
- MYSQLへの接続ができない（my_stg.cnfの書き込み権限を無くしたので、このエラーが出ないはず。）

対策：
- リポジトリにあるsql/my_stg.cnf の権限を読み取り専用にする（右クリック　→　読み取り専用項目チェック入れ）

エラー4：
- DBテーブル内容を変更、追加した場合、内容が反映されない問題

対策：
- volume 削除
```bash
    docker volume rm ocr_mysql_data_volume_stg
    docker compose -f docker-compose-stg.yml up -d
```

エラー5：
- OCR処理が完了しても前端でtext_contentが空になる問題

対策：
- db_to_queueサービスとocr-apiサービスの静的ファイル共有を確認
- docker-compose-stg.ymlでvolume設定を確認
```bash
    docker compose -f docker-compose-stg.yml restart db_to_queue
```

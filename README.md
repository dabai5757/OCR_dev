## AIBT_dev
AIBTの開発用リポジトリ

## Features
- 社内ローカル環境で実行できる
- 推定完了時刻表示
- 完了後ポップアップ通知（ブラウザ通知有効化必要ある）
- 対応可能ファイル（mp3、mp4、mpweg、mpga、m4a、wav、webm）
- 結果出力タイプ（txt、md、rtf）
- 対応可能言語（日本語、英語、中国語）
- 文字起こし結果自動ダウンロード
- 個人情報が残らない
    - 音声ファイル削除（翻訳完了後に即時削除）
    - 翻訳結果削除（最大2時間保持）
- Auto Monitoring（コンテナが停止した場合など、Slackへ通知）
- Auto Deploy
- リアルタイム文字起こしをサポートするAPI
- 大きめなビデオでも処理できる
- タイムスタンプ有り無し選択できる

## Environment
prod
```bash
https://192.168.32.232:33400/aibt-prod/
```

stg
```bash
https://192.168.32.232:33390/aibt-stg/
```

dev
```bash
https://192.168.32.184:33380/aibt-dev/
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
- https://192.168.32.232:33400/aibt-prod/ をアクセス
- 【ファイル選択】ボタンを押す　→　ファイル選択　→　【文字起こし】ボタンを押す　→　待つ　→　文字起こし完了（結果自動DLされる）
- 補足：
    - 【ファイル選択】から一度に1つのファイルしかアップロードできないこと
    -  200MBを超えるファイルのアップロードできないこと
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
    - cd AIBT_dev

- ENVファイル設定
    - ".env.example" を ".env" という名前で COPY する
    - ENV内容は以下notionからコピーして、貼り付ける
    -  https://www.notion.so/ENV-106c129916b080b8be0ae8430970d3a0

- モデルDL
    - 特に設定する必要がない。
      - 補足：初回だけDLされて、その後は volumes【model_cache_volume_dev】を削除しない限り、再DLしない。

- chrome AI用APIの使い方(簡易版)
    - 文字起こしを行うAPIには以下の2つのエンドポイントがあります：
        - 1. **音声ファイルを送信して 、１分後に、結果取得成功の場合は、翻訳結果 ＆ audio_id が返される。失敗の場合は、該当する情報が返されるAPI**
        - 2. **1で結果取得できない場合は、1で返された`audio_id` を使用して文字起こし結果を取得するAPI**

    - APIの使い方

        - ⓵ 音声ファイルを送信して 、１分後に、結果取得成功の場合は、翻訳結果 ＆ audio_id が返される。失敗の場合は、該当する情報が返されるAPI

            - 以下のAPIを実行すると、音声ファイルがサーバーに送信され、処理に使用する `audio_id` が返されます。
            - 音声ファイルパス必要に応じて変更してください。

            - リクエスト例
                ```bash
                curl -k -X POST http://127.0.0.1:33379/api/aibt/transcribe_api -H "Authorization: Bearer no-key" -F "ID=1234567890" -F "user_name=your_username" -F "audio_file=@\"C:\Users\vbtea\Desktop\audio sample\sample_2.wav\"" -F "initial_prompt=詳しく言うと"　　　　　　　　【httpの場合】
                curl -k -X POST https://127.0.0.1:33380/api/aibt/transcribe_api -H "Authorization: Bearer no-key" -F "ID=1234567890" -F "user_name=your_username" -F "audio_file=@\"C:\Users\vbtea\Desktop\audio sample\sample_2.wav\"" -F "initial_prompt=詳しく言うと"    　　 【httpsの場合】
                ```

            - レスポンス例(翻訳完了の場合：200)
                ```bash
                {
                    "status": "completed",
                    "data": {
                        "audio_id": 1,
                        "message": "映画鑑賞やボーリングを行っております\n"
                                "この言葉からどんなことを思い浮かべますか 常夏、雄大な自然、グルメ、リラクセーション\n"
                                "交換受付はいつでも組合事務局で行っております 皆様のご利用をお待ちしております\n"
                                "全国のニュースでもお伝えしましたが今日は大寒 関東地方の内陸や山沿いではけさ氷点下の冷え込みとなりました\n"
                                "関東地方はこれから明日にかけて気温があまり上がらず 北部の山沿いで雪が降りやすい見込みです\n"
                    }
                }
                ```

            - レスポンス例(翻訳未完了の場合：202)
                - statusがpendingの場合
                ```bash
                {
                    "status": "pending",
                    "data": {
                        "audio_id": 1,
                        "message": "null"
                    }
                }
                ```
                - statusがprocessingの場合
                ```bash
                {
                    "status": "processing",
                    "data": {
                        "audio_id": 1,
                        "message": "null"
                    }
                }
                ```

            - レスポンス例(エラーの場合：404)
                ```bash
                {
                    "status": "error",
                    "data": {
                        "audio_id": 1,
                        "message": "not found"
                    }
                }
                ```

            - 補足：
                - audio_id：MYSQLにある音声データの ID（MySQLのauto_increment機能）

        - ⓶ 文字起こし結果を取得する
            - ①で結果取得できない場合は、①で返された`audio_id` を使用して文字起こし結果を取得するAPI

            - リクエスト例
                ```bash
                curl -X POST http://127.0.0.1:33379/api/aibt/get_api_content -H "Content-Type: application/json" -d "{\"audio_id\": \"1\"}"　　　　　　【httpの場合】
                curl -k -X POST https://127.0.0.1:33380/api/aibt/get_api_content -H "Content-Type: application/json" -d "{\"audio_id\": \"1\"}"　　　　【httpsの場合】
                ```

            - レスポンス例（statusがcompletedの場合）
                ```bash
                {
                    "text_content": "一番めのテスト。\n二番めのテスト。\n..."
                }
                ```

            - レスポンス例（statusがproccessing＆pendingの場合）
                ```bash
                {
                    "text_content":null
                }
                ```

            - レスポンス例（送信したaudio_idが存在しない場合）
                ```bash
                {
                    "error":"audio_id does not exist"
                }
                ```

            - レスポンス例（送信したaudio_idが存在するが、文字起こし結果が自動削除された場合）
                ```bash
                {
                    "error": "\u5185\u90e8\u30a8\u30e9\u30fc\u304c\u767a\u751f\u3057\u307e\u3057\u305f\u3002"
                }
                ```

- ネットワーク作成＆Docker Compose
    - docker network create ai-network
    - ubuntuの場合
    　　- docker compose -f "docker-compose.yml" up -d --build
    - macの場合
    　　- docker compose -f "docker-compose-mac.yml" up -d --build

- 確認
    - https://127.0.0.1:33380/aibt-dev/

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
- aibtすべてコンテナ&イメージを削除
- docker volume rm aibt_mysql_data_volume_dev
- docker volume create aibt_mysql_data_volume_dev
- docker compose up -d

エラー3：
- MYSQLへの接続ができない（my_dev.cnfの書き込み権限を無くしたので、このエラーが出ないはず。）

対策：
- リポジトリにあるsql/my_dev.cnf の権限を読み取り専用にする（右クリック　→　読み取り専用項目チェック入れ）

エラー4：
- DBテーブル内容を変更、追加した場合、内容が反映されない問題

対策：
- volume 削除
```bash
    docker volume rm aibt_mysql_data_volume_dev
    docker-compose up
```

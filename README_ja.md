# RedmineMCP

[Claude Code](https://claude.ai/claude-code) から Redmine を直接操作できる MCP（Model Context Protocol）サーバーです。
RHEL または Docker 上で HTTP サーバーとして動作します。認証情報はサーバーに保存されず、Claude Code の設定ファイルから HTTP ヘッダー経由でリクエストごとに渡されます。

---

## 主な特徴

1. **コンテキスト重視の設計**
   チケットと一緒にジャーナル（コメント）を返すため、AI が履歴を踏まえた正確な提案や進捗サマリーを生成できます。

2. **ステートレス設計**
   API キーはクライアントからリクエストごとに渡され、サーバーには保存されません。これにより 3 つの実用的なメリットがあります：
   - **最高レベルのセキュリティ** — サーバーが侵害されても、保存された API キーは存在しないため盗まれるものがありません。
   - **マルチテナント対応** — サーバーを 1 台チームで共有できます。各ユーザーは Claude 側に自分の API キーを設定するだけで、サーバー側にユーザーごとの設定は不要です。
   - **認証情報変更のメンテナンスが不要** — Redmine のパスワードや API キーが変わっても、更新が必要なのはクライアント側の Claude 設定のみです。サーバー側の変更は不要です。

3. **強力な全文検索**
   `search_issues_full` はチケットの件名・説明・コメントを横断検索し、AI が処理しやすい形式で結果を返します。

---

## 必要要件

- Redmine 5.0 以上（`update_journal` の使用には Redmine 5.0 以上が必要）
- Python 3.12
- RHEL（systemd デプロイ）**または** Docker

---

## Redmine の初期設定

RedmineMCP を使用する前に、Redmine の REST API を有効化してください（デフォルト無効）。

1. 管理者でログイン
2. **管理 → 設定 → API** タブ → **REST による Web サービスを有効にする** にチェックして保存

API キーの取得：

1. 右上メニューの **個人設定** を開く
2. **API アクセスキー** の **表示** をクリック
3. このキーを Claude Code 設定の `X-Redmine-API-Key` に使用します

---

## アーキテクチャ

```
クライアント PC（Claude Code / Mac または Windows）
    ↓ HTTP :8000 + ヘッダー（X-Redmine-URL / X-Redmine-API-Key）
サーバー（RHEL または Docker）
    ↓ REST API
Redmine
```

---

## インストール

### Option A — RHEL（systemd）

**1. ファイルをサーバーに転送**
```bash
ssh root@<サーバー> "mkdir -p /tmp/redmine-mcp-stateless"
scp redmine_mcp_interface.py redmine_mcp_server.py requirements.txt \
    redmine-mcp-stateless.service install.sh uninstall.sh \
    root@<サーバー>:/tmp/redmine-mcp-stateless/
```

**2. インストーラを実行**
```bash
cd /tmp/redmine-mcp-stateless
chmod +x install.sh
./install.sh
```

`install.sh` が行う処理：
- 事前チェック（root 権限、OS、Python 3.12、必要ファイルの確認）
- 専用システムユーザー `redmine-mcp-stateless` の作成
- `/opt/redmine-mcp-stateless/` へのファイルコピーと Python 仮想環境の構築
- logrotate の設定
- systemd サービスの登録・起動
- SELinux 設定（ポート 8000 を `http_port_t` として登録）
- firewalld でポート 8000 を開放
- サービス起動とポートリッスンの確認

**3. 動作確認**
```bash
systemctl status redmine-mcp-stateless
journalctl -u redmine-mcp-stateless -f
```

**アンインストール**
```bash
bash uninstall.sh
```

---

### Option B — Docker

既存の Redmine インスタンスに接続する MCP サーバーをコンテナーとして起動します。ホストから Redmine にアクセスできる必要があります。

**1. ビルドして起動**
```bash
docker compose up -d --build
```

**2. 動作確認**
```bash
docker compose ps
docker compose logs -f redmine-mcp-stateless
```

**停止**
```bash
docker compose down
```

---

## Claude Code 設定

`~/.claude.json` に以下を追加してください。

**RHEL**
```json
{
  "mcpServers": {
    "redmine-mcp-stateless": {
      "type": "sse",
      "url": "http://<サーバーIP>:8000/sse",
      "headers": {
        "X-Redmine-URL": "https://<RedmineのURL>",
        "X-Redmine-API-Key": "<APIキー>"
      }
    }
  }
}
```

**Docker**
```json
{
  "mcpServers": {
    "redmine-mcp-stateless": {
      "type": "sse",
      "url": "http://localhost:8000/sse",
      "headers": {
        "X-Redmine-URL": "https://<RedmineのURL>",
        "X-Redmine-API-Key": "<APIキー>"
      }
    }
  }
}
```

**stdio トランスポート（レジストリ検査・ローカル用）**

通常は SSE（HTTP）で動作しますが、環境変数 `MCP_TRANSPORT=stdio` を設定すると標準入出力（stdio）トランスポートに切り替わります。このモードでは認証情報を HTTP ヘッダーではなく環境変数で渡します：

```bash
MCP_TRANSPORT=stdio REDMINE_URL=https://<RedmineのURL> REDMINE_API_KEY=<APIキー> \
    python redmine_mcp_interface.py
```

主に MCP レジストリ（Glama など）によるサーバー検査向けのモードです。チーム共有デプロイでは SSE を使用してください。

---

## 利用可能なツール

### チケット
| ツール | 説明 |
|---|---|
| `list_issues` | チケット一覧（プロジェクト・ステータス・担当者でフィルタ可） |
| `get_issue` | チケット詳細（コメント・添付ファイル含む） |
| `create_issue` | チケット作成 |
| `update_issue` | チケット更新またはコメント追加 |
| `update_journal` | コメント編集（Redmine 5.0 以上が必要） |
| `list_issues_with_journals` | チケット一覧＋全コメント（担当者別進捗確認に便利） |
| `search_issues_full` | 件名・説明・コメントを横断した全文検索 |

### プロジェクト
| ツール | 説明 |
|---|---|
| `list_projects` | プロジェクト一覧 |
| `get_project` | プロジェクト詳細 |

### マスターデータ
| ツール | 説明 |
|---|---|
| `list_statuses` | ステータス一覧 |
| `list_trackers` | トラッカー一覧 |
| `list_priorities` | 優先度一覧 |
| `list_users` | ユーザー一覧（管理者権限が必要な場合あり） |

---

## 取得できる情報

| カテゴリ | フィールド |
|---|---|
| **プロジェクト** | ID、識別子、名前、説明、ステータス |
| **チケット** | ID、件名、説明、ステータス、プロジェクト、トラッカー、優先度、担当者、作成日・更新日 |
| **ジャーナル（コメント）** | コメント ID、本文、作成日、作成者 |
| **添付ファイル** | ファイル ID、ファイル名、サイズ、MIME タイプ、説明、作成者、作成日 |
| **ステータス / トラッカー / 優先度** | ID、名前 |
| **ユーザー** | ID、ログイン名、姓、名、フルネーム |

---

## ファイル構成

| ファイル | 説明 |
|---|---|
| `redmine_mcp_interface.py` | MCP サーバーエントリーポイント |
| `redmine_mcp_server.py` | Redmine REST API クライアント |
| `requirements.txt` | Python 依存パッケージ |
| `Dockerfile` | コンテナーイメージ（python:3.12-slim） |
| `compose.yml` | Docker Compose 設定 |
| `redmine-mcp-stateless.service` | systemd ユニットファイル |
| `install.sh` | RHEL インストールスクリプト |
| `uninstall.sh` | アンインストールスクリプト |
| `example-claude-code-config.json` | Claude Code 設定例 |

---

## セキュリティ

- Redmine URL と API キーは**サーバーに保存されません**
- リクエストごとに `X-Redmine-URL` / `X-Redmine-API-Key` ヘッダーで渡されます
- サーバー側では `ContextVar` に一時保存され、リクエスト完了後に破棄されます
- RHEL では専用の非特権ユーザー（`redmine-mcp-stateless`）で動作します

---

## ライセンス

MIT

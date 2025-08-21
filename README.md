# なまけ猫AI 配信ツール

OBSとVOICEVOXを使って「なまけ猫AI」が口パク・音声付きで配信に参加できます。  
Gemini APIを設定すれば、自動応答やノベルゲーム実況など高度なモードも利用可能です。  

---

## 1. 準備

### OBS 設定
1. シーンに以下を追加してください:
   - **mouth_open** → `namakeneko_open.png`
   - **mouth_closed** → `namakeneko_closed.png`

### VOICEVOX 設定
1. [VOICEVOX ENGINE 0.24.1 (Windows CPU版)](https://github.com/VOICEVOX/voicevox_engine/releases) をダウンロード  
2. 解凍後、以下を実行  
   ```powershell
   voicevox_engine-windows-cpu-0.24.1/run.exe
   ```

### Gemini APIキー（自動応答を使う場合のみ必要）
1. [Google AI Studio](https://aistudio.google.com/prompts/new_chat) からAPIキーを取得  
2. Windows PowerShellで環境変数を設定  
   ```powershell
   $env:GEMINI_API_KEY="取得したAPIキー"
   ```

---

## 2. 起動方法
```powershell
python.exe .\namakeneko_ai.py
```

- APIキーを設定していない場合は、以下が表示されます  
  ```
  Gemini APIキーを入力してください: 1
  ```
  → 適当に `1` と入力すればOK

---

## 3. 初期設定

1. **口パクアニメーションを使うか**  
   ```
   口パクアニメーション機能を使用しますか？ (y/n): y
   ```

2. **モード選択**  
   ```
   === モード選択 ===
   1. 配信モード - チャット応答・定期つぶやき機能    
   2. 対話モード - 1対1での会話
   3. テキスト読み上げモード - テキストファイルを読み上げ
   4. ノベルゲーム実況モード - ブラウザゲームを自動実況
   5. Webページ読み上げモード - URLを読んでコメント  
   6. OBS画面解析モード - ブラウザソースを見てコメント
   7. テストモード - 基本機能のテスト
   モードを選択してください (1/2/3/4/5/6/7): 1
   ```

3. **テキスト表示ウィンドウ**  
   ```
   テキスト表示ウィンドウを開きますか？ (y/n): n
   ```

4. **YouTube Live連携**  
   ```
   YouTube Live連携を使用しますか？ (y/n): n
   ```

---

## 4. コマンド一覧（配信モード時）

| コマンド | 動作 |
|----------|------|
| `chat:ユーザー名:メッセージ` | チャットをシミュレート |
| `comment` | ランダムにつぶやく |
| `speak:テキスト` | 指定テキストを音声で発話 |
| `talk` | 自由に話す（対話形式） |
| `toggle` | 自動応答 ON/OFF 切り替え |
| `quit` | 配信モード終了 |
| `help` | ヘルプを表示 |

例:  
```powershell
コマンド入力: speak:テスト
```

---

## 5. トラブルシューティング
- 動かない場合や機能を追加したい場合は、**Kiroでこのプロジェクトを開き、チャットで相談**してください。  

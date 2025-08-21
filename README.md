# OBS Setting
シーン/ソース/mouth_openでnamakeneko_open.pngを設定
シーン/ソース/mouth_closedでnamakeneko_closed.pngを設定

# VoiceBox Setting
https://github.com/VOICEVOX/voicevox_engine/releases
VOICEVOX ENGINE 0.24.1のWindows（CPU版）をダウンロードして解凍し、
voicevox_engine-windows-cpu-0.24.1/run.exeを起動する

# GeminiAPIKeyを取得するため、下記にアクセスしてGetAPIKeyする（回答自動生成しないなら不要）
https://aistudio.google.com/prompts/new_chat

# Windows PowerShell で環境設定（回答自動生成しないなら不要）
$env:GEMINI_API_KEY=""

# start
python.exe .\namakeneko_ai.py

# GeminiAPIKeyを設定していない場合はこれが表示されるため、1を入れる（なんでもいい）
Gemini APIキーを入力してください: 1

# yにするとOBSのmouth_open、mouth_closeを表示、非表示で口パク切り替える
口パクアニメーション機能を使用しますか？ (y/n): y

# 1を入力
=== モード選択 ===
1. 配信モード - チャット応答・定期つぶやき機能    
2. 対話モード - 1対1での会話
3. テキスト読み上げモード - テキストファイルを読み上げ
4. ノベルゲーム実況モード - ブラウザゲームを自動実況
5. Webページ読み上げモード - URLを読んでコメント  
6. OBS画面解析モード - ブラウザソースを見てコメン ト
7. テストモード - 基本機能のテスト
モードを選択してください (1/2/3/4/5/6/7):1

# nを選択（怠け猫AIの回答を表示するウィンドウなくてもいい）
=== 配信モード開始 ===
テキスト表示ウィンドウを開きますか？ (y/n): n     

# nを選択（Youtubeのチャット取得して回答する場合はy。API連携とか面倒なので飛ばします）
YouTube Live連携を使用しますか？ (y/n): n

# speak:テストと入れるとVoiceBoxで音声生成して、口パクで話します。
コマンド:
  'chat:ユーザー名:メッセージ' - チャットメッセー ジをシミュレート
  'comment' - 手動でランダムつぶやき
  'speak:テキスト' - 指定したテキストを手動で発話 
  'talk' - 自由に話させる（対話形式）
  'toggle' - 自動応答のON/OFF切り替え
  'quit' - 配信モード終了
  'help' - ヘルプ表示

コマンド入力 (または Enter で待機): speak:テスト

# 動かない場合、機能を変えたい場合は、Kiroでこのプロジェクトを開いて、チャットで聞くと教えてくれるはず・・・

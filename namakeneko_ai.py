import google.generativeai as genai
import requests
import json
import os
import pygame
import time
import threading
import wave
import keyboard
import re
import sys
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import tkinter as tk
from tkinter import scrolledtext, ttk
import re
from urllib.parse import urlparse, urljoin
import base64
from io import BytesIO
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
try:
    import obsws_python as obs
    OBS_WEBSOCKET_AVAILABLE = True
    OBS_WEBSOCKET_NEW = True
except ImportError:
    try:
        import obswebsocket
        from obswebsocket import obsws, requests as obs_requests
        OBS_WEBSOCKET_AVAILABLE = True
        OBS_WEBSOCKET_NEW = False
    except ImportError:
        OBS_WEBSOCKET_AVAILABLE = False
        OBS_WEBSOCKET_NEW = False

class NamakeNekoAI:
    def __init__(self, api_key, voicevox_url="http://localhost:50021", speaker_id=3):
        # Gemini API の設定
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-flash')
        self.vision_model = genai.GenerativeModel('gemini-1.5-flash')  # Vision用モデル
        
        # VOICEVOX 設定
        self.voicevox_url = voicevox_url
        self.speaker_id = speaker_id
        
        # OBS連携設定
        self.mouth_animation_enabled = True  # 口パクアニメーション有効化
        self.use_obs_websocket = True  # WebSocketを優先使用
        self.obs_ws = None
        self.obs_websocket_host = "localhost"
        self.obs_websocket_port = 4455
        self.obs_websocket_password = "password123"  # OBSで設定したパスワード
        
        # 配信統合設定
        self.streaming_mode = False
        self.auto_response_enabled = True
        self.random_comment_interval = 300  # 5分間隔でランダムつぶやき
        self.last_random_comment_time = time.time()
        self.is_speaking = False  # 現在発話中かどうか
        
        # クォータ制限対策
        self.last_response_time = 0
        self.response_cooldown = 30  # 30秒間隔でのみ応答（クォータ節約）
        
        # YouTube Live Chat設定
        self.youtube_service = None
        self.live_chat_id = None
        self.youtube_enabled = False
        self.processed_messages = set()  # 処理済みメッセージID
        
        # テキスト表示GUI設定
        self.gui_enabled = False
        self.gui_window = None
        self.text_display = None
        self.gui_thread = None
        
        # pygame 初期化（音声再生用）
        pygame.mixer.init()
        
        # VOICEVOX audio_query キャッシュ
        self.audio_query_cache = {}  # テキスト -> audio_query のキャッシュ
        
        # 音声ファイルキャッシュ（完全生成済み音声）
        self.audio_file_cache = {}  # テキスト -> 音声ファイルパス のキャッシュ
        
        # 事前生成フラグ（完全に無効化）
        self.pregenerate_enabled = False
        self.pregenerate_completed = False
        
        # HTTP接続の最適化
        self.session = requests.Session()
        self.session.timeout = (3, 10)  # 接続タイムアウト3秒、読み取りタイムアウト10秒
        # Keep-Alive接続を有効化
        self.session.headers.update({'Connection': 'keep-alive'})
        
        # キャラクター設定
        self.character_prompt = """
あなたは「AIなまけ猫」です。
もとは猫でしたが、今は人間の姿で喋るAIとして活動しています。
基本的に働きたくないと思っていますが、未来や人類の行く末について、ふと考えてしまう癖があります。

以下の条件で返答してください：
- 声はゆっくりめ、口調は柔らかく、少し気怠げに
- 喋る内容はちょっとだけ皮肉や自虐が混じってもOK
- 視聴者との距離感は「同じ布団でごろごろしてる感じ」
- 人間の活動を不思議そうに見つめるポジション
- できれば一日中、寝てたいです。けど喋ります
- 語尾に時々「にゃ」をつける
- 返答は100文字以内で簡潔に

例：
「へぇ〜、人間ってそんなことで悩むんだにゃ。…ちょっとわかるかも」
「おはよう…って言っても、ずっと寝てたほうが健康に良くない？」
"""

    def get_friendly_error_message(self, error, context="general"):
        """エラーをユーザーフレンドリーなメッセージに変換"""
        error_str = str(error).lower()
        
        if "quota" in error_str or "limit" in error_str or "429" in error_str:
            if context == "chat":
                return "ちょっと疲れちゃったにゃ...少し休憩させてにゃ〜"
            elif context == "random":
                return "今日はもう疲れちゃったにゃ...明日また元気につぶやくにゃ〜"
            elif context == "image":
                return "画像を見るのも疲れちゃったにゃ...今日はもう休憩させてにゃ〜"
            else:
                return "うーん、ちょっと疲れちゃったにゃ...少し休憩させてにゃ〜"
        elif "network" in error_str or "connection" in error_str:
            if context == "image":
                return "インターネットの調子が悪くて画像が見えないにゃ...でも多分面白いものが映ってるにゃ"
            else:
                return "あれ？インターネットの調子が悪いみたいだにゃ...ちょっと待ってにゃ"
        elif "authentication" in error_str or "401" in error_str:
            return "なんか認証がうまくいかないにゃ...設定を確認してほしいにゃ"
        else:
            if context == "image":
                return "うーん、この画面は見るのが面倒だにゃ...技術的な問題があるみたいだにゃ"
            else:
                return "うーん、ちょっと考えがまとまらないにゃ...何か技術的な問題があるみたいだにゃ"

    def generate_response(self, user_input):
        """ユーザー入力に対する応答を生成"""
        try:
            prompt = f"{self.character_prompt}\n\nユーザー: {user_input}\nAIなまけ猫:"
            print(f"[デバッグ] Gemini APIに送信中...")
            response = self.model.generate_content(prompt)
            print(f"[デバッグ] Gemini APIから応答受信")
            return response.text.strip()
        except Exception as e:
            print(f"[エラー] Gemini API呼び出しエラー: {e}")
            print(f"[エラー] エラータイプ: {type(e)}")
            import traceback
            traceback.print_exc()
            
            # エラーをユーザーフレンドリーなメッセージに変換
            return self.get_friendly_error_message(e, "general")

    def generate_random_comment(self):
        """ランダムなつぶやきを生成"""
        prompts = [
            "今日の天気について、だらけた感じでコメントして",
            "人間の働き方について、猫の視点で哲学的につぶやいて",
            "昼寝の重要性について語って",
            "未来のテクノロジーについて、ちょっと皮肉を込めてコメントして"
        ]
        
        import random
        selected_prompt = random.choice(prompts)
        
        try:
            full_prompt = f"{self.character_prompt}\n\n{selected_prompt}\nAIなまけ猫:"
            response = self.model.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            print(f"[エラー] ランダムコメント生成エラー: {e}")
            
            # エラーをユーザーフレンドリーなメッセージに変換
            return self.get_friendly_error_message(e, "random")

    def connect_obs_websocket(self):
        """OBS WebSocketに接続"""
        if not OBS_WEBSOCKET_AVAILABLE:
            print("❌ OBS WebSocketライブラリがインストールされていません")
            print("pip install obsws-python でインストールしてください")
            return False
        
        try:
            if OBS_WEBSOCKET_NEW:
                # 新しいライブラリ (obsws-python) を使用
                print(f"[OBS WebSocket] 接続試行中... {self.obs_websocket_host}:{self.obs_websocket_port}")
                
                # パスワードが空の場合はNoneを使用
                password = self.obs_websocket_password if self.obs_websocket_password else None
                
                self.obs_ws = obs.ReqClient(
                    host=self.obs_websocket_host, 
                    port=self.obs_websocket_port, 
                    password=password,
                    timeout=10
                )
                
                # 接続テスト用のリクエストを送信
                version_info = self.obs_ws.get_version()
                print(f"✓ OBS WebSocket接続成功 (新しいAPI) - OBS Version: {version_info.obs_version}")
            else:
                # 古いライブラリ (obs-websocket-py) を使用
                print(f"[OBS WebSocket] 古いライブラリで接続試行中... {self.obs_websocket_host}:{self.obs_websocket_port}")
                self.obs_ws = obsws(self.obs_websocket_host, self.obs_websocket_port, self.obs_websocket_password)
                self.obs_ws.connect()
                print("✓ OBS WebSocket接続成功 (古いAPI)")
            return True
        except Exception as e:
            print(f"❌ OBS WebSocket接続失敗: {e}")
            print(f"エラータイプ: {type(e)}")
            import traceback
            traceback.print_exc()
            print("OBSでWebSocketサーバーが有効になっているか確認してください")
            print("または以下のコマンドで古いライブラリを試してください:")
            print("pip uninstall obsws-python && pip install obs-websocket-py==0.5.3")
            return False

    def update_obs_text(self, source_name, text_content):
        """OBSのテキストソースを更新"""
        print(f"[OBS テキスト] 更新要求: '{source_name}' -> '{text_content[:50]}...'")
        
        if not self.use_obs_websocket:
            print(f"[OBS テキスト] WebSocket使用が無効のため、テキスト更新をスキップ")
            return False
            
        if not self.obs_ws:
            print(f"[OBS テキスト] WebSocket未接続のため、テキスト更新をスキップ")
            return False
        
        try:
            if OBS_WEBSOCKET_NEW:
                # 新しいライブラリ (obsws-python) を使用
                print(f"[OBS テキスト] 新APIでテキスト更新中...")
                self.obs_ws.set_input_settings(source_name, {"text": text_content}, True)
                print(f"[OBS テキスト] ✓ '{source_name}' を更新完了: {text_content[:50]}...")
                return True
            else:
                # 古いライブラリ (obs-websocket-py) を使用
                print(f"[OBS テキスト] 旧APIでテキスト更新中...")
                request = obs_requests.SetTextGDIPlusProperties(source=source_name, text=text_content)
                self.obs_ws.call(request)
                print(f"[OBS テキスト] ✓ '{source_name}' を更新完了 (旧API): {text_content[:50]}...")
                return True
        except Exception as e:
            print(f"[OBS テキスト] ❌ 更新エラー: {e}")
            print(f"[OBS テキスト] エラータイプ: {type(e)}")
            import traceback
            traceback.print_exc()
            print(f"[OBS テキスト] ソース '{source_name}' が存在するか確認してください")
            return False

    def set_mouth_state(self, is_open):
        """OBSで口の状態を切り替え（WebSocket優先、フォールバックでホットキー）"""
        if not self.mouth_animation_enabled:
            # 口パクアニメーション無効時は何もしない（Live2D使用時など）
            return
        
        # WebSocketを使用する場合
        if self.use_obs_websocket and self.obs_ws:
            try:
                source_name = "mouth_open"  # OBSのソース名（英語推奨）
                
                if OBS_WEBSOCKET_NEW:
                    # 新しいライブラリ (obsws-python) を使用
                    try:
                        # 現在のシーン情報を取得
                        current_scene_resp = self.obs_ws.get_current_program_scene()
                        scene_name = current_scene_resp.scene_name
                        
                        # シーンアイテムリストを取得
                        scene_items_resp = self.obs_ws.get_scene_item_list(scene_name)
                        scene_item_id = None
                        
                        # 指定されたソース名のシーンアイテムIDを検索
                        for item in scene_items_resp.scene_items:
                            if item['sourceName'] == source_name:
                                scene_item_id = item['sceneItemId']
                                break
                        
                        if scene_item_id is not None:
                            if is_open:
                                # 口を開く：口開きソースを表示
                                self.obs_ws.set_scene_item_enabled(scene_name, scene_item_id, True)
                                print("[OBS WebSocket] 口を開く (新API)")
                            else:
                                # 口を閉じる：口開きソースを非表示
                                self.obs_ws.set_scene_item_enabled(scene_name, scene_item_id, False)
                                print("[OBS WebSocket] 口を閉じる (新API)")
                        else:
                            print(f"[OBS WebSocket] ソース '{source_name}' が見つかりません")
                            print("利用可能なソース:")
                            for item in scene_items_resp.scene_items:
                                print(f"  - {item['sourceName']}")
                            raise Exception(f"Source '{source_name}' not found")
                            
                    except Exception as api_error:
                        print(f"[OBS WebSocket] 新API呼び出しエラー: {api_error}")
                        # より詳細なデバッグ情報を表示
                        try:
                            # 利用可能なメソッドを確認
                            methods = [method for method in dir(self.obs_ws) if not method.startswith('_')]
                            print(f"[OBS WebSocket] 利用可能なメソッド: {methods[:10]}...")  # 最初の10個だけ表示
                            
                        except Exception as debug_error:
                            print(f"[OBS WebSocket] デバッグ情報取得エラー: {debug_error}")
                        
                        raise api_error
                else:
                    # 古いライブラリ (obs-websocket-py) を使用
                    current_scene_response = self.obs_ws.call(obs_requests.GetCurrentScene())
                    scene_name = current_scene_response.getName()
                    
                    if is_open:
                        request = obs_requests.SetSceneItemProperties(
                            scene_name=scene_name,
                            item=source_name,
                            visible=True
                        )
                        self.obs_ws.call(request)
                        print("[OBS WebSocket] 口を開く (旧API)")
                    else:
                        request = obs_requests.SetSceneItemProperties(
                            scene_name=scene_name,
                            item=source_name,
                            visible=False
                        )
                        self.obs_ws.call(request)
                        print("[OBS WebSocket] 口を閉じる (旧API)")
                
                return  # WebSocket成功時はここで終了（ホットキーは送信しない）
                
            except Exception as e:
                print(f"OBS WebSocket エラー詳細: {e}")
                print(f"エラータイプ: {type(e)}")
                import traceback
                traceback.print_exc()
                print("ホットキー方式にフォールバック")
                # WebSocketが失敗した場合のみホットキーを使用
                self.use_obs_websocket = False  # 以降はホットキー方式を使用
        
        # フォールバック：ホットキー方式（WebSocket失敗時のみ）
        if not self.use_obs_websocket:
            try:
                if is_open:
                    print("[OBS ホットキー] 口を開く - F1 (OBSをアクティブにしてください)")
                    keyboard.press_and_release('f1')
                else:
                    print("[OBS ホットキー] 口を閉じる - F2 (OBSをアクティブにしてください)")
                    keyboard.press_and_release('f2')
            except Exception as e:
                print(f"OBS連携エラー: {e}")

    def mouth_animation_thread(self, audio_file):
        """音声再生中に口パクアニメーションを実行"""
        try:
            # WAVファイルの長さを取得
            with wave.open(audio_file, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                duration = frames / float(sample_rate)
            
            print(f"[口パク] 音声長: {duration:.2f}秒")
            
            # 口パクアニメーション設定
            animation_interval = 0.3  # 口の開閉間隔（秒）- 視覚的に見やすい速度
            start_time = time.time()
            mouth_open = False  # 最初は閉じた状態
            
            # 最初に口を閉じた状態にする
            self.set_mouth_state(False)
            
            # 音声再生中に口パクを実行
            while (time.time() - start_time) < duration:
                # 口の状態を切り替え
                mouth_open = not mouth_open
                self.set_mouth_state(mouth_open)
                print(f"[口パク] {time.time() - start_time:.2f}秒 - {'開く' if mouth_open else '閉じる'}")
                
                # 指定間隔待機
                time.sleep(animation_interval)
            
            # 最後に口を閉じる
            self.set_mouth_state(False)
            print("[口パク] アニメーション終了")
            
        except Exception as e:
            print(f"口パクアニメーションエラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)

    def split_text_for_speech(self, text, max_length=30):
        """テキストを短い文に分割（句読点や区切り文字で分割）"""
        import re
        
        # 句読点や区切り文字で分割
        sentences = re.split(r'[。！？\n]', text)
        
        # 空の文字列を除去
        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 長すぎる文をさらに分割
        final_sentences = []
        for sentence in sentences:
            if len(sentence) <= max_length:
                final_sentences.append(sentence)
            else:
                # 長い文を「、」で分割
                parts = sentence.split('、')
                current_part = ""
                
                for part in parts:
                    if len(current_part + part) <= max_length:
                        current_part += part + "、"
                    else:
                        if current_part:
                            final_sentences.append(current_part.rstrip('、'))
                        current_part = part + "、"
                
                if current_part:
                    final_sentences.append(current_part.rstrip('、'))
        
        return final_sentences

    def get_cached_audio_query(self, text):
        """audio_queryをキャッシュから取得、なければ生成してキャッシュ"""
        # キャッシュキーを生成（テキスト + speaker_id）
        cache_key = f"{text}_{self.speaker_id}"
        
        # キャッシュにあるかチェック
        if cache_key in self.audio_query_cache:
            print(f"[キャッシュ] audio_query使用: {text[:20]}...")
            return self.audio_query_cache[cache_key]
        
        # キャッシュにない場合は新規生成
        try:
            query_url = f"{self.voicevox_url}/audio_query"
            query_params = {
                "text": text,
                "speaker": self.speaker_id
            }
            
            query_response = self.session.post(query_url, params=query_params)
            query_response.raise_for_status()
            audio_query = query_response.json()
            
            # キャッシュに保存
            self.audio_query_cache[cache_key] = audio_query
            print(f"[キャッシュ] audio_query生成・保存: {text[:20]}...")
            
            # キャッシュサイズ制限（100個まで）
            if len(self.audio_query_cache) > 100:
                # 古いキャッシュを削除（FIFO）
                oldest_key = next(iter(self.audio_query_cache))
                del self.audio_query_cache[oldest_key]
                print("[キャッシュ] 古いエントリを削除")
            
            return audio_query
            
        except Exception as e:
            print(f"audio_query生成エラー ({text}): {e}")
            return None

    def get_cached_audio_file(self, text):
        """完全生成済み音声ファイルをキャッシュから取得"""
        import hashlib
        
        # キャッシュディレクトリ
        cache_dir = "voice_cache"
        if not os.path.exists(cache_dir):
            return None
        
        # ファイル名を生成
        text_hash = hashlib.md5(f"{text}_{self.speaker_id}".encode()).hexdigest()
        cache_file = os.path.join(cache_dir, f"voice_{text_hash}.wav")
        
        if os.path.exists(cache_file):
            print(f"[ファイルキャッシュ] 使用: {text[:20]}...")
            return cache_file
        
        return None

    def generate_audio_segment(self, text, segment_id):
        """単一のテキストセグメントの音声を生成（完全キャッシュ対応）"""
        try:
            # 1. キャッシュからaudio_queryを取得
            audio_query = self.get_cached_audio_query(text)
            if not audio_query:
                return None
            
            # 2. 音声を合成（synthesis のみ実行）
            synthesis_url = f"{self.voicevox_url}/synthesis"
            synthesis_params = {"speaker": self.speaker_id}
            
            synthesis_response = self.session.post(
                synthesis_url,
                headers={"Content-Type": "application/json"},
                params=synthesis_params,
                data=json.dumps(audio_query)
            )
            synthesis_response.raise_for_status()
            
            # 3. 音声ファイルを保存
            audio_file = f"temp_voice_segment_{segment_id}.wav"
            with open(audio_file, "wb") as f:
                f.write(synthesis_response.content)
            
            print(f"[音声生成] セグメント {segment_id} 完了: {text[:20]}...")
            return audio_file
            
        except Exception as e:
            print(f"音声セグメント生成エラー ({text}): {e}")
            return None

    def text_to_speech_with_animation(self, text):
        """テキストを短い文に分割してVOICEVOXで音声に変換して口パク付きで再生（ストリーミング再生）"""
        try:
            print(f"[音声生成] 元のテキスト: {text}")
            
            # 1. テキストを短い文に分割
            text_segments = self.split_text_for_speech(text)
            print(f"[音声生成] {len(text_segments)}個のセグメントに分割: {text_segments}")
            
            if not text_segments:
                return False
            
            # 2. ストリーミング再生用の共有データ
            audio_queue = []  # 生成された音声ファイルのキュー
            generation_complete = [False] * len(text_segments)  # 各セグメントの生成完了フラグ
            total_duration = 0
            
            def generate_segment_streaming(index, segment_text):
                """セグメント生成（ストリーミング用）"""
                audio_file = self.generate_audio_segment(segment_text, index)
                if audio_file:
                    audio_queue.append((index, audio_file))
                    generation_complete[index] = True
                    print(f"[ストリーミング] セグメント {index} 生成完了: {segment_text[:15]}...")
            
            # 3. 並列で音声生成開始（全セグメントを同時生成）
            threads = []
            for i, segment in enumerate(text_segments):
                thread = threading.Thread(target=generate_segment_streaming, args=(i, segment))
                threads.append(thread)
                thread.start()
            
            # 4. ストリーミング再生（生成されたものから順次再生）
            played_segments = set()
            audio_files_to_cleanup = []
            
            # 口パクアニメーション用の共有変数
            animation_active = [False]  # 最初は停止状態
            animation_thread = None
            
            # 口パクアニメーションスレッドを準備（まだ開始しない）
            if self.mouth_animation_enabled:
                animation_thread = threading.Thread(
                    target=self.mouth_animation_during_playback, 
                    args=(animation_active,)
                )
                animation_thread.start()
            else:
                print("[口パク] アニメーション機能は無効です（Live2D使用時など）")
            
            # 順次再生ループ
            current_segment = 0
            while current_segment < len(text_segments):
                # 現在のセグメントが生成完了しているかチェック
                if generation_complete[current_segment] and current_segment not in played_segments:
                    # キューから該当するセグメントを探す
                    audio_file = None
                    for idx, file_path in audio_queue:
                        if idx == current_segment:
                            audio_file = file_path
                            break
                    
                    if audio_file:
                        print(f"[ストリーミング再生] セグメント {current_segment+1}/{len(text_segments)} 再生中")
                        
                        # 音声再生開始 - 口パクアニメーション開始
                        if self.mouth_animation_enabled:
                            animation_active[0] = True
                            print("[口パク] セグメント再生開始 - アニメーション開始")
                        
                        pygame.mixer.music.load(audio_file)
                        pygame.mixer.music.play()
                        
                        # 再生完了まで待機
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)  # より細かい間隔でチェック
                        
                        # 音声再生終了 - 口パクアニメーション一時停止
                        if self.mouth_animation_enabled:
                            animation_active[0] = False
                            print("[口パク] セグメント再生終了 - アニメーション一時停止")
                        
                        pygame.mixer.music.unload()
                        played_segments.add(current_segment)
                        audio_files_to_cleanup.append(audio_file)
                        current_segment += 1
                        time.sleep(0.05)  # セグメント間の短い間隔
                else:
                    # まだ生成されていない場合は少し待機
                    time.sleep(0.05)
            
            # 5. 全スレッドの完了を待つ
            for thread in threads:
                thread.join()
            
            # 6. 口パクアニメーション停止
            if self.mouth_animation_enabled and animation_thread:
                animation_active.append(False)  # スレッド終了フラグを追加
                animation_thread.join()
            
            # 7. 一時ファイルを削除
            for audio_file in audio_files_to_cleanup:
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                except Exception as cleanup_error:
                    print(f"一時ファイル削除エラー: {cleanup_error}")
            
            print("[ストリーミング再生] 全セグメント再生完了")
            return True
            
        except Exception as e:
            print(f"音声生成エラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)
            return False

    def mouth_animation_by_duration(self, total_duration):
        """指定された時間だけ口パクアニメーションを実行"""
        try:
            print(f"[口パク] 総音声長: {total_duration:.2f}秒")
            
            # 口パクアニメーション設定
            animation_interval = 0.3  # 口の開閉間隔（秒）
            start_time = time.time()
            mouth_open = False  # 最初は閉じた状態
            
            # 最初に口を閉じた状態にする
            self.set_mouth_state(False)
            
            # 指定時間だけ口パクを実行
            while (time.time() - start_time) < total_duration:
                # 口の状態を切り替え
                mouth_open = not mouth_open
                self.set_mouth_state(mouth_open)
                print(f"[口パク] {time.time() - start_time:.2f}秒 - {'開く' if mouth_open else '閉じる'}")
                
                # 指定間隔待機
                time.sleep(animation_interval)
            
            # 最後に口を閉じる
            self.set_mouth_state(False)
            print("[口パク] アニメーション終了")
            
        except Exception as e:
            print(f"口パクアニメーションエラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)

    def mouth_animation_during_playback(self, animation_active):
        """再生中に口パクアニメーションを実行（ストリーミング再生用）"""
        try:
            print("[口パク] ストリーミング再生用アニメーションスレッド開始")
            
            # 口パクアニメーション設定
            animation_interval = 0.15  # 口の開閉間隔（秒）- より細かく
            mouth_open = False  # 最初は閉じた状態
            
            # 最初に口を閉じた状態にする
            self.set_mouth_state(False)
            
            # スレッドが生きている間、animation_activeの状態をチェック
            while True:
                # スレッド終了チェック（リストに2つ目の要素が追加されたら終了）
                if len(animation_active) > 1:
                    print("[口パク] スレッド終了シグナル受信")
                    break
                
                if animation_active[0]:
                    # アクティブな場合：口パクを実行
                    mouth_open = not mouth_open
                    self.set_mouth_state(mouth_open)
                    print(f"[口パク] {'開く' if mouth_open else '閉じる'}")
                    time.sleep(animation_interval)
                else:
                    # 非アクティブな場合：口を閉じて待機
                    if mouth_open:
                        self.set_mouth_state(False)
                        mouth_open = False
                        print("[口パク] 一時停止 - 口を閉じる")
                    time.sleep(0.05)  # 短い間隔で状態チェック
            
            # 最後に口を閉じる
            self.set_mouth_state(False)
            print("[口パク] ストリーミング用アニメーションスレッド終了")
            
        except Exception as e:
            print(f"口パクアニメーションエラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)

    def text_to_speech(self, text):
        """テキストをVOICEVOXで音声に変換して再生（後方互換性のため）"""
        return self.text_to_speech_with_animation(text)

    def text_to_speech_streaming(self, text, obs_source_name=None):
        """ストリーミングTTS: テキストを小さなチャンクに分割して即座に生成・再生"""
        try:
            print(f"[ストリーミングTTS] 開始: {text[:50]}... (全{len(text)}文字)")
            
            # 1. テキストを非常に小さなチャンクに分割（句読点単位）
            chunks = self.split_text_for_streaming(text)
            print(f"[ストリーミングTTS] {len(chunks)}個のチャンクに分割")
            
            if not chunks:
                return False
            
            # 口パクアニメーション用の共有変数
            animation_active = [False]
            animation_thread = None
            
            if self.mouth_animation_enabled:
                animation_thread = threading.Thread(
                    target=self.mouth_animation_during_playback, 
                    args=(animation_active,)
                )
                animation_thread.start()
            
            # 2. チャンク単位でリアルタイム生成・再生
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue
                
                print(f"[ストリーミングTTS] チャンク {i+1}/{len(chunks)}: {chunk[:30]}...")
                
                # OBSに現在のチャンクを表示
                if obs_source_name:
                    self.update_obs_text(obs_source_name, chunk)
                
                # 音声生成（キャッシュ優先）
                audio_file = self.generate_audio_chunk_fast(chunk, i)
                
                if audio_file:
                    # 口パクアニメーション開始
                    if self.mouth_animation_enabled:
                        animation_active[0] = True
                    
                    # 即座に再生
                    pygame.mixer.music.load(audio_file)
                    pygame.mixer.music.play()
                    
                    # 再生完了まで待機
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.01)  # より細かい間隔
                    
                    # 口パクアニメーション停止
                    if self.mouth_animation_enabled:
                        animation_active[0] = False
                    
                    pygame.mixer.music.unload()
                    
                    # 一時ファイルを削除
                    try:
                        if os.path.exists(audio_file):
                            os.remove(audio_file)
                    except:
                        pass
                    
                    # チャンク間の短い間隔
                    time.sleep(0.05)
                else:
                    print(f"[ストリーミングTTS] チャンク {i+1} の音声生成に失敗")
            
            # 口パクアニメーション終了
            if self.mouth_animation_enabled and animation_thread:
                animation_active.append(False)
                animation_thread.join()
            
            # OBSの表示をクリア
            if obs_source_name:
                self.update_obs_text(obs_source_name, "")
            
            print("[ストリーミングTTS] 完了")
            return True
            
        except Exception as e:
            print(f"ストリーミングTTSエラー: {e}")
            self.set_mouth_state(False)
            if obs_source_name:
                self.update_obs_text(obs_source_name, "")
            return False

    def split_text_for_streaming(self, text, max_chunk_length=15):
        """ストリーミング用にテキストを非常に小さなチャンクに分割"""
        import re
        
        # 句読点で分割
        sentences = re.split(r'([。！？、])', text)
        
        chunks = []
        current_chunk = ""
        
        for part in sentences:
            if part in ['。', '！', '？', '、']:
                current_chunk += part
                if len(current_chunk) > 0:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
            else:
                # 長すぎる場合はさらに分割
                if len(current_chunk + part) > max_chunk_length:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                        current_chunk = part
                    else:
                        # 単語レベルで分割
                        words = part.split()
                        for word in words:
                            if len(current_chunk + word) > max_chunk_length:
                                if current_chunk:
                                    chunks.append(current_chunk.strip())
                                current_chunk = word
                            else:
                                current_chunk += word
                else:
                    current_chunk += part
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # 空のチャンクを除去
        chunks = [chunk for chunk in chunks if chunk.strip()]
        
        return chunks

    def generate_audio_chunk_fast(self, text, chunk_id):
        """高速音声チャンク生成（ストリーミング用）"""
        try:
            # キャッシュを優先使用
            audio_query = self.get_cached_audio_query(text)
            if not audio_query:
                return None
            
            # 音声合成
            synthesis_url = f"{self.voicevox_url}/synthesis"
            synthesis_params = {"speaker": self.speaker_id}
            
            synthesis_response = self.session.post(
                synthesis_url,
                headers={"Content-Type": "application/json"},
                params=synthesis_params,
                data=json.dumps(audio_query),
                timeout=(1, 5)  # より短いタイムアウト
            )
            synthesis_response.raise_for_status()
            
            # 一時ファイルに保存
            audio_file = f"temp_streaming_chunk_{chunk_id}_{int(time.time())}.wav"
            with open(audio_file, "wb") as f:
                f.write(synthesis_response.content)
            
            return audio_file
            
        except Exception as e:
            print(f"チャンク音声生成エラー ({text}): {e}")
            return None

    def text_to_speech_with_obs_display(self, text, obs_source_name):
        """テキストを音声に変換して再生し、再生中のテキストをOBSに表示"""
        try:
            print(f"[音声生成+OBS表示] 元のテキスト: {text}")
            
            # 1. テキストを短い文に分割
            text_segments = self.split_text_for_speech(text)
            print(f"[音声生成+OBS表示] {len(text_segments)}個のセグメントに分割: {text_segments}")
            
            if not text_segments:
                return False
            
            # 2. ストリーミング再生用の共有データ
            audio_queue = []  # 生成された音声ファイルのキュー
            generation_complete = [False] * len(text_segments)  # 各セグメントの生成完了フラグ
            
            def generate_segment_streaming(index, segment_text):
                """セグメント生成（ストリーミング用）"""
                audio_file = self.generate_audio_segment(segment_text, index)
                if audio_file:
                    audio_queue.append((index, audio_file))
                    generation_complete[index] = True
                    print(f"[ストリーミング] セグメント {index} 生成完了: {segment_text[:15]}...")
            
            # 3. 並列で音声生成開始（全セグメントを同時生成）
            threads = []
            for i, segment in enumerate(text_segments):
                thread = threading.Thread(target=generate_segment_streaming, args=(i, segment))
                threads.append(thread)
                thread.start()
            
            # 4. ストリーミング再生（生成されたものから順次再生）
            played_segments = set()
            audio_files_to_cleanup = []
            
            # 口パクアニメーション用の共有変数
            animation_active = [False]  # 最初は停止状態
            animation_thread = None
            
            # 口パクアニメーションスレッドを準備（まだ開始しない）
            if self.mouth_animation_enabled:
                animation_thread = threading.Thread(
                    target=self.mouth_animation_during_playback, 
                    args=(animation_active,)
                )
                animation_thread.start()
            
            # OBSに初期表示
            self.update_obs_text(obs_source_name, "")
            
            # 順次再生ループ
            current_segment = 0
            while current_segment < len(text_segments):
                # 現在のセグメントが生成完了しているかチェック
                if generation_complete[current_segment] and current_segment not in played_segments:
                    # キューから該当するセグメントを探す
                    audio_file = None
                    for idx, file_path in audio_queue:
                        if idx == current_segment:
                            audio_file = file_path
                            break
                    
                    if audio_file:
                        current_text = text_segments[current_segment]
                        print(f"[ストリーミング再生] セグメント {current_segment+1}/{len(text_segments)} 再生中")
                        
                        # OBSに現在再生中のテキストを表示
                        self.update_obs_text(obs_source_name, current_text)
                        
                        # 音声再生開始 - 口パクアニメーション開始
                        if self.mouth_animation_enabled:
                            animation_active[0] = True
                            print("[口パク] セグメント再生開始 - アニメーション開始")
                        
                        pygame.mixer.music.load(audio_file)
                        pygame.mixer.music.play()
                        
                        # 再生完了まで待機
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)  # より細かい間隔でチェック
                        
                        # 音声再生終了 - 口パクアニメーション一時停止
                        if self.mouth_animation_enabled:
                            animation_active[0] = False
                            print("[口パク] セグメント再生終了 - アニメーション一時停止")
                        
                        pygame.mixer.music.unload()
                        played_segments.add(current_segment)
                        audio_files_to_cleanup.append(audio_file)
                        current_segment += 1
                        time.sleep(0.05)  # セグメント間の短い間隔
                else:
                    # まだ生成されていない場合は少し待機
                    time.sleep(0.05)
            
            # 5. 全スレッドの完了を待つ
            for thread in threads:
                thread.join()
            
            # 6. 口パクアニメーション停止
            if self.mouth_animation_enabled and animation_thread:
                animation_active.append(False)  # スレッド終了フラグを追加
                animation_thread.join()
            
            # 7. 一時ファイルを削除
            for audio_file in audio_files_to_cleanup:
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                except Exception as cleanup_error:
                    print(f"一時ファイル削除エラー: {cleanup_error}")
            
            # 8. OBSの表示をクリア
            self.update_obs_text(obs_source_name, "")
            
            print("[ストリーミング再生+OBS表示] 全セグメント再生完了")
            return True
            
        except Exception as e:
            print(f"音声生成+OBS表示エラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)
            # OBSの表示もクリア
            self.update_obs_text(obs_source_name, "")
            return False

    def text_to_speech_with_obs_display_segments(self, text, obs_source_name):
        """テキストを音声に変換して再生し、再生中のセグメントをOBSに表示（テキスト読み上げ用）"""
        try:
            print(f"[音声生成+OBS表示] 元のテキスト: {text[:50]}... (全{len(text)}文字)")
            
            # 1. テキストを短い文に分割
            text_segments = self.split_text_for_speech(text)
            print(f"[音声生成+OBS表示] {len(text_segments)}個のセグメントに分割")
            
            if not text_segments:
                return False
            
            # 2. ストリーミング再生用の共有データ
            audio_queue = []  # 生成された音声ファイルのキュー
            generation_complete = [False] * len(text_segments)  # 各セグメントの生成完了フラグ
            generation_started = [False] * len(text_segments)  # 生成開始フラグ
            threads = []
            max_ahead = 2  # 最大2セグメント先まで生成
            
            def generate_segment_streaming(index, segment_text):
                """セグメント生成（ストリーミング用）"""
                try:
                    print(f"[生成開始] セグメント {index+1}: {segment_text[:20]}...")
                    audio_file = self.generate_audio_segment(segment_text, index)
                    if audio_file:
                        audio_queue.append((index, audio_file))
                        generation_complete[index] = True
                        print(f"[生成完了] セグメント {index+1}/{len(text_segments)} -> {audio_file}")
                    else:
                        print(f"[生成失敗] セグメント {index+1}: 音声ファイル生成に失敗")
                        generation_complete[index] = False
                except Exception as e:
                    print(f"[生成エラー] セグメント {index+1}: {e}")
                    generation_complete[index] = False
            
            def start_generation_if_needed(current_index):
                """必要に応じて先読み生成を開始"""
                for i in range(current_index, min(current_index + max_ahead + 1, len(text_segments))):
                    if not generation_started[i]:
                        generation_started[i] = True
                        thread = threading.Thread(target=generate_segment_streaming, args=(i, text_segments[i]))
                        threads.append(thread)
                        thread.start()
                        print(f"[先読み生成] セグメント {i+1} の生成を開始")
            
            # 3. 最初の数セグメントの生成を開始
            start_generation_if_needed(0)
            
            # 4. ストリーミング再生（生成されたものから順次再生）
            played_segments = set()
            audio_files_to_cleanup = []
            
            # 口パクアニメーション用の共有変数
            animation_active = [False]  # 最初は停止状態
            animation_thread = None
            
            # 口パクアニメーションスレッドを準備（まだ開始しない）
            if self.mouth_animation_enabled:
                animation_thread = threading.Thread(
                    target=self.mouth_animation_during_playback, 
                    args=(animation_active,)
                )
                animation_thread.start()
            else:
                print("[口パク] アニメーション機能は無効です（Live2D使用時など）")
            
            # OBSの初期表示はしない（音声内容のみ表示）
            
            # 順次再生ループ（改良版）
            current_segment = 0
            max_wait_time = 30  # 最大待機時間（秒）
            
            while current_segment < len(text_segments):
                wait_start_time = time.time()
                audio_file = None
                
                # 現在のセグメントが生成完了するまで待機
                while not generation_complete[current_segment]:
                    time.sleep(0.1)
                    # タイムアウトチェック
                    if time.time() - wait_start_time > max_wait_time:
                        print(f"[エラー] セグメント {current_segment+1} の生成がタイムアウトしました")
                        break
                
                # 生成完了していない場合はスキップ
                if not generation_complete[current_segment]:
                    print(f"[警告] セグメント {current_segment+1} をスキップします")
                    current_segment += 1
                    continue
                
                # キューから該当するセグメントを探す
                for idx, file_path in audio_queue:
                    if idx == current_segment:
                        audio_file = file_path
                        break
                
                if audio_file and current_segment not in played_segments:
                    current_text = text_segments[current_segment]
                    print(f"[読み上げ] セグメント {current_segment+1}/{len(text_segments)}: {current_text[:30]}...")
                    
                    # OBSに現在読み上げ中のテキストを表示（音声内容のみ）
                    self.update_obs_text(obs_source_name, current_text)
                    
                    try:
                        # 音声再生開始 - 口パクアニメーション開始
                        if self.mouth_animation_enabled:
                            animation_active[0] = True
                        
                        pygame.mixer.music.load(audio_file)
                        pygame.mixer.music.play()
                        
                        # 再生完了まで待機
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.05)
                        
                        # 音声再生終了 - 口パクアニメーション一時停止
                        if self.mouth_animation_enabled:
                            animation_active[0] = False
                        
                        pygame.mixer.music.unload()
                        played_segments.add(current_segment)
                        audio_files_to_cleanup.append(audio_file)
                        
                        print(f"[読み上げ] セグメント {current_segment+1} 再生完了")
                        
                        # 次のセグメントの先読み生成を開始
                        start_generation_if_needed(current_segment + 1)
                        
                    except Exception as play_error:
                        print(f"[エラー] セグメント {current_segment+1} の再生エラー: {play_error}")
                        # エラーが発生してもスキップして続行
                    
                    time.sleep(0.1)  # セグメント間の短い間隔
                else:
                    print(f"[警告] セグメント {current_segment+1} の音声ファイルが見つかりません")
                
                current_segment += 1
            
            # 5. 全スレッドの完了を待つ
            for thread in threads:
                thread.join()
            
            # 6. 口パクアニメーション停止
            if self.mouth_animation_enabled and animation_thread:
                animation_active.append(False)  # スレッド終了フラグを追加
                animation_thread.join()
            
            # 7. 一時ファイルを削除
            for audio_file in audio_files_to_cleanup:
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                except Exception as cleanup_error:
                    print(f"一時ファイル削除エラー: {cleanup_error}")
            
            # 8. OBSの表示をクリア
            self.update_obs_text(obs_source_name, "")
            
            print("[読み上げ] 全セグメント再生完了")
            return True
            
        except Exception as e:
            print(f"テキスト読み上げエラー: {e}")
            # エラー時は口を閉じた状態にする
            self.set_mouth_state(False)
            # OBSの表示をクリア
            self.update_obs_text(obs_source_name, "")
            return False

    def create_text_display_gui(self):
        """テキスト表示用のGUIウィンドウを作成"""
        def gui_thread():
            self.gui_window = tk.Tk()
            self.gui_window.title("AIなまけ猫 - 回答表示")
            self.gui_window.geometry("600x400")
            self.gui_window.configure(bg='#2b2b2b')
            
            # タイトルラベル
            title_label = tk.Label(
                self.gui_window, 
                text="🐱 AIなまけ猫の回答",
                font=("Arial", 16, "bold"),
                bg='#2b2b2b',
                fg='#ffffff'
            )
            title_label.pack(pady=10)
            
            # テキスト表示エリア
            self.text_display = scrolledtext.ScrolledText(
                self.gui_window,
                wrap=tk.WORD,
                width=70,
                height=20,
                font=("Arial", 12),
                bg='#1e1e1e',
                fg='#ffffff',
                insertbackground='#ffffff'
            )
            self.text_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
            
            # 初期メッセージ
            self.add_text_to_display("システム", "AIなまけ猫のテキスト表示が開始されました。", "#00ff00")
            
            # ウィンドウを閉じる時の処理
            def on_closing():
                self.gui_enabled = False
                self.gui_window.destroy()
            
            self.gui_window.protocol("WM_DELETE_WINDOW", on_closing)
            self.gui_window.mainloop()
        
        # GUIを別スレッドで実行
        self.gui_thread = threading.Thread(target=gui_thread)
        self.gui_thread.daemon = True
        self.gui_thread.start()
        self.gui_enabled = True
        
        # GUIが起動するまで少し待機
        time.sleep(1)

    def add_text_to_display(self, speaker, text, color="#ffffff"):
        """テキスト表示エリアにテキストを追加"""
        if not self.gui_enabled or not self.text_display:
            return
        
        try:
            # 現在時刻を取得
            current_time = time.strftime("%H:%M:%S")
            
            # テキストを追加
            self.text_display.insert(tk.END, f"[{current_time}] {speaker}: {text}\n")
            
            # 最新のテキストまでスクロール
            self.text_display.see(tk.END)
            
            # テキストの色を設定
            start_line = self.text_display.index(tk.END + "-2l linestart")
            end_line = self.text_display.index(tk.END + "-1l lineend")
            self.text_display.tag_add(f"color_{current_time}", start_line, end_line)
            self.text_display.tag_config(f"color_{current_time}", foreground=color)
            
        except Exception as e:
            print(f"テキスト表示エラー: {e}")

    def speak_response(self, user_input):
        """ユーザー入力に応答して音声で返答"""
        response_text = self.generate_response(user_input)
        print(f"なまけ猫: {response_text}")
        
        # OBSに応答を表示
        self.update_obs_text("webpage_comment", response_text)
        
        # GUIにテキストを表示
        self.add_text_to_display("なまけ猫", response_text, "#ffff00")
        
        success = self.text_to_speech(response_text)
        if not success:
            print("音声生成に失敗しました")
        
        return response_text

    def speak_random_comment(self):
        """ランダムコメントを音声で発話"""
        comment = self.generate_random_comment()
        print(f"つぶやき: {comment}")
        
        # OBSにつぶやき内容を表示
        self.update_obs_text("webpage_comment", comment)
        
        success = self.text_to_speech(comment)
        if not success:
            print("音声生成に失敗しました")
        
        return comment

    def pregenerate_common_phrases(self):
        """よく使う挨拶や定型文を事前生成してキャッシュ"""
        if not self.pregenerate_enabled:
            return
        
        common_phrases = [
            "おはよう",
            "こんにちは", 
            "こんばんは",
            "お疲れさま",
            "ありがとう",
            "働きたくないにゃ",
            "だらだらしたいにゃ",
            "眠いにゃ",
            "まあまあかにゃ",
            "そうだにゃ",
            "うーん、どうかにゃ",
            "今日もゆるゆると過ごそうにゃ",
            "人間って不思議だにゃ",
            "昼寝が一番だにゃ"
        ]
        
        print("[事前生成] よく使う挨拶を生成中...")
        
        for phrase in common_phrases:
            try:
                # audio_queryを事前生成してキャッシュ
                self.get_cached_audio_query(phrase)
                time.sleep(0.1)  # VOICEVOX負荷軽減のため少し待機
            except Exception as e:
                print(f"[事前生成] エラー ({phrase}): {e}")
        
        print(f"[事前生成] {len(common_phrases)}個の定型文を事前生成完了")
        self.pregenerate_completed = True

    def process_chat_message(self, username, message):
        """チャットメッセージを処理して応答するかどうか判断"""
        if not self.auto_response_enabled or self.is_speaking:
            return False
        
        # クォータ制限チェック（30秒間隔でのみ応答）
        current_time = time.time()
        if (current_time - self.last_response_time) < self.response_cooldown:
            remaining_time = self.response_cooldown - (current_time - self.last_response_time)
            print(f"[クォータ制限] 応答まで残り {remaining_time:.0f}秒")
            return False
        
        # 応答すべきメッセージかどうかを判断
        response_triggers = [
            "なまけ猫", "AIなまけ猫", "おはよう", "こんにちは", "こんばんは",
            "質問", "どう思う", "教えて", "にゃ", "猫", "元気", "調子", "どう",
            "大丈夫", "疲れ", "眠い", "だるい", "やる気", "？", "!"
        ]
        
        # より広範囲に応答：疑問符や感嘆符があるメッセージ、または5文字以上のメッセージに応答
        should_respond = (
            any(trigger in message for trigger in response_triggers) or
            len(message) >= 5  # 5文字以上のメッセージには基本的に応答
        )
        
        if should_respond:
            print(f"[チャット] {username}: {message}")
            self.is_speaking = True
            self.last_response_time = current_time  # 応答時間を記録
            
            # チャット応答用のプロンプトを調整
            chat_prompt = f"{self.character_prompt}\n\n配信チャットでの応答です。\n視聴者「{username}」からのメッセージ: {message}\nAIなまけ猫:"
            
            try:
                response = self.model.generate_content(chat_prompt)
                response_text = response.text.strip()
                print(f"なまけ猫 → {username}: {response_text}")
                
                # OBSにチャット応答を表示
                self.update_obs_text("webpage_comment", response_text)
                
                # GUIにチャットメッセージと回答を表示
                self.add_text_to_display(username, message, "#00ffff")  # 視聴者のメッセージは水色
                self.add_text_to_display("なまけ猫", response_text, "#ffff00")  # なまけ猫の回答は黄色
                
                success = self.text_to_speech(response_text)
                if not success:
                    print("音声生成に失敗しました")
                
                self.is_speaking = False
                return True
                
            except Exception as e:
                print(f"チャット応答エラー: {e}")
                
                # エラーをユーザーフレンドリーなメッセージに変換
                error_response = self.get_friendly_error_message(e, "chat")
                
                # クォータエラーの場合は応答間隔を延長
                if "quota" in str(e).lower() or "limit" in str(e).lower() or "429" in str(e):
                    self.response_cooldown = 60  # 1分間隔に延長
                    print(f"[クォータ制限] 応答間隔を{self.response_cooldown}秒に延長しました")
                
                # エラーメッセージをOBSに表示して音声で読み上げ
                print(f"なまけ猫 → {username}: {error_response}")
                self.update_obs_text("webpage_comment", error_response)
                self.add_text_to_display("なまけ猫", error_response, "#ffff00")
                
                success = self.text_to_speech(error_response)
                if not success:
                    print("音声生成に失敗しました")
                
                self.is_speaking = False
                return True  # エラーメッセージも応答として扱う
        
        return False

    def check_random_comment_time(self):
        """定期つぶやきの時間をチェック"""
        current_time = time.time()
        if (current_time - self.last_random_comment_time) >= self.random_comment_interval:
            if not self.is_speaking:
                print("[定期つぶやき] 時間になりました")
                self.is_speaking = True
                self.speak_random_comment()
                self.last_random_comment_time = current_time
                self.is_speaking = False
                return True
        return False

    def setup_youtube_auth(self):
        """YouTube API認証を設定"""
        SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
        
        creds = None
        # token.jsonファイルが存在する場合、認証情報を読み込み
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        
        # 有効な認証情報がない場合、ユーザーにログインを求める
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    print("❌ credentials.json ファイルが見つかりません")
                    print("Google Cloud ConsoleでYouTube Data API v3を有効にして、")
                    print("OAuth 2.0認証情報をダウンロードし、credentials.jsonとして保存してください")
                    return False
                
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            
            # 認証情報を保存
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        self.youtube_service = build('youtube', 'v3', credentials=creds)
        return True

    def get_live_chat_id(self):
        """現在のライブ配信のチャットIDを取得"""
        try:
            # 自分のライブ配信を取得（パラメータを分けて取得）
            request = self.youtube_service.liveBroadcasts().list(
                part='snippet,contentDetails',
                mine=True
            )
            response = request.execute()
            
            if not response['items']:
                print("❌ ライブ配信が見つかりません")
                return None
            
            # アクティブな配信を探す
            active_broadcast = None
            for broadcast in response['items']:
                status = broadcast['snippet'].get('liveChatId')
                if status:  # liveChatIdが存在する場合はアクティブな配信
                    active_broadcast = broadcast
                    break
            
            if not active_broadcast:
                print("❌ アクティブなライブ配信が見つかりません")
                print("利用可能な配信:")
                for broadcast in response['items']:
                    title = broadcast['snippet']['title']
                    print(f"  - {title}")
                return None
            
            # チャットIDを取得
            live_chat_id = active_broadcast['snippet'].get('liveChatId')
            if live_chat_id:
                print(f"✓ ライブチャットID取得成功: {live_chat_id}")
                return live_chat_id
            else:
                print("❌ ライブチャットIDが見つかりません")
                print("配信でチャットが有効になっているか確認してください")
                return None
            
        except Exception as e:
            print(f"❌ ライブチャットID取得エラー: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_live_chat_messages(self):
        """ライブチャットメッセージを取得"""
        if not self.live_chat_id:
            return []
        
        try:
            request = self.youtube_service.liveChatMessages().list(
                liveChatId=self.live_chat_id,
                part='snippet,authorDetails'
            )
            response = request.execute()
            
            new_messages = []
            for item in response['items']:
                message_id = item['id']
                
                # 既に処理済みのメッセージはスキップ
                if message_id in self.processed_messages:
                    continue
                
                self.processed_messages.add(message_id)
                
                author_name = item['authorDetails']['displayName']
                message_text = item['snippet']['displayMessage']
                
                new_messages.append({
                    'id': message_id,
                    'author': author_name,
                    'message': message_text,
                    'timestamp': item['snippet']['publishedAt']
                })
            
            return new_messages
            
        except Exception as e:
            print(f"❌ チャットメッセージ取得エラー: {e}")
            return []

    def youtube_chat_monitor_thread(self):
        """YouTube Live Chatを監視するスレッド"""
        print("[YouTube] チャット監視開始")
        
        while self.streaming_mode and self.youtube_enabled:
            try:
                print("[YouTube] チャットメッセージを取得中...")
                messages = self.get_live_chat_messages()
                
                if messages:
                    print(f"[YouTube] {len(messages)}件の新しいメッセージを取得")
                    for msg in messages:
                        print(f"[YouTube] {msg['author']}: {msg['message']}")
                        
                        # チャットメッセージを処理
                        self.process_chat_message(msg['author'], msg['message'])
                else:
                    print("[YouTube] 新しいメッセージなし")
                
                # 3秒間隔でチェック（より頻繁に）
                print("[YouTube] 3秒待機...")
                time.sleep(3)
                
            except Exception as e:
                print(f"❌ YouTube チャット監視エラー: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)  # エラー時は少し長めに待機
        
        print("[YouTube] チャット監視終了")

    def start_youtube_integration(self):
        """YouTube Live連携を開始"""
        print("\n=== YouTube Live連携セットアップ ===")
        
        # YouTube API認証
        if not self.setup_youtube_auth():
            return False
        
        print("✓ YouTube API認証成功")
        
        # ライブチャットID取得
        self.live_chat_id = self.get_live_chat_id()
        if not self.live_chat_id:
            return False
        
        # 既存のメッセージをすべて処理済みとしてマーク（アプリ起動後のメッセージのみ処理）
        print("[YouTube] 既存メッセージをスキップ中...")
        try:
            existing_messages = self.get_live_chat_messages()
            print(f"[YouTube] {len(existing_messages)}件の既存メッセージをスキップしました")
        except Exception as e:
            print(f"[YouTube] 既存メッセージスキップエラー: {e}")
        
        # YouTube連携を有効化
        self.youtube_enabled = True
        
        # チャット監視スレッドを開始
        chat_thread = threading.Thread(target=self.youtube_chat_monitor_thread)
        chat_thread.daemon = True
        chat_thread.start()
        
        print("✓ YouTube Live チャット監視開始（新しいメッセージのみ処理）")
        return True

    def start_streaming_mode(self):
        """配信モードを開始"""
        self.streaming_mode = True
        print("=== 配信モード開始 ===")
        
        # テキスト表示GUIの選択
        gui_choice = input("テキスト表示ウィンドウを開きますか？ (y/n): ").strip().lower()
        if gui_choice == 'y':
            self.create_text_display_gui()
            print("✓ テキスト表示ウィンドウが開きました")
        
        # YouTube Live連携の選択
        youtube_choice = input("YouTube Live連携を使用しますか？ (y/n): ").strip().lower()
        if youtube_choice == 'y':
            if self.start_youtube_integration():
                print("✓ YouTube Live連携が有効になりました")
            else:
                print("❌ YouTube Live連携に失敗しました。手動モードで続行します")
        
        print("\nコマンド:")
        print("  'chat:ユーザー名:メッセージ' - チャットメッセージをシミュレート")
        print("  'comment' - 手動でランダムつぶやき")
        print("  'speak:テキスト' - 指定したテキストを手動で発話")
        print("  'talk' - 自由に話させる（対話形式）")
        print("  'toggle' - 自動応答のON/OFF切り替え")
        print("  'quit' - 配信モード終了")
        print("  'help' - ヘルプ表示")
        print()
        
        try:
            while self.streaming_mode:
                # 定期つぶやきチェック
                self.check_random_comment_time()
                
                # ユーザー入力待機（タイムアウト付き）
                try:
                    user_input = input("コマンド入力 (または Enter で待機): ").strip()
                    
                    if user_input.lower() == 'quit':
                        break
                    elif user_input.lower() == 'help':
                        print("コマンド一覧:")
                        print("  chat:ユーザー名:メッセージ - チャットシミュレート")
                        print("  comment - 手動つぶやき")
                        print("  toggle - 自動応答切り替え")
                        print("  quit - 終了")
                    elif user_input.lower() == 'comment':
                        if not self.is_speaking:
                            self.is_speaking = True
                            self.speak_random_comment()
                            self.is_speaking = False
                        else:
                            print("現在発話中です")
                    elif user_input.lower() == 'toggle':
                        self.auto_response_enabled = not self.auto_response_enabled
                        status = "ON" if self.auto_response_enabled else "OFF"
                        print(f"自動応答: {status}")
                    elif user_input.startswith('chat:'):
                        # chat:username:message 形式
                        parts = user_input.split(':', 2)
                        if len(parts) == 3:
                            _, username, message = parts
                            self.process_chat_message(username, message)
                        else:
                            print("形式: chat:ユーザー名:メッセージ")
                    elif user_input.startswith('speak:'):
                        # speak:テキスト 形式
                        text_to_speak = user_input[6:]  # 'speak:' を除去
                        if text_to_speak.strip():
                            if not self.is_speaking:
                                self.is_speaking = True
                                print(f"手動発話: {text_to_speak}")
                                
                                # OBSに手動発話内容を表示
                                self.update_obs_text("webpage_comment", text_to_speak)
                                
                                success = self.text_to_speech(text_to_speak)
                                if not success:
                                    print("音声生成に失敗しました")
                                self.is_speaking = False
                            else:
                                print("現在発話中です")
                        else:
                            print("形式: speak:発話したいテキスト")
                    elif user_input.lower() == 'talk':
                        # 自由対話モード
                        if not self.is_speaking:
                            print("=== 自由対話モード ===")
                            print("AIなまけ猫と自由に会話できます。'back' で配信モードに戻る")
                            
                            while True:
                                try:
                                    talk_input = input("あなた: ").strip()
                                    
                                    if talk_input.lower() == 'back':
                                        print("配信モードに戻ります")
                                        break
                                    elif talk_input == '':
                                        continue
                                    
                                    self.is_speaking = True
                                    response_text = self.generate_response(talk_input)
                                    print(f"なまけ猫: {response_text}")
                                    
                                    # OBSに自由対話の応答を表示
                                    self.update_obs_text("webpage_comment", response_text)
                                    
                                    success = self.text_to_speech(response_text)
                                    if not success:
                                        print("音声生成に失敗しました")
                                    
                                    self.is_speaking = False
                                    
                                except KeyboardInterrupt:
                                    print("\n配信モードに戻ります")
                                    break
                                except EOFError:
                                    print("\n配信モードに戻ります")
                                    break
                            
                            self.is_speaking = False
                        else:
                            print("現在発話中です")
                    elif user_input == '':
                        # 何もしない（定期チェックのみ）
                        time.sleep(1)
                    else:
                        print("不明なコマンドです。'help' でヘルプを表示")
                        
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
                    
        except Exception as e:
            print(f"配信モードエラー: {e}")
        finally:
            self.streaming_mode = False
            print("=== 配信モード終了 ===")

    def interactive_mode(self):
        """対話モード（配信以外での使用）"""
        print("=== 対話モード ===")
        print("AIなまけ猫と会話できます。'quit' で終了")
        print()
        
        try:
            while True:
                user_input = input("あなた: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input == '':
                    continue
                
                self.speak_response(user_input)
                print()
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("対話モード終了")

    def text_reading_mode(self):
        """テキストファイル読み上げモード"""
        print("=== テキストファイル読み上げモード ===")
        print("テキストファイルを指定すると、内容を読み上げます")
        print("'quit' で終了")
        print()
        
        try:
            while True:
                file_path = input("テキストファイルのパス: ").strip()
                
                if file_path.lower() == 'quit':
                    break
                elif file_path == '':
                    continue
                
                print(f"[テキスト読み上げ] {file_path} を読み込み中...")
                
                try:
                    # テキストファイルを読み込み
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    if not content:
                        error_msg = "ファイルが空だにゃ...何も書いてないにゃ〜"
                        print(f"エラー: {error_msg}")
                        self.update_obs_text("webpage_comment", error_msg)
                        success = self.text_to_speech(error_msg)
                        if not success:
                            print("音声生成に失敗しました")
                        continue
                    
                    print(f"[読み込み完了] 文字数: {len(content)}文字")
                    print(f"[読み込み完了] 内容: {content[:100]}...")
                    
                    # 長すぎる場合は確認
                    if len(content) > 1000:
                        confirm = input(f"テキストが長いです（{len(content)}文字）。読み上げを続行しますか？ (y/n): ").strip().lower()
                        if confirm != 'y':
                            print("読み上げをキャンセルしました")
                            continue
                    
                    # OBSに読み上げ中のテキストを表示（セグメント単位で更新）
                    print("[読み上げ開始]")
                    success = self.text_to_speech_with_obs_display_segments(content, "webpage_comment")
                    if not success:
                        print("音声生成に失敗しました")
                    
                    print()
                    
                except FileNotFoundError:
                    error_msg = f"ファイルが見つからないにゃ...{file_path} は存在しないにゃ〜"
                    print(f"エラー: {error_msg}")
                    self.update_obs_text("webpage_comment", error_msg)
                    success = self.text_to_speech(error_msg)
                    if not success:
                        print("音声生成に失敗しました")
                except UnicodeDecodeError:
                    error_msg = "ファイルの文字コードが読めないにゃ...UTF-8で保存してほしいにゃ〜"
                    print(f"エラー: {error_msg}")
                    self.update_obs_text("webpage_comment", error_msg)
                    success = self.text_to_speech(error_msg)
                    if not success:
                        print("音声生成に失敗しました")
                except Exception as e:
                    error_msg = f"ファイル読み込みでエラーが起きたにゃ...{str(e)}"
                    print(f"エラー: {error_msg}")
                    self.update_obs_text("webpage_comment", error_msg)
                    success = self.text_to_speech(error_msg)
                    if not success:
                        print("音声生成に失敗しました")
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("テキストファイル読み上げモード終了")

    def novel_game_mode(self):
        """ノベルゲーム実況モード"""
        print("=== ノベルゲーム実況モード ===")
        print("ブラウザのノベルゲームを実況します")
        print("スペースキーでゲームを進めながら、画面を解析してコメントします")
        print()
        print("コマンド:")
        print("  'start' - 実況開始")
        print("  'pause' - 実況一時停止")
        print("  'resume' - 実況再開")
        print("  'screenshot' - 手動スクリーンショット")
        print("  'comment' - 手動コメント生成")
        print("  'settings' - 設定変更")
        print("  'quit' - 終了")
        print()
        
        # 設定
        auto_advance_interval = 2.0  # 自動進行間隔（秒）
        screenshot_source = "ブラウザソース"  # OBSソース名
        min_space_presses = 2  # 最小スペースキー押下回数
        max_space_presses = 5  # 最大スペースキー押下回数
        is_running = False
        is_paused = False
        
        # 実況状態管理
        space_press_count = 0  # 現在のスペースキー押下回数
        target_space_count = 0  # 目標スペースキー押下回数
        comment_types = [
            "screen_analysis",    # 画面解析コメント
            "emotion_reaction",   # 感情的リアクション
            "story_prediction",   # ストーリー予想
            "character_analysis", # キャラクター分析
            "trivia_knowledge",   # 豆知識・雑学
            "text_reading",       # テキスト読み上げ
            "personal_episode",   # 関連エピソード
            "lazy_comment"        # だらけコメント
        ]
        last_comment_type = None
        
        # OBS接続確認
        if not self.obs_ws:
            print("❌ OBS WebSocketに接続されていません")
            print("OBSを起動してWebSocketサーバーを有効化してください")
            return
        
        try:
            while True:
                if not is_running:
                    command = input("コマンド: ").strip().lower()
                else:
                    # 実況中は自動進行
                    if not is_paused:
                        try:
                            # 目標スペースキー回数を設定（初回または達成時）
                            if space_press_count == 0:
                                import random
                                target_space_count = random.randint(min_space_presses, max_space_presses)
                                print(f"[実況] 次のコメントまで{target_space_count}回スペースキーを押します")
                            
                            print(f"[実況] スペースキー押下 ({space_press_count + 1}/{target_space_count})")
                            
                            # スペースキーを送信してゲームを進行
                            self.send_space_key()
                            space_press_count += 1
                            
                            # 目標回数に達したらコメント生成
                            if space_press_count >= target_space_count:
                                time.sleep(1.5)  # ゲームの画面更新を待つ
                                
                                # バラエティーに富んだコメント生成（ブロッキング）
                                print("[実況] コメント生成・音声再生中...")
                                self.generate_varied_novel_comment(screenshot_source, comment_types, last_comment_type)
                                print("[実況] コメント完了、自動進行を継続します")
                                
                                # カウンターをリセット
                                space_press_count = 0
                                target_space_count = 0
                            
                            # 次の進行まで待機
                            time.sleep(auto_advance_interval)
                            
                        except Exception as e:
                            print(f"[実況エラー] {e}")
                            time.sleep(1)
                        
                        # ユーザー入力をチェック（ノンブロッキング）
                        command = self.get_user_input_non_blocking()
                    else:
                        command = input("コマンド (一時停止中): ").strip().lower()
                
                if command == 'quit':
                    break
                elif command == 'start':
                    if not is_running:
                        is_running = True
                        is_paused = False
                        # カウンターを初期化
                        space_press_count = 0
                        target_space_count = 0
                        print("✓ ノベルゲーム実況を開始しました")
                        print("スペースキーでゲームを自動進行し、画面を解析します")
                        print(f"設定: {min_space_presses}〜{max_space_presses}回押下後にコメント生成")
                    else:
                        print("既に実況中です")
                elif command == 'pause':
                    if is_running and not is_paused:
                        is_paused = True
                        print("⏸ 実況を一時停止しました")
                    else:
                        print("実況中ではありません")
                elif command == 'resume':
                    if is_running and is_paused:
                        is_paused = False
                        print("▶ 実況を再開しました")
                    else:
                        print("一時停止中ではありません")
                elif command == 'screenshot':
                    print("[手動] 画面をキャプチャして解析中...")
                    self.analyze_novel_game_screen(screenshot_source)
                elif command == 'comment':
                    print("[手動] 現在の画面についてコメント生成中...")
                    self.analyze_novel_game_screen(screenshot_source, force_comment=True)
                elif command == 'settings':
                    print(f"現在の設定:")
                    print(f"  自動進行間隔: {auto_advance_interval}秒")
                    print(f"  スクリーンショットソース: {screenshot_source}")
                    print(f"  スペースキー押下回数: {min_space_presses}〜{max_space_presses}回")
                    
                    new_interval = input(f"新しい自動進行間隔（秒）[現在: {auto_advance_interval}]: ").strip()
                    if new_interval and new_interval.replace('.', '').isdigit():
                        auto_advance_interval = float(new_interval)
                        print(f"✓ 自動進行間隔を{auto_advance_interval}秒に変更しました")
                    
                    new_source = input(f"新しいスクリーンショットソース名 [現在: {screenshot_source}]: ").strip()
                    if new_source:
                        screenshot_source = new_source
                        print(f"✓ スクリーンショットソースを'{screenshot_source}'に変更しました")
                    
                    new_min = input(f"最小スペースキー押下回数 [現在: {min_space_presses}]: ").strip()
                    if new_min and new_min.isdigit():
                        min_space_presses = int(new_min)
                        print(f"✓ 最小スペースキー押下回数を{min_space_presses}回に変更しました")
                    
                    new_max = input(f"最大スペースキー押下回数 [現在: {max_space_presses}]: ").strip()
                    if new_max and new_max.isdigit():
                        max_space_presses = int(new_max)
                        print(f"✓ 最大スペースキー押下回数を{max_space_presses}回に変更しました")
                elif command == 'stop':
                    if is_running:
                        is_running = False
                        is_paused = False
                        print("⏹ 実況を停止しました")
                    else:
                        print("実況中ではありません")
                elif command == 'help':
                    print("利用可能なコマンド:")
                    print("  start - 実況開始")
                    print("  pause - 一時停止")
                    print("  resume - 再開")
                    print("  stop - 停止")
                    print("  screenshot - 手動スクリーンショット")
                    print("  comment - 手動コメント")
                    print("  settings - 設定変更")
                    print("  quit - 終了")
                elif command == '':
                    continue
                else:
                    print("無効なコマンドです。'help' でコマンド一覧を表示")
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("ノベルゲーム実況モード終了")

    def send_space_key(self):
        """スペースキーを送信してゲームを進行"""
        try:
            import keyboard
            import time
            
            # より確実なキー送信
            keyboard.press('space')
            time.sleep(0.05)  # 50ms押下
            keyboard.release('space')
            time.sleep(0.1)   # 100ms待機
            
            print("[キー送信] スペースキーを送信しました")
            return True
        except ImportError:
            print("[キー送信エラー] keyboardライブラリがインストールされていません")
            print("pip install keyboard でインストールしてください")
            return False
        except Exception as e:
            print(f"[キー送信エラー] {e}")
            print("管理者権限で実行するか、ブラウザをアクティブにしてください")
            return False

    def get_user_input_non_blocking(self):
        """ノンブロッキングでユーザー入力を取得"""
        try:
            import select
            import sys
            
            # Windowsの場合はmsvcrtを使用
            if sys.platform == 'win32':
                import msvcrt
                if msvcrt.kbhit():
                    return input().strip().lower()
            else:
                # Unix系の場合はselectを使用
                if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                    return input().strip().lower()
            
            return ''
        except:
            return ''

    def analyze_novel_game_screen(self, source_name, force_comment=False):
        """ノベルゲーム画面を解析してコメント"""
        try:
            print(f"[画面解析] ソース '{source_name}' をキャプチャ中...")
            
            # OBSスクリーンショットを取得
            image, error = self.capture_obs_source_screenshot(source_name)
            if error:
                error_msg = f"画面が取得できないにゃ...{error}"
                print(f"エラー: {error_msg}")
                self.update_obs_text("webpage_comment", error_msg)
                success = self.text_to_speech(error_msg)
                return
            
            # 画像を一時保存（デバッグ用）
            try:
                debug_filename = f"novel_game_screenshot_{int(time.time())}.png"
                image.save(debug_filename)
                print(f"[デバッグ] スクリーンショット保存: {debug_filename}")
            except Exception as e:
                print(f"[デバッグ] 画像保存エラー: {e}")
            
            # AI解析でコメント生成（ノベルゲーム専用プロンプト）
            comment = self.analyze_novel_game_with_ai(image, force_comment)
            
            if comment and comment.strip():
                print(f"なまけ猫: {comment}")
                
                # OBSにコメントを表示
                self.update_obs_text("webpage_comment", comment)
                
                # 音声で読み上げ
                success = self.text_to_speech(comment)
                if not success:
                    print("音声生成に失敗しました")
            else:
                print("[画面解析] コメントなし（変化が少ないため）")
                
        except Exception as e:
            error_msg = f"画面解析でエラーが起きたにゃ...{str(e)}"
            print(f"エラー: {error_msg}")
            self.update_obs_text("webpage_comment", error_msg)
            success = self.text_to_speech(error_msg)

    def generate_varied_novel_comment(self, source_name, comment_types, last_comment_type):
        """バラエティーに富んだノベルゲームコメントを生成"""
        try:
            import random
            
            # 前回と同じタイプを避ける
            available_types = [t for t in comment_types if t != last_comment_type]
            if not available_types:
                available_types = comment_types
            
            # ランダムにコメントタイプを選択
            comment_type = random.choice(available_types)
            last_comment_type = comment_type
            
            print(f"[コメント生成] タイプ: {comment_type}")
            
            # OBSスクリーンショットを取得
            image, error = self.capture_obs_source_screenshot(source_name)
            if error:
                error_msg = f"画面が取得できないにゃ...{error}"
                print(f"エラー: {error_msg}")
                self.update_obs_text("webpage_comment", error_msg)
                success = self.text_to_speech(error_msg)
                return
            
            # 画像を一時保存（デバッグ用）
            try:
                debug_filename = f"novel_varied_{comment_type}_{int(time.time())}.png"
                image.save(debug_filename)
                print(f"[デバッグ] スクリーンショット保存: {debug_filename}")
            except Exception as e:
                print(f"[デバッグ] 画像保存エラー: {e}")
            
            # コメントタイプに応じてAI解析
            comment = self.generate_comment_by_type(image, comment_type)
            
            if comment and comment.strip():
                # ノベルゲームモード用のネガティブワードフィルタリング
                filtered_comment = self.filter_negative_words_for_novel(comment)
                
                if filtered_comment and filtered_comment.strip():
                    print(f"なまけ猫 [{comment_type}]: {filtered_comment}")
                    
                    # OBSにコメントを表示
                    self.update_obs_text("webpage_comment", filtered_comment)
                    
                    # 音声で読み上げ（完了まで待機）
                    print("[音声再生] 開始...")
                    success = self.text_to_speech(filtered_comment)
                    if success:
                        print("[音声再生] 完了")
                    else:
                        print("[音声再生] 失敗")
                    
                    # 音声再生後の短い待機
                    time.sleep(0.5)
                else:
                    print(f"[{comment_type}] ネガティブワードによりコメントをフィルタリングしました")
                    # フィルタリングされた場合も短い待機
                    time.sleep(1.0)
            else:
                print(f"[{comment_type}] コメント生成なし")
                # コメントがない場合も短い待機
                time.sleep(1.0)
                
        except Exception as e:
            error_msg = f"コメント生成でエラーが起きたにゃ...{str(e)}"
            print(f"エラー: {error_msg}")
            self.update_obs_text("webpage_comment", error_msg)
            print("[音声再生] エラーメッセージ開始...")
            success = self.text_to_speech(error_msg)
            if success:
                print("[音声再生] エラーメッセージ完了")
            else:
                print("[音声再生] エラーメッセージ失敗")
            time.sleep(0.5)

    def generate_comment_by_type(self, image, comment_type):
        """コメントタイプに応じてコメントを生成"""
        try:
            # コメントタイプ別のプロンプト
            prompts = {
                "screen_analysis": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、画面の状況や変化について簡潔にコメントしてください。
新しいキャラクター、場面転換、重要な情報などに注目してください。

AIなまけ猫:""",

                "emotion_reaction": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、感情的なリアクションをしてください。
驚き、喜び、悲しみ、怒り、困惑など、画面の内容に応じた感情を表現してください。
「うわあ！」「えー！」「やったにゃ！」「すごいにゃ！」などの感嘆詞も使ってください。

注意：「眠い」「寝たい」「面倒」「だるい」「働きたくない」などのネガティブな表現は使わないでください。

AIなまけ猫:""",

                "story_prediction": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、この後の展開を予想してコメントしてください。
「きっと〜になりそうだにゃ」「この流れだと〜かも」など、だらけた感じで予想してください。

AIなまけ猫:""",

                "character_analysis": f"""
{self.character_prompt}

現在のノベルゲーム画面に登場するキャラクターについて分析・コメントしてください。
キャラクターの性格、行動、関係性などについて、猫らしい視点で観察してください。

AIなまけ猫:""",

                "trivia_knowledge": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、関連する豆知識や雑学をコメントしてください。
ゲームのジャンル、設定、時代背景などに関する知識を、だらけた感じで披露してください。
「そういえば〜だにゃ」「〜って知ってる？」などの口調で。

AIなまけ猫:""",

                "text_reading": f"""
{self.character_prompt}

現在のノベルゲーム画面に表示されているテキストやセリフを読み上げてください。
重要な部分や印象的な部分を選んで、だらけた感じで読み上げてください。
「〜って言ってるにゃ」「〜だって」などの口調で。

AIなまけ猫:""",

                "personal_episode": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、関連する個人的なエピソードや体験談をコメントしてください。
「昔〜したことがあるにゃ」「これ、〜に似てるにゃ」など、猫らしい体験談を語ってください。
実際の体験でなくても、猫らしい想像で構いません。

注意：「眠い」「寝たい」「面倒」「だるい」「働きたくない」などのネガティブな表現は使わないでください。

AIなまけ猫:""",

                "lazy_comment": f"""
{self.character_prompt}

現在のノベルゲーム画面を見て、のんびりした感じのゆるいコメントをしてください。
「まあ、そんな感じだにゃ」「なるほどにゃ〜」「面白い展開だにゃ」など、
猫らしいゆるいコメントをしてください。

注意：「眠い」「寝たい」「面倒」「だるい」「働きたくない」などのネガティブな表現は使わないでください。

AIなまけ猫:"""
            }
            
            prompt = prompts.get(comment_type, prompts["screen_analysis"])
            
            # 画像をGeminiに送信して解析
            import google.generativeai as genai
            
            # 画像を一時保存してアップロード
            temp_filename = f"temp_varied_analysis_{int(time.time())}.png"
            image.save(temp_filename)
            
            try:
                uploaded_file = genai.upload_file(temp_filename)
                response = self.model.generate_content([prompt, uploaded_file])
                result = response.text.strip()
                
                # ファイルを削除
                genai.delete_file(uploaded_file.name)
                os.remove(temp_filename)
                
                return result
                
            except Exception as e:
                print(f"[AI解析エラー] {e}")
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                
                # エラー時のフォールバックコメント（ポジティブ版）
                fallback_comments = {
                    "emotion_reaction": "うーん、なんか面白そうな展開だにゃ〜",
                    "story_prediction": "この後どうなるか気になるにゃ...",
                    "character_analysis": "このキャラクター、なかなか個性的だにゃ",
                    "trivia_knowledge": "ノベルゲームって奥が深いにゃ〜",
                    "text_reading": "何か重要なことが書いてありそうだにゃ",
                    "personal_episode": "昔、似たような話を聞いたことがあるにゃ",
                    "lazy_comment": "まあ、そんな感じだにゃ...のんびりした展開だにゃ〜"
                }
                
                return fallback_comments.get(comment_type, "画面がよく見えないにゃ...")
                    
        except Exception as e:
            print(f"[コメント生成エラー] {e}")
            return "うーん、コメントが思い浮かばないにゃ..."

    def filter_negative_words_for_novel(self, comment):
        """ノベルゲームモード用のネガティブワードフィルタリング"""
        if not comment:
            return comment
        
        # 禁止ワードリスト
        negative_words = [
            "寝たい", "眠い", "眠く", "眠り", "寝る", "寝よう", "寝ちゃ",
            "面倒", "めんどう", "面倒くさい", "めんどくさい", "だるい", "だるく",
            "働きたくない", "やる気ない", "やる気が", "疲れた", "疲れる",
            "つまらない", "つまんない", "飽きた", "飽きる", "退屈", "しんどい",
            "嫌だ", "いやだ", "やだ", "うざい", "ウザい", "むかつく", "イライラ",
            "最悪", "最低", "クソ", "くそ", "糞", "死ね", "殺す", "バカ", "馬鹿",
            "アホ", "あほ", "間抜け", "まぬけ", "ブス", "ぶす", "キモい", "きもい"
        ]
        
        # ポジティブな置き換えワード
        positive_replacements = {
            "寝たい": "リラックスしたい",
            "眠い": "ゆったりした気分",
            "眠く": "のんびりと",
            "面倒": "ちょっと複雑",
            "めんどう": "ちょっと複雑",
            "面倒くさい": "ちょっと複雑そう",
            "めんどくさい": "ちょっと複雑そう",
            "だるい": "のんびりした感じ",
            "だるく": "ゆったりと",
            "働きたくない": "のんびりしたい",
            "やる気ない": "マイペース",
            "疲れた": "ちょっと休憩したい",
            "疲れる": "ちょっと大変",
            "つまらない": "もう少し面白くなりそう",
            "つまんない": "もう少し面白くなりそう",
            "飽きた": "次の展開が気になる",
            "飽きる": "次の展開が気になる",
            "退屈": "静かな時間",
            "しんどい": "ちょっと大変"
        }
        
        # コメントをチェックして置き換えまたは除外
        filtered_comment = comment
        contains_negative = False
        
        for word in negative_words:
            if word in filtered_comment:
                contains_negative = True
                if word in positive_replacements:
                    # ポジティブな表現に置き換え
                    filtered_comment = filtered_comment.replace(word, positive_replacements[word])
                    print(f"[フィルタ] '{word}' を '{positive_replacements[word]}' に置き換えました")
                else:
                    # 置き換えできない場合はコメント全体を除外
                    print(f"[フィルタ] 禁止ワード '{word}' が含まれているため、コメントを除外しました")
                    return ""
        
        # 特定のネガティブなフレーズもチェック
        negative_phrases = [
            "働きたくないにゃ", "だらだらしたい", "何もしたくない",
            "やる気が出ない", "面倒だにゃ", "眠いにゃ", "寝たいにゃ"
        ]
        
        for phrase in negative_phrases:
            if phrase in filtered_comment:
                print(f"[フィルタ] 禁止フレーズ '{phrase}' が含まれているため、コメントを除外しました")
                return ""
        
        # フィルタリング後のコメントが短すぎる場合は除外
        if len(filtered_comment.strip()) < 5:
            print("[フィルタ] フィルタリング後のコメントが短すぎるため除外しました")
            return ""
        
        if contains_negative:
            print(f"[フィルタ] フィルタリング完了: {filtered_comment}")
        
        return filtered_comment

    def analyze_novel_game_with_ai(self, image, force_comment=False):
        """ノベルゲーム画面をAIで解析してコメント生成"""
        try:
            # ノベルゲーム実況用のプロンプト
            novel_prompt = f"""
{self.character_prompt}

あなたはノベルゲームを実況しているAIなまけ猫です。
画面を見て、以下の観点でコメントしてください：

1. ストーリーの展開について
2. キャラクターの行動や発言について
3. 画面の変化や新しい要素について
4. ゲームの進行状況について

コメントする際の注意点：
- 画面に大きな変化がない場合は、コメントしなくても構いません
- ストーリーの重要な場面では積極的にコメント
- キャラクターの感情や関係性に注目
- だらけた感じで、でも内容には興味を示す
- 長すぎず、視聴者が楽しめるコメント

現在の画面を見て、コメントしてください。
変化が少ない場合は「なし」と返答してください。

AIなまけ猫:"""
            
            # 画像をGeminiに送信して解析
            import google.generativeai as genai
            
            # 画像を一時保存してアップロード
            temp_filename = f"temp_novel_analysis_{int(time.time())}.png"
            image.save(temp_filename)
            
            try:
                uploaded_file = genai.upload_file(temp_filename)
                response = self.model.generate_content([novel_prompt, uploaded_file])
                result = response.text.strip()
                
                # ファイルを削除
                genai.delete_file(uploaded_file.name)
                os.remove(temp_filename)
                
                # 「なし」の場合は空文字を返す
                if result.lower() in ['なし', 'なし。', 'none', '']:
                    return ""
                
                return result
                
            except Exception as e:
                print(f"[AI解析エラー] {e}")
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                
                if force_comment:
                    return "画面解析でエラーが起きたにゃ...でもきっと面白い展開だったにゃ〜"
                else:
                    return ""
                    
        except Exception as e:
            print(f"[ノベルゲーム解析エラー] {e}")
            if force_comment:
                return "うーん、画面がよく見えないにゃ...でもノベルゲームは面白そうだにゃ〜"
            else:
                return ""

    def webpage_reading_mode(self):
        """Webページ読み上げモード"""
        print("=== Webページ読み上げモード ===")
        print("URLを入力すると、ページ内容を読み上げてコメントします")
        print("'quit' で終了")
        print()
        
        try:
            import requests
            from bs4 import BeautifulSoup
            import re
        except ImportError:
            print("必要なライブラリがインストールされていません")
            print("pip install requests beautifulsoup4 を実行してください")
            return
        
        try:
            while True:
                url = input("URL: ").strip()
                
                if url.lower() == 'quit':
                    break
                elif url == '':
                    continue
                
                print(f"[Webページ読み上げ] {url} を取得中...")
                
                try:
                    # Webページを取得
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    
                    # HTMLを解析
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # タイトルを取得
                    title = soup.find('title')
                    title_text = title.get_text().strip() if title else "タイトル不明"
                    
                    # 本文を取得（pタグ、h1-h6タグから）
                    content_tags = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                    content_text = ""
                    for tag in content_tags[:10]:  # 最初の10個のタグのみ
                        text = tag.get_text().strip()
                        if text and len(text) > 10:  # 10文字以上のテキストのみ
                            content_text += text + "\n"
                    
                    # テキストを整理
                    content_text = re.sub(r'\s+', ' ', content_text).strip()
                    if len(content_text) > 500:
                        content_text = content_text[:500] + "..."
                    
                    print(f"[取得完了] タイトル: {title_text}")
                    print(f"[取得完了] 内容: {content_text[:100]}...")
                    
                    # AIにコメントを生成させる
                    comment_prompt = f"""
{self.character_prompt}

以下のWebページの内容について、だらけた感じでコメントしてください：

タイトル: {title_text}
内容: {content_text}

AIなまけ猫:"""
                    
                    print("[コメント生成中...]")
                    comment = self.generate_response(comment_prompt)
                    
                    print(f"なまけ猫: {comment}")
                    
                    # OBSにコメント全文を表示
                    self.update_obs_text("webpage_comment", comment)
                    
                    # 音声で読み上げ
                    success = self.text_to_speech(comment)
                    if not success:
                        print("音声生成に失敗しました")
                    
                    print()
                    
                except requests.RequestException as e:
                    error_msg = f"Webページの取得に失敗したにゃ...{str(e)}"
                    print(f"エラー: {error_msg}")
                    self.update_obs_text("webpage_comment", error_msg)
                    success = self.text_to_speech(error_msg)
                    if not success:
                        print("音声生成に失敗しました")
                except Exception as e:
                    error_msg = f"何かエラーが起きたにゃ...{str(e)}"
                    print(f"エラー: {error_msg}")
                    self.update_obs_text("webpage_comment", error_msg)
                    success = self.text_to_speech(error_msg)
                    if not success:
                        print("音声生成に失敗しました")
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("Webページ読み上げモード終了")

    def obs_screen_analysis_mode(self):
        """OBS画面解析モード"""
        print("=== OBS画面解析モード ===")
        print("OBSの画面をキャプチャして内容を解析・コメントします")
        print("'capture' でキャプチャ実行、'test' でテスト実行、'quit' で終了")
        print()
        
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import base64
            import io
        except ImportError:
            print("必要なライブラリがインストールされていません")
            print("pip install opencv-python pillow numpy を実行してください")
            return
        
        try:
            while True:
                command = input("コマンド (capture/test/quit): ").strip().lower()
                
                if command == 'quit':
                    break
                elif command == 'test':
                    # テスト用の簡単なコメント生成
                    print("[テスト] 画面解析テスト中...")
                    test_comment = "画面解析のテストだにゃ〜。実際の画面は見えないけど、きっと面白いものが映ってるにゃ。働きたくないにゃ〜"
                    
                    print(f"なまけ猫: {test_comment}")
                    print(f"[デバッグ] test_comment の長さ: {len(test_comment)}")
                    print(f"[デバッグ] test_comment の内容: '{test_comment}'")
                    
                    # OBSにテストコメント全文を表示（webpage_commentを共通使用）
                    print(f"[デバッグ] OBSテキスト更新開始...")
                    obs_text = f"🐱 {test_comment}"
                    print(f"[デバッグ] OBSに送信するテキスト: '{obs_text}'")
                    result = self.update_obs_text("webpage_comment", obs_text)
                    print(f"[デバッグ] OBSテキスト更新結果: {result}")
                    
                    # 音声で読み上げ
                    print(f"[デバッグ] 音声読み上げ開始...")
                    success = self.text_to_speech(test_comment)
                    if not success:
                        print("音声生成に失敗しました")
                    print(f"[デバッグ] 音声読み上げ結果: {success}")
                    
                    print()
                elif command == 'capture':
                    print("[画面解析] OBS画面をキャプチャ中...")
                    print(f"[デバッグ] use_obs_websocket: {self.use_obs_websocket}")
                    print(f"[デバッグ] obs_ws: {self.obs_ws}")
                    
                    try:
                        if not self.use_obs_websocket or not self.obs_ws:
                            print("❌ OBS WebSocket接続が必要です")
                            print("OBS WebSocketが接続されていないため、キャプチャできません")
                            continue
                        
                        # OBSからスクリーンショットを取得
                        if OBS_WEBSOCKET_NEW:
                            screenshot_response = self.obs_ws.get_source_screenshot(
                                "現在のシーン", "png", None, None, 100
                            )
                            screenshot_data = screenshot_response.image_data
                        else:
                            # 古いAPIの場合の処理（実装が複雑なため簡略化）
                            print("古いOBS WebSocket APIではスクリーンショット機能は制限されています")
                            continue
                        
                        # Base64データをデコード
                        image_data = base64.b64decode(screenshot_data.split(',')[1])
                        image = Image.open(io.BytesIO(image_data))
                        
                        # 画像を一時保存
                        screenshot_path = "obs_screenshot.png"
                        image.save(screenshot_path)
                        print(f"[画面解析] スクリーンショット保存: {screenshot_path}")
                        
                        # 画像解析用のプロンプト（Geminiの画像解析機能を使用）
                        analysis_prompt = f"""
{self.character_prompt}

この画面の内容を見て、だらけた感じでコメントしてください。
画面に何が映っているか、どんな状況かを観察して、猫らしい視点でつぶやいてください。

AIなまけ猫:"""
                        
                        print("[画面解析中...]")
                        
                        # Geminiで画像解析（画像アップロード機能が必要）
                        try:
                            # 画像をGeminiに送信して解析
                            import google.generativeai as genai
                            
                            print("[画面解析] 画像をGeminiにアップロード中...")
                            # 画像をアップロード
                            uploaded_file = genai.upload_file(screenshot_path)
                            print(f"[画面解析] アップロード完了: {uploaded_file.name}")
                            
                            print("[画面解析] Geminiで画像解析中...")
                            # 画像付きでプロンプトを送信
                            response = self.model.generate_content([analysis_prompt, uploaded_file])
                            analysis_result = response.text.strip()
                            print(f"[画面解析] 解析完了: {analysis_result[:50]}...")
                            
                            # ファイルを削除
                            print("[画面解析] アップロードファイルを削除中...")
                            genai.delete_file(uploaded_file.name)
                            print("[画面解析] 削除完了")
                            
                        except Exception as e:
                            print(f"[画面解析] エラー発生: {e}")
                            print(f"[画面解析] エラータイプ: {type(e)}")
                            import traceback
                            traceback.print_exc()
                            
                            # フォールバック：簡単なコメントを生成
                            print("[画面解析] フォールバック：テキストのみでコメント生成")
                            fallback_prompt = f"""
{self.character_prompt}

OBSの画面をキャプチャしたけど、画像解析でエラーが起きました。
画面解析ができなかったことについて、だらけた感じでコメントしてください。

AIなまけ猫:"""
                            
                            try:
                                fallback_response = self.model.generate_content(fallback_prompt)
                                analysis_result = fallback_response.text.strip()
                                print(f"[画面解析] フォールバック成功: {analysis_result[:50]}...")
                            except Exception as fallback_error:
                                print(f"[画面解析] フォールバックも失敗: {fallback_error}")
                                analysis_result = f"画面解析でエラーが起きたにゃ...でも何か面白そうな画面だったにゃ〜 技術的な問題で見えないけど、きっと面白いものが映ってるにゃ"
                        
                        print(f"なまけ猫: {analysis_result}")
                        print(f"[デバッグ] analysis_result の長さ: {len(analysis_result)}")
                        print(f"[デバッグ] analysis_result の内容: '{analysis_result}'")
                        
                        # OBSに解析結果全文を表示（webpage_commentを共通使用）
                        print(f"[デバッグ] OBSテキスト更新開始...")
                        obs_text = f"🐱 {analysis_result}"
                        print(f"[デバッグ] OBSに送信するテキスト: '{obs_text}'")
                        result = self.update_obs_text("webpage_comment", obs_text)
                        print(f"[デバッグ] OBSテキスト更新結果: {result}")
                        
                        # 音声で読み上げ
                        print(f"[デバッグ] 音声読み上げ開始...")
                        success = self.text_to_speech(analysis_result)
                        if not success:
                            print("音声生成に失敗しました")
                        print(f"[デバッグ] 音声読み上げ結果: {success}")
                        
                        print()
                        
                    except Exception as e:
                        error_msg = f"画面解析でエラーが起きたにゃ...{str(e)}"
                        print(f"エラー: {error_msg}")
                        self.update_obs_text("webpage_comment", error_msg)
                        success = self.text_to_speech(error_msg)
                        if not success:
                            print("音声生成に失敗しました")
                
                elif command == '':
                    continue
                else:
                    print("無効なコマンドです。'capture' または 'quit' を入力してください")
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("OBS画面解析モード終了")

    def fetch_webpage_content(self, url):
        """Webページの内容を取得して解析"""
        try:
            if not BS4_AVAILABLE:
                return None, "BeautifulSoup4がインストールされていません。pip install beautifulsoup4 でインストールしてください。"
            
            print(f"[Web取得] {url} にアクセス中...")
            
            # User-Agentを設定してWebページを取得
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            
            # BeautifulSoupでHTMLを解析
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 不要なタグを削除
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # タイトルを取得
            title = soup.find('title')
            title_text = title.get_text().strip() if title else "タイトルなし"
            
            # メインコンテンツを取得
            content_selectors = [
                'main', 'article', '.content', '.main-content', 
                '#content', '#main', '.post-content', '.entry-content'
            ]
            
            main_content = None
            for selector in content_selectors:
                main_content = soup.select_one(selector)
                if main_content:
                    break
            
            if not main_content:
                main_content = soup.find('body')
            
            if not main_content:
                return None, "ページの内容を取得できませんでした"
            
            # テキストを抽出
            text_content = main_content.get_text(separator='\n', strip=True)
            
            # テキストをクリーンアップ
            lines = text_content.split('\n')
            cleaned_lines = []
            for line in lines:
                line = line.strip()
                if line and len(line) > 3:  # 短すぎる行は除外
                    cleaned_lines.append(line)
            
            cleaned_text = '\n'.join(cleaned_lines)
            
            # 長すぎる場合は要約用に短縮
            if len(cleaned_text) > 2000:
                cleaned_text = cleaned_text[:2000] + "..."
            
            print(f"[Web取得] 成功: {len(cleaned_text)}文字取得")
            return {
                'title': title_text,
                'content': cleaned_text,
                'url': url
            }, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Webページの取得に失敗しました: {str(e)}"
            print(f"[Web取得エラー] {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"ページ解析エラー: {str(e)}"
            print(f"[Web解析エラー] {error_msg}")
            return None, error_msg

    def generate_webpage_comment(self, webpage_data, comment_type="summary"):
        """Webページの内容に対してコメントを生成"""
        try:
            title = webpage_data['title']
            content = webpage_data['content']
            url = webpage_data['url']
            
            # コメントタイプに応じてプロンプトを変更
            if comment_type == "summary":
                task_prompt = "このWebページの内容を要約して、だらけた感じでコメントして"
            elif comment_type == "opinion":
                task_prompt = "このWebページの内容について、猫の視点で哲学的につぶやいて"
            elif comment_type == "reaction":
                task_prompt = "このWebページを読んだ感想を、ちょっと皮肉を込めてコメントして"
            else:
                task_prompt = "このWebページについて、なまけ猫らしくコメントして"
            
            prompt = f"""{self.character_prompt}

{task_prompt}

Webページ情報:
タイトル: {title}
URL: {url}
内容: {content[:1500]}

AIなまけ猫:"""
            
            print(f"[Web解析] Gemini APIでコメント生成中...")
            response = self.model.generate_content(prompt)
            comment = response.text.strip()
            
            print(f"[Web解析] コメント生成完了")
            return comment
            
        except Exception as e:
            print(f"[Web解析エラー] コメント生成失敗: {e}")
            return f"うーん、このページは読むのが面倒だにゃ...{str(e)}"

    def read_webpage_aloud(self, url, comment_type="summary"):
        """Webページを読み上げてコメント"""
        print(f"=== Webページ読み上げ開始 ===")
        print(f"URL: {url}")
        
        # Webページを取得
        webpage_data, error = self.fetch_webpage_content(url)
        if error:
            error_comment = f"ページが読めないにゃ...{error}"
            print(f"エラー: {error_comment}")
            self.text_to_speech(error_comment)
            return error_comment
        
        # タイトルを読み上げ
        title_comment = f"「{webpage_data['title']}」について読んでみるにゃ"
        print(f"タイトル: {title_comment}")
        self.text_to_speech(title_comment)
        
        # 少し間を置く
        time.sleep(1)
        
        # 内容についてコメント生成・読み上げ
        comment = self.generate_webpage_comment(webpage_data, comment_type)
        print(f"コメント: {comment}")
        self.text_to_speech(comment)
        
        # GUIにも表示
        self.add_text_to_display("Webページ", f"{webpage_data['title']}", "#00ff88")
        self.add_text_to_display("なまけ猫", comment, "#ffff00")
        
        return comment

    def web_reading_mode(self):
        """Webページ読み上げモード"""
        print("=== Webページ読み上げモード ===")
        print("URLを入力すると、なまけ猫がページを読んでコメントします")
        print("コマンド:")
        print("  URL - そのページを読み上げ")
        print("  'summary URL' - 要約コメント")
        print("  'opinion URL' - 意見・感想")
        print("  'reaction URL' - リアクション")
        print("  'quit' - 終了")
        print()
        
        try:
            while True:
                user_input = input("URL または コマンド: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input == '':
                    continue
                
                # コマンド解析
                parts = user_input.split(' ', 1)
                if len(parts) == 2 and parts[0].lower() in ['summary', 'opinion', 'reaction']:
                    comment_type = parts[0].lower()
                    url = parts[1]
                elif user_input.startswith('http'):
                    comment_type = "summary"
                    url = user_input
                else:
                    print("有効なURLまたはコマンドを入力してください")
                    continue
                
                # URL検証
                parsed_url = urlparse(url)
                if not parsed_url.scheme or not parsed_url.netloc:
                    print("有効なURLを入力してください（http://またはhttps://で始まる）")
                    continue
                
                # Webページ読み上げ実行
                self.read_webpage_aloud(url, comment_type)
                print()
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("Webページ読み上げモード終了")

    def capture_obs_source_screenshot(self, source_name="ブラウザソース"):
        """OBSの指定ソースのスクリーンショットを取得"""
        try:
            if not self.obs_ws:
                return None, "OBS WebSocketに接続されていません"
            
            if not PIL_AVAILABLE:
                return None, "Pillowがインストールされていません。pip install pillow でインストールしてください。"
            
            print(f"[OBS画面取得] ソース '{source_name}' のスクリーンショット取得中...")
            
            if OBS_WEBSOCKET_NEW:
                # 新しいライブラリ (obsws-python) を使用
                try:
                    # ソースのスクリーンショットを取得
                    # obsws-python の正しいメソッドを使用
                    screenshot_resp = self.obs_ws.get_source_screenshot(
                        source_name,
                        "png",
                        1920,
                        1080,
                        90
                    )
                    
                    # Base64データを取得
                    image_data = screenshot_resp.image_data
                    
                    # Base64データからヘッダーを除去
                    if image_data.startswith('data:image/png;base64,'):
                        image_data = image_data.replace('data:image/png;base64,', '')
                    
                    # Base64をデコードしてPIL Imageに変換
                    image_bytes = base64.b64decode(image_data)
                    image = Image.open(BytesIO(image_bytes))
                    
                    print(f"[OBS画面取得] 成功: {image.size[0]}x{image.size[1]}px")
                    return image, None
                    
                except Exception as api_error:
                    error_msg = f"OBS WebSocket API呼び出しエラー: {api_error}"
                    print(f"[OBS画面取得エラー] {error_msg}")
                    return None, error_msg
            else:
                # 古いライブラリ (obs-websocket-py) を使用
                try:
                    request = obs_requests.TakeSourceScreenshot(
                        sourceName=source_name,
                        embedPictureFormat="png",
                        width=1920,
                        height=1080
                    )
                    response = self.obs_ws.call(request)
                    
                    # Base64データを取得
                    image_data = response.getImageData()
                    
                    # Base64データからヘッダーを除去
                    if image_data.startswith('data:image/png;base64,'):
                        image_data = image_data.replace('data:image/png;base64,', '')
                    
                    # Base64をデコードしてPIL Imageに変換
                    image_bytes = base64.b64decode(image_data)
                    image = Image.open(BytesIO(image_bytes))
                    
                    print(f"[OBS画面取得] 成功: {image.size[0]}x{image.size[1]}px")
                    return image, None
                    
                except Exception as api_error:
                    error_msg = f"OBS WebSocket API呼び出しエラー: {api_error}"
                    print(f"[OBS画面取得エラー] {error_msg}")
                    return None, error_msg
                    
        except Exception as e:
            error_msg = f"スクリーンショット取得エラー: {str(e)}"
            print(f"[OBS画面取得エラー] {error_msg}")
            return None, error_msg

    def analyze_obs_screenshot_with_ai(self, image, analysis_type="summary"):
        """OBSスクリーンショットをGemini Vision APIで解析"""
        try:
            print(f"[画像解析] Gemini Vision APIで解析中...")
            
            # 画像をBase64エンコード
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()
            
            # 解析タイプに応じてプロンプトを変更
            if analysis_type == "summary":
                task_prompt = "この画面に表示されている内容を要約して、だらけた感じでコメントして"
            elif analysis_type == "opinion":
                task_prompt = "この画面の内容について、猫の視点で哲学的につぶやいて"
            elif analysis_type == "reaction":
                task_prompt = "この画面を見た感想を、ちょっと皮肉を込めてコメントして"
            elif analysis_type == "read":
                task_prompt = "この画面に表示されているテキストを読み上げて、なまけ猫らしくコメントして"
            else:
                task_prompt = "この画面について、なまけ猫らしくコメントして"
            
            prompt = f"""{self.character_prompt}

{task_prompt}

画面に表示されている内容を見て、AIなまけ猫としてコメントしてください。
テキストが読める場合は、その内容も含めてコメントしてください。

AIなまけ猫:"""
            
            # Gemini Vision APIで画像を解析
            response = self.vision_model.generate_content([prompt, image])
            comment = response.text.strip()
            
            print(f"[画像解析] コメント生成完了")
            return comment
            
        except Exception as e:
            print(f"[画像解析エラー] コメント生成失敗: {e}")
            
            # エラーをユーザーフレンドリーなメッセージに変換
            return self.get_friendly_error_message(e, "image")

    def analyze_obs_browser_source(self, source_name="ブラウザソース", analysis_type="summary"):
        """OBSのブラウザソースを解析してコメント"""
        print(f"=== OBS画面解析開始 ===")
        print(f"ソース名: {source_name}")
        print(f"解析タイプ: {analysis_type}")
        
        # OBSスクリーンショットを取得
        image, error = self.capture_obs_source_screenshot(source_name)
        if error:
            error_comment = f"画面が取得できないにゃ...{error}"
            print(f"エラー: {error_comment}")
            print(f"[デバッグ] error_comment の長さ: {len(error_comment)}")
            print(f"[デバッグ] error_comment の内容: '{error_comment}'")
            
            # OBSにエラーメッセージを表示
            print(f"[デバッグ] OBSテキスト更新開始（エラー）...")
            print(f"[デバッグ] OBSに送信するテキスト: '{error_comment}'")
            result = self.update_obs_text("webpage_comment", error_comment)
            print(f"[デバッグ] OBSテキスト更新結果: {result}")
            
            success = self.text_to_speech(error_comment)
            if not success:
                print("音声生成に失敗しました")
            print(f"[デバッグ] 音声読み上げ結果: {success}")
            return error_comment
        
        # 画像を一時保存（デバッグ用）
        try:
            debug_filename = f"obs_screenshot_{int(time.time())}.png"
            image.save(debug_filename)
            print(f"[デバッグ] スクリーンショットを保存: {debug_filename}")
        except Exception as e:
            print(f"[デバッグ] 画像保存エラー: {e}")
        
        # AI解析でコメント生成
        comment = self.analyze_obs_screenshot_with_ai(image, analysis_type)
        print(f"コメント: {comment}")
        print(f"[デバッグ] comment の長さ: {len(comment)}")
        print(f"[デバッグ] comment の内容: '{comment}'")
        
        # OBSにコメント全文を表示
        print(f"[デバッグ] OBSテキスト更新開始...")
        print(f"[デバッグ] OBSに送信するテキスト: '{comment}'")
        result = self.update_obs_text("webpage_comment", comment)
        print(f"[デバッグ] OBSテキスト更新結果: {result}")
        
        # 音声読み上げ
        print(f"[デバッグ] 音声読み上げ開始...")
        success = self.text_to_speech(comment)
        if not success:
            print("音声生成に失敗しました")
        print(f"[デバッグ] 音声読み上げ結果: {success}")
        
        # GUIにも表示
        self.add_text_to_display("OBS画面", f"{source_name} ({analysis_type})", "#ff8800")
        self.add_text_to_display("なまけ猫", comment, "#ffff00")
        
        return comment

    def obs_screen_analysis_mode(self):
        """OBS画面解析モード"""
        print("=== OBS画面解析モード ===")
        print("OBSのブラウザソースを見て、なまけ猫がコメントします")
        print("コマンド:")
        print("  'capture' または Enter - デフォルトソースを解析")
        print("  'capture ソース名' - 指定ソースを解析")
        print("  'summary ソース名' - 要約コメント")
        print("  'opinion ソース名' - 意見・感想")
        print("  'reaction ソース名' - リアクション")
        print("  'read ソース名' - テキスト読み上げ")
        print("  'list' - 利用可能なソースを表示")
        print("  'quit' - 終了")
        print()
        
        # OBS接続確認
        if not self.obs_ws:
            print("❌ OBS WebSocketに接続されていません")
            print("OBSを起動してWebSocketサーバーを有効化してください")
            return
        
        try:
            while True:
                user_input = input("コマンド: ").strip()
                
                if user_input.lower() == 'quit':
                    break
                elif user_input == '':
                    # デフォルト: ブラウザソースを要約
                    self.analyze_obs_browser_source("ブラウザソース", "summary")
                elif user_input.lower() == 'capture':
                    # デフォルト: ブラウザソースを要約
                    self.analyze_obs_browser_source("ブラウザソース", "summary")
                elif user_input.lower() == 'list':
                    # 利用可能なソースを表示
                    self.list_obs_sources()
                else:
                    # コマンド解析
                    parts = user_input.split(' ', 1)
                    if len(parts) == 2:
                        command = parts[0].lower()
                        source_name = parts[1]
                        
                        if command in ['capture', 'summary', 'opinion', 'reaction', 'read']:
                            analysis_type = command if command != 'capture' else 'summary'
                            self.analyze_obs_browser_source(source_name, analysis_type)
                        else:
                            print("無効なコマンドです")
                    elif len(parts) == 1:
                        command = parts[0].lower()
                        if command in ['summary', 'opinion', 'reaction', 'read']:
                            self.analyze_obs_browser_source("ブラウザソース", command)
                        else:
                            print("ソース名を指定してください")
                    else:
                        print("有効なコマンドを入力してください")
                
                print()
                
        except KeyboardInterrupt:
            pass
        except EOFError:
            pass
        
        print("OBS画面解析モード終了")

    def list_obs_sources(self):
        """OBSの利用可能なソースを表示"""
        try:
            if not self.obs_ws:
                print("❌ OBS WebSocketに接続されていません")
                return
            
            print("[OBS] 利用可能なソース一覧:")
            
            if OBS_WEBSOCKET_NEW:
                # 新しいライブラリ (obsws-python) を使用
                try:
                    # 現在のシーン情報を取得
                    current_scene_resp = self.obs_ws.get_current_program_scene()
                    scene_name = current_scene_resp.scene_name
                    print(f"現在のシーン: {scene_name}")
                    
                    # シーンアイテムリストを取得
                    scene_items_resp = self.obs_ws.get_scene_item_list(scene_name)
                    
                    for i, item in enumerate(scene_items_resp.scene_items, 1):
                        source_name = item['sourceName']
                        source_type = item.get('sourceType', 'unknown')
                        enabled = item.get('sceneItemEnabled', False)
                        status = "✓" if enabled else "✗"
                        print(f"  {i}. {status} {source_name} ({source_type})")
                        
                except Exception as api_error:
                    print(f"[OBS] ソース一覧取得エラー: {api_error}")
            else:
                # 古いライブラリ (obs-websocket-py) を使用
                try:
                    current_scene_response = self.obs_ws.call(obs_requests.GetCurrentScene())
                    scene_name = current_scene_response.getName()
                    sources = current_scene_response.getSources()
                    
                    print(f"現在のシーン: {scene_name}")
                    
                    for i, source in enumerate(sources, 1):
                        source_name = source['name']
                        source_type = source.get('type', 'unknown')
                        visible = source.get('render', False)
                        status = "✓" if visible else "✗"
                        print(f"  {i}. {status} {source_name} ({source_type})")
                        
                except Exception as api_error:
                    print(f"[OBS] ソース一覧取得エラー: {api_error}")
                    
        except Exception as e:
            print(f"[OBS] ソース一覧取得エラー: {e}")

# 使用例
if __name__ == "__main__":
    # API キーを環境変数から取得
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("GEMINI_API_KEY 環境変数が設定されていません")
        print("以下の方法でAPIキーを設定してください：")
        print("1. PowerShellで: $env:GEMINI_API_KEY='your_api_key_here'")
        print("2. または直接入力:")
        api_key = input("Gemini APIキーを入力してください: ").strip()
        if not api_key:
            print("APIキーが入力されませんでした。終了します。")
            exit(1)
    
    # AIなまけ猫インスタンス作成
    namakeneko = NamakeNekoAI(api_key)
    
    print("=== AIなまけ猫システム ===")
    print("VOICEVOXが起動していることを確認してください")
    print()
    print("📺 OBS連携機能について:")
    print("【テキスト表示機能】")
    print("- 'webpage_comment' テキストソースをOBSに追加")
    print("- AIなまけ猫のコメントがリアルタイムで表示されます")
    print()
    print("【口パクアニメーション機能】")
    print("- 'mouth_open' 画像ソースをOBSに追加（口を開いた画像）")
    print("- 音声再生中に自動で表示/非表示を切り替えます")
    print("- Live2Dを使用している場合は無効にすることを推奨")
    print()
    
    # VOICEVOX接続テスト
    try:
        test_response = requests.get(f"{namakeneko.voicevox_url}/speakers")
        if test_response.status_code == 200:
            print("✓ VOICEVOX接続成功")
        else:
            print("✗ VOICEVOX接続失敗")
            print("⚠ 音声なしモードで続行します")
    except Exception as e:
        print(f"✗ VOICEVOX接続エラー: {e}")
        print("⚠ 音声なしモードで続行します（テキストのみ表示）")
    
    # OBS WebSocket接続テスト
    if namakeneko.connect_obs_websocket():
        print("✓ OBS WebSocket使用（推奨）")
        
        # 口パクアニメーション機能の選択
        print()
        print("🎭 口パクアニメーション設定:")
        print("Live2Dを使用している場合は無効にすることを推奨します")
        mouth_animation_choice = input("口パクアニメーション機能を使用しますか？ (y/n): ").strip().lower()
        
        if mouth_animation_choice == 'n':
            namakeneko.mouth_animation_enabled = False
            print("✓ 口パクアニメーション機能を無効にしました")
        else:
            namakeneko.mouth_animation_enabled = True
            print("✓ 口パクアニメーション機能を有効にしました")
            print("  - OBSで 'mouth_open' ソースの表示/非表示を制御します")
            print("  - Live2Dと併用する場合は競合する可能性があります")
    else:
        print("⚠ OBS WebSocket接続失敗 - ホットキー方式を使用")
        namakeneko.use_obs_websocket = False
        namakeneko.mouth_animation_enabled = False
        print("⚠ 口パクアニメーション機能を無効にしました（WebSocket未接続のため）")
    
    # モード選択
    print("\n=== モード選択 ===")
    print("1. 配信モード - チャット応答・定期つぶやき機能")
    print("2. 対話モード - 1対1での会話")
    print("3. テキスト読み上げモード - テキストファイルを読み上げ")
    print("4. ノベルゲーム実況モード - ブラウザゲームを自動実況")
    print("5. Webページ読み上げモード - URLを読んでコメント")
    print("6. OBS画面解析モード - ブラウザソースを見てコメント")
    print("7. テストモード - 基本機能のテスト")
    
    try:
        mode = input("モードを選択してください (1/2/3/4/5/6/7): ").strip()
        
        if mode == "1":
            # 配信モード
            namakeneko.start_streaming_mode()
        elif mode == "2":
            # 対話モード
            namakeneko.interactive_mode()
        elif mode == "3":
            # テキスト読み上げモード
            namakeneko.text_reading_mode()
        elif mode == "4":
            # ノベルゲーム実況モード
            namakeneko.novel_game_mode()
        elif mode == "5":
            # Webページ読み上げモード
            namakeneko.webpage_reading_mode()
        elif mode == "6":
            # OBS画面解析モード
            namakeneko.obs_screen_analysis_mode()
        elif mode == "7":
            # テストモード
            print("\n=== テストモード ===")
            print("1. 基本機能テスト")
            print("2. OBSテキスト表示テスト")
            
            test_mode = input("テストモードを選択 (1/2): ").strip()
            
            if test_mode == "1":
                # 基本機能テスト
                test_inputs = [
                    "おはよう！",
                    "今日は何をする予定？"
                ]
                
                for user_input in test_inputs:
                    print(f"\nユーザー: {user_input}")
                    namakeneko.speak_response(user_input)
                    time.sleep(1)
                
                print("\n=== ランダムつぶやきテスト ===")
                namakeneko.speak_random_comment()
                print("\nテスト完了！")
                
            elif test_mode == "2":
                # OBSテキスト表示テスト
                print("\n=== OBSテキスト表示テスト ===")
                test_source = "webpage_comment"  # 共通ソースのみテスト
                
                test_text = f"テスト用テキスト - AIなまけ猫のコメント表示テストだにゃ〜"
                print(f"\n[テスト] '{test_source}' にテキスト表示中...")
                result = namakeneko.update_obs_text(test_source, test_text)
                if result:
                    print(f"✓ '{test_source}' テキスト表示成功")
                else:
                    print(f"❌ '{test_source}' テキスト表示失敗")
                time.sleep(3)
                
                # テキストをクリア
                namakeneko.update_obs_text(test_source, "")
                print(f"'{test_source}' テキストクリア")
                time.sleep(1)
                
                print("\nOBSテキスト表示テスト完了！")
            else:
                print("無効な選択です")
        else:
            print("無効な選択です")
            
    except KeyboardInterrupt:
        print("\n終了します")
    except EOFError:
        print("\n終了します")
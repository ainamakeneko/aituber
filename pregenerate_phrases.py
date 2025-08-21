#!/usr/bin/env python3
"""
よく使う挨拶や定型文を事前生成してファイルキャッシュするスクリプト
"""

import requests
import json
import os
import time
import hashlib

class PhrasePreGenerator:
    def __init__(self, voicevox_url="http://localhost:50021", speaker_id=3):
        self.voicevox_url = voicevox_url
        self.speaker_id = speaker_id
        self.cache_dir = "voice_cache"
        
        # キャッシュディレクトリを作成
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def get_cache_filename(self, text):
        """テキストからキャッシュファイル名を生成"""
        text_hash = hashlib.md5(f"{text}_{self.speaker_id}".encode()).hexdigest()
        return os.path.join(self.cache_dir, f"voice_{text_hash}.wav")
    
    def generate_and_cache_phrase(self, text):
        """フレーズを生成してファイルキャッシュ"""
        cache_file = self.get_cache_filename(text)
        
        # 既にキャッシュされている場合はスキップ
        if os.path.exists(cache_file):
            print(f"[キャッシュ済み] {text}")
            return cache_file
        
        try:
            # 1. audio_queryを生成
            query_url = f"{self.voicevox_url}/audio_query"
            query_params = {
                "text": text,
                "speaker": self.speaker_id
            }
            
            query_response = requests.post(query_url, params=query_params)
            query_response.raise_for_status()
            audio_query = query_response.json()
            
            # 2. 音声を合成
            synthesis_url = f"{self.voicevox_url}/synthesis"
            synthesis_params = {"speaker": self.speaker_id}
            
            synthesis_response = requests.post(
                synthesis_url,
                headers={"Content-Type": "application/json"},
                params=synthesis_params,
                data=json.dumps(audio_query)
            )
            synthesis_response.raise_for_status()
            
            # 3. ファイルに保存
            with open(cache_file, "wb") as f:
                f.write(synthesis_response.content)
            
            print(f"[生成完了] {text} -> {cache_file}")
            return cache_file
            
        except Exception as e:
            print(f"[生成エラー] {text}: {e}")
            return None
    
    def pregenerate_all(self):
        """全ての定型文を事前生成"""
        common_phrases = [
            # 基本挨拶
            "おはよう",
            "おはようございます", 
            "こんにちは",
            "こんばんは",
            "お疲れさま",
            "お疲れさまでした",
            "ありがとう",
            "ありがとうございます",
            "すみません",
            "失礼します",
            
            # なまけ猫らしい表現
            "働きたくないにゃ",
            "だらだらしたいにゃ",
            "眠いにゃ",
            "疲れたにゃ",
            "まあまあかにゃ",
            "そうだにゃ",
            "うーん、どうかにゃ",
            "今日もゆるゆると過ごそうにゃ",
            "人間って不思議だにゃ",
            "昼寝が一番だにゃ",
            "働くより寝てたいにゃ",
            "未来とかどうでもよくない？",
            
            # よくある応答
            "へぇ〜、そうなんだにゃ",
            "ちょっとわかるかも",
            "それは大変だにゃ",
            "頑張って...でも無理しないでにゃ",
            "まあ、そんな日もあるにゃ",
            "人間って忙しそうだにゃ",
            "もっとゆっくりしたらいいのに",
            "お疲れさま...休憩も大事だにゃ",
            
            # 短い相槌
            "にゃ",
            "そうにゃ",
            "うんうん",
            "なるほどにゃ",
            "わかるにゃ",
            "大丈夫？",
            "元気だにゃ",
            "調子はまあまあにゃ",
            
            # 配信用
            "みなさん、こんにちは",
            "今日もゆるゆると配信していくにゃ",
            "コメントありがとうにゃ",
            "また見に来てくれてありがとう",
            "今日はこの辺で終わりにするにゃ",
            "お疲れさまでした〜"
        ]
        
        print(f"[事前生成開始] {len(common_phrases)}個のフレーズを生成します...")
        
        success_count = 0
        for i, phrase in enumerate(common_phrases, 1):
            print(f"[{i}/{len(common_phrases)}] 処理中: {phrase}")
            
            if self.generate_and_cache_phrase(phrase):
                success_count += 1
            
            # VOICEVOX負荷軽減のため少し待機
            time.sleep(0.2)
        
        print(f"[事前生成完了] {success_count}/{len(common_phrases)}個のフレーズを生成しました")
        print(f"キャッシュディレクトリ: {self.cache_dir}")

if __name__ == "__main__":
    print("=== AIなまけ猫 音声事前生成ツール ===")
    print("VOICEVOXが起動していることを確認してください")
    
    # VOICEVOX接続テスト
    try:
        test_response = requests.get("http://localhost:50021/speakers")
        if test_response.status_code == 200:
            print("✓ VOICEVOX接続成功")
        else:
            print("✗ VOICEVOX接続失敗")
            exit(1)
    except Exception as e:
        print(f"✗ VOICEVOX接続エラー: {e}")
        print("VOICEVOXを起動してから再実行してください")
        exit(1)
    
    # 事前生成実行
    generator = PhrasePreGenerator()
    generator.pregenerate_all()
    
    print("\n事前生成が完了しました！")
    print("メインスクリプト実行時に、これらの音声が高速で再生されます。")
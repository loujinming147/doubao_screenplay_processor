#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
处理文件的主脚本
生成音频，合并为完整的播客
"""

import asyncio
import os
import sys

from utils import ToNlpTexts, merge_audio_files
from bidirection_client import BidirectionTTSClient
import time
import argparse
import logging
from pathlib import Path

def setup_logger(log_dir: str = "logs") -> logging.Logger:
    """设置日志：同时输出到控制台和文件"""
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"podcast_{time.strftime('%Y%m%d')}.log")

    logger = logging.getLogger("PodcastGenerator")
    logger.setLevel(logging.INFO)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 日志格式
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


async def main(args):
    logger = setup_logger()

    """主函数"""
    print("=" * 60)
    print("播客音频生成器")
    print("=" * 60)
    
    # 设置语音映射 - 将不白吃和苏轼都设置为S_62w7if2J1
    print("📝 配置语音映射...")


    print("✅ 语音映射配置完成:")
    for speaker, voice in args.voice_mapping.items():
        print(f"   {speaker} -> {voice}")
    
    # 文件路径配置
    text_file = args.text_file
    # output_dir = args.output_dir
    filename = os.path.basename(text_file)
    stem = Path(filename).stem
    output_dir = os.path.join(args.output_dir, stem)
    os.makedirs(output_dir, exist_ok=True)
    
    # 检查输入文件是否存在
    if not os.path.exists(text_file):
        print(f"❌ 错误: TEXT文件不存在: {text_file}")
        return
    
    print(f"\n📂 输入文件: {text_file}")
    print(f"📁 输出目录: {output_dir}")
    
    try:
        # 开始处理
        print(f"\n🚀 开始处理文件...")
  
        # 使用双向协议生成音频（支持 Resource 切换）
        use_bidirection = True
        if use_bidirection:

            # 解析文本为段落
            converter = ToNlpTexts()
            converter.voice_mapping.update(args.voice_mapping)
            nlp_texts = converter.convert_file_to_nlp_texts(text_file)
            print(f"解析完成，共 {len(nlp_texts)} 个文本段落")
        
            # 双向客户端
            client = BidirectionTTSClient(
                appid=args.appid,
                access_token=args.access_token,
            )
        
            os.makedirs(output_dir, exist_ok=True)
            audio_files = []
        
        
            for i, item in enumerate(nlp_texts):
                text = item["text"]
                voice_type = item["speaker"]  # 已是 voice_id，例如 S_62w7if2J1
                # 选择资源ID：S_ 前缀默认 seed-tts-2.0；否则 seed-icl-2.0；也可用 icl_voices 强制复刻
                resource_id = (
                    "seed-tts-2.0"
                    if not voice_type.startswith("S_")
                    else "seed-icl-2.0"
                )
                output_file = os.path.join(
                    output_dir, f"segment_{i:03d}_{voice_type}.mp3"
                )
                print(f"正在生成音频: {output_file} | voice={voice_type} | resource={resource_id}")
                print(f"文本内容: {text}")
                # 如果文件已存在则跳过
                # if os.path.exists(output_file) and voice_type != "zh_male_taocheng_uranus_bigtts":
                if os.path.exists(output_file):
                    print(f"⚠️ 文件已存在，跳过: {output_file}")
                    audio_files.append(output_file)
                    continue        
                ##########################################
                #### 手动修改音频参数 ######################
                ##########################################
                if voice_type == "S_7ndFaTPI1":
                    speech_rate = 0
                    loudness_rate = 10
                    emotion = "neutral"
                    emotion_scale = 0
                    pitch_rate = 0
                elif voice_type == "zh_male_taocheng_uranus_bigtts":
                    speech_rate = 0
                    loudness_rate = 0
                    emotion = "neutral"
                    emotion_scale = 0
                    pitch_rate = 5
                elif voice_type == "S_7ndFaTPI1":
                    speech_rate = 10
                    loudness_rate = 0
                    emotion = "neutral"
                    emotion_scale = 0
                    pitch_rate = 0
                elif voice_type == "saturn_zh_female_tiaopigongzhu_tob":
                    speech_rate = 0
                    loudness_rate = 0
                    emotion = "neutral"
                    emotion_scale = 0
                    pitch_rate = 4
                elif voice_type == "S_vJMEaTPI1":
                    speech_rate = 20
                    loudness_rate = 0
                    emotion = "neutral"
                    emotion_scale = 0
                    pitch_rate = 0
                else:
                    speech_rate=args.speech_rate
                    loudness_rate=args.loudness_rate
                    emotion=args.emotion
                    emotion_scale=args.emotion_scale
                    pitch_rate = args.pitch_rate
                try:
                    logger.info(f"   🎙️ 生成段落 {i+1}/{len(nlp_texts)} | voice={voice_type}")
                    print("text:", text)
                    await client.synthesize_to_file(
                    text=text,
                    voice_type=voice_type,
                    resource_id=resource_id,
                    output_file=output_file,
                    encoding="mp3",
                    speech_rate=speech_rate,
                    loudness_rate=loudness_rate,
                    emotion=emotion,
                    emotion_scale=emotion_scale,
                    pitch_rate=pitch_rate,
                    )
                    audio_files.append(output_file)
                except Exception as e:
                    logger.error(f"❌ TTS 生成失败 (段落 {i}): {e}")
                    continue  # 继续处理后续段落
        
            # 合并段落为完整播客，复用你已有函数
            final_audio = os.path.join(
                output_dir, f"podcast_complete_{int(time.time())}.mp3"
            )
            ok = merge_audio_files(audio_files, final_audio)
            if not ok:
                raise RuntimeError("音频合并失败")
        
            print(f"\n🎉 处理完成!")
            print(f"🎵 最终音频文件: {final_audio}")
            if os.path.exists(final_audio):
                file_size = os.path.getsize(final_audio)
                print(f"📊 文件大小: {file_size / 1024 / 1024:.2f} MB")
            return
        
        print(f"\n💡 提示:")
        print(f"   - 所有音频段落都使用 S_62w7if2J1 语音类型")
        print(f"   - 个别音频文件保存在: {output_dir}")
        print(f"   - 合并后的完整音频: {final_audio}")
        
    except Exception as e:
        print(f"\n❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
def parse_args():
    parser = argparse.ArgumentParser(description="处理文本文件生成语音播客")
    parser.add_argument("--text_file", type=str, default="assets/不白吃科普娃娃文稿部分.docx", help="输入的 TEXT 文件路径")
    parser.add_argument("--output_dir", type=str, default="output/kepuwawa", help="输出目录路径")
    parser.add_argument("--appid", type=str, default="7913609641", help="Doubao 应用 ID")
    parser.add_argument("--access_token", type=str, default="teLzt62B8gRhfKVOqAbEpiCgDl1Jxcjq", help="Doubao 访问令牌")
    parser.add_argument("--speech_rate", type=int, default=0, help="语速调整参数 -50,100 默认0不使用语速调整")
    parser.add_argument("--loudness_rate", type=int, default=0, help="音量调整参数 -50,100 默认0不使用音量调整")
    parser.add_argument("--emotion", type=str, default="neutral", help="情感调整参数  默认neutral不使用")
    parser.add_argument("--emotion_scale", type=float, default=0, help="情感强度调整参数 1-5 默认0不使用情感调整")
    parser.add_argument("--pitch_rate", type=int, default=0, help="音调调整参数 -50,100 默认0不使用音调调整")

    return parser.parse_args()

def show_help():
    """显示帮助信息"""
    print("=" * 40)
    print("功能:")
    print("  - 读取 TEXT 文件")
    print("  - 解析对话内容")
    print("  - 使用 S_62w7if2J1 语音类型生成音频")
    print("  - 合并所有音频段落为完整播客")
    print()
    print("用法:")
    print("  python process_text_to_voice.py")
    print("  python process_text_to_voice.py --help")

if __name__ == "__main__":
    
    args = parse_args()
    voice_mapping = {
        "不白吃": "S_fN2KaTPI1",
        "大方脸": "zh_male_taocheng_uranus_bigtts", # pitch_rate = 5
        "小 A": "S_7ndFaTPI1", # speech_rate = 10
        "蓝血豆": "saturn_zh_female_tiaopigongzhu_tob",  # pitch_rate = 4
        "药蜂婆婆": "S_vJMEaTPI1", # speech_rate = 30
    }
        # voice_mapping = {
    #     "不白吃": "S_fN2KaTPI1",
    #     # "张骞": "saturn_zh_female_tiaopigongzhu_tob",
    #     # "朱元璋": "S_vNQFaTPI1"
    #     "食客B": "S_hUnLaTPI1",
    #     "食客A": "S_vNQFaTPI1",
    #     "武则天": "S_vJMEaTPI1",
    #     "上官婉儿": "zh_female_meilinvyou_saturn_bigtts",
    #     "侍卫": "zh_male_taocheng_uranus_bigtts"
    # }

    args.voice_mapping = voice_mapping
    
    asyncio.run(main(args))

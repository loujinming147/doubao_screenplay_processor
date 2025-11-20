#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
批量处理文件夹内所有 Markdown 文件，生成播客音频
支持：
  - 自定义 input_dir / output_dir（命令行参数）
  - 日志记录到文件（logs/ 下，按日期命名）
"""

import asyncio
import os
import sys
import time
import glob
import logging
import argparse
from pathlib import Path

from utils import ToNlpTexts, merge_audio_files
from bidirection_client import BidirectionTTSClient


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


async def process_single_file(
    text_file: str,
    base_output_dir: str,
    voice_mapping: dict,
    client: BidirectionTTSClient,
    logger: logging.Logger
):
    """处理单个文件"""
    filename = os.path.basename(text_file)
    stem = Path(filename).stem
    output_dir = os.path.join(base_output_dir, stem)

    # 检查是否已处理
    # final_audio_pattern = os.path.join(output_dir, "podcast_complete_*.mp3")
    # if glob.glob(final_audio_pattern):
    #     logger.info(f"✅ 已存在完成音频，跳过: {filename}")
    #     return

    logger.info(f"🚀 开始处理文件: {filename}")
    os.makedirs(output_dir, exist_ok=True)

    try:
        converter = ToNlpTexts()
        converter.voice_mapping.update(voice_mapping)
        nlp_texts = converter.convert_file_to_nlp_texts(text_file)
        logger.info(f"   解析完成，共 {len(nlp_texts)} 个文本段落")
    except Exception as e:
        logger.error(f"❌ 解析失败 {filename}: {e}")
        return

    audio_files = []
    for i, item in enumerate(nlp_texts):
        text = item["text"]
        voice_type = item.get("speaker")
        if not voice_type or not text.strip():
            logger.warning(f"⚠️ 跳过无效段落 (无说话人或空文本): {text[:30]}...")
            continue

        resource_id = "seed-icl-2.0" if voice_type.startswith("S_") else "seed-tts-2.0"
        safe_voice = "".join(c for c in voice_type if c.isalnum() or c in "._-")
        output_file = os.path.join(output_dir, f"segment_{i:03d}_{safe_voice}.mp3")
        


        if os.path.exists(output_file):
            logger.info(f"   ⚠️ 文件已存在，跳过: segment_{i:03d}")
            audio_files.append(output_file)
            continue
        
        ##########################################
        #### 手动修改音频参数 ######################
        ##########################################
        if voice_type == "S_7ndFaTPI1":
            speech_rate = 0
            loudness_rate = 20
            emotion = "neutral"
            emotion_scale = 0
        elif voice_type == "S_vNQFaTPI1" or voice_type == "S_hUnLaTPI1":
            speech_rate = 30
            loudness_rate = 0
            emotion = "neutral"
            emotion_scale = 0
        elif voice_type == "S_fN2KaTPI1":
            speech_rate = -10
            loudness_rate = 0
            emotion = "neutral"
            emotion_scale = 0
        else:
            speech_rate=args.speech_rate
            loudness_rate=args.loudness_rate
            emotion=args.emotion
            emotion_scale=args.emotion_scale



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
            )
            audio_files.append(output_file)
        except Exception as e:
            logger.error(f"❌ TTS 生成失败 (段落 {i}): {e}")
            continue  # 继续处理后续段落

    if not audio_files:
        logger.error(f"❌ 无有效音频段落，跳过合并: {filename}")
        return

    try:
        final_audio = os.path.join(output_dir, f"podcast_complete_{int(time.time())}.mp3")
        ok = merge_audio_files(audio_files, final_audio)
        if ok and os.path.exists(final_audio):
            file_size = os.path.getsize(final_audio) / (1024 * 1024)
            logger.info(f"🎉 完成! 音频: {Path(final_audio).name} ({file_size:.2f} MB)")
        else:
            logger.error(f"❌ 音频合并失败: {filename}")
    except Exception as e:
        logger.error(f"❌ 合并异常: {e}")


async def main(args):
    logger = setup_logger()

    logger.info("=" * 60)
    logger.info("批量播客音频生成器（支持日志 & 命令行参数）")
    logger.info("=" * 60)

    # 语音映射配置（可后续改为配置文件）
    voice_mapping = {
        "不白吃": "S_fN2KaTPI1",
        # "张骞": "saturn_zh_female_tiaopigongzhu_tob",
        # "朱元璋": "S_vNQFaTPI1"
        "食客B": "S_hUnLaTPI1",
        "食客A": "S_vNQFaTPI1",
        "武则天": "S_7ndFaTPI1",
        "上官婉儿": "zh_female_meilinvyou_saturn_bigtts",
        "侍卫": "zh_male_taocheng_uranus_bigtts"
    }

    logger.info("✅ 语音映射配置:")
    for speaker, voice in voice_mapping.items():
        logger.info(f"   {speaker} -> {voice}")

    input_dir = args.input_dir
    base_output_dir = args.output_dir

    if not os.path.isdir(input_dir):
        logger.error(f"❌ 输入目录不存在: {input_dir}")
        return

    md_files = sorted(glob.glob(os.path.join(input_dir, "*.md")))
    if not md_files:
        logger.warning(f"⚠️ 未找到 .md 文件 in {input_dir}")
        return

    logger.info(f"\n📂 找到 {len(md_files)} 个 Markdown 文件")
    logger.info(f"📁 输入目录: {input_dir}")
    logger.info(f"📁 输出目录: {base_output_dir}")

    client = BidirectionTTSClient(
        appid="7913609641",
        access_token="teLzt62B8gRhfKVOqAbEpiCgDl1Jxcjq",
    )

    for idx, text_file in enumerate(md_files, 1):
        logger.info(f"\n{'-'*50}")
        logger.info(f"📄 [{idx}/{len(md_files)}] {os.path.basename(text_file)}")
        logger.info(f"{'-'*50}")
        try:
            await process_single_file(text_file, base_output_dir, voice_mapping, client, logger)
        except Exception as e:
            logger.error(f"💥 文件级异常 ({os.path.basename(text_file)}): {e}")
            import traceback
            logger.error(traceback.format_exc())
            continue

    logger.info(f"\n🎉 批量处理完成！共处理 {len(md_files)} 个文件。")


def parse_args():
    parser = argparse.ArgumentParser(description="批量生成播客音频")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="assets/test",
        help="输入 Markdown 文件目录"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/test",
        help="基础输出目录"
    )
    # parser.add_argument(
    #     "--help", "-h",
    #     action="help",
    #     help="显示帮助信息"
    # )
    return parser.parse_args()


if __name__ == "__main__":

    args = parse_args()
    asyncio.run(main(args))
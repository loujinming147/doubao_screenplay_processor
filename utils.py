# -*- coding: utf-8 -*-
import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import uuid
from typing import Any, Dict, List

import websockets

# 添加DOCX处理功能
try:
    from docx import Document
except ImportError:
    print("请安装python-docx库: pip install python-docx")
    sys.exit(1)

class ToNlpTexts:
    """
    DOCX、md文件转换为nlp_texts格式的转换器
    支持多种对话格式和场景描述清理
    """
    
    def __init__(self):
        # 预定义的声音映射
        self.voice_mapping = {
            "不白吃": "S_r7eMaTPI1",
            "小星": "S_1GQLaTPI1",
        }
        
        # 默认声音列表
        self.default_voices = [
            "zh_female_mizaitongxue_v2_saturn_bigtts",
            "zh_male_dayixiansheng_v2_saturn_bigtts"
        ]
    
    def get_voice_for_speaker(self, speaker: str) -> str:
        """为说话人分配声音ID"""
        if speaker in self.voice_mapping:
            return self.voice_mapping[speaker]
        
        # 为新说话人分配声音
        voice_index = len(self.voice_mapping) % len(self.default_voices)
        voice_id = self.default_voices[voice_index]
        self.voice_mapping[speaker] = voice_id
        print(f"为额外的说话人 {speaker} 分配声音 {voice_id}")
        return voice_id
    
    def clean_text_markers(self, text: str) -> str:
        """
        清理文本中的场景描述标记
        去除 () 和 【】 中的内容，但保留说话人标记
        """
        # 先处理【开场场景音】这类独立的场景标记
        text = re.sub(r'【[^】]*场景[^】]*】', '', text)
        
        # 去除括号中的场景描述，但要小心不要误删说话人名称
        # 匹配 （描述内容） 格式的场景描述
        text = re.sub(r'（[^）]*）', '', text)
        text = re.sub(r'\([^)]*\)', '', text)
        
        return text.strip()
    
    def extract_speaker_and_content(self, line: str) -> tuple:
        """
        从一行文本中提取说话人和内容
        支持多种格式的说话人标记
        """
        line = line.strip()
        if not line:
            return None, None
    
        # 忽略纯场景/旁白行（整行都在括号内）
        if re.match(r'^\s*[（(][^）)]*[）)]\s*$', line):
            return None, None
    
        # 统一引号与分隔符，兼容 “ ”、「 」、『 』
        line = (
            line.replace('“', '"')
                .replace('”', '"')
                .replace('「', '"')
                .replace('」', '"')
                .replace('『', '"')
                .replace('』', '"')
        )
        # 规范化 冒号+引号 的常见写法为 : "
        line = re.sub(r'\s*[：:]\s*"', ': "', line)
    
        speaker = None
        content = None
    
        # 格式1: 说话人（描述）：内容 或 说话人（描述）：“内容”
        match = re.match(r'^\s*([^：:（(]+?)\s*(?:（[^）]*）)?\s*[：:]\s*(.+)\s*$', line)
        if match:
            speaker = match.group(1).strip()
            content = match.group(2).strip()
    
        # 格式2: [说话人] 内容
        elif re.match(r'^\s*\[([^\]]+)\]\s*(.+)$', line):
            match = re.match(r'^\s*\[([^\]]+)\]\s*(.+)$', line)
            speaker = match.group(1).strip()
            content = match.group(2).strip()
    
        # 格式3: 【说话人】内容
        elif re.match(r'^\s*【([^】]+)】\s*(.+)$', line):
            match = re.match(r'^\s*【([^】]+)】\s*(.+)$', line)
            speaker = match.group(1).strip()
            content = match.group(2).strip()
    
        # 清理内容中的场景描述与外层引号
        if content:
            content = self.clean_text_markers(content).strip()
            # 去掉包裹内容的外层引号（"..." 或 '...'），保留内部的 ‘ ’
            content = re.sub(r'^(["\'])\s*(.*?)\s*\1$', r'\2', content)
    
        return speaker, content

    def extract_speaker_and_content_old(self, line: str) -> tuple:
        """
        从一行文本中提取说话人和内容
        支持多种格式的说话人标记
        """
        line = line.strip()
        if not line:
            return None, None
        
        speaker = None
        content = None
        
        # 格式1: 说话人（描述）：内容
        match = re.match(r'^([^：:（(]+)(?:（[^）]*）)?[：:](.+)$', line)
        if match:
            speaker = match.group(1).strip()
            content = match.group(2).strip()
        
        # 格式2: [说话人] 内容
        elif re.match(r'^\[([^\]]+)\](.+)$', line):
            match = re.match(r'^\[([^\]]+)\](.+)$', line)
            speaker = match.group(1).strip()
            content = match.group(2).strip()
        
        # 格式3: 【说话人】内容
        elif re.match(r'^【([^】]+)】(.+)$', line):
            match = re.match(r'^【([^】]+)】(.+)$', line)
            speaker = match.group(1).strip()
            content = match.group(2).strip()
        
        # 清理内容中的场景描述
        if content:
            content = self.clean_text_markers(content)
        
        return speaker, content

    def read_docx_file(self, file_path: str) -> str:
        """读取DOCX文件内容"""
        try:
            doc = Document(file_path)
            text_content = []
            
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text_content.append(paragraph.text.strip())
            
            return '\n'.join(text_content)
        except Exception as e:
            raise Exception(f"读取DOCX文件失败: {e}")
    
    
    def parse_dialogue_format(self, text: str) -> List[Dict[str, Any]]:
        """
        解析对话格式的文本
        支持格式：
        1. 说话人：内容
        2. 说话人（描述）：内容  
        3. [说话人] 内容
        4. 【说话人】内容
        """
        nlp_texts = []
        
        # 先进行整体的文本清理
        cleaned_text = self.clean_text_markers(text)
        lines = cleaned_text.split('\n')
        
        for line in lines:
            speaker, content = self.extract_speaker_and_content(line)
            
            if speaker and content:
                # 进一步清理说话人名称中的描述
                speaker = re.sub(r'（[^）]*）', '', speaker).strip()
                speaker = re.sub(r'\([^)]*\)', '', speaker).strip()
                
                voice_id = self.get_voice_for_speaker(speaker)
                nlp_texts.append({
                    "speaker": voice_id,
                    "text": content
                })
        
        return nlp_texts
    
    def convert_docx_to_nlp_texts(self, docx_file_path: str) -> List[Dict[str, Any]]:
        """
        将DOCX文件转换为nlp_texts格式
        """
        # 读取DOCX文件
        text_content = self.read_docx_file(docx_file_path)
        
        # 解析对话格式
        nlp_texts = self.parse_dialogue_format(text_content)
        
        if not nlp_texts:
            raise Exception("未能从DOCX文件中解析出有效的对话内容")
        
        return nlp_texts

    def read_md_file(self, file_path: str) -> str:
        """
        读取Markdown文件内容并进行必要的清理
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()

            # 移除三引号代码块
            text = re.sub(r'```.*?```', '', text, flags=re.S)
            # 移除图片 ![alt](url)
            text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
            # 链接 [text](url) 保留可读文本
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
            # 去掉行首引用符号和列表符号
            text = re.sub(r'^\s*>\s*', '', text, flags=re.M)
            text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.M)
            # 去掉标题井号
            text = re.sub(r'^\s*#{1,6}\s*', '', text, flags=re.M)
            # 去掉行内反引号
            text = re.sub(r'`([^`]*)`', r'\1', text)
            # 去掉<>以及其中的内容
            text = re.sub(r'<.*?>', '', text)

            #  去掉所有*
            text = re.sub(r'\*', '', text)

            # 标准化为逐行文本
            lines = [line.strip() for line in text.splitlines() if line.strip()]

            return '\n'.join(lines)
        except Exception as e:
            raise Exception(f"读取Markdown文件失败: {e}")
    
    def convert_md_to_nlp_texts(self, md_file_path: str) -> List[Dict[str, Any]]:
        """
        将Markdown文件转换为nlp_texts格式
        """
        text_content = self.read_md_file(md_file_path)
        nlp_texts = self.parse_dialogue_format(text_content)
        if not nlp_texts:
            raise Exception("未能从Markdown中解析出有效的对话内容")
        return nlp_texts

    def convert_file_to_nlp_texts(self, file_path: str) -> List[Dict[str, Any]]:
        """
        统一入口：根据文件扩展名（.docx / .md / .markdown）转换为 nlp_texts。
        """
        if not os.path.isfile(file_path):
            raise Exception(f"文件不存在: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".docx":
            return self.convert_docx_to_nlp_texts(file_path)
        elif ext in {".md", ".markdown"}:
            return self.convert_md_to_nlp_texts(file_path)
        else:
            raise Exception(f"不支持的文件类型: {ext}，请使用 .docx 或 .md/.markdown")

def merge_audio_files(audio_files: List[str], output_file: str) -> bool:
    """合并音频文件"""
    try:
        # 检查是否安装了pydub
        try:
            from pydub import AudioSegment
        except ImportError:
            print("需要安装pydub库: pip install pydub")
            # 使用简单的二进制合并作为备选方案
            return simple_merge_audio_files(audio_files, output_file)
        
        print(f"正在合并 {len(audio_files)} 个音频文件...")
        
        # 使用pydub合并音频
        combined = AudioSegment.empty()
        for audio_file in audio_files:
            if os.path.exists(audio_file):
                audio = AudioSegment.from_mp3(audio_file)
                combined += audio
                print(f"已添加: {os.path.basename(audio_file)}")
            else:
                print(f"文件不存在，跳过: {audio_file}")
        
        # 导出合并后的音频
        combined.export(output_file, format="mp3")
        print(f"音频合并完成: {output_file}")
        return True
        
    except Exception as e:
        print(f"音频合并失败: {e}")
        return False

def simple_merge_audio_files(audio_files: List[str], output_file: str) -> bool:
    """简单的二进制音频文件合并（备选方案）"""
    try:
        print(f"使用简单合并方式合并 {len(audio_files)} 个音频文件...")
        
        with open(output_file, "wb") as outfile:
            for audio_file in audio_files:
                if os.path.exists(audio_file):
                    with open(audio_file, "rb") as infile:
                        outfile.write(infile.read())
                    print(f"已添加: {os.path.basename(audio_file)}")
                else:
                    print(f"文件不存在，跳过: {audio_file}")
        
        print(f"音频合并完成: {output_file}")
        return True
        
    except Exception as e:
        print(f"简单音频合并失败: {e}")
        return False



if __name__ == "__main__":
    utils = ToNlpTexts()
    
    extract_speaker_and_content = utils.extract_speaker_and_content
    text = "《西游记》第一回播客：石猴蹦出当大王啦！"
    print(extract_speaker_and_content(text))




import gradio as gr
import os
import uuid
import time
import asyncio
import base64
from typing import List, Dict, Any

from utils import ToNlpTexts, merge_audio_files
from bidirection_client import BidirectionTTSClient


def parse_file(file_obj) -> tuple:
    if file_obj is None:
        return [], [], []
    path = file_obj.name
    utils = ToNlpTexts()
    text_items = utils.convert_file_to_nlp_texts_keep_names(path)
    items: List[Dict[str, Any]] = []
    roles: List[str] = []
    for idx, it in enumerate(text_items):
        items.append({
            "segment_id": idx,
            "speaker_name": it.get("speaker_name", ""),
            "voice_type": "",
            "text": it.get("text", ""),
        })
        name = it.get("speaker_name", "")
        if name and name not in roles:
            roles.append(name)
    rows = [[r, ""] for r in roles]
    return items, rows, f"解析到 {len(items)} 段，识别到 {len(roles)} 个角色"


def fill_defaults(role_table: List[List[str]]) -> List[List[str]]:
    defaults = {
        "不白吃": "S_fN2KaTPI1",
        "食客A": "S_vNQFaTPI1",
        "食客B": "S_hUnLaTPI1",
        "武则天": "S_vJMEaTPI1",
        "上官婉儿": "zh_female_meilinvyou_saturn_bigtts",
        "侍卫": "zh_male_taocheng_uranus_bigtts",
    }
    out = []
    for row in role_table or []:
        name = row[0]
        vt = row[1] if len(row) > 1 else ""
        out.append([name, vt or defaults.get(name, vt)])
    return out


def build_role_map(role_table: Any) -> Dict[str, str]:
    m = {}
    if role_table is None:
        return m
    rows = None
    if hasattr(role_table, "values"):
        try:
            rows = role_table.values.tolist()
        except Exception:
            rows = None
    if rows is None:
        rows = role_table if isinstance(role_table, list) else []
    for row in rows:
        if isinstance(row, dict):
            name = row.get("speaker_name")
            vt = row.get("voice_type")
        else:
            name = row[0] if len(row) > 0 else None
            vt = row[1] if len(row) > 1 else None
        if name and vt:
            m[name] = vt
    return m


async def generate_segments(items: List[Dict[str, Any]], role_table: List[List[str]], appid: str, access_token: str, encoding: str, sample_rate: int, speech_rate: float, loudness_rate: float, emotion: str, emotion_scale: float, pitch_rate: float, session_id: str):
    role_map = build_role_map(role_table)
    out_dir = os.path.join("output", session_id)
    os.makedirs(out_dir, exist_ok=True)
    client = BidirectionTTSClient(appid=appid, access_token=access_token, sample_rate=sample_rate)
    files = []
    latest = None
    for it in items:
        name = it.get("speaker_name", "")
        text = it.get("text", "")
        voice = role_map.get(name)
        if not voice or not text:
            continue
        rid = BidirectionTTSClient.get_resource_id_for_voice(voice)
        safe_voice = "".join(c for c in voice if c.isalnum() or c in "._-")
        seg = it.get("segment_id", 0)
        fout = os.path.join(out_dir, f"segment_{seg:03d}_{safe_voice}.mp3")
        await client.synthesize_to_file(
            text=text,
            voice_type=voice,
            resource_id=rid,
            output_file=fout,
            encoding=encoding,
            speech_rate=speech_rate,
            loudness_rate=loudness_rate,
            emotion=emotion,
            emotion_scale=emotion_scale,
            pitch_rate=pitch_rate,
        )
        files.append(fout)
        latest = fout
    return files, latest or ""


def ui():
    with gr.Blocks() as demo:
        session = gr.State(str(uuid.uuid4()))
        items_state = gr.State([])
        files_state = gr.State([])

        with gr.Row():
            file_input = gr.File(file_types=[".docx", ".md"], label="上传剧本文档")
            parse_btn = gr.Button("解析")
        parse_info = gr.Textbox(label="解析结果", interactive=False)
        items_view = gr.Dataframe(headers=["segment_id", "speaker_name", "voice_type", "text"], datatype=["number", "str", "str", "str"], row_count=(0, "dynamic"), label="分段预览")
        role_table = gr.Dataframe(headers=["speaker_name", "voice_type"], datatype=["str", "str"], row_count=(0, "dynamic"), label="角色映射")
        # fill_btn = gr.Button("填充默认映射")

        with gr.Accordion("参数设置", open=True):
            appid = gr.Textbox(label="appid", value="7913609641")
            access_token = gr.Textbox(label="access_token", value="teLzt62B8gRhfKVOqAbEpiCgDl1Jxcjq", type="password")
            encoding = gr.Dropdown(choices=["mp3", "ogg_opus", "pcm"], value="mp3", label="encoding")
            sample_rate = gr.Dropdown(choices=[8000,16000,22050,24000,32000,44100,48000], value=24000, label="sample_rate")
            speech_rate = gr.Slider(minimum=-50, maximum=100, value=0, step=1, label="speech_rate")
            loudness_rate = gr.Slider(minimum=-50, maximum=100, value=0, step=1, label="loudness_rate")
            emotion = gr.Dropdown(choices=["neutral","happy","sad","angry"], value="neutral", label="emotion")
            emotion_scale = gr.Slider(minimum=0, maximum=5, value=0, step=1, label="emotion_scale")
            pitch_rate = gr.Slider(minimum=-50, maximum=100, value=0, step=1, label="pitch_rate")

        gen_btn = gr.Button("开始生成")
        latest_audio = gr.Audio(label="最新段落音频")
        files_preview = gr.HTML(label="段落预览")
        files_list = gr.JSON(label="已生成文件列表")
        merge_btn = gr.Button("合并音频")
        merged_audio = gr.Audio(label="合并后音频")
        merged_info = gr.Textbox(label="合并结果", interactive=False)

        def on_parse(f):
            items, role_rows, info = parse_file(f)
            view_rows = [[it.get("segment_id", 0), it.get("speaker_name", ""), it.get("voice_type", ""), it.get("text", "")] for it in items]
            return items, view_rows, role_rows, info

        parse_btn.click(on_parse, inputs=[file_input], outputs=[items_state, items_view, role_table, parse_info])

        def on_fill(tbl):
            return fill_defaults(tbl)

        # fill_btn.click(on_fill, inputs=[role_table], outputs=[role_table])

        async def on_generate(items, tbl, appid_v, token_v, enc, sr, sr2, lr, emo, emo_s, pr, sess):
            files, latest = await generate_segments(items, tbl, appid_v, token_v, enc, int(sr), float(sr2), float(lr), emo, float(emo_s), float(pr), sess)
            # Build HTML preview with embedded base64 audio for reliable playback
            mime = "audio/mpeg" if enc == "mp3" else ("audio/ogg; codecs=opus" if enc == "ogg_opus" else "audio/wav")
            seg_to_item = {it.get("segment_id"): it for it in (items or [])}
            html_parts = []
            for f in files or []:
                try:
                    b64 = base64.b64encode(open(f, "rb").read()).decode()
                except Exception:
                    b64 = ""
                base = os.path.basename(f)
                parts = base.split("_")
                seg_id = None
                if len(parts) >= 2 and parts[0] == "segment":
                    try:
                        seg_id = int(parts[1])
                    except Exception:
                        seg_id = None
                it = seg_to_item.get(seg_id, {})
                name = it.get("speaker_name", "") if isinstance(it, dict) else ""
                text = it.get("text", "") if isinstance(it, dict) else ""
                label = f"<b>{name}</b>: {text}" if (name or text) else base
                if b64:
                    html_parts.append(f'<div style="margin-bottom:8px">{label}<br/><audio controls src="data:{mime};base64,{b64}"></audio></div>')
                else:
                    html_parts.append(f'<div style="margin-bottom:8px">{label}<br/><audio controls src="{f}"></audio></div>')
            html = "\n".join(html_parts) if html_parts else "<div>未生成任何音频</div>"
            return files, latest, html, files

        gen_btn.click(on_generate, inputs=[items_state, role_table, appid, access_token, encoding, sample_rate, speech_rate, loudness_rate, emotion, emotion_scale, pitch_rate, session], outputs=[files_state, latest_audio, files_preview, files_list])

        def on_merge(files, sess):
            if not files:
                return None, "无可合并文件"
            out_file = os.path.join("output", sess, f"podcast_complete_{int(time.time())}.mp3")
            ok = merge_audio_files(files, out_file)
            if ok:
                return out_file, f"合并完成: {out_file}"
            return None, "合并失败"

        merge_btn.click(on_merge, inputs=[files_state, session], outputs=[merged_audio, merged_info])

    return demo


if __name__ == "__main__":
    demo = ui()
    # 共享形式，其他人也可以访问
    share_url = demo.launch(server_name="0.0.0.0", server_port=12997, share=True)
    print(f"Share URL: {share_url}")
    
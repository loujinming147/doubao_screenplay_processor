#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import copy
import json
import logging
import uuid

import websockets
from volcengine_bidirection_demo.protocols.protocols import (
    EventType,
    MsgType,
    finish_connection,
    finish_session,
    receive_message,
    start_connection,
    start_session,
    task_request,
    wait_for_event,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BidirectionTTSClient:
    def __init__(
        self,
        appid: str,
        access_token: str,
        endpoint: str = "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
        max_size: int = 10 * 1024 * 1024,
        sample_rate: int = 24000,
    ):
        self.appid = appid
        self.access_token = access_token
        self.endpoint = endpoint
        self.max_size = max_size
        self.sample_rate = sample_rate

    async def synthesize_to_file(
        self,
        text: str,
        voice_type: str,
        resource_id: str,  # "seed-icl-2.0" 或 "seed-tts-2.0"
        output_file: str,
        encoding: str = "mp3",
        speech_rate: float = 0,
        loudness_rate: float = 0,
        emotion: str = "neutral",
        emotion_scale: float = 0,
    ) -> None:
        """
        使用双向协议合成文本为音频文件。支持通过 resource_id 切换 TTS/声音复刻。
        """
        headers = {
            "X-Api-App-Key": self.appid,
            "X-Api-Access-Key": self.access_token,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
        logger.info(f"Connecting to {self.endpoint} with headers: {headers}")

        websocket = await websockets.connect(
            self.endpoint, additional_headers=headers, max_size=self.max_size
        )
        logger.info(
            f"Connected, Logid: {websocket.response.headers.get('x-tt-logid', 'unknown')}"
        )

        try:
            # Start connection
            await start_connection(websocket)
            await wait_for_event(
                websocket, MsgType.FullServerResponse, EventType.ConnectionStarted
            )

            # Base request
            base_request = {
                "user": {"uid": str(uuid.uuid4())},
                "namespace": "BidirectionalTTS",
                "req_params": {
                    "speaker": voice_type,
                    "audio_params": {
                        "format": encoding,
                        "sample_rate": self.sample_rate,
                        "enable_timestamp": True,
                    },
                    "additions": json.dumps({"disable_markdown_filter": False}),
                },
            }
            print("#"*100,)
            print(speech_rate)
            # Start session
            session_id = str(uuid.uuid4())
            start_session_request = copy.deepcopy(base_request)
            start_session_request["event"] = EventType.StartSession
            if speech_rate != 0:
                start_session_request["req_params"]["audio_params"]["speech_rate"] = speech_rate
            if loudness_rate != 0:
                start_session_request["req_params"]["audio_params"]["loudness_rate"] = loudness_rate
            if emotion != "neutral":
                start_session_request["req_params"]["audio_params"]["emotion"] = emotion
            if emotion_scale != 0:
                start_session_request["req_params"]["audio_params"]["emotion_scale"] = emotion_scale
            await start_session(
                websocket, json.dumps(start_session_request).encode(), session_id
            )
            await wait_for_event(
                websocket, MsgType.FullServerResponse, EventType.SessionStarted
            )

            # Send full text in one task (也可改为逐字符/逐句分片)
            synthesis_request = copy.deepcopy(base_request)
            synthesis_request["event"] = EventType.TaskRequest
            synthesis_request["req_params"]["text"] = text
            await task_request(
                websocket, json.dumps(synthesis_request).encode(), session_id
            )

            # Finish session
            await finish_session(websocket, session_id)

            # Receive audio
            audio_data = bytearray()
            while True:
                msg = await receive_message(websocket)
                if msg.type == MsgType.FullServerResponse:
                    if msg.event == EventType.SessionFinished:
                        break
                elif msg.type == MsgType.AudioOnlyServer:
                    audio_data.extend(msg.payload)
                elif msg.type == MsgType.Error:
                    raise RuntimeError(f"TTS conversion failed: {msg}")

            if not audio_data:
                raise RuntimeError("No audio data received")

            # Save
            with open(output_file, "wb") as f:
                f.write(audio_data)
            logger.info(
                f"Audio saved to {output_file}, bytes={len(audio_data)}, speaker={voice_type}, resource={resource_id}"
            )

        finally:
            await finish_connection(websocket)
            await wait_for_event(
                websocket, MsgType.FullServerResponse, EventType.ConnectionFinished
            )
            await websocket.close()
            logger.info("Connection closed")

    @staticmethod
    def get_resource_id_for_voice(voice_type: str) -> str:
        """
        默认策略：S_ 前缀走 seed-tts-2.0，否则走 seed-icl-2.0。
        可在调用层覆盖。
        """
        return "seed-icl-2.0" if voice_type.startswith("S_") else "seed-tts-2.0"
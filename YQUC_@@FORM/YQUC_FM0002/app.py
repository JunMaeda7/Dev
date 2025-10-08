from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import requests
import uvicorn
import os
import httpx
import asyncio
from fastapi import FastAPI, Query
from typing import List, Optional
from pydantic import BaseModel

description= "原価センタマスタに紐ついている事業領域を表示する"
app = FastAPI(
    title="フォーム代入（事業領域）",
    description=description,
    summary="フォームに選択した原価センタに基づいて、事業領域にドロップダウンリストを表示される。",
    version="0.0.1",
    terms_of_service="http://example.com/terms/",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)
cf_port = int(os.getenv("PORT", 3000))
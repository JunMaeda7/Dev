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

description= "原価センタの選択を可能とする"
app = FastAPI(
    title="フォーム代入（原価センタ）",
    description=description,
    summary="セールスサービスで入力した会社に基づいて、原価センタをフォームのドロップダウンリストに表示される。",
    version="0.0.1",
    terms_of_service="http://example.com/terms/",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)
cf_port = int(os.getenv("PORT", 3000))

cost_centers =[
  { "companyID": "C280", "CostCenter": "研究_特許(CB00280A01)" },
  { "companyID": "C280", "CostCenter": "研究_共通(CB00280A02)" },
  { "companyID": "C280", "CostCenter": "研究_第一チーム(CB00280A03)" },
  { "companyID": "C280", "CostCenter": "戦略本部(CB00280B01)" },
  { "companyID": "C280", "CostCenter": "品質管理部(CB00280C01)" },
  { "companyID": "C280", "CostCenter": "品証_品質保証T(CB00280C02)" },
  { "companyID": "C280", "CostCenter": "共通_原材料仕入(CB00280D01)" },
  { "companyID": "C280", "CostCenter": "調達部_共通(CB00280D02)" },
  { "companyID": "C280", "CostCenter": "冷市_商品仕入(CB11280D01)" },
  { "companyID": "C280", "CostCenter": "営業戦略部_冷食(CB11280F11)" },
  { "companyID": "C280", "CostCenter": "営業戦略部_業務(CB13280F11)" },
  { "companyID": "C280", "CostCenter": "業務_東京営業一課(CB13280F13)" },
  { "companyID": "S353", "CostCenter": "全社共通(SS01A00)" },
  { "companyID": "S353", "CostCenter": "全社共通（企画）(SS01A01)" },
  { "companyID": "S353", "CostCenter": "ビジネスサポートG共通(SS01B01)" },
  { "companyID": "S353", "CostCenter": "Facility Management T(SS01B05)" },
  { "companyID": "S353", "CostCenter": "財務経理G共通(SS01F10)" },
  { "companyID": "S353", "CostCenter": "文書管理室(SS01F21)" },
  { "companyID": "S353", "CostCenter": "人事G共通(SS01H10)" },
  { "companyID": "S353", "CostCenter": "企画T(人事)(SS01H11)" },
  { "companyID": "S353", "CostCenter": "P2PG共通(SS01P10)" },
  { "companyID": "S353", "CostCenter": "Strategic Planning T(SS01P16)" },
  { "companyID": "S353", "CostCenter": "企画G共通(SS01S10)" }
]


@app.post("/costcenter")
async def costcenter(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ##  {"requestBody":{'case': {"company": { "displayId": "C280" } }

        # Extract fields from payload
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)
        # Extract companyID
        companyID = case_data.get("company", {}).get("displayId")
        print("companyID:", companyID)

        if not companyID:
            raise HTTPException(status_code=400, detail="Missing companyID")
        
        # Find matching items in costcenter based on companyID
        matching_costcenter = [
            item for item in cost_centers
            if item["companyID"] == companyID
        ]
 
        # Extract cost_center values
        CostCenter = [item["CostCenter"] for item in matching_costcenter]
 
        print("Matching cost_center:", CostCenter)
 

         # Build the response structure
        response_body = {
            "responseBody": {
            "messages": [
                {
                "code": "S000",
                "message": "Success",
                "type": "INFO"
                }
            ],
            "value": {
                "codes": [
                {
                    "description": "",
                    "key": item["CostCenter"]
                } for item in matching_costcenter if "CostCenter" in item
                ]
            },
            "isSuccess": True
            }
        }

        return JSONResponse(content=response_body,status_code=200)
 
    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(ex)}")

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=cf_port, log_level="info")
    print('Prehook started....')
 
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
from hdbcli import dbapi
import json
from datetime import datetime, timedelta

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
print("Start....")


conn = dbapi.connect(
    address="6476e830-defb-4b04-871c-7c375442b10a.hana.prod-ap21.hanacloud.ondemand.com",
    port=443,
    user="DBADMIN",
    password="11223344556677889900Aeee"
)
cursor = conn.cursor()

cursor.execute("select * from TBL_BA")
rows = cursor.fetchall()

columns = [col[0] for col in cursor.description]
TBL_BA = [dict(zip(columns, r)) for r in rows]
# print(TBL_MECA)

# Convert to Python list for usage and trim string fields for clearer output
json_result_BA = json.dumps(TBL_BA, ensure_ascii=False)


# Log JSON string for debugging
#print(json.dumps(json_result_BA, ensure_ascii=False))


@app.get('/health')
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)
 


@app.post("/BusinessArea")
async def forms_integration(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {"requestBody": {"Form": {"F_meisai": {"F_Cost_center": "string"  }    }  }}

        # Extract fields from payload
        Form_data = json_body.get("requestBody", {}).get("Form", {})
        print("Form_data:", Form_data)
        
        # Extract CostCenter from the ItemTable in Form    
        item_table = Form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            CostCenter = item_table[0].get("F_Cost_center")
            print("Extracted CostCenter from item_table:", CostCenter)

        if not CostCenter:
            raise HTTPException(status_code=400, detail="Missing field_CostCenter")
             
        # Parse json_result_BA back into a Python object
        BA_data = json.loads(json_result_BA)

        # Normalize inputs so .strip()
        CC = (CostCenter or "").strip()

        # Match rows by Cost_center (trimmed) and collect BUSINESS_AREA values
        matched = [
            item for item in BA_data
            if item.get("COST_CENTER").strip() == CC
        ]
        if not matched:
            raise HTTPException(status_code=401, detail="No matched_COST_CENTER")
        
        print("matched:", matched)

        # Extract BusinessArea values and remove duplicates (preserve order)
        BusinessArea = [item.get("BUSINESS_AREA") for item in matched if item.get("BUSINESS_AREA") is not None]

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched:
            val = item.get("BUSINESS_AREA")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})
 
        response_body = {
            "responseBody": {
                "messages": [
                    {"code": "S000", "message": "Success", "type": "INFO"}
                ],
                "value":{
                "codes": codes
            },    
        "isSuccess": True
        }
     }
        

        return JSONResponse(content=response_body)

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(ex)}")



if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=cf_port, log_level="info")
    print('Prehook started....')
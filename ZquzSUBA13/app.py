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

description= "会社コードに紐ついている施策区分を取得"
app = FastAPI(
    title="フォーム代入（施策区分）",
    description=description,
    summary="Self-serviceに選択した会社コードに基づいて、施策区分にドロップダウンリストを表示される。",
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

cursor.execute("select * from TBL_MECA ")
rows = cursor.fetchall()

columns = [col[0] for col in cursor.description]
TBL_MECA = [dict(zip(columns, r)) for r in rows]
# print(TBL_MECA)

# Convert to Python list for usage and trim string fields for clearer output
json_result_MECA = [
    {k: (v.strip() if isinstance(v, str) else v) for k, v in d.items()}
    for d in TBL_MECA
]
# Log JSON string for debugging
#print(json.dumps(json_result_MECA, ensure_ascii=False))


@app.get('/health')
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)
 


@app.post("/MeasureCate")
async def forms_integration(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {"requestBody": {"case": {"extensions": {"CompanyCode": "string"  }    }  }}

        # Extract fields from payload
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case_data:", case_data)
        
        # Extract CompanyCode
        CompanyCode = case_data.get("extensions", {}).get("CompanyCode")
        
        print("CompanyCode:", CompanyCode)

        if not CompanyCode:
            raise HTTPException(status_code=400, detail="Missing CompanyCode")
               
        # Match rows by COMPANY_CODE (trimmed) and collect MEASURE_CATE values
        matched = [
            item for item in json_result_MECA
            if item["COMPANY_CODE"] == CompanyCode
        ]
        if not matched:
            raise HTTPException(status_code=401, detail="No matched_COMPANY_CODE")
        
        print("matched:", matched)

        # Extract MeasureCate values
        MeasureCate = [item["MEASURE_CATE"] for item in matched if item["MEASURE_CATE"] is not None]

        if not MeasureCate:
            raise HTTPException(status_code=402, detail="No matched_MeasureCate")
 
        print("Matching MeasureCate:", MeasureCate)
 
        response_body = {
            "responseBody": {
                "messages": [
                    {"code": "S000", "message": "Success", "type": "INFO"}
                ],
                "value": {
                 "codes": [
                {                    
                    "key": item["MEASURE_CATE"]
                } for item in matched if "MEASURE_CATE" in item
             ] 
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
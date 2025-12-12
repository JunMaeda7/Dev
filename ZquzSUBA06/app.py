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

description= "摘要マスタと勘定科目の表示"
app = FastAPI(
    title="フォーム代入（摘要マスタ）",
    description=description,
    summary="フォーム代入（摘要マスタ）",
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


#for summary 1~6 logic
cursor.execute("select * from TBL_SUM")
rows = cursor.fetchall()

columns = [col[0] for col in cursor.description]
summary1_6 = [dict(zip(columns, row)) for row in rows]

# Change to JSON  format
summary1_6_json = json.dumps(summary1_6, ensure_ascii=False)
#print(summary1_6_json)


@app.get('/health')
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)


@app.post("/summary1")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

        ## {'requestBody': {'case': {'categoryLevel1': {'name': ''}，"caseType": "string"}}}

        # Extract fields from payload
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        if not CaseType or not category_level_1 or not TransactionDate:
            raise HTTPException(status_code=400, detail="Missing caseType Or CategoryLevel1 or TransactionDate")

        # Find matching items in Level1 based on category_level_1 and caseType
        if category_level_1== "海外":
         matching_data = [
                item for item in summary1_6
                if item.get("CASE_TYPE") == CaseType
                 and item.get("CATEGORY1") == category_level_1
                 and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            ]
        else:
             matching_data = [
                item for item in summary1_6
                if item.get("CASE_TYPE") == CaseType
                and item.get("CATEGORY1") == category_level_1
                and item.get("CATEGORY2") == category_level_2
                and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
             ]

        # Extract summary1 values
        summary1 = [item.get("SUMMARY1") for item in matching_data]
        print("Matching summary1:", summary1)

        if not summary1:
            raise HTTPException(status_code=401, detail="No matched_summary1")

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matching_data:
            val = item.get("SUMMARY1")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": key})


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


@app.post("/summary2")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract TransactionDate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
        print("summary1:", summary1)

        if not summary1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        # Normalize inputs so .strip()
        s1 = (summary1 or "").strip()

        if category_level_1== "海外":
         matched_summary2 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            ]
        else:
          matched_summary2 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            and item.get("CATEGORY2") == category_level_2
            ]
          
        # Extract summary2 values (can be None)
        summary2 = [item.get("SUMMARY2") for item in matched_summary2]
        print("Matching summary2:", summary2)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary2:
            val = item.get("SUMMARY2")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result (don't error if no matches; return empty codes)
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



@app.post("/summary3")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract TransactionDate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
        print("summary1:", summary1)
        print("summary2:", summary2)

        if not summary1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        # Normalize inputs so .strip()
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()

        if category_level_1== "海外":
         matched_summary3 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            ]        
        else:
            matched_summary3 = [
                 item for item in summary1_6_data
                if (item.get("SUMMARY1") or "").strip() == s1
                and (item.get("SUMMARY2") or "").strip() == s2
                and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
                and item.get("CASE_TYPE") == CaseType
                and item.get("CATEGORY1") == category_level_1
                and item.get("CATEGORY2") == category_level_2
                ]

        # Extract summary3 values (can be None)
        summary3 = [item.get("SUMMARY3") for item in matched_summary3]
        print("Matching summary3:", summary3)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary3:
            val = item.get("SUMMARY3")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result (don't error if no matches; return empty codes)
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



@app.post("/summary4")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract TransactionDate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)

        if not summary1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        # Normalize inputs so .strip()
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()

        if category_level_1== "海外":
         matched_summary4 = [
            item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            ]
        else:
          matched_summary4 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            and item.get("CATEGORY2") == category_level_2
            ]

        # Extract summary4 values (can be None)
        summary4 = [item.get("SUMMARY4") for item in matched_summary4]
        print("Matching summary4:", summary4)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary4:
            val = item.get("SUMMARY4")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result for all rows（even not matched data ）
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



@app.post("/summary5")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract TransactionDate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
            summary4 = item_table[0].get("F_summary4")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)
        print("summary4:", summary4)

        if not summary1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Normalize to empty string for comparisons so .strip() is safe
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()
        s4 = (summary4 or "").strip()

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)
        if category_level_1== "海外":
         matched_summary5 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            ]
        else:
          matched_summary5 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            and item.get("CATEGORY2") == category_level_2
            ]

        # Extract summary5 values (can be None)
        summary5 = [item.get("SUMMARY5") for item in matched_summary5]
        print("Matching summary5:", summary5)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary5:
            val = item.get("SUMMARY5")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
               seen.add(key)
               codes.append({"key": val})

        # return aggregated result for all rows（even not matched data ）
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


@app.post("/summary6")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract TransactionDate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        CaseType = case_data.get("caseType")
        print("caseType:", CaseType)

        TransactionDate = case_data.get("extensions", {}).get("TransactionDate")
        print("TransactionDate:", TransactionDate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
            summary4 = item_table[0].get("F_summary4")
            summary5 = item_table[0].get("F_summary5")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)
        print("summary4:", summary4)
        print("summary5:", summary5)

        if not summary1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Normalize to empty string for comparisons so .strip() is safe
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()
        s4 = (summary4 or "").strip()
        s5 = (summary5 or "").strip()

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        if category_level_1== "海外":
         matched_summary6 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            ]
        else:
          matched_summary6 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and item.get("VALID_FROM") <= TransactionDate <= item.get("VALID_TO")
            and item.get("CASE_TYPE") == CaseType
            and item.get("CATEGORY1") == category_level_1
            and item.get("CATEGORY2") == category_level_2
            ]

        # Extract summary6 values (can be None)
        summary6 = [item.get("SUMMARY6") for item in matched_summary6]
        print("Matching summary6:", summary6)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary6:
            val = item.get("SUMMARY6")
            if val is None:
                continue
            key = str(val).strip()
            if not key:
                continue
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result for all rows
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

@app.post("/AccountCode")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}
        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        summary1 = None
        summary2 = None
        summary3 = None
        summary4 = None
        summary5 = None
        summary6 = None

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
            summary4 = item_table[0].get("F_summary4")
            summary5 = item_table[0].get("F_summary5")
            summary6 = item_table[0].get("F_summary6")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)
        print("summary4:", summary4)
        print("summary5:", summary5)
        print("summary6:", summary6)

        # Normalize to empty string for comparisons so .strip() is safe
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()
        s4 = (summary4 or "").strip()
        s5 = (summary5 or "").strip()
        s6 = (summary6 or "").strip()

        if not s1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        matched_ACCOUNTCODE = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and (item.get("SUMMARY6") or "").strip() == s6
            ]

        # Extract EnterExpenses values
        ACCOUNTCODE = [item.get("ACCOUNTCODE") for item in matched_ACCOUNTCODE]
        print("Matching ACCOUNTCODE:", ACCOUNTCODE)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_ACCOUNTCODE:
            val = item.get("ACCOUNTCODE")
            if val is None:
                continue
            key = str(val).strip()
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result for all rows
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


@app.post("/EnterExpenses")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}
        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        summary1 = None
        summary2 = None
        summary3 = None
        summary4 = None
        summary5 = None
        summary6 = None

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
            summary4 = item_table[0].get("F_summary4")
            summary5 = item_table[0].get("F_summary5")
            summary6 = item_table[0].get("F_summary6")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)
        print("summary4:", summary4)
        print("summary5:", summary5)
        print("summary6:", summary6)

        # Normalize to empty string for comparisons so .strip() is safe
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()
        s4 = (summary4 or "").strip()
        s5 = (summary5 or "").strip()
        s6 = (summary6 or "").strip()

        if not s1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        matched_EnterExpenses = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and (item.get("SUMMARY6") or "").strip() == s6
            ]

        # Extract EnterExpenses values
        EnterExpenses = [item.get("ENTER_EXPENSES") for item in matched_EnterExpenses]
        print("Matching EnterExpenses:", EnterExpenses)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_EnterExpenses:
            val = item.get("ENTER_EXPENSES")
            if val is None:
                continue
            key = str(val).strip()
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result for all rows
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


@app.post("/Research")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}
        # Extract summary1 from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        summary1 = None
        summary2 = None
        summary3 = None
        summary4 = None
        summary5 = None
        summary6 = None

        if item_table and isinstance(item_table, list):
            summary1 = item_table[0].get("F_summary1")
            summary2 = item_table[0].get("F_summary2")
            summary3 = item_table[0].get("F_summary3")
            summary4 = item_table[0].get("F_summary4")
            summary5 = item_table[0].get("F_summary5")
            summary6 = item_table[0].get("F_summary6")
        print("summary1:", summary1)
        print("summary2:", summary2)
        print("summary3:", summary3)
        print("summary4:", summary4)
        print("summary5:", summary5)
        print("summary6:", summary6)

        # Normalize to empty string for comparisons so .strip() is safe
        s1 = (summary1 or "").strip()
        s2 = (summary2 or "").strip()
        s3 = (summary3 or "").strip()
        s4 = (summary4 or "").strip()
        s5 = (summary5 or "").strip()
        s6 = (summary6 or "").strip()

        if not s1:
            raise HTTPException(status_code=400, detail="Missing field_summary1")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        matched_Research = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and (item.get("SUMMARY6") or "").strip() == s6
            ]

        # Extract Research values
        Research = [item.get("RESEARCH") for item in matched_Research]
        print("Matching Research:", Research)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_Research:
            val = item.get("RESEARCH")
            if val is None:
                continue
            key = str(val).strip()
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

        # return aggregated result for all rows
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

@app.post("/DocCurrAmt")
async def req(request: Request):
    try:
        json_body = await request.json()
        form_data = json_body.get("requestBody", {}).get("Form", {})
        item_table = form_data.get("F_meisai", [])

        form_error_messages = []

        # Case 1: No rows in item_table → treat as validation error
        if not item_table or not isinstance(item_table, list):
            form_error_messages.append("item_table has no value.")
        else:
            summary1_6_data = json.loads(summary1_6_json)

            # Case 2: Validate each row
            for index, item in enumerate(item_table):
                try:
                    summary1 = (item.get("F_summary1") or "").strip()
                    summary2 = (item.get("F_summary2") or "").strip()
                    summary3 = (item.get("F_summary3") or "").strip()
                    summary4 = (item.get("F_summary4") or "").strip()
                    summary5 = (item.get("F_summary5") or "").strip()
                    summary6 = (item.get("F_summary6") or "").strip()
                    AC = (item.get("F_Account_Code") or "").strip()
                    EE = (item.get("F_Enter_expenses") or "").strip()
                    DocCurrAmt = item.get("F_Doc_curr_amt")
                    TaxAmount = item.get("F_Tax_amount")
                    Quantity = item.get("F_Quantity")

                    print(f"[Row {index + 1}] AC:", AC)
                    print(f"[Row {index + 1}] EE:", EE)
                    print(f"[Row {index + 1}] DocCurrAmt:", DocCurrAmt)
                    print(f"[Row {index + 1}] Quantity:", Quantity)
                    print(f"[Row {index + 1}] TaxAmount:", TaxAmount)
                    print(f"[Row {index + 1}] summary1-6:", summary1, summary2, summary3, summary4, summary5, summary6)
           
                    if not AC:
                        form_error_messages.append(
                            f"Row {index + 1}: Missing AccountCode."
                        )
                        continue

                    matched_AMOUNT = [
                        row for row in summary1_6_data
                        if (row.get("ACCOUNTCODE") or "").strip() == AC
                        and (row.get("ENTER_EXPENSES") or "").strip() == EE
                        and (row.get("SUMMARY1") or "").strip() == summary1
                        and (row.get("SUMMARY2") or "").strip() == summary2
                        and (row.get("SUMMARY3") or "").strip() == summary3
                        and (row.get("SUMMARY4") or "").strip() == summary4
                        and (row.get("SUMMARY5") or "").strip() == summary5
                        and (row.get("SUMMARY6") or "").strip() == summary6
                    ]

                    if not matched_AMOUNT:
                        form_error_messages.append(
                            f"Row {index + 1}: 金額範囲が特定できません(摘要内容および交際費区分をご確認ください)")
                        continue

                    min_val = float(matched_AMOUNT[0].get("MIN_AMOUNT"))
                    max_val = float(matched_AMOUNT[0].get("MAX_AMOUNT"))
                    doc_val = float(DocCurrAmt)
                    qty_val = float(Quantity)
                    tax_val = (
                        float(TaxAmount)
                        if (TaxAmount is not None and str(TaxAmount).strip() != "")
                        else 0.0
                    )

                    check_amount = (doc_val - tax_val) / qty_val

                    if not (min_val <= check_amount <= max_val):
                        form_error_messages.append(
                            f"Row {index + 1}: (伝票通貨額 - 税額) / 数量 = {check_amount} "
                            f"is out of allowed range ({min_val} - {max_val})."
                        )

                except Exception:
                    form_error_messages.append(
                        f"Row {index + 1}: 伝票通貨額／数量／税額 に不正な数値が入力されています。"
                    )

        # Case 3: If any validation errors exist
        if form_error_messages:
            final_error_msg = "\n".join(form_error_messages)
            response_body = {
                "responseBody": {
                    "messages": [],
                    "value": {
                        "Form": {
                            "F_FormErrorCheck": False,
                            "F_FormErrorMsg": final_error_msg
                        }
                    },
                    "isSuccess": True
                }
            }
            return JSONResponse(content=response_body)

        # Case 4: no error anywhere → user corrected everything → CLEAR previous error
        response_body = {
            "responseBody": {
                "messages": [],
                "value": {
                    "Form": {
                        "F_FormErrorCheck": True,
                        "F_FormErrorMsg": "エラーなし"     # clear previous errors
                    }
                },
                "isSuccess": True
            }
        }
        return JSONResponse(content=response_body)

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )

@app.post("/DomeCurrAmtOth")
async def req(request: Request):
    try:
        # Step 1: Parse JSON payload from the request
        json_body = await request.json()
        print("Received payload:", json_body)

        # Step 2: Extract Form data and item table (F_meisai) from the request body
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        # Step 3: Prepare a list to collect validation error messages for all rows
        form_error_messages = []

        # Step 4: Basic validation - if item_table is empty or not a list, treat as validation error
        if not item_table or not isinstance(item_table, list):
            form_error_messages.append("item_table has no value.")
        else:
            # Step 5: Load reference data for summary1–summary6 / account / expenses / min-max settings
            summary1_6_data = json.loads(summary1_6_json)

            # Step 6: Validate each row in the item_table one by one
            for index, item in enumerate(item_table):
                try:
                    # Step 6-1: Safely read and normalize summary1–summary6 for this row
                    summary1 = (item.get("F_summary1") or "").strip()
                    summary2 = (item.get("F_summary2") or "").strip()
                    summary3 = (item.get("F_summary3") or "").strip()
                    summary4 = (item.get("F_summary4") or "").strip()
                    summary5 = (item.get("F_summary5") or "").strip()
                    summary6 = (item.get("F_summary6") or "").strip()

                    # Step 6-2: Safely read and normalize account code and enter expenses
                    AC = (item.get("F_Account_Code") or "").strip()
                    EE = (item.get("F_Enter_expenses") or "").strip()

                    # Step 6-3: Read numeric fields for current row
                    DomeAmt = item.get("F_Dome_curr_amt")
                    Quantity = item.get("F_Quantity")

                    print(f"[Row {index + 1}] AC:", AC)
                    print(f"[Row {index + 1}] EE:", EE)
                    print(f"[Row {index + 1}] DomeAmt:", DomeAmt)
                    print(f"[Row {index + 1}] Quantity:", Quantity)
                    print(f"[Row {index + 1}] summary1-6:", summary1, summary2, summary3, summary4, summary5, summary6)

                    # Step 6-4: If account code is missing, treat as validation error for this row
                    if not AC:
                        form_error_messages.append(
                            f"Row {index + 1}: Missing AccountCode."
                        )
                        continue

                    # Step 6-5: Find matched setting row from reference data by AC/EE/summary1–6
                    matched_AMOUNT = [
                        ref for ref in summary1_6_data
                        if (ref.get("ACCOUNTCODE") or "").strip() == AC
                        and (ref.get("ENTER_EXPENSES") or "").strip() == EE
                        and (ref.get("SUMMARY1") or "").strip() == summary1
                        and (ref.get("SUMMARY2") or "").strip() == summary2
                        and (ref.get("SUMMARY3") or "").strip() == summary3
                        and (ref.get("SUMMARY4") or "").strip() == summary4
                        and (ref.get("SUMMARY5") or "").strip() == summary5
                        and (ref.get("SUMMARY6") or "").strip() == summary6
                    ]

                    # Step 6-6: If no settings found for this row, record an error and skip to next row
                    if not matched_AMOUNT:
                        form_error_messages.append(
                            f"Row {index + 1}: 金額範囲が特定できません(摘要内容および交際費区分をご確認ください)"
                        )
                        continue

                    # Step 6-7: Extract min and max amount from the first matched setting
                    min_val = float(matched_AMOUNT[0].get("MIN_AMOUNT"))
                    max_val = float(matched_AMOUNT[0].get("MAX_AMOUNT"))
                    print(f"[Row {index + 1}] Matching MIN:", min_val)
                    print(f"[Row {index + 1}] Matching MAX:", max_val)

                    # Step 6-8: Convert Dome amount and quantity to float for calculation
                    Dome_val = float(DomeAmt)
                    quantity_val = float(Quantity)

                    # Step 6-9: Keep the original calculation logic: Dome / Quantity
                    check_amount = Dome_val / quantity_val
                    print(f"[Row {index + 1}] Check amount (Dome/Qty):", check_amount)

                    # Step 6-10: Check if calculated amount is within the allowed range
                    if not (min_val <= check_amount <= max_val):
                        error_msg = (
                            f"Row {index + 1}: 国内通貨額/数量= {check_amount} "
                            f"is out of allowed range ({min_val} - {max_val})."
                        )
                        form_error_messages.append(error_msg)

                except Exception:
                    # Step 6-11: If any conversion or calculation error occurs, mark this row as invalid
                    form_error_messages.append(
                        f"Row {index + 1}: 国内通貨額／数量に不正な数値が入力されています"
                    )

        # Step 7: If there is any validation error in any row, return aggregated errors
        if form_error_messages:
            # Step 7-1: Join all row error messages into a single text
            final_error_msg = "\n".join(form_error_messages)

            # Step 7-2: Return error response with F_CHECK_flg = False and F_FormErrorMsg
            response_body = {
                "responseBody": {
                    "messages": [],
                    "value": {
                        "Form": {
                            # Business check flag for the screen (unchecked when error exists)
                            "F_FormErrorCheck": False,
                            # Aggregated error message for the screen
                            "F_FormErrorMsg": final_error_msg
                        }
                    },
                    "isSuccess": True
                }
            }
            return JSONResponse(content=response_body)

        # Step 8: If no validation error exists in any row, return success response
        #         with F_CHECK_flg = True and clear previous error message.
        response_body = {
            "responseBody": {
                "messages": [],
                "value": {
                    "Form": {
                        "F_FormErrorCheck": True,
                        "F_FormErrorMsg": "エラーなし"
                    }
                },
                "isSuccess": True
            }
        }
        return JSONResponse(content=response_body)

    except HTTPException as http_ex:
        # Step 9: Re-raise HTTPException so that FastAPI can handle it properly
        raise http_ex
    except Exception as ex:
        # Step 10: Catch unexpected errors and return as 500 Internal Server Error
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=cf_port, log_level="info")
    print('Prehook started....')
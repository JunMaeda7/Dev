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

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

        category_level_1 = case_data.get("categoryLevel1", {}).get("name")
        print("CategoryLevel1:", category_level_1)

        category_level_2 = case_data.get("categoryLevel2", {}).get("name")
        print("CategoryLevel2:", category_level_2)

        if not CaseType or not category_level_1 or not Postingdate:
            raise HTTPException(status_code=400, detail="Missing caseType Or CategoryLevel1 or Postingdate")

        # Find matching items in Level1 based on category_level_1 and caseType
        if category_level_1== "海外":
         matching_data = [
                item for item in summary1_6
                if item.get("CASE_TYPE") == CaseType
                 and item.get("CATEGORY1") == category_level_1
                 and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
            ]
        else:
             matching_data = [
                item for item in summary1_6
                if item.get("CASE_TYPE") == CaseType
                and item.get("CATEGORY1") == category_level_1
                and item.get("CATEGORY2") == category_level_2
                and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
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

        # Extract Postingdate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

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

        matched_summary2 = [
             item for item in summary1_6_data
            if item["SUMMARY1"].strip() == summary1.strip()
            and item["VALID_FROM"] <= Postingdate <= item["VALID_TO"]
           ]

        # Extract summary2 values
        summary2 = [item["SUMMARY2"] for item in matched_summary2]
        print("Matching summary2:", summary2)

        # Remove duplicates while preserving order
        seen = set()
        codes = []
        for item in matched_summary2:
            if "SUMMARY2" in item:
             val = item["SUMMARY2"]
            if val is None:
                continue
            key = val.strip()
            if key not in seen:
                seen.add(key)
                codes.append({"key": val})

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



@app.post("/summary3")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }}

        # Extract Postingdate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

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

        matched_summary3 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
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

        # Extract Postingdate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

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

        matched_summary4 = [
            item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
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

        # Extract Postingdate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

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

        matched_summary5 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
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

        # Extract Postingdate from the case
        case_data = json_body.get("requestBody", {}).get("case", {})
        print("case Data:", case_data)

        Postingdate = case_data.get("extensions", {}).get("Postingdate")
        print("Postingdate:", Postingdate)

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

        matched_summary6 = [
             item for item in summary1_6_data
            if (item.get("SUMMARY1") or "").strip() == s1
            and (item.get("SUMMARY2") or "").strip() == s2
            and (item.get("SUMMARY3") or "").strip() == s3
            and (item.get("SUMMARY4") or "").strip() == s4
            and (item.get("SUMMARY5") or "").strip() == s5
            and item.get("VALID_FROM") <= Postingdate <= item.get("VALID_TO")
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
        print("Received payload:", json_body)

## "requestBody": {"Form": {"F_meisai": [{"F_summary1":}  ]} }"}
        # Extract Account_Code、Doc_curr_amt from the ItemTable in Form
        form_data = json_body.get("requestBody", {}).get("Form", {})
        print("form_data:", form_data)

        Resolution = form_data.get("F_Resolution", {})
        print("Resolution:", Resolution)

        item_table = form_data.get("F_meisai", [])
        print("item_table:", item_table)

        AccountCode = None
        EnterExpenses = None
        DocCurrAmt = None

        if item_table and isinstance(item_table, list):
            AccountCode = item_table[0].get("F_Account_Code")
            EnterExpenses = item_table[0].get("F_Enter_expenses")
            DocCurrAmt = item_table[0].get("F_Doc_curr_amt")
        print("AccountCode:", AccountCode)
        print("EnterExpenses:", EnterExpenses)
        print("DocCurrAmt:", DocCurrAmt)

        # Normalize to empty string for comparisons so .strip() is safe
        AC = (AccountCode or "").strip()
        EE = (EnterExpenses or "").strip()
        if not AC or not EE:
            raise HTTPException(status_code=400, detail="Missing field_AccountCode Or EnterExpenses")

        # Parse summary1_6_json back into a Python object
        summary1_6_data = json.loads(summary1_6_json)

        matched_AMOUNT = [
             item for item in summary1_6_data
              if (item.get("ACCOUNTCODE") or "").strip() == AC
              and (item.get("ENTER_EXPENSES") or "").strip() == EE
           ]

        # Extract MIN_AMOUNT、MAX_AMOUNT values
        MAX = [item.get("MAX_AMOUNT") for item in matched_AMOUNT]
        MIN = [item.get("MIN_AMOUNT") for item in matched_AMOUNT]
        print("Matching MIN:", MIN)
        print("Matching MAX:", MAX)

        if not MAX or not MIN:
            raise HTTPException(status_code=401, detail="No matched_AMOUNT")

        try:
            doc_val = float(DocCurrAmt)
            min_val = float(MIN[0])
            max_val = float(MAX[0])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid numeric value for DocCurrAmt or MIN/MAX")

            # check inclusive range
        if not (min_val <= doc_val <= max_val):
            response_body = {
                "responseBody": {
                    "messages": [
                        {
                            "code": "E001",
                            "message": f"DocCurrAmt {DocCurrAmt} is out of allowed range ({min_val} - {max_val}).",
                            "type": "ERROR"
                        }
                    ],
                    "value": {
                        "Form": {
                            "F_meisai": [
                                {
                                    "F_Doc_curr_amt": DocCurrAmt
                                }
                            ]
                        }
                    },
                    "isSuccess": False
                }
            }
            return JSONResponse(content=response_body)
        else:
           # amount is within range — no action needed


            # return None

        #     response_body = {
        #      "responseBody": {
        #         "messages": [
        #             {
        #                 "code": "S000",
        #                 "message": "Success",
        #                 "type": "INFO"
        #             }
        #         ],
        #         "value": {
        #             "Form": {
        #                 "F_meisai": [
        #                     {
        #                         "F_Doc_curr_amt": DocCurrAmt

        #                     }
        #                 ]
        #             }
        #         },
        #         "isSuccess": True
        #     }
        # }
        # return JSONResponse(content=response_body)
 
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
                    "Form":  {
                        "F_Resolution": Resolution
                                }
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
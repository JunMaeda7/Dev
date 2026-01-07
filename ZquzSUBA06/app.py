from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import requests
import uvicorn
import os
import httpx
import asyncio
import re
import json
from fastapi import FastAPI, Query
from typing import List, Optional
from pydantic import BaseModel
from hdbcli import dbapi
from datetime import datetime, date

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


# ------------------------------------
# Helper: parse date in multiple formats
# ------------------------------------
def parse_any_date(value) -> date | None:
    """
    Accepts:
      - 'YYYY-MM-DD'   e.g. 2025-12-21
      - 'YYYY/MM/DD'   e.g. 2025/12/21
      - 'DD-MM-YYYY'   e.g. 21-12-2025
      - 'DD/MM/YYYY'   e.g. 21/12/2025
      - Also tolerates time suffix like '2025-12-21T00:00:00' or '2025-12-21 00:00:00'
      - datetime/date objects
    Returns:
      - datetime.date or None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    s = str(value).strip()
    if not s:
        return None

    # Keep only the date part if time is included
    s_date = re.split(r"[T\s]", s, maxsplit=1)[0].strip()

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s_date, fmt).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported date format: {s}")


# ------------------------------------
# Helper: build response in unified schema
# ------------------------------------
def build_response(is_success: bool, message: str, msg_type: str = "INFO", code: str = "S000", codes=None):
    if codes is None:
        codes = []

    return {
        "responseBody": {
            "messages": [
                {
                    "code": code,
                    "message": message,
                    "type": msg_type
                }
            ],
            "value": {
                "codes": codes
            },
            "isSuccess": is_success
        }
    }


@app.post("/summary1")
async def req(request: Request):
    try:
        # ------------------------------------
        # 1) Extract payload
        # ------------------------------------
        json_body = await request.json()
        print("Received payload:", json_body)

        # ------------------------------------
        # 2) Extract case data
        # ------------------------------------
        case_data = (json_body.get("requestBody") or {}).get("case") or {}
        print("case_data:", case_data)

        # ------------------------------------
        # 3) Extract fields (safe get + strip)
        # ------------------------------------
        case_type = (case_data.get("caseType") or "").strip()
        print("caseType:", case_type)

        transaction_date_raw = ((case_data.get("extensions") or {}).get("TransactionDate") or "").strip()
        print("TransactionDate(raw):", transaction_date_raw)

        category_level_1 = (((case_data.get("categoryLevel1") or {}).get("name")) or "").strip()
        print("CategoryLevel1:", category_level_1)

        category_level_2 = (((case_data.get("categoryLevel2") or {}).get("name")) or "").strip()
        print("CategoryLevel2:", category_level_2)

        # ------------------------------------
        # 4) Mandatory checks (header-level)
        #    - Return error in responseBody.messages (NO HTTP error)
        # ------------------------------------
        if not case_type or not category_level_1 or not transaction_date_raw:
            resp = build_response(
                is_success=False,
                msg_type="INFO",
                code="E400",
                message="Missing required fields: caseType / category / TransactionDate",
                codes=[]
            )
            return JSONResponse(content=resp)

        # ------------------------------------
        # 5) Parse TransactionDate to date
        # ------------------------------------
        try:
            transaction_date = parse_any_date(transaction_date_raw)
        except ValueError:
            resp = build_response(
                is_success=False,
                msg_type="INFO",
                code="E400",
                message=f"Invalid TransactionDate format: {transaction_date_raw}.",
                codes=[]
            )
            return JSONResponse(content=resp)

        # ------------------------------------
        # 6) Determine rule: overseas vs non-overseas
        #    - Overseas/海外/収入金計上: CATEGORY2 is NOT required
        #    - Non-overseas: CATEGORY2 is REQUIRED
        # ------------------------------------
        only_Cat1 = category_level_1 in {"海外", "Overseas", "収入金計上"}

        if not only_Cat1 and not category_level_2:
            resp = build_response(
                is_success=False,
                msg_type="INFO",
                code="E400",
                message="Please select Category Level2.",
                codes=[]
            )
            return JSONResponse(content=resp)

        # ------------------------------------
        # 7) Find matching items in summary1_6 master
        #    - Compare dates as date objects (handle 'YYYY/MM/DD' in DB)
        # ------------------------------------
        matching_data = []
        for item in summary1_6:
            if (item.get("CASE_TYPE") or "").strip() != case_type:
                continue
            if (item.get("CATEGORY1") or "").strip() != category_level_1:
                continue
            if not only_Cat1 and (item.get("CATEGORY2") or "").strip() != category_level_2:
                continue

            # Parse VALID_FROM/VALID_TO (DB might be 'YYYY/MM/DD')
            try:
                valid_from = parse_any_date(item.get("VALID_FROM"))
                valid_to = parse_any_date(item.get("VALID_TO"))
            except ValueError:
                # master row has unexpected format -> skip this row safely
                continue

            if valid_from is None or valid_to is None:
                continue

            if valid_from <= transaction_date <= valid_to:
                matching_data.append(item)

        print("matching_data count:", len(matching_data))

        # ------------------------------------
        # 8) Build codes list (unique SUMMARY1, preserve order)
        # ------------------------------------
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

        print("Matching summary1 codes:", codes)

        # ------------------------------------
        # 9) No match handling (return error in messages, NO HTTP error)
        # ------------------------------------
        if not codes:
            resp = build_response(
                is_success=False,
                msg_type="INFO",
                code="E404",
                message="No matched SUMMARY1. Please check Category / TransactionDate",
                codes=[]
            )
            return JSONResponse(content=resp)

        # ------------------------------------
        # 10) Success response
        # ------------------------------------
        resp = build_response(
            is_success=True,
            msg_type="INFO",
            code="S000",
            message="Success",
            codes=codes
        )
        return JSONResponse(content=resp)

    except Exception as ex:
        # ------------------------------------
        # 11) Unexpected errors (also return in messages, NO HTTP error)
        # ------------------------------------
        resp = build_response(
            is_success=False,
            msg_type="ERROR",
            code="E500",
            message=f"Internal Server Error: {str(ex)}",
            codes=[]
        )
        return JSONResponse(content=resp)



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
        # --------------------------------------------------------
        # 1) Extract payload
        # --------------------------------------------------------
        json_body = await request.json()
        form_data = json_body.get("requestBody", {}).get("Form", {})
        item_table = form_data.get("F_meisai", [])

        # Header-level fields
        settlement1 = (form_data.get("F_settlement1") or "").strip()
        settlement2 = (form_data.get("F_settlement2") or "").strip()
        settlement3 = (form_data.get("F_settlement3") or "").strip()
        invoice_no  = (form_data.get("F_Invoice_number") or "").strip()
        total_amount_c = form_data.get("F_Total_Amount_C")

        form_error_messages = []

        # --------------------------------------------------------
        # 2) Helper functions
        # --------------------------------------------------------
        FORBIDDEN_CHARS = set(['"', "'", '\\', '/', '<', '>', '|', ':', '*', '?', '、'])

        def has_fullwidth(s: str) -> bool:
            if not s:
                return False
            return any(ord(ch) > 0x7E for ch in s)

        def has_forbidden_chars(s: str) -> bool:
            if not s:
                return False
            return any(ch in FORBIDDEN_CHARS for ch in s)

        def validate_text_field(value: str, field_label: str):
            if has_fullwidth(value):
                form_error_messages.append(f"{field_label} に全角文字が含まれています。")
            if has_forbidden_chars(value):
                form_error_messages.append(f"{field_label} に禁則文字が含まれています。")

        # ---- half-width integer only (no decimal, no negative) ----
        HALF_WIDTH_INT_RE = re.compile(r"^[0-9]+$")

        def is_halfwidth_integer(v) -> bool:
            """
            True if empty OR half-width integer only.
            """
            if v is None:
                return True
            s = str(v).strip()
            if s == "":
                return True
            if has_fullwidth(s):
                return False
            return bool(HALF_WIDTH_INT_RE.match(s))

        # --------------------------------------------------------
        # 3) Validate header text fields
        # --------------------------------------------------------
        validate_text_field(settlement1, "決済番号1")
        validate_text_field(settlement2, "決済番号2")
        validate_text_field(settlement3, "決済番号3")
        validate_text_field(invoice_no, "請求書番号")

         # --------------------------------------------------------
        # 3.5) Validate numeric fields 
        #      - F_Total_Amount_C
        #      - DocCurrAmt / Quantity in each row
        #      - Quantity is REQUIRED and must be >= 1
        #      - DocCurrAmt is REQUIRED
        # --------------------------------------------------------
        rows_with_numeric_error = set()

        def is_empty(v) -> bool:
            return v is None or str(v).strip() == ""

        # ---- Header: 合計金額 ----
        if not is_halfwidth_integer(total_amount_c):
            form_error_messages.append(
                "合計金額 は半角整数で入力してください。"
            )

        # ---- Item table ----
        if item_table and isinstance(item_table, list):
            for index, item in enumerate(item_table):
                DocCurrAmt = item.get("F_Doc_curr_Amt")
                Quantity  = item.get("F_Quantity_1")

                doc_empty = is_empty(DocCurrAmt)
                qty_empty = is_empty(Quantity)

                # 1) Quantity is REQUIRED
                if qty_empty:
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は必須項目です。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # 2) Half-width integer check
                if not is_halfwidth_integer(Quantity):
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                if not doc_empty and not is_halfwidth_integer(DocCurrAmt):
                    form_error_messages.append(
                        f"Row {index + 1}: 伝票通貨額 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # 3) Quantity >= 1
                try:
                    qty_val = int(str(Quantity).strip())
                    if qty_val < 1:
                        form_error_messages.append(
                            f"Row {index + 1}: 数量 は1以上で入力してください。"
                        )
                        rows_with_numeric_error.add(index)
                        continue
                except Exception:
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # 4) DocCurrAmt must be entered
                if doc_empty:
                    form_error_messages.append(
                        f"Row {index + 1}: 伝票通貨額 は必須です。"
                    )
                    rows_with_numeric_error.add(index)

        # --------------------------------------------------------
        # 4) Load summary1–6 mapping data
        # --------------------------------------------------------
        summary1_6_data = json.loads(summary1_6_json)

        # --------------------------------------------------------
        # 5) Validate each row in F_meisai
        # --------------------------------------------------------
        if item_table and isinstance(item_table, list):
            for index, item in enumerate(item_table):

                # Skip rows with numeric format error
                if index in rows_with_numeric_error:
                    continue

                # --------------------------------------------------------
                # 5-1) Extract fields
                # --------------------------------------------------------
                summary1 = (item.get("F_summary1") or "").strip()
                summary2 = (item.get("F_summary2") or "").strip()
                summary3 = (item.get("F_summary3") or "").strip()
                summary4 = (item.get("F_summary4") or "").strip()
                summary5 = (item.get("F_summary5") or "").strip()
                summary6 = (item.get("F_summary6") or "").strip()

                AC = (item.get("F_Account_Code") or "").strip()
                EE = (item.get("F_Enter_expenses") or "").strip()

                DocCurrAmt = item.get("F_Doc_curr_Amt")
                TaxAmount = item.get("F_Tax_amount")
                Quantity = item.get("F_Quantity_1")

                # --------------------------------------------------------
                # 5-2) Missing AccountCode
                # --------------------------------------------------------
                if not AC:
                    form_error_messages.append(
                        f"Row {index + 1}: Missing AccountCode"
                    )
                    continue

                # --------------------------------------------------------
                # 5-3) Match Summary1–6 + AC + EE
                # --------------------------------------------------------
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
                        f"Row {index + 1}: 金額範囲が特定できません(摘要内容および交際費区分をご確認ください)"
                    )
                    continue

                # --------------------------------------------------------
                # 5-4) Amount range check
                # --------------------------------------------------------
                if DocCurrAmt in (None, "") or Quantity in (None, ""):
                    continue

                try:
                    min_val = float(matched_AMOUNT[0].get("MIN_AMOUNT"))
                    max_val = float(matched_AMOUNT[0].get("MAX_AMOUNT"))

                    doc_val = float(DocCurrAmt)
                    qty_val = float(Quantity)
                    tax_val = (
                        float(TaxAmount)
                        if (TaxAmount is not None and str(TaxAmount).strip() != "")
                        else 0.0
                    )

                    if qty_val == 0:
                        form_error_messages.append(
                            f"Row {index + 1}: 伝票通貨額／数量／税額 に不正な数値が入力されています。"
                        )
                        continue

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

        # --------------------------------------------------------
        # 6) No detail rows
        # --------------------------------------------------------
        if not item_table:
            form_error_messages.append("明細なし")

        # --------------------------------------------------------
        # 7) Return errors
        # --------------------------------------------------------
        if form_error_messages:
            response_body = {
                "responseBody": {
                    "messages": [],
                    "value": {
                        "Form": {
                            "F_FormErrorCheck": False,
                            "F_FormErrorMsg": "\n".join(form_error_messages)
                        }
                    },
                    "isSuccess": True
                }
            }
            return JSONResponse(content=response_body)

        # --------------------------------------------------------
        # 8) No errors
        # --------------------------------------------------------
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
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )


@app.post("/DomeCurrAmtOth")
async def req(request: Request):
    try:
        # --------------------------------------------------------
        # 1) Extract payload
        # --------------------------------------------------------
        json_body = await request.json()
        form_data = json_body.get("requestBody", {}).get("Form", {})
        item_table = form_data.get("F_meisai", [])

        # --------------------------------------------------------
        # 1.1) Header-level fields
        # --------------------------------------------------------
        settlement1 = (form_data.get("F_settlement1") or "").strip()
        settlement2 = (form_data.get("F_settlement2") or "").strip()
        settlement3 = (form_data.get("F_settlement3") or "").strip()
        invoice_no  = (form_data.get("F_Invoice_number") or "").strip()
        total_amount_c = form_data.get("F_Total_Amount_C")

        form_error_messages = []

        # --------------------------------------------------------
        # 2) Helper functions
        # --------------------------------------------------------
        FORBIDDEN_CHARS = set(['"', "'", '\\', '/', '<', '>', '|', ':', '*', '?', '、'])

        def has_fullwidth(s: str) -> bool:
            if not s:
                return False
            return any(ord(ch) > 0x7E for ch in s)

        def has_forbidden_chars(s: str) -> bool:
            if not s:
                return False
            return any(ch in FORBIDDEN_CHARS for ch in s)

        def validate_text_field(value: str, field_label: str):
            if has_fullwidth(value):
                form_error_messages.append(
                    f"{field_label} に全角文字が含まれています。"
                )
            if has_forbidden_chars(value):
                form_error_messages.append(
                    f"{field_label} に禁則文字が含まれています。"
                )

        HALF_WIDTH_INT_RE = re.compile(r"^[0-9]+$")

        def is_halfwidth_integer(v) -> bool:
            if v is None:
                return True
            s = str(v).strip()
            if s == "":
                return True
            if has_fullwidth(s):
                return False
            return bool(HALF_WIDTH_INT_RE.match(s))

        def is_empty(v) -> bool:
            return v is None or str(v).strip() == ""

        # --------------------------------------------------------
        # 3) Validate header text fields
        # --------------------------------------------------------
        validate_text_field(settlement1, "決済番号1")
        validate_text_field(settlement2, "決済番号2")
        validate_text_field(settlement3, "決済番号3")
        validate_text_field(invoice_no,  "請求書番号")

        # --------------------------------------------------------
        # 3.5) Validate numeric fields
        #      - F_Total_Amount_C
        #      - F_Doc_curr_Amt / F_Quantity_1
        #      - Quantity is REQUIRED and must be >= 1
        #      - DocCurrAmt is REQUIRED
        # --------------------------------------------------------
        rows_with_numeric_error = set()

        # ---- Header: 合計金額 ----
        if not is_halfwidth_integer(total_amount_c):
            form_error_messages.append(
                "合計金額 は半角整数で入力してください。"
            )

        # ---- Item table numeric validation ----
        if item_table and isinstance(item_table, list):
            for index, item in enumerate(item_table):
                DocCurrAmt = item.get("F_Doc_curr_Amt")
                Quantity   = item.get("F_Quantity_1")

                doc_empty = is_empty(DocCurrAmt)
                qty_empty = is_empty(Quantity)

                # Quantity required
                if qty_empty:
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は必須項目です。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # Quantity half-width integer
                if not is_halfwidth_integer(Quantity):
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # Quantity >= 1
                try:
                    qty_val = int(str(Quantity).strip())
                    if qty_val < 1:
                        form_error_messages.append(
                            f"Row {index + 1}: 数量 は1以上で入力してください。"
                        )
                        rows_with_numeric_error.add(index)
                        continue
                except Exception:
                    form_error_messages.append(
                        f"Row {index + 1}: 数量 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # DocCurrAmt required
                if doc_empty:
                    form_error_messages.append(
                        f"Row {index + 1}: 伝票通貨額 は必須です。"
                    )
                    rows_with_numeric_error.add(index)
                    continue

                # DocCurrAmt half-width integer
                if not is_halfwidth_integer(DocCurrAmt):
                    form_error_messages.append(
                        f"Row {index + 1}: 伝票通貨額 は半角整数で入力してください。"
                    )
                    rows_with_numeric_error.add(index)

        # --------------------------------------------------------
        # 4) Load reference data
        # --------------------------------------------------------
        summary1_6_data = json.loads(summary1_6_json)

        # --------------------------------------------------------
        # 5) Validate each row (amount range check)
        # --------------------------------------------------------
        if item_table and isinstance(item_table, list):
            for index, item in enumerate(item_table):

                if index in rows_with_numeric_error:
                    continue
                try:
                    summary1 = (item.get("F_summary1") or "").strip()
                    summary2 = (item.get("F_summary2") or "").strip()
                    summary3 = (item.get("F_summary3") or "").strip()
                    summary4 = (item.get("F_summary4") or "").strip()
                    summary5 = (item.get("F_summary5") or "").strip()
                    summary6 = (item.get("F_summary6") or "").strip()

                    AC = (item.get("F_Account_Code") or "").strip()
                    EE = (item.get("F_Enter_expenses") or "").strip()

                    DomeAmt  = item.get("F_Dome_curr_amt")
                    Quantity = item.get("F_Quantity_1")

                    if not AC:
                        form_error_messages.append(
                            f"Row {index + 1}: Missing AccountCode."
                        )
                        continue
                    
                    print(
                        f"[Row {index + 1}] "
                        f"AC={AC}, EE={EE}, "
                        f"S1~S6={[summary1, summary2, summary3, summary4, summary5, summary6]}, "
                        f" DomeAmt={DomeAmt}, Qty={Quantity}"
                    )

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

                    if not matched_AMOUNT:
                        form_error_messages.append(
                            f"Row {index + 1}: 金額範囲が特定できません(摘要内容および交際費区分をご確認ください)"
                        )
                        continue

                    min_val = float(matched_AMOUNT[0].get("MIN_AMOUNT"))
                    max_val = float(matched_AMOUNT[0].get("MAX_AMOUNT"))

                    dome_val = float(DomeAmt)
                    qty_val  = float(Quantity)

                    check_amount = dome_val / qty_val

                    if not (min_val <= check_amount <= max_val):
                        form_error_messages.append(
                            f"Row {index + 1}: 国内通貨額/数量 = {check_amount} "
                            f"is out of allowed range ({min_val} - {max_val})."
                            )

                    print(
                        f"[Row {index + 1}] "
                        f"DomeAmt={dome_val}, Qty={qty_val}, "
                        f"CheckAmt={check_amount}, "
                        f"Range=({min_val}-{max_val})"
                        )
                except Exception:
                    form_error_messages.append(
                    f"Row {index + 1}: 国内通貨額／数量には正しい数値を入力してください。"
                )

        # --------------------------------------------------------
        # 6) No detail rows
        # --------------------------------------------------------
        if not item_table:
            form_error_messages.append("明細なし")

        # --------------------------------------------------------
        # 7) Return result
        # --------------------------------------------------------
        if form_error_messages:
            return JSONResponse(
                content={
                    "responseBody": {
                        "messages": [],
                        "value": {
                            "Form": {
                                "F_FormErrorCheck": False,
                                "F_FormErrorMsg": "\n".join(form_error_messages)
                            }
                        },
                        "isSuccess": True
                    }
                }
            )

        return JSONResponse(
            content={
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
        )

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=cf_port, log_level="info")
    print('Prehook started....')
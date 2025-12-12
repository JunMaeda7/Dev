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

description= "セルフサービスの値をフォームに自動表示させる"
app = FastAPI(
    title="フォーム代入（セルフサービス）",
    description=description,
    summary="フォーム代入（セルフサービス）",
    version="0.0.1",
    terms_of_service="http://example.com/terms/",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)
cf_port = int(os.getenv("PORT", 3000))
print("Start....")


@app.get('/health')
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)



@app.post("/PostingDate")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'Postingdate': ''}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)
        Postingdate = form_data.get("extensions", {}).get("Postingdate", {})
        print("Postingdate:", Postingdate)

        if not Postingdate :
            raise HTTPException(status_code=400, detail="Missing Postingdate in request payload")
        
        # Build the response structure
        response_body ={
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
          "key": Postingdate
        }
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



@app.post("/PaymentMethod")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'paymentmethod': ''}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)
        paymentmethod = form_data.get("extensions", {}).get("paymentmethod", {})
        print("paymentmethod:", paymentmethod)

        if not paymentmethod :
            raise HTTPException(status_code=400, detail="Missing paymentmethod name in request payload")
        
        # Build the response structure
        response_body ={
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
          "key": paymentmethod
        }]
            },
    "isSuccess": True
  }
}
 
        return JSONResponse(content=response_body)
 
    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(ex)}")


@app.post("/PaymentDate")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'PaymentDate': ''}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)
        PaymentDate = form_data.get("extensions", {}).get("PaymentDate", {})
        print("PaymentDate:", PaymentDate)

        if not PaymentDate :
            raise HTTPException(status_code=400, detail="Missing PaymentDate in request payload")
        
        # Build the response structure
        response_body ={
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
          "key": PaymentDate
        }
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


@app.post("/Currency")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'currency': ''}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)
        currency = form_data.get("extensions", {}).get("currency", {})
        print("currency:", currency)

        if not currency :
            raise HTTPException(status_code=400, detail="Missing currency name in request payload")
        
        # Build the response structure
        response_body ={
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
          "key": currency
        }]
            },
    "isSuccess": True
  }
}
 
        return JSONResponse(content=response_body)
 
    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(ex)}")


@app.post("/Rate")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'Rate': ''}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)
        Rate = form_data.get("extensions", {}).get("Rate", {})
        print("Rate:", Rate)

        if not Rate :
            raise HTTPException(status_code=400, detail="Missing Rate in request payload")
        
        # Build the response structure
        response_body ={
       "responseBody": {
          "messages": [
            {
                "code": "S000",
                "message": "Success",
                "type": "INFO"
            }
    ],
    "value": {
      "Form": {
        "F_Rate": Rate
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

@app.post("/TotalAmount")
async def req(request: Request):
    try:
        json_body = await request.json()
        print("Received payload:", json_body)
 
        ## {'requestBody': {'case': {'extensions': {'Total_amount': '',  "Total_amount_oth": 0 ,     "currency": "string", }}}}
 
        # Extract fields from payload
        form_data = json_body.get("requestBody", {}).get("case", {})
        print("Form Data:", form_data)

        Total_amount = form_data.get("extensions", {}).get("Total_amount", {})
        print("Total_amount:", Total_amount)       
        
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
          "key": Total_amount
        }
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
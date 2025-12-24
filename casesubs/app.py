from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from hdbcli import dbapi
import json
from datetime import datetime, date, timedelta, timezone
import calendar
from typing import Optional, List
import traceback

# 日本時間（UTC+9）
JST = timezone(timedelta(hours=9))

description = "Self-Service → /casesubs で Postingdate / PaymentDate / paymentmethod / F_Rate / F_Total_Amount_C を計算してフォームに代入"
app = FastAPI(
    title="JT Self-Service Integration (Pattern A)",
    description=description,
    summary="HANAマスタを使った計算を /casesubs で実行",
    version="0.3.0",
)

cf_port = int(os.getenv("PORT", 3000))
print("Start....")


# =========================================
# HANA接続（起動時に一度だけ）※全テーブル必須
# =========================================
def load_table_required(cursor, table_name: str) -> list:
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    columns = [c[0] for c in cursor.description]
    table = [dict(zip(columns, r)) for r in rows]
    print(f"{table_name} loaded: {len(table)} rows")
    return table


def env_required(key: str) -> str:
    v = os.getenv(key)
    if not v:
        raise RuntimeError(f"Missing required env var: {key}")
    return v


try:
    conn = dbapi.connect(
        address=env_required("HANA_ADDRESS"),
        port=int(os.getenv("HANA_PORT", "443")),
        user=env_required("HANA_USER"),
        password=env_required("HANA_PASSWORD"),
    )
    cursor = conn.cursor()

    # ★全部必須テーブル
    TBL_BPS = load_table_required(cursor, "TBL_BPS")
    TBL_BPC = load_table_required(cursor, "TBL_BPC")
    TBL_PMT = load_table_required(cursor, "TBL_PMT")
    TBL_POST_DATE = load_table_required(cursor, "TBL_POST_DATE")
    TBL_EXCHANGE_RATE = load_table_required(cursor, "TBL_EXCHANGE_RATE")
    TBL_USER_COMPANY = load_table_required(cursor, "TBL_USER_COMPANY")
    TBL_ORG_COMPANY = load_table_required(cursor, "TBL_ORG_COMPANY")

    cursor.close()
    conn.close()

except Exception as ex:
    print("❌ Failed loading required HANA tables. Stop startup.")
    print(str(ex))
    traceback.print_exc()
    raise


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)


# =========================================
# 日付ユーティリティ（JSTベース）
# =========================================
def parse_date_yyyy_mm_dd(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def add_months(base_date: date, months: int) -> date:
    total_month = (base_date.month - 1) + months
    year = base_date.year + total_month // 12
    month = (total_month % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base_date.day, last_day)
    return date(year, month, day)


def zfill_8(s: Optional[str]) -> Optional[str]:
    return None if not s else str(s).zfill(8)


def to_circled_number(n: int) -> str:
    if 1 <= n <= 20:
        return chr(ord("①") + n - 1)
    return f"{n}."


# =========================================
# /casesubs メインロジック
# =========================================
@app.post("/casesubs")
async def casesubs(request: Request):
    try:
        now_jst = datetime.now(JST)
        timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S")
        today = now_jst.date()

        json_body = await request.json()

        rb = json_body.get("requestBody", {}) or {}
        case_data = rb.get("case", {}) or {}
        form_data = rb.get("Form", {}) or {}

        # --------------------------------------------------------
        # 0) Debug: 入力(requestBody)の全項目ログ（全ロジックの最初に出力）
        #   ※ 1ログにまとめて、項目ごとに改行
        #   ※ caseType はここで取得して mode 判別に使う
        # --------------------------------------------------------
        def v(x):
            return "None" if x is None else x

        user_data = rb.get("user") or {}
        user_admin = user_data.get("adminData") or {}

        category1 = case_data.get("categoryLevel1") or {}
        ext = case_data.get("extensions") or {}

        supplier_data = case_data.get("supplier") or {}
        processor_data = case_data.get("processor") or {}
        service_team_data = case_data.get("serviceTeam") or {}
        account_data = case_data.get("account") or {}

        # ★caseTypeはここでのみ取得（ユーティリティでは扱わない）
        case_type_raw = case_data.get("caseType")
        case_type_str = "" if case_type_raw is None else str(case_type_raw).strip()

        # ★取得したcaseTypeをそのまま判別に使う（ZZX*/ZZY*）
        if case_type_str.startswith("ZZY"):
            mode = "ZZY"
        else:
            mode = "DEFAULT(ZZX等)"  # ZZX* または空/その他

        debug_lines_in = [
            "========== INPUT DEBUG START (before all logic) ==========",
            f"requestBody.case.caseType = {v(case_type_str)}",
            f"mode(ZZX/ZZY判別) = {v(mode)}",

            # requestBody.Form
            f"requestBody.Form.F_CaseErrorCheck = {v(form_data.get('F_CaseErrorCheck'))}",
            f"requestBody.Form.F_Currency = {v(form_data.get('F_Currency'))}",

            # requestBody.user.adminData
            f"requestBody.user.adminData.createdByName = {v(user_admin.get('createdByName'))}",
            f"requestBody.user.adminData.updatedBy = {v(user_admin.get('updatedBy'))}",
            f"requestBody.user.adminData.createdBy = {v(user_admin.get('createdBy'))}",
            f"requestBody.user.adminData.updatedByName = {v(user_admin.get('updatedByName'))}",

            # requestBody.case.categoryLevel1
            f"requestBody.case.categoryLevel1.displayId = {v(category1.get('displayId'))}",

            # requestBody.case.extensions
            f"requestBody.case.extensions.Total_amount = {v(ext.get('Total_amount'))}",
            f"requestBody.case.extensions.Postingdate = {v(ext.get('Postingdate'))}",
            f"requestBody.case.extensions.PaymentDate = {v(ext.get('PaymentDate'))}",
            f"requestBody.case.extensions.Teijitu = {v(ext.get('Teijitu'))}",
            f"requestBody.case.extensions.Total_amount_oth = {v(ext.get('Total_amount_oth'))}",
            f"requestBody.case.extensions.Request_date = {v(ext.get('Request_date'))}",
            f"requestBody.case.extensions.CompanyCode = {v(ext.get('CompanyCode'))}",
            f"requestBody.case.extensions.paymentmethod = {v(ext.get('paymentmethod'))}",
            f"requestBody.case.extensions.TransactionDate = {v(ext.get('TransactionDate'))}",

            # requestBody.case.supplier
            f"requestBody.case.supplier.id = {v(supplier_data.get('id'))}",
            f"requestBody.case.supplier.displayId = {v(supplier_data.get('displayId'))}",

            # requestBody.case (case自身)
            f"requestBody.case.id = {v(case_data.get('id'))}",
            f"requestBody.case.displayId = {v(case_data.get('displayId'))}",

            # requestBody.case.processor
            f"requestBody.case.processor.name = {v(processor_data.get('name'))}",
            f"requestBody.case.processor.id = {v(processor_data.get('id'))}",
            f"requestBody.case.processor.displayId = {v(processor_data.get('displayId'))}",

            # requestBody.case.serviceTeam
            f"requestBody.case.serviceTeam.id = {v(service_team_data.get('id'))}",
            f"requestBody.case.serviceTeam.displayId = {v(service_team_data.get('displayId'))}",

            # requestBody.case.account
            f"requestBody.case.account.id = {v(account_data.get('id'))}",
            f"requestBody.case.account.displayId = {v(account_data.get('displayId'))}",
            f"requestBody.case.account.defaultExternalBusinessPartnerId = {v(account_data.get('defaultExternalBusinessPartnerId'))}",

            # requestBody.case.status
            f"requestBody.case.status = {v(case_data.get('status'))}",

            "========== INPUT DEBUG END ==========",
        ]
        print("\n".join(debug_lines_in))

        # --------------------------------------------------------
        # ここから先：従来ロジック（reportedOn は使わない）
        # --------------------------------------------------------
        supplier = supplier_data or {}
        account = account_data or {}
        company = case_data.get("company") or {}
        service_team = service_team_data or {}
        extensions = ext or {}

        transaction_date_str = extensions.get("TransactionDate")
        company_code_from_ext = extensions.get("CompanyCode")
        teijitu_flag = extensions.get("Teijitu")
        request_date_str = extensions.get("Request_date")  # ★PostHookで代入された値のみ使用
        ext_postingdate_str = extensions.get("Postingdate")
        ext_paymentdate_str = extensions.get("PaymentDate")
        total_amount = extensions.get("Total_amount")
        total_amount_oth = extensions.get("Total_amount_oth")

        f_currency = form_data.get("F_Currency")

        # 申請者 / 処理者（ID比較用）
        employee = case_data.get("employee") or {}
        processor = processor_data or {}
        employee_compare_id = employee.get("employeeDisplayId") or employee.get("displayId")
        processor_compare_id = processor.get("employeeDisplayId") or processor.get("displayId")

        # company code
        company_code_from_company = company.get("displayId") if isinstance(company, dict) else None

        supplier_display_id = supplier.get("displayId") if isinstance(supplier, dict) else None
        account_display_id = account.get("displayId") if isinstance(account, dict) else None
        service_team_disp_id_raw = service_team.get("displayId") if isinstance(service_team, dict) else None

        # --------------------------------------------------------
        # 1) Postingdate 計算（ZZYでもデフォルト通りに計算）
        # --------------------------------------------------------
        new_postingdate: Optional[str] = None

        if transaction_date_str and request_date_str:
            tx_date = parse_date_yyyy_mm_dd(transaction_date_str)
            req_date = parse_date_yyyy_mm_dd(request_date_str)

            if tx_date and req_date:
                if tx_date.year == req_date.year and tx_date.month == req_date.month:
                    new_postingdate = tx_date.strftime("%Y-%m-%d")
                else:
                    fiscal_year = req_date.year

                    def match_post_row(row):
                        comp = row.get("COMPANY_CODE")
                        fy = row.get("FISCAL_YEAR")
                        try:
                            fy_int = int(fy) if fy is not None else None
                        except Exception:
                            fy_int = None
                        return fy_int == fiscal_year and (
                            (company_code_from_company and comp == company_code_from_company)
                            or (company_code_from_ext and comp == company_code_from_ext)
                        )

                    row = next((r for r in TBL_POST_DATE if match_post_row(r)), None)
                    if row:
                        month_cols = {
                            1: "M_JAN", 2: "M_FEB", 3: "M_MAR", 4: "M_APR",
                            5: "M_MAY", 6: "M_JUN", 7: "M_JUL", 8: "M_AUG",
                            9: "M_SEP", 10: "M_OCT", 11: "M_NOV", 12: "M_DEC",
                        }
                        col = month_cols.get(req_date.month)
                        day_raw = row.get(col)
                        try:
                            day_val = int(day_raw)
                        except Exception:
                            day_val = 0

                        if day_val > 0:
                            last_day = calendar.monthrange(req_date.year, req_date.month)[1]
                            comp_date = date(req_date.year, req_date.month, min(day_val, last_day))

                            if comp_date >= req_date:
                                new_postingdate = tx_date.strftime("%Y-%m-%d")
                            else:
                                nm = add_months(tx_date, 1)
                                new_postingdate = nm.replace(day=1).strftime("%Y-%m-%d")
                        else:
                            new_postingdate = tx_date.strftime("%Y-%m-%d")
                    else:
                        new_postingdate = tx_date.strftime("%Y-%m-%d")
            else:
                new_postingdate = transaction_date_str
        elif transaction_date_str:
            new_postingdate = transaction_date_str

        # --------------------------------------------------------
        # 2) paymentmethod / PaymentDate
        # --------------------------------------------------------
        computed_paymentmethod: Optional[str] = None
        computed_paymentdate: Optional[str] = None

        def match_company_code(row):
            comp = row.get("COMPANY_CODE")
            return (
                (company_code_from_company and comp == company_code_from_company)
                or (company_code_from_ext and comp == company_code_from_ext)
            )

        payment_terms = None
        pmt_row = None

        # PAYMENT_TERMS 取得
        if mode == "DEFAULT(ZZX等)":
            # BPS: SUPPLIER × COMPANY_CODE
            if supplier_display_id and (company_code_from_company or company_code_from_ext):
                bps_row = next(
                    (r for r in TBL_BPS if r.get("SUPPLIER") == supplier_display_id and match_company_code(r)),
                    None,
                )
                if bps_row:
                    payment_terms = bps_row.get("PAYMENT_TERMS")
        else:
            # ZZY: BPC: CUSTOMER(account.displayId) × COMPANY_CODE
            if account_display_id and (company_code_from_company or company_code_from_ext):
                bpc_row = next(
                    (r for r in TBL_BPC if r.get("CUSTOMER") == account_display_id and match_company_code(r)),
                    None,
                )
                if bpc_row:
                    payment_terms = bpc_row.get("PAYMENT_TERMS")

        # PMT: PAYMENT_METHOD
        if payment_terms:
            pmt_row = next((r for r in TBL_PMT if r.get("PAYMENT_TERMS") == payment_terms), None)
            if pmt_row and pmt_row.get("PAYMENT_METHOD"):
                computed_paymentmethod = pmt_row.get("PAYMENT_METHOD")

        # PaymentDate
        if mode == "DEFAULT(ZZX等)":
            # Teijitu=1 の時だけ計算
            if teijitu_flag == "1" and pmt_row:
                try:
                    z_mona = int(pmt_row.get("ZMONA") or 0)
                    z_fael = int(pmt_row.get("ZFAEL") or 0)
                except Exception:
                    z_mona, z_fael = 0, 0

                if not (z_mona == 0 and z_fael == 0):
                    posting_for_pmt = new_postingdate or ext_postingdate_str
                    if posting_for_pmt:
                        base_date = parse_date_yyyy_mm_dd(posting_for_pmt)
                        if base_date:
                            total_month = (base_date.month - 1) + z_mona
                            year = base_date.year + total_month // 12
                            month = (total_month % 12) + 1
                            last_day = calendar.monthrange(year, month)[1]
                            day = last_day if z_fael == 31 else min(z_fael, last_day)
                            computed_paymentdate = date(year, month, day).strftime("%Y-%m-%d")
        else:
            # ZZYはTeijitu無視、PaymentDateは計算しない（代入しない）
            computed_paymentdate = None

        # --------------------------------------------------------
        # 3) F_Rate
        # --------------------------------------------------------
        rate_value = ""

        if transaction_date_str and f_currency and TBL_EXCHANGE_RATE:
            txn_date_str = str(transaction_date_str).split("T")[0]

            if f_currency == "JPY":
                rate_value = ""
            else:
                matched_rate = None
                for row in TBL_EXCHANGE_RATE:
                    quoted = str(row.get("QUOTED_DATE")).split(" ")[0]
                    if quoted == txn_date_str and row.get("UNIT_CURRENCY") == f_currency:
                        matched_rate = row.get("EXCHANGE_RATE")
                        break

                if matched_rate is not None:
                    try:
                        rate_value = str(float(matched_rate))
                    except Exception:
                        rate_value = str(matched_rate)
                else:
                    rate_value = ""

        # --------------------------------------------------------
        # 4) Formへ代入
        # --------------------------------------------------------
        response_form: dict = {}

        final_posting_date = new_postingdate or (ext_postingdate_str if ext_postingdate_str is not None else "")
        response_form["F_Posting_Date"] = final_posting_date

        if computed_paymentdate is not None:
            final_payment_date = computed_paymentdate
        else:
            final_payment_date = ext_paymentdate_str if ext_paymentdate_str is not None else ""
        response_form["F_Payment_Date"] = final_payment_date

        response_form["F_Payment_Method"] = computed_paymentmethod or ""
        response_form["F_Rate"] = rate_value

        if total_amount_oth not in (None, "", 0):
            response_form["F_Total_Amount_C"] = str(total_amount_oth)
        elif total_amount not in (None, "", 0):
            response_form["F_Total_Amount_C"] = str(total_amount)

        # --------------------------------------------------------
        # 5) エラーメッセージ & check
        # --------------------------------------------------------
        errors: List[str] = []

        def add_error(msg: str):
            errors.append(msg)

        # 5-1) 申請者と処理者一致
        if employee_compare_id and processor_compare_id and employee_compare_id == processor_compare_id:
            add_error("申請者と処理者が同一の為、別の処理者を選択してください")

        # 5-2) 転記日エラー（2か月前末日以前 / 2か月後月初以降）
        if final_posting_date:
            pd = parse_date_yyyy_mm_dd(final_posting_date)
            if pd:
                two_months_before = add_months(today, -2)
                last_day_before = date(
                    two_months_before.year,
                    two_months_before.month,
                    calendar.monthrange(two_months_before.year, two_months_before.month)[1],
                )

                two_months_after = add_months(today, 2)
                first_day_after = date(two_months_after.year, two_months_after.month, 1)

                if pd <= last_day_before:
                    add_error(f"転記日が{two_months_before.year}年{two_months_before.month}月より以前の為、取引日付を再確認してください")
                if pd >= first_day_after:
                    add_error(f"転記日が{two_months_after.year}年{two_months_after.month}月より以降の為、取引日付を再確認してください")

        # 5-3) 基準日エラー（caseTypeに影響されずに判定する）
        if teijitu_flag == "2" and final_payment_date:
            pay_dt = parse_date_yyyy_mm_dd(final_payment_date)
            post_dt = parse_date_yyyy_mm_dd(final_posting_date) if final_posting_date else None

            if pay_dt:
                if pay_dt < today:
                    add_error(f"基準日が本日（{today.strftime('%Y-%m-%d')}）より過去の為、基準日を再確認してください")
                if post_dt and pay_dt < post_dt:
                    add_error(f"基準日が転記日（{final_posting_date}）より前の為、基準日を再確認してください")

        # 5-4) 処理者会社エラー
        proc_company_code = None
        org_company_code = None

        if processor_compare_id:
            user_row = next((r for r in TBL_USER_COMPANY if r.get("USER_ID") == processor_compare_id), None)
            if user_row:
                proc_company_code = user_row.get("COMPANY_CODE")

        org_unit_key = zfill_8(service_team_disp_id_raw) if service_team_disp_id_raw else None
        if org_unit_key:
            org_row = next((r for r in TBL_ORG_COMPANY if r.get("ORG_UNIT") == org_unit_key), None)
            if org_row:
                org_company_code = org_row.get("COMPANY_CODE")

        if proc_company_code and org_company_code and proc_company_code != org_company_code:
            add_error("処理者(承認者)の所属会社とサービスチーム(組織ユニット)の会社が不一致の為、処理業務及び処理者を再確認してください")

        # 5-5) 未入力チェック（supplier/accountはmodeで切替）
        if not service_team.get("displayId"):
            add_error("サービスチーム名(組織ユニット) 未入力")

        if mode == "ZZY":
            if not account_display_id:
                add_error("アカウント名(得意先) 未入力")
        else:
            if not supplier_display_id:
                add_error("サプライヤ名(仕入先) 未入力")

        if not processor_data.get("displayId"):
            add_error("処理者名(承認者) 未入力")

        if not response_form.get("F_Payment_Date"):
            add_error("基準日 未入力")

        # --------------------------------------------------------
        # 6) F_CaseErrorMsg / F_CaseErrorCheck / messages
        # --------------------------------------------------------
        if errors:
            case_error_msg = "\n".join([f"{to_circled_number(i)} {m}" for i, m in enumerate(errors, start=1)])
            case_error_check = False
        else:
            case_error_msg = "エラーなし"
            case_error_check = True

        response_form["F_CaseErrorMsg"] = case_error_msg
        response_form["F_CaseErrorCheck"] = case_error_check

        system_message = {
            "code": "S000" if case_error_check else "E001",
            "message": f"{timestamp} ケースエラーなし" if case_error_check else f"{timestamp} ケースエラーあり",
            "type": "INFO" if case_error_check else "ERROR",
        }

        response_body = {
            "responseBody": {
                "messages": [],
                "value": {"Form": response_form},
                "isSuccess": True,
            }
        }

        # --------------------------------------------------------
        # 6.5 Debug: 最新JSON 全項目の最終値ログ（1ログ・項目ごと改行）
        # --------------------------------------------------------
        user_data = rb.get("user") or {}
        user_admin = user_data.get("adminData") or {}

        case = case_data
        category1 = case.get("categoryLevel1") or {}
        ext = case.get("extensions") or {}

        supplier_data = case.get("supplier") or {}
        employee_data = case.get("employee") or {}
        processor_data = case.get("processor") or {}
        service_team_data = case.get("serviceTeam") or {}
        account_data = case.get("account") or {}

        debug_lines = [
            "========== DEBUG START (after all logic) ==========",

            # --- Form ---
            f"Form.Logic_Check = {v(form_data.get('Logic_Check'))}",
            f"Form.F_CaseErrorCheck = {v(form_data.get('F_CaseErrorCheck'))}",
            f"Form.F_Currency = {v(form_data.get('F_Currency'))}",

            # --- user.adminData ---
            f"user.adminData.createdByName = {v(user_admin.get('createdByName'))}",
            f"user.adminData.updatedBy = {v(user_admin.get('updatedBy'))}",
            f"user.adminData.createdBy = {v(user_admin.get('createdBy'))}",
            f"user.adminData.updatedByName = {v(user_admin.get('updatedByName'))}",

            # --- case.categoryLevel1 ---
            f"case.categoryLevel1.displayId = {v(category1.get('displayId'))}",

            # --- case.extensions ---
            f"case.extensions.Total_amount = {v(ext.get('Total_amount'))}",
            f"case.extensions.Postingdate = {v(ext.get('Postingdate'))}",
            f"case.extensions.PaymentDate = {v(ext.get('PaymentDate'))}",
            f"case.extensions.Teijitu = {v(ext.get('Teijitu'))}",
            f"case.extensions.Total_amount_oth = {v(ext.get('Total_amount_oth'))}",
            f"case.extensions.Request_date = {v(ext.get('Request_date'))}",
            f"case.extensions.CompanyCode = {v(ext.get('CompanyCode'))}",
            f"case.extensions.paymentmethod = {v(ext.get('paymentmethod'))}",
            f"case.extensions.TransactionDate = {v(ext.get('TransactionDate'))}",

            # --- case.supplier ---
            f"case.supplier.name = {v(supplier_data.get('name'))}",
            f"case.supplier.defaultExternalSupplierId = {v(supplier_data.get('defaultExternalSupplierId'))}",
            f"case.supplier.id = {v(supplier_data.get('id'))}",
            f"case.supplier.displayId = {v(supplier_data.get('displayId'))}",
            f"case.supplier.defaultExternalBusinessPartnerId = {v(supplier_data.get('defaultExternalBusinessPartnerId'))}",

            # --- case.employee ---
            f"case.employee.employeeDisplayId = {v(employee_data.get('employeeDisplayId'))}",
            f"case.employee.name = {v(employee_data.get('name'))}",
            f"case.employee.id = {v(employee_data.get('id'))}",
            f"case.employee.displayId = {v(employee_data.get('displayId'))}",

            # --- case.processor ---
            f"case.processor.employeeDisplayId = {v(processor_data.get('employeeDisplayId'))}",
            f"case.processor.name = {v(processor_data.get('name'))}",
            f"case.processor.id = {v(processor_data.get('id'))}",
            f"case.processor.displayId = {v(processor_data.get('displayId'))}",

            # --- case.serviceTeam ---
            f"case.serviceTeam.name = {v(service_team_data.get('name'))}",
            f"case.serviceTeam.id = {v(service_team_data.get('id'))}",
            f"case.serviceTeam.displayId = {v(service_team_data.get('displayId'))}",

            # --- case.account ---
            f"case.account.defaultExternalCustomerId = {v(account_data.get('defaultExternalCustomerId'))}",
            f"case.account.name = {v(account_data.get('name'))}",
            f"case.account.id = {v(account_data.get('id'))}",
            f"case.account.displayId = {v(account_data.get('displayId'))}",
            f"case.account.defaultExternalBusinessPartnerId = {v(account_data.get('defaultExternalBusinessPartnerId'))}",

            # --- caseType ---
            f"case.caseType = {v(case.get('caseType'))}",

            # --- calculated / response ---
            f"calc.final_posting_date = {v(final_posting_date)}",
            f"calc.final_payment_date = {v(final_payment_date)}",
            f"response.Form.F_Posting_Date = {v(response_form.get('F_Posting_Date'))}",
            f"response.Form.F_Payment_Date = {v(response_form.get('F_Payment_Date'))}",
            f"response.Form.F_Payment_Method = {v(response_form.get('F_Payment_Method'))}",
            f"response.Form.F_Rate = {v(response_form.get('F_Rate'))}",
            f"response.Form.F_Total_Amount_C = {v(response_form.get('F_Total_Amount_C'))}",
            f"response.Form.F_Total_Amount_T = {v(response_form.get('F_Total_Amount_T'))}",
            f"response.Form.F_CaseErrorMsg = {v(response_form.get('F_CaseErrorMsg'))}",
            f"response.Form.F_CaseErrorCheck = {v(response_form.get('F_CaseErrorCheck'))}",

            "========== DEBUG END ==========",
        ]
        print("\n".join(debug_lines))

        print("→ responseBody.value.Form:")
        print(json.dumps(response_form, ensure_ascii=False, indent=2))

        return JSONResponse(content=response_body, status_code=200)

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(ex)}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=cf_port, log_level="info")
    print("Server started....")

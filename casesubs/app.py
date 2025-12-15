from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from hdbcli import dbapi
import json
from datetime import datetime, date, timedelta, timezone
import calendar
from typing import Optional

# 日本時間（UTC+9）
JST = timezone(timedelta(hours=9))

description = "Self-Service → /casesubs で Postingdate / PaymentDate / paymentmethod / F_Rate / F_Total_Amount_C を計算してフォームに代入"
app = FastAPI(
    title="JT Self-Service Integration (Pattern A)",
    description=description,
    summary="HANAマスタを使った計算を /casesubs で実行",
    version="0.0.1",
    terms_of_service="http://example.com/terms/",
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
)

cf_port = int(os.getenv("PORT", 3000))
print("Start....")

# =========================================
# HANA接続（起動時に一度だけ）
# =========================================
try:
    conn = dbapi.connect(
        address="6476e830-defb-4b04-871c-7c375442b10a.hana.prod-ap21.hanacloud.ondemand.com",
        port=443,
        user="DBADMIN",
        password="11223344556677889900Aeee"
    )
    cursor = conn.cursor()

    # ====== TBL_BPS 仕入先マスタ ======
    cursor.execute("SELECT * FROM TBL_BPS")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    TBL_BPS = [dict(zip(columns, row)) for row in rows]
    print("TBL_BPS loaded:", json.dumps(TBL_BPS, ensure_ascii=False, default=str))

    # ====== TBL_PMT 支払条件マスタ ======
    cursor.execute("SELECT * FROM TBL_PMT")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    TBL_PMT = [dict(zip(columns, row)) for row in rows]
    print("TBL_PMT loaded:", json.dumps(TBL_PMT, ensure_ascii=False, default=str))

    # ====== TBL_POST_DATE 転記日判定マスタ ======
    cursor.execute("SELECT * FROM TBL_POST_DATE")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    TBL_POST_DATE = [dict(zip(columns, row)) for row in rows]
    print("TBL_POST_DATE loaded:", json.dumps(TBL_POST_DATE, ensure_ascii=False, default=str))

    # ====== TBL_EXCHANGE_RATE 為替レートマスタ ======
    cursor.execute("SELECT * FROM TBL_EXCHANGE_RATE")
    rows = cursor.fetchall()
    columns = [col[0] for col in cursor.description]
    TBL_EXCHANGE_RATE = [dict(zip(columns, row)) for row in rows]
    print("TBL_EXCHANGE_RATE loaded:", json.dumps(TBL_EXCHANGE_RATE, ensure_ascii=False, default=str))

    # ====== TBL_USER_COMPANY ユーザ会社マスタ ======
    try:
        cursor.execute("SELECT * FROM TBL_USER_COMPANY")
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        TBL_USER_COMPANY = [dict(zip(columns, row)) for row in rows]
        print("TBL_USER_COMPANY loaded:", json.dumps(TBL_USER_COMPANY, ensure_ascii=False, default=str))
    except Exception as ex_uc:
        print(f"Failed to load TBL_USER_COMPANY: {ex_uc}")
        TBL_USER_COMPANY = []

    # ====== TBL_ORG_COMPANY 組織会社マスタ ======
    try:
        cursor.execute("SELECT * FROM TBL_ORG_COMPANY")
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        TBL_ORG_COMPANY = [dict(zip(columns, row)) for row in rows]
        print("TBL_ORG_COMPANY loaded:", json.dumps(TBL_ORG_COMPANY, ensure_ascii=False, default=str))
    except Exception as ex_oc:
        print(f"Failed to load TBL_ORG_COMPANY: {ex_oc}")
        TBL_ORG_COMPANY = []

    cursor.close()
    conn.close()

except Exception as ex:
    print(f"Failed to load HANA tables: {str(ex)}")
    TBL_BPS = []
    TBL_PMT = []
    TBL_POST_DATE = []
    TBL_EXCHANGE_RATE = []
    TBL_USER_COMPANY = []
    TBL_ORG_COMPANY = []


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "running"}, status_code=200)


# 日付ユーティリティ
def parse_date_yyyy_mm_dd(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception as e:
        print(f"⚠ Failed to parse date '{s}' as YYYY-MM-DD: {e}")
        return None


def add_months(base_date: date, months: int) -> date:
    """
    base_date から months ヶ月加減算した日付を返す。
    日は、移動先月の末日を超えないように調整する。
    """
    total_month = (base_date.month - 1) + months
    year = base_date.year + total_month // 12
    month = (total_month % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(base_date.day, last_day)
    return date(year, month, day)


def zfill_8(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    return str(s).zfill(8)


def to_circled_number(n: int) -> str:
    """
    1 → ①, 2 → ② ... 20 → ⑳
    21以上は "n." にフォールバック
    """
    if 1 <= n <= 20:
        return chr(ord("①") + n - 1)
    return f"{n}."


# =========================================
# /casesubs メインロジック
# =========================================
@app.post("/casesubs")
async def casesubs(request: Request):
    try:
        # JST の現在時刻と日付
        now_jst = datetime.now(JST)
        timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S")
        today = now_jst.date()

        json_body = await request.json()
        print("Received (/casesubs):")
        print(json.dumps(json_body, ensure_ascii=False, indent=2))

        rb = json_body.get("requestBody", {}) or {}
        case_data = rb.get("case", {}) or {}
        form_data = rb.get("Form", {}) or {}

        # --- case 側データ ---
        supplier = case_data.get("supplier") or {}
        company = case_data.get("company") or {}
        service_team = case_data.get("serviceTeam") or {}
        case_type = case_data.get("caseType")

        extensions = case_data.get("extensions", {}) or {}

        transaction_date_str = extensions.get("TransactionDate")
        company_code_from_ext = extensions.get("CompanyCode")
        teijitu_flag = extensions.get("Teijitu")
        request_date_str = extensions.get("Request_date")
        ext_postingdate_str = extensions.get("Postingdate")
        ext_paymentdate_str = extensions.get("PaymentDate")
        total_amount = extensions.get("Total_amount")
        total_amount_oth = extensions.get("Total_amount_oth")

        # paymentmethod はマスタ優先で上書きしたいので、初期値は None
        computed_paymentmethod: Optional[str] = None
        computed_paymentdate: Optional[str] = None

        # 申請者 / 処理者
        employee = case_data.get("employee") or {}
        processor = case_data.get("processor") or {}

        employee_emp_disp_raw = employee.get("employeeDisplayId")
        employee_disp_raw = employee.get("displayId")
        processor_emp_disp_raw = processor.get("employeeDisplayId")
        processor_disp_raw = processor.get("displayId")

        employee_compare_id = employee_emp_disp_raw or employee_disp_raw
        processor_compare_id = processor_emp_disp_raw or processor_disp_raw

        # --- Form 側データ ---
        f_currency = form_data.get("F_Currency")

        # --------------------------------------------------------
        # 共通：company code & supplier & serviceTeam
        # --------------------------------------------------------
        company_code_from_company = None
        if isinstance(company, dict):
            company_code_from_company = company.get("displayId")

        supplier_display_id = None
        if isinstance(supplier, dict):
            supplier_display_id = supplier.get("displayId")

        service_team_disp_id_raw = None
        if isinstance(service_team, dict):
            service_team_disp_id_raw = service_team.get("displayId")

        print(f"→ caseType: {case_type}")
        print(f"→ company_code(from company): {company_code_from_company}")
        print(f"→ company_code(from extensions.CompanyCode): {company_code_from_ext}")
        print(f"→ supplier_display_id: {supplier_display_id}")
        print(f"→ TransactionDate: {transaction_date_str}")
        print(f"→ Request_date: {request_date_str}")
        print(f"→ Teijitu: {teijitu_flag}")
        print(f"→ Total_amount: {total_amount}")
        print(f"→ Total_amount_oth: {total_amount_oth}")
        print(f"→ employeeEmployeeDisplayId(raw): {employee_emp_disp_raw!r}")
        print(f"→ employeeDisplayId(raw): {employee_disp_raw!r}")
        print(f"→ processorEmployeeDisplayId(raw): {processor_emp_disp_raw!r}")
        print(f"→ processorDisplayId(raw): {processor_disp_raw!r}")
        print(f"→ ext Postingdate: {ext_postingdate_str}")
        print(f"→ ext PaymentDate: {ext_paymentdate_str}")
        print(f"→ serviceTeam.displayId(raw): {service_team_disp_id_raw!r}")

        # --------------------------------------------------------
        # 1) Postingdate の計算（TBL_POST_DATE 使用）
        # --------------------------------------------------------
        new_postingdate: Optional[str] = None

        if transaction_date_str and request_date_str:
            tx_date = parse_date_yyyy_mm_dd(transaction_date_str)
            req_date = parse_date_yyyy_mm_dd(request_date_str)

            if tx_date and req_date:
                print(f"→ Postingdate logic: tx_date={tx_date}, request_date={req_date}")

                if tx_date.year == req_date.year and tx_date.month == req_date.month:
                    new_postingdate = tx_date.strftime("%Y-%m-%d")
                    print("✅ Same year-month. Postingdate = TransactionDate.")
                else:
                    print("→ Different year-month. Apply TBL_POST_DATE logic.")

                    fiscal_year = req_date.year

                    def match_post_date_row(row):
                        comp = row.get("COMPANY_CODE")
                        fy = row.get("FISCAL_YEAR")
                        try:
                            fy_int = int(fy) if fy is not None else None
                        except ValueError:
                            fy_int = None
                        return (
                            fy_int == fiscal_year
                            and (
                                (company_code_from_company and comp == company_code_from_company)
                                or (company_code_from_ext and comp == company_code_from_ext)
                            )
                        )

                    post_row = next(
                        (row for row in TBL_POST_DATE if match_post_date_row(row)),
                        None,
                    )

                    if post_row:
                        print(
                            f"✅ Found POST_DATE row. COMPANY_CODE={post_row.get('COMPANY_CODE')}, "
                            f"FISCAL_YEAR={post_row.get('FISCAL_YEAR')}"
                        )
                        month_to_col = {
                            1: "M_JAN",
                            2: "M_FEB",
                            3: "M_MAR",
                            4: "M_APR",
                            5: "M_MAY",
                            6: "M_JUN",
                            7: "M_JUL",
                            8: "M_AUG",
                            9: "M_SEP",
                            10: "M_OCT",
                            11: "M_NOV",
                            12: "M_DEC",
                        }
                        month_col = month_to_col.get(req_date.month)
                        day_raw = post_row.get(month_col)

                        try:
                            day_val = int(day_raw) if day_raw is not None else 0
                        except ValueError:
                            day_val = 0

                        if day_val > 0:
                            last_day = calendar.monthrange(req_date.year, req_date.month)[1]
                            day = min(day_val, last_day)
                            comparison_date = date(req_date.year, req_date.month, day)
                            print(
                                f"→ comparison_date(from TBL_POST_DATE): {comparison_date}, "
                                f"request_date: {req_date}"
                            )

                            if comparison_date >= req_date:
                                new_postingdate = tx_date.strftime("%Y-%m-%d")
                                print("✅ comparison_date >= Request_date. Postingdate = TransactionDate.")
                            else:
                                total_month = (tx_date.month - 1) + 1
                                year = tx_date.year + total_month // 12
                                month = (total_month % 12) + 1
                                next_month_first = date(year, month, 1)
                                new_postingdate = next_month_first.strftime("%Y-%m-%d")
                                print(
                                    "✅ comparison_date < Request_date. "
                                    f"Postingdate = first day of next month of TransactionDate: {next_month_first}"
                                )
                        else:
                            new_postingdate = tx_date.strftime("%Y-%m-%d")
                            print(
                                f"⚠ Invalid or zero day in TBL_POST_DATE({month_col}={day_raw}). "
                                "Fallback: Postingdate = TransactionDate."
                            )
                    else:
                        new_postingdate = tx_date.strftime("%Y-%m-%d")
                        print(
                            "❌ No matching row in TBL_POST_DATE. "
                            "Fallback: Postingdate = TransactionDate."
                        )
            else:
                if transaction_date_str:
                    new_postingdate = transaction_date_str
                    print(
                        "⚠ Could not parse tx_date or request_date. "
                        "Fallback: Postingdate = TransactionDate string."
                    )
        elif transaction_date_str:
            new_postingdate = transaction_date_str
            print("→ Request_date not available. Postingdate = TransactionDate (simple copy).")
        else:
            print("→ TransactionDate not found. Postingdate not calculated.")

        # --------------------------------------------------------
        # 2) paymentmethod / PaymentDate の計算
        # --------------------------------------------------------
        try:
            payment_terms = None
            pmt_row = None

            if supplier_display_id and (company_code_from_company or company_code_from_ext):
                def match_company_code(row):
                    comp = row.get("COMPANY_CODE")
                    return (
                        (company_code_from_company and comp == company_code_from_company)
                        or (company_code_from_ext and comp == company_code_from_ext)
                    )

                bps_row = next(
                    (
                        row
                        for row in TBL_BPS
                        if row.get("SUPPLIER") == supplier_display_id
                        and match_company_code(row)
                    ),
                    None,
                )

                if bps_row:
                    payment_terms = bps_row.get("PAYMENT_TERMS")
                    print(
                        f"✅ Found BPS row. "
                        f"SUPPLIER={supplier_display_id}, "
                        f"COMPANY_CODE={bps_row.get('COMPANY_CODE')}, "
                        f"PAYMENT_TERMS={payment_terms}"
                    )
                else:
                    print(
                        "❌ No matching row in TBL_BPS for "
                        f"SUPPLIER={supplier_display_id} and "
                        f"COMPANY_CODE in "
                        f"({company_code_from_company}, {company_code_from_ext})."
                    )

                if payment_terms:
                    pmt_row = next(
                        (
                            row
                            for row in TBL_PMT
                            if row.get("PAYMENT_TERMS") == payment_terms
                        ),
                        None,
                    )

                    if pmt_row:
                        payment_method = pmt_row.get("PAYMENT_METHOD")
                        print(f"✅ Found PMT row. PAYMENT_METHOD = {payment_method}")
                        if payment_method:
                            computed_paymentmethod = payment_method
                    else:
                        print("❌ No matching row in TBL_PMT for PAYMENT_TERMS.")
            else:
                print(
                    "supplier_display_id or both company_code(from company) / "
                    "company_code(from extensions) are missing. Skip DB mapping for paymentmethod."
                )

            # PaymentDate 計算（Teijitu == "1" のときのみ）
            if teijitu_flag == "1":
                if pmt_row:
                    try:
                        z_mona = int(pmt_row.get("ZMONA") or 0)
                        z_fael = int(pmt_row.get("ZFAEL") or 0)
                        print(f"→ ZMONA: {z_mona}, ZFAEL: {z_fael}")
                    except ValueError:
                        z_mona = 0
                        z_fael = 0
                        print("⚠ ZMONA/ZFAEL parse error. Treat as 0/0.")

                    if not (z_mona == 0 and z_fael == 0):
                        posting_for_pmt = new_postingdate or ext_postingdate_str
                        if posting_for_pmt:
                            try:
                                base_date = datetime.strptime(posting_for_pmt, "%Y-%m-%d").date()

                                total_month = (base_date.month - 1) + z_mona
                                year = base_date.year + total_month // 12
                                month = (total_month % 12) + 1

                                last_day = calendar.monthrange(year, month)[1]

                                if z_fael == 31:
                                    day = last_day
                                else:
                                    day = min(z_fael, last_day)

                                computed_paymentdate = date(year, month, day).strftime("%Y-%m-%d")
                                print(f"✅ PaymentDate calculated: {computed_paymentdate}")
                            except Exception as e_pd:
                                print(f"⚠ Failed to calculate PaymentDate: {e_pd}")
                        else:
                            print("→ Postingdate not available. Cannot calculate PaymentDate.")
                    else:
                        print("→ ZMONA and ZFAEL are both 0. Skip PaymentDate assignment.")
                else:
                    print("→ No PMT row. Skip PaymentDate assignment.")
            else:
                print("→ Teijitu is not '1'. Skip PaymentDate assignment.")

        except Exception as e:
            print(f"⚠ Error while mapping paymentmethod/PaymentDate from HANA: {e}")

        # --------------------------------------------------------
        # 3) F_Rate: TransactionDate × F_Currency → TBL_EXCHANGE_RATE
        #    常に上書き（JPY の場合は必ず ""）
        # --------------------------------------------------------
        rate_value = ""

        if transaction_date_str and f_currency and TBL_EXCHANGE_RATE:
            txn_date_str = str(transaction_date_str)
            if "T" in txn_date_str:
                txn_date_str = txn_date_str.split("T")[0]

            if f_currency == "JPY":
                # JPY の場合は常にブランク
                rate_value = ""
                print("→ F_Currency is JPY. F_Rate will be set to empty string.")
            else:
                matched_rate = None
                for row in TBL_EXCHANGE_RATE:
                    quoted = str(row.get("QUOTED_DATE"))
                    if " " in quoted:
                        quoted = quoted.split(" ")[0]
                    if quoted == txn_date_str and row.get("UNIT_CURRENCY") == f_currency:
                        matched_rate = row.get("EXCHANGE_RATE")
                        break

                print(f"Matched EXCHANGE_RATE for {txn_date_str} / {f_currency}: {matched_rate}")

                if matched_rate is not None:
                    try:
                        rate_value = str(float(matched_rate))
                    except Exception:
                        rate_value = str(matched_rate)
                else:
                    rate_value = ""
        else:
            print("→ F_Rate not calculated (missing TransactionDate or F_Currency or TBL_EXCHANGE_RATE empty).")
            rate_value = ""

        # --------------------------------------------------------
        # 4) Form への代入
        # --------------------------------------------------------
        response_form: dict = {}

        # Postingdate → F_Posting_Date
        final_posting_date: Optional[str] = None
        if new_postingdate:
            response_form["F_Posting_Date"] = new_postingdate
            final_posting_date = new_postingdate
        elif ext_postingdate_str:
            response_form["F_Posting_Date"] = ext_postingdate_str
            final_posting_date = ext_postingdate_str

        # PaymentDate → F_Payment_Date
        if computed_paymentdate is not None:
            final_payment_date = computed_paymentdate
        else:
            if ext_paymentdate_str is not None:
                final_payment_date = ext_paymentdate_str
            else:
                final_payment_date = ""

        # 常に上書き（空文字も含めて）
        response_form["F_Payment_Date"] = final_payment_date

        # paymentmethod → F_Payment_Method（マスタ優先・上書き）
        if computed_paymentmethod:
            response_form["F_Payment_Method"] = computed_paymentmethod

        # F_Rate 常に上書き
        response_form["F_Rate"] = rate_value

        # F_Total_Amount_C：case.extensions から（Total_amount_oth 優先）
        f_total_amount_value = None
        if total_amount_oth not in (None, "", 0):
            f_total_amount_value = str(total_amount_oth)
            print(f"→ F_Total_Amount_C set from Total_amount_oth: {total_amount_oth}")
        elif total_amount not in (None, "", 0):
            f_total_amount_value = str(total_amount)
            print(f"→ F_Total_Amount_C set from Total_amount: {total_amount}")

        if f_total_amount_value is not None:
            response_form["F_Total_Amount_C"] = f_total_amount_value

        # --------------------------------------------------------
        # 5) エラーメッセージ & errorcheck ロジック
        # --------------------------------------------------------
        errors = []

        def add_error(msg: str):
            errors.append(msg)

        # 5-1) 申請者と処理者の employeeDisplayId / displayId が一致
        if employee_compare_id and processor_compare_id and employee_compare_id == processor_compare_id:
            print("★ employee(employeeDisplayId/displayId) と processor(employeeDisplayId/displayId) が一致")
            add_error("申請者と処理者が同一の為、別の処理者を選択してください")

        # 5-2) 転記日エラー
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

                # 「二か月前の月末以前」
                if pd <= last_day_before:
                    print(
                        f"★ 転記日エラー（過去側）pd={pd}, last_day_before={last_day_before}"
                    )
                    add_error(
                        f"転記日が{two_months_before.year}年{two_months_before.month}月より以前の為、取引日付を再確認してください"
                    )

                # 「二か月後の月初以降」
                if pd >= first_day_after:
                    print(
                        f"★ 転記日エラー（未来側）pd={pd}, first_day_after={first_day_after}"
                    )
                    add_error(
                        f"転記日が{two_months_after.year}年{two_months_after.month}月より以降の為、取引日付を再確認してください"
                    )

        # 5-3) 支払基準日エラー (Teijitu = "2")
        if teijitu_flag == "2" and final_payment_date:
            pay_dt = parse_date_yyyy_mm_dd(final_payment_date)
            pd = parse_date_yyyy_mm_dd(final_posting_date) if final_posting_date else None

            if pay_dt:
                cond1 = pay_dt < today
                cond2 = pd is not None and pay_dt < pd
                if cond1:
                    print(
                        f"★ 支払基準日エラー（本日より過去）: pay_dt={pay_dt}, today={today}"
                    )
                    add_error(
                        f"支払基準日が本日（{today.strftime('%Y-%m-%d')}）より過去の為、支払基準日を再確認してください"
                    )
                if cond2:
                    print(
                        f"★ 支払基準日エラー（転記日より前）: pay_dt={pay_dt}, posting_dt={pd}"
                    )
                    add_error(
                        f"支払基準日が転記日（{final_posting_date}）より前の為、支払基準日を再確認してください"
                    )

        # 5-4) 処理者会社エラー (TBL_USER_COMPANY & TBL_ORG_COMPANY)
        proc_company_code = None
        org_company_code = None

        if processor_compare_id and TBL_USER_COMPANY:
            user_row = next(
                (row for row in TBL_USER_COMPANY if row.get("USER_ID") == processor_compare_id),
                None,
            )
            if user_row:
                proc_company_code = user_row.get("COMPANY_CODE")
                print(
                    f"→ TBL_USER_COMPANY hit: USER_ID={processor_compare_id}, "
                    f"COMPANY_CODE={proc_company_code}"
                )
            else:
                print(f"→ TBL_USER_COMPANY no hit for USER_ID={processor_compare_id}")

        org_unit_key = zfill_8(service_team_disp_id_raw) if service_team_disp_id_raw else None
        if org_unit_key and TBL_ORG_COMPANY:
            org_row = next(
                (row for row in TBL_ORG_COMPANY if row.get("ORG_UNIT") == org_unit_key),
                None,
            )
            if org_row:
                org_company_code = org_row.get("COMPANY_CODE")
                print(
                    f"→ TBL_ORG_COMPANY hit: ORG_UNIT={org_unit_key}, "
                    f"COMPANY_CODE={org_company_code}"
                )
            else:
                print(f"→ TBL_ORG_COMPANY no hit for ORG_UNIT={org_unit_key}")
        elif service_team_disp_id_raw:
            print(f"→ serviceTeam.displayId={service_team_disp_id_raw}, padded={org_unit_key}")

        # 両方 COMPANY_CODE が取れていて、かつ不一致のときのみエラー
        if (
            proc_company_code not in (None, "")
            and org_company_code not in (None, "")
            and proc_company_code != org_company_code
        ):
            print(
                f"★ 処理者会社エラー判定: proc_company_code={proc_company_code}, "
                f"org_company_code={org_company_code}"
            )
            add_error(
                "処理者の所属会社とサービス組織の会社が不一致の為、支払依頼及び処理者を再確認してください"
            )

        # 5-5) 未入力チェック
        # serviceTeam.displayId 未入力
        service_team_disp = service_team.get("displayId")
        if not service_team_disp:
            add_error("サービスチーム表示ID 未入力")

        # supplier.displayId 未入力
        supplier_disp = supplier.get("displayId")
        if not supplier_disp:
            add_error("サプライヤ表示 ID 未入力")

        # processor.displayId 未入力
        processor_disp_for_check = processor.get("displayId")
        if not processor_disp_for_check:
            add_error("処理担当者ビジネスパートナー ID 未入力")

        # F_Payment_Date 未入力
        payment_date_for_check = response_form.get("F_Payment_Date")
        if not payment_date_for_check:
            add_error("支払基準日 未入力")

        # --------------------------------------------------------
        # 6) F_CaseErrorMsg / F_CaseErrorCheck / system_message
        # --------------------------------------------------------
        if errors:
            numbered_lines = []
            for idx, msg in enumerate(errors, start=1):
                mark = to_circled_number(idx)
                numbered_lines.append(f"{mark} {msg}")
            case_error_msg = "\n".join(numbered_lines)
            case_error_check = False
        else:
            case_error_msg = "エラーなし"
            case_error_check = True

        response_form["F_CaseErrorMsg"] = case_error_msg
        response_form["F_CaseErrorCheck"] = case_error_check

        # システムメッセージ（INFO / ERROR）
        if case_error_check:
            system_message = {
                "code": "S000",
                "message": f"{timestamp} ケースエラーなし",
                "type": "INFO",
            }
        else:
            system_message = {
                "code": "E001",
                "message": f"{timestamp} ケースエラーあり",
                "type": "ERROR",
            }

        # --------------------------------------------------------
        # レスポンス組み立て
        # --------------------------------------------------------
        response_body = {
            "responseBody": {
                "messages": [
                    system_message
                ],
                "value": {
                    "Form": response_form
                },
                "isSuccess": True,
            }
        }

        print("→ responseBody.value.Form:")
        print(json.dumps(response_form, ensure_ascii=False, indent=2))

        return JSONResponse(content=response_body, status_code=200)

    except HTTPException as http_ex:
        raise http_ex
    except Exception as ex:
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(ex)}"
        )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=cf_port, log_level="info")
    print("Server started....")

"""
飞书审批外部选项API服务 - Vercel Serverless 版本
基于飞书多维表格「投管系统字段选项汇总表」
"""

from flask import Flask, request, jsonify
import json
import requests
import os
from datetime import datetime

app = Flask(__name__)

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a702d854343f100b")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "qlQN64wYn6ocTBeDct7T4eFxp2uhOPGh")
BASE_TOKEN = os.environ.get("BASE_TOKEN", "UcVIbWeh7afIZMsudxOc3vCgnoh")
TABLE_ID = os.environ.get("TABLE_ID", "tblN9MhKkKVSAELI")
API_TOKEN = os.environ.get("API_TOKEN", "approval-options-2024")

FIELD_MAPPING = {
    "investor_type": "投资人性质",
    "enterprise_tag": "天眼查企业标签",
    "seal": "印章",
    "our_entity": "我方主体",
    "payment_entity": "我方付款主体",
    "followup_category": "跟进事项分类",
    "fund_nature": "基金性质",
    "fund_type": "基金类型",
    "fund_record_type": "基金备案类型",
    "industry_investment": "产业投向",
    "pillar_industry": "6大支柱产业",
    "future_industry": "6大未来产业",
    "fund_stage": "基金所处阶段",
    "business_rd": "业务及研发情况",
    "financial_status": "财务情况",
    "project_highlight": "项目亮点标签",
    "company_stage": "企业所属阶段",
    "exit_method": "退出方式",
    "listing_status": "上市状态",
    "amac_level3": "基协三级行业分类",
    "amac_level4": "基协四级行业分类"
}

_options_data = None

def get_feishu_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET
    }, timeout=5)
    result = resp.json()
    if result.get("code") != 0:
        raise Exception(f"获取token失败: {result.get('msg')}")
    return result["tenant_access_token"]

def fetch_all_options():
    token = get_feishu_token()
    all_records = []
    page_token = None
    max_pages = 3
    
    for _ in range(max_pages):
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
            
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        result = resp.json()
        
        if result.get("code") != 0:
            raise Exception(f"获取数据失败: {result.get('msg')}")
        
        items = result["data"].get("items", [])
        all_records.extend(items)
        page_token = result["data"].get("page_token")
        if not page_token or not items:
            break
    
    options = {key: set() for key in FIELD_MAPPING.keys()}
    for record in all_records:
        fields = record.get("fields", {})
        for api_key, field_name in FIELD_MAPPING.items():
            value = fields.get(field_name)
            if value:
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            options[api_key].add(item.strip())
                        elif isinstance(item, dict):
                            if "name" in item and item["name"].strip():
                                options[api_key].add(item["name"].strip())
                elif isinstance(value, str) and value.strip():
                    options[api_key].add(value.strip())
    
    return {k: sorted(list(v)) for k, v in options.items()}

def get_options_data():
    global _options_data
    if _options_data is None:
        _options_data = fetch_all_options()
    return _options_data

def verify_token(request):
    return request.args.get("token", "") == API_TOKEN

@app.route("/", methods=["GET"])
def root():
    if not verify_token(request):
        return jsonify({"code": 403, "msg": "token 无效", "data": {"options": []}}), 403
    return jsonify({
        "code": 0,
        "msg": "success",
        "data": {
            "fields": list(FIELD_MAPPING.keys()),
            "usage": "调用 /api/options?field=字段标识&token=your_token 获取具体选项"
        }
    })

@app.route("/api/options", methods=["GET"])
def get_options():
    if not verify_token(request):
        return jsonify({"code": 403, "msg": "token 无效", "data": {"options": []}}), 403
    
    field = request.args.get("field")
    if not field or field not in FIELD_MAPPING:
        return jsonify({"code": -1, "msg": f"未知字段: {field}", "data": {"options": []}}), 400
    
    try:
        options_data = get_options_data()
        options = options_data.get(field, [])
        return jsonify({
            "code": 0,
            "msg": "success",
            "data": {"options": [{"label": opt, "value": opt} for opt in options]}
        })
    except Exception as e:
        return jsonify({"code": -1, "msg": str(e), "data": {"options": []}}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "code": 0,
        "msg": "healthy",
        "data": {"service": "approval-options-api", "version": "1.1"}
    })

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == "__main__":
    app.run(debug=True)

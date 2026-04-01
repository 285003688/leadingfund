"""
飞书审批外部选项API服务 - Vercel Serverless 版本
基于飞书多维表格「投管系统字段选项汇总表」
"""

import json
import requests
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler

# ============ 配置项 ============
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a702d854343f100b")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "qlQN64wYn6ocTBeDct7T4eFxp2uhOPGh")
BASE_TOKEN = os.environ.get("BASE_TOKEN", "UcVIbWeh7afIZMsudxOc3vCgnoh")
TABLE_ID = os.environ.get("TABLE_ID", "tblN9MhKkKVSAELI")

# 字段映射配置
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

# 简单内存缓存（Vercel 无状态，每次请求可能新实例）
_options_cache = None
_cache_time = None
CACHE_DURATION = 300  # 缓存5分钟

def get_feishu_token():
    """获取飞书 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        resp = requests.post(url, json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        }, timeout=10)
        result = resp.json()
        if result.get("code") != 0:
            raise Exception(f"获取token失败: {result.get('msg')}")
        return result["tenant_access_token"]
    except Exception as e:
        raise Exception(f"飞书API调用失败: {str(e)}")

def fetch_all_options():
    """从多维表格获取所有选项数据"""
    token = get_feishu_token()
    
    # 分页获取所有记录
    all_records = []
    page_token = None
    
    while True:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
            
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        result = resp.json()
        
        if result.get("code") != 0:
            raise Exception(f"获取数据失败: {result.get('msg')}")
        
        items = result["data"]["items"]
        all_records.extend(items)
        
        page_token = result["data"].get("page_token")
        if not page_token or not items:
            break
    
    # 解析数据，按字段聚合选项
    options = {key: set() for key in FIELD_MAPPING.keys()}
    
    for record in all_records:
        fields = record.get("fields", {})
        for api_key, field_name in FIELD_MAPPING.items():
            value = fields.get(field_name)
            if value:
                if isinstance(value, list):
                    # 多选字段
                    for item in value:
                        if isinstance(item, str):
                            options[api_key].add(item.strip())
                        elif isinstance(item, dict):
                            if "name" in item:
                                options[api_key].add(item["name"].strip())
                            elif "text" in item:
                                options[api_key].add(item["text"].strip())
                elif isinstance(value, str):
                    if value.strip():
                        options[api_key].add(value.strip())
    
    # 转换为列表并排序
    return {k: sorted(list(v)) for k, v in options.items()}

def get_cached_options():
    """获取缓存的选项数据"""
    global _options_cache, _cache_time
    
    now = datetime.now()
    if _cache_time is None or (now - _cache_time).seconds > CACHE_DURATION or _options_cache is None:
        try:
            _options_cache = fetch_all_options()
            _cache_time = now
            print(f"[{now}] 缓存已刷新")
        except Exception as e:
            print(f"[{now}] 刷新缓存失败: {e}")
            if _options_cache is None:
                raise
    
    return _options_cache

def handle_request(path, query_params):
    """处理请求逻辑"""
    
    if path == "/api/options" or path == "/":
        field = query_params.get("field")
        
        if field:
            # 返回特定字段的选项
            options_data = get_cached_options()
            if field in options_data:
                return {
                    "code": 0,
                    "msg": "success",
                    "data": {
                        "options": [
                            {"label": opt, "value": opt} 
                            for opt in options_data[field]
                        ]
                    }
                }
            else:
                return {
                    "code": -1,
                    "msg": f"未知字段: {field}，可用字段: {list(FIELD_MAPPING.keys())}",
                    "data": {"options": []}
                }
        else:
            # 返回所有可用字段
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "fields": list(FIELD_MAPPING.keys()),
                    "field_mapping": FIELD_MAPPING,
                    "usage": "调用 /api/options?field=字段标识 获取具体选项"
                }
            }
    
    elif path == "/api/refresh":
        # 强制刷新缓存
        global _cache_time
        _cache_time = None
        options_data = get_cached_options()
        return {
            "code": 0,
            "msg": "缓存已刷新",
            "data": {
                "record_count": len(options_data),
                "fields": {k: len(v) for k, v in options_data.items()}
            }
        }
    
    elif path == "/health":
        return {
            "code": 0,
            "msg": "healthy",
            "data": {
                "timestamp": datetime.now().isoformat(),
                "service": "approval-options-api",
                "version": "1.0"
            }
        }
    
    else:
        return {
            "code": 404,
            "msg": "接口不存在",
            "data": {
                "available_paths": ["/", "/api/options", "/api/refresh", "/health"]
            }
        }

class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Handler"""
    
    def do_GET(self):
        try:
            # 解析路径和查询参数
            path = self.path.split('?')[0]
            query_string = self.path.split('?')[1] if '?' in self.path else ""
            
            query_params = {}
            if query_string:
                for param in query_string.split('&'):
                    if '=' in param:
                        k, v = param.split('=', 1)
                        query_params[k] = v
            
            # 处理请求
            result = handle_request(path, query_params)
            status_code = 200 if result.get("code") == 0 or result.get("code") == 200 else (404 if result.get("code") == 404 else 500)
            
            # 发送响应
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            error_response = {
                "code": -1,
                "msg": str(e),
                "data": {"options": []}
            }
            self.wfile.write(json.dumps(error_response, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        """处理CORS预检请求"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

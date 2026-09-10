import json
import os
import base64
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Optional
from loguru import logger
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

@dataclass
class EnergyInfo:
    electricity_remain: float
    last_read_date: str
    fetch_time: datetime = field(default_factory=datetime.now)

class EnergyService:
    AES_KEY = b'1234567812345678'
    AES_IV = b'1234567812345678'
    
    def __init__(self, ids_session, data_dir: str):
        self.ids_session = ids_session
        self.cache_file = os.path.join(data_dir, 'cache', 'energy.json')
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def _get_signature(self) -> tuple[str, str]:
        res = self.ids_session.post("https://ignypt.xidian.edu.cn/baseNew/api/User/GetSignature", json={
            "data": "",
            "access_token": "",
            "OpCode": "MPAY",
            "RequestID": ""
        })
        data = res.json()["data"]
        return str(data["timestamp"]), str(data["signature"])

    def _request(self, url: str, data: dict, is_get=False):
        timestamp, signature = self._get_signature()
        
        cipher = AES.new(self.AES_KEY, AES.MODE_CBC, self.AES_IV)
        json_data = json.dumps(data, separators=(',', ':')).encode('utf-8')
        encrypted = cipher.encrypt(pad(json_data, AES.block_size))
        b64_content = base64.b64encode(encrypted).decode('utf-8')
        
        headers = {
            "timestamp": timestamp,
            "signature": signature,
            "OpCode": "MPAY",
            "OrgId": "",
            "RequestID": ""
        }
        
        if is_get:
            encoded_content = urllib.parse.quote(b64_content)
            res = self.ids_session.get(f"{url}?content={encoded_content}", headers=headers)
        else:
            res = self.ids_session.post(url, json={"content": b64_content}, headers=headers)
        return res.json()

    def fetch(self, username: str) -> EnergyInfo:
        try:
            target_url = (
                "https://xxcapp.xidian.edu.cn/uc/api/oauth/index?"
                "redirect=https://ignypt.xidian.edu.cn/revenueH5/login?"
                "opcode=MPAY&appid=200260318155520600&state=12312312312312&qrcode=0"
            )
            location = self.ids_session.check_and_login(target=target_url)
            resp = self.ids_session.follow_ids_redirects(location)
            
            # 从重定向后的 URL 或 Location 中提取 code 参数
            code = None
            for candidate_url in [str(resp.url), resp.headers.get("Location", "")]:
                if candidate_url:
                    parsed = urllib.parse.urlparse(candidate_url)
                    extracted = urllib.parse.parse_qs(parsed.query).get("code")
                    if extracted:
                        code = extracted[0]
                        break
                        
            if not code:
                logger.warning("未能通过重定向获取电费 OAuth code，尝试直接使用已登录凭据")
                code = ""
            
            res_oauth = self._request("https://ignypt.xidian.edu.cn/estManage/api/WeChat/V2/OauthGetUserInfo", {"CODE": code}, is_get=True)
            
            res_login = self._request("https://ignypt.xidian.edu.cn/estManage/api/WeChat/V2/H5UserIDLogIn", {
                "UserID": username,
                "Pwd": "",
                "IsCehckPwd": 1,
                "NodeID": ""
            })
            
            node_id = res_login["ResData"][0]["NodeID"]
            
            res_meters = self._request("https://ignypt.xidian.edu.cn/estManage/api/wechat/v2/H5QueryMeterList", {"NodeID": node_id}, is_get=True)
            
            rows = res_meters["ResData"]["rows"]
            elec_meter = next(r for r in rows if r["MediumCode"] == "2")
            
            info = EnergyInfo(
                electricity_remain=float(elec_meter["LastNum"]),
                last_read_date=elec_meter["LastReadDate"]
            )
            
            def date_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError("Type not serializable")
                
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(info), f, default=date_serializer, ensure_ascii=False, indent=2)
                
            return info
        except Exception as e:
            logger.error(f"获取电费信息失败: {e}")
            raise

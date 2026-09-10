import threading
import re
from urllib.parse import urlparse, parse_qs

class IDSReAuthClient:
    def __init__(self, challenge_uri: str):
        self.challenge_uri = challenge_uri
        self.recipient_description = None
        self._delivery_username = None
        self._challenge_prepared = False
        self._prepared_code_type = None

    @staticmethod
    def is_reauth_location(location: str) -> bool:
        parsed = urlparse(location)
        return (parsed.scheme == 'https' and 
                parsed.netloc == 'ids.xidian.edu.cn' and 
                parsed.path == '/authserver/reAuthCheck/reAuthLoginView.do')

    def prepare(self, session, challenge_uri: str, code_type: str = 'sms'):
        if not self._challenge_prepared:
            rsp = session.get(challenge_uri)
            rsp.raise_for_status()
            
            match = re.search(r'"reAuthUserId"\s*:\s*"([^"\\]+)"', rsp.text)
            if match:
                self._delivery_username = match.group(1).strip()
                
            self._challenge_prepared = True
            
        if self._prepared_code_type == code_type:
            return
            
        qs = parse_qs(urlparse(challenge_uri).query)
        is_multifactor = qs.get('isMultifactor', ['true'])[0]
        service = qs.get('service', [''])[0]
        
        reauth_type = '3' if code_type == 'sms' else '4'
        
        rsp = session.post(
            'https://ids.xidian.edu.cn/authserver/reAuthCheck/changeReAuthType.do',
            data={
                'isMultifactor': is_multifactor,
                'reAuthType': reauth_type,
                'service': service,
            }
        )
        json_data = rsp.json()
        if str(json_data.get('code')) != '1':
            raise Exception(json_data.get('message', 'Failed to change reauth type'))
            
        data = json_data.get('data')
        if isinstance(data, dict):
            self.recipient_description = data.get('reAuthUserNameInput')
            
        self._prepared_code_type = code_type

    def send_code(self, session, username: str, code_type: str = 'sms'):
        self.prepare(session, self.challenge_uri, code_type)
        auth_code_type_name = 'reAuthDynamicCodeType' if code_type == 'sms' else 'reAuthWChatDynamicCodeType'
        
        rsp = session.post(
            'https://ids.xidian.edu.cn/authserver/dynamicCode/getDynamicCodeByReauth.do',
            data={
                'userName': self._delivery_username or username,
                'authCodeTypeName': auth_code_type_name,
            }
        )
        return rsp.json()

    def submit_code(self, session, code: str, service: str, code_type: str = 'sms', trust_device: bool = True) -> str:
        self.prepare(session, self.challenge_uri, code_type)
        code = code.strip()
        if not code:
            raise ValueError("Empty code")
            
        qs = parse_qs(urlparse(self.challenge_uri).query)
        is_multifactor = qs.get('isMultifactor', ['true'])[0]
        
        reauth_type = '3' if code_type == 'sms' else '4'
        
        rsp = session.post(
            'https://ids.xidian.edu.cn/authserver/reAuthCheck/reAuthSubmit.do',
            data={
                'service': service or '',
                'reAuthType': reauth_type,
                'isMultifactor': is_multifactor,
                'password': '',
                'dynamicCode': code,
                'uuid': '',
                'answer1': '',
                'answer2': '',
                'otpCode': '',
                'skipTmpReAuth': str(trust_device).lower(),
            }
        )
        json_data = rsp.json()
        status_code = str(json_data.get('code'))
        if status_code != 'reAuth_success':
            raise Exception(json_data.get('msg', 'Reauth failed'))
            
        login_rsp = session.get(
            'https://ids.xidian.edu.cn/authserver/login',
            params={'service': service} if service else None,
            follow_redirects=False
        )
        
        location = login_rsp.headers.get('Location')
        if not location:
            raise Exception('No location header after successful reauth')
            
        if self.is_reauth_location(location):
            raise Exception('Reauth not complete')
            
        return location

reauth_needed_callback = None
reauth_event = threading.Event()
reauth_code_store = {}

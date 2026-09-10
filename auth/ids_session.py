import base64
import urllib.parse
from bs4 import BeautifulSoup
from loguru import logger

from core.crypto import aes_encrypt_ids
from core.network import get_ids_client, save_cookies, load_cookies, cookies_to_string

from auth.slider_captcha import SliderCaptchaSolver, CaptchaSolveFailedException
from auth.ids_fingerprint import get_or_create_ids_browser_fingerprint
from auth.reauth import IDSReAuthClient, reauth_needed_callback, reauth_event, reauth_code_store

class PasswordWrongException(Exception):
    pass

class LoginFailedException(Exception):
    pass

class IDSSession:
    MAX_AUTH_REDIRECTS = 30

    def __init__(self, data_dir: str, on_reauth_needed=None):
        self.data_dir = data_dir
        self.on_reauth_needed = on_reauth_needed or reauth_needed_callback
        self.client = get_ids_client(data_dir)
        load_cookies(self.client, data_dir)

    def _report_step(self, msg: str):
        logger.info(f"[IDS] {msg}")
        if getattr(self, "on_step", None):
            try:
                self.on_step(msg)
            except Exception:
                pass

    def _aes_encrypt_password(self, password: str, key: str) -> str:
        return aes_encrypt_ids(password, key)

    def _register_browser_fingerprint(self):
        fingerprint = get_or_create_ids_browser_fingerprint(self.data_dir)
        import time
        ts = str(int(time.time() * 1000))
        self.client.get(
            'https://ids.xidian.edu.cn/authserver/bfp/info',
            params={'bfp': fingerprint, '_': ts}
        )

    def login(self, username: str, password: str, target: str = None, force_manual_captcha: bool = False) -> str:
        self.username = username
        self.password = password
        self._report_step("正在连接西电统一身份认证 (IDS)...")
        params = {'service': target} if target else None
        
        response = self.client.get('https://ids.xidian.edu.cn/authserver/login', params=params)
        
        if response.status_code == 401:
            raise PasswordWrongException("用户名或密码有误")
            
        if self._is_redirect(response):
            return self._complete_redirect(response, target, username)
            
        self._report_step("正在分析登录页面并注册安全特征...")
        self._register_browser_fingerprint()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        form_inputs = soup.find_all('input', type='hidden')
        
        pwd_encrypt_salt = None
        form_data = {
            'username': username,
            'rememberMe': 'true',
            'cllt': 'userNameLogin',
            'dllt': 'generalLogin',
            '_eventId': 'submit',
        }
        
        for inp in form_inputs:
            name = inp.get('name') or inp.get('id')
            val = inp.get('value', '')
            if name == 'pwdEncryptSalt':
                pwd_encrypt_salt = val
            elif name in ['lt', 'execution']:
                form_data[name] = val
                
        if not pwd_encrypt_salt:
            raise LoginFailedException("未能找到统一认证加密盐 (pwdEncryptSalt)")
            
        form_data['password'] = self._aes_encrypt_password(password, pwd_encrypt_salt)
        
        cookie_str = cookies_to_string(self.client.cookies, domain="ids.xidian.edu.cn")
        
        solver = SliderCaptchaSolver()
        solved = False

        if force_manual_captcha:
            self._report_step("用户选择手动验证，等待网页拖动拼图...")
            if getattr(self, 'on_captcha_needed', None):
                solver.update_puzzle(self.client, cookie_str)
                captcha_data = {
                    "big_image": base64.b64encode(solver.puzzle_data).decode("utf-8"),
                    "small_image": base64.b64encode(solver.piece_data).decode("utf-8"),
                }
                user_res = self.on_captcha_needed(captcha_data)
                if user_res and "move_length" in user_res:
                    move = user_res["move_length"]
                    for delta in [0, 1, -1, 2, -2]:
                        try_move = move + delta
                        tracks = solver.generate_tracks(try_move)
                        if solver.verify(self.client, cookie_str, tracks, solver.aes_key):
                            solved = True
                            break
        else:
            self._report_step("正在通过智能算法自动识别并破解滑块拼图...")
            try:
                solved = solver.solve(self.client, cookie_str)
            except CaptchaSolveFailedException:
                if getattr(self, 'on_captcha_needed', None):
                    self._report_step("自动识图未通过，切换为手动滑动验证...")
                    solver.update_puzzle(self.client, cookie_str)
                    captcha_data = {
                        "big_image": base64.b64encode(solver.puzzle_data).decode("utf-8"),
                        "small_image": base64.b64encode(solver.piece_data).decode("utf-8"),
                    }
                    user_res = self.on_captcha_needed(captcha_data)
                    if user_res and "move_length" in user_res:
                        move = user_res["move_length"]
                        for delta in [0, 1, -1, 2, -2]:
                            try_move = move + delta
                            tracks = solver.generate_tracks(try_move)
                            if solver.verify(self.client, cookie_str, tracks, solver.aes_key):
                                solved = True
                                break

        if not solved:
            raise LoginFailedException("滑块人机验证失败，请重试")
            
        self._report_step("✓ 滑块人机验证已通过！正在校验账号与密码...")
        response = self.client.post(
            'https://ids.xidian.edu.cn/authserver/login',
            params=params,
            data=form_data
        )
        
        if response.status_code == 401:
            raise PasswordWrongException("用户名或密码有误，请核对学号与密码")
            
        if self._is_redirect(response):
            save_cookies(self.client, self.data_dir)
            self._report_step("✓ 登录凭证有效，正在解析系统跳转...")
            return self._complete_redirect(response, target, username)
            
        soup = BeautifulSoup(response.text, 'html.parser')
        continue_form = soup.find('form', id='continue')
        if continue_form:
            inputs = continue_form.find_all('input')
            post_data = {inp.get('name'): inp.get('value') for inp in inputs if inp.get('name')}
            
            response = self.client.post('https://ids.xidian.edu.cn/authserver/login', data=post_data)
            if self._is_redirect(response):
                save_cookies(self.client, self.data_dir)
                return self._complete_redirect(response, target, username)
                
        raise LoginFailedException(f"登录失败，响应状态码：{response.status_code}")

    def get(self, url: str, **kwargs):
        resp = self.client.get(url, **kwargs)
        save_cookies(self.client, self.data_dir)
        return resp

    def post(self, url: str, **kwargs):
        resp = self.client.post(url, **kwargs)
        save_cookies(self.client, self.data_dir)
        return resp

    def check_and_login(self, target: str, username: str = None, password: str = None) -> str:
        logger.info(f"[IDSSession][check_and_login] Checking IDS session for {target}")
        response = self.client.get('https://ids.xidian.edu.cn/authserver/login', params={'service': target})
        
        user = username or getattr(self, 'username', '')
        pwd = password or getattr(self, 'password', '')

        if self._is_redirect(response):
            return self._complete_redirect(response, target, user)
            
        soup = BeautifulSoup(response.text, 'html.parser')
        continue_form = soup.find('form', id='continue')
        if continue_form:
            inputs = continue_form.find_all('input')
            post_data = {inp.get('name'): inp.get('value') for inp in inputs if inp.get('name')}
            response = self.client.post('https://ids.xidian.edu.cn/authserver/login', data=post_data)
            if self._is_redirect(response):
                return self._complete_redirect(response, target, user)
                
        if not user or not pwd:
            raise LoginFailedException("No active session and missing credentials")
            
        return self.login(user, pwd, target)

    def _is_redirect(self, response) -> bool:
        return response.status_code in (301, 302, 303, 307, 308)

    def _complete_redirect(self, response, target: str, username: str) -> str:
        location = response.headers.get('Location')
        if not location:
            raise Exception("统一认证跳转响应缺少 Location")
            
        resolved = urllib.parse.urljoin(str(response.url), location)
        return self._resolve_ids_reauth_if_needed(resolved, target, username)

    def _resolve_ids_reauth_if_needed(self, url: str, service: str, username: str) -> str:
        if not IDSReAuthClient.is_reauth_location(url):
            return url
            
        client = IDSReAuthClient(url)
        
        if getattr(self, 'on_mfa_needed', None):
            self._report_step("触发二次身份认证 (MFA)，请在网页中选择渠道并点击获取验证码...")
            recipient_desc = ""
            try:
                client.prepare(self.client, url, code_type="sms")
                recipient_desc = client.recipient_description or ""
            except Exception as e:
                logger.warning(f"预解析二次认证页面异常: {e}")

            message = "请选择验证码接收方式（手机短信或企业微信），点击【获取动态验证码】"
            if recipient_desc:
                message = f"绑定账号信息: {recipient_desc}。请选择接收渠道后点击【获取动态验证码】"
            
            res = self.on_mfa_needed({
                "client": client,
                "session": self.client,
                "username": username,
                "service": service,
                "message": message,
                "recipient": recipient_desc,
                "type": "sms",
                "code_sent": False
            })
            if not res:
                raise Exception("未输入二次认证验证码")
            if isinstance(res, str):
                code = res
                code_type = "sms"
            else:
                code = res.get("code", "")
                code_type = res.get("type", "sms")
            if not code:
                raise Exception("未输入二次认证验证码")
            self._report_step(f"正在提交二次认证动态码 ({'手机短信' if code_type == 'sms' else '企业微信'})...")
            resumed_url = client.submit_code(self.client, code, service, code_type=code_type)
            return resumed_url

        if not self.on_reauth_needed:
            raise Exception("登录需要二次认证，请打开应用后重试")
            
        reauth_event.clear()
        reauth_code_store.clear()
        
        self.on_reauth_needed(client, self.client, username, service)
        
        reauth_event.wait(timeout=300)
        if not reauth_event.is_set():
            raise Exception("二次认证超时")
            
        code = reauth_code_store.get('code')
        if not code:
            raise Exception("已取消二次认证")
            
        resumed_url = client.submit_code(self.client, code, service)
        return resumed_url

    def follow_ids_redirects(self, initial_location: str) -> object:
        current_url = urllib.parse.urljoin('https://ids.xidian.edu.cn', initial_location)
        redirect_count = 0
        
        while True:
            response = self.client.get(current_url)
            location = response.headers.get('Location')
            if not location:
                save_cookies(self.client, self.data_dir)
                return response
                
            redirect_count += 1
            if redirect_count > self.MAX_AUTH_REDIRECTS:
                raise LoginFailedException("统一认证跳转次数超过 30 次")
                
            next_url = urllib.parse.urljoin(str(response.url), location)
            parsed = urllib.parse.urlparse(next_url)
            service = urllib.parse.parse_qs(parsed.query).get('service', [None])[0]
            
            current_url = self._resolve_ids_reauth_if_needed(next_url, service, None)


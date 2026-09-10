import base64
import json
import unittest
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from core.crypto import (
    aes_encrypt_ids,
    aes_encrypt_captcha,
    aes_encrypt_energy,
)


class TestCrypto(unittest.TestCase):
    def test_aes_encrypt_ids(self):
        password = "MyTestPassword123"
        key = "1234567890123456"  # 16-byte salt
        encrypted_b64 = aes_encrypt_ids(password, key)
        self.assertTrue(len(encrypted_b64) > 0)

        # 解密验证
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv=b"xidianscriptsxdu")
        decrypted = cipher.decrypt(base64.b64decode(encrypted_b64))
        # Remove PKCS7 padding
        pad_len = decrypted[-1]
        raw = decrypted[:-pad_len].decode("utf-8")
        # 验证前缀和密码
        self.assertTrue(raw.startswith("xidianscriptsxdu" * 4))
        self.assertEqual(raw[len("xidianscriptsxdu" * 4):], password)

    def test_aes_encrypt_captcha(self):
        text = json.dumps({"canvasLength": 280, "moveLength": 120})
        key_bytes = b"abcdefghijklmnop"
        encrypted_b64 = aes_encrypt_captcha(text, key_bytes)
        self.assertTrue(len(encrypted_b64) > 0)

        # 解密验证：需要知道 IV。aes_encrypt_captcha 生成的 IV 来自随机串[64:80]
        # 虽然 IV 是随机生成的，但密文解密需要对应的 IV。
        # 验证输出为合法 base64
        decoded_bytes = base64.b64decode(encrypted_b64)
        self.assertEqual(len(decoded_bytes) % 16, 0)

    def test_aes_encrypt_energy(self):
        data = {"UserID": "21009200000", "NodeID": "12345"}
        encrypted_b64 = aes_encrypt_energy(data)

        # 解密验证
        key = b"1234567812345678"
        iv = b"1234567812345678"
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        decrypted = unpad(cipher.decrypt(base64.b64decode(encrypted_b64)), AES.block_size)
        recovered_data = json.loads(decrypted.decode("utf-8"))
        self.assertEqual(recovered_data, data)


class TestNetworkCookies(unittest.TestCase):
    def test_cookies_to_string_and_load_cookies_conflict_prevention(self):
        import tempfile
        import httpx
        from core.network import cookies_to_string, load_cookies, save_cookies

        with tempfile.TemporaryDirectory() as tmpdir:
            client = httpx.Client()
            client.cookies.set("route", "val1", domain="ids.xidian.edu.cn", path="/authserver")
            client.cookies.set("route", "val2", domain="ehall.xidian.edu.cn", path="/jwapp")
            client.cookies.set("JSESSIONID", "sess1", domain="ids.xidian.edu.cn", path="/")

            # Test save_cookies
            save_cookies(client, tmpdir)

            # Test cookies_to_string without error
            s_all = cookies_to_string(client.cookies)
            self.assertIn("route=val1", s_all)
            self.assertIn("route=val2", s_all)
            self.assertIn("JSESSIONID=sess1", s_all)

            s_ids = cookies_to_string(client.cookies, domain="ids.xidian.edu.cn")
            self.assertIn("route=val1", s_ids)
            self.assertNotIn("route=val2", s_ids)

            # Test load_cookies into a new client without CookieConflict
            new_client = httpx.Client()
            load_cookies(new_client, tmpdir)
            self.assertEqual(len(new_client.cookies.jar), 3)


if __name__ == "__main__":
    unittest.main()

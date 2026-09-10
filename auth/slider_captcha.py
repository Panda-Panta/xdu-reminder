import base64
import json
import math
import random
import time
from typing import List, Tuple, Optional
from PIL import Image
from io import BytesIO
import urllib.parse

from loguru import logger
from core.crypto import aes_encrypt_captcha

class CaptchaSolveFailedException(Exception):
    pass

class TrackPoint:
    def __init__(self, a: int, b: int, c: int):
        self.a = a
        self.b = b
        self.c = c

    def to_dict(self):
        return {'a': self.a, 'b': self.b, 'c': self.c}

class SliderCaptchaSolver:
    PUZZLE_WIDTH = 280
    PUZZLE_HEIGHT = 155
    PIECE_WIDTH = 44
    PIECE_HEIGHT = 155

    @staticmethod
    def solve_offset(puzzle_data: bytes, piece_data: bytes, border: int = 24) -> Optional[float]:
        try:
            puzzle = Image.open(BytesIO(puzzle_data)).convert("RGBA")
            piece = Image.open(BytesIO(piece_data)).convert("RGBA")
        except Exception as e:
            logger.error(f"Failed to decode images: {e}")
            return None

        xL, yT, xR, yB = piece.width, piece.height, 0, 0
        piece_pixels = piece.load()
        for y in range(piece.height):
            for x in range(piece.width):
                if piece_pixels[x, y][3] == 255:
                    if x < xL: xL = x
                    if y < yT: yT = y
                    if x > xR: xR = x
                    if y > yB: yB = y
        
        xL += border
        yT += border
        xR -= border
        yB -= border

        window_width = xR - xL + 1
        window_height = yB - yT + 1
        big_width = puzzle.width - piece.width + window_width

        puzzle_l = puzzle.convert("L")
        piece_l = piece.convert("L")
        
        puzzle_pixels = puzzle_l.load()
        piece_pixels = piece_l.load()
        
        def image_sum(img_pixels, start_x, start_y, w, h):
            s = 0.0
            for y in range(start_y, start_y + h):
                for x in range(start_x, start_x + w):
                    s += img_pixels[x, y]
            return s
            
        template_sum = image_sum(piece_pixels, xL, yT, window_width, window_height)
        template_mean = template_sum / (window_width * window_height)
        
        template = []
        for y in range(yT, yT + window_height):
            for x in range(xL, xL + window_width):
                template.append(piece_pixels[x, y] - template_mean)

        column_sums = []
        for x in range(big_width):
            column_sums.append(image_sum(puzzle_pixels, x + xL, yT, 1, window_height))
            
        window_sum = sum(column_sums[:window_width])
        area = window_width * window_height
        
        def image_ncc(img_pixels, start_x, start_y, w, h, tpl, mean_w):
            sum_wt = 0.0
            sum_ww = 0.000001
            idx = 0
            for y in range(start_y, start_y + h):
                for x in range(start_x, start_x + w):
                    w_val = img_pixels[x, y] - mean_w
                    sum_wt += w_val * tpl[idx]
                    sum_ww += w_val * w_val
                    idx += 1
            return sum_wt / sum_ww

        ncc_max = image_ncc(puzzle_pixels, xL, yT, window_width, window_height, template, window_sum / area)
        x_max = 0
        
        for x in range(1, big_width - window_width):
            window_sum += column_sums[x + window_width - 1] - column_sums[x - 1]
            ncc = image_ncc(puzzle_pixels, x + xL, yT, window_width, window_height, template, window_sum / area)
            if ncc > ncc_max:
                ncc_max = ncc
                x_max = x
                
        return x_max / puzzle.width

    @staticmethod
    def generate_tracks(offs: int) -> List[TrackPoint]:
        tracks = [TrackPoint(0, 0, 0)]
        n = random.randint(10, 14)
        b = 0
        
        gen_tracks_norm = 1.0 / (1.0 + math.exp(-7.0 * (1.0 - 0.42)))
        
        for i in range(n):
            z = (1.0 / (1.0 + math.exp(-7.0 * ((i / n) - 0.42)))) / gen_tracks_norm
            a_calc = round(offs * z)
            a = min(offs - 1, max(tracks[-1].a + 1, a_calc))
            
            r = random.random()
            if r < 0.65:
                b -= 1
            elif r < 0.80:
                b += 1
            b = max(-10, min(10, b))
            
            tracks.append(TrackPoint(a, b, random.randint(300, 500)))
            
        tracks.append(TrackPoint(offs, b, random.randint(300, 500)))
        return tracks

    def __init__(self):
        self.puzzle_data = None
        self.piece_data = None
        self.aes_key = None

    def update_puzzle(self, session, cookie_str: str):
        logger.info("Fetching slider captcha...")
        ts = str(int(time.time() * 1000))
        rsp = session.get(
            "https://ids.xidian.edu.cn/authserver/common/openSliderCaptcha.htl",
            params={'_': ts},
            headers={"Cookie": cookie_str}
        )
        rsp.raise_for_status()
        data = rsp.json()
        
        puzzle_base64 = data["bigImage"]
        piece_base64 = data["smallImage"]
        
        self.puzzle_data = base64.b64decode(puzzle_base64)
        self.piece_data = base64.b64decode(piece_base64)
        self.aes_key = self.piece_data[-16:]

    def verify(self, session, cookie_str: str, tracks: List[TrackPoint], aes_key: bytes) -> bool:
        payload = json.dumps({
            "canvasLength": self.PUZZLE_WIDTH,
            "moveLength": tracks[-1].a if tracks else 0,
            "tracks": [t.to_dict() for t in tracks]
        }, separators=(',', ':'))
        
        sign = aes_encrypt_captcha(payload, aes_key)
        data = f"sign={urllib.parse.quote(sign)}"
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Cookie": cookie_str,
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Origin": "https://ids.xidian.edu.cn",
            "X-Requested-With": "XMLHttpRequest"
        }
        
        rsp = session.post(
            "https://ids.xidian.edu.cn/authserver/common/verifySliderCaptcha.htl",
            data=data,
            headers=headers
        )
        rsp.raise_for_status()
        res_data = rsp.json()
        logger.info(f"Tried captcha payload:{payload}, result:{res_data}")
        return res_data.get("errorCode") == 1

    def solve(self, session, cookie_str: str) -> bool:
        logger.info("Solving slider captcha automatically")
        for i in range(6):
            self.update_puzzle(session, cookie_str)
            offset = self.solve_offset(self.puzzle_data, self.piece_data)
            if offset is None:
                raise CaptchaSolveFailedException("Failed to calculate offset")
                
            base_move = round(offset * self.PUZZLE_WIDTH)
            
            for delta in [1, -1, 2, -2, 3, -3, 4]:
                move = base_move + delta
                if move < 0 or move > self.PUZZLE_WIDTH:
                    continue
                    
                tracks = self.generate_tracks(move)
                
                delay_ms = max(tracks[-1].c - 100, 0)
                time.sleep(delay_ms / 1000.0)
                
                try:
                    if self.verify(session, cookie_str, tracks, self.aes_key):
                        return True
                except Exception as e:
                    logger.warning(f"Verification request failed: {e}")
                    
        raise CaptchaSolveFailedException("Failed to solve captcha after 6 rounds")

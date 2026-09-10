import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from loguru import logger
from datetime import datetime, timedelta

@dataclass
class ExamSubject:
    subject: str
    type_str: str
    time_str: str
    place: str
    seat: str = ''
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

@dataclass
class ExamData:
    subjects: List[ExamSubject] = field(default_factory=list)
    to_be_arranged: List[dict] = field(default_factory=list)

class ExamService:
    def __init__(self, ids_session, data_dir: str):
        self.ids_session = ids_session
        self.cache_file = os.path.join(data_dir, 'cache', 'exam.json')
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def fetch(self, semester_code: str) -> ExamData:
        try:
            location = self.ids_session.check_and_login(target='https://ehall.xidian.edu.cn/appShow?appId=4768687067472349')
            if location:
                self.ids_session.follow_ids_redirects(location)
            
            res = self.ids_session.post(
                'https://ehall.xidian.edu.cn/jwapp/sys/studentWdksapApp/modules/wdksap/wdksap.do',
                data={'XNXQDM': semester_code, '*order': '-KSRQ,-KSSJMS'}
            )
            if res.status_code != 200:
                raise Exception(f"获取考试安排失败 HTTP {res.status_code}: {res.text[:200]}")
            res_json = res.json()
            rows = res_json.get('datas', {}).get('wdksap', {}).get('rows') or []
            
            data = ExamData()
            
            time_pattern = re.compile(r'(\d+)-(\d+)-(\d+) (\d+)[::](\d+)-(\d+)[::](\d+)')
            
            for row in rows:
                time_str = row.get('KSSJMS', '')
                subj = ExamSubject(
                    subject=row.get('KCM', ''),
                    type_str=row.get('KSMC', ''),
                    time_str=time_str,
                    place=row.get('JASMC', ''),
                    seat=row.get('ZWH', '')
                )
                
                match = time_pattern.search(time_str)
                if match:
                    y, M, d, H1, m1, H2, m2 = map(int, match.groups())
                    subj.start_time = datetime(y, M, d, H1, m1)
                    subj.end_time = datetime(y, M, d, H2, m2)
                    
                data.subjects.append(subj)
                
            res_tba = self.ids_session.post(
                'https://ehall.xidian.edu.cn/jwapp/sys/studentWdksapApp/modules/wdksap/cxyxkwapkwdkc.do',
                data={'XNXQDM': semester_code}
            )
            data.to_be_arranged = res_tba.json().get('datas', {}).get('cxyxkwapkwdkc', {}).get('rows') or []
            
            def date_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError("Type not serializable")
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(data), f, default=date_serializer, ensure_ascii=False, indent=2)
                
            return data
        except Exception as e:
            logger.error(f"获取考试信息失败: {e}")
            raise

    def get_upcoming_exams(self, data: ExamData, hours_ahead=48) -> List[ExamSubject]:
        now = datetime.now()
        upcoming = []
        for subj in data.subjects:
            if subj.start_time and now <= subj.start_time <= now + timedelta(hours=hours_ahead):
                upcoming.append(subj)
        return upcoming

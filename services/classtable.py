import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from loguru import logger
from datetime import datetime, timedelta

@dataclass
class ClassDetail:
    name: str
    code: str = ''
    number: str = ''

@dataclass
class TimeArrangement:
    index: int
    week_list: List[bool]
    day: int
    start: int
    stop: int
    classroom: str = ''
    teacher: str = ''

@dataclass
class ClassTableData:
    semester_code: str = ''
    term_start_day: str = ''
    semester_length: int = 1
    class_details: List[ClassDetail] = field(default_factory=list)
    time_arrangements: List[TimeArrangement] = field(default_factory=list)
    not_arranged: List[dict] = field(default_factory=list)

TIME_LIST = [
    '08:30', '09:15',  # Period 1
    '09:20', '10:05',  # Period 2
    '10:25', '11:10',  # Period 3
    '11:15', '12:00',  # Period 4
    '14:00', '14:45',  # Period 5
    '14:50', '15:35',  # Period 6
    '15:55', '16:40',  # Period 7
    '16:45', '17:30',  # Period 8
    '19:00', '19:45',  # Period 9
    '19:55', '20:35',  # Period 10
    '20:40', '21:25',  # Period 11
]

def get_period_start_time(period: int) -> str:
    return TIME_LIST[(period - 1) * 2]

def get_period_end_time(period: int) -> str:
    return TIME_LIST[(period - 1) * 2 + 1]

class ClassTableService:
    def __init__(self, ids_session, data_dir: str):
        self.ids_session = ids_session
        self.cache_file = os.path.join(data_dir, 'cache', 'classtable.json')
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)

    def fetch(self, semester_code: str, username: str) -> ClassTableData:
        try:
            location = self.ids_session.check_and_login(target='https://ehall.xidian.edu.cn/appShow?appId=4770397878132218')
            if location:
                self.ids_session.follow_ids_redirects(location)
            
            # 1. 获取学期开始日期
            parts = semester_code.split('-')
            XN = f"{parts[0]}-{parts[1]}"
            XQ = parts[2]
            res_jcs = self.ids_session.post('https://ehall.xidian.edu.cn/jwapp/sys/wdkb/modules/jshkcb/cxjcs.do', data={'XN': XN, 'XQ': XQ})
            if res_jcs.status_code != 200:
                raise Exception(f"获取学期基础信息失败 HTTP {res_jcs.status_code}: {res_jcs.text[:200]}")
            term_start_raw = res_jcs.json()['datas']['cxjcs']['rows'][0]['XQKSRQ']
            term_start_day = str(term_start_raw).strip().split()[0]
            
            # 2. 获取课程表
            res_kcb = self.ids_session.post('https://ehall.xidian.edu.cn/jwapp/sys/wdkb/modules/xskcb/xskcb.do', data={'XNXQDM': semester_code, 'XH': username})
            if res_kcb.status_code != 200:
                raise Exception(f"获取课程表失败 HTTP {res_kcb.status_code}: {res_kcb.text[:200]}")
            rows = res_kcb.json()['datas']['xskcb']['rows']
            
            data = ClassTableData(semester_code=semester_code, term_start_day=term_start_day)
            
            for row in rows:
                cd = ClassDetail(name=row.get('KCM', ''), code=row.get('KCH', ''), number=row.get('KXH', ''))
                if cd not in data.class_details:
                    data.class_details.append(cd)
                idx = data.class_details.index(cd)
                
                week_str = str(row.get('SKZC', ''))
                week_list = [c == '1' for c in week_str]
                if len(week_list) > data.semester_length:
                    data.semester_length = len(week_list)
                
                ta = TimeArrangement(
                    index=idx,
                    week_list=week_list,
                    day=int(row.get('SKXQ', 0)),
                    start=int(row.get('KSJC', 0)),
                    stop=int(row.get('JSJC', 0)),
                    classroom=row.get('JASMC', ''),
                    teacher=row.get('SKJS', '')
                )
                data.time_arrangements.append(ta)
            
            # 3. 未排课程
            res_not_arranged = self.ids_session.post('https://ehall.xidian.edu.cn/jwapp/sys/wdkb/modules/xskcb/cxxsllsywpk.do', data={'XNXQDM': semester_code, 'XH': username})
            data.not_arranged = res_not_arranged.json()['datas']['cxxsllsywpk']['rows']
            
            # 4. 调课信息
            res_change = self.ids_session.post('https://ehall.xidian.edu.cn/jwapp/sys/wdkb/modules/xskcb/xsdkkc.do', data={'XNXQDM': semester_code, '*order': '-SQSJ'})
            changes = res_change.json()['datas']['xsdkkc']['rows']
            
            for change in changes:
                tklxdm = change.get('TKLXDM')
                orig_code = change.get('KCH', '')
                orig_week = int(change.get('SKXQ', 0)) if change.get('SKXQ') else None
                orig_start = int(change.get('KSJC', 0)) if change.get('KSJC') else None
                orig_stop = int(change.get('JSJC', 0)) if change.get('JSJC') else None
                
                new_week = int(change.get('XSKXQ', 0)) if change.get('XSKXQ') else None
                new_start = int(change.get('XKSJC', 0)) if change.get('XKSJC') else None
                new_stop = int(change.get('XJSJC', 0)) if change.get('XJSJC') else None
                
                orig_affected = [c == '1' for c in str(change.get('SKZC', ''))] if change.get('SKZC') else []
                new_affected = [c == '1' for c in str(change.get('XSKZC', ''))] if change.get('XSKZC') else []
                
                # 寻找对应的 TimeArrangement
                matches = []
                for ta in data.time_arrangements:
                    cd = data.class_details[ta.index]
                    if cd.code == orig_code and ta.day == orig_week and ta.start == orig_start and ta.stop == orig_stop:
                        matches.append(ta)
                
                if tklxdm == '02': # 停课
                    for ta in matches:
                        for w_idx in range(min(len(ta.week_list), len(orig_affected))):
                            if orig_affected[w_idx]:
                                ta.week_list[w_idx] = False
                elif tklxdm == '01': # 调课
                    for ta in matches:
                        for w_idx in range(min(len(ta.week_list), len(orig_affected))):
                            if orig_affected[w_idx]:
                                ta.week_list[w_idx] = False
                    
                    if matches:
                        cd_idx = matches[0].index
                        new_ta = TimeArrangement(
                            index=cd_idx,
                            week_list=new_affected,
                            day=new_week or 0,
                            start=new_start or 0,
                            stop=new_stop or 0,
                            classroom=change.get('XJASMC', ''),
                            teacher=change.get('XSKJS', '') or change.get('YSKJS', '')
                        )
                        data.time_arrangements.append(new_ta)
                elif tklxdm == '03': # 补课
                    cd_idx = None
                    for i, cd in enumerate(data.class_details):
                        if cd.code == orig_code:
                            cd_idx = i
                            break
                    if cd_idx is None:
                        new_cd = ClassDetail(name=change.get('KCM', ''), code=orig_code, number=change.get('KXH', ''))
                        data.class_details.append(new_cd)
                        cd_idx = len(data.class_details) - 1
                    
                    new_ta = TimeArrangement(
                        index=cd_idx,
                        week_list=new_affected or orig_affected,
                        day=new_week or orig_week or 0,
                        start=new_start or orig_start or 0,
                        stop=new_stop or orig_stop or 0,
                        classroom=change.get('XJASMC', '') or change.get('JASMC', ''),
                        teacher=change.get('XSKJS', '') or change.get('YSKJS', '')
                    )
                    data.time_arrangements.append(new_ta)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(asdict(data), f, ensure_ascii=False, indent=2)
            
            return data
        except Exception as e:
            logger.error(f"获取课表失败: {e}")
            raise
    
    def get_cache(self) -> Optional[ClassTableData]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    data = ClassTableData(**d)
                    data.class_details = [ClassDetail(**c) for c in data.class_details]
                    data.time_arrangements = [TimeArrangement(**t) for t in data.time_arrangements]
                    return data
            except Exception as e:
                logger.error(f"读取课表缓存失败: {e}")
        return None
    
    def get_today_classes(self, data: ClassTableData) -> List[dict]:
        try:
            if not data or not data.term_start_day:
                return []
            term_str = str(data.term_start_day).strip().split()[0]
            start_date = datetime.strptime(term_str, '%Y-%m-%d')
            now = datetime.now()
            days_diff = (now - start_date).days
            current_week = days_diff // 7
            current_weekday = now.isoweekday()
            
            today_classes = []
            for ta in data.time_arrangements:
                if ta.day == current_weekday and 0 <= current_week < len(ta.week_list) and ta.week_list[current_week]:
                    cd = data.class_details[ta.index]
                    today_classes.append({
                        'name': cd.name,
                        'classroom': ta.classroom,
                        'teacher': ta.teacher,
                        'start_time': get_period_start_time(ta.start),
                        'end_time': get_period_end_time(ta.stop),
                        'period_start': ta.start,
                        'period_end': ta.stop
                    })
            return today_classes
        except Exception as e:
            logger.error(f"计算今日课程失败: {e}")
            return []

from loguru import logger

class SemesterService:
    def __init__(self, ids_session):
        self.ids_session = ids_session

    def get_current_semester(self) -> str:
        try:
            location = self.ids_session.check_and_login(target='https://ehall.xidian.edu.cn/appShow?appId=4770397878132218')
            if location:
                self.ids_session.follow_ids_redirects(location)
            response = self.ids_session.post('https://ehall.xidian.edu.cn/jwapp/sys/wdkb/modules/jshkcb/dqxnxq.do')
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            data = response.json()
            return data['datas']['dqxnxq']['rows'][0]['DM']
        except Exception as e:
            logger.error(f"获取当前学期失败: {e}")
            raise

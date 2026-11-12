import unittest

from backend.social_sources import TITLE, access_state, count, parse_douban, parse_weibo, parse_baidu_charts


class SocialSourceTests(unittest.TestCase):
    def test_display_units_and_invalid_values(self):
        self.assertEqual(count('3.6亿'),360000000)
        self.assertEqual(count('287.3万'),2873000)
        for value in ('暂无','3.2万+',True,float('nan'),'1次'):
            self.assertIsNone(count(value))

    def test_unrated_subject_never_borrows_recommendation_score(self):
        html=f'''<h1><span property="v:itemreviewed">{TITLE}</span></h1>
        <div id="interest_sectl"><strong property="v:average"></strong>暂无评分</div>
        <div id="comments-section"><h2><a href="comments">全部 3,114 条</a></h2></div>
        <div id="subject-others-interests">3203人在看 / 4791人看过 / 9413人想看</div>
        <div class="recommendations"><span property="v:average">8.8</span></div>'''
        result={r['metric']:r for r in parse_douban(html)}
        self.assertIsNone(result['rating']['value'])
        self.assertEqual(result['short_comments']['value'],3114)
        self.assertEqual(result['watching']['value'],3203)
        self.assertEqual(result['wish']['value'],9413)
        self.assertEqual(parse_douban(html.replace(TITLE,'其他剧')),[])

    def test_topic_requires_exact_title_and_official_account_verification(self):
        packet={'url':'https://m.weibo.cn/api/container/getIndex','data':{'ok':1,'data':{
            'cardlistInfo':{'cardlist_head_cards':[
                {'head_data':{'title':f'#{TITLE}#','midtext':'阅读量3.6亿 讨论量287.3万'}},
                {'head_data':{'title':'#其他话题#','midtext':'阅读量9亿 讨论量9亿'}},
            ]},'cards':[
                {'user':{'screen_name':TITLE+'官微','verified_reason':f'《{TITLE}》官方微博','id':123,'followers_count':'10.6万','statuses_count':169}},
                {'user':{'screen_name':TITLE+'官微','verified_reason':'非官方','id':999,'followers_count':'9亿'}},
            ]}}}
        result={r['metric']:r for r in parse_weibo([packet])}
        self.assertEqual(result['topic_reads']['value'],360000000)
        self.assertEqual(result['official_followers']['value'],106000)
        self.assertEqual(result['official_followers']['source_url'],'https://m.weibo.cn/u/123')
        self.assertEqual(result['topic_discussions']['metadata']['raw'],'287.3万')

    def test_verification_and_login_are_distinct(self):
        state,_=access_state('douyin','https://www.douyin.com/','','<script src="captcha/index.js"></script>',[])
        self.assertEqual(state,'verification_required')
        packet={'url':'https://index.baidu.com/Interface/api/pcPass','data':{'data':{'result':{'isLogin':0}}}}
        state,_=access_state('baidu_index','https://index.baidu.com/','', '',[packet])
        self.assertEqual(state,'login_required')
        state,_=access_state('baidu_index','https://index.baidu.com/','热门词推荐', '',[])
        self.assertEqual(state,'adapter_pending')

    def test_baidu_requires_matching_series_and_real_dates(self):
        charts=[{'dates':['2026-11-08','2026-02-30','2026-11-09'], 'series':[
            {'name':'其他关键词','data':[999,999,999]},
            {'name':TITLE,'data':[1234,9876,None]},
        ]}]
        rows=parse_baidu_charts(charts,'https://index.baidu.com/')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['value'],1234)
        self.assertEqual(rows[0]['source_time'],'2026-11-08')


if __name__=='__main__':
    unittest.main()

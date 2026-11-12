import unittest
from backend.mango_metrics import parse_play_count


def page(raw='3.6亿',field='3.6亿',title='今天是太阳雨',icon='hitv-play'):
    return f'<div class="content"><h1 class="title">{title}</h1><div class="tags"><span class="tag"><i class="{icon}"></i>{raw}</span></div></div><aside>其他剧集9.9亿</aside><script>var detail={{playCnt:"{field}"}}</script>'


class MangoPlayTests(unittest.TestCase):
    def test_header_count_is_confirmed_and_precision_preserved(self):
        result=parse_play_count(page(),'今天是太阳雨')
        self.assertEqual(result['value'],360000000)
        self.assertEqual(result['raw'],'3.6亿')
        self.assertEqual(result['field'],'detail.playCnt')
        self.assertIn('取整',result['precision'])
        self.assertEqual(parse_play_count(page('985万','985万'),'今天是太阳雨')['value'],9850000)

    def test_unlabelled_wrong_drama_or_mismatched_values_are_rejected(self):
        for html in [page(title='其他剧集'),page(icon='heat'),page(field='4.2亿'),page(raw='暂无数据'),page()+page()]:
            self.assertIsNone(parse_play_count(html,'今天是太阳雨'))


if __name__=='__main__':unittest.main()

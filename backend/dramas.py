from urllib.parse import quote

PRIMARY = '今天是太阳雨'
COMPARISON = '折月亮'
DRAMAS = (PRIMARY, COMPARISON)
WEIBO_TOPICS = {PRIMARY: PRIMARY, COMPARISON: '剧集折月亮'}
DOUBAN_SUBJECTS = {
    PRIMARY: 'https://movie.douban.com/subject/36689621/',
    COMPARISON: 'https://movie.douban.com/subject/36809913/',
}
MANGO_PAGES = {PRIMARY: 'https://www.mgtv.com/h/817372.html'}
DOUYIN_RANK_URL = 'https://www.douyin.com/search/' + quote('剧集榜') + '?type=general'


def weibo_search(title):
    return 'https://m.weibo.cn/search?containerid=' + quote('100103type=1&q=' + title, safe='')


def weibo_topic(title):
    topic = WEIBO_TOPICS.get(title, title)
    return 'https://m.weibo.cn/search?containerid=' + quote('231522type=1&t=10&q=#' + topic + '#', safe='')


def baidu_index(title):
    return 'https://index.baidu.com/v2/main/index.html#/trend/' + quote(title) + '?words=' + quote(title)


def source_url(source, title, fallback=''):
    return {
        'weibo': weibo_topic(title), 'douban': DOUBAN_SUBJECTS[title],
        'douyin': DOUYIN_RANK_URL,
        'xiaohongshu': 'https://www.xiaohongshu.com/search_result?keyword=' + quote(title),
        'baidu_index': baidu_index(title),
        'mango': MANGO_PAGES.get(title, 'https://so.mgtv.com/so?k=' + quote(title)),
    }.get(source, fallback)

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from store import connect, save_quotes, product_view, PRODUCTS, stamp, now, demo_products
from collectors import danawa_products, danawa_quotes, bestbuy_quotes, ebay_quotes, matches, parse_news, update_news, update_prices, import_feed
from server import preferred_lang, default_market, render_page, prices_due


class Prices(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.tmp.name)/'test.sqlite3')
        self.at = now().replace(microsecond=0)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def quote(self, **kwargs):
        return {'product_id':PRODUCTS[0]['id'],'market':'KR','offer_key':'sku-a','price':100000,
            'shipping':None,'stock':'in_stock','merchant':'Seller','title':'Test product',
            'url':'https://example.com/item','source':'test','observed_at':stamp(self.at),**kwargs}

    def view(self):
        return product_view(self.db, PRODUCTS[0], 'KR', self.at)

    def test_stale_and_sold_out_never_win(self):
        save_quotes(self.db,[self.quote(price=1, observed_at=stamp(self.at-dt.timedelta(days=2))),
            self.quote(price=2,stock='out_of_stock'),self.quote(offer_key='b',price=120000)])
        self.assertEqual(self.view()['price'],120000)

    def test_stale_only_has_no_current_price(self):
        save_quotes(self.db,[self.quote(observed_at=stamp(self.at-dt.timedelta(hours=37)))])
        self.assertIsNone(self.view()['price'])
        self.assertEqual(len(self.view()['history']),1)

    def test_zero_and_mixed_market_rejected(self):
        for row in [self.quote(price=0),self.quote(market='UK'),self.quote(price=float('nan')),
                    self.quote(price=-5), self.quote(price=True),self.quote(url='javascript:alert(1)')]:
            with self.assertRaises(ValueError):save_quotes(self.db,[row])

    def test_atomic_import(self):
        with self.assertRaises(ValueError):save_quotes(self.db,[self.quote(),self.quote(product_id='untracked')])
        self.assertEqual(self.db.execute('select count(*) from prices').fetchone()[0],0)

    def test_duplicate_and_currency_separation(self):
        row=self.quote()
        self.assertEqual(save_quotes(self.db,[row,row]),1)
        save_quotes(self.db,[self.quote(market='US',price=12345)])
        self.assertEqual(self.view()['price'],100000)
        self.assertEqual(product_view(self.db,PRODUCTS[0],'US',self.at)['price'],123.45)

    def test_24h_change_uses_observation_before_daily_rollup(self):
        save_quotes(self.db,[self.quote(price=100000,observed_at=stamp(self.at-dt.timedelta(hours=25))),
            self.quote(price=110000,observed_at=stamp(self.at-dt.timedelta(hours=23))),
            self.quote(price=90000)])
        self.assertEqual(self.view()['change'],-10)

    def test_single_point_has_no_invented_change(self):
        save_quotes(self.db,[self.quote()])
        self.assertIsNone(self.view()['change'])
        self.assertEqual(len(self.view()['history']),1)

    def test_future_observation_rejected(self):
        with self.assertRaises(ValueError):save_quotes(self.db,[self.quote(observed_at=stamp(self.at+dt.timedelta(days=1)))])

    def test_demo_does_not_write_live_database(self):
        self.assertEqual(len(demo_products('US')),10)
        self.assertIsNone(self.view()['price'])

    def test_feed_keeps_original_observation_time(self):
        old=stamp(self.at-dt.timedelta(days=3))
        import_feed(self.db,{'observations':[self.quote(observed_at=old)]})
        self.assertEqual(self.view()['observed_at'],old)
        self.assertIsNone(self.view()['price'])


class Providers(unittest.TestCase):
    def test_product_matching_excludes_wrong_variant(self):
        gpu=next(p for p in PRODUCTS if p['id']=='rtx-5070')
        self.assertTrue(matches(gpu,'MSI 지포스 RTX 5070 12GB'))
        for title in ['RTX 5070 Ti 12GB','RTX 5070 12GB 중고','RTX 5070 12GB 조립PC','RTX 5070 12GB 노트북']:
            self.assertFalse(matches(gpu,title))
        ram=PRODUCTS[1]
        self.assertFalse(matches(ram,'삼성 DDR5 5600 16GB 2개'))
        self.assertFalse(matches(ram,'삼성 DDR5 5600 16GB ECC 서버'))
        self.assertTrue(matches(ram,'삼성전자 DDR5-5600 16GB'))

    def test_danawa_keeps_new_catalog_items_in_category_with_enough_shops(self):
        gpu=next(p for p in PRODUCTS if p['id']=='rtx-5080')
        def item(code,name,price,shops=30,cat=972,status='가격비교'):
            return {'productSeq':code,'productName':name,'bundleName':'','minPrice':price,'shopCount':shops,'categorySeq3':cat,'priceCompareStatusType':status}
        items=[item('1','PALIT 지포스 <b>RTX 5080</b> D7 16GB',2600000),item('2','GIGABYTE 지포스 RTX 5080 D7 16GB',2539000),
               item('3','PNY 지포스 RTX 5080 D7 16GB',2400000,shops=1),item('TH201_9','RTX 5080 교체용 쿨러 16GB',88000),
               item('4','GIGABYTE AORUS RTX 5080 AI BOX 16GB',2000000,cat=975),item('5','MSI 지포스 RTX 5080 16GB 중고',1900000),
               item('6','MSI 지포스 RTX 5080 Ti 16GB',0)]
        rows=danawa_quotes(gpu,items)
        self.assertEqual([r['offer_key'] for r in rows],['2','1'])
        self.assertEqual((rows[0]['price'],rows[0]['shops'],rows[0]['url']),(2539000,30,'https://prod.danawa.com/info/?pcode=2'))

    def test_danawa_ram_uses_bundle_capacity_and_overrides(self):
        ram=next(p for p in PRODUCTS if p['id']=='samsung-ddr5-16')
        kit=next(p for p in PRODUCTS if p['id']=='corsair-ddr5-32')
        def item(code,name,bundle):
            return {'productSeq':code,'productName':name,'bundleName':bundle,'minPrice':100,'shopCount':9,'categorySeq3':221725,'priceCompareStatusType':'가격비교'}
        self.assertEqual(len(danawa_quotes(ram,[item('1','삼성전자 DDR5-5600','16GB'),item('2','삼성전자 노트북 DDR5-5600','16GB'),item('3','삼성전자 DDR5-5600','32GB')])),1)
        rows=danawa_quotes(kit,[item('1','CORSAIR DDR5-6000 CL30 VENGEANCE RGB 패키지','32GB(16Gx2)'),item('2','CORSAIR DDR5-6000 CL30 VENGEANCE 패키지','32GB(16Gx2)')])
        self.assertEqual([r['offer_key'] for r in rows],['2'])

    def test_danawa_page_parsing_and_layout_change(self):
        flight=json.dumps('17:{"data":{"products":[{"productSeq":"7","minPrice":5}],"x":1}}')[1:-1]
        page=f'<script>self.__next_f.push([1,"{flight}"])</script>'.encode()
        self.assertEqual(danawa_products(page),[{'productSeq':'7','minPrice':5}])
        with self.assertRaises(ValueError):danawa_products(b'<html>changed</html>')

    def test_bestbuy_converts_dollars_to_cents_and_stock(self):
        gpu=next(p for p in PRODUCTS if p['id']=='rtx-5070')
        data={'products':[{'sku':1,'name':'NVIDIA GeForce RTX 5070 12GB GDDR7','salePrice':549.99,'onlineAvailability':True,'url':'https://www.bestbuy.com/site/1.p'},
                          {'sku':2,'name':'ASUS GeForce RTX 5070 Ti 16GB','salePrice':749.99,'onlineAvailability':True,'url':'https://www.bestbuy.com/site/2.p'},
                          {'sku':3,'name':'MSI GeForce RTX 5070 12GB','salePrice':529.0,'onlineAvailability':False,'url':'https://www.bestbuy.com/site/3.p'}]}
        rows=bestbuy_quotes(gpu,data)
        self.assertEqual([(r['offer_key'],r['price'],r['stock']) for r in rows],[('3',52900,'out_of_stock'),('1',54999,'in_stock')])

    def test_news_filters_relevance_dates_and_urls(self):
        import email.utils
        date=email.utils.format_datetime(now())
        def item(title,link='https://example.com/article',date=date):
            return f'<item><title>{title} - Publisher</title><link>{link}</link><source>Publisher</source><pubDate>{date}</pubDate></item>'
        raw=('<rss><channel>'+item('RTX 5070 price update')+item('Apple phone update')+item('RTX 5080 price',link='javascript:bad')+item('RTX 5090 price',date='Wed, 01 Jan 2020 00:00:00 GMT')+'</channel></rss>').encode()
        rows=parse_news(raw,'en','gpu')
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][3],'RTX 5070 price update')

    def test_daily_news_is_idempotent_and_failure_preserves_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory)/'test.db') as db:
                with patch('collectors.fetch',return_value=b'<rss><channel></channel></rss>') as request:
                    update_news(db)
                    update_news(db)
                    self.assertEqual(request.call_count,4)
                with patch('collectors.fetch',side_effect=TimeoutError):
                    update_news(db,force=True)
                self.assertEqual(db.execute("select count(*) from runs where state='error' and succeeded_at is not null").fetchone()[0],4)


class SevenDay(unittest.TestCase):
    def test_change7_compares_with_close_seven_days_ago(self):
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory)/'test.db') as db:
                at=now().replace(microsecond=0)
                base={'product_id':PRODUCTS[0]['id'],'market':'KR','offer_key':'a','shipping':None,'stock':'in_stock',
                      'merchant':'Seller','title':'t','url':'https://example.com/a','source':'test'}
                save_quotes(db,[base|{'price':100000,'observed_at':stamp(at-dt.timedelta(days=7))},base|{'price':95000,'observed_at':stamp(at)}])
                self.assertEqual(product_view(db,PRODUCTS[0],'KR',at)['change7'],-5)
                self.assertIsNotNone(demo_products('KR')[0]['change7'])

    def test_update_prices_waits_between_requests_and_isolates_failures(self):
        flight=json.dumps('1:{"products":[{"productSeq":"9","productName":"삼성전자 DDR5-5600","bundleName":"16GB","minPrice":349690,"shopCount":303,"categorySeq3":221725,"priceCompareStatusType":"가격비교"}]}')[1:-1]
        page=f'<script>self.__next_f.push([1,"{flight}"])</script>'.encode()
        calls=[]
        def fake_fetch(url,headers=None):
            calls.append(url)
            if len(calls)==3: raise TimeoutError  # third product fails
            return page
        waits=[]
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory)/'test.db') as db:
                with patch('collectors.fetch',side_effect=fake_fetch), patch.dict('os.environ',{},clear=False):
                    import os; os.environ.pop('BESTBUY_API_KEY',None); os.environ.pop('PRICE_FEED_URL',None)
                    result=update_prices(db,sleep=waits.append)
                self.assertEqual(len(calls),len(PRODUCTS))
                self.assertEqual(waits,[10]*(len(PRODUCTS)-1))
                self.assertEqual(result[0]['matched']['samsung-ddr5-16'],1)
                self.assertIn('TimeoutError',result[0]['error'])
                self.assertEqual(db.execute("select state from runs where job='prices:danawa'").fetchone()[0],'error')

    def test_ebay_keeps_new_fixed_price_items_from_rated_sellers(self):
        gpu=next(p for p in PRODUCTS if p['id']=='rtx-5080')
        def item(i,title,price,score=500,pct='99.5',cond='1000',ship='0.00'):
            return {'itemId':f'v1|{i}|0','title':title,'price':{'value':price,'currency':'USD'},'conditionId':cond,
                    'seller':{'username':'someone','feedbackScore':score,'feedbackPercentage':pct},
                    'shippingOptions':[{'shippingCost':{'value':ship,'currency':'USD'}}],'itemWebUrl':f'https://www.ebay.com/itm/{i}'}
        data={'itemSummaries':[item(1,'MSI GeForce RTX 5080 16GB GDDR7 Ventus','1299.99'),
            item(2,'ZOTAC RTX 5080 16GB Solid','1249.00',ship='15.50'),
            item(3,'RTX 5080 16GB Founders Edition BOX ONLY','150.00'),
            item(4,'ASUS RTX 5080 16GB TUF','999.00',score=3),
            item(5,'Gigabyte RTX 5080 16GB Gaming','1100.00',cond='3000'),
            item(6,'PNY RTX 5080 Ti 16GB laptop','900.00')]}
        rows=ebay_quotes(gpu,data)
        self.assertEqual([(r['offer_key'],r['price'],r['shipping']) for r in rows],[('v1|2|0',124900,1550),('v1|1|0',129999,0)])
        self.assertTrue(all(r['merchant']=='eBay' for r in rows))

    def test_update_prices_uses_one_ebay_token_for_all_searches(self):
        empty=json.dumps('1:{"products":[]}')[1:-1].encode()
        page=b'<script>self.__next_f.push([1,"'+empty+b'"])</script>'
        calls=[]
        def fake_fetch(url,headers=None,data=None):
            calls.append((url,headers,data))
            if 'oauth2/token' in url: return b'{"access_token":"t0k"}'
            if 'api.ebay.com' in url: return b'{"itemSummaries":[]}'
            return page
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory)/'test.db') as db:
                env={'EBAY_CLIENT_ID':'id','EBAY_CLIENT_SECRET':'secret','BESTBUY_API_KEY':'','PRICE_FEED_URL':''}
                with patch('collectors.fetch',side_effect=fake_fetch), patch.dict('os.environ',env):
                    update_prices(db,sleep=lambda s:None)
        token=[c for c in calls if 'oauth2/token' in c[0]]
        searches=[c for c in calls if 'item_summary/search' in c[0]]
        self.assertEqual(len(token),1)
        self.assertTrue(token[0][1]['Authorization'].startswith('Basic '))
        self.assertEqual(len(searches),len(PRODUCTS))
        self.assertTrue(all(c[1]['Authorization']=='Bearer t0k' and c[1]['X-EBAY-C-MARKETPLACE-ID']=='EBAY_US' for c in searches))
        self.assertIn('conditionIds%3A%7B1000%7D',searches[0][0])

    def test_prices_run_each_morning_kst(self):
        with tempfile.TemporaryDirectory() as directory:
            with connect(Path(directory)/'test.db') as db:
                kst=dt.timezone(dt.timedelta(hours=9))
                self.assertTrue(prices_due(db,dt.datetime(2026,11,1,3,0,tzinfo=kst),9))
                db.execute("insert into runs values('prices:danawa','2026-10-31T00:05:00+00:00','2026-10-31T00:05:00+00:00','ok','x')")
                self.assertFalse(prices_due(db,dt.datetime(2026,10,31,20,0,tzinfo=kst),9))
                self.assertFalse(prices_due(db,dt.datetime(2026,11,1,8,59,tzinfo=kst),9))
                self.assertTrue(prices_due(db,dt.datetime(2026,11,1,9,0,tzinfo=kst),9))
                db.execute("update runs set attempted_at='2026-11-01T00:30:00+00:00',state='error'")
                self.assertFalse(prices_due(db,dt.datetime(2026,11,1,9,45,tzinfo=kst),9))
                self.assertTrue(prices_due(db,dt.datetime(2026,11,1,10,31,tzinfo=kst),9))


class Locale(unittest.TestCase):
    def test_accept_language_wins_then_country(self):
        self.assertEqual(preferred_lang('ko-KR,ko;q=0.9,en-US;q=0.8'),'ko')
        self.assertEqual(preferred_lang('en-US,en;q=0.9,ko;q=0.8','KR'),'en')
        self.assertEqual(preferred_lang('fr-FR,fr;q=0.9,ko;q=0.5'),'ko')
        self.assertEqual(preferred_lang('ko;q=0,en'),'en')
        self.assertEqual(preferred_lang('fr-FR','KR'),'ko')
        self.assertEqual(preferred_lang('', None),'en')
        self.assertEqual(preferred_lang('*;q=x','US'),'en')

    def test_market_follows_country_then_language(self):
        self.assertEqual(default_market('KR','en'),'KR')
        self.assertEqual(default_market('JP','ko'),'US')
        self.assertEqual(default_market(None,'ko'),'KR')
        self.assertEqual(default_market(None,'en'),'US')

    def test_every_page_renders_completely(self):
        for lang in ('ko','en'):
            for page in ('prices','news','about'):
                text=render_page(lang,page,'KR')
                self.assertNotIn('{{',text)
                self.assertIn(f'<html lang="{lang}">',text)
                boot=json.loads(text.split('id="boot">',1)[1].split('</script>',1)[0])
                self.assertEqual((boot['lang'],boot['page'],boot['market']),(lang,page,'KR'))



class StaticSite(unittest.TestCase):
    def test_build_writes_every_page_with_base_path_and_data(self):
        from build import build
        with tempfile.TemporaryDirectory() as directory:
            out=build(Path(directory)/'dist','/quite-terrible','https://example.github.io')
            for lang in ('ko','en'):
                for path in ('','news/','about/'):
                    text=(out/lang/path/'index.html').read_text()
                    self.assertNotIn('{{',text)
                    self.assertIn('href="/quite-terrible/styles.css"',text)
                    boot=json.loads(text.split('id="boot">',1)[1].split('</script>',1)[0])
                    self.assertEqual((boot['base'],boot['static'],boot['market']),('/quite-terrible',True,None))
            for name in ('prices-KR.json','prices-US.json','prices-KR-demo.json','news-ko.json','news-en.json'):
                self.assertTrue(json.loads((out/'data'/name).read_text()))
            self.assertIn('/quite-terrible/lang.js',(out/'index.html').read_text())
            self.assertTrue((out/'.nojekyll').exists())
            product=(out/'ko'/'rtx-5080'/'index.html').read_text()
            self.assertIn('<link rel="canonical" href="https://example.github.io/quite-terrible/ko/rtx-5080/">',product)
            self.assertIn('RTX 5080',product.split('<title>',1)[1].split('</title>',1)[0])
            ld=json.loads(product.split('application/ld+json">',1)[1].split('</script>',1)[0])
            self.assertIn('Product',[g['@type'] for g in ld['@graph']])
            site=(out/'sitemap.xml').read_text()
            self.assertIn('https://example.github.io/quite-terrible/en/rtx-5080/',site)
            self.assertIn('Sitemap: https://example.github.io/quite-terrible/sitemap.xml',(out/'robots.txt').read_text())

if __name__=='__main__':unittest.main()

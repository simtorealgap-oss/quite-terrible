import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from store import connect, save_quotes, product_view, coupang_offer, PRODUCTS, stamp, now, demo_products
from collectors import (danawa_products, danawa_quotes, bestbuy_quotes, ebay_quotes, coupang_quotes, coupang_authorization,
    matches, parse_news, update_news, update_prices, import_feed, COUPANG_SEARCH)
from server import preferred_lang, default_market, render_page, prices_due, prices_payload
from seo import product_static

NO_COUPANG={'COUPANG_ACCESS_KEY':'','COUPANG_SECRET_KEY':''}


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
        self.assertEqual(len(demo_products('US')),len(PRODUCTS))
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
        ram=next(p for p in PRODUCTS if p['id']=='samsung-ddr5-16')
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
                    update_news(db,sleep=lambda s:None)
                    update_news(db,sleep=lambda s:None)
                    queries=sum(len(q) for c in __import__('collectors').NEWS_QUERIES.values() for q in c.values())
                    self.assertEqual(request.call_count,queries)  # second call is inside the cooldown
                with patch('collectors.fetch',side_effect=TimeoutError):
                    update_news(db,force=True,sleep=lambda s:None)
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
                with patch('collectors.fetch',side_effect=fake_fetch), patch.dict('os.environ',NO_COUPANG):
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
                env={'EBAY_CLIENT_ID':'id','EBAY_CLIENT_SECRET':'secret','BESTBUY_API_KEY':'','PRICE_FEED_URL':''}|NO_COUPANG
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


def danawa_page(price=2539000,code='9'):
    flight=json.dumps('1:{"products":[{"productSeq":"%s","productName":"GIGABYTE 지포스 RTX 5080 D7 16GB","bundleName":"","minPrice":%d,"shopCount":30,"categorySeq3":972,"priceCompareStatusType":"가격비교"}]}'%(code,price))[1:-1]
    return f'<script>self.__next_f.push([1,"{flight}"])</script>'.encode()


def coupang_item(i,name,price,rocket=False,free=False,url=None,image=None):
    return {'keyword':'x','rank':i,'isRocket':rocket,'isFreeShipping':free,'productId':1000+i,'productName':name,'productPrice':price,
            'productImage':image or f'https://ads-partners.coupang.com/image1/{i}','productUrl':url or f'https://link.coupang.com/re/AFFSDP?itemId={i}'}


class Coupang(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.tmp.name)/'test.sqlite3')
        self.at=now().replace(microsecond=0)
        self.gpu=next(p for p in PRODUCTS if p['id']=='rtx-5080')

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def row(self,price,key='c1',at=None,**kwargs):
        return {'product_id':'rtx-5080','market':'KR','offer_key':key,'price':price,'shipping':None,'stock':'in_stock',
                'merchant':'Coupang','title':'ASUS PRIME 지포스 RTX 5080 O16G','url':'https://link.coupang.com/re/AFFSDP?itemId=1',
                'affiliate_url':'https://link.coupang.com/re/AFFSDP?itemId=1','image':'https://ads-partners.coupang.com/image1/a',
                'rocket':True,'source':'coupang','observed_at':stamp(at or self.at),**kwargs}

    def test_signature_follows_partners_api_guide(self):
        kst=dt.timezone(dt.timedelta(hours=9))
        header=coupang_authorization('GET',COUPANG_SEARCH,'keyword=RTX%205080&limit=10','test-access','test-secret',
                                     dt.datetime(2026,11,1,9,5,9,tzinfo=kst))
        # HMAC-SHA256 of "261101T000509Z" + "GET" + path + query, checked with openssl.
        self.assertEqual(header,'CEA algorithm=HmacSHA256, access-key=test-access, signed-date=261101T000509Z, '
                                'signature=11bf2d3ded360b5f9a5a23f60365524f90d2804518c8144592709f2f8aeb7e88')
        self.assertEqual(COUPANG_SEARCH,'/v2/providers/affiliate_open_api/apis/openapi/v1/products/search')

    def test_parsing_keeps_matching_coupang_listings_only(self):
        data={'rCode':'0','rMessage':'','data':{'landingUrl':'https://link.coupang.com/re/AFFSRP','productData':[
            coupang_item(1,'ASUS PRIME 지포스 RTX 5080 O16G OC D7 16GB',2885140,rocket=True),
            coupang_item(2,'MSI 지포스 RTX 5080 벤투스 3X OC D7 16GB',2790000.0,free=True,image='https://evil.example/a.png'),
            coupang_item(3,'RTX 5080 16GB 그래픽카드 지지대',15000),
            coupang_item(4,'게이밍 컴퓨터 i7 RTX 5080 16GB 본체',3500000),
            coupang_item(5,'MSI 지포스 RTX 5080 16GB 중고',2000000),
            coupang_item(6,'GIGABYTE 지포스 RTX 5070 Ti 16GB',1900000),
            coupang_item(7,'PNY 지포스 RTX 5080 16GB',2100000,url='https://evil.example/item'),
            coupang_item(8,'ZOTAC 지포스 RTX 5080 16GB','n/a'),
            coupang_item(9,'ZOTAC 지포스 RTX 5080 16GB',None)]}}
        rows=coupang_quotes(self.gpu,data,stamp(self.at))
        self.assertEqual([(r['offer_key'],r['price'],r['rocket'],r['shipping']) for r in rows],[('1002',2790000,False,0),('1001',2885140,True,None)])
        self.assertIsNone(rows[0]['image'])
        self.assertEqual(rows[1]['image'],'https://ads-partners.coupang.com/image1/1')
        self.assertTrue(all(r['source']=='coupang' and r['url']==r['affiliate_url'] for r in rows))
        self.assertEqual(save_quotes(self.db,rows),2)
        with self.assertRaises(ValueError):coupang_quotes(self.gpu,{'rCode':'400','rMessage':'bad'})
        ram=next(p for p in PRODUCTS if p['id']=='samsung-ddr5-16')
        data={'rCode':'0','data':{'productData':[coupang_item(1,'삼성전자 DDR5 PC5-44800 16GB 데스크탑 메모리',89000),
            coupang_item(2,'삼성전자 DDR5-5600 16GB x 2개',170000),coupang_item(3,'삼성전자 노트북 DDR5-5600 16GB',85000)]}}
        self.assertEqual([r['offer_key'] for r in coupang_quotes(ram,data)],['1001'])

    def test_no_keys_means_no_coupang_requests(self):
        calls=[]
        def fake_fetch(url,headers=None,data=None):
            calls.append(url)
            return danawa_page()
        for env in ({'COUPANG_ACCESS_KEY':'','COUPANG_SECRET_KEY':''},{'COUPANG_ACCESS_KEY':'key','COUPANG_SECRET_KEY':''}):
            with patch('collectors.fetch',side_effect=fake_fetch), patch.dict('os.environ',env|{'BESTBUY_API_KEY':'','PRICE_FEED_URL':'','EBAY_CLIENT_ID':''}):
                result=update_prices(self.db,sleep=lambda s:None)
            self.assertNotIn('coupang',[r['source'] for r in result])
        self.assertFalse([u for u in calls if 'coupang' in u])
        self.assertIsNone(self.db.execute("select 1 from runs where job='prices:coupang'").fetchone())

    def test_signed_search_for_each_product_then_cooldown(self):
        calls,waits=[],[]
        listing={'rCode':'0','rMessage':'','data':{'productData':[coupang_item(1,'ASUS PRIME 지포스 RTX 5080 O16G OC D7 16GB',2885140,rocket=True)]}}
        def fake_fetch(url,headers=None,data=None):
            calls.append((url,headers))
            return json.dumps(listing).encode() if url.startswith('https://api-gateway.coupang.com/') else danawa_page()
        env={'COUPANG_ACCESS_KEY':'ak','COUPANG_SECRET_KEY':'sk','BESTBUY_API_KEY':'','PRICE_FEED_URL':'','EBAY_CLIENT_ID':''}
        with patch('collectors.fetch',side_effect=fake_fetch), patch.dict('os.environ',env):
            result=update_prices(self.db,sleep=waits.append)
            update_prices(self.db,sleep=waits.append)  # within the hour: Danawa again, Coupang left alone
        searches=[c for c in calls if 'api-gateway.coupang.com' in c[0]]
        searchable=[p for p in PRODUCTS if p.get('coupangSearch')]
        self.assertEqual(len(searches),len(searchable))
        self.assertEqual(waits.count(3),len(searchable)-1)
        import hmac,hashlib,urllib.parse
        for url,headers in searches:
            parts=urllib.parse.urlsplit(url)
            self.assertEqual(parts.path,COUPANG_SEARCH)
            self.assertIn('limit=10',parts.query)
            signed=headers['Authorization'].split('signed-date=')[1].split(',')[0]
            expected=hmac.new(b'sk',(signed+'GET'+parts.path+parts.query).encode(),hashlib.sha256).hexdigest()
            self.assertTrue(headers['Authorization'].startswith('CEA algorithm=HmacSHA256, access-key=ak, '))
            self.assertTrue(headers['Authorization'].endswith(f'signature={expected}'))
        self.assertIn('keyword=%EC%A7%80%ED%8F%AC%EC%8A%A4%20RTX%205080%2016GB',next(u for u,_ in searches if '5080' in urllib.parse.unquote(u)))
        coupang=next(r for r in result if r['source']=='coupang')
        self.assertEqual(coupang['matched']['rtx-5080'],1)
        self.assertEqual(self.db.execute("select state from runs where job='prices:coupang'").fetchone()[0],'ok')
        self.assertEqual(coupang_offer(self.db,self.gpu)['price'],2885140)
        self.assertEqual(product_view(self.db,self.gpu,'KR')['price'],2539000)

    def test_danawa_price_history_and_stats_ignore_coupang(self):
        danawa={'product_id':'rtx-5080','market':'KR','offer_key':'9','price':2539000,'shipping':None,'stock':'in_stock',
                'merchant':'GIGABYTE','title':'GIGABYTE RTX 5080','url':'https://prod.danawa.com/info/?pcode=9','source':'danawa','shops':30}
        save_quotes(self.db,[danawa|{'observed_at':stamp(self.at-dt.timedelta(days=1))},danawa|{'observed_at':stamp(self.at)}])
        before=product_view(self.db,self.gpu,'KR',self.at)
        save_quotes(self.db,[self.row(1990000,'old',self.at-dt.timedelta(days=1)),self.row(2885140,'c1'),
                             self.row(2700000,'c2',rocket=False),self.row(None,'c3',stock='out_of_stock')])
        after=product_view(self.db,self.gpu,'KR',self.at)
        for key in ('price','change','change7','history','low30','high30','merchant_count','observed_at','offers'):
            self.assertEqual(after[key],before[key],key)
        self.assertTrue(all(o['source']=='danawa' for o in after['offers']))
        offer=coupang_offer(self.db,self.gpu,self.at)
        # Latest check only: yesterday's cheaper listing may be sold out now.
        self.assertEqual((offer['price'],offer['rocket'],offer['name']),(2700000,False,'ASUS PRIME 지포스 RTX 5080 O16G'))
        self.assertIsNone(coupang_offer(self.db,self.gpu,self.at+dt.timedelta(hours=37)))
        self.assertIsNone(coupang_offer(self.db,PRODUCTS[0],self.at))

    def test_payload_exposes_coupang_offer_for_live_korean_prices_only(self):
        save_quotes(self.db,[self.row(2885140)])
        record=__import__('store').record_run
        record(self.db,'prices:coupang','error','HTTPError 429')
        with patch.dict('os.environ',{'RAMPRICE_DB':str(Path(self.tmp.name)/'test.sqlite3')}):
            kr,us,demo=prices_payload('KR'),prices_payload('US'),prices_payload('KR',demo=True)
        item=next(p for p in kr['products'] if p['id']=='rtx-5080')
        self.assertEqual((item['coupangOffer']['price'],item['coupangOffer']['url']),(2885140,'https://link.coupang.com/re/AFFSDP?itemId=1'))
        self.assertIsNone(item['price'])  # no Danawa price: the Coupang price is not the site's price
        self.assertTrue(all(p['coupangOffer'] is None for p in us['products']+demo['products']))
        self.assertNotIn('prices:coupang',[r['job'] for r in kr['runs']])

    def test_feed_cannot_supply_coupang_prices(self):
        with self.assertRaises(ValueError):import_feed(self.db,{'observations':[self.row(1000000)]})
        self.assertIsNone(coupang_offer(self.db,self.gpu))

    def test_product_page_shows_api_price_or_plain_link(self):
        strings=json.loads((Path(__file__).resolve().parents[1]/'config/i18n.json').read_text())['ko']
        offer={'name':'ASUS PRIME 지포스 RTX 5080 O16G','price':2885140,'url':'https://link.coupang.com/re/AFFSDP?itemId=1',
               'image':'https://ads-partners.coupang.com/image1/a','rocket':True,'free_shipping':False,'observed_at':'2026-11-01T00:05:00+00:00'}
        text=product_static(self.gpu|{'coupangOffer':offer},'ko',strings)
        for part in ('2,885,140원','로켓배송','11월 1일 9시 쿠팡 파트너스 API로 확인','href="https://link.coupang.com/re/AFFSDP?itemId=1"',strings['coupangDisclosure']):
            self.assertIn(part,text)
        plain=product_static(self.gpu|{'coupangOffer':None},'ko',strings)
        self.assertNotIn('원',plain.split('coupang-note')[0].replace(strings['coupangDisclosure'],''))
        self.assertIn(self.gpu['coupang'],plain)


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
            home=(out/'index.html').read_text()
            self.assertIn('/quite-terrible/lang.js',home)
            self.assertLess(home.index('lang.js'),home.index('app.js'))
            self.assertIn('id="rows"><tr class="row">',home)
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


class BuyList(unittest.TestCase):
    strings=json.loads((Path(__file__).resolve().parents[1]/'config/i18n.json').read_text())['ko']

    def test_memory_makers_cover_each_capacity_once(self):
        from seo import MAKERS
        ddr5=[p for p in PRODUCTS if p['category']=='ram' and p['generation']=='DDR5']
        self.assertTrue(all(p.get('maker') in MAKERS and p.get('coupang') and p.get('shortKo') for p in ddr5))
        cells=[(p['maker'],p['capacity']) for p in ddr5]
        self.assertEqual(len(cells),len(set(cells)))
        self.assertTrue({16,32,64}<={p['capacity'] for p in ddr5})

    def test_maker_table_links_each_priced_cell(self):
        from seo import maker_rows
        products=[p|{'price':100000+i} for i,p in enumerate(PRODUCTS)]
        html=maker_rows(products,'ko','',self.strings)
        self.assertEqual(html.count('<tr>'),6)
        self.assertIn('href="/ko/hynix-ddr5-32/"',html)
        samsung=html.split('</tr>')[0]
        self.assertIn('삼성전자',samsung)
        self.assertTrue(samsung.endswith('<td class="num"><span class="muted">—</span></td>'))  # no 64GB desktop module

    def test_product_page_lists_coupang_then_one_danawa_price(self):
        p=next(q for q in PRODUCTS if q['id']=='samsung-ddr5-32')
        offers=[{'source':'danawa','title':f'모델 {n}','merchant':f'모델 {n}','amount':price,'price':price,'shops':10,'stock':'unknown',
                 'stale':False,'url':f'https://prod.danawa.com/info/?pcode={n}','observed_at':'2026-11-01T00:05:00+00:00'}
                for n,price in ((1,790970),(2,812000),(3,905000))]
        text=product_static(p|{'offers':offers,'coupangOffer':None},'ko',self.strings)
        self.assertEqual(text.count('<li class="seller">'),2)
        self.assertLess(text.index('mall coupang'),text.index('mall danawa'))
        self.assertIn('790,970원',text)
        self.assertNotIn('812,000원',text)
        self.assertIn(p['coupang'],text)
        self.assertIn('rel="sponsored noopener noreferrer"',text)
        self.assertIn(self.strings['coupangDisclosure'],text)
        # Without an API price the Coupang row shows no amount at all.
        self.assertNotIn('원',text.split('mall danawa')[0])


class Regions(unittest.TestCase):
    def test_us_morning_run_skips_korean_sources(self):
        db=connect(Path(tempfile.mkdtemp())/'r.sqlite3')
        with patch.dict('os.environ',{**NO_COUPANG,'EBAY_CLIENT_ID':'','EBAY_CLIENT_SECRET':'','BESTBUY_API_KEY':'','PRICE_FEED_URL':''}), \
             patch('collectors.fetch',side_effect=AssertionError('no request expected')):
            self.assertEqual(update_prices(db,sleep=lambda s:None,market='US'),[])
            self.assertEqual(update_news(db,force=True,langs=['xx']),[])


class NewsMix(unittest.TestCase):
    def test_one_publisher_shows_at_most_two_headlines_a_day(self):
        tmp=Path(tempfile.mkdtemp())/'n.sqlite3'
        db=connect(tmp); at=now()
        rows=[(f'id{i}','ko','ram',f'D램 기사 {i}','https://example.com/a','GameGPU' if i<5 else '연합뉴스',stamp(at-dt.timedelta(minutes=i)),stamp(at)) for i in range(7)]
        with db: db.executemany('INSERT INTO news VALUES(?,?,?,?,?,?,?,?)',rows)
        with patch.dict('os.environ',{'RAMPRICE_DB':str(tmp)}):
            from server import news_payload
            news=news_payload('ko')['news']
        self.assertEqual([n['publisher'] for n in news].count('GameGPU'),2)
        self.assertEqual([n['publisher'] for n in news].count('연합뉴스'),2)

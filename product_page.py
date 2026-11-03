# -*- coding: utf-8 -*-
"""
product_page.py — توليد صفحات منتجات ديناميكية (SSR) لتحسين SEO
-----------------------------------------------------------------
يجلب المنتجات من Cloud Firestore عبر REST API ويولّد:
  - صفحة HTML كاملة لكل منتج (/product/<id>/<slug>) مع Schema.org
  - sitemap.xml ديناميكي يشمل كل المنتجات الحالية
التخزين المؤقت: ذاكرة (5 دقائق) + ملف JSON احتياطي (يصمد بعد إعادة التشغيل
وعند انقطاع Firestore أو استنفاد الحصة).
"""
import json
import os
import re
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from html import escape

PROJECT_ID = 'qatar-oman'
API_KEY = 'AIzaSyDNQotHYC8WcMi1AAHrHJe_rQR7OZ0V5FI'
PANEL_EMAIL = 'panel-dashboard@qatar-oman.local'
PANEL_PASSWORD = 'ZainDashboard2026!'

BASE_URL = 'https://althenayanfarms.app'
SITE_NAME = 'مزارع الثنيان'
CACHE_TTL = 300  # 5 دقائق
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.products-cache.json')

_lock = threading.Lock()
_mem_cache = {'products': None, 'ts': 0}
_id_token = {'token': None, 'expires': 0}
_state = {'last_error': None}


# ═══════════════════════ جلب البيانات من Firestore ═══════════════════════

def _http_json(url, headers=None, data=None, timeout=8):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _get_id_token():
    """تسجيل دخول بحساب اللوحة عبر Firebase Auth REST (يُخزَّن 55 دقيقة)."""
    now = time.time()
    if _id_token['token'] and now < _id_token['expires']:
        return _id_token['token']
    url = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=' + API_KEY
    payload = json.dumps({
        'email': PANEL_EMAIL, 'password': PANEL_PASSWORD, 'returnSecureToken': True
    }).encode('utf-8')
    res = _http_json(url, data=payload)
    _id_token['token'] = res['idToken']
    _id_token['expires'] = now + 3300
    return _id_token['token']


def _firestore_get(url):
    """محاولة بدون مصادقة أولاً (قراءة عامة)، ثم برمز اللوحة عند الرفض."""
    try:
        return _http_json(url + ('&' if '?' in url else '?') + 'key=' + API_KEY)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            token = _get_id_token()
            return _http_json(url, headers={'Authorization': 'Bearer ' + token})
        raise


def _fs_value(v):
    if 'stringValue' in v:
        return v['stringValue']
    if 'integerValue' in v:
        return int(v['integerValue'])
    if 'doubleValue' in v:
        return float(v['doubleValue'])
    if 'booleanValue' in v:
        return v['booleanValue']
    if 'timestampValue' in v:
        return v['timestampValue']
    if 'arrayValue' in v:
        return [_fs_value(x) for x in v['arrayValue'].get('values', [])]
    if 'mapValue' in v:
        return {k: _fs_value(x) for k, x in v['mapValue'].get('fields', {}).items()}
    return None


def _parse_doc(doc):
    fields = doc.get('fields', {})
    item = {k: _fs_value(v) for k, v in fields.items()}
    item['_id'] = doc['name'].rsplit('/', 1)[-1]
    return item


def _product_key(p):
    return (p.get('name') or '', str(p.get('price') or ''), p.get('desc') or '')


def _merge_missing(products, local):
    """دمج بترتيب يحافظ على الموضع: قاعدة البيانات لها الأولوية، وأي منتج موجود
    في اللقطة المرفوعة وفُقدت وثيقته يُدرَج في **موضعه الأصلي** من اللقطة (لا في
    الأسفل). يمنع اختفاء المنتجات وتغيّر ترتيبها بعد إعادة الترتيب من اللوحة."""
    rem = products or []
    loc = local or []
    rem_keys = {_product_key(p) for p in rem}
    loc_keys = {_product_key(p) for p in loc}
    out = []
    seen = set()
    recovered = 0

    def push_remote(p):
        k = _product_key(p)
        if k not in seen:
            seen.add(k); out.append(p)

    def push_local(p):
        nonlocal recovered
        k = _product_key(p)
        if k not in seen:
            seen.add(k); out.append(p); recovered += 1

    i = j = 0
    while i < len(rem) and j < len(loc):
        rk, lk = _product_key(rem[i]), _product_key(loc[j])
        if rk == lk:
            push_remote(rem[i]); i += 1; j += 1
        elif lk not in rem_keys:
            push_local(loc[j]); j += 1
        elif rk not in loc_keys:
            push_remote(rem[i]); i += 1
        else:
            push_remote(rem[i]); i += 1
    while i < len(rem):
        push_remote(rem[i]); i += 1
    while j < len(loc):
        push_local(loc[j]); j += 1

    if recovered:
        print('products: أُعيد %d منتجاً محلياً مفقوداً من قاعدة البيانات' % recovered, flush=True)
    return out


def _read_snapshot():
    """اللقطة المرفوعة (products-snapshot.json) — مرجع استرجاع المنتجات المفقودة.
    تُحدَّث بـ sync_products.py بعد أي تغيير شرعي (حذف/إضافة) فلا تُحيي محذوفاً."""
    try:
        with open(SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_products():
    url = ('https://firestore.googleapis.com/v1/projects/%s/databases/(default)'
           '/documents/products?pageSize=300' % PROJECT_ID)
    res = _firestore_get(url)
    docs = res.get('documents', [])
    products = [_parse_doc(d) for d in docs]
    products.sort(key=lambda p: p.get('order') or 0)  # ترتيب قاعدة البيانات أولاً
    # لا تُسقط منتجات موجودة في اللقطة اختفت وثائقها من قاعدة البيانات (إصلاح
    # اختفاء المنتجات بعد إعادة الترتيب) — تُدرَج في موضعها الأصلي.
    products = _merge_missing(products, _read_snapshot())
    for idx, p in enumerate(products):  # ترقيم متسلسل يثبّت الترتيب المدمج
        p['order'] = idx
    return products


SNAPSHOT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'products-snapshot.json')


def _read_disk_cache():
    # أولاً آخر نسخة ناجحة الجلب (تُحدَّث تلقائياً)، ثم اللقطة المرفوعة مع المستودع
    for path in (CACHE_FILE, SNAPSHOT_FILE):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data:
                return data
        except Exception:
            continue
    return None


def _write_disk_cache(products):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(products, f, ensure_ascii=False)
    except Exception:
        pass


def get_products():
    """قائمة المنتجات: ذاكرة ← Firestore ← آخر نسخة محفوظة على القرص."""
    now = time.time()
    with _lock:
        if _mem_cache['products'] is not None and now - _mem_cache['ts'] < CACHE_TTL:
            return _mem_cache['products']
    try:
        products = _fetch_products()
        if products:
            with _lock:
                _mem_cache['products'] = products
                _mem_cache['ts'] = now
            _write_disk_cache(products)
            return products
        _state['last_error'] = 'empty documents from Firestore'
    except Exception as exc:
        _state['last_error'] = repr(exc)
        print('products fetch FAILED: %r' % exc, flush=True)
    # فشل الجلب: استخدم آخر نسخة معروفة (ذاكرة قديمة أو قرص)
    with _lock:
        if _mem_cache['products'] is not None:
            return _mem_cache['products']
    cached = _read_disk_cache()
    if cached:
        with _lock:
            _mem_cache['products'] = cached
            _mem_cache['ts'] = now
        return cached
    return []


def get_product(product_id):
    for p in get_products():
        if p.get('_id') == product_id:
            return p
    return None


# ═══════════════════════ أدوات مساعدة ═══════════════════════

_TRANSLIT = {
    'ا': 'a', 'أ': 'a', 'إ': 'a', 'آ': 'a', 'ٱ': 'a',
    'ب': 'b', 'ت': 't', 'ث': 'th', 'ج': 'j', 'ح': 'h', 'خ': 'kh',
    'د': 'd', 'ذ': 'dh', 'ر': 'r', 'ز': 'z', 'س': 's', 'ش': 'sh',
    'ص': 's', 'ض': 'd', 'ط': 't', 'ظ': 'dh', 'ع': 'a', 'غ': 'gh',
    'ف': 'f', 'ق': 'q', 'ك': 'k', 'ل': 'l', 'م': 'm', 'ن': 'n',
    'ه': 'h', 'و': 'w', 'ي': 'y', 'ى': 'a', 'ة': 'h', 'ء': '',
    'ئ': 'y', 'ؤ': 'w', '٠': '0', '١': '1', '٢': '2', '٣': '3',
    '٤': '4', '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
}


def slugify(name):
    """رابط لطيف من اسم المنتج. يُولَّد بصيغة ASCII فقط (ترجمة صوتية للعربية)
    لتجنّب خلل Netlify مع الروابط العربية/المشفّرة percent-encoding التي تمنع
    إعادة التوجيه إلى صفحة المنتج الثابتة وتُرجع index.html (صفحة رئيسية بلا سكربتات)."""
    translit = ''.join(_TRANSLIT.get(ch, ch) for ch in (name or ''))
    s = re.sub(r'[^A-Za-z0-9\s-]', '', translit)
    s = re.sub(r'[\s_]+', '-', s.strip().lower())
    return s or 'product'


def product_url(p):
    """رابط صفحة المنتج — ASCII فقط: /product/<id>/<slug> (بلا ترميز percent)."""
    return '/product/%s/%s' % (p['_id'], slugify(p.get('name', '')))


def abs_img(product):
    """رابط صورة مطلق — الصور المضمّنة (data:) تُقدَّم عبر /product-img/<id>."""
    img = product.get('img') if isinstance(product, dict) else product
    if not img:
        return BASE_URL + '/assets/images/nfc2.png'
    if img.startswith('data:'):
        return BASE_URL + '/product-img/%s' % product.get('_id', '')
    if img.startswith('http'):
        return img
    return BASE_URL + '/' + img.lstrip('./')


def product_img_url(product):
    """رابط الصورة داخل الصفحة (src وسمة img)."""
    img = product.get('img') or ''
    if img.startswith('data:'):
        return '/product-img/%s' % product.get('_id', '')
    if img.startswith('http'):
        return img
    return '/' + img.lstrip('./')


def get_data_image(product):
    """يفكّك صورة data URI إلى (content_type, bytes) — وإلا None."""
    img = (product or {}).get('img') or ''
    if not img.startswith('data:') or ',' not in img:
        return None
    header, b64 = img.split(',', 1)
    ctype = header[5:].split(';')[0] or 'image/jpeg'
    import base64
    try:
        return ctype, base64.b64decode(b64)
    except Exception:
        return None


def fmt_price(price):
    try:
        return '%.3f' % float(price)
    except (TypeError, ValueError):
        return str(price)


# ═══════════════════════ قالب صفحة المنتج ═══════════════════════

_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_desc}">
<meta name="keywords" content="{meta_keys}">
<meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1">
<link rel="canonical" href="{canonical}">
<link rel="alternate" hreflang="ar" href="{canonical}">
<link rel="alternate" hreflang="x-default" href="{canonical}">
<meta name="theme-color" content="#004d7a">
<meta property="og:type" content="product">
<meta property="og:site_name" content="{site_name}">
<meta property="og:locale" content="ar_KW">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{meta_desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{img_abs}">
<meta property="product:price:amount" content="{price}">
<meta property="product:price:currency" content="KWD">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{meta_desc}">
<meta name="twitter:image" content="{img_abs}">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script type="application/ld+json">{product_schema}</script>
<script type="application/ld+json">{breadcrumb_schema}</script>
<script type="application/ld+json">{faq_schema}</script>
<script src="/assets/js/cart.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; -webkit-tap-highlight-color: transparent; }}
body {{ background: #f8f9fa; color: #111; }}
a {{ text-decoration: none; color: inherit; }}
.header {{ background: #fff; position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 3px rgba(0,0,0,.07); }}
.header-inner {{ max-width: 1000px; margin: 0 auto; padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; }}
.logo img {{ width: 110px; height: 35px; object-fit: contain; display: block; }}
.cart-link {{ background: #004d7a; color: #fff; padding: 8px 18px; border-radius: 10px; font-size: 14px; font-weight: 700; }}
.wrap {{ max-width: 1000px; margin: 0 auto; padding: 15px; }}
.breadcrumb {{ font-size: 13px; color: #777; margin: 10px 0 18px; }}
.breadcrumb a {{ color: #004d7a; }}
.card {{ background: #fff; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,.06); overflow: hidden; display: flex; flex-wrap: wrap; }}
.card-img {{ flex: 1 1 320px; background: #f1f3f5; display: flex; align-items: center; justify-content: center; min-height: 300px; }}
.card-img img {{ width: 100%; height: 100%; object-fit: cover; max-height: 420px; }}
.card-body {{ flex: 1 1 320px; padding: 26px; display: flex; flex-direction: column; gap: 14px; }}
h1 {{ font-size: 24px; color: #111; line-height: 1.5; }}
.desc {{ color: #444; line-height: 1.9; font-size: 15px; }}
.price {{ font-size: 26px; font-weight: 800; color: #004d7a; }}
.price small {{ font-size: 15px; font-weight: 600; }}
.badges {{ display: flex; gap: 8px; flex-wrap: wrap; }}
.badge {{ background: #e8f4ea; color: #1e7e34; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 20px; }}
.badge.blue {{ background: #e7f1f8; color: #004d7a; }}
.buy-row {{ display: flex; gap: 10px; margin-top: auto; flex-wrap: wrap; }}
.btn {{ border: none; cursor: pointer; border-radius: 12px; font-size: 16px; font-weight: 800; padding: 14px 22px; flex: 1; min-width: 140px; text-align: center; }}
.btn-add {{ background: #004d7a; color: #fff; }}
.btn-cart {{ background: #fff; color: #004d7a; border: 2px solid #004d7a; }}
.section {{ background: #fff; border-radius: 16px; box-shadow: 0 2px 10px rgba(0,0,0,.06); padding: 22px 26px; margin-top: 18px; }}
.section h2 {{ font-size: 18px; color: #004d7a; margin-bottom: 12px; }}
.section p, .section li {{ color: #444; line-height: 2; font-size: 14.5px; }}
.faq details {{ border-bottom: 1px solid #eee; padding: 10px 0; }}
.faq summary {{ cursor: pointer; font-weight: 700; font-size: 15px; color: #222; }}
.faq details p {{ padding: 8px 0 4px; }}
.related {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }}
.rel-card {{ background: #f8f9fa; border-radius: 12px; overflow: hidden; border: 1px solid #eee; transition: transform .15s; }}
.rel-card:hover {{ transform: translateY(-3px); }}
.rel-card img {{ width: 100%; height: 110px; object-fit: cover; }}
.rel-card .rel-body {{ padding: 10px; }}
.rel-card .rel-name {{ font-size: 13.5px; font-weight: 700; color: #222; line-height: 1.5; }}
.rel-card .rel-price {{ font-size: 13px; font-weight: 800; color: #004d7a; margin-top: 4px; }}
.footer {{ text-align: center; color: #999; font-size: 13px; padding: 26px 15px; }}
.toast {{ position: fixed; bottom: 22px; right: 50%; transform: translateX(50%) translateY(80px); background: #1e7e34; color: #fff; padding: 12px 26px; border-radius: 12px; font-weight: 700; opacity: 0; transition: all .3s; z-index: 999; }}
.toast.show {{ opacity: 1; transform: translateX(50%) translateY(0); }}
</style>
</head>
<body>
<header class="header">
  <div class="header-inner">
    <a class="logo" href="/"><img src="/assets/images/nfc2.png" alt="{site_name}"></a>
    <a class="cart-link" href="/cartepage.html">🛒 سلة الطلبات</a>
  </div>
</header>
<main class="wrap">
  <nav class="breadcrumb" aria-label="breadcrumb">
    <a href="/">الرئيسية</a> &lsaquo; <a href="/#products">المنتجات</a> &lsaquo; <span>{name}</span>
  </nav>
  <article class="card" itemscope itemtype="https://schema.org/Product">
    <div class="card-img"><img src="{img_rel}" alt="{img_alt}" itemprop="image" fetchpriority="high"></div>
    <div class="card-body">
      <h1 itemprop="name">{name}</h1>
      <div class="badges">
        <span class="badge">✅ طازج يومياً</span>
        <span class="badge blue">🚚 توصيل مجاني خلال 40 دقيقة</span>
        <span class="badge blue">🇰🇼 داخل الكويت</span>
      </div>
      <p class="desc" itemprop="description">{desc}</p>
      <div class="price" itemprop="offers" itemscope itemtype="https://schema.org/Offer">
        <meta itemprop="priceCurrency" content="KWD">
        <span itemprop="price" content="{price}">{price}</span> <small>د.ك</small>
        <link itemprop="availability" href="https://schema.org/InStock">
      </div>
      <div class="buy-row">
        <button class="btn btn-add" onclick="addToCart()">🛒 إضافة للسلة</button>
        <a class="btn btn-cart" href="/cartepage.html" onclick="buyNow(event)">إتمام الطلب</a>
      </div>
    </div>
  </article>

  <section class="section">
    <h2>{name} — توصيل طازج في الكويت من مزارع الثنيان</h2>
    <p>اطلب {name} الآن من متجر مزارع الثنيان الإلكتروني واحصل على توصيل مجاني وسريع خلال 40 دقيقة لجميع مناطق الكويت. {desc_sent} نحرص على وصول منتجاتنا طازجة يومياً من المزرعة إلى باب بيتك، مع إمكانية الدفع عند الاستلام أو بالكي نت. السعر المعروض شامل التوصيل، والطلب يتم أونلاين بخطوات بسيطة.</p>
  </section>

  <section class="section faq">
    <h2>أسئلة شائعة عن {name}</h2>
    <details><summary>هل يتوفر {name} للتوصيل في جميع مناطق الكويت؟</summary><p>نعم، نوصل {name} وجميع منتجاتنا الطازجة لجميع محافظات ومناطق الكويت خلال 40 دقيقة تقريباً، والتوصيل مجاني.</p></details>
    <details><summary>ما هو سعر {name} اليوم؟</summary><p>سعر {name} حالياً {price} د.ك شامل التوصيل المجاني. الأسعار تُحدَّث يومياً على موقعنا.</p></details>
    <details><summary>كيف أطلب {name} أونلاين؟</summary><p>اضغط زر «إضافة للسلة» ثم انتقل لسلة الطلبات وأكمل بياناتك، وسيصلك الطلب طازجاً حتى باب البيت مع الدفع عند الاستلام أو بالكي نت.</p></details>
    <details><summary>هل المنتجات طازجة فعلاً؟</summary><p>نعم، جميع منتجات مزارع الثنيان تُجهَّز طازجة يومياً من المزرعة وتُوصَّل مباشرة دون تخزين طويل.</p></details>
  </section>

  <section class="section">
    <h2>تجربة عملائنا مع {site_name}</h2>
    <p>يصلنا يومياً عشرات الطلبات من جميع محافظات الكويت، ويعود أغلب عملائنا للطلب مرة بعد مرة لأنهم وجدوا منتجاً طازجاً يوصلهم في وقته وبسعر يوفر عليهم مقارنة بالسوق. كثير من عملائنا يخبروننا أن طعم منتجاتنا الطازجة يفرق معهم، وأن سرعة التوصيل خلال 40 دقيقة وفّرت عليهم مشوار السوق — وهذا أكبر دليل على جودة خدمتنا، ونحرص أن يكون {name} الذي يصلك بنفس هذا المستوى في كل مرة.</p>
  </section>

  <section class="section">
    <h2>منتجات طازجة أخرى قد تعجبك</h2>
    <div class="related">{related_html}</div>
  </section>
</main>
<footer class="footer">{site_name} — توصيل المنتجات الطازجة في الكويت 🇰🇼<br>
<a href="/prices" style="color:#004d7a">أسعار منتجاتنا اليوم</a> · <a href="/terms.html" style="color:#004d7a">الشروط والأحكام</a> · <a href="/privacy.html" style="color:#004d7a">سياسة الخصوصية</a> · <a href="/returns.html" style="color:#004d7a">سياسة الاسترجاع</a></footer>
<div class="toast" id="toast">✅ تمت الإضافة إلى السلة</div>
<script>
var PRODUCT = {product_js};
function addToCart() {{
  if (window.CartAdd) window.CartAdd(PRODUCT, 1);
  var t = document.getElementById('toast');
  t.classList.add('show');
  setTimeout(function () {{ t.classList.remove('show'); }}, 1800);
}}
function buyNow(e) {{
  if (window.CartAdd) window.CartAdd(PRODUCT, 1);
  // يُترك التنقّل الافتراضي للرابط إلى /cartepage.html ليكمل الطلب
}}
</script>
</body>
</html>
"""

_NOT_FOUND = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>المنتج غير موجود | مزارع الثنيان</title>
<meta name="robots" content="noindex, follow">
<style>body{{font-family:system-ui;background:#f8f9fa;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.box{{background:#fff;border-radius:16px;padding:40px;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,.08)}}
a{{display:inline-block;margin-top:16px;background:#004d7a;color:#fff;padding:12px 28px;border-radius:12px;text-decoration:none;font-weight:700}}</style>
</head><body><div class="box"><h1>😕 هذا المنتج لم يعد متوفراً</h1>
<p style="margin-top:10px;color:#555">ربما انتهى العرض أو تغيّر الرابط — تصفح منتجاتنا الطازجة الحالية</p>
<a href="/">تصفح كل المنتجات</a></div></body></html>
"""


def render_product_html(product, all_products):
    name = str(product.get('name') or 'منتج')
    desc = str(product.get('desc') or '').strip()
    price = fmt_price(product.get('price', '0'))
    img_rel = product_img_url(product)
    img_abs = abs_img(product)
    url = BASE_URL + product_url(product)

    # السعر في العنوان والوصف: يظهر في نتيجة البحث، والصفحة نفسها تبقى نظيفة
    title = '%s بسعر %s د.ك فقط | توصيل مجاني في الكويت - %s' % (name, price, SITE_NAME)
    meta_desc = ('%s من %s بسعر %s د.ك شامل التوصيل — أفضل عروض وأسعار %s في الكويت. '
                 '%s توصيل مجاني خلال 40 دقيقة لجميع المناطق. اطلب أونلاين الآن.'
                 % (name, SITE_NAME, price, name,
                    (desc[:60] + '... ') if len(desc) > 60 else (desc + ' ' if desc else '')))[:300]
    meta_keys = ', '.join([name, 'عروض ' + name, 'أرخص ' + name, name + ' الكويت',
                           'سعر ' + name + ' اليوم', 'أسعار ' + name, 'توصيل ' + name,
                           'عروض طازجة الكويت', SITE_NAME, 'توصيل طازج الكويت'])

    desc_sent = desc if desc else 'منتج طازج من مزرعتنا بجودة مضمونة.'
    product_schema = json.dumps({
        '@context': 'https://schema.org', '@type': 'Product',
        'name': name, 'description': desc_sent, 'image': img_abs, 'url': url,
        'brand': {'@type': 'Brand', 'name': SITE_NAME},
        'offers': {'@type': 'Offer', 'url': url, 'priceCurrency': 'KWD',
                   'price': price, 'availability': 'https://schema.org/InStock',
                   'itemCondition': 'https://schema.org/NewCondition',
                   'areaServed': {'@type': 'Country', 'name': 'Kuwait'},
                   'priceValidUntil': '%s-12-31' % time.strftime('%Y'),
                   'shippingDetails': {'@type': 'OfferShippingDetails',
                                       'shippingRate': {'@type': 'MonetaryAmount', 'value': '0', 'currency': 'KWD'},
                                       'shippingDestination': {'@type': 'DefinedRegion', 'addressCountry': 'KW'},
                                       'deliveryTime': {'@type': 'ShippingDeliveryTime',
                                                        'handlingTime': {'@type': 'QuantitativeValue', 'minValue': 0, 'maxValue': 1, 'unitCode': 'h'},
                                                        'transitTime': {'@type': 'QuantitativeValue', 'minValue': 0, 'maxValue': 1, 'unitCode': 'h'}}}}
    }, ensure_ascii=False)
    breadcrumb_schema = json.dumps({
        '@context': 'https://schema.org', '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'الرئيسية', 'item': BASE_URL + '/'},
            {'@type': 'ListItem', 'position': 2, 'name': 'المنتجات', 'item': BASE_URL + '/#products'},
            {'@type': 'ListItem', 'position': 3, 'name': name, 'item': url}
        ]
    }, ensure_ascii=False)
    faq_schema = json.dumps({
        '@context': 'https://schema.org', '@type': 'FAQPage',
        'mainEntity': [
            {'@type': 'Question', 'name': 'هل يتوفر %s للتوصيل في جميع مناطق الكويت؟' % name,
             'acceptedAnswer': {'@type': 'Answer', 'text': 'نعم، نوصل %s لجميع محافظات الكويت خلال 40 دقيقة والتوصيل مجاني.' % name}},
            {'@type': 'Question', 'name': 'ما هو سعر %s اليوم؟' % name,
             'acceptedAnswer': {'@type': 'Answer', 'text': 'سعر %s حالياً %s د.ك شامل التوصيل المجاني.' % (name, price)}},
            {'@type': 'Question', 'name': 'كيف أطلب %s أونلاين؟' % name,
             'acceptedAnswer': {'@type': 'Answer', 'text': 'اضغط إضافة للسلة ثم أكمل الطلب، والدفع عند الاستلام أو بالكي نت.'}}
        ]
    }, ensure_ascii=False)

    related = [p for p in all_products if p.get('_id') != product.get('_id')][:4]
    related_html = ''.join(
        '<a class="rel-card" href="%s"><img src="%s" alt="%s" loading="lazy">'
        '<div class="rel-body"><div class="rel-name">%s</div>'
        '<div class="rel-price">%s د.ك</div></div></a>'
        % (product_url(p), escape(product_img_url(p) if p.get('img') else '/assets/images/nfc2.png'),
           escape(str(p.get('name', ''))), escape(str(p.get('name', ''))), fmt_price(p.get('price', '0')))
        for p in related
    ) or '<p>تصفح بقية منتجاتنا من <a href="/" style="color:#004d7a">الصفحة الرئيسية</a>.</p>'

    product_js = json.dumps({
        'name': name, 'desc': desc, 'price': str(product.get('price', '0')),
        'img': str(product.get('img') or '')
    }, ensure_ascii=False)

    return _PAGE.format(
        title=escape(title), meta_desc=escape(meta_desc), meta_keys=escape(meta_keys),
        canonical=url, site_name=escape(SITE_NAME), img_abs=escape(img_abs),
        img_rel=escape(img_rel), img_alt=escape('%s - %s الكويت' % (name, SITE_NAME)),
        name=escape(name), desc=escape(desc) or 'منتج طازج من مزرعتنا بجودة مضمونة.',
        desc_sent=escape(desc_sent), price=escape(price),
        product_schema=escape(product_schema, quote=False),
        breadcrumb_schema=escape(breadcrumb_schema, quote=False),
        faq_schema=escape(faq_schema, quote=False),
        related_html=related_html, product_js=product_js,
    )


def render_not_found_html():
    return _NOT_FOUND


# ═══════════════════════ sitemap.xml ديناميكي ═══════════════════════

def render_sitemap_xml(products, lastmod=None):
    lastmod = lastmod or time.strftime('%Y-%m-%d')
    urls = [
        (BASE_URL + '/', '1.0', 'daily'),
        (BASE_URL + '/prices', '0.9', 'daily'),
        (BASE_URL + '/cartepage.html', '0.8', 'daily'),
        (BASE_URL + '/terms.html', '0.3', 'monthly'),
        (BASE_URL + '/privacy.html', '0.3', 'monthly'),
        (BASE_URL + '/returns.html', '0.3', 'monthly'),
    ]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
           '        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"',
           '        xmlns:xhtml="http://www.w3.org/1999/xhtml">']

    def emit(loc, priority, freq, images=()):
        out.append('  <url>')
        out.append('    <loc>%s</loc>' % escape(loc))
        out.append('    <lastmod>%s</lastmod>' % lastmod)
        out.append('    <changefreq>%s</changefreq>' % freq)
        out.append('    <priority>%s</priority>' % priority)
        out.append('    <xhtml:link rel="alternate" hreflang="ar" href="%s"/>' % escape(loc))
        out.append('    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>' % escape(loc))
        for img, cap in images:
            out.append('    <image:image><image:loc>%s</image:loc><image:title>%s</image:title></image:image>'
                       % (escape(img), escape(cap)))
        out.append('  </url>')

    home_images = [(abs_img(p), str(p.get('name', ''))) for p in products[:8] if p.get('img')]
    emit(urls[0][0], urls[0][1], urls[0][2], home_images)
    for loc, prio, freq in urls[1:]:
        emit(loc, prio, freq)
    for p in products:
        loc = BASE_URL + product_url(p)
        images = [(abs_img(p), str(p.get('name', '')))] if p.get('img') else []
        emit(loc, '0.9', 'daily', images)
    out.append('</urlset>')
    return '\n'.join(out)


# ═══════════════════════ صفحة أسعار اليوم (/prices) ═══════════════════════

_AR_DAYS = ['الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت', 'الأحد']
_AR_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
              'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']


def today_arabic():
    t = time.localtime()
    return '%s %d %s %d' % (_AR_DAYS[t.tm_wday], t.tm_mday, _AR_MONTHS[t.tm_mon - 1], t.tm_year)


_PRICES_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>أسعار مزارع الثنيان اليوم {today} — أسعار الروبيان والتين والتمور والدواجن في الكويت</title>
<meta name="description" content="أسعار منتجات مزارع الثنيان اليوم {today}: سعر الروبيان، التين، تمر الصقعي والخلاص، الحمام الزاجل، البط الفرنسي، دجاج الساسو وسمك البلطي في الكويت. أسعار يومية محدّثة مع توصيل مجاني.">
<meta name="keywords" content="اسعار الروبيان اليوم الكويت, سعر التين اليوم, اسعار التمور في الكويت, سعر الحمام الزاجل, سعر دجاج الساسو, اسعار البط الفرنسي, سعر سمك البلطي اليوم, عروض مزارع الكويت, مزارع الثنيان">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{base}/prices">
<meta property="og:type" content="website">
<meta property="og:title" content="أسعار مزارع الثنيان اليوم {today}">
<meta property="og:description" content="أسعار يومية محدّثة لمنتجات المزرعة الطازجة في الكويت مع توصيل مجاني.">
<meta property="og:url" content="{base}/prices">
<meta property="og:image" content="{base}/assets/images/nfc2.png">
<meta name="theme-color" content="#004d7a">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<script type="application/ld+json">{itemlist_schema}</script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; }}
body {{ background: #f8f9fa; color: #111; }}
a {{ text-decoration: none; color: inherit; }}
.header {{ background: #fff; position: sticky; top: 0; z-index: 100; box-shadow: 0 1px 3px rgba(0,0,0,.07); }}
.header-inner {{ max-width: 1000px; margin: 0 auto; padding: 10px 15px; display: flex; justify-content: space-between; align-items: center; }}
.logo img {{ width: 110px; height: 35px; object-fit: contain; display: block; }}
.cart-link {{ background: #004d7a; color: #fff; padding: 8px 18px; border-radius: 10px; font-size: 14px; font-weight: 700; }}
.wrap {{ max-width: 1000px; margin: 0 auto; padding: 15px; }}
.hero {{ background: linear-gradient(135deg, #004d7a, #006ba6); color: #fff; border-radius: 16px; padding: 26px; text-align: center; margin-bottom: 18px; }}
.hero h1 {{ font-size: 23px; margin-bottom: 8px; }}
.hero p {{ opacity: .92; font-size: 14.5px; line-height: 1.9; }}
.date-pill {{ display: inline-block; background: rgba(255,255,255,.18); padding: 5px 16px; border-radius: 20px; font-size: 13.5px; font-weight: 700; margin-top: 10px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
.pcard {{ background: #fff; border-radius: 14px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,.05); display: flex; flex-direction: column; transition: transform .15s; }}
.pcard:hover {{ transform: translateY(-3px); }}
.pcard img {{ width: 100%; height: 150px; object-fit: cover; background: #f1f3f5; }}
.pbody {{ padding: 14px; display: flex; flex-direction: column; gap: 6px; flex: 1; }}
.pname {{ font-weight: 700; font-size: 15px; line-height: 1.5; }}
.pdesc {{ font-size: 13px; color: #666; line-height: 1.7; }}
.pprice {{ font-size: 20px; font-weight: 800; color: #004d7a; margin-top: auto; }}
.pprice small {{ font-size: 12px; color: #1e7e34; font-weight: 700; display: block; }}
.note {{ background: #fff; border-radius: 14px; padding: 20px 24px; margin-top: 18px; box-shadow: 0 2px 8px rgba(0,0,0,.05); }}
.note h2 {{ color: #004d7a; font-size: 17px; margin-bottom: 10px; }}
.note p {{ font-size: 14px; color: #444; line-height: 2; }}
.footer {{ text-align: center; color: #999; font-size: 13px; padding: 26px 15px; }}
</style>
</head>
<body>
<header class="header">
  <div class="header-inner">
    <a class="logo" href="/"><img src="/assets/images/nfc2.png" alt="{site_name}"></a>
    <a class="cart-link" href="/cartepage.html">🛒 سلة الطلبات</a>
  </div>
</header>
<main class="wrap">
  <div class="hero">
    <h1>أسعار منتجات المزرعة اليوم في الكويت</h1>
    <p>أسعار محدّثة يومياً لجميع منتجات {site_name} الطازجة: روبيان، تين، تمور، حمام، بط، دجاج وسمك — جميع الأسعار شاملة التوصيل المجاني لجميع مناطق الكويت.</p>
    <span class="date-pill">📅 {today}</span>
  </div>
  <div class="grid">{cards_html}</div>
  <section class="note">
    <h2>كيف تقرأ أسعار اليوم؟</h2>
    <p>الأسعار المعروضة أعلاه هي أسعار اليوم {today} وتُحدَّث مباشرة من المزرعة. جميع الأسعار بالدينار الكويتي وتشمل التوصيل المجاني خلال 40 دقيقة تقريباً لأي منطقة داخل الكويت، مع إمكانية الدفع عند الاستلام أو بالكي نت. اضغط على أي منتج للاطلاع على تفاصيله وطلبه أونلاين مباشرة.</p>
  </section>
</main>
<footer class="footer">{site_name} — أسعار طازجة يومياً في الكويت 🇰🇼<br>
<a href="/" style="color:#004d7a">الرئيسية</a> · <a href="/terms.html" style="color:#004d7a">الشروط والأحكام</a> · <a href="/privacy.html" style="color:#004d7a">سياسة الخصوصية</a></footer>
</body>
</html>
"""


def render_prices_html(products):
    today = today_arabic()
    cards = []
    for p in products:
        img = product_img_url(p) if p.get('img') else '/assets/images/nfc2.png'
        cards.append(
            '<a class="pcard" href="%s"><img src="%s" alt="سعر %s اليوم في الكويت" loading="lazy">'
            '<div class="pbody"><div class="pname">%s</div>'
            '<div class="pdesc">%s</div>'
            '<div class="pprice">%s د.ك<small>شامل التوصيل المجاني ✅</small></div>'
            '</div></a>'
            % (product_url(p), escape(img), escape(str(p.get('name', ''))),
               escape(str(p.get('name', ''))), escape(str(p.get('desc', ''))),
               fmt_price(p.get('price', '0')))
        )
    itemlist = json.dumps({
        '@context': 'https://schema.org', '@type': 'ItemList',
        'name': 'أسعار مزارع الثنيان اليوم %s' % today,
        'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1,
             'url': BASE_URL + product_url(p), 'name': str(p.get('name', ''))}
            for i, p in enumerate(products)
        ]
    }, ensure_ascii=False)
    return _PRICES_PAGE.format(
        today=today, base=BASE_URL, site_name=SITE_NAME,
        cards_html=''.join(cards), itemlist_schema=escape(itemlist, quote=False),
    )


# ═══════════════════ Google Merchant Center Feed (/feed.xml) ═══════════════════

def render_feed_xml(products):
    """ملف منتجات بصيغة RSS 2.0 المتوافقة مع Google Merchant Center."""
    items = []
    for p in products:
        name = str(p.get('name') or 'منتج')
        desc = str(p.get('desc') or name)
        link = BASE_URL + product_url(p)
        items.append(
            '  <item>\n'
            '    <g:id>%s</g:id>\n'
            '    <title>%s</title>\n'
            '    <description>%s</description>\n'
            '    <link>%s</link>\n'
            '    <g:image_link>%s</g:image_link>\n'
            '    <g:price>%s KWD</g:price>\n'
            '    <g:availability>in_stock</g:availability>\n'
            '    <g:condition>new</g:condition>\n'
            '    <g:brand>%s</g:brand>\n'
            '    <g:identifier_exists>no</g:identifier_exists>\n'
            '    <g:shipping><g:country>KW</g:country><g:price>0.000 KWD</g:price></g:shipping>\n'
            '  </item>'
            % (escape(p.get('_id', '')), escape(name), escape(desc), escape(link),
               escape(abs_img(p)), fmt_price(p.get('price', '0')), escape(SITE_NAME))
        )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n'
            '<channel>\n'
            '  <title>%s</title>\n'
            '  <link>%s</link>\n'
            '  <description>منتجات %s الطازجة مع توصيل مجاني في الكويت</description>\n'
            '%s\n</channel>\n</rss>'
            % (escape(SITE_NAME), BASE_URL, escape(SITE_NAME), '\n'.join(items)))

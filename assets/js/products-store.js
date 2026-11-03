/**
 * products-store.js — طبقة مزامنة المنتجات مع Cloud Firestore
 * -----------------------------------------------------------
 * توفر واجهة موحّدة لقراءة/كتابة المنتجات:
 *  - المصدر الأساسي: مجموعة products في Firestore (إدارة مركزية من أي جهاز)
 *  - الاحتياطي: localStorage.allProducts (في حال انقطاع الاتصال)
 * تعتمد على firebase-client.js (يجب تحميله قبلها).
 */
(function () {
  const LS_KEY = 'allProducts';

  function validOnly(list) {
    return (Array.isArray(list) ? list : []).filter(p => p && p.name && p.img && p.price);
  }

  /** بصمة المنتج للمقارنة بين المصادر (اسم + سعر + وصف). تُستخدم لإحياء منتجات
   *  حُذفت سهواً من قاعدة البيانات عند إعادة الترتيب من اللوحة. */
  function productKey(p) {
    return [p.name || '', String(p.price || ''), p.desc || ''].join('\u0000');
  }

  /** دمج مصدرين بترتيب يحافظ على الموضع: قاعدة البيانات لها الأولوية، وأي
   *  منتج محلي مفقود من قاعدة البيانات يُدرَج في **موضعه الأصلي** من القائمة
   *  المحلية (لا في الأسفل). هكذا لا يختفي منتج ولا يتغيّر ترتيبه عند المزامنة. */
  function mergeProducts(remote, local) {
    const rem = remote || [];
    const loc = local || [];
    const remKeys = new Set(rem.map(productKey));
    const locKeys = new Set(loc.map(productKey));
    const out = [];
    const seen = new Set();
    let recovered = 0;

    const pushRemote = (p) => { const k = productKey(p); if (!seen.has(k)) { seen.add(k); out.push(p); } };
    const pushLocal = (p) => { const k = productKey(p); if (!seen.has(k)) { seen.add(k); out.push(p); recovered++; } };

    let i = 0, j = 0;
    while (i < rem.length && j < loc.length) {
      const rk = productKey(rem[i]);
      const lk = productKey(loc[j]);
      if (rk === lk) { pushRemote(rem[i]); i++; j++; continue; }
      if (!remKeys.has(lk)) { pushLocal(loc[j]); j++; continue; } // محلي مفقود → موضعه
      if (!locKeys.has(rk)) { pushRemote(rem[i]); i++; continue; } // بعيد جديد → موضعه
      pushRemote(rem[i]); i++; // اختلاف ترتيب → ترتيب قاعدة البيانات
    }
    while (i < rem.length) { pushRemote(rem[i]); i++; }
    while (j < loc.length) { pushLocal(loc[j]); j++; }

    if (recovered) console.warn('products-store: أُعيد %d منتجاً محلياً مفقوداً من قاعدة البيانات', recovered);
    return out;
  }

  function readLocalStorage() {
    try { return validOnly(JSON.parse(localStorage.getItem(LS_KEY))); }
    catch (e) { return []; }
  }

  /**
   * المصدر المحلي الأفضل: ملف المشروع المولّد (LOCAL_PRODUCTS) مقابل نسخة
   * المتصفح. نأخذ الأغنى لأن localStorage قد يحمل لقطة قديمة أصغر (منتجات
   * افتراضية قديمة) فتُخفي منتجات حقيقية عند اكتمال المزامنة.
   */
  function readLocal() {
    const fromFile = validOnly(window.LOCAL_PRODUCTS);
    const fromLS = readLocalStorage();
    return fromLS.length > fromFile.length ? fromLS : fromFile;
  }

  /** مرجع استرجاع المنتجات المفقودة عند الدمج: ملف المشروع المولّد
   *  (LOCAL_PRODUCTS) — لقطة سليمة يُحدّثها sync_products.py بعد أي حذف/إضافة
   *  شرعية فلا يُحيي محذوفاً، ولا يحمل أي بيانات قديمة عالقة في المتصفح. */
  function mergeRef() {
    const fromFile = validOnly(window.LOCAL_PRODUCTS);
    return fromFile.length ? fromFile : readLocalStorage();
  }

  function writeLocal(products) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(products)); } catch (e) {}
  }

  function firestoreAvailable() {
    return !!(window.db && typeof window.db.collection === 'function');
  }

  /** جلب المنتجات: Firestore أولاً، ثم المحلي عند الفشل */
  window.storeGetProducts = async function () {
    if (firestoreAvailable()) {
      // orderBy('order') يفشل إن كانت وثيقة بلا حقل order أو إن كان الفهرس ناقصاً
      for (const useOrder of [true, false]) {
        try {
          const col = window.db.collection('products');
          const snap = await (useOrder ? col.orderBy('order', 'asc') : col).get();
          const items = snap.docs.map(d => ({ _id: d.id, ...d.data() }));
          const valid = items.filter(p => p.name && p.img && p.price);
          if (valid.length) {
            // دمج مع المحلي حتى لا تختفي منتجات فقدت وثائقها من قاعدة البيانات
            const merged = mergeProducts(valid, mergeRef());
            writeLocal(merged); // مزامنة النسخة المحلية
            return merged;
          }
          break; // المجموعة فارغة أو كل وثائقها ناقصة → استخدم المحلي
        } catch (e) {
          if (!useOrder) console.warn('Firestore products read failed, using local:', e);
        }
      }
    }
    return readLocal();
  };

  /** حفظ القائمة كاملة (إضافة/تعديل/حذف/إعادة ترتيب) */
  window.storeSaveProducts = async function (products) {
    writeLocal(products); // تحديث فوري محلياً
    if (!firestoreAvailable()) return false;
    try {
      const col = window.db.collection('products');
      const existing = await col.get();
      const batch = window.db.batch();
      // حذف الوثائق التي لم تعد موجودة — لكن فقط إن كانت القائمة تحمل معرّفات
      // (_id). قائمة بلا أي معرّف (مثل القائمة الافتراضية عند فقدان المصدر)
      // لا يجوز أن تمحو كل منتجات قاعدة البيانات.
      const keepIds = new Set(products.filter(p => p._id).map(p => p._id));
      if (keepIds.size) {
        existing.docs.forEach(doc => {
          if (!keepIds.has(doc.id)) batch.delete(doc.ref);
        });
      }
      // كتابة/تحديث كل المنتجات مع ترتيبها
      products.forEach((p, i) => {
        const data = {
          name: p.name, desc: p.desc, price: p.price, img: p.img,
          order: i,
          updatedAt: firebase.firestore.FieldValue.serverTimestamp()
        };
        if (p._id) {
          batch.set(col.doc(p._id), data, { merge: true });
        } else {
          batch.set(col.doc(), { ...data, createdAt: firebase.firestore.FieldValue.serverTimestamp() });
        }
      });
      await batch.commit();
      return true;
    } catch (e) {
      console.error('Firestore products save failed:', e);
      return false;
    }
  };

  /** الاستماع اللحظي لتغييرات المنتجات (لتحديث واجهة العميل مباشرة) */
  window.storeWatchProducts = function (onChange) {
    if (!firestoreAvailable()) return function () {};
    let unsub = function () {};
    const attach = (useOrder) => {
      const col = window.db.collection('products');
      return (useOrder ? col.orderBy('order', 'asc') : col)
        .onSnapshot((snap) => {
          const items = snap.docs.map(d => ({ _id: d.id, ...d.data() }));
          const valid = items.filter(p => p.name && p.img && p.price);
          if (valid.length) {
            const merged = mergeProducts(valid, mergeRef());
            writeLocal(merged);
            onChange(merged);
          }
        }, (err) => {
          // فشل orderBy (فهرس ناقص) → أعِد الاشتراك بدون ترتيب
          if (useOrder) { console.warn('products watch retry without order:', err && err.code); unsub = attach(false); }
          else console.warn('products watch error:', err);
        });
    };
    try {
      unsub = attach(true);
      return function () { try { unsub(); } catch (e) {} };
    } catch (e) {
      return function () {};
    }
  };
})();

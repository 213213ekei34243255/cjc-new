/*!
 * Noah - Christ Junior College assistant widget.
 * One file, no dependencies. Embed with:
 *   <script src="https://YOUR-SERVER/widget.js" data-api="https://YOUR-SERVER" defer></script>
 * Everything the visitor sees (chat, stream advisor, callback and visit booking, documents checklist,
 * careers, events, wellness, Student Zone, and the staff panel) is rendered from this file inside a
 * shadow root, so the college site's own CSS can never break it and it can never break the site.
 */
(function () {
  'use strict';
  if (window.__NOAH_WIDGET__) return;
  window.__NOAH_WIDGET__ = true;

  var thisScript = document.currentScript || Array.prototype.slice.call(document.scripts).reverse().find(function (s) { return s.src && /widget\.js/.test(s.src); });
  var BASE = ((thisScript && thisScript.getAttribute('data-api')) || (thisScript && thisScript.src && new URL(thisScript.src).origin) || 'https://www.byncai.net').replace(/\/$/, '');

  function boot() {
    try { start(); } catch (e) { console.error('[NOAH] failed to start', e); }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

  function start() {
    /* ============================================================================================
     * 1. Small utilities
     * ========================================================================================== */
    var VERSION = '2026-10-31.5';
    var LS = {
      get: function (k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
      set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
      del: function (k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }
    };
    var SS = {
      get: function (k, d) { try { var v = sessionStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } },
      set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* ignore */ } },
      del: function (k) { try { sessionStorage.removeItem(k); } catch (e) { /* ignore */ } }
    };

    function h(tag, props) {
      var e = document.createElement(tag);
      var p = props || {};
      Object.keys(p).forEach(function (k) {
        var v = p[k];
        if (v === null || v === undefined || v === false) return;
        if (k === 'class') e.className = v;
        else if (k === 'style') e.style.cssText = v;
        else if (k === 'html') e.innerHTML = v;                       // only ever fed escaped text or static strings
        else if (k.slice(0, 2) === 'on' && typeof v === 'function') e.addEventListener(k.slice(2).toLowerCase(), v);
        else e.setAttribute(k, v === true ? '' : v);
      });
      for (var i = 2; i < arguments.length; i++) append(e, arguments[i]);
      return e;
    }
    function append(parent, kid) {
      if (kid === null || kid === undefined || kid === false) return;
      if (Array.isArray(kid)) { kid.forEach(function (k) { append(parent, k); }); return; }
      parent.appendChild(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
    /** Like Element.append but skips null/false and flattens arrays (native append would print "null"). */
    function put(parent) { for (var i = 1; i < arguments.length; i++) append(parent, arguments[i]); return parent; }
    function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function safeUrl(u) { return /^https?:\/\//i.test(u) ? u : '#'; }

    /** Tiny, safe markdown: **bold**, "- " bullets, bare links, line breaks. Input is escaped first. */
    function md(text) {
      var lines = esc(text || '').split('\n'), out = [], list = false;
      lines.forEach(function (line) {
        var m = /^\s*(?:[-*•])\s+(.*)$/.exec(line);
        if (m) { if (!list) { out.push('<ul>'); list = true; } out.push('<li>' + inline(m[1]) + '</li>'); return; }
        if (list) { out.push('</ul>'); list = false; }
        out.push(line.trim() ? inline(line) + '<br>' : '<br>');
      });
      if (list) out.push('</ul>');
      return out.join('').replace(/(<br>)+$/, '').replace(/<br><br>(<br>)+/g, '<br><br>');
      function inline(s) {
        return s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
          .replace(/(https?:\/\/[^\s<]+[^\s<.,;:!?)\]])/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
      }
    }

    function uid() { return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : 'sess-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10); }
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function inr(n) { return typeof n === 'number' ? '₹' + n.toLocaleString('en-IN') : String(n); }
    function prettyDate(iso) { var d = new Date(iso + 'T00:00:00'); return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' }); }
    function reduceMotion() { return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches; }

    /* ============================================================================================
     * 2. Languages (static interface text only; answers are translated by the server)
     * Native-speaker review is recommended before launch.
     * ========================================================================================== */
    var LANGS = [
      { code: 'en', native: 'English', speech: 'en-IN' }, { code: 'kn', native: 'ಕನ್ನಡ', speech: 'kn-IN' },
      { code: 'hi', native: 'हिन्दी', speech: 'hi-IN' }, { code: 'ta', native: 'தமிழ்', speech: 'ta-IN' },
      { code: 'ml', native: 'മലയാളം', speech: 'ml-IN' }, { code: 'te', native: 'తెలుగు', speech: 'te-IN' }
    ];
    var I18N = {
      en: { placeholder: 'Write a message...', send: 'Send', tools: 'Tools', listening: 'Listening...', back: 'Back', close: 'Close', language: 'Language', privacy: 'Chats may be read by college staff to improve answers.', advisor: 'Stream Advisor', callback: 'Talk to admissions', visit: 'Book a campus visit', documents: 'Documents checklist', careers: 'Career paths', events: 'Events', wellness: 'Wellness check-in', student: 'Student Zone', compare: 'PU vs IBDP', helpful: 'Helpful', notHelpful: 'Not helpful', copy: 'Copy', speak: 'Read aloud', mic: 'Speak', newChat: 'New chat', offline: 'Could not reach the server. Check your connection and try again.', thanks: 'Thanks for the feedback', welcome: 'What would you like to do?', online: 'Online', studyMode: 'Study helper mode', exit: 'Exit' },
      hi: { placeholder: 'संदेश लिखें...', send: 'भेजें', tools: 'टूल्स', listening: 'सुन रहा हूँ...', back: 'वापस', close: 'बंद करें', language: 'भाषा', privacy: 'बेहतर उत्तरों के लिए कॉलेज स्टाफ़ चैट देख सकता है।', advisor: 'स्ट्रीम सलाहकार', callback: 'एडमिशन टीम से बात करें', visit: 'कैंपस विज़िट बुक करें', documents: 'दस्तावेज़ सूची', careers: 'करियर के रास्ते', events: 'कार्यक्रम', wellness: 'वेलनेस चेक-इन', student: 'स्टूडेंट ज़ोन', welcome: 'आप क्या करना चाहेंगे?' },
      kn: { placeholder: 'ಸಂದೇಶ ಬರೆಯಿರಿ...', send: 'ಕಳುಹಿಸಿ', tools: 'ಸಾಧನಗಳು', listening: 'ಆಲಿಸುತ್ತಿದ್ದೇನೆ...', back: 'ಹಿಂದೆ', close: 'ಮುಚ್ಚಿ', language: 'ಭಾಷೆ', privacy: 'ಉತ್ತಮ ಉತ್ತರಗಳಿಗಾಗಿ ಕಾಲೇಜು ಸಿಬ್ಬಂದಿ ಚಾಟ್‌ಗಳನ್ನು ನೋಡಬಹುದು.', advisor: 'ಸ್ಟ್ರೀಮ್ ಸಲಹೆಗಾರ', callback: 'ಪ್ರವೇಶ ತಂಡದೊಂದಿಗೆ ಮಾತನಾಡಿ', visit: 'ಕ್ಯಾಂಪಸ್ ಭೇಟಿ ಬುಕ್ ಮಾಡಿ', documents: 'ದಾಖಲೆಗಳ ಪಟ್ಟಿ', careers: 'ವೃತ್ತಿ ಮಾರ್ಗಗಳು', events: 'ಕಾರ್ಯಕ್ರಮಗಳು', wellness: 'ಯೋಗಕ್ಷೇಮ ಪರಿಶೀಲನೆ', student: 'ವಿದ್ಯಾರ್ಥಿ ವಿಭಾಗ', welcome: 'ನೀವು ಏನು ಮಾಡಲು ಬಯಸುವಿರಿ?' },
      ta: { placeholder: 'செய்தியை எழுதுங்கள்...', send: 'அனுப்பு', tools: 'கருவிகள்', listening: 'கேட்கிறேன்...', back: 'பின்', close: 'மூடு', language: 'மொழி', privacy: 'சிறந்த பதில்களுக்காக கல்லூரி ஊழியர்கள் அரட்டைகளைப் பார்க்கலாம்.', advisor: 'ஸ்ட்ரீம் ஆலோசகர்', callback: 'சேர்க்கைக் குழுவிடம் பேசுங்கள்', visit: 'வளாக வருகையை பதிவு செய்யுங்கள்', documents: 'ஆவணப் பட்டியல்', careers: 'தொழில் வழிகள்', events: 'நிகழ்வுகள்', wellness: 'நலன் சோதனை', student: 'மாணவர் மண்டலம்', welcome: 'நீங்கள் என்ன செய்ய விரும்புகிறீர்கள்?' },
      ml: { placeholder: 'സന്ദേശം എഴുതുക...', send: 'അയയ്ക്കുക', tools: 'ടൂളുകൾ', listening: 'കേൽക്കുന്നു...', back: 'തിരികെ', close: 'അടയ്ക്കുക', language: 'ഭാഷ', privacy: 'മികച്ച ഉത്തരങ്ങൾക്കായി കോളേജ് സ്റ്റാഫിന് ചാറ്റുകൾ കാണാം.', advisor: 'സ്ട്രീം ഉപദേഷ്ടാവ്', callback: 'പ്രവേശന ടീമുമായി സംസാരിക്കുക', visit: 'ക്യാമ്പസ് സന്ദർശനം ബുക്ക് ചെയ്യുക', documents: 'രേഖകളുടെ പട്ടിക', careers: 'കരിയർ വഴികൾ', events: 'പരിപാടികൾ', wellness: 'ക്ഷേമ പരിശോധന', student: 'വിദ്യാർത്ഥി മേഖല', welcome: 'നിങ്ങൾ എന്ത് ചെയ്യാൻ ആഗ്രഹിക്കുന്നു?' },
      te: { placeholder: 'సందేశం రాయండి...', send: 'పంపండి', tools: 'సాధనాలు', listening: 'వింటున్నాను...', back: 'వెనుకకు', close: 'మూసివేయి', language: 'భాష', privacy: 'మెరుగైన సమాధానాల కోసం కళాశాల సిబ్బంది చాట్‌లను చూడవచ్చు.', advisor: 'స్ట్రీమ్ సలహాదారు', callback: 'ప్రవేశ బృందంతో మాట్లాడండి', visit: 'క్యాంపస్ సంస్లేషను బుక్ చేయండి', documents: 'పత్రాల జాబితా', careers: 'కెరీర్ మార్గాలు', events: 'కార్యక్రమాలు', wellness: 'ఆరోగ్య తనిఖీ', student: 'విద్యార్థి జోన్', welcome: 'మీరు ఏమి చేయాలనుకుంటున్నారు?' }
    };

    /* ============================================================================================
     * 3. State
     * ========================================================================================== */
    var S = {
      sid: LS.get('veronica_session_id_v1') || (function () { var i = uid(); LS.set('veronica_session_id_v1', i); return i; })(),
      lang: LS.get('noah_lang', ''), theme: LS.get('noah_theme', 'auto'),
      open: false, busy: false, mode: 'chat', speakNext: false,
      student: null, staff: null, ctx: null, recognizing: false, abort: null
    };
    try { S.student = JSON.parse(SS.get('noah_student', 'null')); } catch (e) { S.student = null; }
    try { S.staff = JSON.parse(SS.get('noah_staff', 'null')); } catch (e) { S.staff = null; }
    if (!S.lang) {
      var nav = (navigator.language || 'en').slice(0, 2).toLowerCase();
      S.lang = LANGS.some(function (l) { return l.code === nav; }) ? nav : 'en';
    }
    function T(key) { return (I18N[S.lang] && I18N[S.lang][key]) || I18N.en[key] || key; }

    /* ============================================================================================
     * 4. Icons (Feather-style, stroke only)
     * ========================================================================================== */
    var ICONS = {
      chat: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
      x: '<path d="M18 6L6 18M6 6l12 12"/>',
      send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
      mic: '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8"/>',
      globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
      grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
      back: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
      up: '<path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>',
      down: '<path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3zm7-13h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>',
      copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
      speaker: '<path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>',
      compass: '<circle cx="12" cy="12" r="10"/><path d="M16.24 7.76l-2.12 6.36-6.36 2.12 2.12-6.36 6.36-2.12z"/>',
      phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
      calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
      file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/>',
      trend: '<path d="M23 6l-9.5 9.5-5-5L1 18"/><path d="M17 6h6v6"/>',
      flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1zM4 22v-7"/>',
      heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
      user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
      book: '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
      sun: '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>',
      moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
      check: '<path d="M20 6L9 17l-5-5"/>',
      clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
      pin: '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
      shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
      refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
      logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
      chart: '<path d="M12 20V10M18 20V4M6 20v-4"/>',
      printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
      download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
      layers: '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
      next: '<path d="M9 18l6-6-6-6"/>',
      trash: '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
      key: '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.78 7.78 5.5 5.5 0 0 1 7.78-7.78zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>',
      inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
      info: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
      mail: '<path d="M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M22 6l-10 7L2 6"/>',
      link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
      star: '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>',
      dots: '<circle cx="12" cy="5" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="12" cy="19" r="1.4"/>',
      users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>'
    };
    function icon(name, size) {
      var s = h('span', { class: 'nw-ic', 'aria-hidden': 'true' });
      s.innerHTML = '<svg viewBox="0 0 24 24" width="' + (size || 18) + '" height="' + (size || 18) + '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || '') + '</svg>';
      return s;
    }

    var TOOLS = [
      { id: 'advisor', icon: 'compass', key: 'advisor', hue: '#e0148c', blurb: 'Find the stream that fits you' },
      { id: 'callback', icon: 'phone', key: 'callback', hue: '#1746d1', blurb: 'We call you back' },
      { id: 'visit', icon: 'calendar', key: 'visit', hue: '#0e9f6e', blurb: 'Pick a day and time' },
      { id: 'documents', icon: 'file', key: 'documents', hue: '#d97706', blurb: 'Tick off and save as PDF' },
      { id: 'careers', icon: 'trend', key: 'careers', hue: '#7c3aed', blurb: 'Exams, courses, careers' },
      { id: 'events', icon: 'flag', key: 'events', hue: '#0891b2', blurb: 'Dates, links, reminders' },
      { id: 'wellness', icon: 'heart', key: 'wellness', hue: '#dc2626', blurb: 'Private. Not saved' },
      { id: 'student', icon: 'user', key: 'student', hue: '#4f46e5', blurb: 'Exams, quizzes, flashcards' }
    ];

    /* ============================================================================================
     * 5. Styles
     * ========================================================================================== */
    var CSS = [
      ':host{all:initial}',
      '.nw,.nw *{box-sizing:border-box}',
      '.nw{--bg:#f3f5fb;--surface:#fff;--surface2:#eceff8;--text:#0f1530;--muted:#5a6483;--line:rgba(15,21,48,.1);--brand:#e0148c;--brand2:#1746d1;--mint:#17f38c;--ok:#0f9d63;--warn:#c27003;--bad:#d92d20;--shadow:0 22px 60px rgba(8,12,40,.32);position:fixed;right:20px;bottom:20px;z-index:2147483000;font:14px/1.45 Inter,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans","Noto Sans Kannada","Noto Sans Devanagari","Noto Sans Tamil","Noto Sans Malayalam","Noto Sans Telugu",sans-serif;color:var(--text);-webkit-font-smoothing:antialiased}',
      '.nw[data-theme=dark]{--bg:#0d1120;--surface:#161b31;--surface2:#212848;--text:#eef0fb;--muted:#9ba5c6;--line:rgba(255,255,255,.1);--brand:#ff4fb4;--brand2:#6f8cff;--ok:#2ee59d;--warn:#ffb84d;--bad:#ff7066;--shadow:0 22px 60px rgba(0,0,0,.6)}',
      '.nw :where(button){font:inherit;color:inherit;cursor:pointer}',
      '.nw :where(a){color:var(--brand2)}',
      '.nw ul{margin:4px 0 4px 18px;padding:0}',
      '.nw [hidden]{display:none!important}',
      '.nw-ic{display:inline-grid;place-items:center;line-height:0}',
      /* launcher */
      '.nw-fab{position:relative;width:64px;height:64px;border:0;border-radius:50%;padding:0;background:transparent;display:grid;place-items:center;float:right;filter:drop-shadow(0 8px 18px rgba(0,0,0,.28));transition:transform .25s cubic-bezier(.2,.9,.3,1.4)}',
      '.nw-fab:hover{transform:scale(1.08) rotate(-4deg)}',
      '.nw-fab::before{content:"";position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,#e0148c,#17f38c,#1746d1,#e0148c);animation:nw-spin 5s linear infinite}',
      '.nw-fab::after{content:"";position:absolute;inset:4px;border-radius:50%;background:radial-gradient(circle at 30% 25%,#7bffc6,#17f38c 55%,#0bbd68)}',
      '.nw-fab .nw-ic{position:relative;z-index:1;color:#05261a}',
      '.nw-fab .nw-ic svg{width:28px;height:28px}',
      '.nw-fab.open .nw-ic.c{display:none}.nw-fab:not(.open) .nw-ic.x{display:none}',
      '.nw-fab .dot{position:absolute;z-index:2;top:2px;right:2px;width:15px;height:15px;border-radius:50%;background:#e0148c;border:2px solid #fff;animation:nw-pulse 2s infinite}',
      '.nw-teaser{position:absolute;right:0;bottom:78px;width:max-content;min-width:170px;max-width:250px;background:var(--surface);color:var(--text);padding:11px 30px 11px 14px;border-radius:16px 16px 4px 16px;box-shadow:var(--shadow);border:1px solid var(--line);animation:nw-pop .5s cubic-bezier(.2,.9,.3,1.3);cursor:pointer;font-size:13.5px}',
      '.nw-teaser button{position:absolute;top:4px;right:4px;width:24px;height:24px;border:0;background:transparent;border-radius:50%;color:var(--muted)}',
      '.nw-teaser[hidden]{display:none}',
      /* window */
      '.nw-win{position:absolute;right:0;bottom:78px;width:404px;max-width:calc(100vw - 24px);height:min(690px,calc(100vh - 110px));display:flex;flex-direction:column;background:var(--bg);border-radius:24px;overflow:hidden;box-shadow:var(--shadow);border:1px solid var(--line);transform-origin:100% 100%;transform:scale(.85) translateY(16px);opacity:0;visibility:hidden;transition:transform .34s cubic-bezier(.2,.9,.25,1.12),opacity .2s ease,visibility 0s .34s}',
      '.nw-win.open{transform:none;opacity:1;visibility:visible;transition:transform .34s cubic-bezier(.2,.9,.25,1.12),opacity .2s ease}',
      '@media(max-width:520px){.nw{right:0;bottom:0}.nw-fab{position:fixed;right:16px;bottom:16px}.nw-teaser{position:fixed;right:16px;bottom:92px}.nw-win{position:fixed;inset:0;width:100%;max-width:none;height:100vh;height:100dvh;border-radius:0;border:0}.nw-fab.open{display:none}}',
      /* header */
      '.nw-head{position:relative;flex:none;display:flex;align-items:center;gap:10px;padding:14px 12px 14px 14px;color:#000;overflow:hidden;background:url("' + BASE + '/static/charlie.jpeg") center/cover no-repeat,#cfe8f1;min-height:92px}',
      '.nw-logo{flex:none;display:block;line-height:0}',
      '.nw-logo img{width:128px;height:auto;display:block}',
      '.nw-title{flex:1;min-width:0;align-self:center}.nw-title b{display:block;font-size:17px;font-weight:700;color:#000;line-height:1.15}',
      '.nw-title span{display:block;font-size:13px;color:#000;line-height:1.2;white-space:nowrap}',
      '.nw-hbs{position:absolute;top:8px;right:10px;z-index:2;display:flex;gap:5px}',
      '.nw-hb{height:28px;min-width:28px;border:0;border-radius:15px;background:rgba(255,255,255,.82);color:#14213d;display:grid;place-items:center;box-shadow:0 1px 5px rgba(0,0,0,.22);transition:background .15s,transform .15s}',
      '.nw-hb:hover{background:#fff;transform:translateY(-1px)}',
      '.nw-hb.lang{display:flex;align-items:center;gap:4px;padding:0 9px;font-size:11.5px;font-weight:700}',
      '@media(max-width:400px){.nw-logo img{width:100px}.nw-title b{font-size:16px}.nw-title span{font-size:12px}.nw-head{gap:8px}}',
      /* body + messages */
      '.nw-body{position:relative;flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}',
      '.nw-msgs{flex:1;overflow-y:auto;padding:14px 12px 4px;display:flex;flex-direction:column;gap:10px;scroll-behavior:smooth;overscroll-behavior:contain}',
      '.nw-msgs::-webkit-scrollbar,.nw-pbody::-webkit-scrollbar{width:6px}.nw-msgs::-webkit-scrollbar-thumb,.nw-pbody::-webkit-scrollbar-thumb{background:var(--line);border-radius:3px}',
      '.nw-row{display:flex;gap:8px;align-items:flex-end;animation:nw-in .32s cubic-bezier(.2,.9,.3,1.1) both}',
      '.nw-row.bot{align-items:flex-start}.nw-row.user{justify-content:flex-end}',
      '.nw-av{width:28px;height:28px;border-radius:50%;background:linear-gradient(135deg,#1746d1,#e0148c);color:#fff;font-weight:800;font-size:13px;flex:none;display:grid;place-items:center;box-shadow:0 2px 8px rgba(0,0,0,.18)}',
      '.nw-col{display:flex;flex-direction:column;gap:6px;min-width:0;max-width:calc(100% - 40px)}',
      '.nw-bub{padding:10px 13px;border-radius:5px 18px 18px 18px;background:var(--surface);border:1px solid var(--line);word-wrap:break-word;overflow-wrap:anywhere;box-shadow:0 2px 8px rgba(10,15,40,.05)}',
      '.nw-row.user .nw-bub{background:linear-gradient(135deg,#e0148c,#a30e68);color:#fff;border:0;border-radius:18px 18px 5px 18px;max-width:82%;box-shadow:0 6px 18px rgba(224,20,140,.28)}',
      '.nw-row.user .nw-bub a{color:#fff}',
      '.nw-bub.live::after{content:"";display:inline-block;width:7px;height:15px;margin-left:2px;vertical-align:-2px;border-radius:2px;background:var(--brand);animation:nw-blink .9s steps(2) infinite}',
      '.nw-typing{display:inline-flex;gap:4px;padding:3px 2px}.nw-typing i{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:nw-bounce 1.1s infinite}.nw-typing i:nth-child(2){animation-delay:.15s}.nw-typing i:nth-child(3){animation-delay:.3s}',
      '.nw-meta{display:flex;gap:2px;opacity:0;transition:opacity .2s}.nw-row:hover .nw-meta,.nw-meta.keep{opacity:1}',
      '.nw-mb{width:26px;height:26px;border:0;border-radius:8px;background:transparent;color:var(--muted);display:grid;place-items:center}.nw-mb:hover{background:var(--surface2);color:var(--text)}.nw-mb.on{color:var(--brand);background:var(--surface2)}',
      '.nw-acts{display:flex;flex-wrap:wrap;gap:6px}',
      /* chips + composer */
      '.nw-chips{flex:none;display:flex;gap:8px;padding:6px 12px 8px;overflow-x:auto;scrollbar-width:none}.nw-chips::-webkit-scrollbar{display:none}.nw-chips:empty{display:none}',
      '.nw-chip{flex:none;border:1px solid var(--line);background:var(--surface);color:var(--text);padding:7px 13px;border-radius:999px;font-size:13px;white-space:nowrap;transition:transform .15s,box-shadow .15s,border-color .15s;animation:nw-in .35s both}.nw-chip:hover{transform:translateY(-2px);border-color:var(--brand);box-shadow:0 6px 14px rgba(224,20,140,.16)}',
      '.nw-comp{position:relative;z-index:8;flex:none;display:flex;align-items:flex-end;gap:8px;padding:10px 12px 8px;background:var(--surface);border-top:1px solid var(--line)}',
      '.nw-input{flex:1;min-height:40px;max-height:110px;overflow-y:hidden;resize:none;border:1px solid var(--line);background:var(--bg);color:var(--text);border-radius:20px;padding:10px 14px;font:inherit;outline:none;transition:border-color .15s,box-shadow .15s}',
      '.nw-input:focus{border-color:var(--brand);box-shadow:0 0 0 3px rgba(224,20,140,.15)}',
      '.nw-ib2{width:40px;height:40px;border:0;border-radius:50%;background:var(--surface2);color:var(--text);display:grid;place-items:center;flex:none;transition:transform .15s,background .15s}.nw-ib2:hover{transform:scale(1.07)}',
      '.nw-ib2.on{background:#d92d20;color:#fff;animation:nw-pulse-red 1.2s infinite}',
      '.nw-send{background:linear-gradient(135deg,#e0148c,#a30e68);color:#fff;box-shadow:0 6px 16px rgba(224,20,140,.38)}.nw-send:disabled{opacity:.45;box-shadow:none;transform:none}',
      '.nw-win.haspanel .nw-comp,.nw-win.haspanel .nw-foot{display:none}',
      '.nw-ver{opacity:.7;white-space:nowrap}',
      '.nw-foot{position:relative;z-index:8;flex:none;font-size:11px;color:var(--muted);text-align:center;padding:0 12px 8px;background:var(--surface)}.nw-foot a{color:var(--muted)}',
      '.nw-banner{flex:none;display:flex;align-items:center;gap:8px;padding:8px 12px;background:linear-gradient(90deg,#4f46e5,#7c3aed);color:#fff;font-size:12.5px}.nw-banner[hidden]{display:none}.nw-banner button{margin-left:auto;border:0;border-radius:12px;padding:3px 10px;background:rgba(255,255,255,.2);color:#fff}',
      /* cards in chat */
      '.nw-card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;animation:nw-in .4s both;overflow:hidden}',
      '.nw-card h4{margin:0 0 8px;font-size:13.5px;display:flex;align-items:center;gap:6px}',
      '.nw-card.warn{border-color:rgba(217,45,32,.4);background:linear-gradient(180deg,rgba(217,45,32,.09),var(--surface))}',
      '.nw-fee{display:grid;grid-template-columns:auto 1fr auto;gap:2px 10px;align-items:center;padding:6px 0;border-top:1px dashed var(--line)}.nw-fee:first-of-type{border-top:0}',
      '.nw-code{font-weight:700;font-size:12px;padding:3px 8px;border-radius:8px;background:var(--surface2)}',
      '.nw-fee small{color:var(--muted);grid-column:2/4;grid-row:2}',
      '.nw-bar{height:6px;border-radius:3px;background:var(--surface2);overflow:hidden;grid-column:1/4}.nw-bar i{display:block;height:100%;width:0;border-radius:3px;background:linear-gradient(90deg,#1746d1,#e0148c);transition:width .9s cubic-bezier(.2,.8,.2,1)}',
      '.nw-kv{display:flex;gap:10px;padding:6px 0;border-top:1px dashed var(--line);align-items:flex-start}.nw-kv:first-of-type{border-top:0}.nw-kv span{color:var(--muted);flex:none;width:84px;font-size:12px;padding-top:1px}.nw-kv b{font-weight:500;min-width:0;overflow-wrap:anywhere}',
      /* buttons + forms */
      '.nw-btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;border:0;border-radius:12px;padding:10px 16px;font-weight:600;background:linear-gradient(135deg,#1746d1,#5a1fb3);color:#fff;box-shadow:0 6px 16px rgba(23,70,209,.28);transition:transform .15s,box-shadow .15s,opacity .15s;text-decoration:none;font-size:13.5px}',
      '.nw-btn:hover{transform:translateY(-1px)}.nw-btn:disabled{opacity:.5;transform:none;cursor:default}',
      '.nw-btn.pink{background:linear-gradient(135deg,#e0148c,#a30e68);box-shadow:0 6px 16px rgba(224,20,140,.3)}',
      '.nw-btn.ghost{background:var(--surface);color:var(--text);box-shadow:none;border:1px solid var(--line)}',
      '.nw-btn.sm{padding:7px 12px;font-size:12.5px;border-radius:10px}.nw-btn.block{width:100%}',
      '.nw-btn.danger{background:linear-gradient(135deg,#d92d20,#a31d14);box-shadow:0 6px 16px rgba(217,45,32,.3)}',
      '.nw-field{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}.nw-field>label,.nw-lab{font-size:12px;font-weight:600;color:var(--muted)}',
      '.nw-f{width:100%;min-height:42px;border:1px solid var(--line);background:var(--surface);color:var(--text);border-radius:12px;padding:10px 12px;font:inherit;outline:none;transition:border-color .15s,box-shadow .15s}',
      '.nw-f:focus{border-color:var(--brand2);box-shadow:0 0 0 3px rgba(23,70,209,.16)}textarea.nw-f{min-height:70px;resize:vertical}',
      '.nw-field.err .nw-f{border-color:var(--bad)}.nw-err{color:var(--bad);font-size:12px;min-height:0}',
      '.nw-hp{position:absolute!important;left:-9999px!important;width:1px;height:1px;opacity:0}',
      '.nw-seg{display:flex;gap:6px;flex-wrap:wrap}.nw-seg button{flex:1;min-width:0;border:1px solid var(--line);background:var(--surface);padding:9px 8px;border-radius:12px;font-size:13px;transition:all .15s}.nw-seg button.on{background:linear-gradient(135deg,#1746d1,#5a1fb3);color:#fff;border-color:transparent;box-shadow:0 6px 14px rgba(23,70,209,.25)}',
      '.nw-check{display:flex;gap:10px;align-items:flex-start;font-size:12.5px;color:var(--muted);margin:4px 0 14px;cursor:pointer}.nw-check input{margin-top:3px;width:18px;height:18px;accent-color:#1746d1;flex:none}',
      '.nw-phone{display:flex;gap:6px}.nw-phone span{display:grid;place-items:center;padding:0 12px;border:1px solid var(--line);border-radius:12px;background:var(--surface2);font-weight:600}',
      /* panels */
      '.nw-panel{position:absolute;inset:0;z-index:6;background:var(--bg);display:flex;flex-direction:column;transform:translateX(102%);transition:transform .32s cubic-bezier(.2,.85,.2,1);visibility:hidden}.nw-panel.open{transform:none;visibility:visible}',
      '.nw-phead{flex:none;display:flex;align-items:center;gap:10px;padding:10px 12px;background:var(--surface);border-bottom:1px solid var(--line)}.nw-phead b{flex:1;font-size:15px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '.nw-pb{width:34px;height:34px;border:0;border-radius:50%;background:var(--surface2);display:grid;place-items:center}.nw-pb:hover{background:var(--line)}',
      '.nw-pbody{flex:1;overflow-y:auto;padding:14px;overscroll-behavior:contain}',
      '.nw-step{animation:nw-slide .35s cubic-bezier(.2,.85,.2,1) both}',
      '.nw-prog{display:flex;gap:5px;margin-bottom:14px}.nw-prog i{flex:1;height:5px;border-radius:3px;background:var(--surface2);overflow:hidden;position:relative}.nw-prog i.on::after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,#1746d1,#e0148c);animation:nw-fill .5s both}',
      '.nw-q{font-size:18px;font-weight:700;line-height:1.25;margin:0 0 6px}.nw-hint{color:var(--muted);font-size:12.5px;margin:0 0 14px}',
      '.nw-opts{display:grid;grid-template-columns:1fr 1fr;gap:9px}.nw-opts.one{grid-template-columns:1fr}',
      '.nw-opt{text-align:left;border:1.5px solid var(--line);background:var(--surface);border-radius:14px;padding:13px 12px;font-size:13.5px;font-weight:500;transition:transform .15s,border-color .15s,box-shadow .15s,background .15s;position:relative}',
      '.nw-opt:hover{transform:translateY(-2px);border-color:var(--brand2);box-shadow:0 8px 18px rgba(23,70,209,.14)}.nw-opt.on{border-color:var(--brand2);background:linear-gradient(135deg,rgba(23,70,209,.12),rgba(224,20,140,.1))}',
      '.nw-opt.ok{border-color:var(--ok);background:rgba(15,157,99,.14);animation:nw-pop .35s}.nw-opt.no{border-color:var(--bad);background:rgba(217,45,32,.12);animation:nw-shake .35s}',
      '.nw-slider{margin:18px 4px 8px}.nw-big{font-size:46px;font-weight:800;text-align:center;background:linear-gradient(135deg,#1746d1,#e0148c);-webkit-background-clip:text;background-clip:text;color:transparent;line-height:1.1;font-variant-numeric:tabular-nums}',
      '.nw-slider input{width:100%;accent-color:#e0148c;height:30px}',
      '.nw-row2{display:flex;gap:8px;margin-top:16px}.nw-row2>*{flex:1}',
      /* tiles */
      '.nw-tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px}',
      '.nw-tile{--hue:#1746d1;text-align:left;border:1px solid var(--line);background:var(--surface);border-radius:16px;padding:12px;display:flex;flex-direction:column;gap:8px;transition:transform .2s cubic-bezier(.2,.9,.3,1.3),box-shadow .2s;animation:nw-in .4s both;position:relative;overflow:hidden}',
      '.nw-tile::after{content:"";position:absolute;right:-24px;top:-24px;width:70px;height:70px;border-radius:50%;background:var(--hue);opacity:.12;transition:transform .3s}.nw-tile:hover{transform:translateY(-3px) scale(1.02);box-shadow:0 12px 24px rgba(10,15,40,.14)}.nw-tile:hover::after{transform:scale(2.2)}',
      '.nw-tile .ti{width:34px;height:34px;border-radius:11px;background:var(--hue);color:#fff;display:grid;place-items:center;box-shadow:0 6px 14px rgba(0,0,0,.18)}.nw-tile b{font-size:13.5px;line-height:1.2}.nw-tile small{color:var(--muted);font-size:11.5px;line-height:1.3}',
      '.nw-sheet{position:absolute;left:0;right:0;bottom:0;z-index:4;background:var(--bg);border-radius:22px 22px 0 0;padding:14px 14px 10px;box-shadow:0 -14px 40px rgba(0,0,0,.25);transform:translateY(105%);visibility:hidden;pointer-events:none;transition:transform .32s cubic-bezier(.2,.85,.2,1),visibility 0s .32s;max-height:88%;overflow:auto}.nw-sheet.open{transform:none;visibility:visible;pointer-events:auto;transition:transform .32s cubic-bezier(.2,.85,.2,1)}',
      '.nw-scrim{position:absolute;inset:0;z-index:3;background:rgba(5,8,25,.45);opacity:0;pointer-events:none;transition:opacity .25s}.nw-scrim.open{opacity:1;pointer-events:auto}',
      '.nw-sheet h3{margin:0 0 10px;font-size:15px;display:flex;align-items:center;justify-content:space-between}',
      '.nw-pop{position:absolute;top:42px;right:10px;z-index:9;background:var(--surface);border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow);padding:6px;min-width:170px;animation:nw-pop .25s cubic-bezier(.2,.9,.3,1.3);transform-origin:100% 0}.nw-pop[hidden]{display:none}',
      '.nw-pop button{display:flex;width:100%;align-items:center;justify-content:space-between;gap:10px;border:0;background:transparent;padding:9px 12px;border-radius:10px;font-size:14px;text-align:left}.nw-pop button:hover{background:var(--surface2)}.nw-pop button.on{font-weight:700;color:var(--brand2)}',
      /* advisor result */
      '.nw-res{display:grid;grid-template-columns:auto 1fr;gap:12px;background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:14px;margin-bottom:12px;animation:nw-in .5s both;position:relative;overflow:hidden}',
      '.nw-res.best{border-color:transparent;background:linear-gradient(var(--surface),var(--surface)) padding-box,linear-gradient(135deg,#1746d1,#e0148c,#17f38c) border-box;border:2px solid transparent;box-shadow:0 12px 30px rgba(23,70,209,.18)}',
      '.nw-ring{width:62px;height:62px;position:relative;flex:none}.nw-ring svg{transform:rotate(-90deg)}.nw-ring circle{fill:none;stroke-width:6;stroke-linecap:round}.nw-ring .bg{stroke:var(--surface2)}.nw-ring .fg{stroke:url(#nwg);transition:stroke-dashoffset 1.1s cubic-bezier(.2,.8,.2,1)}.nw-ring b{position:absolute;inset:0;display:grid;place-items:center;font-size:15px}',
      '.nw-res h4{margin:0;font-size:15px}.nw-res small{color:var(--muted)}',
      '.nw-pills{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}.nw-pill{font-size:11.5px;padding:3px 9px;border-radius:999px;background:var(--surface2);color:var(--text)}.nw-pill.ok{background:rgba(15,157,99,.16);color:var(--ok)}.nw-pill.warn{background:rgba(194,112,3,.16);color:var(--warn)}.nw-pill.bad{background:rgba(217,45,32,.14);color:var(--bad)}.nw-pill.brand{background:rgba(224,20,140,.14);color:var(--brand)}',
      '.nw-note{font-size:12px;color:var(--muted);background:var(--surface2);border-radius:12px;padding:9px 11px;margin:10px 0}',
      '.nw-alert{display:flex;gap:9px;padding:10px 12px;border-radius:14px;font-size:12.5px;background:rgba(194,112,3,.12);color:var(--text);border:1px solid rgba(194,112,3,.3);margin-bottom:12px}',
      /* tables, timeline, checklist */
      '.nw-tbl{width:100%;border-collapse:separate;border-spacing:0;font-size:12.5px;background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}.nw-tbl th,.nw-tbl td{padding:9px 10px;text-align:left;vertical-align:top;border-top:1px solid var(--line)}.nw-tbl thead th{border-top:0;background:linear-gradient(135deg,#1746d1,#5a1fb3);color:#fff}.nw-tbl td:first-child{font-weight:600;color:var(--muted);width:24%}',
      '.nw-cl{display:flex;gap:11px;align-items:flex-start;padding:11px 12px;background:var(--surface);border:1px solid var(--line);border-radius:14px;margin-bottom:8px;cursor:pointer;transition:background .2s,border-color .2s,transform .15s;animation:nw-in .35s both}.nw-cl:hover{transform:translateX(2px)}',
      '.nw-cl .bx{width:22px;height:22px;border-radius:7px;border:2px solid var(--line);display:grid;place-items:center;flex:none;color:transparent;transition:all .2s;margin-top:1px}.nw-cl.on{background:rgba(15,157,99,.1);border-color:rgba(15,157,99,.4)}.nw-cl.on .bx{background:var(--ok);border-color:var(--ok);color:#fff}.nw-cl.on b{text-decoration:line-through;opacity:.6}',
      '.nw-cl small{display:block;color:var(--muted);margin-top:2px;font-size:12px}',
      '.nw-tl{position:relative;margin:6px 0 4px 12px;padding-left:20px;border-left:2px dashed var(--line)}.nw-tl div{position:relative;padding:4px 0 12px;font-size:13px}.nw-tl div::before{content:attr(data-n);position:absolute;left:-33px;top:2px;width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#1746d1,#e0148c);color:#fff;display:grid;place-items:center;font-size:11px;font-weight:700}',
      '.nw-meter{display:flex;align-items:center;gap:10px;margin:0 0 14px;font-size:12.5px;color:var(--muted)}.nw-meter .tr{flex:1;height:8px;border-radius:4px;background:var(--surface2);overflow:hidden}.nw-meter .tr i{display:block;height:100%;width:0;background:linear-gradient(90deg,#0f9d63,#17f38c);border-radius:4px;transition:width .5s}',
      /* careers map */
      '.nw-paths{display:flex;gap:7px;overflow-x:auto;padding-bottom:10px;scrollbar-width:none}.nw-paths::-webkit-scrollbar{display:none}.nw-paths button{flex:none;border:1.5px solid var(--line);background:var(--surface);border-radius:999px;padding:7px 13px;font-size:12.5px;font-weight:600;transition:all .2s}.nw-paths button.on{color:#fff;border-color:transparent;box-shadow:0 6px 14px rgba(0,0,0,.2)}',
      '.nw-map{position:relative;padding-left:26px}.nw-map::before{content:"";position:absolute;left:9px;top:14px;bottom:14px;width:3px;border-radius:2px;background:linear-gradient(var(--c),transparent)}',
      '.nw-node{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;margin-bottom:12px;animation:nw-slide .45s both}.nw-node::before{content:"";position:absolute;left:-23px;top:20px;width:14px;height:14px;border-radius:50%;background:var(--c);box-shadow:0 0 0 4px var(--bg),0 0 0 6px var(--c)}.nw-node::after{content:"";position:absolute;left:-10px;top:26px;width:10px;height:2px;background:var(--c)}',
      '.nw-node h5{margin:0 0 8px;font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted)}.nw-node .nw-pills{margin:0}.nw-node .nw-pill{background:color-mix(in srgb,var(--c) 14%,var(--surface));font-size:12px}',
      /* events */
      '.nw-ev{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:14px;margin-bottom:12px;animation:nw-in .4s both;position:relative;overflow:hidden}.nw-ev::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c,#1746d1)}',
      '.nw-ev h4{margin:0 0 4px;font-size:15px}.nw-ev p{margin:4px 0 8px;color:var(--muted);font-size:13px}',
      '.nw-cd{display:flex;gap:8px;margin:8px 0}.nw-cd div{background:linear-gradient(160deg,#1746d1,#5a1fb3);color:#fff;border-radius:12px;padding:7px 4px;min-width:52px;text-align:center}.nw-cd b{display:block;font-size:20px;line-height:1;font-variant-numeric:tabular-nums}.nw-cd small{font-size:10px;opacity:.85;text-transform:uppercase;letter-spacing:.5px}',
      /* wellness */
      '.nw-tabs{display:flex;gap:4px;background:var(--surface2);padding:4px;border-radius:14px;margin-bottom:14px}.nw-tabs button{flex:1;border:0;background:transparent;border-radius:10px;padding:8px 4px;font-size:12.5px;font-weight:600;color:var(--muted)}.nw-tabs button.on{background:var(--surface);color:var(--text);box-shadow:0 2px 8px rgba(0,0,0,.1)}',
      '.nw-moods{display:flex;justify-content:space-between;gap:6px;margin:14px 0}.nw-mood{flex:1;border:0;background:transparent;display:flex;flex-direction:column;align-items:center;gap:7px;font-size:11px;color:var(--muted);transition:transform .25s cubic-bezier(.2,.9,.3,1.5)}.nw-mood i{width:100%;aspect-ratio:1;max-width:52px;border-radius:50%;background:var(--g);box-shadow:inset 0 -6px 12px rgba(0,0,0,.14),0 6px 14px var(--s);transition:transform .25s}.nw-mood:hover{transform:translateY(-4px)}.nw-mood.on{color:var(--text);font-weight:700}.nw-mood.on i{transform:scale(1.18);outline:3px solid var(--surface);box-shadow:0 0 0 5px var(--brand2),0 10px 20px var(--s)}',
      '.nw-chipsel{display:flex;flex-wrap:wrap;gap:8px}.nw-chipsel button{border:1.5px solid var(--line);background:var(--surface);border-radius:999px;padding:8px 13px;font-size:13px;transition:all .15s}.nw-chipsel button.on{background:linear-gradient(135deg,#1746d1,#5a1fb3);color:#fff;border-color:transparent}',
      '.nw-breath{display:grid;place-items:center;padding:18px 0 8px;text-align:center}.nw-orb{width:150px;height:150px;border-radius:50%;display:grid;place-items:center;background:radial-gradient(circle at 35% 30%,#9ee7ff,#4f8cff 55%,#5a1fb3);box-shadow:0 0 0 0 rgba(79,140,255,.5),inset 0 -14px 30px rgba(0,0,0,.2);transform:scale(.62);transition:transform 4s ease-in-out,box-shadow 4s ease-in-out;color:#fff;font-weight:700;font-size:15px}.nw-orb.in{transform:scale(1);box-shadow:0 0 50px 14px rgba(79,140,255,.45),inset 0 -14px 30px rgba(0,0,0,.2)}.nw-orb.hold{transform:scale(1);transition-duration:2s}.nw-orb.out{transform:scale(.62);transition-duration:6s;box-shadow:0 0 0 0 rgba(79,140,255,0)}',
      '.nw-helps{display:flex;flex-direction:column;gap:8px}.nw-help{display:flex;align-items:center;gap:12px;padding:11px 12px;border-radius:14px;background:var(--surface);border:1px solid rgba(217,45,32,.35);text-decoration:none;color:var(--text)}.nw-help .ti{width:36px;height:36px;border-radius:50%;background:#d92d20;color:#fff;display:grid;place-items:center;flex:none}.nw-help b{display:block}.nw-help small{color:var(--muted)}.nw-help em{margin-left:auto;font-style:normal;font-weight:800;font-size:16px;color:#d92d20}',
      '.nw-strip{flex:none;display:flex;align-items:center;gap:8px;padding:8px 12px;font-size:12px;background:rgba(217,45,32,.1);border-top:1px solid rgba(217,45,32,.25)}.nw-strip a{color:var(--bad);font-weight:700;text-decoration:none;margin-left:auto}',
      /* student / quiz / flashcards */
      '.nw-hero{display:flex;align-items:center;gap:14px;border-radius:20px;padding:16px;color:#fff;background:linear-gradient(135deg,#1746d1,#7c3aed 60%,#e0148c);box-shadow:0 14px 30px rgba(79,70,229,.35);margin-bottom:14px;position:relative;overflow:hidden}.nw-hero::after{content:"";position:absolute;right:-30px;top:-30px;width:120px;height:120px;border-radius:50%;background:rgba(255,255,255,.14)}.nw-hero .n{font-size:44px;font-weight:800;line-height:1;font-variant-numeric:tabular-nums}.nw-hero small{opacity:.9}',
      '.nw-exam{display:flex;gap:12px;align-items:center;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:10px 12px;margin-bottom:8px;animation:nw-in .35s both}.nw-exam.next{border-color:var(--brand2);box-shadow:0 8px 20px rgba(23,70,209,.18)}.nw-exam.past{opacity:.5}.nw-exam.hol{background:var(--surface2);border-style:dashed}',
      '.nw-date{width:46px;flex:none;text-align:center;border-radius:11px;background:var(--surface2);padding:5px 0}.nw-date b{display:block;font-size:18px;line-height:1.1}.nw-date small{font-size:10px;text-transform:uppercase;color:var(--muted);letter-spacing:.4px}',
      '.nw-qhead{display:flex;justify-content:space-between;align-items:center;font-size:12.5px;color:var(--muted);margin-bottom:10px}',
      '.nw-score{text-align:center;padding:10px 0}.nw-score .nw-ring{margin:0 auto 10px;width:120px;height:120px}.nw-score .nw-ring b{font-size:30px}',
      '.nw-fc{perspective:900px;height:200px;margin:6px 0 14px;cursor:pointer}.nw-fc>div{position:relative;width:100%;height:100%;transition:transform .6s cubic-bezier(.3,.8,.3,1);transform-style:preserve-3d}.nw-fc.flip>div{transform:rotateY(180deg)}',
      '.nw-fc .f,.nw-fc .b{position:absolute;inset:0;backface-visibility:hidden;-webkit-backface-visibility:hidden;border-radius:20px;display:grid;place-items:center;text-align:center;padding:18px;font-size:17px;font-weight:600;box-shadow:0 14px 30px rgba(10,15,40,.2)}',
      '.nw-fc .f{background:linear-gradient(135deg,#1746d1,#5a1fb3);color:#fff}.nw-fc .b{background:linear-gradient(135deg,#0f9d63,#0b7a4d);color:#fff;transform:rotateY(180deg)}.nw-fc small{position:absolute;bottom:10px;left:0;right:0;font-size:11px;opacity:.75;font-weight:400}',
      '.nw-skel{border-radius:14px;height:64px;margin-bottom:10px;background:linear-gradient(90deg,var(--surface2) 25%,var(--surface) 50%,var(--surface2) 75%);background-size:200% 100%;animation:nw-shimmer 1.3s infinite}',
      '.nw-conf{position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:20}.nw-conf i{position:absolute;top:-12px;width:8px;height:14px;border-radius:2px;animation:nw-fall var(--d) ease-in forwards}',
      /* check mark + success */
      '.nw-done{text-align:center;padding:18px 6px}.nw-done>svg{width:76px;height:76px}.nw-done>svg circle{fill:none;stroke:var(--ok);stroke-width:3;stroke-dasharray:166;stroke-dashoffset:166;animation:nw-draw .6s ease-out forwards}.nw-done>svg path{fill:none;stroke:var(--ok);stroke-width:4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:48;stroke-dashoffset:48;animation:nw-draw .4s .5s ease-out forwards}',
      '.nw-ref{display:inline-block;font-weight:800;letter-spacing:1px;background:var(--surface2);padding:6px 14px;border-radius:10px;margin:6px 0}',
      '.nw-days{display:flex;gap:8px;overflow-x:auto;padding:2px 2px 10px;scrollbar-width:none}.nw-days::-webkit-scrollbar{display:none}.nw-day{flex:none;width:62px;border:1.5px solid var(--line);background:var(--surface);border-radius:14px;padding:8px 0;text-align:center;transition:all .2s}.nw-day b{display:block;font-size:20px;line-height:1.1}.nw-day small{font-size:11px;color:var(--muted)}.nw-day.on{background:linear-gradient(160deg,#1746d1,#5a1fb3);color:#fff;border-color:transparent;transform:translateY(-3px);box-shadow:0 10px 20px rgba(23,70,209,.3)}.nw-day.on small{color:rgba(255,255,255,.85)}',
      '.nw-slots{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}.nw-slot{border:1.5px solid var(--line);background:var(--surface);border-radius:12px;padding:9px 4px;text-align:center;font-weight:600;transition:all .15s}.nw-slot small{display:block;font-weight:400;color:var(--muted);font-size:10.5px}.nw-slot.on{background:linear-gradient(135deg,#0e9f6e,#0b7a4d);color:#fff;border-color:transparent}.nw-slot.on small{color:rgba(255,255,255,.85)}',
      /* staff */
      '.nw-stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:12px}.nw-stat{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:10px;text-align:center}.nw-stat b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.nw-stat small{color:var(--muted);font-size:11px}',
      '.nw-chart{display:flex;align-items:flex-end;gap:3px;height:84px;background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:10px}.nw-chart i{flex:1;background:linear-gradient(180deg,#e0148c,#1746d1);border-radius:3px 3px 0 0;min-height:2px;transition:height .8s cubic-bezier(.2,.8,.2,1);height:0}',
      '.nw-donut{width:86px;height:86px;border-radius:50%;flex:none;mask:radial-gradient(circle,transparent 46%,#000 47%);-webkit-mask:radial-gradient(circle,transparent 46%,#000 47%)}',
      '.nw-sec{margin:16px 0 8px;font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.7px;color:var(--muted)}',
      '.nw-lead{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:11px 12px;margin-bottom:9px}.nw-lead header{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:4px}.nw-lead select{max-width:130px}',
      '.nw-code-box{font-family:ui-monospace,Consolas,monospace;font-size:22px;font-weight:800;letter-spacing:2px;text-align:center;background:var(--surface2);border:2px dashed var(--brand2);border-radius:14px;padding:14px;margin:8px 0;user-select:all}',
      '.nw-toast{position:absolute;left:50%;bottom:86px;transform:translateX(-50%) translateY(20px);background:#0f1530;color:#fff;padding:9px 16px;border-radius:999px;font-size:13px;opacity:0;transition:all .3s;z-index:30;pointer-events:none;white-space:nowrap;max-width:90%;overflow:hidden;text-overflow:ellipsis}.nw-toast.on{opacity:1;transform:translateX(-50%)}',
      /* keyframes */
      '@keyframes nw-spin{to{transform:rotate(360deg)}}@keyframes nw-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.25)}}',
      '@keyframes nw-pulse-red{0%{box-shadow:0 0 0 0 rgba(217,45,32,.6)}100%{box-shadow:0 0 0 14px rgba(217,45,32,0)}}',
      '@keyframes nw-ping{0%{box-shadow:0 0 0 0 rgba(51,245,160,.7)}80%,100%{box-shadow:0 0 0 8px rgba(51,245,160,0)}}',
      '@keyframes nw-drift{from{transform:translate(0,0) scale(1)}to{transform:translate(60px,40px) scale(1.25)}}',
      '@keyframes nw-in{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}',
      '@keyframes nw-slide{from{opacity:0;transform:translateX(24px)}to{opacity:1;transform:none}}',
      '@keyframes nw-pop{from{opacity:0;transform:scale(.8)}to{opacity:1;transform:none}}',
      '@keyframes nw-blink{50%{opacity:0}}@keyframes nw-bounce{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-6px)}}',
      '@keyframes nw-fill{from{transform:translateX(-100%)}to{transform:none}}',
      '@keyframes nw-shake{25%{transform:translateX(-5px)}75%{transform:translateX(5px)}}',
      '@keyframes nw-shimmer{to{background-position:-200% 0}}',
      '@keyframes nw-draw{to{stroke-dashoffset:0}}',
      '@keyframes nw-fall{to{transform:translateY(720px) rotate(720deg);opacity:.9}}',
      '@media (prefers-reduced-motion:reduce){.nw *,.nw *::before,.nw *::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}}'
    ].join('\n');

    /* ============================================================================================
     * 6. DOM skeleton
     * ========================================================================================== */
    var host = h('div', { id: 'noah-widget-host' });
    host.style.cssText = 'all:initial';
    var shadow = host.attachShadow({ mode: 'open' });
    document.body.appendChild(host);
    shadow.appendChild(h('style', {}, CSS));

    var binds = [];                                   // {el, key, attr} refreshed when the language changes
    function bindText(el, key, attr) { binds.push({ el: el, key: key, attr: attr }); applyBind(binds[binds.length - 1]); return el; }
    function applyBind(b) { var v = T(b.key); if (b.attr) b.el.setAttribute(b.attr, v); else b.el.textContent = v; }

    var logoImg = function (cls) { return h('img', { src: BASE + '/static/logo.png', alt: '', class: cls || '', onerror: function () { this.style.visibility = 'hidden'; } }); };
    var $ = {};
    $.fab = h('button', { class: 'nw-fab', 'aria-label': 'Chat with Noah', 'aria-expanded': 'false', onclick: function () { toggle(); } }, icon('chat'), icon('x'), h('span', { class: 'dot' }));
    $.fab.children[0].classList.add('c'); $.fab.children[1].classList.add('x');
    $.teaser = h('div', { class: 'nw-teaser', hidden: true, role: 'status', onclick: function () { open(); } }, h('span', { class: 'tt' }, 'Questions about admissions? Ask Noah.'),
      h('button', { 'aria-label': 'Dismiss', onclick: function (e) { e.stopPropagation(); $.teaser.hidden = true; SS.set('noah_teaser', '1'); } }, icon('x', 14)));
    $.lang = h('button', { class: 'nw-hb lang', 'aria-label': 'Language', onclick: function (e) { e.stopPropagation(); $.morepop.hidden = true; $.pop.hidden = !$.pop.hidden; } }, icon('globe', 15), h('span', {}, 'EN'));
    $.more = h('button', { class: 'nw-hb', 'aria-label': 'Menu', onclick: function (e) { e.stopPropagation(); $.pop.hidden = true; $.morepop.hidden = !$.morepop.hidden; } }, icon('dots', 16));
    $.close = h('button', { class: 'nw-hb', 'aria-label': 'Close', onclick: function () { close(); } }, icon('x', 17));
    $.head = h('div', { class: 'nw-head' }, h('div', { class: 'nw-logo' }, logoImg()), h('div', { class: 'nw-title' }, h('b', {}, 'Noah'), h('span', {}, 'Institutional Language Model')), h('div', { class: 'nw-hbs' }, $.lang, $.more, $.close));
    $.pop = h('div', { class: 'nw-pop', hidden: true, role: 'menu' });
    $.morepop = h('div', { class: 'nw-pop', hidden: true, role: 'menu' });
    $.banner = h('div', { class: 'nw-banner', hidden: true }, icon('book', 16), h('span', {}), h('button', { onclick: function () { setMode('chat'); } }, 'Exit'));
    $.msgs = h('div', { class: 'nw-msgs', role: 'log', 'aria-live': 'polite' });
    $.chips = h('div', { class: 'nw-chips' });
    $.panel = h('div', { class: 'nw-panel', 'aria-hidden': 'true' });
    $.scrim = h('div', { class: 'nw-scrim', onclick: function () { hideSheet(); } });
    $.sheet = h('div', { class: 'nw-sheet', hidden: true });
    $.toast = h('div', { class: 'nw-toast', role: 'status' });
    $.body = h('div', { class: 'nw-body' }, $.banner, $.msgs, $.chips, $.scrim, $.sheet, $.panel, $.toast);
    $.input = h('textarea', { class: 'nw-input', rows: '1', maxlength: '1200', 'aria-label': 'Message', onkeydown: function (e) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); send($.input.value); } }, oninput: autoGrow });
    bindText($.input, 'placeholder', 'placeholder');
    $.tools = h('button', { class: 'nw-ib2', 'aria-label': 'Tools', onclick: function () { showSheet(); } }, icon('grid'));
    bindText($.tools, 'tools', 'aria-label');
    $.mic = h('button', { class: 'nw-ib2', 'aria-label': 'Speak', onclick: toggleMic }, icon('mic'));
    bindText($.mic, 'mic', 'aria-label');
    $.sendb = h('button', { class: 'nw-ib2 nw-send', 'aria-label': 'Send', onclick: function () { send($.input.value); } }, icon('send', 17));
    bindText($.sendb, 'send', 'aria-label');
    $.comp = h('div', { class: 'nw-comp' }, $.tools, $.input, $.mic, $.sendb);
    $.privacy = h('span', {}); bindText($.privacy, 'privacy');
    $.foot = h('div', { class: 'nw-foot' }, $.privacy, h('br'), '© 2026 ', h('a', { href: 'https://www.jonahbrowser.com', target: '_blank', rel: 'noopener noreferrer' }, 'CogniAI Studios'), '. All rights reserved.', h('span', { class: 'nw-ver', title: 'Noah widget ' + VERSION }, ' · build ' + VERSION.split('.').pop()));
    $.win = h('div', { class: 'nw-win', role: 'dialog', 'aria-label': 'Noah chat assistant' }, $.head, $.pop, $.morepop, $.body, $.comp, $.foot);
    var root = h('div', { class: 'nw', 'data-theme': 'light' }, $.teaser, $.win, $.fab);
    shadow.appendChild(root);
    shadow.addEventListener('click', function () { $.pop.hidden = true; $.morepop.hidden = true; });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && S.open) { if ($.sheet.classList.contains('open')) hideSheet(); else if ($.panel.classList.contains('open')) closePanel(); else close(); } });

    // gradient used by the progress rings
    var defs = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    defs.setAttribute('width', '0'); defs.setAttribute('height', '0'); defs.style.position = 'absolute';
    defs.innerHTML = '<defs><linearGradient id="nwg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1746d1"/><stop offset="1" stop-color="#e0148c"/></linearGradient></defs>';
    root.appendChild(defs);

    /* ============================================================================================
     * 7. Theme, language, window
     * ========================================================================================== */
    function systemDark() { return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches; }
    function setTheme(t) {
      S.theme = t; LS.set('noah_theme', t);
      var dark = t === 'dark' || (t === 'auto' && systemDark());
      root.setAttribute('data-theme', dark ? 'dark' : 'light');
      clear($.morepop);
      put($.morepop,
        h('button', { role: 'menuitem', onclick: function () { $.morepop.hidden = true; setTheme(dark ? 'light' : 'dark'); } }, h('span', {}, dark ? 'Light mode' : 'Dark mode'), icon(dark ? 'sun' : 'moon', 15)),
        h('button', { role: 'menuitem', onclick: function () { $.morepop.hidden = true; newChat(); } }, h('span', {}, T('newChat')), icon('refresh', 15)));
    }
    function setLang(code, quiet) {
      if (!LANGS.some(function (l) { return l.code === code; })) return;
      S.lang = code; LS.set('noah_lang', code);
      binds.forEach(applyBind);
      $.lang.lastChild.textContent = code.toUpperCase();
      document.documentElement.setAttribute('data-noah-lang', code);
      renderLangMenu(); setTheme(S.theme);
      if (S.recognizing && recognizer) recognizer.stop();
      if (!quiet) toast(LANGS.filter(function (l) { return l.code === code; })[0].native);
    }
    function renderLangMenu() {
      clear($.pop);
      LANGS.forEach(function (l) {
        $.pop.appendChild(h('button', { class: S.lang === l.code ? 'on' : '', role: 'menuitem', onclick: function () { setLang(l.code); $.pop.hidden = true; } }, h('span', {}, l.native), S.lang === l.code ? icon('check', 15) : null));
      });
    }
    function open() {
      S.open = true; $.win.classList.add('open'); $.fab.classList.add('open'); $.fab.setAttribute('aria-expanded', 'true');
      $.teaser.hidden = true; var dot = $.fab.querySelector('.dot'); if (dot) dot.style.display = 'none';
      SS.set('noah_open', '1'); ensureWelcome(); setTimeout(function () { $.input.focus(); if (S.fresh) $.msgs.scrollTop = 0; else scrollDown(); }, 330);
    }
    function close() { S.open = false; $.win.classList.remove('open'); $.fab.classList.remove('open'); $.fab.setAttribute('aria-expanded', 'false'); SS.del('noah_open'); stopSpeaking(); }
    function toggle() { if (S.open) close(); else open(); }
    function toast(msg) { $.toast.textContent = msg; $.toast.classList.add('on'); clearTimeout(toast.t); toast.t = setTimeout(function () { $.toast.classList.remove('on'); }, 2200); }
    function autoGrow() { $.input.style.height = 'auto'; $.input.style.height = Math.min($.input.scrollHeight, 110) + 'px'; $.input.style.overflowY = $.input.scrollHeight > 110 ? 'auto' : 'hidden'; }
    function scrollDown() { $.msgs.scrollTop = $.msgs.scrollHeight; }
    function copyText(t) { if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(t); var ta = h('textarea', { style: 'position:fixed;opacity:0' }); ta.value = t; shadow.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) { /* ignore */ } ta.remove(); return Promise.resolve(); }

    /* ============================================================================================
     * 8. Server calls
     * ========================================================================================== */
    function api(path, o) {
      o = o || {};
      var headers = {};
      if (o.body !== undefined) headers['Content-Type'] = 'application/json';
      if (o.student && S.student) headers['X-Student-Token'] = S.student.token;
      if (o.staff && S.staff) headers['Authorization'] = 'Bearer ' + S.staff.token;
      return fetch(BASE + path, { method: o.method || (o.body !== undefined ? 'POST' : 'GET'), headers: headers, body: o.body !== undefined ? JSON.stringify(o.body) : undefined })
        .then(function (r) {
          return r.text().then(function (t) {
            var data = {}; try { data = t ? JSON.parse(t) : {}; } catch (e) { data = { raw: t }; }
            if (r.status === 401 && o.student && S.student) { S.student = null; SS.del('noah_student'); }
            if (r.status === 401 && o.staff && S.staff) { S.staff = null; SS.del('noah_staff'); }
            return { ok: r.ok, status: r.status, data: data };
          });
        })
        .catch(function () { return { ok: false, status: 0, data: { error: T('offline') } }; });
    }

    /* ============================================================================================
     * 9. Chat core
     * ========================================================================================== */
    var HIST = [];
    try { HIST = JSON.parse(SS.get('noah_chat_v1', '[]')) || []; } catch (e) { HIST = []; }
    function saveHist() { SS.set('noah_chat_v1', JSON.stringify(HIST.slice(-40))); }
    var welcomed = false;

    function toolById(id) { return TOOLS.filter(function (t) { return t.id === id; })[0]; }
    function toolTitle(id) { var t = toolById(id); return t ? T(t.key) : id === 'compare' ? T('compare') : id === 'staff' ? 'Staff panel' : id; }

    function addUser(text) {
      var row = h('div', { class: 'nw-row user' }, h('div', { class: 'nw-bub', html: md(text) }));
      $.msgs.appendChild(row); scrollDown(); return row;
    }

    function addBot(text, o) {
      o = o || {};
      var bub = h('div', { class: 'nw-bub' });
      var extra = h('div', { class: 'nw-col-extra', style: 'display:flex;flex-direction:column;gap:8px' });
      var meta = h('div', { class: 'nw-meta' });
      var col = h('div', { class: 'nw-col' }, bub, extra, meta);
      var row = h('div', { class: 'nw-row bot' }, h('div', { class: 'nw-av', 'aria-hidden': 'true' }, 'N'), col);
      var bot = { row: row, bub: bub, extra: extra, meta: meta, text: text || '', replyId: '' };
      bot.set = function (t) { bot.text = t; bub.innerHTML = md(t); scrollDownIfNear(); };
      if (o.typing) bub.appendChild(h('span', { class: 'nw-typing', 'aria-label': 'Noah is typing' }, h('i'), h('i'), h('i')));
      else bot.set(text || '');
      $.msgs.appendChild(row); scrollDown();
      return bot;
    }
    function scrollDownIfNear() { var m = $.msgs; if (m.scrollHeight - m.scrollTop - m.clientHeight < 140) scrollDown(); }

    function setChips(chips) {
      clear($.chips);
      (chips || []).forEach(function (c, i) {
        var b = h('button', { class: 'nw-chip', style: 'animation-delay:' + (i * 50) + 'ms', onclick: function () { if (c.open) openPanel(c.open, c.args); else send(c.send || c.label); } }, c.label);
        $.chips.appendChild(b);
      });
    }

    function numberFromFee(v) { var m = /^Rs\s*([\d,]+)$/.exec(String(v)); return m ? parseInt(m[1].replace(/,/g, ''), 10) : null; }

    function renderCard(c) {
      if (c.type === 'fees') {
        var max = Math.max.apply(null, c.rows.map(function (r) { return numberFromFee(r.value) || 0; }).concat([1]));
        var card = h('div', { class: 'nw-card' }, h('h4', {}, icon('file', 15), c.title));
        c.rows.forEach(function (r) {
          var n = numberFromFee(r.value);
          var bar = h('div', { class: 'nw-bar' }, h('i'));
          card.appendChild(h('div', { class: 'nw-fee' }, h('span', { class: 'nw-code' }, r.code), h('span', {}, r.name), h('b', {}, String(r.value).replace(/^Rs\s*/, '\u20B9')), n ? bar : null));
          if (n) setTimeout(function () { bar.firstChild.style.width = Math.max(8, Math.round(n / max * 100)) + '%'; }, 80);
        });
        if (c.note) card.appendChild(h('div', { class: 'nw-note' }, c.note));
        return card;
      }
      if (c.type === 'contact') {
        var cc = h('div', { class: 'nw-card' }, h('h4', {}, icon('phone', 15), c.title));
        c.rows.forEach(function (r) { cc.appendChild(h('div', { class: 'nw-kv' }, h('span', {}, r.label), h('b', {}, r.href ? h('a', { href: r.href, target: r.href.indexOf('http') === 0 ? '_blank' : null, rel: 'noopener noreferrer' }, r.value) : r.value))); });
        (c.buttons || []).forEach(function (b) { cc.appendChild(h('a', { class: 'nw-btn sm block', style: 'margin-top:10px', href: safeUrl(b.url), target: '_blank', rel: 'noopener noreferrer' }, icon('pin', 15), b.label)); });
        return cc;
      }
      if (c.type === 'helplines') {
        var hc = h('div', { class: 'nw-card warn' }, h('h4', {}, icon('heart', 15), c.title), h('div', { class: 'nw-helps' }, c.rows.map(function (r) {
          return h('a', { class: 'nw-help', href: 'tel:' + String(r.phone).replace(/[^\d+]/g, '') }, h('span', { class: 'ti' }, icon('phone', 17)), h('span', {}, h('b', {}, r.name), h('small', {}, r.note || '')), h('em', {}, r.phone));
        })));
        if (c.note) hc.appendChild(h('div', { class: 'nw-note' }, c.note));
        return hc;
      }
      return null;
    }

    function actionButton(a) {
      var t = toolById(a.open);
      return h('button', { class: 'nw-btn sm', onclick: function () { openPanel(a.open, a.args); } }, icon(t ? t.icon : 'layers', 15), toolTitle(a.open));
    }

    function applyReply(bot, reply, auto) {
      bot.bub.classList.remove('live');
      bot.set(reply.answer || '');
      bot.replyId = reply.reply_id || '';
      clear(bot.extra);
      (reply.cards || []).forEach(function (c) { var el = renderCard(c); if (el) bot.extra.appendChild(el); });
      var acts = h('div', { class: 'nw-acts' });
      (reply.links || []).forEach(function (l) { acts.appendChild(h('a', { class: 'nw-btn ghost sm', href: safeUrl(l.url), target: '_blank', rel: 'noopener noreferrer' }, icon('link', 14), l.label)); });
      var toolIntent = /^tool:/.test(reply.intent || '');
      (reply.actions || []).forEach(function (a) { if (!(toolIntent && auto !== false)) acts.appendChild(actionButton(a)); });
      if (acts.children.length) bot.extra.appendChild(acts);
      buildMeta(bot, reply);
      setChips(reply.chips || []);
      if (reply.url) { try { window.open(reply.url, '_blank', 'noopener,noreferrer'); } catch (e) { /* popup blocked: link is in the text */ } }
      if (reply.lang && reply.lang !== S.lang) setLang(reply.lang, true);
      if (auto !== false && toolIntent && reply.actions && reply.actions[0]) setTimeout(function () { openPanel(reply.actions[0].open, reply.actions[0].args); }, 450);
      if (S.speakNext) { S.speakNext = false; speak(reply.answer); }
      scrollDownIfNear();
    }

    function buildMeta(bot, reply) {
      clear(bot.meta);
      if (reply.private) return;
      var vote = function (v, btn) {
        if (!bot.replyId) return;
        api('/api/feedback', { body: { reply_id: bot.replyId, session_id: S.sid, vote: v } });
        Array.prototype.forEach.call(bot.meta.querySelectorAll('.v'), function (x) { x.classList.remove('on'); });
        btn.classList.add('on'); bot.meta.classList.add('keep'); toast(T('thanks'));
      };
      var up = h('button', { class: 'nw-mb v', 'aria-label': 'Helpful', title: T('helpful'), onclick: function () { vote('up', up); } }, icon('up', 14));
      var dn = h('button', { class: 'nw-mb v', 'aria-label': 'Not helpful', title: T('notHelpful'), onclick: function () { vote('down', dn); } }, icon('down', 14));
      var cp = h('button', { class: 'nw-mb', 'aria-label': 'Copy', title: T('copy'), onclick: function () { copyText(bot.text).then(function () { toast('Copied'); }); } }, icon('copy', 14));
      var sp = h('button', { class: 'nw-mb', 'aria-label': 'Read aloud', title: T('speak'), onclick: function () { speak(bot.text); } }, icon('speaker', 14));
      put(bot.meta, up, dn, cp);
      if (window.speechSynthesis) bot.meta.appendChild(sp);
    }

    /* ---- sending ------------------------------------------------------------------------------ */
    function setBusy(b) { S.busy = b; $.sendb.disabled = b; }

    function send(raw) {
      var text = String(raw || '').trim();
      if (!text || S.busy) return;
      hideSheet(); $.pop.hidden = true;
      ensureWelcome(); S.fresh = false;
      addUser(text); HIST.push({ r: 'u', t: text }); saveHist();
      $.input.value = ''; autoGrow(); setChips([]);
      setBusy(true);
      var bot = addBot('', { typing: true });
      var payload = { message: text, session_id: S.sid, url: location.href, lang: S.lang, mode: S.mode, user_agent: navigator.userAgent || '', timestamp: new Date().toISOString() };
      streamReply(payload, bot).catch(function (err) {
        if (bot.text && err && err.partial) return { answer: bot.text, partial: true };
        return plainReply(payload);
      }).then(function (reply) {
        applyReply(bot, reply);
        HIST.push({ r: 'b', t: reply.answer || '' }); saveHist();
      }).catch(function () {
        applyReply(bot, { answer: T('offline'), cards: [], chips: [] });
      }).then(function () { setBusy(false); });
    }

    function headers() { var hd = { 'Content-Type': 'application/json' }; if (S.student) hd['X-Student-Token'] = S.student.token; return hd; }

    function plainReply(payload) {
      return fetch(BASE + '/predict', { method: 'POST', headers: headers(), body: JSON.stringify(payload) })
        .then(function (r) { return r.json().then(function (j) { if (!r.ok && !j.answer) throw new Error('http ' + r.status); return j; }); });
    }

    function streamReply(payload, bot) {
      if (!window.ReadableStream || !window.TextDecoder) return Promise.reject(new Error('no streaming'));
      var ctl = window.AbortController ? new AbortController() : null;
      var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 60000);
      return fetch(BASE + '/predict/stream', { method: 'POST', headers: headers(), body: JSON.stringify(payload), signal: ctl ? ctl.signal : undefined }).then(function (res) {
        var type = res.headers.get('content-type') || '';
        if (type.indexOf('text/event-stream') === -1) {
          return res.json().then(function (j) { clearTimeout(timer); if (!j.answer) throw new Error('http ' + res.status); return j; });
        }
        var reader = res.body.getReader(), dec = new TextDecoder(), buf = '', shown = '', started = false, final = null;
        function handle(ev) {
          if (ev.type === 'delta') {
            if (!started) { started = true; clear(bot.bub); bot.bub.classList.add('live'); }
            shown += ev.text; bot.set(shown);
          } else if (ev.type === 'reset') { shown = ''; bot.set(''); }
          else if (ev.type === 'final') final = ev.reply;
        }
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) {
              clearTimeout(timer);
              if (final) return final;
              var e = new Error('stream ended'); e.partial = started; throw e;
            }
            buf += dec.decode(r.value, { stream: true });
            var i;
            while ((i = buf.indexOf('\n\n')) >= 0) {
              var chunk = buf.slice(0, i); buf = buf.slice(i + 2);
              var line = chunk.split('\n').filter(function (l) { return l.indexOf('data:') === 0; })[0];
              if (line) { try { handle(JSON.parse(line.slice(5))); } catch (e) { /* ignore a malformed frame */ } }
            }
            return pump();
          });
        }
        return pump();
      });
    }

    /* ---- chat lifecycle ------------------------------------------------------------------------ */
    function welcomeTiles() {
      var feat = (S.ctx && S.ctx.features) || {};
      var grid = h('div', { class: 'nw-tiles' });
      TOOLS.forEach(function (t, i) {
        if ((t.id === 'wellness' && feat.wellness === false) || (t.id === 'student' && feat.student === false)) return;
        grid.appendChild(h('button', { class: 'nw-tile', style: '--hue:' + t.hue + ';animation-delay:' + (120 + i * 55) + 'ms', onclick: function () { openPanel(t.id); } },
          h('span', { class: 'ti' }, icon(t.icon, 17)), h('b', {}, T(t.key)), h('small', {}, t.blurb)));
      });
      return grid;
    }

    function ensureWelcome() {
      if (welcomed) return; welcomed = true;
      if (HIST.length) {
        HIST.forEach(function (m) { if (m.r === 'u') addUser(m.t); else addBot(m.t); });
        setChips(S.ctx ? S.ctx.chips : []);
        return;
      }
      var greet = (S.ctx && S.ctx.greeting) || 'Hi, I\u2019m Noah. Ask me anything about Christ Junior College.';
      var bot = addBot(greet);
      bot.extra.appendChild(h('div', { class: 'nw-lab', style: 'margin-top:2px' }, T('welcome')));
      bot.extra.appendChild(welcomeTiles());
      setChips(S.ctx ? S.ctx.chips : []);
      S.fresh = true; $.msgs.scrollTop = 0;
    }

    function newChat() {
      stopSpeaking(); clear($.msgs); HIST = []; saveHist(); welcomed = false;
      S.sid = uid(); LS.set('veronica_session_id_v1', S.sid); setMode('chat', true); ensureWelcome();
    }

    function setMode(m, quiet) {
      S.mode = m;
      $.banner.hidden = m !== 'study';
      if (m === 'study') { $.banner.children[1].textContent = T('studyMode'); $.banner.children[2].textContent = T('exit'); $.input.setAttribute('placeholder', 'Ask a study question...'); }
      else $.input.setAttribute('placeholder', T('placeholder'));
      if (!quiet && m === 'study') { addBot('Study helper is on. Ask me to explain a topic, work through an idea step by step, or check your understanding. I\u2019m a study aid, so confirm syllabus questions with your teacher.'); setChips([]); }
      if (!quiet && m === 'chat') setChips(S.ctx ? S.ctx.chips : []);
    }

    var sheetTimer = null;
    function showSheet() {
      clearTimeout(sheetTimer);
      clear($.sheet);
      put($.sheet, h('h3', {}, T('tools'), h('button', { class: 'nw-pb', 'aria-label': 'Close', onclick: hideSheet }, icon('x', 16))), welcomeTiles());
      $.sheet.hidden = false;
      void $.sheet.offsetHeight;                     // force layout so the slide-up transition runs (no timers or frames needed)
      $.scrim.classList.add('open'); $.sheet.classList.add('open');
    }
    function hideSheet() {
      $.scrim.classList.remove('open'); $.sheet.classList.remove('open');
      clearTimeout(sheetTimer);
      sheetTimer = setTimeout(function () { if (!$.sheet.classList.contains('open')) $.sheet.hidden = true; }, 360);
    }

    /* ---- voice ----------------------------------------------------------------------------------- */
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition, recognizer = null;
    function speechLang() { return LANGS.filter(function (l) { return l.code === S.lang; })[0].speech; }
    if (!SR) $.mic.style.display = 'none';
    function toggleMic() {
      if (!SR) return;
      if (S.recognizing && recognizer) { recognizer.stop(); return; }
      recognizer = new SR(); recognizer.lang = speechLang(); recognizer.interimResults = true; recognizer.continuous = false;
      recognizer.onstart = function () { S.recognizing = true; $.mic.classList.add('on'); $.input.setAttribute('placeholder', T('listening')); };
      recognizer.onresult = function (e) {
        var t = ''; for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
        $.input.value = t; autoGrow();
        if (e.results[e.results.length - 1].isFinal && t.trim()) { S.speakNext = true; send(t); }
      };
      recognizer.onerror = function (e) { if (e.error === 'not-allowed' || e.error === 'service-not-allowed') toast('Microphone permission is blocked'); };
      recognizer.onend = function () { S.recognizing = false; $.mic.classList.remove('on'); $.input.setAttribute('placeholder', S.mode === 'study' ? 'Ask a study question...' : T('placeholder')); };
      try { recognizer.start(); } catch (e) { /* already started */ }
    }
    function plain(t) { return String(t || '').replace(/\*\*/g, '').replace(/https?:\/\/\S+/g, '').replace(/[\u2022*-]\s/g, ' '); }
    /* VOICE-START
     * Read-aloud uses a female voice. Browsers do not say which voice is male or female, so we choose by the
     * well-known names (Windows Zira/Neerja/Swara/Sapna/Pallavi/Shruti/Sobhana, Apple Samantha/Veena/Lekha,
     * Google's default voices). If a device only has a male voice for the language, the pitch is raised.
     * VOICE-END marker below. */
    var VOICE = {
      female: /\b(female|woman|zira|hazel|susan|heera|neerja|swara|kalpana|sapna|pallavi|shruti|sobhana|lekha|veena|soumya|samantha|karen|moira|tessa|fiona|victoria|allison|ava|aria|jenny|sonia|libby|natasha|clara|emma|ananya|aarti|priya|kavya|kajal|tara)\b|^google\b/i,
      male: /\b(male|david|mark|george|ravi|prabhat|madhur|hemant|gagan|valluvar|midhun|mohan|rishi|daniel|alex|fred|james|guy|ryan|thomas|oliver|arthur|aaron|bruce|ralph|jorge|diego)\b/i,
      norm: function (l) { return String(l || '').toLowerCase().replace('_', '-'); },
      isFemale: function (v) { return VOICE.female.test(v.name || '') && !VOICE.male.test(v.name || ''); },
      pick: function (voices, lang, speech) {
        var exact = VOICE.norm(speech);
        var inLang = (voices || []).filter(function (v) { return v.lang && VOICE.norm(v.lang).indexOf(lang) === 0; });
        var fem = inLang.filter(VOICE.isFemale).sort(function (a, b) { return (VOICE.norm(b.lang) === exact) - (VOICE.norm(a.lang) === exact); });
        if (fem.length) return { voice: fem[0], confirmed: true };
        var neutral = inLang.filter(function (v) { return !VOICE.male.test(v.name || ''); });
        return { voice: neutral[0] || inLang[0] || null, confirmed: false };
      }
    };
    /* VOICE-END */
    function speak(text) {
      if (!window.speechSynthesis) return;
      var say = function () {
        try {
          speechSynthesis.cancel();
          var u = new SpeechSynthesisUtterance(plain(text)); u.lang = speechLang(); u.rate = 1;
          var all = speechSynthesis.getVoices() || [];
          var pick = VOICE.pick(all, S.lang, speechLang());
          if (!pick.voice && all.length && S.lang !== 'en') { toast('No voice for this language is installed on this device'); return; }
          if (pick.voice) u.voice = pick.voice;
          u.pitch = pick.confirmed ? 1.05 : 1.3;        // no confirmed female voice installed: raise the pitch
          speechSynthesis.speak(u);
        } catch (e) { /* ignore */ }
      };
      if ((speechSynthesis.getVoices() || []).length) return say();
      // Some browsers load their voice list late; wait briefly for it so the first reply is not read by a default male voice.
      var fired = false, go = function () { if (!fired) { fired = true; say(); } };
      try { speechSynthesis.addEventListener('voiceschanged', go, { once: true }); } catch (e) { /* old browsers */ }
      setTimeout(go, 700);
    }
    function stopSpeaking() { try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) { /* ignore */ } }

    /* ============================================================================================
     * 10. Panel framework
     * ========================================================================================== */
    var PANELS = {};
    var panelToken = 0;
    function openPanel(id, args) {
      if (!PANELS[id]) return;
      hideSheet();
      var token = ++panelToken;
      var back = h('button', { class: 'nw-pb', 'aria-label': T('back'), onclick: closePanel }, icon('back', 17));
      var title = h('b', {}, toolTitle(id));
      var right = h('span', {});
      var body = h('div', { class: 'nw-pbody' });
      var foot = h('div');
      put(clear($.panel), h('div', { class: 'nw-phead' }, back, title, right), body, foot);
      var ctx = { body: body, foot: foot, title: title, right: right, args: args || {}, alive: function () { return token === panelToken && $.panel.classList.contains('open'); } };
      $.panel.classList.add('open'); $.panel.setAttribute('aria-hidden', 'false'); $.win.classList.add('haspanel');
      if (!S.open) open();
      PANELS[id](ctx);
      body.scrollTop = 0;
    }
    function closePanel() { panelToken++; $.panel.classList.remove('open'); $.panel.setAttribute('aria-hidden', 'true'); $.win.classList.remove('haspanel'); stopBreathing(); }

    function loading(body, n) { clear(body); for (var i = 0; i < (n || 4); i++) body.appendChild(h('div', { class: 'nw-skel', style: 'animation-delay:' + (i * 90) + 'ms' })); }
    function failure(ctx, msg, retry) {
      put(clear(ctx.body), h('div', { class: 'nw-note', style: 'text-align:center;padding:20px' }, msg || T('offline'), retry ? h('div', { style: 'margin-top:12px' }, h('button', { class: 'nw-btn sm', onclick: retry }, icon('refresh', 14), 'Try again')) : null));
    }
    function confetti() {
      if (reduceMotion()) return;
      var wrap = h('div', { class: 'nw-conf' }), colors = ['#e0148c', '#1746d1', '#17f38c', '#f5a524', '#7c3aed', '#00b8d9'];
      for (var i = 0; i < 46; i++) wrap.appendChild(h('i', { style: 'left:' + Math.random() * 100 + '%;background:' + colors[i % colors.length] + ';--d:' + (1.6 + Math.random() * 1.6) + 's;animation-delay:' + Math.random() * .5 + 's;transform:rotate(' + Math.random() * 360 + 'deg)' }));
      $.win.appendChild(wrap); setTimeout(function () { wrap.remove(); }, 3600);
    }
    function successView(title, ref, lines, extra) {
      var d = h('div', { class: 'nw-done nw-step' });
      d.innerHTML = '<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="26"/><path d="M18 31l8 8 16-17"/></svg>';
      put(d, h('h3', { style: 'margin:10px 0 4px' }, title), ref ? h('div', { class: 'nw-ref' }, ref) : null, (lines || []).map(function (l) { return h('p', { style: 'margin:6px 0;color:var(--muted)' }, l); }), extra || null);
      return d;
    }
    function field(label, input, errText) { var w = h('div', { class: 'nw-field' }, h('label', {}, label), input, h('div', { class: 'nw-err' })); if (errText) { w.classList.add('err'); w.lastChild.textContent = errText; } return w; }
    function showFieldError(form, name, msg) {
      Array.prototype.forEach.call(form.querySelectorAll('.nw-field'), function (f) { f.classList.remove('err'); f.lastChild.textContent = ''; });
      var el = form.querySelector('[data-f="' + name + '"]'); var f = el && el.closest('.nw-field');
      if (f) { f.classList.add('err'); f.lastChild.textContent = msg; el.focus && el.focus(); f.scrollIntoView({ block: 'center', behavior: reduceMotion() ? 'auto' : 'smooth' }); }
      else toast(msg);
    }
    function segmented(options, value, onchange) {
      var wrap = h('div', { class: 'nw-seg' });
      options.forEach(function (o) {
        var b = h('button', { type: 'button', class: o.id === value ? 'on' : '', onclick: function () { Array.prototype.forEach.call(wrap.children, function (x) { x.classList.remove('on'); }); b.classList.add('on'); onchange(o.id); } }, o.label);
        wrap.appendChild(b);
      });
      return wrap;
    }

    /* ---- calendar files (client side, so no extra server endpoint is needed) ----------------- */
    function icsEscape(s) { return String(s || '').replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n'); }
    function utcStamp(date, time) {            // IST wall-clock -> UTC stamp
      var p = date.split('-').map(Number), t = (time || '00:00').split(':').map(Number);
      var d = new Date(Date.UTC(p[0], p[1] - 1, p[2], t[0], t[1]) - 330 * 60000);
      return d.getUTCFullYear() + pad(d.getUTCMonth() + 1) + pad(d.getUTCDate()) + 'T' + pad(d.getUTCHours()) + pad(d.getUTCMinutes()) + '00Z';
    }
    function dateOnly(date) { return date.replace(/-/g, ''); }
    function makeIcs(events) {
      var out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//CJC Noah//EN', 'CALSCALE:GREGORIAN'];
      events.forEach(function (e) {
        out.push('BEGIN:VEVENT', 'UID:' + e.uid + '@cjc-noah', 'DTSTAMP:' + new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+/, ''));
        if (e.allDay) { out.push('DTSTART;VALUE=DATE:' + dateOnly(e.date)); if (e.endDate) { var nd = new Date(e.endDate + 'T00:00:00'); nd.setDate(nd.getDate() + 1); out.push('DTEND;VALUE=DATE:' + nd.getFullYear() + pad(nd.getMonth() + 1) + pad(nd.getDate())); } }
        else { out.push('DTSTART:' + utcStamp(e.date, e.start), 'DTEND:' + utcStamp(e.date, e.end || e.start)); }
        out.push('SUMMARY:' + icsEscape(e.title));
        if (e.desc) out.push('DESCRIPTION:' + icsEscape(e.desc));
        if (e.location) out.push('LOCATION:' + icsEscape(e.location));
        (e.alarms || []).forEach(function (mins) { out.push('BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + icsEscape(e.title), 'TRIGGER:-PT' + mins + 'M', 'END:VALARM'); });
        out.push('END:VEVENT');
      });
      out.push('END:VCALENDAR');
      return out.join('\r\n');
    }
    function downloadFile(name, text, type) {
      var url = URL.createObjectURL(new Blob([text], { type: type || 'text/calendar' }));
      var a = h('a', { href: url, download: name }); shadow.appendChild(a); a.click(); setTimeout(function () { a.remove(); URL.revokeObjectURL(url); }, 500);
    }

    /* ============================================================================================
     * 11. Feature 1 - Stream Advisor (+ PU vs IBDP comparison)
     * ========================================================================================== */
    var INTEREST_OF = { PCMB: 'pu_science', PCMC: 'pu_science', CAMS: 'pu_commerce', CAME: 'pu_commerce', HESP: 'pu_arts', HEPP: 'pu_arts', PPES: 'pu_arts', IBDP: 'ibdp' };

    PANELS.advisor = function (ctx) {
      loading(ctx.body, 3);
      api('/api/advisor/questions').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, null, function () { PANELS.advisor(ctx); });
        run(r.data);
      });
      function run(data) {
        var qs = data.questions, i = 0, ans = {};
        function prog() { return h('div', { class: 'nw-prog' }, qs.map(function (_, k) { return h('i', { class: k <= i ? 'on' : '' }); })); }
        function advance() { if (i < qs.length - 1) { i++; step(); } else finish(); }
        function step() {
          var q = qs[i];
          var wrap = h('div', { class: 'nw-step' }, prog(), h('h3', { class: 'nw-q' }, q.title), q.hint ? h('p', { class: 'nw-hint' }, q.hint) : h('p', { class: 'nw-hint' }, 'Question ' + (i + 1) + ' of ' + qs.length));
          if (i === 0 && data.admission_status) wrap.insertBefore(h('div', { class: 'nw-alert' }, icon('info', 16), h('span', {}, data.admission_status)), wrap.firstChild.nextSibling);
          if (q.type === 'choice') {
            var o = h('div', { class: 'nw-opts' + (q.options.length > 4 ? ' one' : '') });
            q.options.forEach(function (opt) {
              o.appendChild(h('button', { class: 'nw-opt' + (ans[q.id] === opt.id ? ' on' : ''), onclick: function (e) { e.currentTarget.classList.add('on'); ans[q.id] = opt.id; setTimeout(advance, 180); } }, opt.label));
            });
            wrap.appendChild(o);
          } else if (q.type === 'slider') {
            var val = ans[q.id] !== undefined ? ans[q.id] : q.default;
            var big = h('div', { class: 'nw-big' }, val + q.unit);
            var rng = h('input', { type: 'range', min: q.min, max: q.max, value: val, 'aria-label': q.title, oninput: function () { val = Number(rng.value); big.textContent = val + q.unit; } });
            wrap.appendChild(h('div', { class: 'nw-slider' }, big, rng));
            wrap.appendChild(h('div', { class: 'nw-row2' }, q.optional ? h('button', { class: 'nw-btn ghost', onclick: function () { delete ans[q.id]; advance(); } }, 'Skip') : null, h('button', { class: 'nw-btn', onclick: function () { ans[q.id] = val; advance(); } }, 'Next', icon('next', 15))));
          } else if (q.type === 'multi') {
            var picked = ans[q.id] || [];
            var grid = h('div', { class: 'nw-opts' });
            q.options.forEach(function (opt) {
              var b = h('button', { class: 'nw-opt' + (picked.indexOf(opt.id) > -1 ? ' on' : ''), onclick: function () {
                var at = picked.indexOf(opt.id);
                if (at > -1) { picked.splice(at, 1); b.classList.remove('on'); }
                else if (picked.length < (q.max || 3)) { picked.push(opt.id); b.classList.add('on'); }
                else toast('Pick up to ' + (q.max || 3));
              } }, opt.label);
              grid.appendChild(b);
            });
            put(wrap, grid, h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { ans[q.id] = picked; advance(); } }, 'Next', icon('next', 15))));
          }
          if (i > 0) wrap.appendChild(h('button', { class: 'nw-btn ghost sm', style: 'margin-top:12px', onclick: function () { i--; step(); } }, icon('back', 14), T('back')));
          clear(ctx.body).appendChild(wrap); ctx.body.scrollTop = 0;
        }
        function finish() {
          loading(ctx.body, 3);
          api('/api/advisor/recommend', { body: { answers: ans } }).then(function (r) {
            if (!ctx.alive()) return;
            if (!r.ok) return failure(ctx, r.data.error, finish);
            showResults(r.data);
          });
        }
        function showResults(res) {
          var box = h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'Your best fits'), h('p', { class: 'nw-hint' }, 'Ranked from your answers. Tap a card’s buttons to take the next step.'));
          if (res.admission_status) box.appendChild(h('div', { class: 'nw-alert' }, icon('info', 16), h('span', {}, res.admission_status)));
          res.results.forEach(function (r, k) {
            var circ = 2 * Math.PI * 26;
            var ring = h('div', { class: 'nw-ring' });
            ring.innerHTML = '<svg width="62" height="62" viewBox="0 0 62 62"><circle class="bg" cx="31" cy="31" r="26"/><circle class="fg" cx="31" cy="31" r="26" stroke-dasharray="' + circ + '" stroke-dashoffset="' + circ + '"/></svg>';
            var fg = ring.querySelector('.fg'); ring.appendChild(h('b', {}, r.fit + '%'));
            setTimeout(function () { fg.setAttribute('stroke-dashoffset', circ * (1 - r.fit / 100)); }, 120 + k * 150);
            var pills = h('div', { class: 'nw-pills' });
            pills.appendChild(h('span', { class: 'nw-pill brand' }, 'Fee ' + (typeof r.fee === 'number' ? inr(r.fee) + '/yr' : r.fee)));
            if (r.cutoff) {
              if (r.cutoff.status === 'above') pills.appendChild(h('span', { class: 'nw-pill ok' }, 'Above ' + r.cutoff.category + ' cutoff ' + r.cutoff.value + '%'));
              else if (r.cutoff.status === 'below') pills.appendChild(h('span', { class: 'nw-pill warn' }, 'Below ' + r.cutoff.category + ' cutoff ' + r.cutoff.value + '%'));
              else pills.appendChild(h('span', { class: 'nw-pill' }, 'No ' + r.cutoff.category + ' cutoff published'));
            }
            r.reasons.forEach(function (t) { pills.appendChild(h('span', { class: 'nw-pill' }, t)); });
            r.warnings.forEach(function (t) { pills.appendChild(h('span', { class: 'nw-pill warn' }, t)); });
            box.appendChild(h('div', { class: 'nw-res' + (k === 0 ? ' best' : ''), style: 'animation-delay:' + (k * 120) + 'ms' }, ring,
              h('div', {}, h('h4', {}, r.code + (k === 0 ? '  •  Best fit' : '')), h('small', {}, r.name), pills, h('p', { style: 'margin:8px 0 0;font-size:12.5px;color:var(--muted)' }, r.blurb + (r.process ? ' ' + r.process : '')),
                h('div', { class: 'nw-row2', style: 'margin-top:10px' }, h('button', { class: 'nw-btn sm', onclick: function () { openPanel('callback', { interest: INTEREST_OF[r.code] }); } }, icon('phone', 14), 'Talk to admissions'), h('button', { class: 'nw-btn ghost sm', onclick: function () { closePanel(); send('What are the subjects and fee for ' + r.code + '?'); } }, 'Ask Noah')))));
          });
          box.appendChild(h('div', { class: 'nw-note' }, res.disclaimer));
          box.appendChild(h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn ghost', onclick: function () { openPanel('compare'); } }, icon('layers', 15), T('compare')), h('button', { class: 'nw-btn ghost', onclick: function () { i = 0; ans = {}; step(); } }, icon('refresh', 15), 'Start again')));
          clear(ctx.body).appendChild(box); ctx.body.scrollTop = 0;
        }
        step();
      }
    };

    PANELS.compare = function (ctx) {
      loading(ctx.body, 3);
      api('/api/compare').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, null, function () { PANELS.compare(ctx); });
        var d = r.data;
        var tbl = h('table', { class: 'nw-tbl' }, h('thead', {}, h('tr', {}, h('th', {}), d.columns.map(function (c) { return h('th', {}, c); }))),
          h('tbody', {}, d.rows.map(function (row) { return h('tr', {}, row.map(function (cell) { return h('td', {}, cell); })); })));
        put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'PU or IB Diploma?'), h('p', { class: 'nw-hint' }, d.note), tbl,
          h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { openPanel('advisor'); } }, icon('compass', 15), T('advisor')), h('button', { class: 'nw-btn ghost', onclick: function () { openPanel('callback', { interest: 'ibdp' }); } }, icon('phone', 15), T('callback')))));
      });
    };

    /* ============================================================================================
     * 12. Feature 2 - Callback request and campus visit
     * ========================================================================================== */
    var INTERESTS = [{ id: 'pu_science', label: 'PU Science' }, { id: 'pu_commerce', label: 'PU Commerce' }, { id: 'pu_arts', label: 'PU Arts' }, { id: 'ibdp', label: 'IB Diploma' }, { id: 'not_sure', label: 'Not sure yet' }];
    var BOARD_OPTS = [{ id: 'state', label: 'Karnataka State' }, { id: 'cbse', label: 'CBSE' }, { id: 'icse', label: 'ICSE' }, { id: 'other', label: 'Other' }];
    var CONSENT = 'I agree that Christ Junior College may contact me about admissions on this number. My details are used only for that.';

    function contactFields(form, v) {
      var name = h('input', { class: 'nw-f', 'data-f': 'name', autocomplete: 'name', maxlength: '80', placeholder: 'Full name' });
      var phone = h('input', { class: 'nw-f', 'data-f': 'phone', type: 'tel', inputmode: 'numeric', autocomplete: 'tel-national', maxlength: '14', placeholder: '10 digit mobile number' });
      var email = h('input', { class: 'nw-f', 'data-f': 'email', type: 'email', autocomplete: 'email', maxlength: '120', placeholder: 'name@example.com' });
      var consent = h('input', { type: 'checkbox', 'data-f': 'consent' });
      var hp = h('input', { class: 'nw-hp', tabindex: '-1', autocomplete: 'off', 'aria-hidden': 'true', name: 'website' });
      v.get = function () { return { name: name.value, phone: phone.value, email: email.value, consent: consent.checked, website: hp.value }; };
      return [field('Your name', name), field('Mobile number', h('div', { class: 'nw-phone' }, h('span', {}, '+91'), phone)), field('Email (optional)', email),
        h('label', { class: 'nw-check' }, consent, h('span', {}, CONSENT)), hp];
    }

    PANELS.callback = function (ctx) {
      var v = {}, state = { role: 'parent', board: '', interest: ctx.args.interest || 'not_sure', pref: 'any' };
      var form = h('form', { class: 'nw-step', novalidate: true, onsubmit: function (e) { e.preventDefault(); submit(); } });
      var note = h('textarea', { class: 'nw-f', maxlength: '300', placeholder: 'Anything you want us to know (optional)' });
      put(form, h('h3', { class: 'nw-q' }, 'We’ll call you back'), h('p', { class: 'nw-hint' }, 'Leave your details and the admissions office will phone you during office hours (Mon-Fri, 8:30-4:30).'),
        field('I am a', segmented([{ id: 'parent', label: 'Parent' }, { id: 'student', label: 'Student' }], state.role, function (x) { state.role = x; })),
        field('Class 10 board', segmented(BOARD_OPTS, state.board, function (x) { state.board = x; })),
        field('Interested in', (function () { var s = h('select', { class: 'nw-f' }, INTERESTS.map(function (o) { return h('option', { value: o.id, selected: o.id === state.interest ? true : null }, o.label); })); s.onchange = function () { state.interest = s.value; }; return s; })()),
        field('Best time to call', segmented([{ id: 'morning', label: 'Morning' }, { id: 'afternoon', label: 'Afternoon' }, { id: 'any', label: 'Any time' }], state.pref, function (x) { state.pref = x; })),
        contactFields(form, v), field('Note', note));
      var btn = h('button', { class: 'nw-btn pink block', type: 'submit' }, icon('phone', 16), 'Request a callback');
      form.appendChild(btn);
      clear(ctx.body).appendChild(form);
      function submit() {
        btn.disabled = true;
        var body = Object.assign(v.get(), { role: state.role, board: state.board, interest: state.interest, pref_time: state.pref, note: note.value });
        api('/api/callback', { body: body }).then(function (r) {
          btn.disabled = false;
          if (!r.ok) return showFieldError(form, r.data.field, r.data.error || T('offline'));
          clear(ctx.body).appendChild(successView('Request received', r.data.ref, ['The admissions office will call you soon on the number you gave.', 'Keep this reference handy if you call us.'],
            h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn ghost', onclick: function () { openPanel('visit'); } }, icon('calendar', 15), T('visit')), h('button', { class: 'nw-btn ghost', onclick: closePanel }, 'Done'))));
        });
      }
    };

    PANELS.visit = function (ctx) {
      loading(ctx.body, 3);
      api('/api/visit/slots').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, r.data.error, function () { PANELS.visit(ctx); });
        build(r.data);
      });
      function build(data) {
        if (!data.days.length) return clear(ctx.body).appendChild(h('div', { class: 'nw-note' }, 'No visit slots are open right now. Please request a callback and we will arrange one.', h('div', { style: 'margin-top:10px' }, h('button', { class: 'nw-btn sm', onclick: function () { openPanel('callback'); } }, T('callback')))));
        var pick = { date: data.days[0].date, time: '' }, v = {};
        var slotsBox = h('div', { class: 'nw-slots' });
        var dayBox = h('div', { class: 'nw-days' });
        function drawDays() {
          clear(dayBox);
          data.days.forEach(function (d) {
            var parts = d.label.split(' ');
            dayBox.appendChild(h('button', { class: 'nw-day' + (d.date === pick.date ? ' on' : ''), onclick: function () { pick.date = d.date; pick.time = ''; drawDays(); drawSlots(); } }, h('small', {}, parts[0]), h('b', {}, parts[1]), h('small', {}, parts[2])));
          });
        }
        function drawSlots() {
          clear(slotsBox);
          data.days.filter(function (d) { return d.date === pick.date; })[0].slots.forEach(function (s) {
            slotsBox.appendChild(h('button', { type: 'button', class: 'nw-slot' + (pick.time === s.time ? ' on' : ''), onclick: function () { pick.time = s.time; drawSlots(); } }, s.time, h('small', {}, s.left + (s.left === 1 ? ' place left' : ' places left'))));
          });
        }
        var form = h('form', { class: 'nw-step', novalidate: true, onsubmit: function (e) { e.preventDefault(); submit(); } });
        put(form, h('h3', { class: 'nw-q' }, 'Visit the campus'), h('p', { class: 'nw-hint' }, data.note), h('div', { class: 'nw-lab', style: 'margin-bottom:6px' }, 'Choose a day'), dayBox, h('div', { class: 'nw-lab', style: 'margin:4px 0 8px' }, 'Choose a time'), slotsBox,
          h('div', { class: 'nw-lab', style: 'margin-bottom:6px' }, 'Interested in'),
          h('div', { style: 'margin-bottom:12px' }, (function () { var s = h('select', { class: 'nw-f' }, INTERESTS.map(function (o) { return h('option', { value: o.id }, o.label); })); s.onchange = function () { pick.interest = s.value; }; pick.interest = 'not_sure'; return s; })()),
          contactFields(form, v));
        var btn = h('button', { class: 'nw-btn pink block', type: 'submit' }, icon('calendar', 16), 'Confirm my visit');
        form.appendChild(btn);
        drawDays(); drawSlots();
        clear(ctx.body).appendChild(form);
        function submit() {
          if (!pick.time) return toast('Please choose a time');
          btn.disabled = true;
          api('/api/visit/book', { body: Object.assign(v.get(), { date: pick.date, time: pick.time, interest: pick.interest }) }).then(function (r) {
            btn.disabled = false;
            if (!r.ok) { if (r.data.field === 'slot') { toast(r.data.error); return PANELS.visit(ctx); } return showFieldError(form, r.data.field, r.data.error || T('offline')); }
            var res = r.data;
            var when = prettyDate(res.date) + ' at ' + res.time;
            var cal = h('button', { class: 'nw-btn ghost', onclick: function () {
              var end = pad(parseInt(res.time.split(':')[0], 10) + 1) + ':' + res.time.split(':')[1];
              downloadFile('cjc-campus-visit.ics', makeIcs([{ uid: 'visit-' + res.ref, date: res.date, start: res.time, end: end, title: 'Campus visit - Christ Junior College', desc: res.note + ' Reference ' + res.ref, location: res.place, alarms: [1440, 120] }]));
            } }, icon('download', 15), 'Add to calendar');
            var maps = h('a', { class: 'nw-btn ghost', href: 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(res.place), target: '_blank', rel: 'noopener noreferrer' }, icon('pin', 15), 'Directions');
            clear(ctx.body).appendChild(successView('You’re booked', res.ref, [when, res.place, res.note], h('div', { class: 'nw-row2' }, cal, maps)));
          });
        }
      }
    };

    /* ============================================================================================
     * 13. Feature 8 - Document checklist (tick off, print or save as PDF, share)
     * ========================================================================================== */
    PANELS.documents = function (ctx) {
      var sel = { program: ctx.args.program || 'pu', board: ctx.args.board || LS.get('noah_board', 'state') };
      var opts = null, listBox = h('div'), head = h('div');
      loading(ctx.body, 3);
      api('/api/checklist/options').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, null, function () { PANELS.documents(ctx); });
        opts = r.data;
        put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'Documents you need'), h('p', { class: 'nw-hint' }, 'Pick your programme and Class 10 board. Tick items off as you collect them.'),
          h('div', { class: 'nw-lab' }, 'Programme'), segmented(opts.programs, sel.program, function (x) { sel.program = x; load(); }),
          h('div', { class: 'nw-lab', style: 'margin-top:10px' }, 'Class 10 board'),
          (function () { var s = h('select', { class: 'nw-f', style: 'margin-bottom:12px' }, opts.boards.map(function (b) { return h('option', { value: b.id, selected: b.id === sel.board ? true : null }, b.label); })); s.onchange = function () { sel.board = s.value; LS.set('noah_board', s.value); load(); }; return s; })(),
          head, listBox));
        load();
      });
      function load() {
        loading(listBox, 3); clear(head);
        api('/api/checklist?program=' + sel.program + '&board=' + sel.board).then(function (r) {
          if (!ctx.alive()) return;
          if (!r.ok) return failure({ body: listBox }, r.data.error);
          render(r.data);
        });
      }
      function render(c) {
        var key = 'noah_docs_v1:' + c.program + ':' + c.board, done = {};
        try { done = JSON.parse(LS.get(key, '{}')) || {}; } catch (e) { done = {}; }
        var meter = h('div', { class: 'nw-meter' }, h('span', {}), h('div', { class: 'tr' }, h('i')), h('b', {}));
        function refresh() {
          var n = c.items.filter(function (it) { return done[it.id]; }).length;
          meter.firstChild.textContent = 'Collected'; meter.lastChild.textContent = n + '/' + c.items.length;
          meter.querySelector('i').style.width = (c.items.length ? n / c.items.length * 100 : 0) + '%';
          if (c.items.length && n === c.items.length && !refresh.fired) { refresh.fired = true; confetti(); }
        }
        clear(head);
        if (c.items.length) head.appendChild(meter);
        clear(listBox);
        if (!c.items.length) listBox.appendChild(h('div', { class: 'nw-note' }, 'The college does not publish a fixed document list for this programme. The office confirms it during the process.'));
        c.items.forEach(function (it, k) {
          var row = h('div', { class: 'nw-cl' + (done[it.id] ? ' on' : ''), style: 'animation-delay:' + (k * 50) + 'ms', role: 'checkbox', 'aria-checked': done[it.id] ? 'true' : 'false', tabindex: '0',
            onclick: function (e) { if (e.target.closest && e.target.closest('a')) return; done[it.id] = !done[it.id]; LS.set(key, JSON.stringify(done)); row.classList.toggle('on', !!done[it.id]); row.setAttribute('aria-checked', done[it.id] ? 'true' : 'false'); refresh(); },
            onkeydown: function (e) { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); row.click(); } } },
            h('span', { class: 'bx' }, icon('check', 14)), h('div', {}, h('b', {}, it.text + (it.optional ? ' (if applicable)' : '')), it.note ? h('small', {}, it.note) : null,
              it.link_url ? h('a', { class: 'nw-btn sm', style: 'margin-top:8px', href: safeUrl(it.link_url), target: '_blank', rel: 'noopener noreferrer' }, icon('link', 14), it.link_label) : null));
          listBox.appendChild(row);
        });
        listBox.appendChild(h('div', { class: 'nw-sec' }, 'The process'));
        listBox.appendChild(h('div', { class: 'nw-tl' }, c.steps.map(function (s, k) { return h('div', { 'data-n': k + 1 }, s); })));
        if (c.link) listBox.appendChild(h('a', { class: 'nw-btn ghost block', style: 'margin-bottom:10px', href: safeUrl(c.link.url), target: '_blank', rel: 'noopener noreferrer' }, icon('link', 15), c.link.label));
        listBox.appendChild(h('div', { class: 'nw-note' }, c.footer));
        listBox.appendChild(h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { printChecklist(c, done); } }, icon('printer', 15), 'Save as PDF'),
          h('a', { class: 'nw-btn ghost', target: '_blank', rel: 'noopener noreferrer', href: 'https://wa.me/?text=' + encodeURIComponent(c.title + ' (' + c.board_label + ')\n' + c.items.map(function (i) { return '- ' + i.text; }).join('\n') + '\n\nChrist Junior College') }, 'Share')));
        refresh();
      }
      function printChecklist(c, done) {
        var rows = c.items.map(function (i) { return '<li><span class="b">' + (done[i.id] ? '&#10003;' : '') + '</span><div><b>' + esc(i.text) + (i.optional ? ' (if applicable)' : '') + '</b>' + (i.note ? '<br><small>' + esc(i.note) + '</small>' : '') + '</div></li>'; }).join('');
        var steps = c.steps.map(function (s) { return '<li>' + esc(s) + '</li>'; }).join('');
        var html = '<!doctype html><meta charset="utf-8"><title>' + esc(c.title) + '</title><style>body{font:14px/1.5 Arial,sans-serif;color:#111;margin:32px}h1{font-size:22px;margin:0}h2{font-size:15px;margin:22px 0 6px}small{color:#555}.top{border-bottom:3px solid #1746d1;padding-bottom:10px;margin-bottom:14px}ul.c{list-style:none;padding:0}ul.c li{display:flex;gap:12px;padding:8px 0;border-bottom:1px solid #ddd}.b{width:18px;height:18px;border:2px solid #333;border-radius:3px;flex:none;text-align:center;line-height:16px;font-weight:700}.f{margin-top:18px;font-size:12px;color:#444;border-top:1px solid #ccc;padding-top:8px}</style>'
          + '<div class="top"><h1>Christ Junior College, Bengaluru</h1><div>' + esc(c.title) + ' &mdash; ' + esc(c.board_label) + '</div><small>Prepared ' + new Date().toLocaleDateString('en-IN') + '</small></div>'
          + (rows ? '<h2>Documents</h2><ul class="c">' + rows + '</ul>' : '') + '<h2>Process</h2><ol>' + steps + '</ol><div class="f">' + esc(c.footer) + '<br>PU office +91 080 4012 9292 &middot; office@cjc.christcollege.edu</div>';
        var frame = h('iframe', { style: 'position:fixed;width:0;height:0;border:0;right:0;bottom:0', 'aria-hidden': 'true' });
        shadow.appendChild(frame);
        frame.onload = function () { try { frame.contentWindow.focus(); frame.contentWindow.print(); } catch (e) { toast('Printing is blocked in this browser'); } setTimeout(function () { frame.remove(); }, 60000); };
        frame.srcdoc = html;
      }
    };

    /* ============================================================================================
     * 14. Feature 9 - Career pathway explorer
     * ========================================================================================== */
    PANELS.careers = function (ctx) {
      loading(ctx.body, 3);
      api('/api/careers').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, null, function () { PANELS.careers(ctx); });
        var data = r.data, cur = (data.paths.filter(function (p) { return p.id === ctx.args.path; })[0] || data.paths[0]);
        var tabs = h('div', { class: 'nw-paths' }), map = h('div');
        function draw() {
          clear(tabs);
          data.paths.forEach(function (p) {
            tabs.appendChild(h('button', { class: p === cur ? 'on' : '', style: p === cur ? 'background:' + p.color : '', onclick: function () { cur = p; draw(); } }, p.label));
          });
          clear(map).appendChild(h('div', { class: 'nw-map', style: '--c:' + cur.color },
            [['Entrance exams', cur.exams], ['Courses after PUC', cur.courses], ['Careers', cur.careers]].map(function (g, k) {
              return h('div', { class: 'nw-node', style: 'animation-delay:' + (k * 130) + 'ms' }, h('h5', {}, g[0]), h('div', { class: 'nw-pills' }, g[1].map(function (t) { return h('span', { class: 'nw-pill' }, t); })));
            })));
          if (INTEREST_OF[cur.id]) map.appendChild(h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn ghost', onclick: function () { closePanel(); send('What are the subjects and fee for ' + cur.id + '?'); } }, 'Ask Noah about ' + cur.id), h('button', { class: 'nw-btn ghost', onclick: function () { openPanel('callback', { interest: INTEREST_OF[cur.id] }); } }, T('callback'))));
        }
        put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'Where can it lead?'), h('p', { class: 'nw-hint' }, 'Choose a stream to see exams, courses and careers.'), tabs, map,
          h('div', { class: 'nw-note' }, h('b', {}, 'Christ University route. '), data.christ_route), h('div', { class: 'nw-note' }, data.disclaimer)));
        draw();
      });
    };

    /* ============================================================================================
     * 15. Feature 10 - Event assistant
     * ========================================================================================== */
    var TAG_COLOR = { conference: '#7c3aed', admission: '#e0148c', fest: '#0891b2', sports: '#0e9f6e', celebration: '#c81e3a' };
    PANELS.events = function (ctx) {
      loading(ctx.body, 3);
      var timer = null;
      api('/api/events').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok) return failure(ctx, r.data.error, function () { PANELS.events(ctx); });
        var box = h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'Events and campaigns'), h('p', { class: 'nw-hint' }, 'Dates, links and reminders for what is happening at CJC.'));
        var tickers = [];
        r.data.events.forEach(function (e, k) {
          var status = e.status === 'over' ? h('span', { class: 'nw-pill' }, 'Over for this year') : e.status === 'happening' ? h('span', { class: 'nw-pill ok' }, 'Happening now') : e.status === 'today' ? h('span', { class: 'nw-pill ok' }, 'Today') : e.status === 'past' ? h('span', { class: 'nw-pill' }, 'Ended') : e.status === 'upcoming' ? h('span', { class: 'nw-pill brand' }, 'In ' + e.days_left + (e.days_left === 1 ? ' day' : ' days')) : h('span', { class: 'nw-pill warn' }, 'Dates to be announced');
          var card = h('div', { class: 'nw-ev', style: '--c:' + (TAG_COLOR[e.tag] || '#1746d1') + ';animation-delay:' + (k * 80) + 'ms' }, h('div', { class: 'nw-pills', style: 'margin:0 0 6px' }, status, e.tag ? h('span', { class: 'nw-pill' }, e.tag) : null), h('h4', {}, e.title), h('p', {}, e.blurb));
          if (e.status === 'upcoming') {
            var cd = h('div', { class: 'nw-cd' }, ['Days', 'Hours', 'Min', 'Sec'].map(function (u) { return h('div', {}, h('b', {}, '0'), h('small', {}, u)); }));
            card.appendChild(cd);
            var parts = e.starts.split('T'), tgt = utcMs(parts[0], parts[1] || '00:00');
            tickers.push(function () { var s = Math.max(0, Math.floor((tgt - Date.now()) / 1000)); var v = [Math.floor(s / 86400), Math.floor(s % 86400 / 3600), Math.floor(s % 3600 / 60), s % 60]; v.forEach(function (n, i) { cd.children[i].firstChild.textContent = i ? pad(n) : n; }); });
          }
          if (e.starts) card.appendChild(h('div', { class: 'nw-kv' }, h('span', {}, 'When'), h('b', {}, prettyDate(e.starts.split('T')[0]) + (e.ends ? ' to ' + prettyDate(e.ends.split('T')[0]) : '') + (e.starts.indexOf('T') > -1 ? ', ' + e.starts.split('T')[1] : ''))));
          if (e.location) card.appendChild(h('div', { class: 'nw-kv' }, h('span', {}, 'Where'), h('b', {}, e.location)));
          if (e.contact) card.appendChild(h('div', { class: 'nw-kv' }, h('span', {}, 'Contact'), h('b', {}, /@/.test(e.contact) ? h('a', { href: 'mailto:' + e.contact }, e.contact) : /^\+?[\d\s]+$/.test(e.contact) ? h('a', { href: 'tel:' + e.contact.replace(/\s/g, '') }, e.contact) : e.contact)));
          var row = h('div', { class: 'nw-acts', style: 'margin-top:10px' });
          if (e.link_url) row.appendChild(h('a', { class: 'nw-btn sm', href: safeUrl(e.link_url), target: '_blank', rel: 'noopener noreferrer' }, icon('link', 14), e.link_label || 'Details'));
          if (e.starts && e.status !== 'past' && e.status !== 'over') row.appendChild(h('button', { class: 'nw-btn ghost sm', onclick: function () {
            var d0 = e.starts.split('T'), allDay = !d0[1];
            downloadFile(e.id + '.ics', makeIcs([{ uid: e.id, title: e.title, desc: e.blurb, location: e.location, date: d0[0], start: d0[1], end: d0[1], allDay: allDay, endDate: e.ends ? e.ends.split('T')[0] : null, alarms: [1440, 60] }]));
          } }, icon('calendar', 14), 'Remind me'));
          row.appendChild(h('button', { class: 'nw-btn ghost sm', onclick: function () { closePanel(); send('Tell me about ' + e.title); } }, 'Ask Noah'));
          card.appendChild(row);
          box.appendChild(card);
        });
        if (!r.data.events.length) box.appendChild(h('div', { class: 'nw-note' }, 'No events are listed right now. Check back soon.'));
        clear(ctx.body).appendChild(box);
        if (tickers.length) { var tick = function () { if (!ctx.alive()) return clearInterval(timer); tickers.forEach(function (f) { f(); }); }; tick(); timer = setInterval(tick, 1000); }
      });
    };
    function utcMs(date, time) { var p = date.split('-').map(Number), t = time.split(':').map(Number); return Date.UTC(p[0], p[1] - 1, p[2], t[0], t[1]) - 330 * 60000; }

    /* ============================================================================================
     * 16. Feature 13 - Wellness check-in (private: nothing here goes into the chat log)
     * ========================================================================================== */
    var breathTimers = [];
    function stopBreathing() { breathTimers.forEach(clearTimeout); breathTimers = []; }
    var MOOD_STYLE = [
      { g: 'linear-gradient(145deg,#8b97c9,#4b5a9e)', s: 'rgba(75,90,158,.4)' }, { g: 'linear-gradient(145deg,#8fb3e6,#4f78c0)', s: 'rgba(79,120,192,.4)' },
      { g: 'linear-gradient(145deg,#a8dccd,#4fa68c)', s: 'rgba(79,166,140,.4)' }, { g: 'linear-gradient(145deg,#ffe29a,#f2a93a)', s: 'rgba(242,169,58,.45)' },
      { g: 'linear-gradient(145deg,#ffb3c9,#e0148c)', s: 'rgba(224,20,140,.4)' }
    ];

    PANELS.wellness = function (ctx) {
      var info = null, tab = ctx.args.tab || 'checkin', pane = h('div'), tabs = h('div', { class: 'nw-tabs' });
      loading(ctx.body, 3);
      api('/api/wellness/info').then(function (r) {
        if (!ctx.alive()) return;
        if (!r.ok || r.data.enabled === false) return failure(ctx, r.data.error || 'The wellness check-in is not available right now.');
        info = r.data;
        var h0 = info.helplines[0];
        clear(ctx.foot).appendChild(h('div', { class: 'nw-strip' }, icon('heart', 15), h('span', {}, 'Need to talk to someone now?'), h('a', { href: 'tel:' + h0.phone }, h0.phone + ' (free, 24x7)')));
        put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'How are you, really?'), h('p', { class: 'nw-hint' }, 'A private check-in. Nothing here is saved to the chat log, and it is not a diagnosis.'), tabs, pane));
        draw();
      });
      function draw() {
        stopBreathing(); clear(tabs);
        [['checkin', 'Check-in'], ['breathe', 'Breathe'], ['help', 'Get help']].forEach(function (t) { tabs.appendChild(h('button', { class: tab === t[0] ? 'on' : '', onclick: function () { tab = t[0]; draw(); } }, t[1])); });
        clear(pane);
        if (tab === 'checkin') checkin(); else if (tab === 'breathe') breathe(pane); else help();
      }
      function checkin() {
        var mood = 0, picked = [];
        var moods = h('div', { class: 'nw-moods' }, info.moods.map(function (m, i) {
          var b = h('button', { class: 'nw-mood', style: '--g:' + MOOD_STYLE[i].g + ';--s:' + MOOD_STYLE[i].s, 'aria-label': m.label, onclick: function () { mood = m.value; Array.prototype.forEach.call(moods.children, function (x) { x.classList.remove('on'); }); b.classList.add('on'); next.disabled = false; } }, h('i'), m.label);
          return b;
        }));
        var chips = h('div', { class: 'nw-chipsel' }, info.concerns.map(function (c) {
          var b = h('button', { type: 'button', onclick: function () { var at = picked.indexOf(c); if (at > -1) { picked.splice(at, 1); b.classList.remove('on'); } else if (picked.length < 3) { picked.push(c); b.classList.add('on'); } else toast('Pick up to 3'); } }, c);
          return b;
        }));
        var next = h('button', { class: 'nw-btn pink block', style: 'margin-top:16px', disabled: true, onclick: function () {
          next.disabled = true;
          api('/api/wellness/checkin', { body: { mood: mood, concerns: picked, lang: S.lang } }).then(function (r) {
            if (!r.ok) { next.disabled = false; return toast(r.data.error || T('offline')); }
            result(r.data);
          });
        } }, 'See my reflection', icon('next', 15));
        put(pane, h('div', { class: 'nw-lab' }, 'How are you feeling right now?'), moods, h('div', { class: 'nw-lab' }, 'What is on your mind? (optional, up to 3)'), chips, next);
      }
      function result(d) {
        clear(pane).appendChild(h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, d.headline), h('p', { style: 'margin:0 0 12px' }, d.message),
          d.tips.map(function (t) { return h('div', { class: 'nw-card', style: 'margin-bottom:8px' }, t); }),
          d.show_helplines ? [h('div', { class: 'nw-sec' }, 'You are not alone'), helpList(d.helplines), h('div', { class: 'nw-note' }, d.college_line)] : null,
          h('div', { class: 'nw-sec' }, 'Try a 5-4-3-2-1 grounding'), h('div', { class: 'nw-tl' }, d.grounding.map(function (g, k) { return h('div', { 'data-n': 5 - k }, g); })),
          h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { tab = 'breathe'; draw(); } }, 'Breathe with me'), d.suggest_counsellor ? h('button', { class: 'nw-btn ghost', onclick: function () { tab = 'help'; draw(); } }, 'Talk to a counsellor') : null)));
      }
      function helpList(list) {
        return h('div', { class: 'nw-helps' }, list.map(function (x) { return h('a', { class: 'nw-help', href: 'tel:' + x.phone }, h('span', { class: 'ti' }, icon('phone', 17)), h('span', {}, h('b', {}, x.name), h('small', {}, x.note || '')), h('em', {}, x.phone)); }));
      }
      function help() {
        var v = {}, pref = 'any', cls = h('input', { class: 'nw-f', 'data-f': 'class_name', maxlength: '40', placeholder: 'For example II PUC' });
        var note = h('textarea', { class: 'nw-f', maxlength: '300', placeholder: 'Only share what you are comfortable with (optional)' });
        var form = h('form', { novalidate: true, onsubmit: function (e) { e.preventDefault(); submit(); } });
        put(form, field('Your class', cls), field('Best time', segmented([{ id: 'morning', label: 'Morning' }, { id: 'afternoon', label: 'Afternoon' }, { id: 'any', label: 'Any time' }], pref, function (x) { pref = x; })), contactFields(form, v), field('Note', note));
        var btn = h('button', { class: 'nw-btn pink block', type: 'submit' }, icon('heart', 15), 'Request a counsellor');
        form.appendChild(btn);
        put(pane, h('div', { class: 'nw-sec', style: 'margin-top:0' }, 'Free helplines'), helpList(info.helplines), h('div', { class: 'nw-note' }, info.college_line),
          h('div', { class: 'nw-sec' }, 'Ask the counselling team to contact you'), form);
        function submit() {
          btn.disabled = true;
          api('/api/wellness/counselling', { body: Object.assign(v.get(), { class_name: cls.value, pref_time: pref, note: note.value }) }).then(function (r) {
            btn.disabled = false;
            if (!r.ok) return showFieldError(form, r.data.field, r.data.error || T('offline'));
            clear(pane).appendChild(successView('Request sent', r.data.ref, ['The counselling team will contact you. Reaching out was a brave step.']));
          });
        }
      }
    };

    function breathe(pane) {
      var orb = h('div', { class: 'nw-orb' }, 'Ready'), count = h('div', { class: 'nw-hint', style: 'margin-top:14px' }, 'Five slow breaths. In for 4, hold for 2, out for 6.');
      var go = h('button', { class: 'nw-btn block', onclick: function () { start(); } }, 'Start');
      put(pane, h('div', { class: 'nw-breath' }, orb, count), go);
      function start() {
        stopBreathing(); go.disabled = true; var n = 0;
        function cycle() {
          if (n >= 5) { orb.className = 'nw-orb'; orb.textContent = 'Well done'; count.textContent = 'Notice how your body feels now.'; go.disabled = false; go.textContent = 'Again'; return; }
          n++; count.textContent = 'Breath ' + n + ' of 5';
          orb.className = 'nw-orb in'; orb.textContent = 'Breathe in';
          breathTimers.push(setTimeout(function () { orb.className = 'nw-orb hold'; orb.textContent = 'Hold'; }, 4000));
          breathTimers.push(setTimeout(function () { orb.className = 'nw-orb out'; orb.textContent = 'Breathe out'; }, 6000));
          breathTimers.push(setTimeout(cycle, 12000));
        }
        requestAnimationFrame(function () { requestAnimationFrame(cycle); });
      }
    }

    /* ============================================================================================
     * 17. Features 11 + 12 - Student Zone (exam planner, quiz, flashcards, study helper)
     * ========================================================================================== */
    function parseTiming(t) {
      var m = /(\d{1,2}):(\d{2})\s*(AM|PM)\s*to\s*(\d{1,2}):(\d{2})\s*(AM|PM)/i.exec(t || '');
      function to24(hh, mm, ap) { var x = (+hh) % 12; if (/pm/i.test(ap)) x += 12; return pad(x) + ':' + mm; }
      return m ? { start: to24(m[1], m[2], m[3]), end: to24(m[4], m[5], m[6]) } : { start: '10:00', end: '13:00' };
    }

    PANELS.student = function (ctx) {
      if (!S.student) return studentLogin();
      var tab = ctx.args.tab || 'exams', pane = h('div'), tabs = h('div', { class: 'nw-tabs' });
      var out = h('button', { class: 'nw-pb', 'aria-label': 'Sign out', title: 'Sign out', onclick: function () { S.student = null; SS.del('noah_student'); if (S.mode === 'study') setMode('chat', true); PANELS.student(ctx); } }, icon('logout', 16));
      clear(ctx.right).appendChild(out);
      put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, S.student.label), h('p', { class: 'nw-hint' }, 'Your Student Zone. The study tools are an aid, not a replacement for your teachers.'), tabs, pane));
      draw();
      function draw() {
        clear(tabs);
        [['exams', 'Exams'], ['quiz', 'Quiz'], ['cards', 'Cards'], ['tutor', 'Tutor']].forEach(function (t) { tabs.appendChild(h('button', { class: tab === t[0] ? 'on' : '', onclick: function () { tab = t[0]; draw(); } }, t[1])); });
        clear(pane);
        if (tab === 'exams') exams(); else if (tab === 'quiz') studyForm('quiz'); else if (tab === 'cards') studyForm('cards'); else tutor();
      }
      function expired() { toast('Your Student Zone session ended. Please sign in again.'); PANELS.student(ctx); }

      function studentLogin() {
        clear(ctx.right);
        var code = h('input', { class: 'nw-f', placeholder: 'CJC-XXXXX-XXXXX', autocomplete: 'off', autocapitalize: 'characters', maxlength: '20', style: 'text-transform:uppercase;letter-spacing:1.5px;font-weight:700;text-align:center;font-size:16px' });
        var err = h('div', { class: 'nw-err', style: 'text-align:center;margin-top:6px' });
        var btn = h('button', { class: 'nw-btn block', type: 'submit', style: 'margin-top:12px' }, icon('key', 15), 'Open my Student Zone');
        var form = h('form', { class: 'nw-step', onsubmit: function (e) {
          e.preventDefault(); if (!code.value.trim()) return;
          btn.disabled = true; err.textContent = '';
          api('/api/student/login', { body: { code: code.value } }).then(function (r) {
            btn.disabled = false;
            if (!r.ok) { err.textContent = r.data.error || T('offline'); return; }
            S.student = r.data; SS.set('noah_student', JSON.stringify(r.data)); PANELS.student(ctx);
          });
        } }, h('div', { style: 'text-align:center;margin:10px 0 18px' }, h('div', { class: 'nw-tile', style: '--hue:#4f46e5;display:inline-grid;place-items:center;width:72px;height:72px;border-radius:24px' }, h('span', { class: 'ti', style: 'width:44px;height:44px;border-radius:16px' }, icon('user', 24)))),
        h('h3', { class: 'nw-q', style: 'text-align:center' }, 'Student Zone'), h('p', { class: 'nw-hint', style: 'text-align:center' }, 'Your exam planner, quizzes, flashcards and a study helper. Enter the access code your class teacher gave you.'), code, err, btn,
          h('div', { class: 'nw-note', style: 'margin-top:16px' }, 'This is separate from the college Student Login portal. Ask your class teacher or the office if you do not have a code.'));
        clear(ctx.body).appendChild(form); code.focus();
      }

      /* -- exams -- */
      function exams() {
        var chosen = []; try { chosen = JSON.parse(LS.get('noah_subjects_v1', '[]')) || []; } catch (e) { chosen = []; }
        var box = h('div'); pane.appendChild(box); loading(box, 3);
        function load() {
          api('/api/student/exams?subjects=' + encodeURIComponent(chosen.join(',')), { student: true }).then(function (r) {
            if (!ctx.alive() || tab !== 'exams') return;
            if (r.status === 401) return expired();
            if (!r.ok) return failure({ body: box }, r.data.error, load);
            render(r.data);
          });
        }
        function render(d) {
          clear(box);
          box.appendChild(h('div', { class: 'nw-lab' }, 'My subjects (tap to choose)'));
          box.appendChild(h('div', { class: 'nw-chipsel', style: 'margin-bottom:14px' }, d.subjects.map(function (s) {
            var b = h('button', { type: 'button', class: chosen.indexOf(s) > -1 ? 'on' : '', onclick: function () { var at = chosen.indexOf(s); if (at > -1) chosen.splice(at, 1); else chosen.push(s); LS.set('noah_subjects_v1', JSON.stringify(chosen)); load(); } }, s); return b;
          })));
          if (d.next) {
            var n = d.next;
            box.appendChild(h('div', { class: 'nw-hero' }, h('div', { class: 'n' }, n.days_left === 0 ? 'Today' : n.days_left), h('div', {}, h('b', {}, n.days_left === 0 ? 'Your next exam is today' : (n.days_left === 1 ? 'day to your next exam' : 'days to your next exam')),
              h('div', {}, n.subjects.map(function (s) { return s.name; }).join(', ')), h('small', {}, prettyDate(n.date) + ', ' + n.timing))));
          } else if (d.finished) box.appendChild(h('div', { class: 'nw-alert' }, icon('info', 16), h('span', {}, 'All exams in this timetable are over. The next timetable will appear here when the college publishes it.')));
          else if (!d.rows.length) box.appendChild(h('div', { class: 'nw-note' }, 'No exams found for the subjects you chose.'));
          d.rows.forEach(function (row, k) {
            var dt = new Date(row.date + 'T00:00:00');
            var cls = 'nw-exam' + (row.holiday ? ' hol' : '') + (d.next && d.next.date === row.date ? ' next' : '') + (row.days_left < 0 ? ' past' : '');
            box.appendChild(h('div', { class: cls, style: 'animation-delay:' + (k * 40) + 'ms' }, h('div', { class: 'nw-date' }, h('b', {}, dt.getDate()), h('small', {}, dt.toLocaleDateString('en-IN', { month: 'short' }))),
              h('div', {}, row.holiday ? h('b', {}, row.holiday) : row.subjects.map(function (s) { return h('div', {}, h('b', {}, s.name), h('small', { style: 'color:var(--muted)' }, ' code ' + s.code)); }), h('small', { style: 'color:var(--muted)' }, row.day + (row.timing ? ', ' + row.timing : '')))));
          });
          var upcoming = d.rows.filter(function (r) { return r.subjects.length && r.days_left >= 0; });
          if (upcoming.length) box.appendChild(h('button', { class: 'nw-btn block', style: 'margin-top:8px', onclick: function () {
            var evs = upcoming.map(function (r, i) { var tm = parseTiming(r.timing); return { uid: 'exam-' + r.date + '-' + i, date: r.date, start: tm.start, end: tm.end, title: 'Exam: ' + r.subjects.map(function (s) { return s.name; }).join(', '), desc: d.title + ' (' + d.term + ')', location: 'Christ Junior College', alarms: [1440, 60] }; });
            downloadFile('cjc-exams.ics', makeIcs(evs)); toast('Calendar file saved. Open it to add reminders.');
          } }, icon('calendar', 15), 'Add my exams + reminders to my calendar'));
        }
        load();
      }

      /* -- quiz + flashcards -- */
      function studyForm(kind) {
        var subj = h('select', { class: 'nw-f' }), topic = h('input', { class: 'nw-f', maxlength: '120', placeholder: kind === 'quiz' ? 'For example: Newton’s laws of motion' : 'For example: Periodic table trends' });
        var diff = 'medium', count = kind === 'quiz' ? 5 : 8;
        var go = h('button', { class: 'nw-btn block', style: 'margin-top:6px', onclick: generate }, icon('star', 15), kind === 'quiz' ? 'Make my quiz' : 'Make my flashcards');
        put(pane, h('div', { class: 'nw-field' }, h('label', {}, 'Subject'), subj), field('Topic', topic),
          kind === 'quiz' ? [field('Difficulty', segmented([{ id: 'easy', label: 'Easy' }, { id: 'medium', label: 'Medium' }, { id: 'hard', label: 'Hard' }], diff, function (x) { diff = x; })), field('Questions', segmented([{ id: '5', label: '5' }, { id: '8', label: '8' }, { id: '10', label: '10' }], '5', function (x) { count = +x; }))] : null, go,
          h('div', { class: 'nw-note', style: 'margin-top:14px' }, 'Made by AI from your topic. It can make mistakes, so check anything important with your textbook or teacher.'));
        api('/api/study/subjects', { student: true }).then(function (r) { if (r.status === 401) return expired(); (r.data.subjects || ['General']).forEach(function (s) { subj.appendChild(h('option', { value: s }, s)); }); });
        function generate() {
          if (topic.value.trim().length < 3) return toast('Add a topic first');
          var body = { subject: subj.value, topic: topic.value, lang: S.lang }, view = h('div');
          if (kind === 'quiz') { body.difficulty = diff; body.count = count; } else body.count = count;
          clear(pane).appendChild(view); loading(view, 3);
          view.appendChild(h('p', { class: 'nw-hint', style: 'text-align:center' }, 'Writing your ' + (kind === 'quiz' ? 'quiz' : 'cards') + '...'));
          api(kind === 'quiz' ? '/api/study/quiz' : '/api/study/flashcards', { body: body, student: true }).then(function (r) {
            if (!ctx.alive() || tab !== (kind === 'quiz' ? 'quiz' : 'cards')) return;
            if (r.status === 401) return expired();
            if (!r.ok) { clear(pane); studyForm(kind); return toast(r.data.error || T('offline')); }
            if (kind === 'quiz') runQuiz(r.data); else runCards(r.data);
          });
        }
      }

      function runQuiz(q) {
        var i = 0, score = 0, wrong = [], box = h('div'); clear(pane).appendChild(box);
        function ask() {
          var item = q.questions[i], locked = false;
          var opts = h('div', { class: 'nw-opts one' }), why = h('div', { class: 'nw-note', hidden: true }), nextBtn = h('button', { class: 'nw-btn block', hidden: true, onclick: function () { i++; if (i < q.questions.length) ask(); else end(); } }, i === q.questions.length - 1 ? 'See my score' : 'Next question', icon('next', 15));
          item.options.forEach(function (o, k) {
            var b = h('button', { class: 'nw-opt', onclick: function () {
              if (locked) return; locked = true;
              var right = k === item.answer;
              b.classList.add(right ? 'ok' : 'no'); if (!right) { opts.children[item.answer].classList.add('ok'); wrong.push(item); } else score++;
              if (item.explain) { why.textContent = (right ? 'Correct. ' : 'Not quite. ') + item.explain; why.hidden = false; }
              nextBtn.hidden = false; nextBtn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            } }, String.fromCharCode(65 + k) + '.  ' + o);
            opts.appendChild(b);
          });
          clear(box).appendChild(h('div', { class: 'nw-step' }, h('div', { class: 'nw-qhead' }, h('span', {}, q.subject + ' • ' + q.topic), h('b', {}, (i + 1) + '/' + q.questions.length)),
            h('div', { class: 'nw-prog' }, q.questions.map(function (_, k) { return h('i', { class: k <= i ? 'on' : '' }); })), h('h3', { class: 'nw-q' }, item.q), opts, why, nextBtn));
        }
        function end() {
          var pct = Math.round(score / q.questions.length * 100), circ = 2 * Math.PI * 52;
          var ring = h('div', { class: 'nw-ring' }); ring.innerHTML = '<svg width="120" height="120" viewBox="0 0 120 120"><circle class="bg" cx="60" cy="60" r="52"/><circle class="fg" cx="60" cy="60" r="52" stroke-dasharray="' + circ + '" stroke-dashoffset="' + circ + '"/></svg>';
          ring.appendChild(h('b', {}, score + '/' + q.questions.length));
          setTimeout(function () { ring.querySelector('.fg').setAttribute('stroke-dashoffset', circ * (1 - pct / 100)); }, 100);
          if (pct >= 80) confetti();
          clear(box).appendChild(h('div', { class: 'nw-step nw-score' }, ring, h('h3', { class: 'nw-q' }, pct >= 80 ? 'Excellent work' : pct >= 50 ? 'Good effort' : 'Keep practising'), h('p', { class: 'nw-hint' }, pct >= 80 ? 'You know this topic well.' : 'Review the ones you missed and try again.'),
            wrong.length ? h('div', { style: 'text-align:left' }, h('div', { class: 'nw-sec' }, 'To review'), wrong.map(function (w) { return h('div', { class: 'nw-card', style: 'margin-bottom:8px' }, h('b', {}, w.q), h('div', { style: 'color:var(--ok);margin-top:4px' }, 'Answer: ' + w.options[w.answer]), w.explain ? h('small', { style: 'color:var(--muted)' }, w.explain) : null); })) : null,
            h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { runQuiz(q); } }, icon('refresh', 15), 'Retry'), h('button', { class: 'nw-btn ghost', onclick: function () { clear(pane); studyForm('quiz'); } }, 'New quiz'))));
        }
        ask();
      }

      function runCards(deck) {
        var i = 0, known = 0, box = h('div'); clear(pane).appendChild(box);
        function show() {
          if (i >= deck.cards.length) return summary();
          var c = deck.cards[i];
          var card = h('div', { class: 'nw-fc', tabindex: '0', role: 'button', 'aria-label': 'Flip card', onclick: function () { card.classList.toggle('flip'); }, onkeydown: function (e) { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); card.classList.toggle('flip'); } } },
            h('div', {}, h('div', { class: 'f' }, c.front, h('small', {}, 'Tap to flip')), h('div', { class: 'b' }, c.back)));
          clear(box).appendChild(h('div', { class: 'nw-step' }, h('div', { class: 'nw-qhead' }, h('span', {}, deck.subject + ' • ' + deck.topic), h('b', {}, (i + 1) + '/' + deck.cards.length)), card,
            h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn ghost', onclick: function () { deck.cards.push(c); i++; show(); } }, 'Again later'), h('button', { class: 'nw-btn', onclick: function () { known++; i++; show(); } }, icon('check', 15), 'Got it'))));
        }
        function summary() {
          confetti();
          clear(box).appendChild(h('div', { class: 'nw-step nw-score' }, h('h3', { class: 'nw-q' }, 'Deck complete'), h('p', { class: 'nw-hint' }, 'You marked ' + known + ' cards as known.'), h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { clear(pane); studyForm('cards'); } }, 'New deck'))));
        }
        show();
      }

      function tutor() {
        put(pane, h('div', { class: 'nw-card' }, h('h4', {}, icon('book', 15), 'Study helper chat'), h('p', { style: 'margin:0 0 10px;color:var(--muted)' }, 'Ask for an idea to be explained step by step, with an example and a quick check. It stays on school subjects and never replaces your teacher.'),
          h('button', { class: 'nw-btn block', onclick: function () { closePanel(); setMode('study'); $.input.focus(); } }, icon('chat', 15), 'Open the study helper')));
      }
    };

    /* ============================================================================================
     * 18. Staff panel (feature 3 inbox + analytics, leads, codes, events, timetable)
     * ========================================================================================== */
    PANELS.staff = function (ctx) {
      var tab = 'overview', pane = h('div'), tabs = h('div', { class: 'nw-tabs', style: 'overflow-x:auto' });
      if (!S.staff) return login();
      clear(ctx.right).appendChild(h('button', { class: 'nw-pb', title: 'Sign out', 'aria-label': 'Sign out', onclick: function () { S.staff = null; SS.del('noah_staff'); PANELS.staff(ctx); } }, icon('logout', 16)));
      put(clear(ctx.body), h('div', { class: 'nw-step' }, h('h3', { class: 'nw-q' }, 'Staff panel'), tabs, pane));
      draw();
      function draw() {
        clear(tabs);
        [['overview', 'Overview'], ['inbox', 'Inbox'], ['leads', 'Leads'], ['codes', 'Codes'], ['events', 'Events'], ['timetable', 'Timetable']].forEach(function (t) { tabs.appendChild(h('button', { class: tab === t[0] ? 'on' : '', style: 'flex:none;padding:8px 12px', onclick: function () { tab = t[0]; draw(); } }, t[1])); });
        clear(pane); loading(pane, 3);
        ({ overview: overview, inbox: inbox, leads: leads, codes: codes, events: events, timetable: timetable })[tab]();
      }
      function get(path, cb) { api(path, { staff: true }).then(function (r) { if (!ctx.alive()) return; if (r.status === 401) { toast('Please sign in again'); return PANELS.staff(ctx); } if (!r.ok) return failure({ body: pane }, r.data.error, draw); cb(r.data); }); }
      function mutate(method, path, body, done) { api(path, { method: method, body: body, staff: true }).then(function (r) { if (r.status === 401) return PANELS.staff(ctx); if (!r.ok) return toast(r.data.error || 'Failed'); if (done) done(r.data); }); }

      function login() {
        clear(ctx.right);
        var pw = h('input', { class: 'nw-f', type: 'password', autocomplete: 'current-password', placeholder: 'Staff password' });
        var err = h('div', { class: 'nw-err', style: 'margin-top:6px' });
        var form = h('form', { class: 'nw-step', onsubmit: function (e) {
          e.preventDefault(); err.textContent = '';
          api('/api/staff/login', { body: { password: pw.value } }).then(function (r) { if (!r.ok) { err.textContent = r.data.error || T('offline'); return; } S.staff = { token: r.data.token }; SS.set('noah_staff', JSON.stringify(S.staff)); PANELS.staff(ctx); });
        } }, h('h3', { class: 'nw-q' }, 'Staff sign in'), h('p', { class: 'nw-hint' }, 'For college staff only: unanswered questions, leads, student codes, events and analytics.'), pw, err, h('button', { class: 'nw-btn block', style: 'margin-top:12px', type: 'submit' }, icon('key', 15), 'Sign in'));
        clear(ctx.body).appendChild(form); pw.focus();
      }

      function bars(values, labelFn) {
        var max = Math.max.apply(null, values.concat([1]));
        var c = h('div', { class: 'nw-chart' }, values.map(function (v, i) { return h('i', { title: labelFn(i) + ': ' + v }); }));
        setTimeout(function () { Array.prototype.forEach.call(c.children, function (el, i) { el.style.height = Math.max(2, values[i] / max * 100) + '%'; }); }, 60);
        return c;
      }
      function overview() {
        get('/api/staff/overview?days=30', function (d) {
          var a = d.analytics, up = a.thumbs_up, dn = a.thumbs_down;
          var byDay = {}; a.per_day.forEach(function (x) { byDay[x.d] = x.n; });
          var days = []; for (var i = 29; i >= 0; i--) { var dt = new Date(Date.now() - i * 86400000); days.push(dt.toISOString().slice(0, 10)); }
          var hours = []; for (var k = 0; k < 24; k++) hours.push(0); a.per_hour.forEach(function (x) { if (x.h >= 0 && x.h < 24) hours[x.h] = x.n; });
          var total = a.engines.reduce(function (s, e) { return s + e.n; }, 0) || 1, acc = 0, pal = { gemini: '#1746d1', qwen: '#f59e0b', rules: '#0f9d63', cache: '#7c3aed', staff: '#e0148c', none: '#d92d20' };
          var stops = a.engines.map(function (e) { var from = acc / total * 360; acc += e.n; return (pal[e.engine] || '#999') + ' ' + from + 'deg ' + (acc / total * 360) + 'deg'; }).join(',');
          var l = d.llm;
          put(clear(pane), 
            h('div', { class: 'nw-stats' }, stat(a.questions, 'Questions'), stat(a.sessions, 'Visitors'), stat(a.new_leads, 'New leads'), stat(a.unanswered_open, 'Unanswered'), stat(up + '/' + dn, 'Thumbs up/down'), stat(a.private_chats, 'Private chats')),
            h('div', { class: 'nw-sec' }, 'Questions per day (30 days)'), bars(days.map(function (x) { return byDay[x] || 0; }), function (i) { return days[i]; }),
            h('div', { class: 'nw-sec' }, 'Busiest hours (IST)'), bars(hours, function (i) { return i + ':00'; }),
            h('div', { class: 'nw-sec' }, 'Top questions'), a.top_questions.length ? h('div', { class: 'nw-card' }, a.top_questions.map(function (q) { return h('div', { class: 'nw-kv' }, h('span', { style: 'width:34px;font-weight:700' }, q.n + 'x'), h('b', {}, q.norm)); })) : h('div', { class: 'nw-note' }, 'No questions yet.'),
            h('div', { class: 'nw-sec' }, 'Answered by'), h('div', { class: 'nw-card', style: 'display:flex;gap:14px;align-items:center' }, h('div', { class: 'nw-donut', style: 'background:conic-gradient(' + (stops || '#ddd 0deg 360deg') + ')' }), h('div', {}, a.engines.map(function (e) { return h('div', {}, h('span', { style: 'display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:' + (pal[e.engine] || '#999') }), (e.engine || 'unknown') + ': ' + e.n); }))),
            h('div', { class: 'nw-sec' }, 'Pages with most questions'), a.top_pages.length ? h('div', { class: 'nw-card' }, a.top_pages.map(function (p) { return h('div', { class: 'nw-kv' }, h('span', { style: 'width:34px;font-weight:700' }, p.n), h('b', { style: 'font-size:12px' }, p.page.replace(/^https?:\/\/[^/]+/, '') || '/')); })) : h('div', { class: 'nw-note' }, 'No page data yet.'),
            h('div', { class: 'nw-sec' }, 'Languages'), h('div', { class: 'nw-pills' }, a.languages.map(function (x) { return h('span', { class: 'nw-pill' }, (x.lang || '?') + ' ' + x.n); })),
            h('div', { class: 'nw-sec' }, 'System'), h('div', { class: 'nw-card' },
              kv('Main model', l.gemini.configured ? l.gemini.model + (l.gemini.breaker.open_for_s ? ' (paused ' + l.gemini.breaker.open_for_s + 's after errors)' : '') : 'NOT CONFIGURED - set GEMINI_API_KEY'),
              kv('Backup model', l.qwen.enabled ? 'Qwen' + (l.qwen.breaker.open_for_s ? ' (paused)' : '') : 'off'), kv('Last Gemini error', l.gemini.breaker.last_error || 'none'),
              kv('Email alerts', d.notifications.email ? 'on' : 'off'), kv('Webhook', d.notifications.webhook ? 'on' : 'off'), kv('WhatsApp', d.notifications.whatsapp ? 'on' : 'off'), kv('Chat log kept', d.retention_days + ' days'), kv('Widget file version', VERSION)),
            h('button', { class: 'nw-btn ghost block', style: 'margin-top:12px', onclick: function () { mutate('POST', '/api/staff/purge', {}, function (r) { toast('Removed ' + r.removed + ' old rows'); }); } }, icon('trash', 15), 'Delete chat logs older than the retention period'));
        });
      }
      function stat(n, label) { return h('div', { class: 'nw-stat' }, h('b', {}, n), h('small', {}, label)); }
      function kv(k, v) { return h('div', { class: 'nw-kv' }, h('span', {}, k), h('b', {}, v)); }

      function inbox() {
        get('/api/staff/unanswered', function (d) {
          var box = h('div');
          box.appendChild(h('div', { class: 'nw-sec', style: 'margin-top:0' }, 'Open questions (' + d.open.length + ')'));
          if (!d.open.length) box.appendChild(h('div', { class: 'nw-note' }, 'Nothing waiting. Questions Noah could not answer, and replies visitors marked unhelpful, appear here.'));
          d.open.forEach(function (u) {
            var ans = h('textarea', { class: 'nw-f', placeholder: 'Write the answer Noah should give from now on', maxlength: '1200' });
            box.appendChild(h('div', { class: 'nw-lead' }, h('header', {}, h('b', {}, u.question), h('span', { class: 'nw-pill brand' }, u.count + 'x')), h('small', { style: 'color:var(--muted)' }, 'Reason: ' + u.reason), ans,
              h('div', { class: 'nw-row2', style: 'margin-top:8px' }, h('button', { class: 'nw-btn sm', onclick: function () { mutate('POST', '/api/staff/unanswered/' + u.id + '/answer', { answer: ans.value }, function () { toast('Saved. Noah will use this answer.'); draw(); }); } }, 'Save answer'), h('button', { class: 'nw-btn ghost sm', onclick: function () { mutate('POST', '/api/staff/unanswered/' + u.id + '/dismiss', {}, draw); } }, 'Dismiss'))));
          });
          if (d.disliked.length) {
            box.appendChild(h('div', { class: 'nw-sec' }, 'Replies marked unhelpful'));
            d.disliked.slice(0, 15).forEach(function (x) { box.appendChild(h('div', { class: 'nw-lead' }, h('b', {}, x.question || '(question not stored)'), h('div', { style: 'color:var(--muted);font-size:12.5px;margin-top:4px' }, 'Noah said: ' + (x.answer || '').slice(0, 220)), x.comment ? h('div', { style: 'font-size:12.5px;margin-top:4px' }, 'Visitor: ' + x.comment) : null)); });
          }
          box.appendChild(h('div', { class: 'nw-sec' }, 'Teach Noah something new'));
          var q = h('input', { class: 'nw-f', placeholder: 'Question', maxlength: '300' }), a = h('textarea', { class: 'nw-f', placeholder: 'Answer', maxlength: '1200' });
          box.appendChild(h('div', { class: 'nw-lead' }, q, h('div', { style: 'height:8px' }), a, h('button', { class: 'nw-btn sm', style: 'margin-top:8px', onclick: function () { mutate('POST', '/api/staff/learned', { question: q.value, answer: a.value }, function () { toast('Added'); draw(); }); } }, 'Add')));
          box.appendChild(h('div', { class: 'nw-sec' }, 'Staff-taught answers (' + d.learned.length + ')'));
          d.learned.forEach(function (x) { box.appendChild(h('div', { class: 'nw-lead' }, h('header', {}, h('b', {}, x.question), h('button', { class: 'nw-pb', 'aria-label': 'Delete', onclick: function () { mutate('DELETE', '/api/staff/learned/' + x.id, undefined, draw); } }, icon('trash', 15))), h('div', { style: 'font-size:12.5px;color:var(--muted)' }, x.answer))); });
          clear(pane).appendChild(box);
        });
      }

      function leads() {
        var kind = '', status = '';
        var fk = h('select', { class: 'nw-f', style: 'min-height:36px;padding:6px 8px' }, [['', 'All kinds'], ['callback', 'Callbacks'], ['visit', 'Visits'], ['counselling', 'Counselling']].map(function (o) { return h('option', { value: o[0] }, o[1]); }));
        var fs = h('select', { class: 'nw-f', style: 'min-height:36px;padding:6px 8px' }, [['', 'Any status'], ['new', 'New'], ['contacted', 'Contacted'], ['done', 'Done'], ['cancelled', 'Cancelled']].map(function (o) { return h('option', { value: o[0] }, o[1]); }));
        var list = h('div');
        fk.onchange = function () { kind = fk.value; load(); }; fs.onchange = function () { status = fs.value; load(); };
        put(clear(pane), h('div', { class: 'nw-row2', style: 'margin:0 0 10px' }, fk, fs, h('button', { class: 'nw-btn ghost sm', onclick: exportCsv }, icon('download', 14), 'CSV')), list);
        function exportCsv() {
          fetch(BASE + '/api/staff/leads.csv', { headers: { Authorization: 'Bearer ' + S.staff.token } }).then(function (r) { if (!r.ok) throw new Error(); return r.text(); }).then(function (t) { downloadFile('noah-leads.csv', t, 'text/csv'); }).catch(function () { toast('Export failed'); });
        }
        function load() {
          loading(list, 2);
          api('/api/staff/leads?kind=' + kind + '&status=' + status, { staff: true }).then(function (r) {
            if (!ctx.alive()) return; if (r.status === 401) return PANELS.staff(ctx);
            clear(list);
            if (!r.data.leads.length) return list.appendChild(h('div', { class: 'nw-note' }, 'No requests yet.'));
            r.data.leads.forEach(function (x) {
              var st = h('select', { class: 'nw-f', style: 'min-height:32px;padding:4px 6px;width:auto' }, ['new', 'contacted', 'done', 'cancelled'].map(function (s) { return h('option', { value: s, selected: s === x.status ? true : null }, s); }));
              st.onchange = function () { mutate('PATCH', '/api/staff/leads/' + x.id, { status: st.value }, function () { toast('Updated'); }); };
              var nt = h('input', { class: 'nw-f', style: 'min-height:34px;padding:6px 10px;margin-top:6px', placeholder: 'Staff note', value: x.staff_note || '', maxlength: '500' });
              nt.onchange = function () { mutate('PATCH', '/api/staff/leads/' + x.id, { staff_note: nt.value }, function () { toast('Note saved'); }); };
              list.appendChild(h('div', { class: 'nw-lead' }, h('header', {}, h('b', {}, x.name + ' '), h('span', { class: 'nw-pill brand' }, x.kind), st),
                h('div', {}, h('a', { href: 'tel:' + x.phone }, x.phone), x.email ? [' • ', h('a', { href: 'mailto:' + x.email }, x.email)] : null),
                h('small', { style: 'color:var(--muted)' }, [x.role, x.board, x.interest, x.slot_date ? 'Visit ' + x.slot_date + ' ' + x.slot_time : '', x.pref_time ? 'Call ' + x.pref_time : '', (x.ts || '').slice(0, 16).replace('T', ' ')].filter(Boolean).join(' • ')), x.note ? h('div', { style: 'font-size:12.5px;margin-top:4px' }, x.note) : null, nt));
            });
          });
        }
        load();
      }

      function codes() {
        var label = h('input', { class: 'nw-f', placeholder: 'Label, e.g. II PUC PCMB 2026-27', maxlength: '80' }), course = h('input', { class: 'nw-f', placeholder: 'Class (optional)', maxlength: '40' }), days = h('input', { class: 'nw-f', type: 'number', value: '365', min: '1', max: '730' });
        var out = h('div'), listBox = h('div');
        function drawList() {
          api('/api/staff/student-codes', { staff: true }).then(function (r) {
            if (!ctx.alive()) return; if (r.status === 401) return PANELS.staff(ctx);
            clear(listBox);
            (r.data.codes || []).forEach(function (c) {
              listBox.appendChild(h('div', { class: 'nw-lead' }, h('header', {}, h('b', {}, c.label), h('span', { class: 'nw-pill ' + (c.active ? 'ok' : 'bad') }, c.active ? 'active' : 'revoked')),
                h('small', { style: 'color:var(--muted)' }, 'ends ...' + c.hint + ' • used ' + c.uses + 'x • expires ' + (c.expires_ts || 'never').slice(0, 10)),
                c.active ? h('div', { style: 'margin-top:6px' }, h('button', { class: 'nw-btn danger sm', onclick: function () { mutate('DELETE', '/api/staff/student-codes/' + c.id, undefined, drawList); } }, 'Revoke')) : null));
            });
            if (!(r.data.codes || []).length) listBox.appendChild(h('div', { class: 'nw-note' }, 'No codes yet.'));
          });
        }
        var create = h('button', { class: 'nw-btn block', onclick: function () {
          mutate('POST', '/api/staff/student-codes', { label: label.value, course: course.value, days: +days.value }, function (r) {
            put(clear(out), h('div', { class: 'nw-code-box' }, r.code), h('div', { class: 'nw-note' }, r.note), h('button', { class: 'nw-btn ghost sm', onclick: function () { copyText(r.code).then(function () { toast('Copied'); }); } }, icon('copy', 14), 'Copy'));
            drawList();
          });
        } }, icon('key', 15), 'Create access code');
        clear(pane).appendChild(h('div', {}, h('div', { class: 'nw-lead' }, field('Label', label), field('Class', course), field('Valid for (days)', days), create), out, h('div', { class: 'nw-sec' }, 'Issued codes'), listBox));
        drawList();
      }

      function events() {
        get('/api/staff/events', function (d) {
          var box = h('div'), form = h('div', { class: 'nw-lead' });
          function editor(e) {
            e = e || { active: 1, sort: 50, link_label: 'More details', tag: '' };
            var f = {};
            function inp(name, ph, type) { f[name] = h('input', { class: 'nw-f', type: type || 'text', placeholder: ph || '', value: e[name] || '' }); return f[name]; }
            var sd = (e.starts || '').split('T'), ed = (e.ends || '').split('T');
            f.sdate = h('input', { class: 'nw-f', type: 'date', value: sd[0] || '' }); f.stime = h('input', { class: 'nw-f', type: 'time', value: sd[1] || '' }); f.edate = h('input', { class: 'nw-f', type: 'date', value: ed[0] || '' });
            f.tag = h('select', { class: 'nw-f' }, ['', 'conference', 'admission', 'fest', 'sports', 'celebration'].map(function (t) { return h('option', { value: t, selected: t === (e.tag || '') ? true : null }, t || 'no tag'); }));
            f.active = h('input', { type: 'checkbox', checked: e.active ? true : null });
            f.over = h('input', { type: 'checkbox', checked: e.over ? true : null });
            put(clear(form), h('b', {}, e.id ? 'Edit ' + e.title : 'Add an event'), h('div', { style: 'height:8px' }), field('Title', inp('title', 'Title')), field('Description', inp('blurb', 'One or two sentences')),
              h('div', { class: 'nw-row2', style: 'margin:0' }, field('Starts', f.sdate), field('Time (optional)', f.stime), field('Ends', f.edate)), field('Where', inp('location', 'Location')), field('Link label', inp('link_label', 'Register')), field('Link (https://)', inp('link_url', 'https://')), field('Contact', inp('contact', 'Email or phone')), field('Tag', f.tag),
              h('label', { class: 'nw-check' }, f.active, h('span', {}, 'Visible to visitors')),
              h('label', { class: 'nw-check' }, f.over, h('span', {}, 'This year’s edition is over')),
              h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () {
                var body = { id: e.id, title: f.title.value, blurb: f.blurb.value, starts: f.sdate.value ? f.sdate.value + (f.stime.value ? 'T' + f.stime.value : '') : '', ends: f.edate.value, location: f.location.value, link_label: f.link_label.value, link_url: f.link_url.value, contact: f.contact.value, tag: f.tag.value, active: f.active.checked, over: f.over.checked, sort: e.sort || 50 };
                mutate('POST', '/api/staff/events', body, function () { toast('Saved'); draw(); });
              } }, 'Save event'), e.id ? h('button', { class: 'nw-btn ghost', onclick: function () { editor(null); } }, 'New event') : null));
          }
          editor(null); box.appendChild(form); box.appendChild(h('div', { class: 'nw-sec' }, 'Events'));
          d.events.forEach(function (e) { box.appendChild(h('div', { class: 'nw-lead' }, h('header', {}, h('b', {}, e.title), h('span', { class: 'nw-pill ' + (e.active ? 'ok' : '') }, e.status === 'dates_tba' ? 'no dates' : e.status)), h('small', { style: 'color:var(--muted)' }, e.starts || 'dates not set'),
            h('div', { class: 'nw-row2', style: 'margin-top:8px' }, h('button', { class: 'nw-btn ghost sm', onclick: function () { editor(e); form.scrollIntoView({ behavior: 'smooth' }); } }, 'Edit'), h('button', { class: 'nw-btn danger sm', onclick: function () { if (confirm('Delete ' + e.title + '?')) mutate('DELETE', '/api/staff/events/' + encodeURIComponent(e.id), undefined, draw); } }, 'Delete')))); });
          clear(pane).appendChild(box);
        });
      }

      function timetable() {
        get('/api/staff/timetable', function (d) {
          var ta = h('textarea', { class: 'nw-f', style: 'min-height:260px;font-family:ui-monospace,Consolas,monospace;font-size:12px' }); ta.value = JSON.stringify(d.timetable, null, 2);
          put(clear(pane), h('div', { class: 'nw-note' }, 'Students see this in the Student Zone and Noah answers exam questions from it. Currently: ' + (d.custom ? 'your custom timetable' : 'the bundled default') + '. Dates look like 28.09.2026.'), ta,
            h('div', { class: 'nw-row2' }, h('button', { class: 'nw-btn', onclick: function () { var obj; try { obj = JSON.parse(ta.value); } catch (e) { return toast('That is not valid JSON'); } mutate('PUT', '/api/staff/timetable', { timetable: obj }, function () { toast('Timetable saved'); draw(); }); } }, 'Save timetable'),
              d.custom ? h('button', { class: 'nw-btn ghost', onclick: function () { mutate('DELETE', '/api/staff/timetable', undefined, function () { toast('Reset to default'); draw(); }); } }, 'Reset to default') : null));
        });
      }
    };

    /* ============================================================================================
     * 19. Start-up
     * ========================================================================================== */
    setTheme(S.theme);
    if (window.matchMedia) { try { matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () { if (S.theme === 'auto') setTheme('auto'); }); } catch (e) { /* old Safari */ } }
    setLang(S.lang, true);
    setMode('chat', true);
    api('/api/context?url=' + encodeURIComponent(location.href)).then(function (r) {
      if (!r.ok) return;
      S.ctx = r.data;
      if (r.data.greeting) $.teaser.firstChild.textContent = r.data.greeting;
      if (S.open && !welcomed) ensureWelcome();
    });
    if (SS.get('noah_open') === '1') open();
    else if (!SS.get('noah_teaser')) setTimeout(function () { if (!S.open && !SS.get('noah_teaser')) $.teaser.hidden = false; }, 6000);
    if (/[#?&]noah=staff/.test(location.href)) setTimeout(function () { openPanel('staff'); }, 500);

    var publicApi = {
      version: VERSION, baseUrl: BASE, sessionId: S.sid,
      open: open, close: close, toggle: toggle,
      send: function (msg) { open(); send(msg); },
      openPanel: function (id, args) { open(); openPanel(id, args); },
      openStaff: function () { open(); openPanel('staff'); },
      setLanguage: function (c) { setLang(c); }
    };
    window.NOAH_WIDGET = publicApi;
    window.VERONICA_WIDGET = publicApi;      // name used by the previous widget; kept so any page code keeps working
    console.log('[NOAH] widget ready, version ' + VERSION);
  }
})();

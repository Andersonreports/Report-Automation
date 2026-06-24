// Session-based idle logout — per IT's requirement: if the page sits idle
// for 30 minutes, clear the session and send the user back to login.
// Activity timestamp lives in localStorage so it's shared across tabs —
// being active in one tab keeps the whole session alive, not just that tab.
(function () {
  var IDLE_LIMIT_MS = 30 * 60 * 1000;
  var CHECK_INTERVAL_MS = 15 * 1000;
  var ACTIVITY_KEY = 'arc_last_activity';
  var WRITE_THROTTLE_MS = 5 * 1000;

  if (localStorage.getItem('arc_authenticated') !== 'true') return;

  var lastWrite = 0;

  function recordActivity() {
    var now = Date.now();
    if (now - lastWrite < WRITE_THROTTLE_MS) return;
    lastWrite = now;
    localStorage.setItem(ACTIVITY_KEY, String(now));
  }

  function logout() {
    localStorage.removeItem('arc_authenticated');
    localStorage.removeItem('arc_access_control');
    localStorage.removeItem('arc_mobile_number');
    localStorage.removeItem('arc_name');
    localStorage.removeItem('arc_role');
    localStorage.removeItem('arc_report');
    localStorage.removeItem(ACTIVITY_KEY);
    window.location.replace('/login.html');
  }

  function checkIdle() {
    var last = parseInt(localStorage.getItem(ACTIVITY_KEY), 10) || Date.now();
    if (Date.now() - last >= IDLE_LIMIT_MS) logout();
  }

  recordActivity();
  ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click'].forEach(function (evt) {
    window.addEventListener(evt, recordActivity, { passive: true });
  });
  setInterval(checkIdle, CHECK_INTERVAL_MS);
})();

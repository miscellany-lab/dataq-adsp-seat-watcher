const steps = [
  { key: 'welcome', title: '처음 설정', template: 'welcomeScreen' },
  { key: 'telegram', title: '선택 알림 설정', template: 'telegramScreen' },
  { key: 'browser', title: 'DataQ 팝업 준비', template: 'browserScreen' },
  { key: 'settings', title: '감시 설정', template: 'settingsScreen' },
  { key: 'run', title: '실행', template: 'runScreen' },
];

const state = {
  index: 0,
  config: {},
  telegramOk: false,
  log: '',
  events: [],
  results: [],
};

const $ = (selector) => document.querySelector(selector);

function bridgeReady() {
  return window.pywebview && window.pywebview.api;
}

async function callApi(name, payload) {
  if (!bridgeReady()) {
    return { ok: false, message: '앱 브리지가 아직 준비되지 않았습니다.' };
  }
  if (payload === undefined) {
    return window.pywebview.api[name]();
  }
  return window.pywebview.api[name](payload);
}

function renderSteps() {
  const nav = $('#steps');
  nav.innerHTML = '';
  steps.forEach((step, index) => {
    const item = document.createElement('div');
    item.className = `step ${index === state.index ? 'active' : ''} ${index < state.index ? 'done' : ''}`;
    item.innerHTML = `<b>${index + 1}</b><span>${step.title}</span>`;
    nav.appendChild(item);
  });
}

function render() {
  const step = steps[state.index];
  $('#pageTitle').textContent = step.title;
  renderSteps();

  const template = document.getElementById(step.template);
  const screen = $('#screen');
  screen.innerHTML = '';
  screen.appendChild(template.content.cloneNode(true));
  wireScreen(step.key);
  hydrateFields();
}

function wireScreen(key) {
  document.querySelectorAll('[data-next]').forEach((button) => {
    button.addEventListener('click', () => {
      collectFields();
      state.index = Math.min(state.index + 1, steps.length - 1);
      render();
    });
  });

  document.querySelectorAll('[data-prev]').forEach((button) => {
    button.addEventListener('click', () => {
      collectFields();
      state.index = Math.max(state.index - 1, 0);
      render();
    });
  });

  if (key === 'telegram') {
    $('#telegramTest').addEventListener('click', async () => {
      collectFields();
      const result = await callApi('test_telegram', state.config);
      state.telegramOk = Boolean(result.ok);
      $('#telegramHint').textContent = result.message;
      toast(result.message);
    });
  }

  if (key === 'browser') {
    $('#openDataq').addEventListener('click', async () => {
      const result = await callApi('open_dataq');
      toast(result.message);
    });
  }

  if (key === 'run') {
    $('#startWatcher').addEventListener('click', startWatcher);
    $('#stopWatcher').addEventListener('click', stopWatcher);
    $('#copyLog').addEventListener('click', async () => {
      await navigator.clipboard.writeText(state.log || '');
      toast('로그를 클립보드에 복사했습니다.');
    });
    renderResults();
  }
}

function hydrateFields() {
  const map = [
    ['telegramToken', 'telegram_token'],
    ['telegramChatId', 'telegram_chat_id'],
    ['interval', 'interval'],
    ['pages', 'pages'],
    ['wheelNotches', 'wheel_notches'],
    ['focusClick', 'focus_click'],
  ];
  map.forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el) el.value = state.config[key] ?? '';
  });

  const checks = [
    ['refresh', 'refresh'],
    ['confirmResubmit', 'confirm_resubmit'],
    ['keepAwake', 'keep_awake'],
    ['clipboardAssist', 'clipboard_assist'],
  ];
  checks.forEach(([id, key]) => {
    const el = document.getElementById(id);
    if (el) el.checked = Boolean(state.config[key]);
  });
}

function collectFields() {
  const values = {
    telegram_token: $('#telegramToken')?.value?.trim() ?? state.config.telegram_token,
    telegram_chat_id: $('#telegramChatId')?.value?.trim() ?? state.config.telegram_chat_id,
    interval: Number($('#interval')?.value ?? state.config.interval),
    pages: Number($('#pages')?.value ?? state.config.pages),
    wheel_notches: Number($('#wheelNotches')?.value ?? state.config.wheel_notches),
    focus_click: $('#focusClick')?.value ?? state.config.focus_click,
    refresh: $('#refresh')?.checked ?? state.config.refresh,
    confirm_resubmit: $('#confirmResubmit')?.checked ?? state.config.confirm_resubmit,
    keep_awake: $('#keepAwake')?.checked ?? state.config.keep_awake,
    clipboard_assist: $('#clipboardAssist')?.checked ?? state.config.clipboard_assist,
  };
  state.config = { ...state.config, ...values };
}

async function startWatcher() {
  collectFields();
  const result = await callApi('start_watcher', state.config);
  toast(result.message);
  if (result.ok) {
    setRunning(true);
  }
}

async function stopWatcher() {
  const result = await callApi('stop_watcher');
  toast(result.message);
  setRunning(false);
}

function setRunning(running) {
  const badge = $('#runBadge');
  const start = $('#startWatcher');
  const stop = $('#stopWatcher');
  if (!badge || !start || !stop) return;
  badge.textContent = running ? '감시 중' : '대기 중';
  start.disabled = running;
  stop.disabled = !running;
  $('#metricState').textContent = running ? '실행 중' : '대기';
}

function renderResults() {
  const list = $('#resultList');
  if (!list) return;
  list.innerHTML = '';
  if ($('#metricResultCount')) $('#metricResultCount').textContent = `${state.results.length}건`;

  if (state.results.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-result';
    empty.innerHTML = '<strong>아직 감지된 잔여좌석이 없습니다.</strong><span>감시가 진행되면 고사장명, 지역, 좌석 수가 이곳에 정리됩니다.</span>';
    list.appendChild(empty);
    return;
  }

  state.results.slice().reverse().forEach((result) => {
    const item = document.createElement('article');
    item.className = 'seat-result';
    item.innerHTML = `
      <div class="seat-result-top">
        <span>No.${escapeHtml(result.no)}</span>
        <strong>${escapeHtml(result.seats)}석</strong>
      </div>
      <h4>${escapeHtml(result.site)}</h4>
      <p>${escapeHtml(result.address || '주소 정보 없음')}</p>
      <footer><span>${escapeHtml(result.region)}</span><span>${escapeHtml(result.time)}</span></footer>
    `;
    list.appendChild(item);
  });
}

async function poll() {
  if (!bridgeReady()) return;
  const result = await window.pywebview.api.poll();
  state.log = result.log || state.log;
  state.events.push(...(result.events || []));
  state.events = state.events.slice(-120);
  state.results = result.results || state.results;
  if ($('#metricStarted')) $('#metricStarted').textContent = result.startedAt || '-';
  setRunning(Boolean(result.running));
  renderResults();
}

function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove('show'), 2600);
}

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

$('#themeButton').addEventListener('click', () => {
  document.body.classList.toggle('dark');
  $('#themeButton').textContent = document.body.classList.contains('dark') ? '라이트 모드' : '다크 모드';
});

window.addEventListener('pywebviewready', async () => {
  state.config = await window.pywebview.api.get_default_config();
  render();
  setInterval(poll, 900);
});

setTimeout(() => {
  if (!bridgeReady()) {
    state.config = {
      interval: 40,
      pages: 15,
      wheel_notches: 9,
      focus_click: '900,500',
      refresh: true,
      confirm_resubmit: true,
      keep_awake: true,
      clipboard_assist: true,
    };
    render();
  }
}, 400);

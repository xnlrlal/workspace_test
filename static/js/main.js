/* 시그널 대시보드 — 차트 렌더링 & 데이터 로딩 */

const COLORS = {
  up: "#E1524B",
  down: "#3E7CB1",
  forecast: "#E3A83B",
  forecastFill: "rgba(227, 168, 59, 0.14)",
  smaFast: "#4FA98A",
  smaSlow: "#9C8FC2",
  ink: "#EDEAE2",
  inkDim: "#8B92A0",
  inkFaint: "#565D6B",
  line: "#262C36",
  panel: "#171B22",
};

const PLOTLY_BASE_LAYOUT = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: COLORS.inkDim, family: "JetBrains Mono, monospace", size: 11 },
  margin: { l: 48, r: 16, t: 8, b: 32 },
  xaxis: { gridcolor: COLORS.line, zerolinecolor: COLORS.line, showspikes: false },
  yaxis: { gridcolor: COLORS.line, zerolinecolor: COLORS.line },
  showlegend: false,
  hovermode: "x unified",
  // 드래그로 확대/축소하는 상호작용을 꺼서, 모바일에서 페이지를 스크롤하려고
  // 차트 위를 손가락으로 쓸어넘길 때 확대 제스처로 오인식되지 않게 한다.
  dragmode: false,
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true, scrollZoom: false };

const daysRange = document.getElementById("days-range");
const daysValue = document.getElementById("days-value");
const horizonRange = document.getElementById("horizon-range");
const horizonValue = document.getElementById("horizon-value");
const tickerInput = document.getElementById("ticker-input");
const searchForm = document.getElementById("search-form");
const statusBanner = document.getElementById("status-banner");
const watchlistChips = document.getElementById("watchlist-chips");
const watchlistStar = document.getElementById("watchlist-star");

daysRange.addEventListener("input", () => (daysValue.textContent = daysRange.value));
horizonRange.addEventListener("input", () => (horizonValue.textContent = horizonRange.value));

searchForm.addEventListener("submit", (e) => {
  e.preventDefault();
  loadStock();
});

daysRange.addEventListener("change", loadStock);
horizonRange.addEventListener("change", loadStock);

/* ---------- 워치리스트 (브라우저 로컬스토리지 저장) ---------- */

const WATCHLIST_KEY = "signal.watchlist";
const DEFAULT_WATCHLIST = [
  { ticker: "005930", name: "삼성전자" },
  { ticker: "000660", name: "SK하이닉스" },
  { ticker: "373220", name: "LG에너지솔루션" },
  { ticker: "AAPL", name: "Apple" },
  { ticker: "NVDA", name: "NVIDIA" },
  { ticker: "TSLA", name: "Tesla" },
];

function loadWatchlist() {
  try {
    const raw = localStorage.getItem(WATCHLIST_KEY);
    if (raw === null) return DEFAULT_WATCHLIST.slice();
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return DEFAULT_WATCHLIST.slice();
  }
}

function saveWatchlist(list) {
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
}

function isInWatchlist(ticker) {
  return loadWatchlist().some((item) => item.ticker === ticker);
}

function addToWatchlist(ticker, name) {
  const list = loadWatchlist();
  if (list.some((item) => item.ticker === ticker)) return;
  list.push({ ticker, name });
  saveWatchlist(list);
  renderWatchlist();
}

function removeFromWatchlist(ticker) {
  const list = loadWatchlist().filter((item) => item.ticker !== ticker);
  saveWatchlist(list);
  renderWatchlist();
  updateWatchlistStar(tickerInput.value.trim());
}

function renderWatchlist() {
  const list = loadWatchlist();
  watchlistChips.innerHTML = "";

  if (list.length === 0) {
    watchlistChips.innerHTML = '<p class="chips-empty">관심종목이 없습니다. ☆ 버튼으로 추가해보세요.</p>';
    return;
  }

  list.forEach((item) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.dataset.ticker = item.ticker;

    const label = document.createElement("span");
    label.textContent = `${item.ticker} · ${item.name}`;
    chip.appendChild(label);

    const remove = document.createElement("span");
    remove.className = "chip-remove";
    remove.textContent = "×";
    remove.title = "워치리스트에서 삭제";
    remove.addEventListener("click", (e) => {
      e.stopPropagation();
      removeFromWatchlist(item.ticker);
    });
    chip.appendChild(remove);

    chip.addEventListener("click", () => {
      tickerInput.value = item.ticker;
      loadStock();
    });

    watchlistChips.appendChild(chip);
  });
}

function updateWatchlistStar(ticker) {
  const active = isInWatchlist(ticker);
  watchlistStar.textContent = active ? "★" : "☆";
  watchlistStar.classList.toggle("active", active);
  watchlistStar.setAttribute("aria-pressed", String(active));
}

watchlistStar.addEventListener("click", () => {
  if (!currentStockData) return;
  const { ticker, name } = currentStockData;

  if (isInWatchlist(ticker)) {
    removeFromWatchlist(ticker);
  } else {
    addToWatchlist(ticker, name);
  }
  updateWatchlistStar(ticker);
});

function setStatus(msg, isError = false) {
  if (!msg) {
    statusBanner.classList.add("hidden");
    return;
  }
  statusBanner.textContent = msg;
  statusBanner.classList.remove("hidden");
  statusBanner.classList.toggle("error", isError);
}

async function loadStock() {
  const ticker = tickerInput.value.trim();
  if (!ticker) return;

  const days = daysRange.value;
  const horizon = horizonRange.value;

  setStatus(`${ticker} 데이터를 불러오는 중…`);
  document.getElementById("stock-name").textContent = "불러오는 중…";

  try {
    const res = await fetch(`/api/stock/${encodeURIComponent(ticker)}?days=${days}&horizon=${horizon}`);
    const data = await res.json();

    if (!res.ok) {
      setStatus(data.error || "데이터를 불러오지 못했습니다.", true);
      return;
    }

    setStatus("");
    renderHeader(data);
    renderPriceChart(data);
    renderRSI(data);
    renderMACD(data);
    renderAnalog(data);
  } catch (err) {
    setStatus(`요청 실패: ${err.message}`, true);
  }
}

let currentStockData = null;

function renderHeader(data) {
  currentStockData = { ticker: data.ticker, name: data.name };
  document.getElementById("stock-name").textContent = `${data.name} (${data.ticker})`;
  document.getElementById("market-badge").textContent = data.market === "KR" ? "국내" : "해외";
  document.getElementById("last-price").textContent = data.last_close.toLocaleString();

  const badge = document.getElementById("change-badge");
  const sign = data.change_pct >= 0 ? "+" : "";
  badge.textContent = `${sign}${data.change_pct}%`;
  badge.className = "change-badge " + (data.change_pct >= 0 ? "up" : "down");

  updateWatchlistStar(data.ticker);
}

function renderPriceChart(data) {
  const h = data.history;
  const f = data.forecast;

  const candlestick = {
    type: "candlestick",
    name: "가격",
    x: h.dates,
    open: h.open,
    high: h.high,
    low: h.low,
    close: h.close,
    increasing: { line: { color: COLORS.up }, fillcolor: COLORS.up },
    decreasing: { line: { color: COLORS.down }, fillcolor: COLORS.down },
  };

  const sma20 = {
    type: "scatter",
    mode: "lines",
    name: "SMA20",
    x: h.dates,
    y: h.sma20,
    line: { color: COLORS.smaFast, width: 1.4 },
  };

  const sma60 = {
    type: "scatter",
    mode: "lines",
    name: "SMA60",
    x: h.dates,
    y: h.sma60,
    line: { color: COLORS.smaSlow, width: 1.4 },
  };

  // 예측 팬: 마지막 실측 종가를 시작점으로 신뢰구간을 연결해 부드럽게 이어지도록 구성
  const lastDate = h.dates[h.dates.length - 1];
  const lastClose = h.close[h.close.length - 1];

  const fanX = [lastDate, ...f.dates, ...[...f.dates].reverse(), lastDate];
  const fanY = [lastClose, ...f.upper, ...[...f.lower].reverse(), lastClose];

  const forecastFan = {
    type: "scatter",
    mode: "none",
    name: "예측 구간 (80%)",
    x: fanX,
    y: fanY,
    fill: "toself",
    fillcolor: COLORS.forecastFill,
    line: { width: 0 },
    hoverinfo: "skip",
  };

  const forecastMean = {
    type: "scatter",
    mode: "lines",
    name: "예측 평균",
    x: [lastDate, ...f.dates],
    y: [lastClose, ...f.mean],
    line: { color: COLORS.forecast, width: 2, dash: "dot" },
  };

  const layout = {
    ...PLOTLY_BASE_LAYOUT,
    xaxis: { ...PLOTLY_BASE_LAYOUT.xaxis, rangeslider: { visible: false } },
    yaxis: { ...PLOTLY_BASE_LAYOUT.yaxis, title: "" },
    shapes: [
      {
        type: "line",
        x0: lastDate,
        x1: lastDate,
        y0: 0,
        y1: 1,
        yref: "paper",
        line: { color: COLORS.inkFaint, width: 1, dash: "dash" },
      },
    ],
    annotations: [
      {
        x: lastDate,
        y: 1,
        yref: "paper",
        text: "오늘",
        showarrow: false,
        yanchor: "bottom",
        font: { color: COLORS.inkFaint, size: 10 },
      },
    ],
  };

  Plotly.newPlot(
    "price-chart",
    [forecastFan, candlestick, sma20, sma60, forecastMean],
    layout,
    PLOTLY_CONFIG
  );
}

function renderRSI(data) {
  const h = data.history;
  const trace = {
    type: "scatter",
    mode: "lines",
    x: h.dates,
    y: h.rsi,
    line: { color: COLORS.forecast, width: 1.4 },
    fill: "tozeroy",
    fillcolor: "rgba(227, 168, 59, 0.06)",
  };

  const layout = {
    ...PLOTLY_BASE_LAYOUT,
    yaxis: { ...PLOTLY_BASE_LAYOUT.yaxis, range: [0, 100] },
    shapes: [
      { type: "line", x0: h.dates[0], x1: h.dates[h.dates.length - 1], y0: 70, y1: 70,
        line: { color: COLORS.up, width: 1, dash: "dot" } },
      { type: "line", x0: h.dates[0], x1: h.dates[h.dates.length - 1], y0: 30, y1: 30,
        line: { color: COLORS.down, width: 1, dash: "dot" } },
    ],
  };

  Plotly.newPlot("rsi-chart", [trace], layout, PLOTLY_CONFIG);
}

function renderMACD(data) {
  const h = data.history;

  const hist = h.macd.map((v, i) => (v === null || h.macd_signal[i] === null ? null : v - h.macd_signal[i]));
  const histColors = hist.map((v) => (v >= 0 ? COLORS.up : COLORS.down));

  const bar = {
    type: "bar",
    x: h.dates,
    y: hist,
    marker: { color: histColors },
    opacity: 0.55,
  };

  const macdLine = {
    type: "scatter",
    mode: "lines",
    x: h.dates,
    y: h.macd,
    line: { color: COLORS.smaSlow, width: 1.3 },
  };

  const signalLine = {
    type: "scatter",
    mode: "lines",
    x: h.dates,
    y: h.macd_signal,
    line: { color: COLORS.forecast, width: 1.3 },
  };

  Plotly.newPlot("macd-chart", [bar, macdLine, signalLine], PLOTLY_BASE_LAYOUT, PLOTLY_CONFIG);
}

function renderAnalog(data) {
  const a = data.analog;
  const subtitle = document.getElementById("analog-subtitle");
  const body = document.getElementById("analog-body");

  if (!a || !a.available) {
    subtitle.textContent = "";
    body.innerHTML = `<p class="analog-empty">${(a && a.reason) || "유사 패턴 데이터를 불러오지 못했습니다."}</p>`;
    return;
  }

  subtitle.textContent = `최근 ${a.window}거래일 패턴과 가장 비슷했던 과거 ${a.sample_size}개 구간 · 이후 ${a.forward}거래일 결과`;

  const fmtPct = (v) => `${v >= 0 ? "+" : ""}${v}%`;
  const returnClass = (v) => (v >= 0 ? "return-pos" : "return-neg");

  const stats = `
    <div class="analog-stats">
      <div class="analog-stat">
        <span class="analog-stat-value">${a.up_ratio_pct}%</span>
        <span class="analog-stat-label">상승 비율</span>
      </div>
      <div class="analog-stat">
        <span class="analog-stat-value ${returnClass(a.avg_return_pct)}">${fmtPct(a.avg_return_pct)}</span>
        <span class="analog-stat-label">평균 수익률</span>
      </div>
      <div class="analog-stat">
        <span class="analog-stat-value ${returnClass(a.median_return_pct)}">${fmtPct(a.median_return_pct)}</span>
        <span class="analog-stat-label">중간값 수익률</span>
      </div>
    </div>
  `;

  const rows = a.matches
    .map(
      (m) => `
      <tr>
        <td>${m.start_date} ~ ${m.end_date}</td>
        <td>${m.pattern_diff_pct}%p</td>
        <td class="${returnClass(m.forward_return_pct)}">${fmtPct(m.forward_return_pct)}</td>
      </tr>`
    )
    .join("");

  const table = `
    <table class="analog-table">
      <thead>
        <tr><th>구간</th><th>패턴 차이</th><th>이후 ${a.forward}거래일 수익률</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  body.innerHTML = stats + table;
}

// 초기 로드
renderWatchlist();
loadStock();

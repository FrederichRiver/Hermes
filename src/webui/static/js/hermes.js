/**
 * Hermes Quant Trading System — 前端 JavaScript
 * 纯原生 JS，无框架依赖
 * 通过 Fetch API 调用 Django REST Framework 后端
 */

const API_BASE = '/api/v1';

// ==========================================================================
// API 客户端
// ==========================================================================
async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) throw new Error(`API ${endpoint} failed: ${res.status}`);
  return res.json();
}

// ==========================================================================
// 时钟 & 日期
// ==========================================================================
function updateClock() {
  const now = new Date();
  const timeStr = now.toLocaleTimeString('zh-CN', { hour12: false });
  const dateOnly = now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
  const dateDisplay = document.getElementById('date-display');
  if (dateDisplay) dateDisplay.innerHTML = `${dateOnly} <span class="time-display">${timeStr}</span>`;
}

setInterval(updateClock, 1000);
updateClock();

// ==========================================================================
// 统计卡片
// ==========================================================================
async function loadStats() {
  try {
    const data = await apiGet('/dashboard/stats/');
    const container = document.getElementById('stat-cards');
    const items = [
      { key: 'total_asset', icon: 'wallet', title: '总资产' },
      { key: 'available_cash', icon: 'piggy', title: '可用资金' },
      { key: 'holding_pnl', icon: 'chart', title: '持仓盈亏' },
      { key: 'capital_utilization', icon: 'percent', title: '资金利用率' },
    ];

    container.innerHTML = items.map(item => {
      const stat = data[item.key];
      const typeClass = stat.change_type === 'up' ? 'up' : stat.change_type === 'down' ? 'down' : 'neutral';
      const arrow = stat.change_type === 'up' ? '↑' : stat.change_type === 'down' ? '↓' : '−';
      return `
        <div class="panel stat-card">
          <div class="flex items-center justify-between mb-3">
            <div class="stat-label">${item.title}</div>
            <div class="text-muted">${getIcon(item.icon)}</div>
          </div>
          <div class="stat-value">${stat.value}</div>
          <div class="stat-change ${typeClass}">
            <span>${arrow}</span>
            <span>${stat.change}</span>
            <span class="stat-subtitle">${stat.subtitle}</span>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('loadStats failed:', err);
  }
}

function getIcon(name) {
  const icons = {
    wallet: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M20 12V8H6a2 2 0 0 1 0-4h14v4"/><path d="M20 12v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6"/><path d="M16 16h.01"/></svg>',
    piggy: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><path d="M19 5c-1.5 0-2.8 1.4-3 2-3.5-1.5-11-.3-11 5 0 1.8 0 3 2 4.5V20h4v-2h3v2h4v-4c1-.5 1.7-1 2-2h2v-4h-2c0-1-.5-1.5-1-2h0V5z"/><path d="M2 9v1c0 1.1.9 2 2 2h1"/><path d="M16 11h0"/></svg>',
    chart: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    percent: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>',
  };
  return icons[name] || '';
}

// ==========================================================================
// 净值曲线图表 (Chart.js)
// ==========================================================================
let netValueChart = null;

async function loadNetValueChart() {
  try {
    const data = await apiGet('/netvalue/');
    const ctx = document.getElementById('netValueChart').getContext('2d');

    const labels = data.map(p => p.time);
    const values = data.map(p => parseFloat(p.value));
    const benchmarks = data.map(p => parseFloat(p.benchmark));

    if (netValueChart) netValueChart.destroy();

    netValueChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: '策略净值',
            data: values,
            borderColor: '#06b6d4',
            backgroundColor: 'rgba(6, 182, 212, 0.1)',
            borderWidth: 2,
            fill: true,
            tension: 0.4,
            pointRadius: 0,
            pointHoverRadius: 4,
          },
          {
            label: '基准指数',
            data: benchmarks,
            borderColor: '#64748b',
            borderWidth: 1.5,
            borderDash: [4, 4],
            fill: false,
            tension: 0.4,
            pointRadius: 0,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#111827',
            titleColor: '#94a3b8',
            bodyColor: '#e2e8f0',
            borderColor: '#1e293b',
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: '#1e293b', drawBorder: false },
            ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 11 } }
          },
          y: {
            grid: { color: '#1e293b', borderDash: [3, 3], drawBorder: false },
            ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 11 } }
          }
        }
      }
    });
  } catch (err) {
    console.error('loadNetValueChart failed:', err);
  }
}

// ==========================================================================
// 自选行情
// ==========================================================================
async function loadQuotes() {
  try {
    const quotes = await apiGet('/quotes/');
    const container = document.getElementById('quote-list');
    container.innerHTML = quotes.map(q => {
      const isUp = parseFloat(q.change) >= 0;
      const badgeClass = isUp ? 'up' : 'down';
      const arrow = isUp ? '↑' : '↓';
      return `
        <div class="quote-item">
          <div class="quote-left">
            <div>
              <div class="quote-name">${q.name}</div>
              <div class="quote-code">${q.symbol}</div>
            </div>
            ${q.has_alert ? '<div class="quote-alert"></div>' : ''}
          </div>
          <div class="quote-right">
            <div class="quote-price">
              <div class="quote-price-value">${parseFloat(q.price).toFixed(2)}</div>
              <div class="quote-price-volume">${q.volume}</div>
            </div>
            <div class="quote-badge ${badgeClass}">
              <span>${arrow}</span>
              <span>${parseFloat(q.change_pct) >= 0 ? '+' : ''}${parseFloat(q.change_pct).toFixed(2)}%</span>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('loadQuotes failed:', err);
  }
}

// ==========================================================================
// 持仓列表
// ==========================================================================
async function loadPositions() {
  try {
    const positions = await apiGet('/positions/');
    document.getElementById('position-count').textContent = `共 ${positions.length} 只标的`;
    const tbody = document.getElementById('position-tbody');
    tbody.innerHTML = positions.map(pos => {
      const pnl = parseFloat(pos.unrealized_pnl);
      const pnlPct = parseFloat(pos.unrealized_pnl_pct);
      const pnlClass = pnl >= 0 ? 'td-up' : 'td-down';
      const pnlSign = pnl >= 0 ? '+' : '';
      return `
        <tr>
          <td class="td-mono td-muted">${pos.symbol}</td>
          <td class="td-mono" style="color:var(--text-primary);font-weight:500;">${pos.name}</td>
          <td class="td-mono text-right">${pos.quantity.toLocaleString()}</td>
          <td class="td-mono td-muted text-right">${parseFloat(pos.avg_price).toFixed(2)}</td>
          <td class="td-mono text-right">${parseFloat(pos.current_price).toFixed(2)}</td>
          <td class="text-right">
            <div class="td-mono ${pnlClass}">${pnlSign}${pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
            <div class="td-mono ${pnlClass}" style="font-size:10px;opacity:0.7;">${pnlSign}${pnlPct.toFixed(2)}%</div>
          </td>
          <td class="td-mono text-right">${(parseFloat(pos.market_value) / 10000).toFixed(1)}万</td>
          <td class="text-right">
            <div class="weight-bar">
              <div class="weight-track">
                <div class="weight-fill" style="width:${parseFloat(pos.weight_pct) * 2}%"></div>
              </div>
              <span class="td-mono td-muted" style="width:40px;text-align:right;">${parseFloat(pos.weight_pct).toFixed(1)}%</span>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('loadPositions failed:', err);
  }
}

// ==========================================================================
// 交易信号
// ==========================================================================
async function loadSignals() {
  try {
    const signals = await apiGet('/signals/?limit=20');
    const container = document.getElementById('signal-list');
    const typeConfig = {
      buy: { icon: '↑', bg: 'buy' },
      sell: { icon: '↓', bg: 'sell' },
      warning: { icon: '⚠', bg: 'warning' },
      info: { icon: 'ℹ', bg: 'info' },
      risk: { icon: '✓', bg: 'risk' },
    };
    const statusConfig = {
      executed: { dot: 'executed', label: '已执行', color: 'var(--up)' },
      pending: { dot: 'pending', label: '待执行', color: 'var(--warning)' },
      rejected: { dot: 'rejected', label: '已拒绝', color: 'var(--down)' },
      info: { dot: 'info', label: '信息', color: 'var(--text-muted)' },
    };

    container.innerHTML = signals.map(s => {
      const tc = typeConfig[s.type] || typeConfig.info;
      const sc = statusConfig[s.status] || statusConfig.info;
      return `
        <div class="signal-item">
          <div class="signal-icon ${tc.bg}">${tc.icon}</div>
          <div class="signal-content">
            <div class="signal-meta">
              <span class="signal-time">${s.time_display || ''}</span>
              <span class="signal-symbol">${s.symbol}</span>
              <div class="signal-status">
                <div class="signal-status-dot ${sc.dot}"></div>
                <span class="signal-status-text ${sc.dot}" style="color:${sc.color}">${sc.label}</span>
              </div>
            </div>
            <div class="signal-message">${s.message}</div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('loadSignals failed:', err);
  }
}

// ==========================================================================
// 风控监控
// ==========================================================================
async function loadRisk() {
  try {
    const data = await apiGet('/risk/');
    const container = document.getElementById('risk-list');
    const summary = document.getElementById('risk-summary');

    const iconMap = {
      '单日回撤': '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/></svg>',
      '单仓上限': '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>',
      '总仓比例': '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>',
      '可用资金': '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
    };

    container.innerHTML = data.metrics.map(m => {
      const fillClass = m.status;
      const labelClass = m.status;
      return `
        <div>
          <div class="risk-item-header">
            <div class="risk-item-label">
              ${iconMap[m.name] || ''}
              <span>${m.name}</span>
            </div>
            <div class="risk-item-values">
              <span class="risk-current">${parseFloat(m.current_value).toFixed(2)}%</span>
              <span class="risk-limit">/ ${parseFloat(m.limit_value).toFixed(2)}%</span>
            </div>
          </div>
          <div class="risk-bar-row">
            <div class="risk-track">
              <div class="risk-fill ${fillClass}" style="width:${Math.min(parseFloat(m.usage_pct), 100)}%"></div>
            </div>
            <span class="risk-label ${labelClass}">${m.status === 'safe' ? '正常' : m.status === 'warning' ? '预警' : '超限'}</span>
          </div>
        </div>
      `;
    }).join('');

    const score = data.overall_score;
    summary.innerHTML = `
      <div class="risk-summary-header">
        <div class="risk-summary-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <span>综合风控评分</span>
        </div>
        <span class="risk-score">${score.toFixed(1)}</span>
      </div>
      <div class="risk-summary-bar">
        <div class="risk-summary-fill" style="width:${score}%"></div>
      </div>
    `;
  } catch (err) {
    console.error('loadRisk failed:', err);
  }
}

// ==========================================================================
// 初始化 & 定时刷新
// ==========================================================================
function loadAll() {
  loadStats();
  loadNetValueChart();
  loadQuotes();
  loadPositions();
  loadSignals();
  loadRisk();
}

// 页面加载完成后执行
document.addEventListener('DOMContentLoaded', () => {
  loadAll();

  // 每 30 秒自动刷新数据
  setInterval(() => {
    loadStats();
    loadQuotes();
    loadPositions();
    loadSignals();
    loadRisk();
  }, 30000);

  // 侧边栏导航点击（仅切换 active 状态，实际路由需扩展）
  document.querySelectorAll('.nav-item[data-tab]').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
    });
  });
});

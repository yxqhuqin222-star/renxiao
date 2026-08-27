"""Export a read-only public snapshot of the dashboard to docs/index.html.

The published GitHub Pages page keeps the full filtering UI (date range,
mode multi-select, xuebu multi-select) but runs it **entirely client-side**:
the full dataset is embedded as JSON and the browser filters/aggregates it
with the exact same semantics as ``pipeline.fetch_filtered`` /
``pipeline._table_aggregate`` / ``pipeline.fetch_cost_trend``.

No backend, no upload, no download, no database writes. Opening the link
shows the default view; changing filters re-renders instantly in the browser.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from app import app  # noqa: E402
import pipeline  # noqa: E402
from config import settings as S  # noqa: E402

OUTPUT_DIR = PROJECT_DIR / "docs"
OUTPUT_PATH = OUTPUT_DIR / "index.html"
FAVICON_SRC = PROJECT_DIR / "favicon_io"

FAVICON_FILES = [
    "apple-touch-icon.png",
    "favicon-32x32.png",
    "favicon-16x16.png",
    "favicon.ico",
    "site.webmanifest",
]

# Client-side filtering logic. Plain string (NOT an f-string) so that the
# JavaScript template literals (${...}) are preserved verbatim.
CLIENT_JS = r"""
(function () {
  var data = JSON.parse(document.getElementById('ro-data').textContent);
  var allRows = data.rows || [];
  var maxDate = data.maxDate;
  var costDecimals = data.costDecimals;
  var DEFAULT_TABLE = 'latest';
  var DEFAULT_CHART = '7d';

  function fmtNum(v, d) { return v == null ? '-' : Number(v).toFixed(d); }
  function fmtInt(v) { return v == null ? '-' : String(Math.round(Number(v))); }
  function fmtCost(v) { return v == null ? '-' : Number(v).toFixed(1); }
  function fmtRate(v) { return v == null ? '-' : (Number(v) * 100).toFixed(2) + '%'; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
    });
  }

  function shiftDate(ds, delta) {
    var p = ds.split('-');
    var dt = new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
    dt.setDate(dt.getDate() + delta);
    var y = dt.getFullYear();
    var m = String(dt.getMonth() + 1).padStart(2, '0');
    var d = String(dt.getDate()).padStart(2, '0');
    return y + '-' + m + '-' + d;
  }

  function norm(s) {
    if (!s) return null;
    var m = /^(\d{4})[-/]?(\d{2})[-/]?(\d{2})$/.exec(String(s).trim());
    if (!m) return null;
    return m[1] + '-' + m[2] + '-' + m[3];
  }

  function datePredicate(view, start, end) {
    if (view === 'all') return function () { return true; };
    if (view === 'latest') return function (r) { return r['日期'] === maxDate; };
    if (view === '7d') { var s7 = shiftDate(maxDate, -6); return function (r) { return r['日期'] >= s7; }; }
    if (view === '30d') { var s30 = shiftDate(maxDate, -29); return function (r) { return r['日期'] >= s30; }; }
    if (view === 'custom') {
      var ns = norm(start), ne = norm(end);
      return function (r) { return (!ns || r['日期'] >= ns) && (!ne || r['日期'] <= ne); };
    }
    return function () { return true; };
  }

  function readForm(form) {
    var view = form.querySelector('.js-view-input').value || 'all';
    var start = '', end = '';
    var si = form.querySelector('input[name$="_start"]');
    var ei = form.querySelector('input[name$="_end"]');
    if (si) start = si.value;
    if (ei) end = ei.value;
    var modes = Array.prototype.slice.call(form.querySelectorAll('input[type=checkbox][name$="_mode"]'))
      .filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
    var xuebus = Array.prototype.slice.call(form.querySelectorAll('input[type=checkbox][name$="_xuebu"]'))
      .filter(function (c) { return c.checked; }).map(function (c) { return c.value; });
    return { view: view, start: start, end: end, modes: modes, xuebus: xuebus };
  }

  function filterRows(f, withXuebu) {
    var pred = datePredicate(f.view, f.start, f.end);
    return allRows.filter(function (r) {
      if (!pred(r)) return false;
      if (f.modes.length && f.modes.indexOf(r['流转模式']) === -1) return false;
      if (withXuebu && f.xuebus.length && f.xuebus.indexOf(r['学部']) === -1) return false;
      return true;
    });
  }

  function aggregate(rows) {
    var totalExamples = rows.reduce(function (s, r) { return s + (Number(r['单量']) || 0); }, 0);
    if (totalExamples <= 0) {
      return { efficiency: '-', target: '-', case_cost: '-', line_cost: '-', rate: '-', total_examples: '-' };
    }
    var caseCost = rows.reduce(function (s, r) { return s + (Number(r['单例子结算成本']) || 0) * (Number(r['单量']) || 0); }, 0) / totalExamples;
    var lineCost = rows.reduce(function (s, r) { return s + (Number(r['线路成本']) || 0) * (Number(r['单量']) || 0); }, 0) / totalExamples;
    var ai = rows.reduce(function (s, r) { return s + (Number(r['AI接通数']) || 0); }, 0);
    var byDayMode = {};
    rows.forEach(function (r) {
      var key = r['日期'] + '|' + r['流转模式'];
      if (!byDayMode[key]) byDayMode[key] = r;
    });
    var att = Object.keys(byDayMode).reduce(function (s, k) { return s + (Number(byDayMode[k]['出勤']) || 0); }, 0);
    var effVol = Object.keys(byDayMode).reduce(function (s, k) { return s + (Number(byDayMode[k]['人效单量']) || 0); }, 0);
    var targetAtt = Object.keys(byDayMode).reduce(function (s, k) {
      return byDayMode[k]['人效目标'] == null ? s : s + (Number(byDayMode[k]['出勤']) || 0);
    }, 0);
    var targetVol = Object.keys(byDayMode).reduce(function (s, k) {
      return byDayMode[k]['人效目标'] == null ? s : s + (Number(byDayMode[k]['人效目标']) || 0) * (Number(byDayMode[k]['出勤']) || 0);
    }, 0);
    var efficiency = att ? effVol / att : 0;
    var target = targetAtt ? targetVol / targetAtt : null;
    var rate = ai ? totalExamples / ai : 0;
    return {
      efficiency: fmtNum(efficiency, 1),
      target: target == null ? '-' : fmtNum(target, 1),
      case_cost: fmtCost(caseCost),
      line_cost: fmtCost(lineCost),
      rate: fmtRate(rate),
      total_examples: fmtInt(totalExamples)
    };
  }

  function aggregateByDate(rows) {
    var byDate = {};
    rows.forEach(function (r) {
      var d = r['日期'];
      (byDate[d] || (byDate[d] = [])).push(r);
    });
    return Object.keys(byDate).sort().reverse().map(function (d) {
      var agg = aggregate(byDate[d]);
      agg.date = d;
      return agg;
    });
  }

  function viewLabel(f) {
    if (f.view === 'latest') return '最新一天';
    if (f.view === 'all') return '全部历史';
    if (f.view === '7d') return '近 7 天';
    if (f.view === '30d') return '近 30 天';
    if (f.view === 'custom') return (norm(f.start) || '开始') + ' 至 ' + (norm(f.end) || '结束');
    return f.view;
  }

  function renderTable(rows, f) {
    var wrap = document.querySelector('#results .table-wrap');
    if (!rows.length) {
      wrap.innerHTML = '<div class="empty"><strong>没有符合条件的结果</strong><br>调整筛选条件后重新查询。</div>';
    } else {
      var body = rows.map(function (r) {
        return '<tr>' +
          '<td class="date-value">' + esc(r['日期']) + '</td>' +
          '<td><span class="pill mode">' + esc(r['流转模式']) + '</span></td>' +
          '<td><span class="pill x' + esc(r['学部']) + '">' + esc(r['学部']) + '</span></td>' +
          '<td class="num">' + fmtNum(r['人效'], 1) + '</td>' +
          '<td class="num">' + fmtNum(r['人效目标'], 1) + '</td>' +
          '<td class="num">' + fmtInt(r['单量']) + '</td>' +
          '<td class="num">' + fmtCost(r['线路成本']) + '</td>' +
          '<td class="num">' + fmtCost(r['单例子结算成本']) + '</td>' +
          '<td class="num">' + fmtRate(r['接通转化率']) + '</td>' +
          '</tr>';
      }).join('');
      wrap.innerHTML = '<table><thead><tr>' +
        '<th>日期</th><th>流转模式</th><th>学部</th><th>人效</th><th>人效目标</th><th>单量</th>' +
        '<th>线路成本</th><th>单例子结算成本</th><th>接通转化率</th>' +
        '</tr></thead><tbody>' + body + '</tbody></table>';
    }
    var daily = aggregateByDate(rows);
    var dailyWrap = document.querySelector('#results .aggregate-table-wrap');
    if (dailyWrap) {
      if (!daily.length) {
        dailyWrap.innerHTML = '<div class="empty"><strong>没有可聚合的数据</strong><br>调整筛选条件后重新查询。</div>';
      } else {
        var dailyBody = daily.map(function (r) {
          return '<tr>' +
            '<td class="date-value">' + esc(r.date) + '</td>' +
            '<td class="num">' + r.efficiency + '</td>' +
            '<td class="num">' + r.target + '</td>' +
            '<td class="num">' + r.total_examples + '</td>' +
            '<td class="num">' + r.line_cost + '</td>' +
            '<td class="num">' + r.case_cost + '</td>' +
            '<td class="num">' + r.rate + '</td>' +
            '</tr>';
        }).join('');
        dailyWrap.innerHTML = '<table class="aggregate-table"><thead><tr>' +
          '<th>日期</th><th>人效</th><th>人效目标</th><th>单量</th><th>线路成本</th>' +
          '<th>单例子结算成本</th><th>接通转化率</th>' +
          '</tr></thead><tbody>' + dailyBody + '</tbody></table>';
      }
    }
    document.querySelector('#results .result-count').innerHTML =
      '共 <b>' + rows.length + '</b> 行 <span>' + viewLabel(f) + '</span>';
  }

  function trendPoints(f) {
    var pred = datePredicate(f.view, f.start, f.end);
    var seen = {};
    allRows.forEach(function (r) {
      if (Number(r['单量']) <= 0) return;
      if (!pred(r)) return;
      if (f.modes.length && f.modes.indexOf(r['流转模式']) === -1) return;
      var d = r['日期'];
      var b = seen[d] || (seen[d] = { cost: 0, vol: 0 });
      b.cost += (Number(r['单例子结算成本']) || 0) * (Number(r['单量']) || 0);
      b.vol += (Number(r['单量']) || 0);
    });
    return Object.keys(seen).sort().map(function (d) {
      var b = seen[d];
      return { '日期': d, '聚合单例子结算成本': b.vol > 0 ? Number((b.cost / b.vol).toFixed(costDecimals)) : 0, '总单量': b.vol };
    });
  }

  function renderKpi(rows) {
    var agg = aggregate(rows);
    var map = {
      efficiency: agg.efficiency,
      total_examples: agg.total_examples,
      line_cost: agg.line_cost,
      case_cost: agg.case_cost,
      rate: agg.rate
    };
    Object.keys(map).forEach(function (k) {
      var el = document.querySelector('[data-kpi="' + k + '"]');
      if (el) el.textContent = map[k];
    });
  }

  function applyChart() {
    var f = readForm(document.getElementById('chart-form'));
    var pts = trendPoints(f);
    var chartBox = document.getElementById('trend-chart');
    chartBox.dataset.points = JSON.stringify(pts);
    if (typeof window.renderTrendChart === 'function') window.renderTrendChart();
    var el = document.getElementById('trend-latest');
    if (el) el.textContent = pts.length ? Number(pts[pts.length - 1]['聚合单例子结算成本']).toFixed(1) : '-';
  }

  function applyTable() {
    var f = readForm(document.getElementById('table-form'));
    var rows = filterRows(f, true);
    renderTable(rows, f);
    renderKpi(rows);
  }

  function resetForm(form, defaultView) {
    form.querySelectorAll('input[type=checkbox]').forEach(function (cb) { cb.checked = false; });
    var vi = form.querySelector('.js-view-input');
    if (vi) vi.value = defaultView;
    form.querySelectorAll('.segment').forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.view === defaultView ? 'true' : 'false');
    });
    var cr = form.querySelector('.custom-range');
    if (cr) cr.classList.toggle('is-visible', defaultView === 'custom');
    form.querySelectorAll('.js-date-dropdown').forEach(function (dd) {
      var inp = document.getElementById(dd.dataset.input);
      if (inp) inp.value = '';
      dd.querySelectorAll('.date-option').forEach(function (o) {
        o.setAttribute('aria-selected', o.dataset.value === '' ? 'true' : 'false');
      });
      var sum = dd.querySelector('.mode-summary');
      if (sum) sum.textContent = dd.dataset.emptyLabel;
    });
    form.querySelectorAll('.js-mode-dropdown').forEach(function (dd) {
      var sum = dd.querySelector('.mode-summary');
      if (sum) sum.textContent = '全部';
    });
  }

  function apply(form) {
    if (form.id === 'chart-form') applyChart();
    else if (form.id === 'table-form') applyTable();
  }

  function bind() {
    var chartForm = document.getElementById('chart-form');
    var tableForm = document.getElementById('table-form');
    [chartForm, tableForm].forEach(function (form) {
      if (!form) return;
      form.addEventListener('submit', function (e) { e.preventDefault(); });
      form.addEventListener('click', function (e) {
        if (e.target.closest('[data-reset]')) return;
        apply(form);
      });
      form.addEventListener('change', function (e) {
        if (e.target.matches('input[type=checkbox]')) apply(form);
      });
    });
    document.querySelectorAll('[data-reset]').forEach(function (link) {
      link.addEventListener('click', function (e) {
        e.preventDefault();
        var isChart = link.dataset.reset === 'chart';
        var form = isChart ? chartForm : tableForm;
        resetForm(form, isChart ? DEFAULT_CHART : DEFAULT_TABLE);
        apply(form);
      });
    });
    // Apply once on load so the initial render uses the same maxDate-anchored
    // baseline as every later interaction (no mixed today-vs-maxDate basis).
    applyChart();
    applyTable();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
"""


def fix_favicons(html: str) -> str:
    for fname in FAVICON_FILES:
        src = FAVICON_SRC / fname
        if src.exists():
            shutil.copy(src, OUTPUT_DIR / fname)
        html = html.replace(f"/favicon_io/{fname}", fname)
    return html


def _remove_upload(html: str) -> str:
    return re.sub(r'<form action="/upload"[^>]*>.*?</form>', "", html, flags=re.S)


def _remove_download(html: str) -> str:
    return re.sub(r'<a class="btn btn-secondary" href="/download[^"]*">.*?</a>', "", html, flags=re.S)


def _relabel_forms(html: str) -> str:
    html = html.replace(
        '<form class="controls chart-controls js-range-form" action="/" method="get">',
        '<form id="chart-form" class="controls chart-controls js-range-form" method="get" onsubmit="return false">',
    )
    html = html.replace(
        '<form class="controls js-range-form" action="/" method="get">',
        '<form id="table-form" class="controls js-range-form" method="get" onsubmit="return false">',
    )
    return html


def _relabel_resets(html: str) -> str:
    pat = re.compile(r'<a class="btn btn-secondary" href="/\?[^"]*">重置</a>')
    matches = list(pat.finditer(html))
    if len(matches) >= 1:
        m0 = matches[0]
        html = html[: m0.start()] + '<a class="btn btn-secondary" href="#" data-reset="chart">重置</a>' + html[m0.end():]
        remaining = list(pat.finditer(html))
        if remaining:
            m1 = remaining[0]
            html = html[: m1.start()] + '<a class="btn btn-secondary" href="#" data-reset="table">重置</a>' + html[m1.end():]
    return html


def transform(html: str) -> str:
    html = _remove_upload(html)
    html = _remove_download(html)
    html = _relabel_forms(html)
    html = _relabel_resets(html)
    return html


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with app.test_client() as client:
        response = client.get("/?table_view=latest&chart_view=7d")
        if response.status_code != 200:
            raise SystemExit(f"GET / failed: {response.status_code}")
        html = response.get_data(as_text=True)

    all_rows = pipeline.fetch_filtered(view="all")
    data = {
        "rows": all_rows,
        "dates": pipeline.distinct_dates(),
        "modes": pipeline.distinct_modes(),
        "xuebus": list(S.XUBU_WHITELIST),
        "maxDate": pipeline.latest_date(),
        "costDecimals": S.COST_DECIMALS,
        "defaultTable": "latest",
        "defaultChart": "7d",
    }
    json_blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    html = transform(html)
    html = fix_favicons(html)

    inject = (
        '<script type="application/json" id="ro-data">' + json_blob + "</script>\n"
        '<script>' + CLIENT_JS + "</script>\n"
    )
    html = html.replace("</body>", inject + "</body>")

    banner = "<!-- Read-only public snapshot with client-side filtering. No backend, no upload or download. -->\n"
    html = "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    OUTPUT_PATH.write_text(banner + html, encoding="utf-8")
    (OUTPUT_DIR / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH} | embedded rows={len(all_rows)} | maxDate={data['maxDate']}")


if __name__ == "__main__":
    main()

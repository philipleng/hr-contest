// 里程碑报告图表与流程图初始化
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // --- Chart: 主开发会话任务分布 ---
  var el = document.getElementById('chart-tasks');
  if (el) {
    var chart = echarts.init(el, null, { renderer: 'svg' });
    chart.setOption({
      animation: false,
      grid: { left: 44, right: 24, top: 24, bottom: 40 },
      tooltip: {
        appendToBody: true,
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: bg2,
        borderColor: rule,
        textStyle: { color: ink }
      },
      xAxis: {
        type: 'category',
        data: ['10-15', '10-20', '10-21', '10-23', '10-24', '10-25', '11-02'],
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 12 }
      },
      yAxis: {
        type: 'value',
        name: '任务数',
        nameTextStyle: { color: muted, fontSize: 11 },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
        axisLabel: { color: muted, fontSize: 12 }
      },
      series: [{
        type: 'bar',
        data: [28, 10, 6, 4, 35, 38, 12],
        barWidth: '46%',
        itemStyle: { color: accent, borderRadius: [3, 3, 0, 0] },
        emphasis: { itemStyle: { color: accent2 } },
        label: {
          show: true,
          position: 'top',
          color: ink,
          fontSize: 12,
          fontWeight: 600
        }
      }]
    });
    window.addEventListener('resize', function () { chart.resize(); });
  }

  // --- Diagram: Mermaid ---
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: true,
      theme: 'neutral',
      securityLevel: 'loose',
      flowchart: { htmlLabels: true, curve: 'basis' }
    });
  }
})();

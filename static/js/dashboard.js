/* Dashboard charts (Chart.js). Data comes from /api/dashboard. */
(function () {
  var COLORS = {"Completed":"#2a9d5c","Under Review":"#e0a100","Submitted":"#7a5cd0","In Progress":"#2f7fd4","Not Started":"#9aa8b6","Rejected":"#d45a5a","Overdue":"#b42318"};
  Chart.defaults.font.family = '"IBM Plex Sans", system-ui, sans-serif';
  Chart.defaults.color = "#5f7083";
  var grid = {color: "#e7edf3"};

  function empty(canvas, text) {
    var box = canvas.parentElement; box.innerHTML = '<div class="empty"><i class="bi bi-bar-chart"></i><div>' + text + '</div></div>';
  }

  fetch(window.DASHBOARD_API, {credentials: "same-origin"}).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status); return r.json();
  }).then(function (d) {
    var sc = document.getElementById("chartStatus"), labels = Object.keys(d.status), vals = labels.map(function (k) { return d.status[k]; });
    if (vals.reduce(function (a, b) { return a + b; }, 0) === 0) empty(sc, "No tasks yet.");
    else new Chart(sc, {type: "doughnut", data: {labels: labels, datasets: [{data: vals, backgroundColor: labels.map(function (l) { return COLORS[l]; }), borderWidth: 2, borderColor: "#fff"}]},
      options: {maintainAspectRatio: false, cutout: "62%", plugins: {legend: {position: "right", labels: {usePointStyle: true, boxWidth: 8}}}}});

    var tc = document.getElementById("chartTeams");
    if (!d.teams.labels.length) empty(tc, "No teams yet.");
    else new Chart(tc, {type: "bar", data: {labels: d.teams.labels, datasets: [
        {label: "Completed", data: d.teams.completed, backgroundColor: "#2a9d5c", borderRadius: 4},
        {label: "Total tasks", data: d.teams.total, backgroundColor: "#c9d5e1", borderRadius: 4}]},
      options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: grid, ticks: {precision: 0}}, x: {grid: {display: false}}},
        plugins: {legend: {position: "bottom", labels: {usePointStyle: true, boxWidth: 8}},
          tooltip: {callbacks: {afterBody: function (items) { var i = items[0].dataIndex; return "Completion: " + d.teams.completion[i] + "%"; }}}}}});

    var ic = document.getElementById("chartInterns");
    if (!d.interns.labels.length) empty(ic, "No intern activity yet.");
    else new Chart(ic, {type: "bar", data: {labels: d.interns.labels, datasets: [
        {label: "Completed tasks", data: d.interns.completed, backgroundColor: "#0d7c86", borderRadius: 4, yAxisID: "y"},
        {label: "Average score", data: d.interns.avg_score, type: "line", borderColor: "#f0b43c", backgroundColor: "#f0b43c", tension: .3, yAxisID: "y1", pointRadius: 4}]},
      options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: grid, ticks: {precision: 0}, title: {display: true, text: "Completed"}},
        y1: {position: "right", min: 0, max: 100, grid: {display: false}, title: {display: true, text: "Avg score"}}, x: {grid: {display: false}, ticks: {maxRotation: 55, minRotation: 35}}},
        plugins: {legend: {position: "bottom", labels: {usePointStyle: true, boxWidth: 8}}}}});

    var mc = document.getElementById("chartMonthly");
    new Chart(mc, {type: "line", data: {labels: d.monthly.labels, datasets: [
        {label: "Submitted", data: d.monthly.submitted, borderColor: "#0d7c86", backgroundColor: "rgba(13,124,134,.14)", fill: true, tension: .3, pointRadius: 4},
        {label: "Assigned", data: d.monthly.assigned, borderColor: "#9aa8b6", borderDash: [5, 4], tension: .3, pointRadius: 3}]},
      options: {maintainAspectRatio: false, scales: {y: {beginAtZero: true, grid: grid, ticks: {precision: 0}}, x: {grid: {display: false}}},
        plugins: {legend: {position: "bottom", labels: {usePointStyle: true, boxWidth: 8}}}}});
  }).catch(function () {
    document.querySelectorAll(".chart-box").forEach(function (b) { b.innerHTML = '<div class="empty"><i class="bi bi-exclamation-triangle"></i><div>Charts could not be loaded. Check your internet connection and reload.</div></div>'; });
  });
})();

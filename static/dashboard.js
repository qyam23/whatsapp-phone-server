(function () {
  "use strict";

  const dataElement = document.getElementById("dashboard-data");
  const chart = document.getElementById("activity-chart");
  if (!dataElement || !chart) return;

  const data = JSON.parse(dataElement.textContent || "{}");
  const labels = data.labels || [];
  const current = data.current || [];
  const previous = data.previous || [];
  const width = 900;
  const height = 270;
  const margin = { top: 14, right: 18, bottom: 38, left: 42 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;
  const maxValue = Math.max(1, ...current, ...previous);
  const yMax = Math.ceil(maxValue / 5) * 5 || 5;
  const ns = "http://www.w3.org/2000/svg";

  chart.setAttribute("viewBox", `0 0 ${width} ${height}`);
  chart.replaceChildren();

  function append(name, attributes, text) {
    const node = document.createElementNS(ns, name);
    Object.entries(attributes || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = text;
    chart.appendChild(node);
    return node;
  }

  function x(index) {
    return margin.left + (labels.length <= 1 ? 0 : (index / (labels.length - 1)) * innerWidth);
  }

  function y(value) {
    return margin.top + innerHeight - (value / yMax) * innerHeight;
  }

  function path(values) {
    return values.map((value, index) => `${index ? "L" : "M"} ${x(index)} ${y(value)}`).join(" ");
  }

  for (let step = 0; step <= 4; step += 1) {
    const value = (yMax / 4) * step;
    const yPosition = y(value);
    append("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: yPosition,
      y2: yPosition,
      class: "chart-grid"
    });
    append("text", {
      x: margin.left - 9,
      y: yPosition + 4,
      "text-anchor": "end",
      class: "chart-axis-label"
    }, String(Math.round(value)));
  }

  const labelStep = labels.length > 12 ? Math.ceil(labels.length / 8) : Math.max(1, Math.ceil(labels.length / 6));
  labels.forEach((label, index) => {
    if (index % labelStep !== 0 && index !== labels.length - 1) return;
    append("text", {
      x: x(index),
      y: height - 12,
      "text-anchor": index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle",
      class: "chart-axis-label"
    }, label);
  });

  if (previous.length) append("path", { d: path(previous), class: "chart-line-previous" });
  if (current.length) {
    append("path", { d: path(current), class: "chart-line-current" });
    current.forEach((value, index) => {
      const point = append("circle", {
        cx: x(index),
        cy: y(value),
        r: 3.5,
        class: "chart-point"
      });
      const title = document.createElementNS(ns, "title");
      title.textContent = `${labels[index]}: ${value} messages`;
      point.appendChild(title);
    });
  }

  window.setTimeout(function () {
    window.location.reload();
  }, 12 * 60 * 60 * 1000);
})();

const state = { page: 1, total: 0, options: [] };
const $ = (selector) => document.querySelector(selector);

function option(value, label) {
  const element = document.createElement("option");
  element.value = value;
  element.textContent = label;
  return element;
}

function setCities() {
  const provinceName = $("#province").value;
  const city = $("#city");
  city.replaceChildren(option("", "全部城市"));
  const province = state.options.find((item) => item.name === provinceName);
  for (const item of province?.cities ?? []) {
    city.append(option(item.name, `${item.name}（${item.position_count.toLocaleString()}）`));
  }
  city.disabled = !province || province.cities.length === 0;
}

function locationText(item) {
  return item.locations.map((location) => location.raw_text).join("、") || "未注明";
}

function render(items) {
  const list = $("#position-list");
  list.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "没有找到符合条件的岗位";
    list.append(empty);
    return;
  }
  const template = $("#position-template");
  for (const item of items) {
    const card = template.content.cloneNode(true);
    card.querySelector(".employer").textContent = item.employer_name || item.organization_name;
    card.querySelector(".title").textContent = item.title;
    card.querySelector(".headcount").textContent = `招 ${item.headcount ?? "—"} 人`;
    card.querySelector(".location").textContent = locationText(item);
    card.querySelector(".education").textContent = [item.education, item.degree].filter(Boolean).join(" / ") || "未注明";
    card.querySelector(".major").textContent = item.majors_raw || "未注明";
    card.querySelector(".political").textContent = item.political_status || "未注明";
    card.querySelector(".requirements").textContent = item.other_requirements || "无补充要求";
    card.querySelector(".code").textContent = `职位代码 ${item.position_code || "—"}`;
    const source = card.querySelector(".source");
    source.href = item.source_url;
    list.append(card);
  }
}

async function loadPositions() {
  const error = $("#error");
  error.hidden = true;
  $("#result-status").textContent = "正在读取数据…";
  const params = new URLSearchParams({
    page: String(state.page),
    page_size: $("#page-size").value,
  });
  const keyword = $("#keyword").value.trim();
  const province = $("#province").value;
  const city = $("#city").value;
  if (keyword) params.set("keyword", keyword);
  if (province) params.set("province_name", province);
  if (city) params.set("city_name", city);
  if ($("#broader-scope").checked) params.set("include_broader_scope", "true");

  try {
    const response = await fetch(`/api/positions?${params}`);
    if (!response.ok) throw new Error(`请求失败（${response.status}）`);
    const data = await response.json();
    state.total = data.total;
    render(data.items);
    const pages = Math.max(1, Math.ceil(data.total / data.page_size));
    $("#total-count").textContent = data.total.toLocaleString();
    $("#result-label").textContent = city || province || "全国岗位";
    $("#result-status").textContent = `找到 ${data.total.toLocaleString()} 条职位`;
    $("#page-label").textContent = `第 ${data.page} / ${pages} 页`;
    $("#previous").disabled = data.page <= 1;
    $("#next").disabled = data.page >= pages;
  } catch (reason) {
    error.textContent = `数据加载失败：${reason.message}`;
    error.hidden = false;
    $("#result-status").textContent = "暂时无法读取岗位";
  }
}

async function loadOptions() {
  const response = await fetch("/api/location-options");
  if (!response.ok) throw new Error("地区选项加载失败");
  state.options = await response.json();
  const province = $("#province");
  for (const item of state.options) {
    province.append(option(item.name, `${item.name}（${item.position_count.toLocaleString()}）`));
  }
}

$("#province").addEventListener("change", () => { setCities(); state.page = 1; });
$("#search-button").addEventListener("click", () => { state.page = 1; loadPositions(); });
$("#keyword").addEventListener("keydown", (event) => {
  if (event.key === "Enter") { state.page = 1; loadPositions(); }
});
$("#previous").addEventListener("click", () => { state.page -= 1; loadPositions(); scrollTo(0, 0); });
$("#next").addEventListener("click", () => { state.page += 1; loadPositions(); scrollTo(0, 0); });

Promise.all([loadOptions(), loadPositions()]).catch((reason) => {
  $("#error").textContent = reason.message;
  $("#error").hidden = false;
});

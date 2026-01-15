const configSelect = document.getElementById("configSelect");
const configForm = document.getElementById("configForm");
const saveButton = document.getElementById("saveConfig");
const createPersonaButton = document.getElementById("createPersona");
const addNodeButton = document.getElementById("addNode");
const statusLabel = document.getElementById("saveStatus");
const jsonPreview = document.getElementById("jsonPreview");
const runButton = document.getElementById("runDemo");
const runSeconds = document.getElementById("runSeconds");
const runOutput = document.getElementById("runOutput");
const runMeta = document.getElementById("runMeta");

let currentConfigId = null;
let currentConfigData = null;

const EMPTY_PERSONA_TEMPLATE = {
  name: "",
  description: "",
  initial_knowledge: [],
  memory_config: {
    promotion_threshold: 4.0,
    decay_rate: 0.1,
    forget_threshold: 15.0,
    max_strength: 100.0,
  },
};

/** 判断是否为人设配置 ID。 */
function isPersonaConfigId(configId) {
  return configId && configId.startsWith("persona:");
}

/** 规范化人设文件名并校验合法性。 */
function normalizePersonaFilename(rawName) {
  const trimmed = (rawName || "").trim();
  if (!trimmed) {
    throw new Error("人设文件名不能为空");
  }
  const base = trimmed.endsWith(".toml")
    ? trimmed.slice(0, -".toml".length)
    : trimmed;
  if (!/^[A-Za-z0-9_-]+$/.test(base)) {
    throw new Error("人设文件名仅支持字母、数字、下划线或短横线");
  }
  return `${base}.toml`;
}

/** 设置保存状态提示文本。 */
function setStatus(message, tone) {
  statusLabel.textContent = message || "";
  if (tone) {
    statusLabel.dataset.tone = tone;
  } else {
    statusLabel.removeAttribute("data-tone");
  }
}

/** 设置运行元信息提示。 */
function setRunMeta(message) {
  runMeta.textContent = message;
}

/** 使用 JSON 方式深拷贝对象。 */
function deepClone(obj) {
  return JSON.parse(JSON.stringify(obj));
}

/** 解析数值输入并抛出错误提示。 */
function readNumber(value, label) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    throw new Error(`${label} 必须是数字`);
  }
  return parsed;
}

/** 将逗号分隔文本拆分为数组。 */
function splitList(value) {
  if (!value) {
    return [];
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** 创建文本/多行输入字段。 */
function createField({ label, id, value, type = "text", multiline = false }) {
  const wrapper = document.createElement("label");
  wrapper.className = "field";
  const span = document.createElement("span");
  span.textContent = label;
  const input = multiline ? document.createElement("textarea") : document.createElement("input");
  if (!multiline) {
    input.type = type;
  }
  input.id = id;
  input.value = value == null ? "" : String(value);
  wrapper.appendChild(span);
  wrapper.appendChild(input);
  return { wrapper, input };
}

/** 创建复选框字段。 */
function createCheckboxField({ label, id, checked }) {
  const wrapper = document.createElement("label");
  wrapper.className = "field";
  const span = document.createElement("span");
  span.textContent = label;
  const input = document.createElement("input");
  input.type = "checkbox";
  input.id = id;
  input.checked = Boolean(checked);
  wrapper.appendChild(span);
  wrapper.appendChild(input);
  return { wrapper, input };
}

/** 创建分组区域。 */
function createSection(title) {
  const section = document.createElement("div");
  section.className = "section";
  const heading = document.createElement("h3");
  heading.className = "section-title";
  heading.textContent = title;
  section.appendChild(heading);
  return section;
}

/** 请求 JSON 接口并处理错误。 */
async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  let data = null;
  try {
    data = await response.json();
  } catch (err) {
    if (!response.ok) {
      throw new Error(`请求失败，状态码 ${response.status}`);
    }
  }
  if (!response.ok) {
    const errorMessage =
      data && data.error ? data.error : `请求失败，状态码 ${response.status}`;
    throw new Error(errorMessage);
  }
  return data;
}

/** 更新 JSON 预览区内容。 */
function updatePreview(content) {
  jsonPreview.textContent = JSON.stringify(content, null, 2);
}

/** 渲染 LLM 配置表单。 */
function renderLlmConfig(config) {
  configForm.innerHTML = "";

  const providers = config.providers || {};
  const embedApi = providers.embed_api || {};
  const fastApi = providers.fast_api || {};
  const advancedApi = providers.advanced_api || {};

  const providerSection = createSection("提供方");
  const providerGrid = document.createElement("div");
  providerGrid.className = "field-grid";

  providerGrid.appendChild(
    createField({
      label: "Embed API 类型",
      id: "llm-embed-type",
      value: embedApi.type || "",
    }).wrapper
  );
  providerGrid.appendChild(
    createField({
      label: "向量维度",
      id: "llm-embed-dim",
      value: embedApi.embedding_dim ?? "",
      type: "number",
    }).wrapper
  );
  providerGrid.appendChild(
    createField({
      label: "Fast API 类型",
      id: "llm-fast-type",
      value: fastApi.type || "",
    }).wrapper
  );
  providerGrid.appendChild(
    createField({
      label: "Advanced API 类型",
      id: "llm-advanced-type",
      value: advancedApi.type || "",
    }).wrapper
  );

  providerSection.appendChild(providerGrid);
  configForm.appendChild(providerSection);

  const routing = config.routing || {};
  const defaultRouting = routing.default || {};
  const memoryRouting = routing.memory || {};
  const behaviorRouting = routing.behavior || {};

  const routingSection = createSection("路由");
  const routingGrid = document.createElement("div");
  routingGrid.className = "field-grid";

  routingGrid.appendChild(
    createField({
      label: "默认 摘要与评分",
      id: "route-default-summary",
      value: defaultRouting.summarize_and_score || "",
    }).wrapper
  );
  routingGrid.appendChild(
    createField({
      label: "默认 生成意图",
      id: "route-default-intent",
      value: defaultRouting.generate_intent || "",
    }).wrapper
  );
  routingGrid.appendChild(
    createField({
      label: "记忆 摘要与评分",
      id: "route-memory-summary",
      value: memoryRouting.summarize_and_score || "",
    }).wrapper
  );
  routingGrid.appendChild(
    createField({
      label: "行为 生成意图",
      id: "route-behavior-intent",
      value: behaviorRouting.generate_intent || "",
    }).wrapper
  );

  routingSection.appendChild(routingGrid);
  configForm.appendChild(routingSection);
}

/** 渲染应用配置表单。 */
function renderAppConfig(config) {
  configForm.innerHTML = "";

  const pathSection = createSection("路径配置");
  const pathGrid = document.createElement("div");
  pathGrid.className = "field-grid";
  pathGrid.appendChild(
    createField({
      label: "知识树路径",
      id: "app-knowledge-path",
      value: config.knowledge_path || "",
    }).wrapper
  );
  pathGrid.appendChild(
    createField({
      label: "世界观路径",
      id: "app-worldview-path",
      value: config.worldview_path || "",
    }).wrapper
  );
  pathGrid.appendChild(
    createField({
      label: "LLM 配置路径",
      id: "app-llm-path",
      value: config.llm_config_path || "",
    }).wrapper
  );
  pathGrid.appendChild(
    createField({
      label: "人设路径",
      id: "app-persona-path",
      value: config.persona_path || "",
    }).wrapper
  );
  pathSection.appendChild(pathGrid);
  configForm.appendChild(pathSection);

  const agentSection = createSection("启动配置");
  const agentGrid = document.createElement("div");
  agentGrid.className = "field-grid";
  agentGrid.appendChild(
    createField({
      label: "Agent 列表（逗号分隔）",
      id: "app-agents",
      value: Array.isArray(config.agents) ? config.agents.join(", ") : "",
    }).wrapper
  );
  agentGrid.appendChild(
    createField({
      label: "演示运行秒数",
      id: "app-run-seconds",
      value: config.run_seconds ?? "",
      type: "number",
    }).wrapper
  );
  agentGrid.appendChild(
    createCheckboxField({
      label: "启动记忆测试",
      id: "app-memory-test",
      checked: config.memory_test,
    }).wrapper
  );
  agentSection.appendChild(agentGrid);
  configForm.appendChild(agentSection);

  const webuiSection = createSection("Web UI");
  const webuiGrid = document.createElement("div");
  webuiGrid.className = "field-grid";
  const webui = config.webui || {};
  webuiGrid.appendChild(
    createField({
      label: "Host",
      id: "app-webui-host",
      value: webui.host || "",
    }).wrapper
  );
  webuiGrid.appendChild(
    createField({
      label: "Port",
      id: "app-webui-port",
      value: webui.port ?? "",
      type: "number",
    }).wrapper
  );
  webuiSection.appendChild(webuiGrid);
  configForm.appendChild(webuiSection);
}

/** 渲染人设配置表单。 */
function renderPersonaConfig(config) {
  configForm.innerHTML = "";

  const baseSection = createSection("人设");
  const baseGrid = document.createElement("div");
  baseGrid.className = "field-grid";
  baseGrid.appendChild(
    createField({
      label: "名称",
      id: "persona-name",
      value: config.name || "",
    }).wrapper
  );
  baseGrid.appendChild(
    createField({
      label: "初始知识（逗号分隔）",
      id: "persona-knowledge",
      value: (config.initial_knowledge || []).join(", "),
    }).wrapper
  );
  baseSection.appendChild(baseGrid);
  const descField = createField({
    label: "描述",
    id: "persona-description",
    value: config.description || "",
    multiline: true,
  });
  baseSection.appendChild(descField.wrapper);
  configForm.appendChild(baseSection);

  const memoryConfig = config.memory_config || {};
  const memorySection = createSection("记忆配置");
  const memoryGrid = document.createElement("div");
  memoryGrid.className = "field-grid";
  memoryGrid.appendChild(
    createField({
      label: "提升阈值",
      id: "memory-promotion",
      value: memoryConfig.promotion_threshold ?? "",
      type: "number",
    }).wrapper
  );
  memoryGrid.appendChild(
    createField({
      label: "衰减率",
      id: "memory-decay",
      value: memoryConfig.decay_rate ?? "",
      type: "number",
    }).wrapper
  );
  memoryGrid.appendChild(
    createField({
      label: "遗忘阈值",
      id: "memory-forget",
      value: memoryConfig.forget_threshold ?? "",
      type: "number",
    }).wrapper
  );
  memoryGrid.appendChild(
    createField({
      label: "最大强度",
      id: "memory-max",
      value: memoryConfig.max_strength ?? "",
      type: "number",
    }).wrapper
  );
  memorySection.appendChild(memoryGrid);
  configForm.appendChild(memorySection);
}

/** 构建知识节点表格行。 */
function buildNodeRow(node, index) {
  const row = document.createElement("div");
  row.className = "node-row";
  row.dataset.index = String(index);

  row.appendChild(
    createField({
      label: "节点 ID",
      id: `node-id-${index}`,
      value: node.id || "",
    }).wrapper
  );
  row.appendChild(
    createField({
      label: "父节点 ID",
      id: `node-parent-${index}`,
      value: node.parent ?? "",
    }).wrapper
  );
  row.appendChild(
    createCheckboxField({
      label: "锁定",
      id: `node-locked-${index}`,
      checked: node.is_locked,
    }).wrapper
  );
  row.appendChild(
    createField({
      label: "前置条件（逗号分隔）",
      id: `node-prereq-${index}`,
      value: (node.prerequisites || []).join(", "),
    }).wrapper
  );
  row.appendChild(
    createField({
      label: "内容",
      id: `node-content-${index}`,
      value: node.content || "",
      multiline: true,
    }).wrapper
  );

  const actions = document.createElement("div");
  actions.className = "node-actions";
  const removeButton = document.createElement("button");
  removeButton.type = "button";
  removeButton.className = "ghost";
  removeButton.textContent = "移除";
  removeButton.addEventListener("click", () => {
    row.remove();
  });
  actions.appendChild(removeButton);
  row.appendChild(actions);

  return row;
}

/** 渲染知识树配置表单。 */
function renderKnowledgeGraph(config) {
  configForm.innerHTML = "";

  const nodesSection = createSection("知识节点");
  const nodeList = document.createElement("div");
  nodeList.className = "node-list";
  nodeList.id = "nodeList";

  const nodes = Array.isArray(config.nodes) ? config.nodes : [];
  nodes.forEach((node, index) => {
    nodeList.appendChild(buildNodeRow(node, index));
  });

  nodesSection.appendChild(nodeList);
  configForm.appendChild(nodesSection);
}

/** 根据配置类型渲染表单。 */
function renderConfigForm(configId, config) {
  if (configId === "app_config") {
    renderAppConfig(config);
  } else if (configId === "llm_config") {
    renderLlmConfig(config);
  } else if (isPersonaConfigId(configId)) {
    renderPersonaConfig(config);
  } else if (configId === "knowledge_graph") {
    renderKnowledgeGraph(config);
  } else {
    configForm.innerHTML = "<p>不支持的配置类型。</p>";
  }
}

/** 从表单构建 LLM 配置对象。 */
function buildLlmConfig(base) {
  const updated = deepClone(base);
  updated.providers = updated.providers || {};
  updated.providers.embed_api = updated.providers.embed_api || {};
  updated.providers.fast_api = updated.providers.fast_api || {};
  updated.providers.advanced_api = updated.providers.advanced_api || {};

  updated.providers.embed_api.type = document.getElementById("llm-embed-type").value;
  updated.providers.embed_api.embedding_dim = readNumber(
    document.getElementById("llm-embed-dim").value,
    "Embedding dim"
  );
  updated.providers.fast_api.type = document.getElementById("llm-fast-type").value;
  updated.providers.advanced_api.type =
    document.getElementById("llm-advanced-type").value;

  updated.routing = updated.routing || {};
  updated.routing.default = updated.routing.default || {};
  updated.routing.memory = updated.routing.memory || {};
  updated.routing.behavior = updated.routing.behavior || {};

  updated.routing.default.summarize_and_score = document.getElementById(
    "route-default-summary"
  ).value;
  updated.routing.default.generate_intent = document.getElementById(
    "route-default-intent"
  ).value;
  updated.routing.memory.summarize_and_score = document.getElementById(
    "route-memory-summary"
  ).value;
  updated.routing.behavior.generate_intent = document.getElementById(
    "route-behavior-intent"
  ).value;

  return updated;
}

/** 从表单构建应用配置对象。 */
function buildAppConfig(base) {
  const updated = deepClone(base);
  updated.knowledge_path = document.getElementById("app-knowledge-path").value.trim();
  updated.worldview_path = document.getElementById("app-worldview-path").value.trim();
  updated.llm_config_path = document.getElementById("app-llm-path").value.trim();
  updated.persona_path = document.getElementById("app-persona-path").value.trim();
  updated.agents = splitList(document.getElementById("app-agents").value);
  updated.run_seconds = readNumber(
    document.getElementById("app-run-seconds").value || "0",
    "Run seconds"
  );
  updated.memory_test = document.getElementById("app-memory-test").checked;

  updated.webui = updated.webui || {};
  updated.webui.host = document.getElementById("app-webui-host").value.trim();
  updated.webui.port = readNumber(
    document.getElementById("app-webui-port").value || "8000",
    "Web UI port"
  );
  return updated;
}

/** 从表单构建人设配置对象。 */
function buildPersonaConfig(base) {
  const updated = deepClone(base);
  updated.name = document.getElementById("persona-name").value.trim();
  updated.description = document.getElementById("persona-description").value.trim();
  updated.initial_knowledge = splitList(
    document.getElementById("persona-knowledge").value
  );

  updated.memory_config = updated.memory_config || {};
  updated.memory_config.promotion_threshold = readNumber(
    document.getElementById("memory-promotion").value,
    "Promotion threshold"
  );
  updated.memory_config.decay_rate = readNumber(
    document.getElementById("memory-decay").value,
    "Decay rate"
  );
  updated.memory_config.forget_threshold = readNumber(
    document.getElementById("memory-forget").value,
    "Forget threshold"
  );
  updated.memory_config.max_strength = readNumber(
    document.getElementById("memory-max").value,
    "Max strength"
  );

  return updated;
}

/** 从表单构建知识树配置对象。 */
function buildKnowledgeGraph(base) {
  const updated = deepClone(base);
  const nodeList = document.getElementById("nodeList");
  const rows = nodeList ? Array.from(nodeList.querySelectorAll(".node-row")) : [];

  const nodes = rows.map((row) => {
    const index = row.dataset.index;
    const id = document.getElementById(`node-id-${index}`).value.trim();
    const parentRaw = document.getElementById(`node-parent-${index}`).value.trim();
    const locked = document.getElementById(`node-locked-${index}`).checked;
    const content = document
      .getElementById(`node-content-${index}`)
      .value.trim();
    const prereq = splitList(
      document.getElementById(`node-prereq-${index}`).value
    );

    if (!id) {
      throw new Error("知识节点 ID 不能为空");
    }
    if (!content) {
      throw new Error(`知识节点 "${id}" 内容不能为空`);
    }

    return {
      id,
      parent: parentRaw ? parentRaw : null,
      is_locked: locked,
      content,
      prerequisites: prereq,
    };
  });

  updated.nodes = nodes;
  return updated;
}

/** 组装提交用的配置内容。 */
function buildConfigPayload() {
  if (!currentConfigId || !currentConfigData) {
    return null;
  }
  if (currentConfigId === "app_config") {
    return buildAppConfig(currentConfigData);
  }
  if (currentConfigId === "llm_config") {
    return buildLlmConfig(currentConfigData);
  }
  if (isPersonaConfigId(currentConfigId)) {
    return buildPersonaConfig(currentConfigData);
  }
  if (currentConfigId === "knowledge_graph") {
    return buildKnowledgeGraph(currentConfigData);
  }
  return null;
}

/** 监听表单变更并刷新预览。 */
function attachPreviewListener() {
  configForm.addEventListener("input", () => {
    if (!currentConfigId || !currentConfigData) {
      return;
    }
    try {
      const updated = buildConfigPayload();
      if (updated) {
        updatePreview(updated);
      }
    } catch (err) {
      // 编辑过程中忽略预览错误。
    }
  });
}

/** 加载配置列表并填充下拉框。 */
async function loadConfigs(selectFirst = false) {
  const data = await fetchJSON("/api/configs");
  const current = configSelect.value;
  configSelect.innerHTML = "";
  data.configs.forEach((config) => {
    const option = document.createElement("option");
    option.value = config.id;
    option.textContent = config.label;
    configSelect.appendChild(option);
  });
  if (selectFirst || !current) {
    configSelect.selectedIndex = 0;
  } else {
    const option = Array.from(configSelect.options).find(
      (item) => item.value === current
    );
    if (option) {
      configSelect.value = current;
    }
  }
}

/** 加载当前选择的配置内容。 */
async function loadConfig() {
  const configId = configSelect.value;
  if (!configId) {
    return;
  }
  setStatus("加载中...", null);
  const data = await fetchJSON(`/api/config?id=${encodeURIComponent(configId)}`);
  currentConfigId = configId;
  currentConfigData = JSON.parse(data.content || "{}");
  renderConfigForm(configId, currentConfigData);
  updatePreview(currentConfigData);
  addNodeButton.classList.toggle(
    "hidden",
    currentConfigId !== "knowledge_graph"
  );
  setStatus("已加载。", "ok");
}

/** 保存当前配置到后端。 */
async function saveConfig() {
  const configId = configSelect.value;
  if (!configId || !currentConfigData) {
    return;
  }
  setStatus("保存中...", null);
  let updated;
  try {
    updated = buildConfigPayload();
  } catch (err) {
    setStatus(err.message, "error");
    return;
  }
  if (!updated) {
    setStatus("没有可保存的内容。", "error");
    return;
  }
  const payload = {
    content: JSON.stringify(updated, null, 2),
  };
  await fetchJSON(`/api/config?id=${encodeURIComponent(configId)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  currentConfigData = updated;
  updatePreview(updated);
  setStatus("已保存。", "ok");
}

/** 创建新的空人设配置。 */
async function createEmptyPersona() {
  const rawName = window.prompt("请输入人设文件名（不含 .toml）");
  if (rawName == null) {
    return;
  }
  let filename;
  try {
    filename = normalizePersonaFilename(rawName);
  } catch (err) {
    setStatus(err.message, "error");
    return;
  }
  const payload = {
    filename,
    content: JSON.stringify(
      {
        ...EMPTY_PERSONA_TEMPLATE,
        name: "",
      },
      null,
      2
    ),
  };
  const data = await fetchJSON("/api/persona", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  await loadConfigs(false);
  configSelect.value = data.id;
  await loadConfig();
  setStatus("新人设已创建。", "ok");
}

/** 追加一个空知识节点。 */
function addKnowledgeNode() {
  if (currentConfigId !== "knowledge_graph") {
    return;
  }
  const nodeList = document.getElementById("nodeList");
  if (!nodeList) {
    return;
  }
  const indices = Array.from(nodeList.querySelectorAll(".node-row")).map((row) =>
    Number(row.dataset.index || 0)
  );
  const index = indices.length ? Math.max(...indices) + 1 : 0;
  const newNode = {
    id: "",
    parent: null,
    is_locked: true,
    content: "",
    prerequisites: [],
  };
  nodeList.appendChild(buildNodeRow(newNode, index));
}

/** 调用后端运行脚本化演示。 */
async function runDemo() {
  const seconds = parseInt(runSeconds.value, 10) || 5;
  runOutput.textContent = "";
  setRunMeta("运行中...");
  const payload = {
    run_seconds: seconds,
  };
  const data = await fetchJSON("/api/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const header = `退出码: ${data.returncode} | 耗时: ${data.duration}s | 运行秒数: ${data.run_seconds}`;
  const pieces = [header];
  if (data.stdout) {
    pieces.push("\n--- 标准输出 ---\n" + data.stdout.trim());
  }
  if (data.stderr) {
    pieces.push("\n--- 标准错误 ---\n" + data.stderr.trim());
  }
  runOutput.textContent = pieces.join("\n");
  setRunMeta("运行完成。");
}

/** 统一处理前端错误提示。 */
function handleError(error) {
  setStatus(error.message, "error");
  setRunMeta(error.message);
}

saveButton.addEventListener("click", () => {
  saveConfig().catch(handleError);
});

addNodeButton.addEventListener("click", () => {
  addKnowledgeNode();
});

createPersonaButton.addEventListener("click", () => {
  createEmptyPersona().catch(handleError);
});

runButton.addEventListener("click", () => {
  runDemo().catch(handleError);
});

window.addEventListener("load", () => {
  attachPreviewListener();
  loadConfigs(true)
    .then(loadConfig)
    .catch(handleError);
});

configSelect.addEventListener("change", () => {
  loadConfig().catch(handleError);
});

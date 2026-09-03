/**
 * 施工日报解析配置生成 — Pi 自定义工具扩展
 *
 * 安全设计（重点）：
 * - 本扩展**不注册任何文件系统 / shell 类工具**（无 read / write / bash / edit），
 *   也不做任意 URL fetch —— 只调用后端内部的 report-config 端点；
 * - 日报文件由后端落在受控临时目录，AI 只能拿到后端生成的 `file_path` 字符串
 *   （不能自行指定路径）；扩展工具不读取文件内容，仅原样转发参数；
 * - 真正的安全边界（配置 Gate 0-4 校验、正则 ReDoS 检测、配置落盘路径约束）
 *   全部位于后端 service，AI 无法绕过。
 *
 * 部署时通过 pi 的 `-e <path>` 加载；pi 以 `--no-builtin-tools` 启动，
 * 因此内置工具（bash 等）对模型完全不可见。
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const INTERNAL_BASE_URL = process.env["PI_INTERNAL_BASE_URL"] ?? "http://127.0.0.1:8000";
// 内部工具端点的鉴权令牌：后端生成并注入，扩展仅原样透传。
const INTERNAL_TOKEN = process.env["PI_INTERNAL_TOKEN"] ?? "";

async function callInternal(path: string, method = "GET", body?: unknown): Promise<unknown> {
  const headers: Record<string, string> = {};
  if (INTERNAL_TOKEN) headers["x-internal-token"] = INTERNAL_TOKEN;
  if (body !== undefined) headers["content-type"] = "application/json";

  const res = await fetch(`${INTERNAL_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const json = (await res.json()) as { detail?: string };
      if (json.detail) detail = `${detail}: ${json.detail}`;
    } catch {
      // 非 JSON 响应，保留状态码
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return await res.json();
}

export default function (pi: ExtensionAPI): void {
  // ────────────────────────────────────────────────────────────────
  // 工具 0：获取项目上下文（资源清单、标签维度，帮助 AI 做映射决策）
  // ────────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "get_project_context",
    label: "获取项目上下文",
    description:
      "获取当前施工项目的资源清单、资源分类与标签维度。AI 在编写日报解析配置前应先调用此工具，以便将日报中的资源名称映射到项目已有资源。",
    promptSnippet: "获取项目资源清单与标签维度（编写解析配置前调用）",
    promptGuidelines: [
      "编写日报解析配置前，先调用 get_project_context 获取项目已有资源与标签维度，据此决定配置中的 name/quantity 映射。",
      "AI 只能使用本项目提供的工具，不得尝试读取文件或执行命令。",
    ],
    parameters: Type.Object({
      project_id: Type.Integer({ description: "项目 ID" }),
    }),
    async execute(_toolCallId, params) {
      const data = await callInternal(`/internal/ai/projects/${params.project_id}/context`);
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        details: { data },
      };
    },
  });

  // ────────────────────────────────────────────────────────────────
  // 工具 1：提取日报文本预览（AI 阅读日报结构）
  // ────────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "extract_report_preview",
    label: "提取日报预览",
    description:
      "获取上传的施工日报 Excel 文件的头部文本预览（Markdown 表格），供 AI 理解日报的行列结构，是编写解析配置的前提。file_path 由后端提供，AI 不得自行拼接路径。",
    promptSnippet: "提取日报文件文本预览（编写配置前的第一步）",
    promptGuidelines: [
      "收到用户提供的施工日报后，第一步调用 extract_report_preview 获取其结构，不要凭空猜测列布局。",
      "file_path 必须使用用户消息中给出的路径，不要修改或自行构造。",
    ],
    parameters: Type.Object({
      project_id: Type.Integer({ description: "项目 ID" }),
      file_path: Type.String({ description: "日报文件的临时绝对路径（由后端提供）" }),
    }),
    async execute(_toolCallId, params) {
      const data = await callInternal(
        `/internal/ai/projects/${params.project_id}/extract-preview`,
        "POST",
        { file_path: params.file_path },
      );
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        details: { data },
      };
    },
  });

  // ────────────────────────────────────────────────────────────────
  // 工具 2：校验配置 + 干跑解析预览（无副作用）
  // ────────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "validate_report_config",
    label: "校验解析配置",
    description:
      "校验 AI 生成的日报解析配置（ParseEngineConfig JSON），可选地配合样例日报文件进行干跑解析预览。无副作用，不保存任何数据。编写配置后、保存前必须先调用此工具确认通过。",
    promptSnippet: "校验日报解析配置并预览解析结果（保存前的必经步骤）",
    promptGuidelines: [
      "生成解析配置后必须调用 validate_report_config 校验；只有校验通过（success=true）才能调用 save_report_config 保存。",
      "校验失败时根据 errors 修正配置后重新校验，不要直接保存未通过的配置。",
    ],
    parameters: Type.Object({
      project_id: Type.Integer({ description: "项目 ID" }),
      config_json: Type.Any({
        description: "ParseEngineConfig 的 JSON 表示（schema_version + blocks）",
      }),
      sample_file_path: Type.Optional(
        Type.String({ description: "可选：样例日报文件的临时绝对路径" }),
      ),
    }),
    async execute(_toolCallId, params) {
      const data = await callInternal(
        `/internal/ai/projects/${params.project_id}/validate-config`,
        "POST",
        {
          config_json: params.config_json,
          sample_file_path: params.sample_file_path ?? null,
        },
      );
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        details: { data },
      };
    },
  });

  // ────────────────────────────────────────────────────────────────
  // 工具 3：保存配置（通过全量校验的配置才能落盘）
  // ────────────────────────────────────────────────────────────────
  pi.registerTool({
    name: "save_report_config",
    label: "保存解析配置",
    description:
      "保存 AI 生成的日报解析配置到项目。服务端会再次执行全量校验（Gate 0-4），只有通过的配置才会落盘。保存成功返回 config_id。",
    promptSnippet: "保存校验通过的日报解析配置",
    promptGuidelines: [
      "仅当 validate_report_config 校验通过后才可调用 save_report_config；保存成功后告知用户 config_id。",
    ],
    parameters: Type.Object({
      project_id: Type.Integer({ description: "项目 ID" }),
      config_json: Type.Any({
        description: "ParseEngineConfig 的 JSON 表示（已通过校验）",
      }),
      name: Type.Optional(Type.String({ description: "人类可读的配置名称" })),
    }),
    async execute(_toolCallId, params) {
      const data = await callInternal(
        `/internal/ai/projects/${params.project_id}/save-config`,
        "POST",
        {
          config_json: params.config_json,
          name: params.name ?? null,
        },
      );
      return {
        content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        details: { data },
      };
    },
  });
}

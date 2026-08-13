import type { Analysis, AgentTrace, AnalysisRecord, AuditEvent, Dataset, DatasetAsset, Session, SessionDetail } from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, options)
  } catch {
    // 网络层失败（后端未启动 / 连接超时 / 跨域被拦截等），避免把原始
    // "Failed to fetch" 暴露给用户，统一为中文提示。
    throw new Error('网络异常，无法连接分析服务，请确认后端已启动后重试。')
  }
  if (!response.ok) {
    // 部分 404 为 FastAPI 默认路由（detail 为英文 "Not Found"），统一转为中文。
    const payload = await response.json().catch(() => ({} as Record<string, string>))
    const detail = payload.detail ?? (response.status === 404 ? '请求的资源不存在。' : '请求失败，请稍后重试。')
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function uploadDataset(file: File, displayName = ''): Promise<Dataset> {
  const form = new FormData()
  form.append('file', file)
  if (displayName) form.append('display_name', displayName)
  return request('/api/v1/datasets/upload', { method: 'POST', body: form })
}

export function createDemoDataset(displayName = ''): Promise<Dataset> {
  const form = new FormData()
  if (displayName) form.append('display_name', displayName)
  return request('/api/v1/demo/dataset', { method: 'POST', body: form })
}

/** 修改数据集在左侧的自定义显示名称。 */
export function renameDataset(datasetId: string, displayName = ''): Promise<Dataset> {
  const form = new FormData()
  form.append('display_name', displayName)
  return request(`/api/v1/datasets/${datasetId}/display-name`, { method: 'PATCH', body: form })
}

export function startAnalysis(payload: {
  dataset_id: string
  question: string
  strategy_goal: string
  brand_tone?: string
  analysis_window: string
  session_name?: string
}): Promise<Analysis> {
  return request('/api/v1/analyses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getAnalysis(id: string): Promise<Analysis> {
  return request(`/api/v1/analyses/${id}`)
}

export function listAnalyses(limit = 50): Promise<Analysis[]> {
  return request(`/api/v1/analyses?limit=${limit}`)
}

export function deleteAnalysis(id: string): Promise<void> {
  return request(`/api/v1/analyses/${id}`, { method: 'DELETE' })
}

export function getEvents(id: string): Promise<AuditEvent[]> {
  return request(`/api/v1/analyses/${id}/events`)
}

export function getDatasetAsset(datasetId: string): Promise<DatasetAsset> {
  return request(`/api/v1/datasets/${datasetId}/asset`)
}

/** 左侧导航：按数据集维度列出全部数据集（一数据集一张卡片）。 */
export function listDatasets(limit = 100): Promise<Dataset[]> {
  return request(`/api/v1/datasets?limit=${limit}`)
}

/** 数据集详情：聚合该数据集下所有业务记录（含完整洞察/策略/轨迹）。 */
export function getDatasetDetail(datasetId: string): Promise<SessionDetail> {
  return request(`/api/v1/datasets/${datasetId}/detail`)
}

/** 提交业务问题前查重：若数据集下已存在相同问题，返回对应业务记录可直接跳转复用。 */
export function findExistingQuestion(
  datasetId: string,
  question: string,
): Promise<{ found: boolean; conversation: AnalysisRecord | null }> {
  return request(
    `/api/v1/datasets/${datasetId}/find-question?question=${encodeURIComponent(question)}`,
  )
}

// ----------------------------------------------------------------------
// AI Customer Intelligence · 会话式分析系统
// Session（分析会话）/ AnalysisRecord（会话内业务分析记录）
// 端点保持与历史 sessions API 兼容
// ----------------------------------------------------------------------
export function listSessions(limit = 50): Promise<Session[]> {
  return request(`/api/v1/sessions?limit=${limit}`)
}

export function getSessionDetail(sessionId: string): Promise<SessionDetail> {
  return request(`/api/v1/sessions/${sessionId}`)
}

export function deleteSession(sessionId: string): Promise<void> {
  return request(`/api/v1/sessions/${sessionId}`, { method: 'DELETE' })
}

/** 按数据集维度真实删除：级联移除业务记录、轨迹与上传文件。 */
export function deleteDataset(datasetId: string): Promise<void> {
  return request(`/api/v1/datasets/${datasetId}`, { method: 'DELETE' })
}

export function continueSession(
  sessionId: string,
  payload: {
    question: string
    strategy_goal?: string
    brand_tone?: string
    analysis_window?: string
  },
): Promise<Analysis> {
  return request(`/api/v1/sessions/${sessionId}/continue`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

// 兼容别名（历史命名）
export const listProjects = listSessions
export const getProjectDetail = getSessionDetail
export const deleteProject = deleteSession
export const continueAnalysis = continueSession

export type { Session, SessionDetail, AnalysisRecord, AgentTrace }

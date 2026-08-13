export type Severity = 'info' | 'warning' | 'error'

export interface QualityIssue {
  code: string
  severity: Severity
  message: string
  field?: string
}

export interface QualityReport {
  row_count: number
  usable_row_count: number
  user_count: number
  analyzability_score: number
  field_mapping: Record<string, string>
  missing_rates: Record<string, number>
  category_coverage: number
  issues: QualityIssue[]
  can_analyze: boolean
}

export interface Dataset {
  id: string
  name: string
  /** 用户自定义的左侧显示名称（为空时回退到 name） */
  display_name: string
  file_type: string
  row_count: number
  quality: QualityReport
  created_at: string
  preview?: DatasetPreview | null
  /** 该数据集下的业务分析记录数（左侧卡片展示） */
  record_count: number
}

export interface Evidence {
  metric: string
  value: string
  benchmark: string
  interpretation: string
}

export interface IncomeBand {
  label: string
  share: number
}

export interface IncomeProfile {
  available: boolean
  average_income?: number | null
  median_income?: number | null
  high_income_share?: number | null
  income_bands?: IncomeBand[]
  note?: string
}

export interface CategoryContribution {
  category: string
  category_cn: string
  spend?: number
  spend_share?: number
  user_count?: number
  user_share?: number
}

export interface RecentActivityPattern {
  last_event_days_ago?: number
  recent_30d_event_share?: number
  peak_hours?: number[]
  high_ticket_category?: string | null
  high_ticket_category_value?: number | null
}

export interface OverallConsumptionInsight {
  available: boolean
  summary?: string
  top_categories?: CategoryContribution[]
  category_spend_distribution?: CategoryContribution[]
  category_user_distribution?: CategoryContribution[]
  recent_activity_pattern?: RecentActivityPattern
  segment_count?: number
}

export interface Segment {
  segment_id: string
  cluster_id?: number | null
  name: string
  user_count: number
  share: number
  income_profile?: IncomeProfile
  statistics?: Record<string, unknown>
  key_features: string[]
  evidence: Evidence[]
  recommended_strategy?: string
  rule_basis: string[]
  opportunity_score?: number
  opportunity_level?: 'high' | 'medium' | 'low'
  opportunity_reason?: string[]
}

export interface DatasetPreview {
  sample_row_count: number
  segments: Segment[]
  insights: Array<{
    title: string
    summary: string
    evidence: string[]
  }>
  top_products: Array<{
    name: string
    count: number
  }>
  date_range: string
  avg_order_value: number
  total_amount: number
  income_profile?: IncomeProfile
  overall_consumption_insight?: OverallConsumptionInsight
}

/** 数据集级分析资产（沉淀的完整客户洞察，供所有业务问题复用） */
export interface DatasetAsset {
  dataset_id: string
  dataset_name: string
  quality: QualityReport
  segments: Segment[]
  insights: Insight[]
  overall_consumption_insight: OverallConsumptionInsight
  income_profile?: IncomeProfile
  cluster_quality?: {
    silhouette_score: number | null
    cluster_count: number
    sample_size: number
    auto_selected?: boolean
    search_range?: number[]
    clustering_features?: string[]
  }
  segment_method?: string
  has_asset: boolean
}

export interface InterestProfile {
  direct_interests: string[]
  behavior_interests: string[]
}

export interface Insight {
  segment_id: string
  segment_name: string
  segment_size?: number
  income_profile?: IncomeProfile
  top_tags: string[]
  persona_tags: string[]
  profile: string
  predicted_interests: string[]
  interests: string[]
  interest_profile?: InterestProfile
  value_tier: string
  behavior_profile: string[]
  consumption_features?: string[]
  category_preference?: string[]
  brand_preference?: string[]
  motivation: string
  needs: string[]
  trend_explanation: string
  decision_implications: string[]
  recommended_actions: string[]
  alternative_explanations: string[]
  limitations: string[]
}

export interface StrategyBasis {
  data: string[]
  knowledge: string[]
}

export interface StrategyCard {
  segment_id: string
  segment_name: string
  opportunity: string
  target_positioning?: string
  marketing_goal?: string
  content_strategy?: string
  product_strategy?: string
  promotion_strategy?: string
  marketing_direction?: string
  ad_theme?: string
  ad_elements?: string[]
  recommended_products?: string[]
  channels?: string[]
  metrics?: string[]
  strategy_basis: StrategyBasis
  product_mechanisms: string[]
  benefits: string[]
  page: {
    theme: string
    visual_keywords: string[]
    modules: string[]
    hero_title: string
    hero_subtitle: string
    emotional_direction: string
  }
  slogans: string[]
  validation_metrics: string[]
  evidence_summary: string[]
  limitations: string[]
}

export interface AnalysisResult {
  route: 'quality_only' | 'segment_only' | 'full_strategy'
  executive_summary: string
  quality: QualityReport
  segments: Segment[]
  insights: Insight[]
  strategy_cards: StrategyCard[]
  evaluation: {
    completeness: number
    evidence_coverage: number
    strategy_actionability: number
    differentiation: number
    warnings: string[]
  }
  segment_method?: string
  overall_consumption_insight?: OverallConsumptionInsight
  income_profile?: IncomeProfile
  cluster_quality?: {
    silhouette_score: number | null
    cluster_count: number
    sample_size: number
    auto_selected?: boolean
    search_range?: number[]
    clustering_features?: string[]
  }
  agent_plan?: string[]
  agent_delegation?: Record<string, boolean>
  intent?: string
  reasoning?: string
  agent_trace?: Array<{
    agent: string
    action: string
    output: string
  }>
  knowledge_support?: {
    context: string
    sources: string[]
  }
  model_mode: 'deterministic' | 'llm_enhanced'
  warnings: string[]
}

export interface Analysis {
  id: string
  dataset_id: string
  dataset_name: string
  question: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  route: string
  result: AnalysisResult | Record<string, never>
  error_message: string
  created_at: string
  updated_at: string
}

export interface AuditEvent {
  agent: string
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

// ----------------------------------------------------------------------
// AI Customer Intelligence · 会话式分析系统
// 产品术语（前端）：Session = 分析会话（一个数据集对应一个会话）
// AnalysisRecord = 会话内的业务分析记录（每一条业务问题）
// 后端复用 SessionRecord / ConversationRecord，保持 API 兼容。
// ----------------------------------------------------------------------
export interface SessionStats {
  segment_count: number
  insight_count: number
  strategy_count: number
  conversation_count: number
}

/** 会话：一个数据集对应一个分析会话 */
export interface Session {
  id: string
  dataset_id: string
  dataset_name: string
  display_name?: string
  name: string
  status: string
  summary: string
  created_at: string
  updated_at: string
  stats: SessionStats
  question: string
}

/**
 * 业务分析记录：会话内的每一条业务问题（自动以问题命名）。
 * 每条记录自带一套结果归属：问题、洞察结果、策略结果、Agent 轨迹。
 */
export interface AnalysisRecord {
  id: string
  session_id: string
  analysis_id: string
  question: string
  answer: string
  answer_summary: string
  /** Strategy Agent 完整输出（已持久化，展开时直接使用） */
  strategy_result?: StrategyCard[]
  /** Insight Agent 输出（已持久化，展开时直接使用） */
  insight_result?: Insight[]
  /** Agent 执行轨迹（已持久化） */
  agent_trace?: Array<{ agent: string; action: string; output: string }>
  created_at: string
}

export interface AgentTrace {
  id: string
  session_id: string
  conversation_id: string
  agent: string
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

export interface SessionDetail {
  session: Session
  conversations: AnalysisRecord[]
  messages: AgentTrace[]
}

// 兼容别名（内部复用）
export type Project = Session
export type ProjectDetail = SessionDetail
export type ProjectStats = SessionStats
export type Conversation = AnalysisRecord
export type Message = AgentTrace
export type SessionSummary = SessionStats

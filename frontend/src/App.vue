<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  ArrowRight,
  Check,
  DataAnalysis,
  Document,
  MagicStick,
  Promotion,
  UploadFilled,
  UserFilled,
  Warning,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import {
  continueSession,
  createDemoDataset,
  deleteDataset,
  deleteSession,
  findExistingQuestion,
  getAnalysis,
  getDatasetAsset,
  getDatasetDetail,
  getEvents,
  listDatasets,
  renameDataset,
  startAnalysis,
  uploadDataset,
} from './api'
import type { Analysis, AnalysisRecord, AnalysisResult, AuditEvent, Dataset, DatasetAsset, Insight, Session, SessionDetail, Segment, StrategyCard } from './types'

use([CanvasRenderer, BarChart, PieChart, GridComponent, LegendComponent, TooltipComponent])

const dataset = ref<Dataset | null>(null)
const analysis = ref<Analysis | null>(null)
const events = ref<AuditEvent[]>([])
// 数据集级分析资产：沉淀的完整客户洞察，驱动会话详情页顶部基础分析结果展示
const datasetAsset = ref<DatasetAsset | null>(null)
// 会话式：list = 会话列表/详情；compose = 新建分析流程
const activeView = ref<'list' | 'compose'>('list')
const sessions = ref<Session[]>([])
const selectedSession = ref<Session | null>(null)
const sessionDetail = ref<SessionDetail | null>(null)
const selectedCard = ref(0)
const activeResultTab = ref<'overview' | 'evidence' | 'page'>('overview')
const busy = ref(false)
const dragging = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
// 新建会话时的会话名称（自定义优先，否则按数据集名自动生成）
const sessionName = ref('')
// 左侧数据集自定义显示名称（重命名对话框）
const renameVisible = ref(false)
const renameTarget = ref<Session | null>(null)
const renameInput = ref('')

// 继续追问
const followUpQuestion = ref('')
const followUpBusy = ref(false)
const expandedRecordId = ref<string | null>(null)
// 当前数据集下全部分析项目（session）id，用于「生成业务策略」时复用某个会话
const datasetSessionIds = ref<string[]>([])

// 刷新后恢复视图状态：记住最后选中的会话与展开的业务记录
const STORAGE_SELECTED = 'cia:selected_session'
const STORAGE_EXPANDED = 'cia:expanded_record'

const form = ref({
  question: '哪些用户人群最适合承接下一期专题页或营销活动？请给出差异化策略。',
  strategy_goal: '输出用户画像、人群识别、产品机制、页面方向和验证指标',
  analysis_window: '全部数据',
})

const result = computed<AnalysisResult | null>(() => {
  if (analysis.value?.status !== 'completed') return null
  if (dataset.value && analysis.value.dataset_id !== dataset.value.id) return null
  return analysis.value.result as AnalysisResult
})

// 会话详情页「用户洞察」展示来源：统一以数据集沉淀资产（DatasetAsset）为唯一真相源。
// 新建分析会话完成后也会复用同一数据集资产，保证两个入口进入的页面完全一致。
const assetResult = computed<AnalysisResult | null>(() => {
  const asset = datasetAsset.value
  if (asset && asset.has_asset) {
    return {
      route: 'full_strategy',
      executive_summary: asset.dataset_name ? `${asset.dataset_name} 的客户洞察资产` : '客户洞察资产',
      quality: asset.quality,
      segments: asset.segments,
      insights: asset.insights,
      strategy_cards: [],
      evaluation: { completeness: 1, evidence_coverage: 1, strategy_actionability: 1, differentiation: 1, warnings: [] },
      overall_consumption_insight: asset.overall_consumption_insight,
      income_profile: asset.income_profile,
      cluster_quality: asset.cluster_quality,
      segment_method: asset.segment_method,
      agent_trace: [],
      model_mode: 'deterministic',
      warnings: [],
    }
  }
  // 数据集资产尚未就绪（如刚上传、分析进行中）时，回退到本次分析结果预览
  if (result.value) return result.value
  return null
})
const uploadPreview = computed(() => dataset.value?.preview ?? null)
const currentCard = computed<StrategyCard | null>(() => result.value?.strategy_cards[selectedCard.value] ?? null)
const currentInsight = computed(() => {
  if (!currentCard.value) return null
  return result.value?.insights.find((item) => item.segment_id === currentCard.value?.segment_id)
})
const scoreTone = computed(() => {
  const score = dataset.value?.quality.analyzability_score ?? 0
  if (score >= 85) return 'great'
  if (score >= 70) return 'good'
  return 'warn'
})
// 当前用于图表/列表展示的人群：只展示占比最高的 Top 3，避免品类过细
const activeSegments = computed(() => {
  const source = (assetResult.value ?? result.value)?.segments ?? []
  return [...source].sort((a, b) => b.share - a.share).slice(0, 3)
})
const insightPanelCards = computed<Array<{ segment: Segment; insight?: Insight; summary: string }>>(() => {
  const base = assetResult.value ?? result.value
  const source = base?.segments.length
    ? base.segments
    : (uploadPreview.value?.segments ?? [])
  const top = [...source].sort((a, b) => b.share - a.share).slice(0, 3)
  return top.map((segment) => {
    const insight = base?.insights.find((item) => item.segment_id === segment.segment_id)
    return {
      segment,
      insight,
      summary: insight?.profile || insight?.motivation || segment.key_features.slice(0, 2).join('；'),
    }
  })
})
const consumptionInsight = computed(() => {
  const base = assetResult.value ?? result.value
  if (base?.overall_consumption_insight?.available) return base.overall_consumption_insight
  return uploadPreview.value?.overall_consumption_insight ?? null
})
const segmentChart = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
  grid: { left: 4, right: 18, top: 8, bottom: 4, containLabel: true },
  xAxis: {
    type: 'value',
    max: 100,
    axisLabel: { formatter: '{value}%', color: '#7b8496' },
    splitLine: { lineStyle: { color: '#edf1f6' } },
  },
  yAxis: {
    type: 'category',
    data: (activeSegments.value.length ? activeSegments.value : insightPanelCards.value.map((item) => item.segment)).map((item) => item.name).reverse(),
    axisLabel: { color: '#273246', fontWeight: 600 },
    axisLine: { show: false },
    axisTick: { show: false },
  },
  series: [
    {
      type: 'bar',
      data: (activeSegments.value.length ? activeSegments.value : insightPanelCards.value.map((item) => item.segment))
        .map((item) => Math.round(item.share * 100))
        .reverse(),
      barWidth: 16,
      itemStyle: { color: '#2f6eea', borderRadius: [0, 6, 6, 0] },
      label: { show: true, position: 'right', formatter: '{c}%', color: '#526074' },
    },
  ],
}))
const categoryMixChart = computed(() => {
  const segments = activeSegments.value.length ? activeSegments.value : insightPanelCards.value.map((item) => item.segment)
  const palette = ['#2563eb', '#4f46e5', '#7c3aed', '#8b5cf6', '#3b82f6', '#6366f1', '#60a5fa', '#c4b5fd']
  return {
    tooltip: { trigger: 'item', formatter: '{b}<br/>{c} 人 · {d}%' },
    legend: { bottom: 0, left: 'center', itemWidth: 8, itemHeight: 8, textStyle: { color: '#64748b', fontSize: 10 } },
    color: palette,
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        label: { formatter: '{b}\\n{d}%', color: '#475569', fontSize: 10 },
        labelLine: { length: 8, length2: 6 },
        emphasis: {
          scaleSize: 6,
          itemStyle: { shadowBlur: 18, shadowColor: 'rgba(47, 110, 234, .22)' },
        },
        itemStyle: { borderColor: '#fff', borderWidth: 3 },
        data: segments.slice(0, 8).map((segment) => ({
          name: segment.name,
          value: segment.user_count,
        })),
      },
    ],
  }
})

function resetResults() {
  analysis.value = null
  events.value = []
  selectedCard.value = 0
  activeResultTab.value = 'overview'
}

async function refreshSessions() {
  // 左侧按数据集维度加载：一数据集一张卡片，聚合其全部业务记录。
  const datasets = await listDatasets(100)
  sessions.value = datasets.map((ds) => ({
    id: ds.id,
    dataset_id: ds.id,
    dataset_name: ds.name,
    display_name: ds.display_name || '',
    name: `${ds.name} 分析项目`,
    status: 'active',
    summary: '',
    created_at: ds.created_at,
    updated_at: ds.created_at,
    stats: { segment_count: 0, insight_count: 0, strategy_count: 0, conversation_count: ds.record_count },
    question: '',
  }))
  if (selectedSession.value && !sessions.value.some((item) => item.id === selectedSession.value?.id)) {
    selectedSession.value = null
    sessionDetail.value = null
  }
  if (!selectedSession.value && sessions.value.length) {
    // 刷新后：优先恢复上次选中的数据集，否则打开最近更新的数据集
    const savedId = localStorage.getItem(STORAGE_SELECTED)
    const target = sessions.value.find((item) => item.id === savedId) ?? sessions.value[0]
    await openSession(target)
  }
}

// 左侧数据集显示名称：自定义 display_name 优先，否则回退到数据集名
function datasetDisplayName(s: Session): string {
  return s.display_name?.trim() || s.dataset_name || '未命名数据集'
}

function openRenameDialog(record: Session) {
  renameTarget.value = record
  renameInput.value = record.display_name?.trim() || ''
  renameVisible.value = true
}

async function confirmRename() {
  if (!renameTarget.value) return
  const target = renameTarget.value
  try {
    const updated = await renameDataset(target.dataset_id, renameInput.value.trim())
    target.display_name = updated.display_name || ''
    renameVisible.value = false
    ElMessage.success('显示名称已更新')
  } catch {
    ElMessage.error('更新显示名称失败')
  }
}

async function openSession(record: Session) {
  selectedSession.value = record
  localStorage.setItem(STORAGE_SELECTED, record.id)
  // 数据集级聚合详情：加载该数据集下所有业务记录（每条独立含洞察/策略/轨迹）
  sessionDetail.value = await getDatasetDetail(record.id)
  // 收集该数据集下的所有分析项目（session）id，供「生成业务策略」复用
  datasetSessionIds.value = [
    ...new Set(sessionDetail.value.conversations.map((item) => item.session_id)),
  ]
  // 恢复上次展开的业务记录（若该记录仍属于此数据集）
  const savedExpanded = localStorage.getItem(STORAGE_EXPANDED)
  expandedRecordId.value = savedExpanded && sessionDetail.value.conversations.some((item) => item.id === savedExpanded)
    ? savedExpanded
    : null
  followUpQuestion.value = ''
  analysis.value = null
  events.value = []
  // 加载数据集级分析资产（沉淀的洞察/分群/消费趋势），驱动顶部基础分析结果
  try {
    datasetAsset.value = await getDatasetAsset(record.dataset_id)
  } catch {
    datasetAsset.value = null
  }
}

async function removeSession(record: Session, event: MouseEvent) {
  event.stopPropagation()
  try {
    await ElMessageBox.confirm('删除后该数据集、历史业务记录与 Agent 轨迹都会移除，不能在页面中恢复。', '删除这个数据集？', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  await deleteDataset(record.dataset_id)
  if (selectedSession.value?.dataset_id === record.dataset_id) {
    selectedSession.value = null
    sessionDetail.value = null
    analysis.value = null
    localStorage.removeItem(STORAGE_SELECTED)
    localStorage.removeItem(STORAGE_EXPANDED)
  }
  await refreshSessions()
  ElMessage.success('数据集已删除')
}

function startCompose() {
  activeView.value = 'compose'
  dataset.value = null
  resetResults()
  sessionName.value = ''
}

async function submitFollowUp() {
  if (!selectedSession.value) return
  if (!followUpQuestion.value.trim()) {
    ElMessage.warning('请输入业务问题')
    return
  }
  followUpBusy.value = true
  try {
    // 提交前查重：若数据集下已存在完全相同业务问题，直接跳转复用，不重复分析
    const dup = await findExistingQuestion(
      selectedSession.value.dataset_id,
      followUpQuestion.value,
    )
    if (dup.found && dup.conversation) {
      await openSession(selectedSession.value)
      expandedRecordId.value = dup.conversation.id
      localStorage.setItem(STORAGE_EXPANDED, dup.conversation.id)
      followUpQuestion.value = ''
      ElMessage.info('该业务问题已存在，已为你直接打开历史分析记录')
      return
    }
    if (!datasetSessionIds.value.length) {
      // 该数据集尚未生成过完整分析：直接走完整分析流程，
      // 以当前业务问题作为首个分析，避免「请先生成完整分析」的阻塞。
      const newAnalysis = await startAnalysis({
        dataset_id: selectedSession.value.dataset_id,
        question: followUpQuestion.value,
        strategy_goal: form.value.strategy_goal,
        analysis_window: form.value.analysis_window,
        session_name: `${selectedSession.value.dataset_name} 分析项目`,
      })
      await pollAnalysis(newAnalysis.id)
      ElMessage.success('已为该数据集生成首个业务分析记录')
      followUpQuestion.value = ''
      await refreshSessions()
      const created = sessions.value.find(
        (item) => item.dataset_id === selectedSession.value?.dataset_id,
      )
      if (created) await openSession(created)
      return
    }
    // 复用该数据集下的某个分析项目继续追问（业务问题沉淀为独立业务记录）
    const targetSessionId = datasetSessionIds.value[0]
    const newAnalysis = await continueSession(targetSessionId, {
      question: followUpQuestion.value,
      strategy_goal: form.value.strategy_goal,
      analysis_window: form.value.analysis_window,
    })
    await pollAnalysis(newAnalysis.id)
    ElMessage.success('已为该数据集生成新的业务分析记录')
    followUpQuestion.value = ''
    await openSession(selectedSession.value)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    followUpBusy.value = false
  }
}

const workspaceAnalysis = ref<Analysis | null>(null)

// 当前展开的业务记录（历史结果已从后端完整持久化，直接读取，无需懒加载）
const expandedRecord = computed<AnalysisRecord | null>(
  () => sessionDetail.value?.conversations.find((item) => item.id === expandedRecordId.value) ?? null,
)
const recordInsights = computed<Insight[]>(() => expandedRecord.value?.insight_result ?? [])
const recordStrategyCards = computed<StrategyCard[]>(() => expandedRecord.value?.strategy_result ?? [])
const recordEvents = computed<AuditEvent[]>(
  () => expandedRecord.value?.agent_trace?.map((item): AuditEvent => ({ agent: item.agent, event_type: item.action, payload: { output: item.output }, created_at: '' })) ?? [],
)

function toggleRecord(record: AnalysisRecord) {
  const open = expandedRecordId.value !== record.id
  expandedRecordId.value = open ? record.id : null
  if (open) {
    localStorage.setItem(STORAGE_EXPANDED, record.id)
  } else {
    localStorage.removeItem(STORAGE_EXPANDED)
  }
}

const workspaceResult = computed<AnalysisResult | null>(() => {
  if (workspaceAnalysis.value?.status !== 'completed') return null
  return workspaceAnalysis.value.result as AnalysisResult
})

async function loadRecordResult(record?: AnalysisRecord) {
  if (!record) return
  try {
    const loaded = await getAnalysis(record.analysis_id)
    analysis.value = loaded
    if (loaded.status === 'completed') {
      events.value = await getEvents(record.analysis_id)
      selectedCard.value = 0
      activeResultTab.value = 'overview'
    }
  } catch {
    analysis.value = null
  }
}

// 业务分析记录编号：按业务问题创建时间正序（最早=#1），与列表展示顺序无关
function recordOrderNumber(record: AnalysisRecord): number {
  const list = sessionDetail.value?.conversations ?? []
  const sorted = [...list].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )
  return sorted.findIndex((item) => item.id === record.id) + 1
}

// 判断业务问题是否为空或仅含标点/问号（无实际语义）
function isBlankQuestion(question: string): boolean {
  const q = (question ?? "").trim()
  if (!q) return true
  return !/[0-9a-zA-Z\u4e00-\u9fff]/.test(q)
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).filter(Boolean)
  if (typeof value === 'string') {
    return value
      .split(/[、，,;\s]+/)
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return []
}

function insightTags(item: Insight | undefined): string[] {
  if (!item) return []
  const tags = asList(item.top_tags)
  return (tags.length ? tags : asList(item.persona_tags)).slice(0, 3)
}

function predictedInterests(item: Insight): string[] {
  const interests = asList(item.predicted_interests)
  return (interests.length ? interests : asList(item.interests)).slice(0, 3)
}

function opportunityLabel(level?: string): string {
  return { high: '高', medium: '中', low: '低' }[level ?? ''] ?? '—'
}

function directInterests(item: Insight): string[] {
  return asList(item.interest_profile?.direct_interests).slice(0, 3)
}

function behaviorInterests(item: Insight): string[] {
  return asList(item.interest_profile?.behavior_interests).slice(0, 3)
}

// 根据数据集文件名自动生成会话名称（用户未自定义时使用）
function deriveSessionName(fileName: string): string {
  const base = fileName.replace(/\.[^.]+$/, '').replace(/[_\-]+/g, ' ').trim()
  const hasCn = /[一-龥]/.test(base)
  if (hasCn) return `${base}消费分析`
  return `${base} 用户消费分析`
}

function openFilePicker() {
  if (!busy.value) fileInputRef.value?.click()
}

function isSupportedFile(file: File) {
  return /\.(csv|xlsx|xls)$/i.test(file.name)
}

async function handleFile(file: File) {
  if (!isSupportedFile(file)) {
    ElMessage.error('请上传 CSV、XLSX 或 XLS 文件')
    return
  }
  busy.value = true
  resetResults()
  try {
    dataset.value = await uploadDataset(file)
    resetResults()
    // 需求四：若数据集已存在且已有沉淀资产，直接进入历史 Dataset Detail，不重新生成洞察
    try {
      const asset = await getDatasetAsset(dataset.value.id)
      if (asset.has_asset) {
        ElMessage.success('该数据集已存在，已为你直接打开历史分析项目')
        activeView.value = 'list'
        await refreshSessions()
        const existing = sessions.value.find((item) => item.id === dataset.value?.id)
        if (existing) await openSession(existing)
        return
      }
    } catch {
      /* 资产尚未就绪时继续走新建分析流程 */
    }
    ElMessage.success('数据已上传，用户洞察预览已生成')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busy.value = false
  }
}

function onFileInput(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void handleFile(file)
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void handleFile(file)
}

async function useDemo() {
  busy.value = true
  resetResults()
  try {
    dataset.value = await createDemoDataset()
    resetResults()
    ElMessage.success('示例数据已载入')
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busy.value = false
  }
}

async function runAnalysis() {
  if (!dataset.value) {
    ElMessage.warning('请先上传数据或载入示例数据')
    return
  }
  if (!form.value.question.trim()) {
    ElMessage.warning('请输入业务问题')
    return
  }
  busy.value = true
  activeResultTab.value = 'overview'
  selectedCard.value = 0
  analysis.value = null
  events.value = []
  try {
    const name = sessionName.value.trim() || deriveSessionName(dataset.value.name)
    analysis.value = await startAnalysis({
      dataset_id: dataset.value.id,
      question: form.value.question,
      strategy_goal: form.value.strategy_goal,
      analysis_window: form.value.analysis_window,
      session_name: name,
    })
    await pollAnalysis(analysis.value.id)
    ElMessage.success('分析已完成，已为你创建分析会话')
    // 生成后回到会话列表并打开新建的会话
    activeView.value = 'list'
    await refreshSessions()
    const created = sessions.value.find((item) => item.name === name) ?? sessions.value[0]
    if (created) await openSession(created)
  } catch (error) {
    ElMessage.error((error as Error).message)
  } finally {
    busy.value = false
  }
}

async function pollAnalysis(id: string) {
  if (!id) {
    throw new Error('分析任务创建失败，未返回任务标识，请重试。')
  }
  const deadline = Date.now() + 240_000
  while (Date.now() < deadline) {
    const [latest, latestEvents] = await Promise.all([getAnalysis(id), getEvents(id)])
    analysis.value = latest
    events.value = latestEvents
    if (latest.status === 'completed') {
      await nextTick()
      ElMessage.success('完整用户洞察和策略已生成')
      return
    }
    if (latest.status === 'failed') throw new Error(latest.error_message || '分析失败')
    await new Promise((resolve) => window.setTimeout(resolve, 900))
  }
  throw new Error('任务仍在运行，请稍后刷新查看')
}

function eventLabel(event: AuditEvent): string {
  const labels: Record<string, string> = {
    plan_created: '任务拆解完成',
    tool_started: '读取与校验数据',
    tool_completed: '完成人群识别',
    insights_created: '生成用户洞察',
    strategy_cards_created: '生成策略卡',
    evaluation_completed: '完成结果评估',
  }
  return labels[event.event_type] ?? event.event_type
}

function agentLabel(agent: string): string {
  return {
    orchestrator: 'Orchestrator',
    data_agent: 'Data Agent',
    insight_agent: 'Insight Agent',
    knowledge_agent: 'Knowledge Agent',
    strategy_agent: 'Strategy Agent',
    evaluator: 'Evaluator',
  }[agent] ?? agent
}

function intentLabel(intent: string): string {
  return {
    customer_analysis: '客户分析',
    marketing_strategy: '营销策略',
    market_research: '市场研究',
  }[intent] ?? intent
}

function featureLabel(feature: string): string {
  return {
    total_purchase_amount: '实际购买金额',
    purchase_order_count: '购买订单数',
    average_purchase_value: '平均客单价',
    recency_days: '最近消费间隔',
    category_concentration: '消费集中度',
    unique_category_count: '品类多样性',
    weighted_purchase_value: '加权高价值行为',
    active_days: '活跃天数',
  }[feature] ?? feature
}

// 应用启动时自动恢复：加载会话列表，并回到上次选中的数据集会话（数据已在数据库持久化）
onMounted(async () => {
  try {
    await refreshSessions()
  } catch {
    sessions.value = []
  }
})

</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><MagicStick /></div>
        <div>
          <strong>群策</strong>
          <span>Customer Intelligence</span>
        </div>
      </div>

      <button class="compose-button" :disabled="busy" @click="startCompose">
        <Document /> 新建分析会话
      </button>

      <div class="history-head-mini">
        <span class="eyebrow">数据集</span>
      </div>
      <nav class="session-list" aria-label="数据集列表">
        <button
          v-for="record in sessions"
          :key="record.id"
          :class="['session-item', { active: selectedSession?.id === record.id }]"
          @click="openSession(record)"
        >
          <Document class="session-icon" />
          <div class="session-item-main">
            <strong>{{ datasetDisplayName(record) }}</strong>
            <span>业务分析记录：{{ record.stats.conversation_count }}</span>
            <small>更新于 {{ formatTime(record.updated_at) }}</small>
          </div>
          <div class="session-item-actions">
            <button class="session-rename" title="重命名" @click="openRenameDialog(record)">✎</button>
            <button class="session-delete" title="删除" @click="removeSession(record, $event)">×</button>
          </div>
        </button>
        <div v-if="!sessions.length" class="session-empty">还没有数据集。点击「新建分析会话」开始。</div>
      </nav>

      <div class="architecture-card">
        <div class="eyebrow light">3+1 AGENT SYSTEM</div>
        <div class="agent-orbit">
          <span>O</span>
          <i class="dot dot-1">D</i>
          <i class="dot dot-2">I</i>
          <i class="dot dot-3">S</i>
        </div>
        <p>Orchestrator 协同 Data、Insight、Strategy 三个 Agent，从数据到洞察再到策略。</p>
      </div>
    </aside>

    <main class="workspace">
      <!-- ============ 新建分析流程 ============ -->
      <template v-if="activeView === 'compose'">
        <header class="topbar">
          <div>
            <div class="eyebrow">AI CUSTOMER INTELLIGENCE · 新建分析会话</div>
            <h1>上传数据，生成完整客户洞察与营销策略</h1>
            <p>一个数据集对应一个分析会话。完成分析后会自动创建会话，之后每次业务追问都会沉淀在会话内，无需重新上传。</p>
          </div>
          <div class="status-pill">
            <span class="pulse"></span>
            {{ analysis?.status === 'running' ? 'Agents 工作中' : dataset ? '数据已就绪' : '等待数据' }}
          </div>
        </header>

        <section class="session-name-row">
          <label class="field">
            <span>会话名称（可选，留空将按数据集自动命名）</span>
            <input v-model="sessionName" placeholder="例如：手机用户营销分析" />
          </label>
        </section>

        <section class="control-strip">
          <article class="panel upload-card" :class="{ done: analysis?.status === 'completed' }">
            <div class="panel-title">
              <span>01</span>
              <div>
                <h2>数据接入</h2>
                <p>支持 CSV / Excel，上传后立即生成洞察预览。</p>
              </div>
              <span v-if="analysis?.status === 'completed'" class="module-done"><Check /> 已完成</span>
            </div>
            <input ref="fileInputRef" class="file-input" type="file" accept=".csv,.xlsx,.xls" @change="onFileInput" />
            <button
              v-if="!analysis || analysis.status !== 'completed'"
              type="button"
              :class="['dropzone', { dragging }]"
              :disabled="busy"
              @click="openFilePicker"
              @dragenter.prevent="dragging = true"
              @dragover.prevent="dragging = true"
              @dragleave.prevent="dragging = false"
              @drop.prevent="onDrop"
            >
              <UploadFilled />
              <strong>{{ busy ? '正在生成洞察预览...' : dataset ? dataset.name : '拖入文件或点击上传' }}</strong>
              <span>{{ dataset ? `${dataset.row_count.toLocaleString()} 条记录` : 'CSV / XLSX / XLS，最大 25 MB' }}</span>
            </button>
            <button v-if="!analysis || analysis.status !== 'completed'" class="text-button" :disabled="busy" @click="useDemo">
              载入示例数据 <ArrowRight />
            </button>
            <div v-else class="done-meta">
              <span>文件：{{ dataset?.name }}</span>
              <span>规模：{{ dataset ? dataset.row_count.toLocaleString() : 0 }} 条记录</span>
            </div>
          </article>

          <article class="panel quality-card" :class="{ empty: !dataset, done: analysis?.status === 'completed' }">
            <div class="panel-title">
              <span>02</span>
              <div>
                <h2>数据体检</h2>
                <p>判断字段完整度、可分析性和样本覆盖。</p>
              </div>
              <span v-if="analysis?.status === 'completed'" class="module-done"><Check /> 已完成</span>
            </div>
            <template v-if="dataset">
              <div class="quality-body">
                <div class="score-ring" :class="scoreTone">
                  <strong>{{ dataset.quality.analyzability_score }}</strong>
                  <span>可分析</span>
                </div>
                <div class="quality-metrics">
                  <div><span>有效记录</span><strong>{{ dataset.quality.usable_row_count.toLocaleString() }}</strong></div>
                  <div><span>独立用户</span><strong>{{ dataset.quality.user_count.toLocaleString() }}</strong></div>
                  <div><span>品类覆盖</span><strong>{{ Math.round(dataset.quality.category_coverage * 100) }}%</strong></div>
                </div>
              </div>
              <div v-if="dataset.quality.issues.length" class="issue-list">
                <div v-for="issue in dataset.quality.issues" :key="issue.code" :class="['issue', issue.severity]">
                  <Warning /> {{ issue.message }}
                </div>
              </div>
              <div v-else class="quality-ok"><Check /> 数据结构完整，可以继续分析</div>
            </template>
            <div v-else class="empty-state"><DataAnalysis /><span>上传后显示体检结果</span></div>
          </article>
        </section>

        <section v-if="dataset" class="insight-board">
          <div class="board-head">
            <div>
              <div class="eyebrow">USER INTELLIGENCE</div>
              <h2>用户洞察工作台</h2>
              <p>这里是使用者理解用户的主入口。先看人群和证据，再决定业务问题怎么问。</p>
            </div>
            <button class="secondary-button" :disabled="busy || !dataset?.quality.can_analyze" @click="runAnalysis">
              <MagicStick />
              {{ result ? '重新分析' : '生成智能分析' }}
            </button>
          </div>

          <div class="board-status">
            <span v-if="result">完整洞察已生成，下面展示全量分析结果。</span>
            <span v-else-if="analysis?.status === 'running'">Agent 正在生成完整用户洞察和策略。</span>
            <span v-else>数据已就绪，可以生成完整用户洞察。</span>
          </div>

          <div v-if="uploadPreview" class="summary-grid">
            <div><span>预览样本</span><strong>{{ uploadPreview.sample_row_count.toLocaleString() }}</strong></div>
            <div><span>总记录</span><strong>{{ dataset.row_count.toLocaleString() }}</strong></div>
            <div><span>独立用户</span><strong>{{ dataset.quality.user_count.toLocaleString() }}</strong></div>
            <div><span>时间范围</span><strong>{{ uploadPreview.date_range || '待识别' }}</strong></div>
          </div>

          <div v-if="consumptionInsight" class="consumption-trend">
            <div class="trend-head">
              <div>
                <div class="eyebrow">CONSUMPTION TREND</div>
                <h3>整体消费趋势</h3>
                <p>{{ consumptionInsight.summary }}</p>
              </div>
            </div>
            <div class="trend-cards">
              <div class="trend-col">
                <h4>消费贡献 Top 品类</h4>
                <ul>
                  <li v-for="cat in consumptionInsight.category_spend_distribution?.slice(0, 4)" :key="cat.category">
                    <span>{{ cat.category_cn }}</span>
                    <i>金额 {{ Math.round((cat.spend_share ?? 0) * 100) }}%</i>
                  </li>
                </ul>
              </div>
              <div class="trend-col">
                <h4>用户覆盖 Top 品类</h4>
                <ul>
                  <li v-for="cat in consumptionInsight.category_user_distribution?.slice(0, 4)" :key="cat.category">
                    <span>{{ cat.category_cn }}</span>
                    <i>覆盖 {{ Math.round((cat.user_share ?? 0) * 100) }}%</i>
                  </li>
                </ul>
              </div>
              <div class="trend-col" v-if="consumptionInsight.recent_activity_pattern">
                <h4>近期活动模式</h4>
                <ul>
                  <li v-if="consumptionInsight.recent_activity_pattern.high_ticket_category">
                    <span>高客单品类</span>
                    <i>{{ consumptionInsight.recent_activity_pattern.high_ticket_category }}</i>
                  </li>
                  <li v-if="consumptionInsight.recent_activity_pattern.peak_hours?.length">
                    <span>活跃时段</span>
                    <i>{{ consumptionInsight.recent_activity_pattern.peak_hours.join(':00, ') }}:00</i>
                  </li>
                  <li>
                    <span>近期活跃</span>
                    <i>30天内 {{ Math.round((consumptionInsight.recent_activity_pattern.recent_30d_event_share ?? 0) * 100) }}% 事件</i>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div v-if="insightPanelCards.length" class="insight-layout">
            <article class="panel chart-card">
              <h3>人群规模分布</h3>
              <v-chart class="segment-chart" :option="segmentChart" autoresize />
              <div class="chart-divider"></div>
              <h3>人群结构占比</h3>
              <v-chart class="mix-chart" :option="categoryMixChart" autoresize />
            </article>
            <div class="persona-list">
              <article v-for="item in insightPanelCards" :key="item.segment.segment_id" class="persona-row">
                <div class="persona-main">
                  <div>
                    <h3>{{ item.segment.name }}</h3>
                    <span>人群占比 {{ Math.round(item.segment.share * 100) }}% · {{ item.segment.user_count.toLocaleString() }} 人</span>
                  </div>
                  <span v-if="item.segment.opportunity_level" :class="['opportunity-badge', item.segment.opportunity_level]">
                    运营优先级：{{ opportunityLabel(item.segment.opportunity_level) }}
                    <small v-if="item.segment.opportunity_score != null">（{{ item.segment.opportunity_score }}）</small>
                  </span>
                </div>
                <div v-if="item.segment.opportunity_reason?.length" class="opportunity-reason">
                  <span class="reason-label">推荐优先运营</span>
                  <ul>
                    <li v-for="reason in item.segment.opportunity_reason" :key="reason">{{ reason }}</li>
                  </ul>
                </div>
                <p>{{ item.summary }}</p>
                <div v-if="item.insight" class="insight-detail-block">
                  <div class="tier-line">
                    <span>价值层级</span>
                    <strong>{{ item.insight.value_tier }}</strong>
                  </div>
                  <div class="metric-line" v-if="item.segment.statistics">
                    <span>平均消费 ¥{{ Math.round(Number(item.segment.statistics.average_spend || 0)).toLocaleString() }}</span>
                    <span>平均次数 {{ Math.round(Number(item.segment.statistics.average_frequency || 0)) }} 次</span>
                  </div>
                  <div class="tag-group">
                    <span v-for="tag in insightTags(item.insight)" :key="tag">{{ tag }}</span>
                  </div>
                  <div class="detail-columns">
                    <div>
                      <h4>直接关联兴趣</h4>
                      <ul>
                        <li v-for="interest in (directInterests(item.insight).length ? directInterests(item.insight) : predictedInterests(item.insight))" :key="interest">{{ interest }}</li>
                        <li v-if="!directInterests(item.insight).length && !predictedInterests(item.insight).length">暂无明确品类信号</li>
                      </ul>
                    </div>
                    <div>
                      <h4>行为推断兴趣</h4>
                      <ul>
                        <li v-for="interest in behaviorInterests(item.insight)" :key="interest">{{ interest }}</li>
                        <li v-if="!behaviorInterests(item.insight).length">常规稳定消费</li>
                      </ul>
                    </div>
                    <div>
                      <h4>品类偏好</h4>
                      <ul>
                        <li v-for="pref in (item.insight.category_preference || []).slice(0, 3)" :key="pref">{{ pref }}</li>
                        <li v-if="item.insight.brand_preference?.length">品牌：{{ item.insight.brand_preference.join('、') }}</li>
                      </ul>
                    </div>
                  </div>
                </div>
                <div class="evidence-chips">
                  <span v-for="evidence in item.segment.evidence.slice(0, 3)" :key="evidence.metric">
                    {{ evidence.metric }}：{{ evidence.value }}
                  </span>
                </div>
                <div v-if="item.segment.recommended_strategy" class="strategy-hint">
                  <span>推荐策略</span>
                  <p>{{ item.segment.recommended_strategy }}</p>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section class="question-card">
          <div class="panel-title">
            <span>03</span>
            <div>
              <h2>业务分析</h2>
              <p>结合上方用户洞察，告诉 Agent 你要做的产品或运营决策。提交后会创建分析会话。</p>
            </div>
          </div>
          <div class="question-layout">
            <label class="field main-field">
              <span>业务问题</span>
              <textarea v-model="form.question" rows="3" placeholder="例如：哪些用户适合下一期新品推广？" />
            </label>
            <div class="field-stack">
              <label class="field">
                <span>输出目标</span>
                <input v-model="form.strategy_goal" placeholder="例如：输出用户画像、人群策略、营销方案" />
              </label>
            </div>
          </div>
          <div class="question-actions">
            <div class="guardrail"><Check /> 只向模型发送聚合证据，不发送原始交易明细</div>
            <button class="primary-button" :disabled="busy || !dataset?.quality.can_analyze" @click="runAnalysis">
              <MagicStick />
              {{ busy ? 'Agent 正在协作...' : '生成智能分析' }}
            </button>
          </div>
        </section>

        <section v-if="events.length || analysis?.status === 'running'" class="pipeline">
          <div class="pipeline-title">
            <div>
              <span class="eyebrow">LIVE WORKFLOW</span>
              <h2>Agent 协作轨迹</h2>
            </div>
            <span>{{ events.length }} 个关键节点</span>
          </div>
          <div v-if="result?.agent_delegation" class="delegation-row">
            <span class="delegation-label">本次编排</span>
            <span
              v-for="(active, agent) in result.agent_delegation"
              :key="agent"
              :class="['delegation-chip', { on: active }]"
            >
              {{ agentLabel(agent) }}
            </span>
          </div>
          <div v-if="result?.agent_plan?.length" class="plan-row">
            <span class="delegation-label">执行计划</span>
            <span v-for="(step, idx) in result.agent_plan" :key="step" class="plan-step">
              <i>{{ idx + 1 }}</i>{{ step }}
            </span>
          </div>
          <div v-if="result?.intent" class="intent-row">
            <span class="delegation-label">任务意图</span>
            <span class="intent-chip">{{ intentLabel(result.intent) }}</span>
            <span class="intent-reason">{{ result.reasoning }}</span>
          </div>
          <div class="pipeline-track">
            <div v-for="(event, index) in events" :key="`${event.event_type}-${index}`" class="pipeline-event">
              <div class="event-dot"><Check /></div>
              <div>
                <strong>{{ agentLabel(event.agent) }}</strong>
                <span>{{ eventLabel(event) }}</span>
              </div>
            </div>
          </div>
        </section>

        <section v-if="analysis?.status === 'failed'" class="panel error-panel">
          <div class="panel-title">
            <span>!</span>
            <div>
              <h2>分析失败</h2>
              <p>{{ analysis.error_message || '模型或后端服务暂时不可用，请稍后重试。' }}</p>
            </div>
          </div>
        </section>

        <section v-if="result?.strategy_cards.length" class="results-section">
          <div class="result-heading">
            <div>
              <span class="eyebrow">DECISION OUTPUT</span>
              <h2>{{ result.executive_summary }}</h2>
            </div>
            <div class="result-badges">
              <span>{{ result.model_mode === 'llm_enhanced' ? '模型增强' : '确定性基线' }}</span>
              <span>证据覆盖 {{ Math.round(result.evaluation.evidence_coverage * 100) }}%</span>
              <span v-if="result.segment_method">
                分群方式：{{ result.segment_method === 'category_preference' ? '品类偏好分群' : result.segment_method }}
              </span>
            </div>
          </div>

          <div class="strategy-workbench">
            <div class="segment-tabs" role="tablist" aria-label="人群策略">
              <button
                v-for="(card, index) in result.strategy_cards"
                :key="card.segment_id"
                :class="{ active: selectedCard === index }"
                @click="selectedCard = index"
              >
                <span>{{ card.segment_name }}</span>
                <small>人群占比 {{ Math.round((result.segments[index]?.share ?? 0) * 100) }}% · {{ result.segments[index]?.user_count ?? 0 }} 人</small>
                <small v-if="result.segments[index]?.opportunity_level" :class="['tab-opportunity', result.segments[index]?.opportunity_level]">
                  运营优先级 {{ opportunityLabel(result.segments[index]?.opportunity_level) }}
                </small>
              </button>
            </div>

            <div v-if="currentCard" class="strategy-detail">
              <div class="detail-nav">
                <button :class="{ active: activeResultTab === 'overview' }" @click="activeResultTab = 'overview'">策略卡</button>
                <button :class="{ active: activeResultTab === 'evidence' }" @click="activeResultTab = 'evidence'">证据与限制</button>
                <button :class="{ active: activeResultTab === 'page' }" @click="activeResultTab = 'page'">页面方向</button>
              </div>

              <div v-if="activeResultTab === 'overview'" class="detail-grid">
                <article class="strategy-main">
                  <span class="eyebrow">完整营销方案</span>
                  <h3>{{ currentCard.opportunity }}</h3>

                  <div v-if="currentCard.target_positioning" class="plan-block">
                    <h4>1 · 人群定位</h4>
                    <p>{{ currentCard.target_positioning }}</p>
                  </div>
                  <div v-if="currentCard.marketing_goal" class="plan-block">
                    <h4>2 · 营销目标</h4>
                    <p>{{ currentCard.marketing_goal }}</p>
                  </div>
                  <div v-if="currentCard.content_strategy" class="plan-block">
                    <h4>3 · 内容策略</h4>
                    <p>{{ currentCard.content_strategy }}</p>
                  </div>
                  <div v-if="currentCard.product_strategy" class="plan-block">
                    <h4>4 · 商品策略</h4>
                    <p>{{ currentCard.product_strategy }}</p>
                  </div>
                  <div v-if="currentCard.promotion_strategy" class="plan-block">
                    <h4>5 · 促销策略</h4>
                    <p>{{ currentCard.promotion_strategy }}</p>
                  </div>
                  <div v-if="currentCard.ad_theme || currentCard.ad_elements?.length" class="plan-block">
                    <h4>6 · 广告主题</h4>
                    <p v-if="currentCard.ad_theme"><strong>{{ currentCard.ad_theme }}</strong></p>
                    <div v-if="currentCard.ad_elements?.length" class="ad-elements">
                      <span class="sub-label">广告元素</span>
                      <div class="chip-group">
                        <span v-for="el in currentCard.ad_elements" :key="el">{{ el }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="currentCard.channels?.length" class="plan-block">
                    <h4>7 · 推荐渠道</h4>
                    <div class="channel-line">{{ currentCard.channels.join(' · ') }}</div>
                  </div>

                  <h4>商品机制 / 代表性权益</h4>
                  <div class="chip-group">
                    <span v-for="item in currentCard.product_mechanisms" :key="item">{{ item }}</span>
                  </div>
                  <ul class="check-list">
                    <li v-for="item in currentCard.benefits" :key="item"><Check />{{ item }}</li>
                  </ul>

                  <div v-if="currentCard.recommended_products?.length" class="plan-block">
                    <h4>推荐商品组合</h4>
                    <div class="chip-group">
                      <span v-for="p in currentCard.recommended_products" :key="p">{{ p }}</span>
                    </div>
                  </div>

                  <template v-if="currentCard.strategy_basis">
                    <h4>10 · 策略依据</h4>
                    <div class="basis-block">
                      <div v-if="currentCard.strategy_basis.data?.length" class="basis-col">
                        <span class="basis-label">数据依据</span>
                        <ul>
                          <li v-for="item in currentCard.strategy_basis.data" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                      <div v-if="currentCard.strategy_basis.knowledge?.length" class="basis-col">
                        <span class="basis-label knowledge">知识依据（RAG）</span>
                        <ul>
                          <li v-for="item in currentCard.strategy_basis.knowledge" :key="item">{{ item }}</li>
                        </ul>
                      </div>
                    </div>
                  </template>
                </article>

                <article class="slogan-card">
                  <Promotion />
                  <span>一句话文案示例</span>
                  <blockquote>{{ currentCard.slogans[0] }}</blockquote>
                  <div class="alternatives">
                    <span v-for="item in currentCard.slogans.slice(1)" :key="item">{{ item }}</span>
                  </div>
                </article>
                <article class="metrics-card">
                  <h4>9 · 效果指标</h4>
                  <div class="metric-tags">
                    <span v-for="metric in (currentCard.metrics?.length ? currentCard.metrics : currentCard.validation_metrics)" :key="metric">{{ metric }}</span>
                  </div>
                  <h4 v-if="currentCard.marketing_direction" style="margin-top:14px">营销方向</h4>
                  <p v-if="currentCard.marketing_direction" class="muted-note">{{ currentCard.marketing_direction }}</p>
                </article>
              </div>

              <div v-else-if="activeResultTab === 'evidence'" class="evidence-view">
                <article>
                  <h3>行为证据</h3>
                  <div class="evidence-list">
                    <div v-for="item in result.segments[selectedCard]?.evidence" :key="item.metric">
                      <span>{{ item.metric }}</span>
                      <strong>{{ item.value }}</strong>
                      <small>{{ item.benchmark }}</small>
                      <p>{{ item.interpretation }}</p>
                    </div>
                  </div>
                </article>
                <article class="caution-card">
                  <Warning />
                  <div>
                    <h3>解释边界</h3>
                    <p v-for="item in currentInsight?.alternative_explanations" :key="item">{{ item }}</p>
                    <p v-for="item in currentCard.limitations" :key="item">{{ item }}</p>
                  </div>
                </article>
              </div>

              <div v-else class="page-view">
                <article class="page-mock">
                  <div class="mock-topline"><span></span><span></span><span></span></div>
                  <div class="mock-hero">
                    <small>{{ currentCard.page.theme }}</small>
                    <h3>{{ currentCard.page.hero_title }}</h3>
                    <p>{{ currentCard.page.hero_subtitle }}</p>
                    <button>立即开启</button>
                  </div>
                  <div class="mock-modules">
                    <div v-for="module in currentCard.page.modules" :key="module">{{ module }}</div>
                  </div>
                </article>
                <article class="page-spec">
                  <span class="eyebrow">页面要素</span>
                  <h3>关键词</h3>
                  <p>用于页面主题、视觉元素和推荐内容</p>
                  <div class="chip-group">
                    <span v-for="keyword in currentCard.page.visual_keywords" :key="keyword">{{ keyword }}</span>
                  </div>
                  <div class="draft-note"><Warning /> 这是产品与视觉方向草案，仍需产品经理和设计师确认。</div>
                </article>
              </div>
            </div>
          </div>
        </section>
      </template>

      <!-- ============ 会话详情 ============ -->
      <template v-else>
        <div v-if="selectedSession && sessionDetail" class="session-detail">
          <header class="topbar">
            <div>
              <div class="eyebrow">AI CUSTOMER INTELLIGENCE · 分析会话</div>
              <h1>{{ selectedSession.name || '分析会话' }}</h1>
              <p>{{ selectedSession.summary || '该会话尚未生成摘要。' }}</p>
            </div>
            <div class="status-pill">
              <span class="pulse"></span>
              {{ selectedSession.status }}
            </div>
          </header>

          <div class="session-info-strip">
            <div><span>数据名称</span><strong>{{ datasetDisplayName(selectedSession) }}</strong></div>
            <div><span>创建时间</span><strong>{{ formatTime(selectedSession.created_at) }}</strong></div>
            <div><span>用户数量</span><strong>{{ assetResult ? assetResult.quality.user_count.toLocaleString() : (sessionDetail.session.stats.segment_count ? '—' : '—') }}</strong></div>
            <div><span>数据状态</span><strong>{{ selectedSession.status }}</strong></div>
            <div><span>业务记录</span><strong>{{ sessionDetail.conversations.length }}</strong></div>
          </div>

          <template v-if="assetResult">
            <!-- 用户洞察（统一结构：整体消费趋势 → 人群规模分布 → 人群结构占比 → 用户分群卡片） -->
            <section class="detail-section">
              <h2 class="section-title">用户洞察</h2>

              <!-- 1. 整体消费趋势 -->
              <div v-if="consumptionInsight" class="insight-sub-block">
                <h3 class="insight-sub-title">整体消费趋势</h3>
                <p class="trend-summary">{{ consumptionInsight.summary }}</p>
                <div class="trend-cards">
                  <div class="trend-col">
                    <h4>Top 消费品类（金额贡献）</h4>
                    <ul>
                      <li v-for="cat in consumptionInsight.category_spend_distribution?.slice(0, 4)" :key="cat.category">
                        <span>{{ cat.category_cn }}</span>
                        <i>金额 {{ Math.round((cat.spend_share ?? 0) * 100) }}%</i>
                      </li>
                    </ul>
                  </div>
                  <div class="trend-col">
                    <h4>用户覆盖 Top 品类</h4>
                    <ul>
                      <li v-for="cat in consumptionInsight.category_user_distribution?.slice(0, 4)" :key="cat.category">
                        <span>{{ cat.category_cn }}</span>
                        <i>覆盖 {{ Math.round((cat.user_share ?? 0) * 100) }}%</i>
                      </li>
                    </ul>
                  </div>
                  <div class="trend-col" v-if="consumptionInsight.recent_activity_pattern">
                    <h4>最近消费趋势与活跃时间</h4>
                    <ul>
                      <li v-if="consumptionInsight.recent_activity_pattern.high_ticket_category">
                        <span>高客单品类</span>
                        <i>{{ consumptionInsight.recent_activity_pattern.high_ticket_category }}</i>
                      </li>
                      <li v-if="consumptionInsight.recent_activity_pattern.peak_hours?.length">
                        <span>活跃时段</span>
                        <i>{{ consumptionInsight.recent_activity_pattern.peak_hours.join(':00, ') }}:00</i>
                      </li>
                      <li>
                        <span>近期活跃</span>
                        <i>30天内 {{ Math.round((consumptionInsight.recent_activity_pattern.recent_30d_event_share ?? 0) * 100) }}% 事件</i>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>

              <!-- 2. 人群规模分布 -->
              <div class="insight-sub-block">
                <h3 class="insight-sub-title">人群规模分布</h3>
                <p class="trend-summary" v-if="assetResult.executive_summary">{{ assetResult.executive_summary }} · 共识别 {{ insightPanelCards.length }} 个人群</p>
                <v-chart v-if="insightPanelCards.length" class="segment-chart" :option="segmentChart" autoresize />
                <div v-else class="history-empty detail">暂无人群规模数据。</div>
              </div>

              <!-- 3. 用户分群卡片 -->
              <div class="insight-sub-block">
                <h3 class="insight-sub-title">用户分群卡片</h3>
                <div v-if="insightPanelCards.length" class="history-card-grid">
                  <article v-for="item in insightPanelCards" :key="item.segment.segment_id" class="history-card segment">
                    <div class="persona-main">
                      <h4>{{ item.segment.name }}</h4>
                      <span v-if="item.segment.opportunity_level" :class="['opportunity-badge', item.segment.opportunity_level]">
                        运营优先级：{{ opportunityLabel(item.segment.opportunity_level) }}
                      </span>
                    </div>
                    <span class="scale-tag">规模 {{ item.segment.user_count.toLocaleString() }} 人 · {{ Math.round(item.segment.share * 100) }}%</span>
                    <p>{{ item.summary }}</p>
                    <div v-if="item.insight" class="insight-detail-block">
                      <div class="tier-line" v-if="item.insight.value_tier">
                        <span>价值层级</span>
                        <strong>{{ item.insight.value_tier }}</strong>
                      </div>
                      <div class="metric-line" v-if="item.segment.statistics">
                        <span>平均消费 ¥{{ Math.round(Number(item.segment.statistics.average_spend || 0)).toLocaleString() }}</span>
                        <span>平均次数 {{ Math.round(Number(item.segment.statistics.average_frequency || 0)) }} 次</span>
                      </div>
                      <div class="tag-group">
                        <span v-for="tag in insightTags(item.insight)" :key="tag">{{ tag }}</span>
                      </div>
                    </div>
                    <div class="detail-columns" v-if="item.insight">
                      <div>
                        <h5>品类偏好</h5>
                        <ul>
                          <li v-for="pref in (item.insight.category_preference || []).slice(0, 3)" :key="pref">{{ pref }}</li>
                        </ul>
                      </div>
                      <div>
                        <h5>品牌偏好</h5>
                        <ul>
                          <li v-if="item.insight.brand_preference?.length" v-for="brand in item.insight.brand_preference.slice(0, 3)" :key="brand">{{ brand }}</li>
                          <li v-if="!item.insight.brand_preference?.length">暂无品牌数据</li>
                        </ul>
                      </div>
                      <div>
                        <h5>商品特点</h5>
                        <ul>
                          <li v-for="feat in (item.insight.consumption_features || []).slice(0, 3)" :key="feat">{{ feat }}</li>
                        </ul>
                      </div>
                    </div>
                    <div v-if="item.segment.recommended_strategy" class="strategy-hint">
                      <span>消费特点</span>
                      <p>{{ item.segment.recommended_strategy }}</p>
                    </div>
                  </article>
                </div>
                <div v-else class="history-empty detail">暂无用户分群结果。</div>
              </div>
            </section>
          </template>

          <!-- 业务分析记录（折叠卡片，底部） -->
          <section class="detail-section">
            <h2 class="section-title">业务分析记录</h2>
            <div class="analysis-records">
              <div class="records-list">
                <article
                  v-for="record in sessionDetail.conversations"
                  :key="record.id"
                  class="record-card"
                  :class="{ open: record.id === expandedRecordId }"
                >
                  <header class="record-head" @click="toggleRecord(record)">
                    <div class="record-title">
                      <span class="record-index">#{{ recordOrderNumber(record) }}</span>
                      <div>
                        <p class="record-question">{{ isBlankQuestion(record.question) ? '未命名业务问题' : record.question }}</p>
                        <small>{{ formatTime(record.created_at) }}</small>
                      </div>
                    </div>
                    <span class="record-toggle">{{ record.id === expandedRecordId ? '收起' : '展开结果' }}</span>
                  </header>
                  <div v-if="record.id === expandedRecordId" class="record-body">
                    <p v-if="record.answer_summary" class="record-answer">{{ record.answer_summary }}</p>

                    <!-- 业务记录展开主要展示「营销策略」（用户洞察已在顶部用户洞察模块统一展示，避免重复） -->
                    <template v-if="expandedRecordId === record.id">
                      <!-- 营销策略 -->
                      <div v-if="recordStrategyCards.length" class="record-block">
                        <h4>营销策略</h4>
                        <div class="history-card-grid">
                          <article v-for="card in recordStrategyCards" :key="card.segment_id" class="history-card strategy">
                            <h4>{{ card.segment_name }}</h4>
                            <p>{{ card.opportunity }}</p>
                            <div v-if="card.target_positioning" class="card-sub"><strong>目标人群</strong>{{ card.target_positioning }}</div>
                            <div v-if="card.product_strategy" class="card-sub"><strong>产品定位</strong>{{ card.product_strategy }}</div>
                            <div v-if="card.marketing_goal" class="card-sub"><strong>营销方向</strong>{{ card.marketing_goal }}</div>
                            <div v-if="card.ad_theme" class="card-sub"><strong>广告主题</strong>{{ card.ad_theme }}</div>
                            <div v-if="card.ad_elements?.length" class="card-sub"><strong>广告元素</strong>{{ card.ad_elements.join(' · ') }}</div>
                            <div v-if="card.recommended_products?.length" class="card-sub"><strong>推荐商品</strong>{{ card.recommended_products.join('、') }}</div>
                            <div v-if="card.channels?.length" class="card-sub"><strong>推荐渠道</strong>{{ card.channels.join(' · ') }}</div>
                            <div v-if="card.product_mechanisms?.length" class="card-sub"><strong>活动机制</strong>{{ card.product_mechanisms.join('、') }}</div>
                            <div class="metric-tags">
                              <span v-for="metric in (card.metrics?.length ? card.metrics : card.validation_metrics).slice(0, 4)" :key="metric">{{ metric }}</span>
                            </div>
                          </article>
                        </div>
                      </div>

                      <div v-if="!recordStrategyCards.length" class="record-loading">
                        该业务问题暂无完整营销策略（可能分析未完成）。
                      </div>
                    </template>
                  </div>
                </article>
                <div v-if="!sessionDetail.conversations.length" class="history-empty detail">该会话还没有业务分析记录。</div>
              </div>
            </div>
          </section>

          <!-- 业务问题分析输入框 -->
          <section class="followup-box">
            <div class="followup-inner">
              <div class="followup-head">
                <strong>业务问题分析</strong>
                <span class="followup-hint">基于已有数据洞察生成新的营销策略，不重复执行完整分析</span>
              </div>
              <textarea
                v-model="followUpQuestion"
                rows="2"
                placeholder="请输入业务问题，例如：哪些用户适合下一期活动？如何提升某品类复购？如何设计会员体系？"
                @keydown.meta.enter="submitFollowUp"
                @keydown.ctrl.enter="submitFollowUp"
              />
              <div class="followup-actions">
                <span class="guardrail"><Check /> 复用当前数据集的洞察资产，仅调用 Strategy / Knowledge Agent</span>
                <button class="primary-button" :disabled="followUpBusy || !followUpQuestion.trim()" @click="submitFollowUp">
                  <MagicStick />
                  {{ followUpBusy ? 'Agent 正在协作...' : '生成业务策略' }}
                </button>
              </div>
            </div>
          </section>
        </div>

        <div v-else class="session-empty-detail">
          <UserFilled />
          <strong>选择一个分析会话，或新建一个</strong>
          <span>左侧是按最近更新排序的历史会话。点击进入后可查看完整洞察，并继续提出业务问题。</span>
          <button class="primary-button" @click="startCompose">新建分析会话</button>
        </div>
      </template>
    </main>
  </div>

  <el-dialog v-model="renameVisible" title="重命名数据集显示名称" width="420px">
    <p class="rename-hint">该名称仅用于左侧列表展示，不影响实际数据集文件。</p>
    <el-input
      v-model="renameInput"
      placeholder="留空则恢复为数据集文件名称"
      maxlength="50"
      show-word-limit
      @keyup.enter="confirmRename"
    />
    <template #footer>
      <el-button @click="renameVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmRename">确定</el-button>
    </template>
  </el-dialog>
</template>

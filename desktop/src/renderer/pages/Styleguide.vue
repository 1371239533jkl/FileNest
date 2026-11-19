<script setup lang="ts">
import { ref } from 'vue'
import AppButton from '../components/AppButton.vue'
import BarList from '../components/BarList.vue'
import DataTable, { type Column } from '../components/DataTable.vue'
import Panel from '../components/Panel.vue'
import StatCard from '../components/StatCard.vue'
import { renderMarkdown } from '../lib/markdown'

const MARKDOWN_SAMPLE = [
  '### 找到 2 个相关文件',
  '',
  '- **季度报告.pdf** — 2.4 MB，最后修改 11-18',
  '- `budget.xlsx` — 812 KB',
  '',
  '> 以下结论基于本地索引，不联网。',
  '',
  '| 类型 | 数量 |',
  '|------|------|',
  '| 文档 | 458 |',
  '| 图片 | 302 |',
  '',
  '```python',
  'print("hello")',
  '```',
  '',
  '参考 [文档](https://example.com)。',
].join('\n')

const COLORS = [
  ['背景', '--bg'], ['卡片', '--card'], ['描边', '--line'],
  ['主色', '--primary'], ['成功', '--ok'], ['警告', '--warn'],
  ['危险', '--danger'], ['强调', '--purple'],
]

const COLUMNS: Column[] = [
  { key: 'name', title: '名称', width: '1.5fr' },
  { key: 'type', title: '类型', width: '80px' },
  { key: 'size', title: '大小', width: '90px', align: 'right' },
]

const demoRows = [
  { id: 1, name: '季度报告.pdf', type: '文档', size: '2.4 MB' },
  { id: 2, name: 'screenshot.png', type: '图片', size: '812 KB' },
  { id: 3, name: 'main.py', type: '代码', size: '12 KB' },
]

const emptyRows = ref<any[]>([])
const loadingRows = ref<any[]>([])
</script>

<template>
  <div class="page">
    <header class="page-head">
      <div>
        <h1>组件</h1>
        <p>设计系统与组件状态总览（内部页，发布前移除导航入口）</p>
      </div>
    </header>

    <Panel title="色板" hint="tokens.css">
      <div class="swatches">
        <div v-for="[name, token] in COLORS" :key="token" class="swatch">
          <span class="chip" :style="{ background: `var(${token})` }" />
          <b>{{ name }}</b>
          <code>{{ token }}</code>
        </div>
      </div>
    </Panel>

    <Panel title="文字">
      <h1 class="demo-h1">页面标题 20px</h1>
      <h2 class="demo-h2">面板标题 13px</h2>
      <p class="demo-body">正文 14px，用于列表与说明文字。</p>
      <p class="demo-muted">次要文字 12px，用于时间、路径、辅助信息。</p>
    </Panel>

    <Panel title="Markdown 渲染" hint="markdown-it + DOMPurify">
      <div class="md" data-md-sample v-html="renderMarkdown(MARKDOWN_SAMPLE)" />
    </Panel>

    <Panel title="按钮">
      <div class="row">
        <AppButton>默认</AppButton>
        <AppButton variant="primary">主要</AppButton>
        <AppButton variant="ghost">次要</AppButton>
        <AppButton size="sm">小号</AppButton>
        <AppButton disabled>禁用</AppButton>
      </div>
    </Panel>

    <Panel title="统计卡">
      <div class="cards">
        <StatCard label="总文件数" value="23,100" sub="近 7 天新增 22,000" />
        <StatCard label="已分类" value="0" sub="覆盖率 0%" accent="var(--ok)" />
        <StatCard label="标签数" value="12" sub="关联 48 次" accent="var(--warn)" />
        <StatCard label="存储用量" value="249 MB" sub="回收区 0 项" accent="var(--purple)" />
      </div>
    </Panel>

    <Panel title="条形列表">
      <BarList
        :items="[
          { label: '文档', value: 458, sub: '458 · 30.6 MB', color: '#89b4fa' },
          { label: '其他', value: 422, sub: '422 · 29.9 MB', color: '#6b6b7b' },
          { label: '代码', value: 220, sub: '220 · 24.6 MB', color: '#a6e3a1' },
        ]"
      />
    </Panel>

    <div class="grid">
      <Panel title="表格 · 正常">
        <DataTable :rows="demoRows" :columns="COLUMNS" :row-height="40" />
      </Panel>
      <Panel title="表格 · 空态">
        <DataTable :rows="emptyRows" :columns="COLUMNS" empty-text="这里还没有数据" />
      </Panel>
      <Panel title="表格 · 加载中">
        <DataTable :rows="loadingRows" :columns="COLUMNS" loading />
      </Panel>
    </div>
  </div>
</template>

<style scoped>
.page { display: flex; flex-direction: column; gap: var(--space-4); }
.page-head h1 { margin: 0; font-size: 20px; }
.page-head p { margin: 2px 0 0; color: var(--dim); font-size: 12px; }
.swatches { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }
.swatch { display: flex; flex-direction: column; gap: 4px; }
.chip { height: 28px; border: 1px solid var(--line); border-radius: var(--radius-sm); }
.swatch b { font-size: 12px; font-weight: 500; }
.swatch code { color: var(--dim); font-size: 11px; font-family: var(--mono); }
.demo-h1 { margin: 0 0 4px; font-size: 20px; }
.demo-h2 { margin: 0 0 4px; font-size: 13px; }
.demo-body { margin: 0 0 4px; font-size: 14px; }
.demo-muted { margin: 0; color: var(--dim); font-size: 12px; }
.row { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--space-3); }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: var(--space-4); }
</style>

---
# https://vitepress.dev/reference/default-theme-home-page
layout: home

hero:
  name: 'CCT'
  text: '施工多目标优化系统'
  tagline: 基于 NSGA-II 的施工成本 · 工期 · 碳排放多目标优化
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quickstart
    - theme: alt
      text: 软件简介
      link: /guide/intro

features:
  - title: 📥 施工日报导入
    details: 上传施工日报 Excel，自动解析资源使用数据，经核对、分配到工序后入库，替代繁琐的手工录入。
  - title: 🧩 工序与资源管理
    details: 以项目为单位管理工序（任务）、依赖关系、资源字典与资源使用情况，支持关键路径与甘特图展示。
  - title: 🎯 NSGA-II 多目标优化
    details: 支持四种施工模式（标准 / 加速 / 低碳 / 加速低碳），以成本现值、工期、碳排放为目标求帕累托最优解集。
  - title: 📊 帕累托解集可视化
    details: 三维散点图展示帕累托前沿，支持方案对比、施工模式对比、最优解甘特图回放与多轮优化结果合并。
  - title: 🏷️ 碳排放标签与图表
    details: 扁平标签 + 分组管理，从资源 / 工序 / 用量三个粒度打标，自定义图表切片（标签组或/且），拆解碳排放构成。
  - title: 🔁 资源周转与约束
    details: 材料周转次数修正碳排放与成本；资源日用量上限作为优化约束，过滤不可行的施工方案。
---

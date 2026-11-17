<template>
  <router-view />
</template>

<script setup>
</script>

<style>
/* ---------------------------------------------------------------
   招聘登记处 · 基础视觉
   纸感底色 + 深青主色 + 日黄标记；字体全部使用系统字体，不下载外部字体
   --------------------------------------------------------------- */
:root {
  --paper: #f4eee2;
  --paper-raised: #fbf7ef;
  --ink: #1f1b16;
  --ink-soft: #5f574d;
  --ink-faint: #8a8074;
  --teal: #124c4a;
  --teal-deep: #0c3a38;
  --sun: #e0a526;
  --rule: #dccfba;
  --danger: #a93f32;

  --sans: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Helvetica, 'Segoe UI',
    Roboto, Arial, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft Yahei', sans-serif;
  --serif: 'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, 'Noto Serif',
    'Source Han Serif SC', serif;

  /* Vant 主题变量：一次覆盖，所有组件跟随 */
  --van-primary-color: var(--teal);
  --van-success-color: #2e6b4f;
  --van-danger-color: var(--danger);
  --van-text-color: var(--ink);
  --van-text-color-2: var(--ink-soft);
  --van-text-color-3: var(--ink-faint);
  --van-background: var(--paper);
  --van-background-2: var(--paper-raised);
  --van-border-color: var(--rule);
  --van-cell-background: transparent;
  --van-cell-font-size: 15px;
  --van-cell-vertical-padding: 13px;
  --van-cell-group-background: transparent;
  --van-field-label-color: var(--ink-soft);
  --van-field-label-width: 6.8em;
  --van-field-input-text-color: var(--ink);
  --van-field-placeholder-text-color: #a99e8f;
  --van-button-primary-background: var(--teal);
  --van-button-primary-border-color: var(--teal);
  --van-button-default-color: var(--teal);
  --van-button-default-border-color: var(--rule);
  --van-radius-md: 8px;
  --van-radius-lg: 10px;
  --van-popup-background: var(--paper-raised);
  --van-picker-background: var(--paper-raised);
  --van-checkbox-checked-icon-color: var(--teal);
  --van-checkbox-border-color: #b9ab95;
  --van-loading-spinner-color: var(--paper-raised);
}

html,
body {
  height: 100%;
}

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  min-height: 100%;
}

/* 纸质登记表的双细线，只用在标题区和分区标题 */
.hairline-double {
  border-top: 1px solid var(--rule);
  border-bottom: 3px double var(--rule);
}

/* 分区标题：衬线字 + 左侧细标记，替代 Vant 默认的小字标题 */
.van-cell-group__title {
  font-family: var(--serif);
  font-size: 1.02rem;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.01em;
  padding: 1.5rem 1.25rem 0.5rem;
}

.van-cell-group__title::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 0.92em;
  margin-right: 0.55rem;
  vertical-align: -0.08em;
  background: var(--sun);
}

/* 成组卡片：纸面 + 细边框，不用阴影和大的圆角 */
.van-cell-group--inset {
  margin: 0 1rem;
  border: 1px solid var(--rule);
  border-radius: 10px;
  background: var(--paper-raised);
  overflow: hidden;
}

.van-cell::after {
  border-color: #ece3d3;
}

/* iOS 在字号小于 16px 的输入框上会自动放大页面 */
.van-field__control {
  font-size: 16px;
  line-height: 1.4;
}

.van-field__label {
  font-size: 0.92rem;
}

/* 必填星号和标签之间留一点空隙，避免挤成 "*First Name" */
.van-field__label--required::before {
  margin-right: 4px;
}

.van-button--large {
  height: 50px;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0.01em;
}

.van-button--large.van-button--round {
  border-radius: 8px;
}
</style>

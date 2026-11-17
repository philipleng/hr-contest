<template>
  <div class="success-page">
    <div class="receipt">
      <div class="receipt-head">
        <van-icon name="passed" size="26" class="receipt-icon" />
        <h1>Application received</h1>
        <p class="desc">
          Thank you. A recruiter will contact you by phone or Messenger,
          using the number you provided.
        </p>
      </div>

      <div class="receipt-rule" />

      <p class="next-title">What happens next</p>
      <ol class="next-steps">
        <li>Our recruiter reviews your application.</li>
        <li>We contact you to schedule an interview.</li>
        <li>After you pass, we match you with employers.</li>
      </ol>
    </div>

    <van-button
      v-if="fbPageUsername"
      type="primary"
      size="large"
      block
      class="messenger-btn"
      @click="openMessenger"
    >
      <template #icon>
        <van-icon name="chat-o" size="20" />
      </template>
      Message our recruiter
    </van-button>

    <p v-if="fbPageUsername" class="messenger-hint">
      Opens Facebook Messenger. The conversation is saved, so we can reach you anytime.
    </p>

    <van-button plain size="large" block class="back-btn" @click="$router.push('/apply')">
      Submit another application
    </van-button>
  </div>
</template>

<script setup>
const rawFbUsername = (import.meta.env.VITE_FB_PAGE_USERNAME || '').trim()
const fbPageUsername = rawFbUsername && rawFbUsername !== 'your.fb.page' ? rawFbUsername : ''

function openMessenger() {
  if (!fbPageUsername) return
  window.location.href = `https://m.me/${encodeURIComponent(fbPageUsername)}`
}
</script>

<style scoped>
.success-page {
  max-width: 560px;
  margin: 0 auto;
  min-height: 100vh;
  padding: 1.75rem 1rem 2rem;
  box-sizing: border-box;
}
.receipt {
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: 10px;
  padding: 1.6rem 1.25rem 1.35rem;
}
.receipt-head {
  text-align: center;
}
.receipt-icon {
  color: var(--teal);
}
h1 {
  margin: 0.5rem 0 0.6rem;
  font-family: var(--serif);
  font-size: 1.55rem;
  font-weight: 600;
  line-height: 1.2;
  color: var(--teal);
}
.desc {
  margin: 0 auto;
  max-width: 30em;
  font-size: 0.9rem;
  line-height: 1.6;
  color: var(--ink-soft);
}
.receipt-rule {
  margin: 1.25rem 0 1rem;
  border-top: 3px double var(--rule);
}
.next-title {
  margin: 0 0 0.5rem;
  font-family: var(--serif);
  font-size: 1rem;
  font-weight: 600;
  color: var(--ink);
}
.next-steps {
  margin: 0;
  padding-left: 1.2rem;
  color: var(--ink-soft);
  font-size: 0.9rem;
  line-height: 1.75;
}
.messenger-btn {
  margin-top: 1.25rem;
}
.messenger-hint {
  margin: 0.65rem 0 0;
  font-size: 0.78rem;
  line-height: 1.5;
  color: var(--ink-faint);
  text-align: center;
}
.back-btn {
  margin-top: 1.25rem;
  color: var(--teal);
  border-color: var(--rule);
  background: transparent;
}
</style>

<script setup lang="ts">
const FEATURES = [
  { title: "See what's clear", desc: 'Find the details already in the message.' },
  { title: "Notice what's missing", desc: 'Spot anything you may want to clarify.' },
  { title: "Keep what's useful", desc: "Save a pattern you'd like to revisit." },
]
</script>

<template>
  <div class="home">
    <div class="hero">
      <h1>Read the room <br />without re-reading the email</h1>
      <p>Paste a message<br />Take a second look, then decide what comes next</p>
    </div>

    <div class="actions">
      <RouterLink to="/decode" class="btn btn--primary">Review a message</RouterLink>
      <RouterLink to="/study" class="btn btn--secondary">Open Study</RouterLink>
    </div>

    <div class="features">
      <div v-for="feature in FEATURES" :key="feature.title" class="feature">
        <strong>{{ feature.title }}</strong>
        <span>{{ feature.desc }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home {
  max-width: 640px;
  display: flex;
  flex-direction: column;
  gap: 26px;
  padding-top: 12px;
}

.hero {
  display: flex;
  flex-direction: column;
  gap: 14px;
  font-style: italic;
}

.hero h1 {
  font-family: var(--font-serif);
  font-size: 42px;
  line-height: 1.14;
  font-weight: 500;
  letter-spacing: -0.02em;
  margin: 0;
  color: var(--color-text);
}

.hero p {
  margin: 0;
  font-size: 16.5px;
  line-height: 1.62;
  color: var(--color-text-muted);
  max-width: 520px;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.btn {
  padding: 13px 22px;
  border-radius: var(--radius-sm);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
}

.btn--primary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary);
  color: var(--color-frame);
}

.btn--primary:hover {
  background: var(--color-primary-hover);
}

.btn--secondary {
  padding: 13px 20px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-frame);
  color: #4a453e;
}

.btn--secondary:hover {
  background: #f6f2ea;
}

.features {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1px;
  background: var(--color-border-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  overflow: hidden;
  margin-top: 6px;
}

@media (max-width: 720px) {
  .hero h1 {
    font-size: 31px;
  }

  .features {
    grid-template-columns: 1fr;
  }
}

.feature {
  background: var(--color-surface-soft);
  padding: 18px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.feature strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.feature span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}
</style>

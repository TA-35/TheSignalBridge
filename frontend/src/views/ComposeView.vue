<script setup lang="ts">
// Not built yet. This page exists because /compose is routed and reachable
// from the nav, and a route that resolves to the words "Coming Soon..." tells
// someone nothing about what they found or where to go instead.
</script>

<template>
  <div class="soon">
    <span class="soon__badge">Coming soon</span>
    <h1>Compose</h1>
    <p class="soon__lead">
      The other half of the idea: paste a draft you are about to send, and see what it
      leaves unsaid before the other person has to guess.
    </p>
    <p class="soon__note">
      It is not built yet. Decoding a message you have received works today.
    </p>
    <div class="soon__actions">
      <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
      <RouterLink to="/library" class="btn btn--secondary">Browse the pattern library</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.soon {
  max-width: 560px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 14px;
  padding-top: 8px;
}

.soon__badge {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--color-surface-soft);
  border: 1px solid var(--color-border);
  color: var(--color-text-muted);
}

.soon h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 34px;
  font-weight: 500;
  letter-spacing: -0.018em;
  color: var(--color-text);
}

.soon__lead {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 17px;
  line-height: 1.62;
  color: var(--color-text);
}

.soon__note {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-muted);
}

.soon__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
}

.btn {
  padding: 12px 20px;
  border-radius: var(--radius-sm);
  font-size: 14.5px;
  cursor: pointer;
  text-decoration: none;
}
</style>

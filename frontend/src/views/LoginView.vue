<script setup lang="ts">
// Not built yet - see ComposeView for the same reasoning. Worth being plain
// about: nothing on this site needs an account today, and everything it
// remembers is already on this device.
</script>

<template>
  <div class="soon">
    <span class="soon__badge">Coming soon</span>
    <h1>Accounts</h1>
    <p class="soon__lead">
      Signing in would let your saved cards follow you between devices.
    </p>
    <p class="soon__note">
      There is nothing to sign in to yet, and nothing here needs an account. Your cards
      and settings are stored in this browser only &mdash;
      <RouterLink to="/privacy">what that means</RouterLink>.
    </p>
    <div class="soon__actions">
      <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
      <RouterLink to="/study" class="btn btn--secondary">See your saved cards</RouterLink>
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

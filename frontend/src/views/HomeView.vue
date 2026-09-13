<script setup lang="ts">
import heroImage from '@/assets/home-hero.jpg'

interface FeatureCard {
  title: string
  desc: string
  to: string | null
  cta: string | null
  status: 'live' | 'soon'
}

const FEATURES: FeatureCard[] = [
  {
    title: 'Message Decoder',
    desc: "Paste a long email and get what's covered, what's missing, and a suggested next step — plus a draft reply asking for exactly what's unclear.",
    to: '/decode',
    cta: 'Decode message',
    status: 'live',
  },
  {
    title: 'Pattern Library',
    desc: 'Browse common workplace phrasings by category — softened requests, vague deadlines, feedback framing — and what they actually imply.',
    to: '/library',
    cta: 'Browse the library',
    status: 'live',
  },
  {
    title: 'Study & Flashcards',
    desc: 'Turn anything you decode or look up into a flashcard. No scores, no streaks — cards you haven’t opened in a while just float a little higher.',
    to: '/study',
    cta: 'Open Study',
    status: 'live',
  },
  {
    title: 'Comfort Settings',
    desc: 'Switch to dark mode, pick an accent color, and resize or bold the text so the page fits how you read best.',
    to: '/settings',
    cta: 'Adjust settings',
    status: 'live',
  },
  {
    title: 'Message Drafter',
    desc: 'For the writing side: paste a message before you send it and see what a neurodivergent reader might find missing.',
    to: null,
    cta: null,
    status: 'soon',
  },
  {
    title: 'Accounts & Progress',
    desc: 'An optional account to keep your history across devices and notice the situations you tend to find unclear.',
    to: null,
    cta: null,
    status: 'soon',
  },
]
</script>

<template>
  <section class="hero-section">
    <img :src="heroImage" alt="A team celebrating together around a meeting table" class="hero-bg-img" />
    <div class="hero-scrim" />
    <div class="hero-inner">
      <div class="hero-panel">
        <h1 class="hero-title">Signals in many forms, <br />A bridge to shared understanding.</h1>
        <p class="hero-subtitle">
          Clearly takes a message apart: what it covers, what it leaves out,
          what the polite wording implies, and what to do next.
          It checks messages you send the same way, before they go out.
        </p>
        <div class="actions">
          <RouterLink to="/decode" class="btn btn--primary">Decode a message</RouterLink>
          <RouterLink to="/compose" class="btn btn--secondary">Compose a message</RouterLink>
        </div>
      </div>
    </div>
  </section>
  <div class="home">
    <section class="features">
      <h2>What we provide</h2>
      <div class="feature-grid">
        <component
          :is="feature.to ? 'RouterLink' : 'div'"
          v-for="feature in FEATURES"
          :key="feature.title"
          :to="feature.to ?? undefined"
          class="feature"
          :class="{ 'feature--soon': feature.status === 'soon' }"
        >
          <div class="feature__head">
            <strong>{{ feature.title }}</strong>
            <span v-if="feature.status === 'soon'" class="badge">Coming soon</span>
          </div>
          <span class="feature__desc">{{ feature.desc }}</span>
          <span v-if="feature.cta" class="feature__cta">{{ feature.cta }}</span>
        </component>
      </div>
    </section>

  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 44px;
  padding-top: 8px;
  padding-bottom: 16px;
}

/* Breaks out of AppShell's centered, padded `.main__inner` (max-width
   1240px) so the photo runs edge-to-edge instead of stopping at that
   container's width. The negative top margin cancels out `.main`'s own
   top padding (32px, 24px under 860px - see AppShell.vue) so the photo
   sits flush under the sticky header instead of leaving a bare strip. */
.hero-section {
  position: relative;
  width: 100vw;
  margin-left: calc(50% - 50vw);
  margin-right: calc(50% - 50vw);
  margin-top: -32px;
  margin-bottom: 32px;
  height: 72vh;
  min-height: 420px;
  display: flex;
  align-items: center;
  overflow: hidden;
}

.hero-bg-img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 0;
}

/* Darkens the photo so the white text stays readable over it. */
.hero-scrim {
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, rgba(0, 0, 0, 0.62) 0%, rgba(0, 0, 0, 0.1) 100%);
  z-index: 1;
}

/* Re-establishes the same content column the rest of the page uses
   (AppShell's `.main__inner`/`.main`), now that the section itself has
   broken out of it. */
.hero-inner {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 1240px;
  margin: 0 auto;
  padding: 0 24px;
}

.hero-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 620px;
  font-style: italic;
}

.hero-title {
  font-family: var(--font-serif);
  font-size: 42px;
  line-height: 1.14;
  font-weight: 500;
  letter-spacing: -0.02em;
  margin: 0;
  color: #ffffff;
}

.hero-subtitle {
  margin: 0;
  font-size: 16.5px;
  line-height: 1.62;
  color: rgba(255, 255, 255, 0.88);
}

@media (max-width: 720px) {
  .hero-title {
    font-size: 31px;
  }
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-style: normal;
  margin-top: 4px;
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

.moments {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1px;
  background: var(--color-border-soft);
  border: 1px solid var(--color-border-soft);
  border-radius: 12px;
  overflow: hidden;
}

.moment {
  background: var(--color-surface-soft);
  padding: 20px 22px;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.moment strong {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
}

.moment span {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.features h2 {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 500;
  letter-spacing: -0.015em;
  margin: 0 0 18px;
  color: var(--color-text);
}

.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
}

.feature {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 18px 18px 20px;
  border: 1px solid var(--color-border-soft);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  color: inherit;
}

a.feature:hover {
  border-color: var(--color-primary-soft-border);
  background: var(--color-primary-soft-bg);
}

.feature--soon {
  background: var(--color-surface-soft);
}

.feature__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.feature__head strong {
  font-size: 14.5px;
  font-weight: 600;
  color: var(--color-text);
}

.badge {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--color-warn-bg);
  color: var(--color-warn-text);
  border: 1px solid var(--color-warn-border);
}

.feature__desc {
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--color-text-muted);
}

.feature__cta {
  margin-top: auto;
  padding-top: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary-strong-text);
}

.closing {
  border-top: 1px solid var(--color-border-soft);
  padding-top: 20px;
}

.closing p {
  margin: 0;
  font-size: 13.5px;
  color: var(--color-text-faint);
}

@media (max-width: 860px) {
  .hero-section {
    margin-top: -24px;
  }

  .feature-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .moments {
    grid-template-columns: 1fr;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>

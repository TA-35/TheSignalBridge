<script setup lang="ts">
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
    desc: 'Adjust contrast, typeface, and colour intensity so the page fits how you read best, on desktop or mobile.',
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
  <div class="home">
    <section class="hero">
      <h1>Signals in many forms, <br />A bridge to shared understanding.</h1>
      <p>
        TheSignalBridge helps neurodivergent and neurotypical colleagues read each other's
        messages the same way — less guessing, less rereading, clearer next steps.
      </p>
      <div class="actions">
        <RouterLink to="/decode" class="btn btn--primary">Review a message</RouterLink>
        <RouterLink to="/library" class="btn btn--secondary">Browse the library</RouterLink>
      </div>
    </section>

    <section class="moments">
      <div class="moment">
        <strong>Reading a message</strong>
        <span>Not sure what an email is actually asking? Decode it into what's clear and what's still open.</span>
      </div>
      <div class="moment">
        <strong>Writing a message</strong>
        <span>Sending one instead? The Drafter (coming soon) flags what a reader might miss before it's sent.</span>
      </div>
    </section>

    <section class="features">
      <h2>What's here</h2>
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
          <span v-if="feature.cta" class="feature__cta">{{ feature.cta }} →</span>
        </component>
      </div>
    </section>

    <section class="closing">
      <p>No account needed to start. Sign-in for saved history and progress is on the way.</p>
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

.hero {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 680px;
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
  .feature-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 720px) {
  .hero h1 {
    font-size: 31px;
  }

  .moments {
    grid-template-columns: 1fr;
  }

  .feature-grid {
    grid-template-columns: 1fr;
  }
}
</style>
